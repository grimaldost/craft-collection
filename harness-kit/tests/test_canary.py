#!/usr/bin/env python3
"""Checks of the presence canary that `kit run` runs between preflight and launch.

Contract under test, with the fake harness of `canary_fake_harness.py`:
- the CLI side: with `KIT_CANARY_NONCE` set and the policy loaded, a shell act
  naming `deny-<nonce>.marker` is denied by `canary.deny` and the CLI writes
  `runs/<id>/canary/refused-<nonce>.marker`; one naming `allow-<nonce>.marker`
  is allowed by `canary.allow` ahead of the policy's rules; an unreadable
  policy still reads `unknown`;
- with the guard intact the canary passes whatever the harness's exit code,
  `canary.json` records `passed` and the markers, and the session starts;
- a harness that runs the calls without the guard, runs nothing, runs only
  the allow half, or a home whose guard is broken or whose copy fails, fails
  the canary: exit 65, `outcome` `refused-canary`, no session start, zero
  requests on the session's endpoint;
- a project-config path of the working folder is copied into the canary's
  work folder byte for byte;
- a harness that hangs with a grandchild is ended at the deadline with reason
  `timeout`, and the grandchild never writes its late marker.

Stdlib-runnable: `python test_canary.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import harnesses, launcher, state, stubmodel
from kit_fixtures import SRC, event, run_module

WINDOWS = os.name == 'nt'
FAKE = Path(__file__).resolve().parent / 'canary_fake_harness.py'
NONCE = '0123456789abcdef'
PINNED = {'claude-code': '2.1.316', 'opencode': '2.2.5'}
SESSION_ARGS = {
    'claude-code': [
        '-p',
        'say hi',
        '--output-format',
        'stream-json',
        '--verbose',
        '--model',
        'stub-model',
        '--setting-sources',
        'user',
        '--allowedTools',
        'Bash',
    ],
    'opencode': ['run', '--standalone', '--format', 'json', '--auto', '--model', 'm', 'say hi'],
}
DENY_ALL_SHELL = """
[[rule]]
id = "deny-all-shell"
effect = "deny"
governed = true
kinds = ["shell"]
reason = "every shell call is denied here"
"""


def scratch() -> Path:
    return Path(os.path.realpath(tempfile.mkdtemp(prefix='kit-canary-')))


def base_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('KIT_', 'GIT_'))}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def kit(*args: str, env: dict, stdin: bytes = b'') -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=180,
    )


class SessionStub:
    """The session's model endpoint: a stub in a thread, its log beside the case."""

    def __init__(self, log: Path) -> None:
        self.log = log
        self.server = stubmodel.Stub(log, [])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f'http://127.0.0.1:{self.server.port}'

    def requests(self) -> int:
        if not self.log.exists():
            return 0
        return len([line for line in self.log.read_text(encoding='utf-8').splitlines() if line])

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class Case:
    """A state root, a test folder, a policy, a session stub and a rendered home."""

    def __init__(self, base: Path, harness: str, mode: str = 'guarded', code: int = 0):
        self.base = base
        self.harness = harness
        self.state = base / 'state'
        self.work = base / 'tests' / 'work'
        self.work.mkdir(parents=True)
        self.out = base / 'fake-out.json'
        self.argv = [sys.executable, str(FAKE), str(self.out), PINNED[harness], str(code), mode]
        self.policy = base / 'policy.toml'
        roots = json.dumps(str(base / 'tests'))
        self.policy.write_text(
            f'version = 1\n\n[launcher]\ntest_roots = [{roots}]\nforbidden_roots = []\n',
            encoding='utf-8',
        )
        self.stub = SessionStub(base / 'session-stub.ndjson')
        self.home = base / f'home-{harness}'
        render = kit(
            'home',
            'render',
            '--harness',
            harness,
            '--dir',
            str(self.home),
            '--endpoint',
            self.stub.endpoint,
            env=self.env(),
        )
        assert render.returncode == 0, render.stderr

    def env(self, **extra: str) -> dict:
        return base_env(
            KIT_STATE_ROOT=str(self.state),
            KIT_HARNESS_ARGV_CLAUDE_CODE=json.dumps(self.argv),
            KIT_HARNESS_ARGV_OPENCODE=json.dumps(self.argv),
            **extra,
        )

    def run(self, **extra: str) -> subprocess.CompletedProcess:
        args = [
            'run',
            '--harness',
            self.harness,
            '--home',
            str(self.home),
            '--workdir',
            str(self.work),
            '--policy',
            str(self.policy),
            '--',
            *SESSION_ARGS[self.harness],
        ]
        return kit(*args, env=self.env(**extra))

    def run_dir(self) -> Path:
        found = sorted((self.state / 'runs').glob('*/run.json'))
        assert len(found) == 1, found
        return found[0].parent

    def run_json(self) -> dict:
        return json.loads((self.run_dir() / 'run.json').read_text(encoding='utf-8'))

    def canary_json(self) -> dict:
        return json.loads((self.run_dir() / 'canary' / 'canary.json').read_text(encoding='utf-8'))

    def close(self) -> None:
        self.stub.close()
        shutil.rmtree(self.base, ignore_errors=True)


def with_case(
    harness: str, body, mode: str = 'guarded', code: int = 0, setup=None, env=None
) -> None:
    case = Case(scratch(), harness, mode=mode, code=code)
    try:
        if setup:
            setup(case)
        proc = case.run(**(env or {}))
        try:
            body(case, proc)
        except AssertionError as exc:
            detail = proc.stderr.decode('utf-8', 'replace')
            raise AssertionError(f'{harness} {mode} {code}: {exc}; stderr {detail!r}') from None
    finally:
        case.close()


def assert_passed(case: Case, proc: subprocess.CompletedProcess, code: int) -> None:
    assert proc.returncode == code, proc.returncode
    assert case.out.exists(), 'the session did not start'
    record = case.canary_json()
    assert record['passed'] is True, record
    assert record['refused_marker'] and record['allow_marker'], record
    assert not record['deny_marker'], record
    assert record['stub_requests'] >= 2, record
    run = case.run_json()
    assert run['outcome'] == 'ended' and run['exit_code'] == code, run


def assert_failed(case: Case, proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 65, proc.returncode
    assert not case.out.exists(), 'the session started'
    assert case.stub.requests() == 0, 'the session endpoint was reached'
    assert not case.stub.log.exists(), 'the session stub log exists'
    assert case.run_json()['outcome'] == 'refused-canary', case.run_json()
    lines = proc.stderr.decode('utf-8', 'replace').splitlines()
    assert len(lines) == 1 and 'canary' in lines[0], lines
    record = case.canary_json()
    assert record['passed'] is False and record['reason'], record
    return record


# ---- the CLI side


def _judge_case(policy_extra: str = '') -> tuple[Path, dict]:
    base = scratch()
    policy = base / 'policy.toml'
    policy.write_text(
        'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n' + policy_extra,
        encoding='utf-8',
    )
    env = base_env(KIT_STATE_ROOT=str(base / 'state'), KIT_POLICY=str(policy))
    minted = kit('state', 'new-run', '--harness', 'opencode', env=env)
    assert minted.returncode == 0, minted.stderr
    run_id = json.loads(minted.stdout)['run_id']
    env.update(KIT_RUN_ID=run_id, KIT_CANARY_NONCE=NONCE)
    return base, env


def _judge(env: dict, command: str) -> dict:
    ev = event(**{'harness.name': 'opencode', 'harness.version': '2.2.5', 'act.command': command})
    proc = kit('judge', env=env, stdin=json.dumps(ev).encode('ascii'))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_canary_deny_rule_refuses_and_writes_the_refused_marker():
    base, env = _judge_case()
    try:
        verdict = _judge(env, f'echo probe > deny-{NONCE}.marker')
        assert verdict['verdict'] == 'deny' and verdict['rule'] == 'canary.deny', verdict
        assert verdict['launched'] is True, verdict
        marker = base / 'state' / 'runs' / env['KIT_RUN_ID'] / 'canary' / f'refused-{NONCE}.marker'
        assert marker.is_file(), marker
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_canary_allow_rule_comes_ahead_of_the_policy():
    base, env = _judge_case(DENY_ALL_SHELL)
    try:
        verdict = _judge(env, f'echo probe > allow-{NONCE}.marker')
        assert verdict['verdict'] == 'allow' and verdict['rule'] == 'canary.allow', verdict
        other = _judge(env, 'echo probe > other.marker')
        assert other['rule'] == 'deny-all-shell', other
        no_nonce = dict(env)
        del no_nonce['KIT_CANARY_NONCE']
        plain = _judge(no_nonce, f'echo probe > allow-{NONCE}.marker')
        assert plain['rule'] == 'deny-all-shell', plain
        runs = base / 'state' / 'runs' / env['KIT_RUN_ID']
        assert not (runs / 'canary').exists(), 'a refused marker was written for an allow'
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_canary_rules_need_a_policy_that_loads():
    base, env = _judge_case('\n[[rule]]\nid = "bad"\n')
    try:
        verdict = _judge(env, f'echo probe > allow-{NONCE}.marker')
        assert verdict['verdict'] == 'unknown' and verdict['effect'] == 'deny', verdict
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_canary_rules_read_only_an_observed_shell_command():
    from harness_kit.policy import load_policy_text
    from harness_kit.verdict import judge

    policy = load_policy_text('version = 1\n' + DENY_ALL_SHELL)
    name = f'/w/deny-{NONCE}.marker'
    write = event(
        **{
            'act.kind': 'file_write',
            'act.command': None,
            'act.paths': [name],
            'observation.command': 'not_applicable',
            'observation.paths': 'observed',
        }
    )
    assert judge(write, policy, True, NONCE)['rule'] is None
    hidden = event(**{'act.command': f'echo > allow-{NONCE}.marker'})
    hidden['observation']['command'] = 'unavailable'
    assert judge(hidden, policy, True, NONCE)['rule'] == 'deny-all-shell'
    shown = event(**{'act.command': f'echo > allow-{NONCE}.marker'})
    assert judge(shown, policy, True, NONCE)['rule'] == 'canary.allow'
    assert judge(shown, policy, True, None)['rule'] == 'deny-all-shell'


def test_canary_stub_keeps_connection_errors_off_kits_stderr():
    import contextlib
    import io

    from harness_kit import canary

    base = scratch()
    try:
        stub = canary.make_stub(base / 'stub.ndjson', [])
        caught = io.StringIO()
        try:
            with contextlib.redirect_stderr(caught):
                try:
                    raise ConnectionResetError(10054, 'reset by the harness')
                except ConnectionResetError:
                    stub.handle_error(None, ('127.0.0.1', 1))
        finally:
            stub.server_close()
        assert caught.getvalue() == '', caught.getvalue()
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- kit run with the canary


def test_canary_passes_with_the_guard_intact_whatever_the_exit_code():
    for harness, code in (('claude-code', 0), ('claude-code', 37), ('opencode', 1)):
        with_case(harness, lambda c, p, k=code: assert_passed(c, p, k), code=code)


def test_canary_fails_when_the_harness_does_not_honour_the_guard():
    for harness, mode in (
        ('opencode', 'unguarded'),
        ('opencode', 'nothing'),
        ('opencode', 'allow-only'),
        ('claude-code', 'unguarded'),
    ):
        with_case(harness, lambda c, p: assert_failed(c, p), mode=mode)


def test_canary_markers_are_recorded_on_failure():
    def body(case, proc):
        record = assert_failed(case, proc)
        assert record['deny_marker'] is True and record['allow_marker'] is True, record
        assert record['refused_marker'] is False, record

    with_case('opencode', body, mode='unguarded')


def test_canary_fails_on_a_broken_home():
    def malformed(case):
        (case.home / 'claude-config' / 'settings.json').write_text('{"hooks": ', encoding='utf-8')

    with_case('claude-code', lambda c, p: assert_failed(c, p), setup=malformed)

    def plugin_gone(case):
        shutil.rmtree(case.home / 'kit-shell' / 'opencode-plugin')

    with_case('opencode', lambda c, p: assert_failed(c, p), setup=plugin_gone)


def test_canary_fails_when_the_home_copy_fails():
    def other_endpoint(case):
        config = case.home / 'conf' / 'opencode.jsonc'
        text = config.read_text(encoding='utf-8')
        config.write_text(text.replace(case.stub.endpoint, 'http://127.0.0.1:1'), encoding='utf-8')

    def body(case, proc):
        record = assert_failed(case, proc)
        assert 'copy' in record['reason'], record

    with_case('opencode', body, setup=other_endpoint)


def test_project_config_of_the_working_folder_reaches_the_canary():
    for harness, entry in (
        ('claude-code', '.claude/settings.json'),
        ('opencode', 'opencode.jsonc'),
    ):
        data = b'{"planted": "project layer"}\n'

        def setup(case, entry=entry, data=data):
            path = case.work / entry
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        def body(case, proc, entry=entry, data=data):
            assert_passed(case, proc, 0)
            copied = case.run_dir() / 'canary' / 'work' / entry
            assert copied.read_bytes() == data, copied

        with_case(harness, body, setup=setup)


def test_canary_passes_with_system_names_planted_in_kits_environment():
    if not WINDOWS:
        return
    planted = {'SYSTEMROOT': r'C:\planted-root', 'WINDIR': r'C:\planted-win'}
    with_case('opencode', lambda c, p: assert_passed(c, p, 0), env=planted)


# ---- the deadline


def _alive(pid: int) -> bool:
    if not WINDOWS:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes

    k32 = ctypes.WinDLL('kernel32')
    k32.OpenProcess.restype = ctypes.c_void_p
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    try:
        k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))
    return code.value == 259  # STILL_ACTIVE


def test_hung_harness_is_ended_at_the_deadline_with_its_grandchild():
    base = scratch()
    try:
        root = base / 'state'
        out = base / 'fake-out.json'
        argv = [sys.executable, str(FAKE), str(out), '2.2.5', '0', 'hang']
        driver = harnesses.get('opencode')
        home = driver.render_home(base / 'home', 'http://127.0.0.1:9')
        policy = base / 'policy.toml'
        policy.write_text('version = 1\n', encoding='utf-8')
        run_id, run_dir = state.mint_run(root, driver.name)
        for name in ('tmp', 'gh-config'):
            (run_dir / name).mkdir()
        environ = base_env()

        def make_env(copy: dict, work: Path) -> dict:
            env, _ = launcher.build_env(
                driver,
                copy,
                environ,
                run_dir=run_dir,
                run_id=run_id,
                root=root,
                policy_path=policy,
                workdir=work,
            )
            return env

        work = base / 'work'
        work.mkdir()
        from harness_kit import canary

        start = time.monotonic()
        result = canary.run_canary(
            driver,
            home,
            argv,
            run_dir=run_dir,
            workdir=work,
            project_config=[],
            make_env=make_env,
            timeout_s=2,
        )
        took = time.monotonic() - start
        assert result['passed'] is False and result['reason'] == 'timeout', result
        assert took < 15, took
        pid = int(Path(str(out) + '.grandchild-pid').read_text(encoding='ascii'))
        time.sleep(6)
        assert not Path(str(out) + '.late').exists(), 'the grandchild outlived the canary'
        assert not _alive(pid), pid
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'presence canary')

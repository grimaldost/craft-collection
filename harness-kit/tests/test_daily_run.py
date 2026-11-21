#!/usr/bin/env python3
"""Checks of `kit run` on a daily home, with a fake harness, the relay and a stub upstream.

Contract under test, with the fake harness of `daily_fake_harness.py` named through
`KIT_HARNESS_ARGV_OPENCODE`, a daily file whose `test` is true, an upstream that is a stub on
127.0.0.1 and a key variable holding a made-up value:
- the order: the relay is not listening while the canary runs and is listening when the session
  starts; the session's request reaches the upstream through the relay, whose ledger holds its
  `reserve` and `settle` lines; `run.json` gets `relay` with exactly `requests`, `refused`,
  `settled_usd` and `stopped`; afterwards no relay holds the port or the ledger's lock, and
  `runs/<id>/relay-stderr.txt` exists;
- the session's environment holds `KIT_RELAY_CAPABILITY` (64 lowercase hex) and neither the key
  variable's name nor its value, no `SESSION_WORKFLOW_GOVERNED_HOME`, and `GIT_CONFIG_GLOBAL`
  naming the run's copy of the home's `gitconfig`; the canary's capability differs from the
  session's; the version probe's environment and preflight's `git` hold neither the key nor any
  other variable the secret-name rule matches;
- a daily home is refused with exit 64 and no run when its daily file is absent, changed (naming
  exactly the keys whose value differs), or invalid, when the key variable is absent or empty,
  when the listen port is bound, when the relay lock is held, when the day or month total is at
  its ceiling, when a rendered file changed, and when it holds `run-open.json`, in headless mode;
- a relay that exits before its ready line (a key with a space) gives `refused-relay`, exit 70
  and no session; a home file changed while the relay replays its ledger gives
  `refused-home-changed`, exit 65 and no session.

Stdlib-runnable: `python test_daily_run.py`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import launcher, relay, stubmodel
from kit_fixtures import SRC, run_module

WINDOWS = os.name == 'nt'
FAKE = Path(__file__).resolve().parent / 'daily_fake_harness.py'
KEY_ENV = 'TEST_DAILY_RELAY_KEY'
KEY = 'made-up-relay-key-5e1d0c3b9a7f'
OTHER_SECRET = ('TEST_OTHER_TOKEN', 'made-up-other-token-77aa')
MODEL_ID = 'vendor/model-a'
ARGS = ['run', '--standalone', '--format', 'json', '--auto', '--model', 'relay/' + MODEL_ID, 'hi']
CAPABILITY = re.compile(r'[0-9a-f]{64}')


def scratch() -> Path:
    return Path(os.path.realpath(tempfile.mkdtemp(prefix='kit-daily-run-')))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def daily_text(port: int, upstream: str, **over: object) -> str:
    values = {'run_usd': 5.0, 'day_usd': 50.0, 'month_usd': 500.0, 'upstream': upstream}
    values.update(over)
    # The numbers below are an example.
    return f"""\
daily = 1

[relay]
listen_port = {port}
upstream_base = "{values['upstream']}"
route = "/v1/chat/completions"
key_env = "{KEY_ENV}"
test = true
usage_include = true
default_model = "{MODEL_ID}"
upstream_timeout_s = 30

[relay.ceilings]
run_usd = {values['run_usd']}
day_usd = {values['day_usd']}
month_usd = {values['month_usd']}

[[relay.model]]
id = "{MODEL_ID}"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 1.0
max_output_tokens = 1000

[git]
name = "Daily Person"
email = "daily.person@example.invalid"
"""


class Case:
    """A state root, a test folder, a policy, an upstream stub, a daily file and its home."""

    def __init__(self, mode: str = 'guarded', **over: object) -> None:
        self.base = scratch()
        self.state = self.base / 'state'
        self.tests = self.base / 'tests'
        self.work = self.tests / 'work'
        self.work.mkdir(parents=True)
        self.out = self.base / 'fake-out.json'
        self.upstream = stubmodel.Stub(self.base / 'upstream.ndjson', [{'text': 'done'}])
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()
        self.port = free_port()
        self.daily = self.base / 'daily.toml'
        upstream = f'http://127.0.0.1:{self.upstream.port}'
        self.daily.write_text(daily_text(self.port, upstream, **over), encoding='utf-8')
        self.policy = self.base / 'policy.toml'
        roots = json.dumps(str(self.tests))
        self.policy.write_text(
            f'version = 1\n\n[launcher]\ntest_roots = [{roots}]\nforbidden_roots = []\n',
            encoding='utf-8',
        )
        options = {'probe_port': self.port, 'model': MODEL_ID}
        self.argv = [sys.executable, str(FAKE), str(self.out), '2.2.5', '0', mode]
        self.argv.append(json.dumps(options))
        self.home = self.base / 'home'
        proc = self.kit(
            'home',
            'render',
            '--harness',
            'opencode',
            '--dir',
            str(self.home),
            '--daily',
            str(self.daily),
        )
        assert proc.returncode == 0, proc.stderr

    def env(self, **extra: str) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('KIT_', 'GIT_'))}
        # No secret of the shell running the tests, nor the app's own names, reaches a case.
        env = {k: v for k, v in env.items() if not launcher.SECRET_NAME.search(k)}
        env = {k: v for k, v in env.items() if not k.upper().startswith(('CLAUDE', 'ANTHROPIC'))}
        env.pop('PYTHONIOENCODING', None)
        env.pop('SESSION_WORKFLOW_GOVERNED_HOME', None)
        env['PYTHONPATH'] = str(SRC)
        env['KIT_STATE_ROOT'] = str(self.state)
        env['KIT_HARNESS_ARGV_OPENCODE'] = json.dumps(self.argv)
        env[KEY_ENV] = KEY
        env[OTHER_SECRET[0]] = OTHER_SECRET[1]
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def kit(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, '-m', 'harness_kit', *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env if env is not None else self.env(),
            cwd=str(self.base),
            timeout=180,
        )

    def run(self, **extra: str) -> subprocess.CompletedProcess:
        head = ['run', '--harness', 'opencode', '--home', str(self.home)]
        head += ['--workdir', str(self.work), '--policy', str(self.policy), '--']
        return self.kit(*head, *ARGS, env=self.env(**extra))

    def runs(self) -> list[Path]:
        folder = self.state / 'runs'
        return sorted(folder.glob('*/run.json')) if folder.is_dir() else []

    def run_dir(self) -> Path:
        found = self.runs()
        assert len(found) == 1, found
        return found[0].parent

    def run_json(self) -> dict:
        return json.loads((self.run_dir() / 'run.json').read_text(encoding='utf-8'))

    def seen(self, suffix: str = '') -> dict:
        return json.loads(Path(str(self.out) + suffix).read_text(encoding='utf-8'))

    def upstream_lines(self) -> list[dict]:
        log = self.base / 'upstream.ndjson'
        if not log.is_file():
            return []
        return [json.loads(x) for x in log.read_text(encoding='utf-8').splitlines() if x]

    def close(self) -> None:
        self.upstream.shutdown()
        self.upstream.server_close()
        shutil.rmtree(self.base, ignore_errors=True)


def upper(env: dict) -> dict:
    return {k.upper(): v for k, v in env.items()}


def assert_no_secret(env: dict, where: str) -> None:
    names = upper(env)
    assert KEY_ENV not in names and OTHER_SECRET[0] not in names, (where, sorted(names))
    text = json.dumps(env)
    assert KEY not in text and OTHER_SECRET[1] not in text, where


def assert_refused(case: Case, proc: subprocess.CompletedProcess, *needles: str) -> str:
    assert proc.returncode == 64, (proc.returncode, proc.stderr)
    lines = proc.stderr.splitlines()
    assert len(lines) == 1, lines
    for needle in needles:
        assert needle in lines[0], (needle, lines)
    assert KEY not in proc.stderr
    assert not case.out.exists(), 'the harness was started'
    assert case.runs() == [], case.runs()
    return lines[0]


def relay_is_gone(case: Case) -> bool:
    lock = case.state / 'relay' / relay.LOCK
    if not lock.exists():
        return launcher.port_free(case.port)
    fd = os.open(lock, os.O_RDWR | getattr(os, 'O_BINARY', 0))
    try:
        free = relay._try_lock(fd)
        if free:
            relay._unlock(fd)
    finally:
        os.close(fd)
    return free and launcher.port_free(case.port)


def ledger_lines(case: Case) -> list[dict]:
    path = case.state / 'relay' / relay.LEDGER
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x]


# ---- a daily run


def test_a_daily_run_starts_the_relay_after_the_canary_and_records_it():
    case = Case()
    try:
        proc = case.run()
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        assert KEY not in proc.stderr and KEY not in proc.stdout
        assert case.seen('.canary-probe.json') == {'listening': False}
        seen = case.seen()
        assert seen['listening'] is True and seen['relay_status'] == 200, seen
        run_dir = case.run_dir()
        run_id = run_dir.name
        record = case.run_json()
        assert record['outcome'] == 'ended' and record['exit_code'] == 0, record
        stats = record['relay']
        assert sorted(stats) == ['refused', 'requests', 'settled_usd', 'stopped'], stats
        assert stats['requests'] == 1 and stats['refused'] == 0 and stats['stopped'] is False
        assert stats['settled_usd'] > 0, stats
        assert len([x for x in case.upstream_lines() if x.get('kind') == 'POST']) == 1
        kinds = [(x['kind'], x['run_id']) for x in ledger_lines(case)]
        assert kinds == [('reserve', run_id), ('settle', run_id)], kinds
        log = (run_dir / relay.LOG).read_text(encoding='utf-8').splitlines()
        assert len(log) == 1 and json.loads(log[0])['decision'] == 'forwarded', log
        assert (run_dir / 'relay-stderr.txt').is_file()
        assert seen['run_open'] is not None and run_id in seen['run_open'], seen['run_open']
        assert not (case.home / 'run-open.json').exists()
        assert relay_is_gone(case), 'a relay was left'
    finally:
        case.close()


def test_the_session_holds_the_capability_and_no_key():
    case = Case()
    try:
        proc = case.run()
        assert proc.returncode == 0, proc.stderr
        session = upper(case.seen()['env'])
        canary = upper(case.seen('.canary-env.json'))
        assert CAPABILITY.fullmatch(session['KIT_RELAY_CAPABILITY']), session
        assert CAPABILITY.fullmatch(canary['KIT_RELAY_CAPABILITY']), canary
        assert session['KIT_RELAY_CAPABILITY'] != canary['KIT_RELAY_CAPABILITY']
        assert 'SESSION_WORKFLOW_GOVERNED_HOME' not in session
        for where, env in (('session', session), ('canary', canary)):
            assert_no_secret(env, where)
        assert_no_secret(case.seen('.version-env.json'), 'version probe')
        run_dir = case.run_dir()
        assert session['GIT_CONFIG_GLOBAL'] == str(run_dir / 'gitconfig'), session
        home_config = (case.home / 'gitconfig').read_bytes()
        assert (run_dir / 'gitconfig').read_bytes() == home_config
        for path in [*case.state.rglob('*'), *case.home.rglob('*'), *case.work.rglob('*')]:
            if path.is_file():
                assert KEY.encode() not in path.read_bytes(), path
    finally:
        case.close()


def test_preflight_git_takes_no_secret_of_kits_environment():
    case = Case()
    calls = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        if argv and argv[0] == 'git':
            calls.append(dict(kwargs.get('env') or os.environ))
        return real(argv, *args, **kwargs)

    environ = case.env()
    git_folder = case.tests / 'repo'
    git_folder.mkdir()
    subprocess.run(['git', 'init', '-q', str(git_folder)], check=True, env=environ)  # noqa: S603, S607
    saved = dict(os.environ)
    os.environ.update({KEY_ENV: KEY, OTHER_SECRET[0]: OTHER_SECRET[1]})
    launcher.subprocess.run = spy
    try:
        plan = launcher.preflight(
            'opencode', str(case.home), str(git_folder), str(case.policy), ARGS, environ
        )
        assert calls, 'preflight ran no git'
        for env in calls:
            assert_no_secret(env, 'git')
        assert KEY_ENV not in upper(environ) and KEY_ENV not in upper(dict(os.environ))
        assert_no_secret(plan.env, 'session')
    finally:
        launcher.subprocess.run = real
        os.environ.clear()
        os.environ.update(saved)
        case.close()


# ---- refusals


def _changed_daily(case: Case, **over: object) -> None:
    upstream = over.pop('upstream', f'http://127.0.0.1:{case.upstream.port}')
    case.daily.write_text(daily_text(case.port, upstream, **over), encoding='utf-8')


def test_a_daily_file_absent_or_changed_is_refused():
    case = Case()
    try:
        moved = case.base / 'moved.toml'
        case.daily.rename(moved)
        assert_refused(case, case.run(), 'daily file', 'absent')
        moved.rename(case.daily)
        _changed_daily(case, day_usd=60.0, upstream='http://127.0.0.1:1')
        line = assert_refused(case, case.run(), 'relay.ceilings.day_usd', 'relay.upstream_base')
        for other in ('run_usd', 'month_usd', 'listen_port', 'git.name'):
            assert other not in line, (other, line)
        assert 'read the file' in line, line
    finally:
        case.close()


def test_an_invalid_daily_file_is_refused():
    case = Case()
    try:
        _changed_daily(case, run_usd=0)
        home = json.loads((case.home / 'home.json').read_text(encoding='utf-8'))
        import hashlib

        home['daily_sha256'] = hashlib.sha256(case.daily.read_bytes()).hexdigest()
        home['daily_settings']['relay']['ceilings']['run_usd'] = 0
        (case.home / 'home.json').write_text(json.dumps(home), encoding='utf-8')
        assert_refused(case, case.run(), 'relay.ceilings.run_usd')
    finally:
        case.close()


def test_an_absent_or_empty_key_variable_is_refused():
    case = Case()
    try:
        assert_refused(case, case.run(**{KEY_ENV: None}), KEY_ENV)
        assert_refused(case, case.run(**{KEY_ENV: ''}), KEY_ENV)
    finally:
        case.close()


def test_a_bound_port_or_a_held_lock_is_refused():
    case = Case()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', case.port))
            sock.listen(1)
            assert_refused(case, case.run(), str(case.port))
        folder = case.state / 'relay'
        folder.mkdir(parents=True)
        fd = os.open(folder / relay.LOCK, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0))
        try:
            assert relay._try_lock(fd)
            assert_refused(case, case.run(), 'lock')
            relay._unlock(fd)
        finally:
            os.close(fd)
    finally:
        case.close()


def _ledger(case: Case, usd: float, stamp: str) -> None:
    folder = case.state / 'relay'
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            'ts_utc': stamp,
            'kind': kind,
            'id': 'r1',
            'run_id': 'earlier',
            'model': MODEL_ID,
            'usd': usd,
        }
        for kind in ('reserve', 'settle')
    ]
    text = ''.join(json.dumps(x) + '\n' for x in lines)
    (folder / relay.LEDGER).write_text(text, encoding='utf-8')


def test_a_day_or_month_total_at_its_ceiling_is_refused():
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    case = Case(day_usd=2.0)
    try:
        _ledger(case, 2.0, now)
        assert_refused(case, case.run(), 'day')
    finally:
        case.close()
    case = Case(day_usd=100.0, month_usd=1.0)
    try:
        _ledger(case, 1.5, now)
        assert_refused(case, case.run(), 'month')
    finally:
        case.close()


def test_a_changed_render_or_an_open_run_is_refused_in_headless_mode():
    case = Case()
    try:
        config = case.home / 'conf' / 'opencode.jsonc'
        original = config.read_bytes()
        config.write_bytes(original + b' ')
        assert_refused(case, case.run(), 'render')
        config.write_bytes(original)
        gitconfig = case.home / 'gitconfig'
        kept = gitconfig.read_bytes()
        gitconfig.write_bytes(kept + b'[core]\n')
        assert_refused(case, case.run(), 'gitconfig')
        gitconfig.write_bytes(kept)
        foreign = '20261118T000000Z-0123456789ab'
        (case.home / 'run-open.json').write_text(json.dumps({'run_id': foreign}), encoding='utf-8')
        assert_refused(case, case.run(), foreign)
    finally:
        case.close()


# ---- a relay that is not ready, a home changed while it starts


def test_a_relay_that_exits_before_its_ready_line_gives_refused_relay():
    case = Case()
    try:
        proc = case.run(**{KEY_ENV: 'ab cd'})
        assert proc.returncode == 70, (proc.returncode, proc.stderr)
        assert 'ab cd' not in proc.stderr
        assert not case.out.exists(), 'the session started'
        assert case.run_json()['outcome'] == 'refused-relay', case.run_json()
        text = (case.run_dir() / 'relay-stderr.txt').read_text(encoding='utf-8')
        assert text.startswith('kit relay: ') and 'ab cd' not in text, text
        assert relay_is_gone(case)
    finally:
        case.close()


def test_a_home_changed_while_the_relay_replays_its_ledger_is_refused():
    case = Case()
    try:
        folder = case.state / 'relay'
        folder.mkdir(parents=True)
        line = {'ts_utc': '2001-01-01T00:00:00.000000Z', 'run_id': 'earlier', 'model': MODEL_ID}
        with open(folder / relay.LEDGER, 'w', encoding='utf-8') as fh:
            for i in range(60000):
                for kind in ('reserve', 'settle'):
                    fh.write(json.dumps({**line, 'kind': kind, 'id': f'r{i}', 'usd': 0.001}) + '\n')
        config = case.home / 'conf' / 'opencode.jsonc'
        done = threading.Event()

        def change_once_the_relay_starts() -> None:
            while not done.is_set():
                if list(case.state.glob('runs/*/relay-stderr.txt')):
                    config.write_bytes(config.read_bytes() + b' ')
                    return
                time.sleep(0.002)

        watcher = threading.Thread(target=change_once_the_relay_starts, daemon=True)
        watcher.start()
        proc = case.run()
        done.set()
        assert proc.returncode == 65, (proc.returncode, proc.stderr)
        assert not case.out.exists(), 'the session started'
        assert case.run_json()['outcome'] == 'refused-home-changed', case.run_json()
        assert relay_is_gone(case)
    finally:
        case.close()


if __name__ == '__main__':
    run_module(globals(), 'kit run on a daily home')

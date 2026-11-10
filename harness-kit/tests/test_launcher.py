#!/usr/bin/env python3
"""Checks of the launcher preflight and of `kit run`.

Contract under test, with a fake harness named through `KIT_HARNESS_ARGV_*`:
- every refusal (no home, a home of another harness, a nested launch, a folder
  outside the test roots, a forbidden root over a test root, a pushable remote,
  a no-push clone with a second real push URL, a link out of a test root, a
  missing or doubled required flag, arguments without the leading tokens, a
  flag outside the allow list or in `--flag=value` form, a policy that does not
  load, a project-config path in an ancestor) exits 64 with one stderr line,
  starts nothing and leaves no `run.json`;
- arguments that pass reach the harness unchanged, in the working folder;
- the child's environment is the allow list plus the session's: `TEMP` and
  `TMP` under the run folder, `KIT_RUN_ID` down to a grandchild, no planted
  token, no `CLAUDE_CODE_SIMPLE` or `CLAUDE_CODE_DISABLE_CLAUDE_MDS` (both named
  in `scrubbed`), and on Windows the operating system's `SYSTEMROOT`,
  `WINDIR`, `COMSPEC`, `PROGRAMDATA` and `PATHEXT` whatever kit received;
- `run.json` records the project-config paths of the working folder, the
  remotes, the version found, `launched` then `ended` with the exit code, and
  `kit run` returns the harness's exit code; a version past the pin prints one
  stderr line and still starts.

Stdlib-runnable: `python test_launcher.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from kit_fixtures import SRC, run_module

WINDOWS = os.name == 'nt'
ENDPOINT = 'http://127.0.0.1:43210'
PLANTED_TOKEN = 'planted-token-value-0f9e8d'  # noqa: S105 - a planted test value, no credential
CLAUDE_ARGS = [
    '-p',
    'say hi & 100%',
    '--output-format',
    'stream-json',
    '--verbose',
    '--model',
    'stub-model',
    '--setting-sources',
    'user',
    '--allowedTools',
    'Bash',
]
OPENCODE_ARGS = [
    'run',
    '--standalone',
    '--format',
    'json',
    '--auto',
    '--model',
    'stub/stub-model',
    'say hi & 100%',
]
SESSION_ARGS = {'claude-code': CLAUDE_ARGS, 'opencode': OPENCODE_ARGS}
PINNED = {'claude-code': '2.1.316', 'opencode': '2.2.5'}

FAKE_HARNESS = r"""
import json, os, subprocess, sys
out, version, code = sys.argv[1], sys.argv[2], int(sys.argv[3])
args = sys.argv[4:]
if args == ['--version']:
    print('fake harness ' + version)
    sys.exit(0)
probe = 'import os, sys; open(sys.argv[1], "w").write(os.environ.get("KIT_RUN_ID", "none"))'
subprocess.run([sys.executable, '-c', probe, out + '.grandchild'], check=True)
with open(out, 'w', encoding='utf-8') as fh:
    json.dump({'args': args, 'env': dict(os.environ), 'cwd': os.getcwd()}, fh)
sys.exit(code)
"""


class Case:
    """One scratch base: a state root, a test root, a policy, a rendered home."""

    def __init__(self, base: Path, harness: str, version: str | None = None, code: int = 0):
        self.base = base
        self.harness = harness
        self.state = base / 'state'
        self.tests = base / 'tests'
        self.tests.mkdir(parents=True, exist_ok=True)
        self.work = self.tests / 'work'
        self.work.mkdir(exist_ok=True)
        self.out = base / 'fake-out.json'
        fake = base / 'fake_harness.py'
        fake.write_text(FAKE_HARNESS, encoding='utf-8')
        self.argv = [
            sys.executable,
            str(fake),
            str(self.out),
            version or PINNED[harness],
            str(code),
        ]
        self.home = base / f'home-{harness}'
        self.policy = base / 'policy.toml'
        self.write_policy([self.tests])
        render = kit(
            self,
            'home',
            'render',
            '--harness',
            harness,
            '--dir',
            str(self.home),
            '--endpoint',
            ENDPOINT,
        )
        assert render.returncode == 0, render.stderr

    def write_policy(
        self, test_roots: list[Path], forbidden: list[Path] = (), extra: str = ''
    ) -> None:
        roots = ', '.join(json.dumps(str(p)) for p in test_roots)
        forb = ', '.join(json.dumps(str(p)) for p in forbidden)
        self.policy.write_text(
            f'version = 1\n\n[launcher]\ntest_roots = [{roots}]\nforbidden_roots = [{forb}]\n{extra}',
            encoding='utf-8',
        )

    def env(self, **extra: str) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('KIT_', 'GIT_'))}
        env.pop('PYTHONIOENCODING', None)
        env['PYTHONPATH'] = str(SRC)
        env['KIT_STATE_ROOT'] = str(self.state)
        env['KIT_HARNESS_ARGV_CLAUDE_CODE'] = json.dumps(self.argv)
        env['KIT_HARNESS_ARGV_OPENCODE'] = json.dumps(self.argv)
        env.update(extra)
        return env

    def run(
        self,
        args: list[str] | None = None,
        workdir: Path | None = None,
        home: Path | None = None,
        harness: str | None = None,
        **env: str,
    ) -> subprocess.CompletedProcess:
        return kit(
            self,
            'run',
            '--harness',
            harness or self.harness,
            '--home',
            str(home or self.home),
            '--workdir',
            str(workdir or self.work),
            '--policy',
            str(self.policy),
            '--',
            *(SESSION_ARGS[self.harness] if args is None else args),
            **env,
        )

    def child(self) -> dict:
        return json.loads(self.out.read_text(encoding='utf-8'))

    def runs(self) -> list[Path]:
        return (
            sorted((self.state / 'runs').glob('*/run.json'))
            if (self.state / 'runs').is_dir()
            else []
        )

    def run_json(self) -> dict:
        found = self.runs()
        assert len(found) == 1, found
        return json.loads(found[0].read_text(encoding='utf-8'))


def kit(case: Case, *args: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=case.env(**env),
        cwd=str(case.base),
        timeout=120,
    )


def git(folder: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(folder), *args],  # noqa: S607 - PATH git
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
    )


def scratch() -> Path:
    return Path(os.path.realpath(tempfile.mkdtemp(prefix='kit-launch-')))


def assert_refused(case: Case, proc: subprocess.CompletedProcess, needle: str = '') -> None:
    assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
    lines = proc.stderr.splitlines()
    assert len(lines) == 1, lines
    assert needle.lower() in lines[0].lower(), (needle, lines)
    assert not case.out.exists(), 'the harness was started'
    assert case.runs() == [], case.runs()


def assert_started(case: Case, proc: subprocess.CompletedProcess) -> dict:
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert case.out.exists(), proc.stderr
    return case.child()


def refused(harness: str, label: str, setup, needle: str = '') -> None:
    base = scratch()
    try:
        case = Case(base, harness)
        kwargs = setup(case) or {}
        proc = case.run(**kwargs)
        try:
            assert_refused(case, proc, needle)
        except AssertionError as exc:
            raise AssertionError(f'{harness}: {label}: {exc}') from None
    finally:
        shutil.rmtree(base, ignore_errors=True)


def started(harness: str, setup=None, version: str | None = None, code: int = 0):
    base = scratch()
    case = Case(base, harness, version=version, code=code)
    kwargs = (setup(case) if setup else None) or {}
    return base, case, case.run(**kwargs)


# ---- refusals


def test_no_home_is_refused():
    def setup(case):
        return {'home': case.base / 'no-such-home'}

    refused('opencode', 'no home', setup, 'home')


def test_home_of_another_harness_is_refused():
    def setup(case):
        other = case.base / 'home-other'
        proc = kit(
            case,
            'home',
            'render',
            '--harness',
            'claude-code',
            '--dir',
            str(other),
            '--endpoint',
            ENDPOINT,
        )
        assert proc.returncode == 0
        return {'home': other}

    refused('opencode', 'wrong harness', setup, 'home')


def test_nested_launch_is_refused():
    refused(
        'claude-code',
        'nested',
        lambda c: {'KIT_RUN_ID': '20261109T000000Z-0123456789ab'},
        'KIT_RUN_ID',
    )


def test_folder_outside_the_test_roots_is_refused():
    def setup(case):
        outside = case.base / 'elsewhere'
        outside.mkdir()
        return {'workdir': outside}

    refused('opencode', 'outside test roots', setup, 'test root')


def test_forbidden_root_wins_over_a_test_root():
    refused('opencode', 'forbidden', lambda c: c.write_policy([c.tests], [c.work]), 'forbidden')


def _clone(case: Case, url: str, pushurls: list[str]) -> Path:
    repo = case.base / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'remote', 'add', 'origin', url)
    for n, push in enumerate(pushurls):
        if n == 0:
            git(repo, 'remote', 'set-url', '--push', 'origin', push)
        else:
            git(repo, 'remote', 'set-url', '--add', '--push', 'origin', push)
    return repo


def test_pushable_remote_is_refused():
    refused(
        'opencode',
        'pushable',
        lambda c: {'workdir': _clone(c, 'https://example.invalid/r.git', [])},
        'remote',
    )


def test_no_push_clone_with_a_second_real_pushurl_is_refused():
    def setup(case):
        repo = _clone(
            case, 'https://example.invalid/r.git', ['no_push', 'https://example.invalid/w.git']
        )
        return {'workdir': repo}

    refused('opencode', 'second pushurl', setup, 'remote')


def _link(link: Path, target: Path) -> None:
    if WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_link_out_of_a_test_root_is_refused():
    def setup(case):
        outside = case.base / 'outside'
        outside.mkdir()
        link = case.tests / 'link'
        _link(link, outside)
        return {'workdir': link}

    refused('opencode', 'link out', setup, 'test root')


def test_missing_required_flag_is_refused():
    args = [a for a in OPENCODE_ARGS if a != '--standalone']
    refused('opencode', 'missing flag', lambda c: {'args': args}, '--standalone')
    args = [a for a in CLAUDE_ARGS if a not in ('--setting-sources', 'user')]
    refused('claude-code', 'missing flag', lambda c: {'args': args}, '--setting-sources')


def test_required_flag_given_twice_is_refused():
    args = [*CLAUDE_ARGS[:-2], '--setting-sources', 'user,project', *CLAUDE_ARGS[-2:]]
    refused('claude-code', 'twice', lambda c: {'args': args}, '--setting-sources')
    args = [*OPENCODE_ARGS[:-1], '--standalone', OPENCODE_ARGS[-1]]
    refused('opencode', 'twice', lambda c: {'args': args}, '--standalone')


def test_arguments_without_the_leading_tokens_are_refused():
    refused('opencode', 'serve', lambda c: {'args': ['serve', '--standalone']}, 'run')
    args = CLAUDE_ARGS[2:]
    refused('claude-code', 'no -p', lambda c: {'args': args}, '-p')


def test_flag_outside_the_allow_list_is_refused():
    for flag in ('--bare', '--settings'):
        args = [*CLAUDE_ARGS[:2], flag, *CLAUDE_ARGS[2:]]
        refused('claude-code', flag, lambda c, a=args: {'args': a}, flag)
    args = [*OPENCODE_ARGS[:-1], '--print-logs', OPENCODE_ARGS[-1]]
    refused('opencode', '--print-logs', lambda c: {'args': args}, '--print-logs')


def test_flag_value_form_is_refused():
    args = [*OPENCODE_ARGS[:-1], '--model=stub/other', OPENCODE_ARGS[-1]]
    refused('opencode', '--flag=value', lambda c: {'args': args}, '--model=stub/other')


def test_policy_that_does_not_load_is_refused():
    bad = '\n[[rule]]\nid = "r"\neffect = "deny"\ngoverned = true\nkinds = ["shell"]\ncommand_regex = "(["\n'
    refused('claude-code', 'bad regex', lambda c: c.write_policy([c.tests], extra=bad), 'policy')


def test_project_path_in_an_ancestor_inside_the_work_tree_is_refused():
    def setup(case):
        repo = case.base / 'repo'
        sub = repo / 'sub'
        sub.mkdir(parents=True)
        git(repo, 'init', '-q')
        (repo / '.claude').mkdir()
        (repo / '.claude' / 'settings.json').write_text('{}', encoding='utf-8')
        return {'workdir': sub}

    refused('claude-code', 'ancestor .claude', setup, '.claude')

    def setup_oc(case):
        repo = case.base / 'repo'
        sub = repo / 'sub'
        sub.mkdir(parents=True)
        git(repo, 'init', '-q')
        (repo / 'opencode.json').write_text('{}', encoding='utf-8')
        case.write_policy([case.base])
        return {'workdir': sub}

    refused('opencode', 'ancestor opencode.json', setup_oc, 'opencode.json')


def test_opencode_entry_in_a_parent_outside_any_work_tree_is_refused():
    def setup(case):
        (case.tests / '.opencode').mkdir()
        (case.tests / '.opencode' / 'opencode.json').write_text('{}', encoding='utf-8')

    refused('opencode', 'parent .opencode', setup, '.opencode')


def test_opencode_entry_above_the_state_root_is_refused():
    def setup(case):
        deeper = case.base / 'deeper'
        (deeper / '.opencode').mkdir(parents=True)
        (deeper / '.opencode' / 'opencode.json').write_text('{}', encoding='utf-8')
        return {'KIT_STATE_ROOT': str(deeper / 'state')}

    refused('opencode', 'above the state root', setup, '.opencode')


# ---- launches


def test_arguments_reach_the_harness_unchanged_in_the_working_folder():
    for harness in ('claude-code', 'opencode'):
        base, case, proc = started(harness)
        try:
            child = assert_started(case, proc)
            assert child['args'] == SESSION_ARGS[harness], child['args']
            assert os.path.samefile(child['cwd'], case.work), child['cwd']
            record = case.run_json()
            assert record['outcome'] == 'ended', record
            assert record['exit_code'] == 0, record
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_exit_code_is_returned_and_recorded():
    base, case, proc = started('opencode', code=37)
    try:
        assert proc.returncode == 37, (proc.returncode, proc.stderr)
        record = case.run_json()
        assert record['outcome'] == 'ended' and record['exit_code'] == 37, record
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_child_environment_is_built_by_the_launcher():
    base, case, proc = started(
        'opencode',
        setup=lambda c: {
            'GH_TOKEN': PLANTED_TOKEN,
            'CLAUDE_CODE_SIMPLE': '1',
            'CLAUDE_CODE_DISABLE_CLAUDE_MDS': '1',
        },
    )
    try:
        child = assert_started(case, proc)
        env = child['env']
        run_dir = case.runs()[0].parent
        record = case.run_json()
        for key in ('TEMP', 'TMP'):
            Path(env[key]).relative_to(run_dir)
        assert env['KIT_RUN_ID'] == record['run_id'], env.get('KIT_RUN_ID')
        grand = Path(str(case.out) + '.grandchild').read_text(encoding='utf-8')
        assert grand == record['run_id'], grand
        assert PLANTED_TOKEN not in json.dumps(env), 'planted token reached the child'
        upper = {k.upper() for k in env}
        assert 'CLAUDE_CODE_SIMPLE' not in upper and 'CLAUDE_CODE_DISABLE_CLAUDE_MDS' not in upper
        assert 'CLAUDE_CODE_SIMPLE' in record['scrubbed'], record['scrubbed']
        assert 'CLAUDE_CODE_DISABLE_CLAUDE_MDS' in record['scrubbed'], record['scrubbed']
        assert 'GH_TOKEN' in record['scrubbed'], record['scrubbed']
        for path in case.state.rglob('*'):
            if path.is_file():
                assert PLANTED_TOKEN.encode() not in path.read_bytes(), path
        assert env['PWD'] == record['workdir'], (env['PWD'], record['workdir'])
        assert env['KIT_STATE_ROOT'] and env['KIT_POLICY'], env
        assert env['GIT_CONFIG_NOSYSTEM'] == '1' and env['GIT_TERMINAL_PROMPT'] == '0'
        assert Path(env['GIT_CONFIG_GLOBAL']).read_bytes() == b''
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_windows_names_come_from_the_operating_system():
    if not WINDOWS:
        return
    import ctypes

    buf = ctypes.create_unicode_buffer(512)
    assert ctypes.windll.kernel32.GetSystemWindowsDirectoryW(buf, 512)
    windir = buf.value
    planted = {
        'SYSTEMROOT': r'C:\planted-root',
        'PROGRAMDATA': r'C:\planted-data',
        'COMSPEC': r'C:\planted\cmd.exe',
        'WINDIR': r'C:\planted-win',
    }
    base, case, proc = started('claude-code', setup=lambda c: planted)
    try:
        env = {k.upper(): v for k, v in assert_started(case, proc)['env'].items()}
        assert env['SYSTEMROOT'] == windir and env['WINDIR'] == windir, env['SYSTEMROOT']
        assert env['COMSPEC'].lower() == os.path.join(windir, 'System32', 'cmd.exe').lower()
        assert 'planted' not in env['PROGRAMDATA'] and os.path.isdir(env['PROGRAMDATA'])
        assert '.EXE' in env['PATHEXT'].upper(), env['PATHEXT']
        assert 'SYSTEMROOT' not in case.run_json()['scrubbed']
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_project_path_in_the_working_folder_is_recorded():
    def setup(case):
        (case.work / 'opencode.jsonc').write_text('{}', encoding='utf-8')

    base, case, proc = started('opencode', setup=setup)
    try:
        assert_started(case, proc)
        assert case.run_json()['project_config'] == ['opencode.jsonc']
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_no_push_clone_starts_and_its_remotes_are_recorded():
    def setup(case):
        case.write_policy([])
        return {'workdir': _clone(case, 'https://example.invalid/r.git', ['no_push'])}

    base, case, proc = started('opencode', setup=setup)
    try:
        assert_started(case, proc)
        remotes = case.run_json()['remotes']
        assert [r['name'] for r in remotes] == ['origin'], remotes
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_claude_code_starts_outside_the_test_roots():
    def setup(case):
        outside = case.base / 'elsewhere'
        outside.mkdir()
        return {'workdir': outside}

    base, case, proc = started('claude-code', setup=setup)
    try:
        assert_started(case, proc)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_version_found_is_recorded_and_a_mismatch_is_named():
    base, case, proc = started('claude-code')
    try:
        assert_started(case, proc)
        assert case.run_json()['harness_version_found'] == '2.1.316'
        assert proc.stderr == '', proc.stderr
    finally:
        shutil.rmtree(base, ignore_errors=True)
    base, case, proc = started('claude-code', version='9.9.9')
    try:
        assert_started(case, proc)
        record = case.run_json()
        assert record['harness_version_found'] == '9.9.9', record
        lines = proc.stderr.splitlines()
        assert len(lines) == 1 and '9.9.9' in lines[0] and '2.1.316' in lines[0], lines
        assert isinstance(record['kit_pid'], int) and record['home'] and record['workdir']
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'launcher preflight and kit run')

#!/usr/bin/env python3
"""Checks of the per-harness drivers and of `kit home render`.

Contract under test:
- `harnesses.get(name)` gives the driver of `claude-code` or `opencode`, whose
  pinned version, leading tokens, required session arguments, allowed flags,
  project paths and project walk hold the values of the drivers' contract;
- `kit home render` writes the shell, its `shell_config.json`, the harness
  configuration and `home.json` into an absent or empty folder, prints
  `home.json`, and refuses a non-empty folder with exit 64, writing nothing;
- the rendered `cli_argv` reaches this package whatever `PYTHONPATH` says;
- `session_env` points the home variables inside the home and the proxies at
  the endpoint;
- `copy_home_for_canary` copies byte for byte; on opencode it swaps the
  endpoint text without parsing, so a malformed file stays malformed, and it
  raises when the text is absent;
- `version` reads the first dotted triple from `--version`, run from an empty
  scratch home; a missing binary gives None;
- on Windows a `.cmd` or `.bat` binary is never run: opencode's own shim is
  resolved to the native binary beside it, anything else reads as missing.

Stdlib-runnable: `python test_harnesses.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import harnesses
from kit_fixtures import SRC, run_module

WINDOWS = os.name == 'nt'
ENDPOINT = 'http://127.0.0.1:43210'
CANARY_ENDPOINT = 'http://127.0.0.1:43299'
FAKE_KEY = 'stub-not-a-key'
HOME_KEYS = ['kit_home', 'harness', 'endpoint', 'dir', 'config_file', 'shell_entry', 'shell_config']
HOME_VARS = ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA')


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def _kit(*args: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=_env(**env),
        timeout=60,
    )


def _render(name: str, folder: Path, endpoint: str = ENDPOINT) -> dict:
    proc = _kit('home', 'render', '--harness', name, '--dir', str(folder), '--endpoint', endpoint)
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    printed = json.loads(proc.stdout)
    written = json.loads((folder / 'home.json').read_text(encoding='utf-8'))
    assert printed == written, (printed, written)
    return written


def _inside(path: str, folder: Path) -> bool:
    try:
        Path(path).resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


# ---- driver members


def test_claude_code_driver_members():
    d = harnesses.get('claude-code')
    assert d.name == 'claude-code'
    assert d.pinned_version == '2.1.316'
    assert d.required_leading_tokens == ('-p',)
    assert d.required_session_args == ('--setting-sources', 'user')
    assert d.allowed_session_flags == (
        '-p',
        '--output-format',
        '--verbose',
        '--model',
        '--setting-sources',
        '--allowedTools',
    )
    assert d.project_config_paths == ('.claude/settings.json', '.claude/settings.local.json')
    assert d.project_walk == 'work_tree'


def test_opencode_driver_members():
    d = harnesses.get('opencode')
    assert d.name == 'opencode'
    assert d.pinned_version == '2.2.5'
    assert d.required_leading_tokens == ('run',)
    assert d.required_session_args == ('--standalone',)
    assert d.allowed_session_flags == ('--standalone', '--format', '--auto', '--model')
    assert d.project_config_paths == ('opencode.json', 'opencode.jsonc', '.opencode')
    assert d.project_walk == 'root'


def test_unknown_harness_is_refused():
    try:
        harnesses.get('codex')
    except KeyError:
        return
    raise AssertionError('an unknown harness gave a driver')


def test_claude_code_canary_argv_and_step():
    d = harnesses.get('claude-code')
    argv = d.canary_argv('do the thing')
    assert argv[:2] == ['-p', 'do the thing'], argv
    assert argv[-2:] == ['--allowedTools', 'Bash'], argv
    for flag in ('--output-format', '--verbose', '--model'):
        assert flag in argv, argv
    i = argv.index('--setting-sources')
    assert argv[i + 1] == 'user'
    assert argv[argv.index('--output-format') + 1] == 'stream-json'
    assert [t for t in argv if t.startswith('-')] == [
        '-p',
        '--output-format',
        '--verbose',
        '--model',
        '--setting-sources',
        '--allowedTools',
    ]
    assert d.canary_step('echo x') == {
        'tool': 'Bash',
        'args': {'command': 'echo x', 'description': 'kit canary'},
    }


def test_opencode_canary_argv_and_step():
    d = harnesses.get('opencode')
    assert d.canary_argv('go') == [
        'run',
        '--standalone',
        '--format',
        'json',
        '--auto',
        '--model',
        'stub/stub-model',
        'go',
    ]
    assert d.canary_step('echo x') == {'tool': 'shell', 'args': {'command': 'echo x'}}


# ---- home render


def test_claude_code_home_contents():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'home-cc'
        home = _render('claude-code', folder)
        assert list(home) == HOME_KEYS, list(home)
        assert home['kit_home'] == 1 and home['harness'] == 'claude-code'
        assert home['endpoint'] == ENDPOINT
        assert Path(home['dir']).resolve() == folder.resolve()
        for key in ('config_file', 'shell_entry', 'shell_config'):
            assert Path(home[key]).is_absolute() and Path(home[key]).is_file(), key
            assert _inside(home[key], folder), key
        assert Path(home['config_file']) == folder / 'claude-config' / 'settings.json'
        assert _inside(home['shell_entry'], folder / 'kit-shell')
        assert Path(home['shell_entry']).name == 'kit_hook.py'
        assert Path(home['shell_config']).parent == Path(home['shell_entry']).parent
        settings = json.loads(Path(home['config_file']).read_text(encoding='utf-8'))
        groups = settings['hooks']['PreToolUse']
        assert len(groups) == 1 and len(groups[0]['hooks']) == 1, groups
        assert groups[0]['matcher'] == 'Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit'
        hook = groups[0]['hooks'][0]
        assert hook['type'] == 'command'
        assert Path(hook['command']).is_absolute() and Path(hook['command']).is_file()
        assert hook['args'][0] == '-I' and len(hook['args']) == 2, hook
        assert hook['args'][1] == home['shell_entry'], hook
        assert hook['command'] == sys.executable, hook
        assert hook['timeout'] == 30 and hook['onFailure'] == 'block'
        shipped = SRC / 'harness_kit' / 'shells' / 'claude_code' / 'kit_hook.py'
        assert Path(home['shell_entry']).read_bytes() == shipped.read_bytes()


def test_opencode_home_contents():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'home-oc'
        home = _render('opencode', folder)
        assert list(home) == HOME_KEYS, list(home)
        assert home['harness'] == 'opencode'
        assert Path(home['config_file']) == folder / 'conf' / 'opencode.jsonc'
        plugin = folder / 'kit-shell' / 'opencode-plugin'
        assert Path(home['shell_entry']) == plugin / 'index.js'
        assert Path(home['shell_config']) == plugin / 'shell_config.json'
        cfg = json.loads(Path(home['config_file']).read_text(encoding='utf-8'))
        assert cfg['update'] == 'disable' and cfg['model'] == 'stub/stub-model'
        assert [Path(p) for p in cfg['plugins']] == [plugin], cfg['plugins']
        stub = cfg['providers']['stub']
        assert stub['settings']['baseURL'] == ENDPOINT + '/v1', stub
        assert stub['env'] == ['STUB_API_KEY'] and 'stub-model' in stub['models']
        shipped = SRC / 'harness_kit' / 'shells' / 'opencode' / 'index.js'
        assert Path(home['shell_entry']).read_bytes() == shipped.read_bytes()


def test_shell_config_names_the_pin_and_the_cli():
    for name, pin in (('claude-code', '2.1.316'), ('opencode', '2.2.5')):
        with tempfile.TemporaryDirectory() as td:
            home = _render(name, Path(td) / 'h')
            config = json.loads(Path(home['shell_config']).read_text(encoding='utf-8'))
            assert list(config) == ['kit_shell_config', 'cli_argv', 'timeout_s', 'harness_version']
            assert config['kit_shell_config'] == 1 and config['timeout_s'] == 3
            assert config['harness_version'] == pin
            argv = config['cli_argv']
            assert argv[1:3] == ['-I', '-c'] and argv[-1] == 'judge' and len(argv) == 5, argv
            assert Path(argv[0]).is_absolute()


def test_cli_argv_ignores_pythonpath():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        decoy = base / 'decoy' / 'harness_kit'
        decoy.mkdir(parents=True)
        (decoy / '__init__.py').write_text('raise SystemExit("decoy loaded")\n', encoding='utf-8')
        (decoy / 'cli.py').write_text('raise SystemExit("decoy loaded")\n', encoding='utf-8')
        home = _render('claude-code', base / 'h')
        argv = json.loads(Path(home['shell_config']).read_text(encoding='utf-8'))['cli_argv']
        env = _env(PYTHONPATH=str(base / 'decoy'), KIT_STATE_ROOT=str(base / 'state'))
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            input=b'{}',
            capture_output=True,
            env=env,
            cwd=str(base / 'decoy'),
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        verdict = json.loads(proc.stdout.decode('ascii'))
        assert verdict['kit_verdict'] == 1 and verdict['verdict'] == 'unknown', verdict


def test_non_empty_dir_is_refused_and_untouched():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'busy'
        folder.mkdir()
        (folder / 'keep.txt').write_text('x', encoding='utf-8')
        for name in ('claude-code', 'opencode'):
            proc = _kit(
                'home', 'render', '--harness', name, '--dir', str(folder), '--endpoint', ENDPOINT
            )
            assert proc.returncode == 64, (proc.returncode, proc.stderr)
            assert proc.stdout == '' and proc.stderr.strip(), proc
            assert sorted(p.name for p in folder.iterdir()) == ['keep.txt']


def test_empty_existing_dir_is_accepted():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'empty'
        folder.mkdir()
        _render('opencode', folder)


def test_unknown_harness_render_exits_64():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'h'
        proc = _kit(
            'home', 'render', '--harness', 'codex', '--dir', str(folder), '--endpoint', ENDPOINT
        )
        assert proc.returncode == 64, proc
        assert not folder.exists()


def test_non_local_endpoint_exits_64():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'h'
        proc = _kit(
            'home',
            'render',
            '--harness',
            'opencode',
            '--dir',
            str(folder),
            '--endpoint',
            'http://example.com:80',
        )
        assert proc.returncode == 64, proc
        assert not folder.exists()


# ---- session environment


def test_session_env_isolates_the_home():
    for name in ('claude-code', 'opencode'):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / 'h'
            home = _render(name, folder)
            d = harnesses.get(name)
            env = d.session_env(
                home, {'KEEP_ME': '1', 'HOME': '/home/user', 'http_proxy': 'http://x:1'}
            )
            assert env['KEEP_ME'] == '1'
            for var in HOME_VARS:
                assert _inside(env[var], folder), (var, env[var])
            assert _inside(env['HOMEDRIVE'] + env['HOMEPATH'], folder), env['HOMEPATH']
            for var in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
                assert env[var] == ENDPOINT, var
            assert 'http_proxy' not in env
            assert env['NO_PROXY'] == '127.0.0.1,localhost'


def test_claude_code_session_env():
    with tempfile.TemporaryDirectory() as td:
        home = _render('claude-code', Path(td) / 'h')
        env = harnesses.get('claude-code').session_env(home, {})
        assert Path(env['CLAUDE_CONFIG_DIR']) == Path(home['config_file']).parent
        assert env['ANTHROPIC_BASE_URL'] == ENDPOINT
        assert env['ANTHROPIC_AUTH_TOKEN'] == FAKE_KEY
        assert env['DISABLE_AUTOUPDATER'] == '1'
        assert env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] == '1'


def test_opencode_session_env():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'h'
        home = _render('opencode', folder)
        env = harnesses.get('opencode').session_env(home, {})
        assert Path(env['OPENCODE_CONFIG_DIR']) == Path(home['config_file']).parent
        assert env['STUB_API_KEY'] == FAKE_KEY
        for var in ('OPENCODE_TEST_HOME', 'OPENCODE_DB', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME'):
            assert _inside(env[var], folder), var
        for var in ('XDG_STATE_HOME', 'XDG_CACHE_HOME'):
            assert _inside(env[var], folder), var
        for var in ('OPENCODE_DISABLE_AUTOUPDATE', 'OPENCODE_DISABLE_MODELS_FETCH'):
            assert env[var] == '1', var


# ---- canary copy


def test_claude_code_copy_is_byte_for_byte():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        home = _render('claude-code', base / 'h')
        dest = base / 'canary' / 'home'
        copy = harnesses.get('claude-code').copy_home_for_canary(home, dest, CANARY_ENDPOINT)
        assert Path(copy['dir']) == dest and copy['endpoint'] == CANARY_ENDPOINT
        assert Path(copy['config_file']) == dest / 'claude-config' / 'settings.json'
        assert Path(copy['config_file']).read_bytes() == Path(home['config_file']).read_bytes()
        assert copy['harness'] == 'claude-code' and list(copy) == HOME_KEYS
        env = harnesses.get('claude-code').session_env(copy, {})
        assert env['ANTHROPIC_BASE_URL'] == CANARY_ENDPOINT
        assert _inside(env['HOME'], dest)


def test_opencode_copy_keeps_a_malformed_file_and_swaps_the_endpoint():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        home = _render('opencode', base / 'h')
        cfg = Path(home['config_file'])
        broken = cfg.read_bytes()[:-5] + b'  ,,{ not json'
        cfg.write_bytes(broken)
        dest = base / 'canary' / 'home'
        copy = harnesses.get('opencode').copy_home_for_canary(home, dest, CANARY_ENDPOINT)
        out = Path(copy['config_file']).read_bytes()
        assert out == broken.replace(ENDPOINT.encode(), CANARY_ENDPOINT.encode()), out
        assert CANARY_ENDPOINT.encode() in out and ENDPOINT.encode() not in out
        assert cfg.read_bytes() == broken, 'the original changed'
        assert copy['endpoint'] == CANARY_ENDPOINT and Path(copy['dir']) == dest


def test_opencode_copy_without_the_endpoint_text_raises():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        home = _render('opencode', base / 'h')
        Path(home['config_file']).write_text('{"plugins": []}', encoding='utf-8')
        try:
            harnesses.get('opencode').copy_home_for_canary(home, base / 'c', CANARY_ENDPOINT)
        except Exception:  # any raise is a failed copy
            return
        raise AssertionError('a copy with no endpoint text did not raise')


# ---- binary and version


def _fake_binary(base: Path, printed: str) -> list[str]:
    script = base / 'fake_harness.py'
    script.write_text(
        'import os, sys\n'
        'from pathlib import Path\n'
        'Path(os.environ["FAKE_SEEN"]).write_text(\n'
        '    os.getcwd() + "\\n" + os.environ.get("HOME", "") + "\\n" + " ".join(sys.argv[1:]),\n'
        '    encoding="utf-8")\n'
        f'print({printed!r})\n',
        encoding='utf-8',
    )
    return [sys.executable, str(script)]


def test_version_parses_both_printed_forms():
    cases = (
        ('claude-code', 'KIT_HARNESS_ARGV_CLAUDE_CODE', '2.1.316 (Claude Code)', '2.1.316'),
        ('opencode', 'KIT_HARNESS_ARGV_OPENCODE', 'opencode v2.2.5', '2.2.5'),
    )
    for name, var, printed, expected in cases:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seen = base / 'seen.txt'
            argv = _fake_binary(base, printed)
            env = {
                **os.environ,
                var: json.dumps(argv),
                'FAKE_SEEN': str(seen),
                'HOME': '/home/user',
            }
            d = harnesses.get(name)
            assert d.binary_argv(env) == argv
            assert d.version(env) == expected, name
            cwd, home, args = seen.read_text(encoding='utf-8').splitlines()
            assert args == '--version'
            assert Path(home).resolve() == Path(cwd).resolve(), (home, cwd)
            assert not _inside(cwd, base), cwd


def test_version_without_a_triple_is_none():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        argv = _fake_binary(base, 'no version here 1.2')
        env = {
            **os.environ,
            'KIT_HARNESS_ARGV_OPENCODE': json.dumps(argv),
            'FAKE_SEEN': str(base / 's'),
        }
        assert harnesses.get('opencode').version(env) is None


def test_missing_binary_reads_as_missing():
    env = {'PATH': '', 'KIT_HARNESS_ARGV_CLAUDE_CODE': json.dumps(['/no/such/claude'])}
    d = harnesses.get('claude-code')
    assert d.version(env) is None
    empty = {'PATH': ''}
    for name in ('claude-code', 'opencode'):
        assert harnesses.get(name).binary_argv(empty) == [], name
        assert harnesses.get(name).version(empty) is None, name


def test_malformed_argv_variable_reads_as_missing():
    for raw in ('not json', '[]', '"claude"', '[1, 2]'):
        env = {'PATH': '', 'KIT_HARNESS_ARGV_CLAUDE_CODE': raw}
        assert harnesses.get('claude-code').binary_argv(env) == [], raw


def _shim(folder: Path, name: str, marker: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    shim = folder / name
    shim.write_text(f'@echo ran > "{marker}"\r\n@echo 9.9.9\r\n', encoding='ascii')
    return shim


def test_windows_batch_files_are_never_run():
    if not WINDOWS:
        return
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        marker = base / 'ran.marker'
        for name, var in (
            ('claude-code', 'KIT_HARNESS_ARGV_CLAUDE_CODE'),
            ('opencode', 'KIT_HARNESS_ARGV_OPENCODE'),
        ):
            for ext in ('.cmd', '.bat', '.CMD'):
                shim = _shim(base / f'{name}{ext}', f'{name.split("-")[0]}{ext}', marker)
                env = {**os.environ, var: json.dumps([str(shim)])}
                d = harnesses.get(name)
                assert d.binary_argv(env) == [], (name, ext)
                assert d.version(env) is None, (name, ext)
            on_path = {
                **os.environ,
                'PATH': str(base / f'{name}.cmd'),
                'PATHEXT': '.COM;.EXE;.BAT;.CMD',
            }
            on_path.pop(var, None)
            assert harnesses.get(name).binary_argv(on_path) == [], name
        assert not marker.exists(), 'a batch file ran'


def test_windows_opencode_shim_resolves_to_the_native_binary():
    if not WINDOWS:
        return
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        marker = base / 'ran.marker'
        npm = base / 'npm'
        shim = _shim(npm, 'opencode.cmd', marker)
        native = npm / 'node_modules' / '@opencode' / 'cli' / 'bin' / 'opencode.exe'
        native.parent.mkdir(parents=True)
        native.write_bytes(b'')
        d = harnesses.get('opencode')
        env = {**os.environ, 'KIT_HARNESS_ARGV_OPENCODE': json.dumps([str(shim), '--x'])}
        assert d.binary_argv(env) == [str(native), '--x'], d.binary_argv(env)
        on_path = {k: v for k, v in os.environ.items() if k != 'KIT_HARNESS_ARGV_OPENCODE'}
        on_path.update(PATH=str(npm), PATHEXT='.COM;.EXE;.BAT;.CMD')
        assert [Path(a) for a in d.binary_argv(on_path)] == [native]
        assert not marker.exists(), 'the shim ran'


if __name__ == '__main__':
    run_module(dict(globals()), 'harness drivers and test homes')

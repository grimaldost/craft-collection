#!/usr/bin/env python3
"""Checks of `kit run --mode`, the session's tree, the home hashes and the open run.

Contract under test, with a fake harness named through `KIT_HARNESS_ARGV_*`:
- the interactive grammar (opencode only): `--standalone` exactly once and only the flags
  `--standalone`, `--continue`, `-c`, `--session`, `-s` and `--prompt`, the last three taking
  the next token as their value; any other token (a positional, a subcommand, `--server`,
  `--auto`, `--yolo`, `--dangerously-skip-permissions`, `--print-logs`, a `--flag=value`
  form) is refused naming it, and so is a value flag with no value left; headless arguments
  are checked as before;
- `kit run --mode headless|interactive`, default headless; interactive mode is refused
  (exit 64, no run) for a driver without it, on any platform but Windows, and for a contract
  whose `[modes.interactive]` reads `absent`; a contract with no entry launches with one
  standard-error line;
- in interactive mode the session also receives the terminal names kit's environment holds,
  and `run.json` lists them as `terminal_names`; a headless session does not;
- every session's `NO_PROXY` is `127.0.0.1,localhost,::1`;
- `runs/<id>/home-hashes.json` lists exactly the watched files of the home; a canary that
  changes, adds or removes one gives `refused-home-changed`, exit 65 and no session;
- an interactive start on a home whose rendered files changed, were added or removed after
  the render, or whose `home.json` has no record, is refused with exit 64 and no run; a
  headless start on a test home is not compared;
- an interactive session finds `run-open.json` holding its run in its home's folder, which is
  gone once the run ended; an interactive start on a home holding one is refused with exit 64
  and no run, naming its run; a headless start on a test home is not refused;
- a session that starts a child at once and a long-lived grandchild leaves no process after
  `kit run` returns;
- an interrupt after the mint and before the session gives `interrupted` and exit 130, ends
  the canary's tree and starts no session; one during preflight exits 130 with no run;
- `run.json` records `work_tree_top`, the top of the working folder's work tree or null.

Stdlib-runnable: `python test_interactive_mode.py`.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import harnesses, launcher, watch
from kit_fixtures import SRC, run_module
from test_launcher import ENDPOINT, OPENCODE_ARGS, PINNED, Case, git, kit, scratch

WINDOWS = os.name == 'nt'
FAKE = Path(__file__).resolve().parent / 'session_fake_harness.py'
INTERACTIVE_ARGS = ['--standalone', '--prompt', 'say hi & 100%']
TERMINAL = {
    'TERM': 'xterm-kit-test',
    'COLORTERM': 'truecolor',
    'LANG': 'C.UTF-8',
    'TZ': 'UTC',
    'NO_COLOR': '1',
    'WT_SESSION': 'kit-test-session',
}
FOREIGN_RUN = '20261118T000000Z-0123456789ab'


def make_case(harness: str, mode: str = 'guarded', code: int = 0, **options) -> Case:
    case = Case(scratch(), harness)
    case.argv = [
        sys.executable,
        str(FAKE),
        str(case.out),
        PINNED[harness],
        str(code),
        mode,
        json.dumps(options),
    ]
    return case


def run(case: Case, args: list[str], mode: str | None = None, **env: str):
    head = ['run', '--harness', case.harness]
    head += ['--mode', mode] if mode else []
    head += ['--home', str(case.home), '--workdir', str(case.work), '--policy', str(case.policy)]
    return kit(case, *head, '--', *args, **env)


def refused(case: Case, proc, needle: str) -> None:
    assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
    lines = proc.stderr.splitlines()
    assert len(lines) == 1, lines
    assert needle in lines[0], (needle, lines)
    assert not case.out.exists(), 'the harness was started'
    assert case.runs() == [], case.runs()


def done(case: Case) -> None:
    shutil.rmtree(case.base, ignore_errors=True)


def alive(pid: int) -> bool:
    if WINDOWS:
        import ctypes

        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
        k32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        k32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return k32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT: still running
        finally:
            k32.CloseHandle(handle)
    try:
        stat = Path(f'/proc/{pid}/stat').read_text(encoding='ascii', errors='replace')
    except OSError:
        return False
    return stat.rsplit(')', 1)[1].split()[0] != 'Z'


# ---- the grammar


def test_interactive_grammar_accepts_the_flag_table():
    driver = harnesses.get('opencode')
    for args in (
        ['--standalone'],
        INTERACTIVE_ARGS,
        ['-c', '--standalone'],
        ['--continue', '--standalone', '-s', 'ses_1'],
        ['--standalone', '--session', '--prompt'],
        ['--prompt', '--standalone', '--standalone'],
    ):
        launcher.check_session_args(args, driver, 'interactive')


def _grammar_refuses(args: list[str], needle: str, harness: str = 'opencode') -> None:
    try:
        launcher.check_session_args(args, harnesses.get(harness), 'interactive')
    except launcher.RefusalError as exc:
        assert needle in str(exc), (args, needle, str(exc))
        assert str(exc).isascii(), str(exc)
        return
    raise AssertionError(f'{args} passed the interactive grammar')


def test_interactive_grammar_refuses_every_other_token_naming_it():
    for token in (
        'proj',
        'C:/work/proj',
        'mini',
        'serve',
        'run',
        '--server',
        '--auto',
        '--yolo',
        '--dangerously-skip-permissions',
        '--print-logs',
        '--prompt=hi',
        '--standalone=1',
        '--model',
    ):
        _grammar_refuses(['--standalone', token], token)
        _grammar_refuses([token, '--standalone'], token)


def test_interactive_grammar_refuses_a_missing_value_and_the_count_of_standalone():
    _grammar_refuses(['--standalone', '--prompt'], '--prompt')
    _grammar_refuses(['--standalone', '-s'], '-s')
    _grammar_refuses([], '--standalone')
    _grammar_refuses(['--prompt', 'hi'], '--standalone')
    _grammar_refuses(['--standalone', '-c', '--standalone'], '--standalone')
    _grammar_refuses(['--standalone'], 'interactive', harness='claude-code')


def test_headless_grammar_is_unchanged():
    driver = harnesses.get('opencode')
    launcher.check_session_args(OPENCODE_ARGS, driver)
    launcher.check_session_args(OPENCODE_ARGS, driver, 'headless')
    try:
        launcher.check_session_args(INTERACTIVE_ARGS, driver, 'headless')
    except launcher.RefusalError as exc:
        assert 'run' in str(exc), str(exc)
    else:
        raise AssertionError('interactive arguments passed the headless grammar')


# ---- kit run --mode


def test_an_unknown_mode_is_refused():
    case = make_case('opencode')
    try:
        refused(case, run(case, INTERACTIVE_ARGS, mode='batch'), 'mode')
    finally:
        done(case)


def test_interactive_mode_is_refused_for_claude_code():
    case = make_case('claude-code')
    try:
        proc = run(case, INTERACTIVE_ARGS, mode='interactive')
        refused(case, proc, 'offers no interactive mode')
    finally:
        done(case)


def test_interactive_mode_is_refused_off_windows():
    if WINDOWS:
        return
    case = make_case('opencode')
    try:
        refused(case, run(case, INTERACTIVE_ARGS, mode='interactive'), 'Windows')
    finally:
        done(case)


def test_the_platform_is_read_when_the_mode_is_checked():
    driver = harnesses.get('opencode')
    real = launcher.WINDOWS
    try:
        launcher.WINDOWS = False
        launcher.check_mode(driver, 'interactive')
    except launcher.RefusalError as exc:
        assert 'Windows' in str(exc), str(exc)
    else:
        raise AssertionError('interactive mode passed off Windows')
    finally:
        launcher.WINDOWS = real


def test_an_open_run_is_named_whatever_its_id():
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        (home / watch.RUN_OPEN).write_text(json.dumps({'run_id': 'run-7'}), encoding='utf-8')
        try:
            launcher.check_open_run(home)
        except launcher.RefusalError as exc:
            assert 'run-7' in str(exc), str(exc)
        else:
            raise AssertionError('an open run passed')
        (home / watch.RUN_OPEN).write_text('not json', encoding='utf-8')
        try:
            launcher.check_open_run(home)
        except launcher.RefusalError as exc:
            assert watch.RUN_OPEN in str(exc), str(exc)
        else:
            raise AssertionError('an unreadable open run passed')


def test_kit_run_refuses_a_token_outside_the_interactive_grammar():
    if not WINDOWS:
        return
    for token in ('proj', '--auto', '--prompt=hi'):
        case = make_case('opencode')
        try:
            refused(case, run(case, ['--standalone', token], mode='interactive'), token)
        finally:
            done(case)


def test_a_valid_interactive_argument_list_launches():
    if not WINDOWS:
        return
    case = make_case('opencode')
    try:
        args = ['--standalone', '-c', '--prompt', 'say hi & 100%', '-s', 'ses_1']
        proc = run(case, args, mode='interactive')
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        child = case.child()
        assert child['args'] == args, child['args']
        assert os.path.samefile(child['cwd'], case.work), child['cwd']
        record = case.run_json()
        assert record['outcome'] == 'ended' and record['exit_code'] == 0, record
    finally:
        done(case)


def scratch_package(base: Path, state: str | None) -> Path:
    """A copy of the package whose opencode contract has `[modes.interactive]` in `state`."""
    src = base / 'pkg-src'
    shutil.copytree(
        SRC / 'harness_kit', src / 'harness_kit', ignore=shutil.ignore_patterns('__pycache__')
    )
    contract = src / 'harness_kit' / 'contracts' / 'opencode.toml'
    text = contract.read_text(encoding='utf-8')
    text = re.sub(r'(?ms)^\[modes\.interactive\]\n.*?(?=^\[|\Z)', '', text)
    if state is not None:
        text += f'\n[modes.interactive]\nstate = "{state}"\nmark = "read"\nevidence = "a test."\n'
    contract.write_text(text, encoding='utf-8')
    return src


def render_with(case: Case, package: Path, name: str) -> Path:
    """A home rendered by the kit of `package`, so its judge is that package's."""
    home = case.base / name
    proc = kit(
        case,
        'home',
        'render',
        '--harness',
        'opencode',
        '--dir',
        str(home),
        '--endpoint',
        ENDPOINT,
        PYTHONPATH=str(package),
    )
    assert proc.returncode == 0, proc.stderr
    return home


def test_the_contract_entry_decides_an_interactive_launch():
    if not WINDOWS:
        return
    case = make_case('opencode')
    try:
        absent = scratch_package(case.base / 'absent', 'absent')
        proc = run(case, INTERACTIVE_ARGS, mode='interactive', PYTHONPATH=str(absent))
        refused(case, proc, 'absent')
        # An interactive start runs only a home whose judge is the kit that starts it.
        missing = scratch_package(case.base / 'missing', None)
        case.home = render_with(case, missing, 'home-missing')
        proc = run(case, INTERACTIVE_ARGS, mode='interactive', PYTHONPATH=str(missing))
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        lines = proc.stderr.splitlines()
        assert len(lines) == 1 and 'interactive' in lines[0], lines
        tested = scratch_package(case.base / 'tested', 'tested')
        case.home = render_with(case, tested, 'home-tested')
        proc = run(case, INTERACTIVE_ARGS, mode='interactive', PYTHONPATH=str(tested))
        assert proc.returncode == 0 and proc.stderr == '', (proc.returncode, proc.stderr)
    finally:
        done(case)


# ---- the session environment


def test_the_terminal_names_reach_an_interactive_session_only():
    if not WINDOWS:
        return
    case = make_case('opencode')
    try:
        proc = run(case, INTERACTIVE_ARGS, mode='interactive', **TERMINAL)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        env = {k.upper(): v for k, v in case.child()['env'].items()}
        for name, value in TERMINAL.items():
            assert env.get(name) == value, (name, env.get(name))
        record = case.run_json()
        want = [n for n in launcher.TERMINAL_NAMES if n in TERMINAL]
        assert record['terminal_names'] == want, record.get('terminal_names')
        assert not set(TERMINAL) & {n.upper() for n in record['scrubbed']}, record['scrubbed']
    finally:
        done(case)
    case = make_case('opencode')
    try:
        proc = run(case, OPENCODE_ARGS, **TERMINAL)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        env = {k.upper() for k in case.child()['env']}
        assert not set(TERMINAL) & env, set(TERMINAL) & env
        assert 'terminal_names' not in case.run_json()
    finally:
        done(case)


def test_every_session_exempts_only_the_loopback_from_the_proxy():
    for harness in ('claude-code', 'opencode'):
        case = make_case(harness)
        try:
            proc = case.run()
            assert proc.returncode == 0, (proc.returncode, proc.stderr)
            env = {k.upper(): v for k, v in case.child()['env'].items()}
            assert env['NO_PROXY'] == '127.0.0.1,localhost,::1', (harness, env['NO_PROXY'])
        finally:
            done(case)


# ---- home hashes


def test_home_hashes_list_exactly_the_watched_files():
    for harness in ('claude-code', 'opencode'):
        case = make_case(harness)
        try:
            proc = case.run()
            assert proc.returncode == 0, (proc.returncode, proc.stderr)
            run_dir = case.runs()[0].parent
            text = (run_dir / watch.HOME_HASHES).read_text(encoding='utf-8')
            hashes = json.loads(text)
            want = watch.hash_files(case.home, harnesses.get(harness))
            assert hashes == want and list(hashes) == sorted(hashes), (harness, hashes)
        finally:
            done(case)


def _changed_by_the_canary(harness: str, action: str, relative: str) -> None:
    case = Case(scratch(), harness)
    target = str(case.home / relative)
    if action == 'remove':
        Path(target).write_bytes(b'a file the canary removes\n')
    case.argv = [
        sys.executable,
        str(FAKE),
        str(case.out),
        PINNED[harness],
        '0',
        'guarded',
        json.dumps({'canary_edit': [action, target]}),
    ]
    try:
        proc = case.run()
        assert proc.returncode == 65, (harness, action, proc.returncode, proc.stderr)
        assert not case.out.exists(), 'the session started'
        record = case.run_json()
        assert record['outcome'] == 'refused-home-changed', record
        assert relative in proc.stderr, proc.stderr
    finally:
        done(case)


def test_a_canary_that_changes_a_watched_file_refuses_the_session():
    _changed_by_the_canary('opencode', 'change', 'conf/opencode.jsonc')
    _changed_by_the_canary('opencode', 'add', 'conf/added.json')
    _changed_by_the_canary('opencode', 'remove', 'kit-shell/extra.txt')
    _changed_by_the_canary('claude-code', 'change', 'claude-config/settings.json')


def test_a_canary_that_changes_an_unwatched_file_starts_the_session():
    case = Case(scratch(), 'opencode')
    target = case.home / 'home' / 'Local' / 'scratch.txt'
    case.argv = [
        sys.executable,
        str(FAKE),
        str(case.out),
        PINNED['opencode'],
        '0',
        'guarded',
        json.dumps({'canary_edit': ['add', str(target)]}),
    ]
    try:
        proc = case.run()
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        assert case.out.exists() and case.run_json()['outcome'] == 'ended'
    finally:
        done(case)


# ---- the render's record and the open run


def _edited_home(edit) -> None:
    if not WINDOWS:
        return
    case = make_case('opencode')
    try:
        edit(case.home)
        refused(case, run(case, INTERACTIVE_ARGS, mode='interactive'), 'render')
        proc = case.run()
        assert proc.returncode != 64 and 'render' not in proc.stderr, proc.stderr
    finally:
        done(case)


def test_an_interactive_start_on_a_home_changed_after_its_render_is_refused():
    def change(home: Path) -> None:
        config = home / 'conf' / 'opencode.jsonc'
        config.write_bytes(config.read_bytes() + b' ')

    def add(home: Path) -> None:
        (home / 'kit-shell' / 'extra.js').write_bytes(b'x')

    def remove(home: Path) -> None:
        (home / 'kit-shell' / 'opencode-plugin' / 'shell_config.json').unlink()

    def no_record(home: Path) -> None:
        data = json.loads((home / 'home.json').read_text(encoding='utf-8'))
        del data['rendered_sha256']
        (home / 'home.json').write_text(json.dumps(data), encoding='utf-8')

    for edit in (change, add, remove, no_record):
        _edited_home(edit)


def test_an_interactive_session_holds_the_open_run_until_its_end():
    if not WINDOWS:
        return
    case = make_case('opencode')
    try:
        proc = run(case, INTERACTIVE_ARGS, mode='interactive')
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        record = case.run_json()
        seen = case.child()['run_open']
        assert seen is not None and json.loads(seen) == {'run_id': record['run_id']}, seen
        assert not (case.home / watch.RUN_OPEN).exists(), 'run-open.json was left'
    finally:
        done(case)


def test_a_home_holding_an_open_run_refuses_an_interactive_start():
    if not WINDOWS:
        return
    case = make_case('opencode')
    try:
        opened = case.home / watch.RUN_OPEN
        opened.write_text(json.dumps({'run_id': FOREIGN_RUN}), encoding='utf-8')
        refused(case, run(case, INTERACTIVE_ARGS, mode='interactive'), FOREIGN_RUN)
        proc = case.run()
        assert proc.returncode == 0, ('headless refused the open run', proc.stderr)
        assert opened.is_file()
    finally:
        done(case)


# ---- the session's tree


def _tree_leaves_nothing(harness: str, mode: str | None) -> None:
    case = make_case(harness, tree=True)
    try:
        args = INTERACTIVE_ARGS if mode == 'interactive' else None
        proc = case.run() if args is None else run(case, args, mode=mode)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        pids = [int(p) for p in Path(str(case.out) + '.pids').read_text().split()]
        assert len(pids) == 2, pids
        if not WINDOWS:
            end = time.monotonic() + 5
            while any(alive(p) for p in pids) and time.monotonic() < end:
                time.sleep(0.05)
        left = [p for p in pids if alive(p)]
        assert not left, f'processes left after kit run returned: {left}'
    finally:
        done(case)


def test_a_session_tree_leaves_no_process_after_kit_run():
    _tree_leaves_nothing('opencode', None)
    _tree_leaves_nothing('claude-code', None)
    if WINDOWS:
        _tree_leaves_nothing('opencode', 'interactive')


# ---- interruption


@contextlib.contextmanager
def _in_process(case: Case):
    """kit's own environment as `case.env()` names it, for `launcher.main` in this process."""
    wanted = case.env()
    names = {k for k in os.environ if k.upper().startswith(('KIT_', 'GIT_'))}
    names |= {k for k in wanted if k.upper().startswith('KIT_')} | {'PYTHONPATH'}
    saved = {k: os.environ.get(k) for k in names}
    handlers = {s: signal.getsignal(s) for s in _signals()}
    for name in names:
        os.environ.pop(name, None)
        if name in wanted:
            os.environ[name] = wanted[name]
    try:
        yield
    finally:
        for name, value in saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def _signals() -> list:
    return [signal.SIGINT] + ([signal.SIGBREAK] if WINDOWS else [])


def _argv(case: Case) -> list[str]:
    head = ['--harness', 'opencode', '--home', str(case.home), '--workdir', str(case.work)]
    return [*head, '--policy', str(case.policy), '--', *OPENCODE_ARGS]


def test_an_interrupt_before_the_session_gives_interrupted_and_130():
    case = make_case('opencode')
    real = launcher.run_canary_for_plan

    def interrupted(plan, environ):
        raise KeyboardInterrupt

    try:
        launcher.run_canary_for_plan = interrupted
        with _in_process(case):
            code = launcher.main(_argv(case))
        assert code == 130, code
        assert case.run_json()['outcome'] == 'interrupted', case.run_json()
        assert not case.out.exists(), 'the session started'
    finally:
        launcher.run_canary_for_plan = real
        done(case)


def test_an_interrupt_during_preflight_exits_130_with_no_run():
    case = make_case('opencode')
    real = launcher.preflight

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    try:
        launcher.preflight = interrupted
        with _in_process(case):
            code = launcher.main(_argv(case))
        assert code == 130, code
        assert case.runs() == [], case.runs()
    finally:
        launcher.preflight = real
        done(case)


def test_an_interrupt_signal_during_the_canary_ends_its_tree():
    case = make_case('opencode', mode='hang')
    marker = Path(str(case.out) + '.grandchild-pid')
    flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {}
    head = ['run', '--harness', 'opencode', '--home', str(case.home)]
    head += ['--workdir', str(case.work), '--policy', str(case.policy), '--', *OPENCODE_ARGS]
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *head],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=case.env(),
        cwd=str(case.base),
        **flags,
    )
    try:
        end = time.monotonic() + 60
        while not marker.is_file() and time.monotonic() < end and proc.poll() is None:
            time.sleep(0.05)
        assert marker.is_file(), 'the canary did not start'
        time.sleep(0.5)
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGINT)
        _, err = proc.communicate(timeout=60)
        assert proc.returncode == 130, (proc.returncode, err)
        assert case.run_json()['outcome'] == 'interrupted', case.run_json()
        assert not case.out.exists(), 'the session started'
        grandchild = int(marker.read_text(encoding='ascii'))
        end = time.monotonic() + 5
        while alive(grandchild) and time.monotonic() < end:
            time.sleep(0.05)
        assert not alive(grandchild), 'the canary tree was left'
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        done(case)


def test_an_interrupt_ends_a_canary_harness_that_ignores_it():
    case = make_case('opencode', deaf_canary=True)
    started = Path(str(case.out) + '.deaf-started')
    ran_on = Path(str(case.out) + '.ran-on')
    flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {}
    head = ['run', '--harness', 'opencode', '--home', str(case.home)]
    head += ['--workdir', str(case.work), '--policy', str(case.policy), '--', *OPENCODE_ARGS]
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *head],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=case.env(),
        cwd=str(case.base),
        **flags,
    )
    try:
        end = time.monotonic() + 60
        while not started.is_file() and time.monotonic() < end and proc.poll() is None:
            time.sleep(0.05)
        assert started.is_file(), 'the canary did not start'
        harness = int(started.read_text(encoding='ascii'))
        os.kill(proc.pid, signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGINT)
        sent = time.monotonic()
        _, err = proc.communicate(timeout=60)
        took = time.monotonic() - sent
        assert proc.returncode == 130, (proc.returncode, err)
        assert took < 5, f'kit took {took:.1f} s to end after the interrupt'
        assert case.run_json()['outcome'] == 'interrupted', case.run_json()
        assert not alive(harness), 'the canary harness was left running'
        time.sleep(9)
        assert not ran_on.exists(), 'the canary harness ran on after the interrupt'
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        done(case)


# ---- work tree top


def test_run_json_records_the_work_tree_top():
    def setup(case):
        repo = case.base / 'repo'
        sub = repo / 'sub'
        sub.mkdir(parents=True)
        git(repo, 'init', '-q')
        return sub

    case = make_case('opencode')
    try:
        sub = setup(case)
        head = ['run', '--harness', 'opencode', '--home', str(case.home), '--workdir', str(sub)]
        proc = kit(case, *head, '--policy', str(case.policy), '--', *OPENCODE_ARGS)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        record = case.run_json()
        top = record['work_tree_top']
        assert top and os.path.samefile(top, case.base / 'repo'), record
    finally:
        done(case)
    case = make_case('opencode')
    try:
        assert case.run().returncode == 0
        assert case.run_json()['work_tree_top'] is None, case.run_json()
    finally:
        done(case)


if __name__ == '__main__':
    run_module(globals(), 'kit run modes, home hashes and the session tree')

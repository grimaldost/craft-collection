#!/usr/bin/env python3
"""Checks of the state root, run identity and journal, in process.

Contract under test:
- the state root is KIT_STATE_ROOT when set, else %LOCALAPPDATA%/harness-kit on
  Windows, else $XDG_STATE_HOME/harness-kit, else ~/.local/state/harness-kit;
- a root inside a harness's configuration is refused: a component naming a
  harness folder, a path under .config/opencode, or a path under the value of
  one of the harness configuration variables; paths are resolved first and
  case-folded on Windows;
- a run id has the shape YYYYMMDDTHHMMSSZ-<12 hex>; minting writes
  runs/<id>/run.json with run_id, harness, started_utc, outcome "minted";
- run.json is written by atomic replace, retried on a sharing error;
- a run is launched only when the id has that shape and its run.json exists;
- a journal line is appended under one exclusive lock beside the journal,
  taken with retries for at most one second; a lock not obtained is a
  journal that cannot be written.

Stdlib-runnable: `python test_state.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import state
from kit_fixtures import run_module

WINDOWS = os.name == 'nt'


def _real(path: Path | str) -> str:
    return os.path.realpath(str(path))


def test_the_override_wins_over_every_default():
    env = {'KIT_STATE_ROOT': '/srv/kit', 'LOCALAPPDATA': '/l', 'XDG_STATE_HOME': '/x'}
    assert state.configured_root(env, windows=True) == '/srv/kit'
    assert state.configured_root(env, windows=False) == '/srv/kit'


def test_the_defaults_follow_the_platform_order():
    env = {'LOCALAPPDATA': 'C:/Users/me/AppData/Local', 'XDG_STATE_HOME': '/x', 'HOME': '/h'}
    assert state.configured_root(env, windows=True) == os.path.join(
        'C:/Users/me/AppData/Local', 'harness-kit'
    )
    assert state.configured_root(env, windows=False) == os.path.join('/x', 'harness-kit')
    env = {'HOME': '/home/user'}
    assert state.configured_root(env, windows=False) == os.path.join(
        '/home/user', '.local', 'state', 'harness-kit'
    )
    env = {'KIT_STATE_ROOT': '', 'XDG_STATE_HOME': '/x'}
    assert state.configured_root(env, windows=False) == os.path.join('/x', 'harness-kit')


def test_harness_folder_components_are_refused():
    for name in ('.claude', '.codex', '.opencode', '.gemini', '.pi', '.agents', '.goose'):
        reason = state.refusal(f'/home/user/{name}/kit', {}, windows=False)
        assert reason is not None and name in reason, (name, reason)
    assert state.refusal('/home/user/claude/kit', {}, windows=False) is None
    assert state.refusal('/home/user/.claudex/kit', {}, windows=False) is None


def test_windows_comparisons_are_case_folded():
    assert state.refusal('C:/Users/me/.CLAUDE/kit', {}, windows=True) is not None
    assert state.refusal('C:/Users/me/.Config/OpenCode/kit', {}, windows=True) is not None
    env = {'CODEX_HOME': 'C:/Users/me/CodexHome'}
    assert state.refusal('c:/users/me/codexhome/kit', env, windows=True) is not None
    assert state.refusal('/home/user/.Claude/kit', {}, windows=False) is None


def test_a_path_under_config_opencode_is_refused():
    assert state.refusal('/home/user/.config/opencode/state', {}, windows=False) is not None
    assert state.refusal('/home/user/.config/opencode', {}, windows=False) is not None
    assert state.refusal('/home/user/.config/other', {}, windows=False) is None
    assert state.refusal('/home/user/opencode/.config', {}, windows=False) is None


def test_a_path_under_a_harness_configuration_variable_is_refused():
    names = (
        'CLAUDE_CONFIG_DIR',
        'OPENCODE_CONFIG_DIR',
        'XDG_CONFIG_HOME',
        'CODEX_HOME',
        'PI_CODING_AGENT_DIR',
        'GOOSE_PATH_ROOT',
    )
    for name in names:
        env = {name: '/srv/conf'}
        assert state.refusal('/srv/conf/kit', env, windows=False) is not None, name
        assert state.refusal('/srv/conf', env, windows=False) is not None, name
        assert state.refusal('/srv/confx/kit', env, windows=False) is None, name
    assert state.refusal('/srv/kit', {'CLAUDE_CONFIG_DIR': ''}, windows=False) is None


def test_the_root_is_resolved_before_it_is_judged():
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / '.claude'
        target.mkdir()
        link = Path(td) / 'plain'
        try:
            if WINDOWS:
                import _winapi

                _winapi.CreateJunction(str(target), str(link))
            else:
                link.symlink_to(target, target_is_directory=True)
        except (OSError, AttributeError) as exc:
            print(f'note: no link available ({type(exc).__name__}); resolution unchecked')
            return
        env = {'KIT_STATE_ROOT': str(link / 'kit')}
        try:
            state.state_root(env)
        except state.StateRootError as exc:
            assert '.claude' in str(exc), exc
        else:
            raise AssertionError('a link into .claude was accepted')


def test_state_root_returns_the_resolved_path_without_creating_it():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'kit'
        assert state.state_root({'KIT_STATE_ROOT': str(root)}) == Path(_real(root))
        assert not root.exists()


def test_a_minted_run_has_the_id_shape_and_run_json():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        run_id, run_dir = state.mint_run(root, 'opencode')
        assert state.RUN_ID_RE.fullmatch(run_id), run_id
        assert run_dir == root / 'runs' / run_id
        data = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
        assert list(data) == ['run_id', 'harness', 'started_utc', 'outcome'], data
        assert (data['run_id'], data['harness'], data['outcome']) == (
            run_id,
            'opencode',
            'minted',
        )
        assert data['started_utc'].endswith('Z'), data
        assert run_id.startswith(data['started_utc'][:10].replace('-', '')), data
        assert [p.name for p in run_dir.iterdir()] == ['run.json']
        assert state.is_launched(root, run_id)
        other, _ = state.mint_run(root, 'opencode')
        assert other != run_id


def test_a_run_id_computed_ahead_is_minted_once():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        run_id = state.new_run_id()
        assert state.RUN_ID_RE.fullmatch(run_id), run_id
        assert not (root / 'runs').exists()
        minted, run_dir = state.mint_run(root, 'claude-code', run_id=run_id)
        assert minted == run_id and run_dir == root / 'runs' / run_id
        data = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
        assert data['run_id'] == run_id and data['outcome'] == 'minted', data
        try:
            state.mint_run(root, 'claude-code', run_id=run_id)
        except FileExistsError:
            pass
        else:
            raise AssertionError('a run id was minted twice')


def test_the_run_id_pattern_rejects_near_misses():
    good = '20261109T120000Z-0123456789ab'
    assert state.RUN_ID_RE.fullmatch(good)
    for bad in (
        good + '\n',
        good.upper(),
        '20261109T120000Z-0123456789a',
        '2026110T120000Z-0123456789ab',
        '../20261109T120000Z-0123456789ab',
        '',
    ):
        assert not state.RUN_ID_RE.fullmatch(bad), bad


def test_launched_needs_the_shape_and_an_existing_run_json():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        forged = '20261109T120000Z-0123456789ab'
        assert not state.is_launched(root, forged)
        (root / 'runs' / forged).mkdir(parents=True)
        assert not state.is_launched(root, forged)
        (root / 'runs' / forged / 'run.json').write_text('{}', encoding='utf-8')
        assert state.is_launched(root, forged)
        assert not state.is_launched(root, None)
        assert not state.is_launched(root, 'not-an-id')


def test_atomic_write_replaces_whole_and_leaves_no_temporary_file():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'run.json'
        state.write_json_atomic(path, {'a': 1})
        state.write_json_atomic(path, {'a': 2, 'b': 'caf\u00e9'})
        assert json.loads(path.read_bytes()) == {'a': 2, 'b': 'caf\u00e9'}
        assert path.read_bytes().isascii()
        assert [p.name for p in Path(td).iterdir()] == ['run.json']


def test_atomic_write_retries_a_sharing_error():
    real = os.replace
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) < 3:
            raise PermissionError(13, 'sharing violation')
        real(src, dst)

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'run.json'
        state.os.replace = flaky
        try:
            state.write_json_atomic(path, {'ok': True}, sharing_retry=True)
        finally:
            state.os.replace = real
        assert len(calls) == 3, calls
        assert json.loads(path.read_bytes()) == {'ok': True}
        assert [p.name for p in Path(td).iterdir()] == ['run.json']


def test_atomic_write_gives_up_and_cleans_up_when_the_error_persists():
    real = os.replace

    def always(src, dst):
        raise PermissionError(13, 'sharing violation')

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'run.json'
        state.os.replace = always
        try:
            state.write_json_atomic(path, {'ok': True}, sharing_retry=True, deadline=0.2)
        except PermissionError:
            pass
        else:
            raise AssertionError('a persistent error was swallowed')
        finally:
            state.os.replace = real
        assert list(Path(td).iterdir()) == []


def test_journal_lines_append_whole():
    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / 'j' / 'journal.ndjson'
        state.append_journal(journal, {'n': 1})
        state.append_journal(journal, {'n': 2, 's': '\u4e2d'})
        lines = journal.read_bytes().split(b'\n')
        assert lines[-1] == b'', lines
        assert [json.loads(x) for x in lines[:-1]] == [{'n': 1}, {'n': 2, 's': '\u4e2d'}]
        assert journal.read_bytes().isascii()
        lock = journal.with_name('journal.ndjson.lock')
        assert lock.is_file() and lock.stat().st_size == 0


_HOLDER = r"""
import os, sys, time
path = sys.argv[1]
fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o666)
if os.name == 'nt':
    import msvcrt
    os.lseek(fd, 0, 0)
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX)
sys.stdout.write('held\n')
sys.stdout.flush()
time.sleep(float(sys.argv[2]))
"""


def hold_lock(lock: Path, seconds: float) -> subprocess.Popen:
    """Start a process that holds the journal lock for `seconds`; return once it holds it."""
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-c', _HOLDER, str(lock), str(seconds)],
        stdout=subprocess.PIPE,
    )
    assert proc.stdout is not None
    first = proc.stdout.readline()
    if first.strip() != b'held':
        proc.kill()
        proc.wait()
        raise AssertionError(f'the lock holder did not take the lock: {first!r}')
    return proc


def test_a_lock_held_past_its_second_is_a_journal_that_cannot_be_written():
    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / 'journal.ndjson'
        holder = hold_lock(journal.with_name('journal.ndjson.lock'), 4)
        try:
            start = time.monotonic()
            try:
                state.append_journal(journal, {'n': 1})
            except state.JournalError:
                pass
            else:
                raise AssertionError('appended while the lock was held')
            waited = time.monotonic() - start
        finally:
            holder.kill()
            holder.wait()
        assert 0.9 <= waited < 3.0, waited
        assert not journal.exists() or journal.read_bytes() == b''
        state.append_journal(journal, {'n': 2})
        assert journal.read_bytes() == b'{"n": 2}\n'


def test_a_lock_released_within_the_second_is_waited_for():
    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / 'journal.ndjson'
        holder = hold_lock(journal.with_name('journal.ndjson.lock'), 0.3)
        try:
            state.append_journal(journal, {'n': 1})
        finally:
            holder.wait()
        assert journal.read_bytes() == b'{"n": 1}\n'


if __name__ == '__main__':
    run_module(globals(), 'state root, run identity, journal')

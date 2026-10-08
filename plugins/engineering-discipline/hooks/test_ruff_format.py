"""Tests for ruff_format. Runnable with pytest or `python test_ruff_format.py`."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile

import ruff_format
from ruff_format import batch_command, batch_files, existing_files, ruff_commands, target_file

BADLY_FORMATTED = 'x=[1,2,\n  3]\n'


def _write(path, text=BADLY_FORMATTED):
    """Write `text` to `path`, creating parent directories; return the path."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def _declare_ruff(d):
    """Make `d` a project that declares ruff (an empty ruff.toml is a valid config)."""
    _write(os.path.join(d, 'ruff.toml'), '')


def test_selects_py_file():
    assert target_file({'tool_input': {'file_path': '/x/y.py'}}) == '/x/y.py'


def test_ignores_non_py():
    assert target_file({'tool_input': {'file_path': '/x/y.md'}}) is None


def test_handles_missing_input():
    assert target_file({}) is None
    assert target_file({'tool_input': {}}) is None


def test_runs_format_only():
    assert ruff_commands('/x/y.py') == [['uvx', 'ruff', 'format', '/x/y.py']]


def test_never_runs_destructive_autofix():
    # Regression guard for the strip-on-save trap: the per-edit hook must never
    # run `ruff check --fix` (it strips an import added in one edit before a later
    # edit uses it). `--fix` is owned by pre-commit/CI. Re-adding it breaks here.
    flat = [tok for cmd in ruff_commands('/x/y.py') for tok in cmd]
    assert '--fix' not in flat
    assert 'check' not in flat


def test_batch_files_dedupes_write_and_edit_preserving_order():
    payload = {
        'tool_calls': [
            {'tool_name': 'Write', 'tool_input': {'file_path': '/a.py'}},
            {'tool_name': 'Edit', 'tool_input': {'file_path': '/b.py'}},
            {'tool_name': 'Edit', 'tool_input': {'file_path': '/a.py'}},  # duplicate
        ]
    }
    assert batch_files(payload) == ['/a.py', '/b.py']


def test_batch_files_ignores_non_write_edit_tools():
    payload = {
        'tool_calls': [
            {'tool_name': 'Bash', 'tool_input': {'file_path': '/a.py'}},
            {'tool_name': 'Read', 'tool_input': {'file_path': '/b.py'}},
        ]
    }
    assert batch_files(payload) == []


def test_batch_files_ignores_non_py():
    payload = {
        'tool_calls': [
            {'tool_name': 'Write', 'tool_input': {'file_path': '/a.md'}},
        ]
    }
    assert batch_files(payload) == []


def test_batch_files_non_list_tool_calls_is_empty():
    # Regression: a truthy scalar `tool_calls` (contract violation or payload
    # drift) must degrade to "nothing to format", not a TypeError — the hook
    # promises to always exit 0.
    for bad in (5, True, 'Write', {'tool_name': 'Write'}):
        assert batch_files({'tool_calls': bad}) == []


def test_main_non_list_tool_calls_exits_0():
    rc, calls = _run_main_with_payload({'tool_calls': 5})
    assert rc == 0
    assert calls == []


def test_existing_files_drops_missing():
    with tempfile.TemporaryDirectory() as d:
        real = os.path.join(d, 'real.py')
        with open(real, 'w', encoding='utf-8') as fh:
            fh.write('x = 1\n')
        missing = os.path.join(d, 'missing.py')
        assert existing_files([real, missing]) == [real]


def test_batch_command_single_invocation_for_multiple_paths():
    assert batch_command(['/a.py', '/b.py']) == [['uvx', 'ruff', 'format', '/a.py', '/b.py']]


def test_batch_command_empty_when_no_paths():
    assert batch_command([]) == []


STATE_DIR_ENV = 'ENGINEERING_DISCIPLINE_STATE_DIR'


def _run_main_capturing(payload, stop_at=None, state_dir=None):
    """Run ruff_format.main() with a fake stdin, a captured stderr and a recording
    subprocess.run stub.

    Returns (return_code, calls, stderr) where calls is the list of argv lists
    that subprocess.run would have been invoked with. The firing log goes to
    `state_dir`, or to a throwaway directory, so a test never writes to a real
    plugin data directory.
    """
    with tempfile.TemporaryDirectory() as scratch:
        old_state = os.environ.get(STATE_DIR_ENV)
        os.environ[STATE_DIR_ENV] = state_dir or scratch
        try:
            return _run_main_capturing_unlogged(payload, stop_at)
        finally:
            if old_state is None:
                os.environ.pop(STATE_DIR_ENV, None)
            else:
                os.environ[STATE_DIR_ENV] = old_state


def _run_main_capturing_unlogged(payload, stop_at=None):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)

        class _Result:
            returncode = 0

        return _Result()

    old_stdin, old_stderr = sys.stdin, sys.stderr
    old_run = ruff_format.subprocess.run
    sys.stdin = io.StringIO(json.dumps(payload))
    sys.stderr = io.StringIO()
    ruff_format.subprocess.run = fake_run
    try:
        rc = ruff_format.main(stop_at=stop_at)
        err = sys.stderr.getvalue()
    finally:
        sys.stdin, sys.stderr = old_stdin, old_stderr
        ruff_format.subprocess.run = old_run
    return rc, calls, err


def _run_main_with_payload(payload, stop_at=None):
    """`_run_main_capturing` without the stderr text: (return_code, calls)."""
    rc, calls, _ = _run_main_capturing(payload, stop_at)
    return rc, calls


def _batch(*paths):
    """A PostToolBatch payload with one Write call per path."""
    return {'tool_calls': [{'tool_name': 'Write', 'tool_input': {'file_path': p}} for p in paths]}


def test_main_batch_formats_deduped_paths_in_one_call():
    with tempfile.TemporaryDirectory() as d:
        _declare_ruff(d)
        a = os.path.join(d, 'a.py')
        b = os.path.join(d, 'b.py')
        for p in (a, b):
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write('x = 1\n')
        payload = {
            'tool_calls': [
                {'tool_name': 'Write', 'tool_input': {'file_path': a}},
                {'tool_name': 'Edit', 'tool_input': {'file_path': b}},
                {'tool_name': 'Edit', 'tool_input': {'file_path': a}},  # duplicate
            ]
        }
        rc, calls = _run_main_with_payload(payload)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a, b]]


def test_main_batch_of_one():
    with tempfile.TemporaryDirectory() as d:
        _declare_ruff(d)
        a = os.path.join(d, 'a.py')
        with open(a, 'w', encoding='utf-8') as fh:
            fh.write('x = 1\n')
        payload = {'tool_calls': [{'tool_name': 'Write', 'tool_input': {'file_path': a}}]}
        rc, calls = _run_main_with_payload(payload)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_main_batch_drops_missing_files():
    with tempfile.TemporaryDirectory() as d:
        _declare_ruff(d)
        a = os.path.join(d, 'a.py')
        with open(a, 'w', encoding='utf-8') as fh:
            fh.write('x = 1\n')
        missing = os.path.join(d, 'missing.py')
        payload = {
            'tool_calls': [
                {'tool_name': 'Write', 'tool_input': {'file_path': a}},
                {'tool_name': 'Edit', 'tool_input': {'file_path': missing}},
            ]
        }
        rc, calls = _run_main_with_payload(payload)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_main_batch_empty_surviving_set_no_subprocess_call():
    payload = {
        'tool_calls': [
            {'tool_name': 'Write', 'tool_input': {'file_path': '/definitely/missing.py'}},
            {'tool_name': 'Bash', 'tool_input': {'file_path': '/x.py'}},
        ]
    }
    rc, calls = _run_main_with_payload(payload)
    assert rc == 0
    assert calls == []


def test_main_legacy_payload_still_formats():
    with tempfile.TemporaryDirectory() as d:
        _declare_ruff(d)
        a = os.path.join(d, 'a.py')
        with open(a, 'w', encoding='utf-8') as fh:
            fh.write('x = 1\n')
        payload = {'tool_input': {'file_path': a}}
        rc, calls = _run_main_with_payload(payload)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_file_outside_any_project_is_not_formatted():
    # No config anywhere between the file and the walk's end: the file belongs to
    # no project that asked for ruff, so its bytes are not ours to rewrite.
    with tempfile.TemporaryDirectory() as d:
        a = _write(os.path.join(d, 'loose', 'a.py'))
        assert ruff_format.declares_ruff(a, stop_at=d) is False
        rc, calls = _run_main_with_payload(_batch(a), stop_at=d)
        assert rc == 0
        assert calls == []


def test_repo_without_ruff_config_is_not_formatted():
    # A repository whose pyproject.toml configures other tools but not ruff.
    with tempfile.TemporaryDirectory() as d:
        os.mkdir(os.path.join(d, '.git'))
        _write(
            os.path.join(d, 'pyproject.toml'),
            '[project]\nname = "x"\n\n[tool.black]\nline-length = 88\n',
        )
        a = _write(os.path.join(d, 'pkg', 'a.py'))
        assert ruff_format.declares_ruff(a, stop_at=d) is False
        rc, calls = _run_main_with_payload(_batch(a), stop_at=d)
        assert rc == 0
        assert calls == []


def test_ruff_toml_project_is_formatted():
    with tempfile.TemporaryDirectory() as d:
        os.mkdir(os.path.join(d, '.git'))
        _declare_ruff(d)
        a = _write(os.path.join(d, 'src', 'pkg', 'a.py'))
        assert ruff_format.declares_ruff(a, stop_at=d) is True
        rc, calls = _run_main_with_payload(_batch(a), stop_at=d)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_dot_ruff_toml_project_is_formatted():
    with tempfile.TemporaryDirectory() as d:
        os.mkdir(os.path.join(d, '.git'))
        _write(os.path.join(d, '.ruff.toml'), 'line-length = 100\n')
        a = _write(os.path.join(d, 'a.py'))
        assert ruff_format.declares_ruff(a, stop_at=d) is True
        rc, calls = _run_main_with_payload(_batch(a), stop_at=d)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_pyproject_tool_ruff_table_is_formatted():
    # [tool.ruff] itself, or any [tool.ruff.*] sub-table alone, declares ruff.
    tables = (
        '[tool.ruff]\nline-length = 100\n',
        '[tool.ruff.lint]\nselect = ["E"]\n',
        '﻿[tool.ruff]\n',  # a byte-order mark, as some Windows editors write
        '[project]\nname = "x"\n\n  [tool.ruff.format]\nquote-style = "single"\n',
    )
    for table in tables:
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, 'pyproject.toml'), table)
            a = _write(os.path.join(d, 'a.py'))
            assert ruff_format.declares_ruff(a, stop_at=d) is True, table
            rc, calls = _run_main_with_payload(_batch(a), stop_at=d)
            assert rc == 0
            assert calls == [['uvx', 'ruff', 'format', a]], table


def test_pyproject_ruff_lookalikes_do_not_declare_ruff():
    # A commented-out table, a different tool whose name starts with "ruff", and
    # a mention inside a value are not a [tool.ruff] table.
    lookalikes = (
        '# [tool.ruff]\n[project]\nname = "x"\n',
        '[tool.ruffle]\nx = 1\n',
        '[project]\ndescription = "uses [tool.ruff] elsewhere"\n',
    )
    for text in lookalikes:
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, 'pyproject.toml'), text)
            a = _write(os.path.join(d, 'a.py'))
            assert ruff_format.declares_ruff(a, stop_at=d) is False, text


def test_pyproject_ruff_spellings_other_than_the_table_header_are_not_detected():
    # Documented limit (CHANGELOG 0.6.0): only a `[tool.ruff]` table header counts.
    # Valid TOML that ruff itself reads, spelled another way, is not detected, so
    # the file is left unformatted. This fails safe and is pinned so a change to
    # the detector is a deliberate one.
    undetected = (
        '[tool]\nruff.line-length = 100\n',
        '[tool]\nruff = { line-length = 100 }\n',
        '[tool."ruff"]\nline-length = 100\n',
    )
    for text in undetected:
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, 'pyproject.toml'), text)
            a = _write(os.path.join(d, 'a.py'))
            assert ruff_format.declares_ruff(a, stop_at=d) is False, text


def test_subpackage_pyproject_without_ruff_inherits_root_ruff_toml():
    # Mirrors ruff's own discovery: a pyproject.toml with no ruff table does not
    # stop the walk, so a monorepo subpackage under a root ruff.toml still formats.
    with tempfile.TemporaryDirectory() as d:
        os.mkdir(os.path.join(d, '.git'))
        _declare_ruff(d)
        sub = os.path.join(d, 'packages', 'sub')
        _write(os.path.join(sub, 'pyproject.toml'), '[project]\nname = "sub"\n')
        a = _write(os.path.join(sub, 'src', 'sub', 'm.py'))
        assert ruff_format.declares_ruff(a, stop_at=d) is True
        rc, calls = _run_main_with_payload(_batch(a), stop_at=d)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_walk_stops_at_git_boundary():
    # A ruff.toml above the repository root belongs to some other project. The
    # boundary holds whether .git is a directory (a clone) or a file (a worktree
    # or a submodule).
    for make_git in (os.mkdir, lambda p: _write(p, 'gitdir: elsewhere\n')):
        with tempfile.TemporaryDirectory() as d:
            _declare_ruff(d)
            repo = os.path.join(d, 'repo')
            os.mkdir(repo)
            make_git(os.path.join(repo, '.git'))
            a = _write(os.path.join(repo, 'a.py'))
            assert ruff_format.declares_ruff(a, stop_at=d) is False
            rc, calls = _run_main_with_payload(_batch(a), stop_at=d)
            assert rc == 0
            assert calls == []


def test_walk_stops_at_stop_at():
    # The tests' own bound: `stop_at` is checked, then the walk ends, so a config
    # above it on the test machine can never leak into a verdict.
    with tempfile.TemporaryDirectory() as d:
        _declare_ruff(d)
        inner = os.path.join(d, 'inner')
        a = _write(os.path.join(inner, 'a.py'))
        assert ruff_format.declares_ruff(a, stop_at=inner) is False
        assert ruff_format.declares_ruff(a, stop_at=d) is True
        _declare_ruff(inner)
        assert ruff_format.declares_ruff(a, stop_at=inner) is True


def test_unreadable_or_garbage_pyproject_fails_open():
    # Garbage bytes are read with errors ignored and do not match; a read that
    # raises means "not declared". Either way: exit 0, no traceback, nothing
    # printed, no subprocess call.
    with tempfile.TemporaryDirectory() as d:
        os.mkdir(os.path.join(d, '.git'))
        with open(os.path.join(d, 'pyproject.toml'), 'wb') as fh:
            fh.write(b'\xff\xfe\x00[[[tool.ruff\x00\x81 = = =\n')
        a = _write(os.path.join(d, 'a.py'))
        assert ruff_format.declares_ruff(a, stop_at=d) is False
        rc, calls, err = _run_main_capturing(_batch(a), stop_at=d)
        assert (rc, calls, err) == (0, [], '')

    # The read raising: OSError (unreadable) and ValueError both mean False, even
    # where the text would have declared ruff.
    for error in (PermissionError(13, 'Permission denied'), ValueError('bad bytes')):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, 'pyproject.toml'), '[tool.ruff]\n')
            a = _write(os.path.join(d, 'a.py'))

            def unreadable(self, *args, _error=error, **kwargs):
                raise _error

            old_read_text = ruff_format.Path.read_text
            ruff_format.Path.read_text = unreadable
            try:
                assert ruff_format.declares_ruff(a, stop_at=d) is False, error
                rc, calls, err = _run_main_capturing(_batch(a), stop_at=d)
            finally:
                ruff_format.Path.read_text = old_read_text
            assert (rc, calls, err) == (0, [], ''), error

    # A path the OS cannot represent (an embedded NUL) neither raises nor counts.
    with tempfile.TemporaryDirectory() as d:
        bad = os.path.join(d, 'bad\x00dir', 'a.py')
        assert ruff_format.declares_ruff(bad, stop_at=d) is False
        rc, calls, err = _run_main_capturing(_batch(bad), stop_at=d)
        assert (rc, calls, err) == (0, [], '')


def test_legacy_payload_is_scoped_too():
    with tempfile.TemporaryDirectory() as d:
        a = _write(os.path.join(d, 'a.py'))
        rc, calls = _run_main_with_payload({'tool_input': {'file_path': a}}, stop_at=d)
        assert rc == 0
        assert calls == []
        _declare_ruff(d)
        rc, calls = _run_main_with_payload({'tool_input': {'file_path': a}}, stop_at=d)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_mixed_batch_formats_only_the_declared_project():
    # One turn can touch files in several projects: only the ruff project's files
    # reach the single invocation, in first-seen order.
    with tempfile.TemporaryDirectory() as d:
        ruff_repo = os.path.join(d, 'ruff-repo')
        other_repo = os.path.join(d, 'other-repo')
        for repo in (ruff_repo, other_repo):
            os.makedirs(os.path.join(repo, '.git'))
        _declare_ruff(ruff_repo)
        a = _write(os.path.join(ruff_repo, 'a.py'))
        b = _write(os.path.join(other_repo, 'b.py'))
        c = _write(os.path.join(ruff_repo, 'pkg', 'c.py'))
        rc, calls = _run_main_with_payload(_batch(a, b, c), stop_at=d)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a, c]]


def test_main_malformed_payload_exits_0():
    with tempfile.TemporaryDirectory() as d:
        old_stdin, old_state = sys.stdin, os.environ.get(STATE_DIR_ENV)
        sys.stdin = io.StringIO('not json{{{')
        os.environ[STATE_DIR_ENV] = d
        try:
            rc = ruff_format.main()
        finally:
            sys.stdin = old_stdin
            if old_state is None:
                os.environ.pop(STATE_DIR_ENV, None)
            else:
                os.environ[STATE_DIR_ENV] = old_state
        assert rc == 0
        assert os.listdir(d) == []


def _log_records(d):
    path = os.path.join(d, 'hook-log.ndjson')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as fh:
        return [json.loads(x) for x in fh.read().splitlines() if x.strip()]


def test_main_dispatch_logs_one_line_with_the_file_count():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as state:
        _declare_ruff(d)
        a = _write(os.path.join(d, 'a.py'))
        b = _write(os.path.join(d, 'b.py'))
        payload = {**_batch(a, b), 'session_id': 's1'}
        rc, calls, _ = _run_main_capturing(payload, stop_at=d, state_dir=state)
        records = _log_records(state)
    assert rc == 0
    assert calls == [['uvx', 'ruff', 'format', a, b]]
    assert len(records) == 1, records
    assert set(records[0]) == {'ts', 'hook', 'files', 'session'}, records[0]
    assert records[0]['hook'] == 'ruff_format'
    assert records[0]['files'] == 2
    assert records[0]['session'] == 's1'


def test_main_without_dispatch_logs_nothing():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as state:
        a = _write(os.path.join(d, 'a.py'))
        rc, calls, _ = _run_main_capturing(_batch(a), stop_at=d, state_dir=state)
        assert (rc, calls) == (0, [])
        assert _log_records(state) == []


def test_main_still_exits_0_when_the_log_cannot_be_written():
    with tempfile.TemporaryDirectory() as d:
        _declare_ruff(d)
        a = _write(os.path.join(d, 'a.py'))
        blocker = _write(os.path.join(d, 'a-file'), '')
        rc, calls, err = _run_main_capturing(_batch(a), stop_at=d, state_dir=blocker)
    assert (rc, calls, err) == (0, [['uvx', 'ruff', 'format', a]], '')


if __name__ == '__main__':
    test_selects_py_file()
    test_ignores_non_py()
    test_handles_missing_input()
    test_runs_format_only()
    test_never_runs_destructive_autofix()
    test_batch_files_dedupes_write_and_edit_preserving_order()
    test_batch_files_ignores_non_write_edit_tools()
    test_batch_files_ignores_non_py()
    test_batch_files_non_list_tool_calls_is_empty()
    test_main_non_list_tool_calls_exits_0()
    test_existing_files_drops_missing()
    test_batch_command_single_invocation_for_multiple_paths()
    test_batch_command_empty_when_no_paths()
    test_main_batch_formats_deduped_paths_in_one_call()
    test_main_batch_of_one()
    test_main_batch_drops_missing_files()
    test_main_batch_empty_surviving_set_no_subprocess_call()
    test_main_legacy_payload_still_formats()
    test_main_malformed_payload_exits_0()
    test_file_outside_any_project_is_not_formatted()
    test_repo_without_ruff_config_is_not_formatted()
    test_ruff_toml_project_is_formatted()
    test_dot_ruff_toml_project_is_formatted()
    test_pyproject_tool_ruff_table_is_formatted()
    test_pyproject_ruff_lookalikes_do_not_declare_ruff()
    test_pyproject_ruff_spellings_other_than_the_table_header_are_not_detected()
    test_subpackage_pyproject_without_ruff_inherits_root_ruff_toml()
    test_walk_stops_at_git_boundary()
    test_walk_stops_at_stop_at()
    test_unreadable_or_garbage_pyproject_fails_open()
    test_legacy_payload_is_scoped_too()
    test_mixed_batch_formats_only_the_declared_project()
    test_main_dispatch_logs_one_line_with_the_file_count()
    test_main_without_dispatch_logs_nothing()
    test_main_still_exits_0_when_the_log_cannot_be_written()
    print('ok: all ruff_format tests passed')

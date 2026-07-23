"""Tests for ruff_format. Runnable with pytest or `python test_ruff_format.py`."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile

import ruff_format
from ruff_format import batch_command, batch_files, existing_files, ruff_commands, target_file


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


def _run_main_with_payload(payload):
    """Run ruff_format.main() with a fake stdin and a recording subprocess.run stub.

    Returns (return_code, calls) where calls is the list of argv lists that
    subprocess.run would have been invoked with.
    """
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)

        class _Result:
            returncode = 0

        return _Result()

    old_stdin = sys.stdin
    old_run = ruff_format.subprocess.run
    sys.stdin = io.StringIO(json.dumps(payload))
    ruff_format.subprocess.run = fake_run
    try:
        rc = ruff_format.main()
    finally:
        sys.stdin = old_stdin
        ruff_format.subprocess.run = old_run
    return rc, calls


def test_main_batch_formats_deduped_paths_in_one_call():
    with tempfile.TemporaryDirectory() as d:
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
        a = os.path.join(d, 'a.py')
        with open(a, 'w', encoding='utf-8') as fh:
            fh.write('x = 1\n')
        payload = {'tool_calls': [{'tool_name': 'Write', 'tool_input': {'file_path': a}}]}
        rc, calls = _run_main_with_payload(payload)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_main_batch_drops_missing_files():
    with tempfile.TemporaryDirectory() as d:
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
        a = os.path.join(d, 'a.py')
        with open(a, 'w', encoding='utf-8') as fh:
            fh.write('x = 1\n')
        payload = {'tool_input': {'file_path': a}}
        rc, calls = _run_main_with_payload(payload)
        assert rc == 0
        assert calls == [['uvx', 'ruff', 'format', a]]


def test_main_malformed_payload_exits_0():
    old_stdin = sys.stdin
    sys.stdin = io.StringIO('not json{{{')
    try:
        rc = ruff_format.main()
    finally:
        sys.stdin = old_stdin
    assert rc == 0


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
    print('ok: all ruff_format tests passed')

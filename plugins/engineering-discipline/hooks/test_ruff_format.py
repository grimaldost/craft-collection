"""Tests for ruff_format. Runnable with pytest or `python test_ruff_format.py`."""

from __future__ import annotations

from ruff_format import ruff_commands, target_file


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


if __name__ == '__main__':
    test_selects_py_file()
    test_ignores_non_py()
    test_handles_missing_input()
    test_runs_format_only()
    test_never_runs_destructive_autofix()
    print('ok: all ruff_format tests passed')

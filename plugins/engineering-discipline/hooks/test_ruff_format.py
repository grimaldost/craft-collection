"""Tests for ruff_format.target_file. Runnable with pytest or `python test_ruff_format.py`."""

from __future__ import annotations

from ruff_format import target_file


def test_selects_py_file():
    assert target_file({'tool_input': {'file_path': '/x/y.py'}}) == '/x/y.py'


def test_ignores_non_py():
    assert target_file({'tool_input': {'file_path': '/x/y.md'}}) is None


def test_handles_missing_input():
    assert target_file({}) is None
    assert target_file({'tool_input': {}}) is None


if __name__ == '__main__':
    test_selects_py_file()
    test_ignores_non_py()
    test_handles_missing_input()
    print('ok: all ruff_format tests passed')

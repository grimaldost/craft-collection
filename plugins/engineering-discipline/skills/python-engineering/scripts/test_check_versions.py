"""Tests for check_versions pure logic (no network).

Runnable with pytest OR directly: `python test_check_versions.py`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from check_versions import is_behind, load_precommit, load_tools

STACK = """\
[meta]
last_reviewed = "2026-06-04"

[tools.ruff]
pypi = "ruff"
pinned_min = "0.15"
category = "lint-format"

[tools.pytest]
pypi = "pytest"
pinned_min = "8.0"
category = "testing"

[precommit]
"ruff-pre-commit" = "v0.15.7"
"""


def _write_stack(d: Path) -> Path:
    p = d / 'stack.toml'
    p.write_text(STACK, encoding='utf-8')
    return p


def test_load_tools():
    with tempfile.TemporaryDirectory() as d:
        tools = load_tools(_write_stack(Path(d)))
        assert tools == {'ruff': '0.15', 'pytest': '8.0'}


def test_load_precommit():
    with tempfile.TemporaryDirectory() as d:
        assert load_precommit(_write_stack(Path(d))) == {'ruff-pre-commit': 'v0.15.7'}


def test_is_behind():
    assert is_behind('0.15', '0.18') is True
    assert is_behind('0.15', '0.15') is False
    assert is_behind('0.15', '0.14') is False
    assert is_behind('1.0', '2.0') is True
    assert is_behind('0.15', '0.15.7') is False  # 0.x patch -> churn, not behind
    assert is_behind('1.0', '1.0.5') is False    # stable patch -> not behind
    # 0.0.x (true 0ver, e.g. ty): the patch IS the release axis -> must be visible
    assert is_behind('0.0.1', '0.0.43') is True
    assert is_behind('0.0.1', '0.0.1') is False
    assert is_behind('0.0.1', '0.1.0') is True


if __name__ == '__main__':
    test_load_tools()
    test_load_precommit()
    test_is_behind()
    print('ok: all check_versions tests passed')

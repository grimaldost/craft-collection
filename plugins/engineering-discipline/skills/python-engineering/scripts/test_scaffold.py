"""Tests for scaffold pure logic.

Runnable with pytest OR directly: `python test_scaffold.py`.
"""

from __future__ import annotations

from scaffold import PRECOMMIT, name_error, render_ci, render_pyproject, resolve_names


def test_resolve_names():
    assert resolve_names('my-cool-tool') == {
        'pypi': 'my-cool-tool',
        'package': 'my_cool_tool',
        'class': 'MyCoolTool',
    }


def test_resolve_names_messy_input():
    n = resolve_names('My Cool_Tool!!')
    assert n['pypi'] == 'my-cool-tool'
    assert n['package'] == 'my_cool_tool'
    assert n['class'] == 'MyCoolTool'


def test_render_pyproject_substitutions():
    out = render_pyproject('my-cool-tool')
    assert 'name = "my-cool-tool"' in out
    assert 'known-first-party = ["my_cool_tool"]' in out
    assert 'build-backend = "uv_build"' in out
    assert 'quote-style = "single"' in out


def test_name_error_rejects_unimportable_package():
    assert name_error(resolve_names('my-cool-tool')) is None
    # digit-leading -> package '3d_tool' is not importable; must be rejected
    assert not resolve_names('3d-tool')['package'].isidentifier()
    assert name_error(resolve_names('3d-tool')) is not None


def test_render_ci_wires_ty_check():
    # ty has no pre-commit hook yet, so the generated CI must run it explicitly.
    out = render_ci('my-cool-tool')
    assert 'uv run ty check src' in out


def test_precommit_pins_current_ruff_version():
    # Scaffolded projects must not start life pinned to a ruff-pre-commit rev the
    # collection itself has already moved past.
    assert 'repo: https://github.com/astral-sh/ruff-pre-commit' in PRECOMMIT
    assert 'rev: v0.16.8' in PRECOMMIT
    assert 'v0.15.7' not in PRECOMMIT


if __name__ == '__main__':
    test_resolve_names()
    test_resolve_names_messy_input()
    test_render_pyproject_substitutions()
    test_name_error_rejects_unimportable_package()
    test_render_ci_wires_ty_check()
    test_precommit_pins_current_ruff_version()
    print('ok: all scaffold tests passed')

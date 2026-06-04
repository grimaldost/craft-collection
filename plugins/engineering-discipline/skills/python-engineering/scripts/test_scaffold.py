"""Tests for scaffold pure logic.

Runnable with pytest OR directly: `python test_scaffold.py`.
"""

from __future__ import annotations

from scaffold import name_error, render_pyproject, resolve_names


def test_resolve_names():
    assert resolve_names('my-cool-tool') == {
        'pypi': 'my-cool-tool', 'package': 'my_cool_tool', 'class': 'MyCoolTool',
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


if __name__ == '__main__':
    test_resolve_names()
    test_resolve_names_messy_input()
    test_render_pyproject_substitutions()
    test_name_error_rejects_unimportable_package()
    print('ok: all scaffold tests passed')

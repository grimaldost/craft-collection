"""Tests for uv_enforce.verdict. Runnable with pytest or `python test_uv_enforce.py`."""

from __future__ import annotations

from uv_enforce import verdict


def test_blocks_pip_in_uv_project():
    assert verdict('pip install requests', cwd_has_uv=True, allow_env=False) == 'block'


def test_allows_pip_outside_uv_project():
    assert verdict('pip install requests', cwd_has_uv=False, allow_env=False) == 'allow'


def test_escape_hatch_allows():
    assert verdict('pip install requests', cwd_has_uv=True, allow_env=True) == 'allow'


def test_allows_uv_commands():
    assert verdict('uv add requests', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict('uv sync', cwd_has_uv=True, allow_env=False) == 'allow'


def test_blocks_poetry_and_venv():
    assert verdict('poetry add x', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('python -m venv .venv', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('virtualenv .venv', cwd_has_uv=True, allow_env=False) == 'block'


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('ok: all uv_enforce tests passed')

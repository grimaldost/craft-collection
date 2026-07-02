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


def test_blocks_poetry_update():
    assert verdict('poetry update', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('poetry update requests', cwd_has_uv=True, allow_env=False) == 'block'


def test_blocks_pipenv():
    assert verdict('pipenv install', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('pipenv install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('pipenv sync', cwd_has_uv=True, allow_env=False) == 'block'


def test_blocks_conda_install():
    assert verdict('conda install pkg', cwd_has_uv=True, allow_env=False) == 'block'


def test_new_blocks_respect_escape_hatch():
    assert verdict('pipenv install', cwd_has_uv=True, allow_env=True) == 'allow'
    assert verdict('conda install pkg', cwd_has_uv=True, allow_env=True) == 'allow'


def test_does_not_false_positive_on_benign_commands():
    # `pytest` and `uv pip compile` must never be blocked, nor words that merely
    # contain 'pip'/'conda' as a substring.
    assert verdict('python -m pytest', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict('uv pip compile pyproject.toml', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict('echo anaconda', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict('grep pipenvironment notes.txt', cwd_has_uv=True, allow_env=False) == 'allow'


def test_allows_uv_pip_install():
    # `uv pip install` is uv's OWN pip interface — it must not be blocked.
    assert verdict('uv pip install requests', cwd_has_uv=True, allow_env=False) == 'allow'
    assert (
        verdict('uv pip install -r requirements.txt', cwd_has_uv=True, allow_env=False) == 'allow'
    )


def test_does_not_block_on_mere_mention():
    # `pip install` mentioned inside a quoted string or a non-command position is
    # not a real install invocation and must not be blocked.
    assert verdict('grep -rn "pip install" docs/', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict("grep -rn 'pip install' docs/", cwd_has_uv=True, allow_env=False) == 'allow'
    assert (
        verdict('git commit -m "document how to pip install foo"', cwd_has_uv=True, allow_env=False)
        == 'allow'
    )
    assert (
        verdict('echo "run pip install requests to set up"', cwd_has_uv=True, allow_env=False)
        == 'allow'
    )
    # A heredoc writing docs that mention pip install must not be blocked.
    heredoc = 'cat <<EOF > README.md\nTo bootstrap: pip install requests\nEOF'
    assert verdict(heredoc, cwd_has_uv=True, allow_env=False) == 'allow'
    # A `#`-comment mentioning pip install is not a command.
    assert (
        verdict('ls  # remember: pip install requests later', cwd_has_uv=True, allow_env=False)
        == 'allow'
    )


def test_blocks_real_install_at_command_positions():
    # A genuine install at a plausible command position IS still blocked.
    assert verdict('pip install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('echo hi && pip install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('true || poetry add requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('cd foo; pip3 install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('echo x | pip install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('result=$(pip install requests)', cwd_has_uv=True, allow_env=False) == 'block'
    # After a newline (multi-line command) is a command position too.
    assert (
        verdict('echo setting up\npip install requests', cwd_has_uv=True, allow_env=False)
        == 'block'
    )


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('ok: all uv_enforce tests passed')

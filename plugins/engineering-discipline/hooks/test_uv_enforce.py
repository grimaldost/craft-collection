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


def test_blocks_python_m_pip_install():
    # `python -m pip install` is the same act as `pip install` — the module form
    # must not slip past the command-position anchor (it did, once).
    assert verdict('python -m pip install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('python3 -m pip install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert (
        verdict('echo hi && python -m pip install requests', cwd_has_uv=True, allow_env=False)
        == 'block'
    )
    # `-m pipx` and `-m pytest` share the prefix but are not pip installs.
    assert verdict('python -m pipx install foo', cwd_has_uv=True, allow_env=False) == 'allow'


def test_hash_inside_a_word_is_not_a_comment():
    # bash starts a comment only at the start of a word; `url#frag` is literal,
    # so everything after it — including a real install — must still be scanned.
    assert (
        verdict('curl http://x.com/a#frag && pip install z', cwd_has_uv=True, allow_env=False)
        == 'block'
    )
    assert (
        verdict('wget file#1.txt; python3 -m pip install z', cwd_has_uv=True, allow_env=False)
        == 'block'
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


def test_blocks_py_launcher_pip_install():
    # Windows py-launcher form of `pip install`, bare and with a version flag.
    assert verdict('py -m pip install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('py -3 -m pip install requests', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('py -3.12 -m pip install requests', cwd_has_uv=True, allow_env=False) == 'block'


def test_blocks_py_launcher_venv():
    assert verdict('py -m venv .venv', cwd_has_uv=True, allow_env=False) == 'block'
    assert verdict('py -3 -m venv .venv', cwd_has_uv=True, allow_env=False) == 'block'


def test_powershell_semicolon_chain_blocks():
    # The PowerShell tool carries the same tool_input.command field as Bash; a
    # `;`-chained install must block the same way it does for Bash.
    assert verdict('cd x; pip install y', cwd_has_uv=True, allow_env=False) == 'block'


def test_py_launcher_does_not_false_positive_on_similar_words():
    assert verdict('py -m pytest', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict('uv pip install x', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict('grep "pip install"', cwd_has_uv=True, allow_env=False) == 'allow'
    # "happy"/"numpy" end in "py" but are not at a command position relative to
    # the py-launcher arm — must not match via the py arm or any other arm.
    assert verdict('happy -m pip install', cwd_has_uv=True, allow_env=False) == 'allow'
    assert verdict('numpy -m pip install x', cwd_has_uv=True, allow_env=False) == 'allow'


# The command reported on 2026-10-07: a PR body written with a heredoc, holding a
# markdown table with one row per updated package. A row's leading `|` put
# `virtualenv` at a command position and the hook blocked the write.
REPORTED_HEREDOC = (
    'cat > b.md <<EOF\n| Package | Version |\n| urllib3 | 2.0.7 |\n| virtualenv | 21.3.0 |\nEOF'
)
BACKSLASH = chr(92)


def _v(command):
    return verdict(command, cwd_has_uv=True, allow_env=False)


def test_heredoc_body_is_data_not_a_command():
    # One simple command into cat or tee, and a body that cannot run code: the
    # body is data and is not scanned.
    allowed = [
        REPORTED_HEREDOC,
        "cat > b.md <<'EOF'\n| virtualenv | 21.3.0 |\nEOF",
        'cat > b.md <<"EOF"\n| virtualenv | 21.3.0 |\nEOF',
        'cat > b.md <<' + BACKSLASH + 'EOF\n| virtualenv | 21.3.0 |\nEOF',
        'cat > b.md << EOF\n| virtualenv | 21.3.0 |\nEOF',
        'cat > b.md <<-EOF\n\t| virtualenv | 21.3.0 |\n\tEOF',
        'cat > notes.md <<EOF\npip install x\nEOF',
        "cat > notes.md <<'EOF'\n```\npip install foo\n```\nEOF",
        'cat > t.md <<EOF\n| name | virtualenv |\n| poetry add | x |\nEOF',
        'cat > t.md <<EOF\npoetry add x\nvirtualenv .venv\npython -m venv .venv\nEOF',
        'cat <<EOF >out.md\n| virtualenv |\nEOF',
        'cat <<EOF>out.md\n| virtualenv |\nEOF',
        '<<EOF cat > b.md\n| virtualenv |\nEOF',
        'LC_ALL=C /bin/cat > b.md <<EOF\n| virtualenv |\nEOF',
        'tee b.md <<EOF\n| virtualenv | 21.3.0 |\nEOF',
        # The whole word is the delimiter.
        'cat <<END-OF-FILE\n| virtualenv |\nEND-OF-FILE',
        "cat <<'END OF'\n| virtualenv |\nEND OF",
        # Two heredocs on one line: their bodies follow in order.
        'cat <<A <<B\n| virtualenv |\nA\npip install x\nB',
        # CRLF line endings.
        'cat > b.md <<EOF\r\n| virtualenv | 21.3.0 |\r\nEOF\r\n',
        # Unterminated: bash reads the rest of the input as the body.
        'cat > b.md <<EOF\n| virtualenv | 21.3.0 |',
        # Only the exact word ends the body, so what follows a near miss is body.
        'cat <<EOF\n| virtualenv |\nEOFX\npip install z',
        'cat <<EOF\n| virtualenv |\n  EOF\npip install z',
        'cat <<-EOF\n| virtualenv |\n  EOF\npip install z',
        # A body with an apostrophe no longer pairs quotes across the command.
        "cat > b.md <<'EOF'\nit's the | virtualenv | row\nEOF",
        # Unchanged from 0.6.0: a quoted span and a PowerShell here-string.
        'gh pr create --body "$(cat <<\'EOF\'\n| virtualenv | 21.3.0 |\nEOF\n)"',
        "$b = @'\n| virtualenv | 21.3.0 |\n'@",
    ]
    for command in allowed:
        assert _v(command) == 'allow', command


def test_command_text_around_a_heredoc_is_still_scanned():
    blocked = [
        'virtualenv x',
        'echo x | virtualenv .venv',
        # After the terminator.
        'cat <<EOF > a\nhi\nEOF\npip install requests',
        'cat <<EOF\r\nhi\r\nEOF\r\npip install z',
        'cat <<A <<B\nx\nA\ny\nB\npip install z',
        'cat <<-EOF\n\tbody\n\tEOF\npip install z',
        'cat <<END-OF-FILE\nx\nEND-OF-FILE\npip install z',
        "cat <<'END OF'\nx\nEND OF\npip install z",
        'cat <<EOF>out.md\nx\nEOF\npip install z',
        # A second command on the operator line, before or after the operator.
        'cat <<EOF && pip install requests\nhi\nEOF',
        'pip install requests && cat <<EOF\nhi\nEOF',
        # A table row outside any heredoc blocks as before.
        'printf x\n| virtualenv | 1 |',
    ]
    for command in blocked:
        assert _v(command) == 'block', command


def test_lookalikes_of_a_heredoc_operator_strip_nothing():
    blocked = [
        # Here-strings are not heredocs.
        'cat <<< x\n| virtualenv |',
        "cat <<< 'x'\npip install z",
        # Arithmetic shifts.
        'echo $((1<<2))\npip install z',
        'echo $((x<<y))\npip install z',
        '(( y = x << z ))\npip install z',
        'echo $[ x << y ]\npip install x',
        # A quoted, escaped or commented operator.
        'echo "<<EOF"\npip install z',
        "echo '<<EOF'\npip install z",
        'echo "a\nb <<EOF\n"\npip install z',
        'cat ' + BACKSLASH + '<<EOF\npip install foo',
        'ls # cat <<EOF\npip install z',
        'true;#<<EOF\npip install x',
        'true&&#<<EOF\npip install x',
        # A delimiter of another shape is not read at all.
        'cat <<EO$F\nx\nEO$F\npip install z',
    ]
    for command in blocked:
        assert _v(command) == 'block', command


def test_a_body_something_can_run_is_still_scanned():
    # The body is skipped only for one simple command into cat or tee.
    # A shell, an interpreter, a pipe, a subshell or a substitution may run it.
    blocked = [
        'bash <<EOF\npip install requests\nEOF',
        'sh -s <<EOF\npip install requests\nEOF',
        '/bin/bash <<EOF\npip install requests\nEOF',
        'ssh build-host <<EOF\npip install requests\nEOF',
        'source /dev/stdin <<EOF\npip install requests\nEOF',
        '. /dev/stdin <<EOF\npip install requests\nEOF',
        'eval "$(cat)" <<EOF\npip install requests\nEOF',
        'python - <<EOF\nimport os\npip install x\nEOF',
        'sudo bash <<EOF\npip install requests\nEOF',
        'env FOO=1 cat <<EOF | bash\npip install requests\nEOF',
        '<<EOF bash\npip install x\nEOF',
        '"cat" <<EOF\npip install x\nEOF',
        'cat <<EOF | bash\npip install requests\nEOF',
        'cat <<EOF | sudo -u ci bash\npip install requests\nEOF',
        'cat <<EOF | (bash)\npip install x\nEOF',
        'tee >(bash) <<EOF\npip install x\nEOF',
        '{ bash; } <<EOF\npip install x\nEOF',
        'while read l; do eval "$l"; done <<EOF\npip install x\nEOF',
        '$(cat <<EOF\npip install x\nEOF\n)',
        'v=$(cat <<EOF\nhello\nEOF)\npip install foo',
        'v=`cat <<EOF\nhello\nEOF`\npip install foo',
        'bash ' + BACKSLASH + '\n<<EOF\npip install requests\nEOF',
        'cat <<EOF && ' + BACKSLASH + '\npip install foo\nEOF',
        'cat <<EOF; echo "a\n"; pip install foo\nbody\nEOF',
        # The walk stops at a line that leaves a quote open or ends in a
        # backslash: here bash reads the operator inside a string, or continues
        # the operator line, and runs `pip`.
        'echo "a\ncat > x <<EOF\n"\npip install z\nEOF',
        'cat <<EOF ' + BACKSLASH + '\n&& pip install z\nbody\nEOF',
        # A body that is scanned is not read for heredoc operators: here bash
        # ends the outer body at A and runs `pip` itself.
        'sh <<A\ncat <<B\nA\npip install x\nB',
        "python3 - <<A\nprint('hi')\ncat > f <<B\nA\npip install x\nB",
        # git and gh are not sinks: an alias can hand the body to a shell.
        "git -c alias.x='!sh' x <<EOF\npip install x\nEOF",
    ]
    for command in blocked:
        assert _v(command) == 'block', command


def test_an_unquoted_body_with_a_substitution_is_scanned():
    # Under an unquoted delimiter bash runs `$(...)` and backticks in the body,
    # so such a body is scanned whole; a quoted delimiter makes it literal.
    blocked = [
        'cat <<EOF\n$(pip install x)\nEOF',
        'cat <<EOF\n$(\npip install x\n)\nEOF',
        'cat <<EOF\n${v:-$(pip install x)}\nEOF',
        'cat > notes.md <<EOF\n```\npip install foo\n```\nEOF',
        'cat <<EOF\n$(echo ")" ; pip install x)\nEOF',
        # Scanned whole, so a table row beside a substitution blocks too.
        'cat > t.md <<EOF\n| virtualenv | $(date) |\nEOF',
    ]
    for command in blocked:
        assert _v(command) == 'block', command
    assert _v("cat <<'EOF'\n$(pip install x)\nEOF") == 'allow'
    assert _v('cat <<"EOF"\n`pip install x`\nEOF') == 'allow'
    assert _v('cat <<' + BACKSLASH + 'EOF\n$(pip install x)\nEOF') == 'allow'


def test_shapes_outside_the_rule_keep_the_old_behaviour():
    # Not one simple command into a data sink: scanned as in 0.6.0, so a table
    # row in the body still blocks. Rewrite as `cat > file <<'EOF'` instead.
    blocked = [
        'body=$(cat <<EOF\n| virtualenv | 21.3.0 |\nEOF\n)',
        'while read l; do echo "$l"; done <<EOF\n| virtualenv |\nEOF',
        'cat <<EOF | grep x\n| virtualenv |\nEOF',
        'sudo tee /etc/x <<EOF\n| virtualenv |\nEOF',
        "git commit -F - <<'EOF'\nBump virtualenv\n\n| virtualenv | 21.3.0 |\nEOF",
        "gh pr create --title 'Bump deps' --body-file - <<'EOF'\n| virtualenv | 21.3.0 |\nEOF",
    ]
    for command in blocked:
        assert _v(command) == 'block', command


def test_blocked_match_names_the_matched_word():
    from uv_enforce import blocked_match

    assert blocked_match('echo x | virtualenv .venv') == 'virtualenv'
    assert blocked_match('cd a && pip3   install x') == 'pip3 install'
    assert blocked_match(REPORTED_HEREDOC) is None
    assert blocked_match('uv add requests') is None


def _run_main(command, uv_project=True, state_dir=None):
    """Run uv_enforce.main() on a hook JSON payload: (return code, stderr).

    The firing log goes to `state_dir`, or to a throwaway directory, so a test
    never writes to a real plugin data directory.
    """
    import io
    import json
    import os
    import sys
    import tempfile

    import uv_enforce

    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as scratch:
        if uv_project:
            with open(os.path.join(d, 'uv.lock'), 'w', encoding='utf-8') as fh:
                fh.write('')
        payload = {'tool_input': {'command': command}, 'cwd': d, 'session_id': 's1'}
        old_stdin, old_stderr = sys.stdin, sys.stderr
        old_allow = os.environ.pop('CLAUDE_ALLOW_PIP', None)
        old_state = os.environ.get(STATE_DIR_ENV)
        os.environ[STATE_DIR_ENV] = state_dir or scratch
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.stderr = io.StringIO()
        try:
            rc = uv_enforce.main()
            err = sys.stderr.getvalue()
        finally:
            sys.stdin, sys.stderr = old_stdin, old_stderr
            if old_allow is not None:
                os.environ['CLAUDE_ALLOW_PIP'] = old_allow
            if old_state is None:
                os.environ.pop(STATE_DIR_ENV, None)
            else:
                os.environ[STATE_DIR_ENV] = old_state
    return rc, err


STATE_DIR_ENV = 'ENGINEERING_DISCIPLINE_STATE_DIR'


def _log_records(d):
    import json
    import os

    path = os.path.join(d, 'hook-log.ndjson')
    if not os.path.exists(path):
        return None, []
    with open(path, encoding='utf-8') as fh:
        raw = fh.read()
    return raw, [json.loads(x) for x in raw.splitlines() if x.strip()]


def test_main_block_logs_one_line_without_the_command_text():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        rc, _ = _run_main('cd secret-token-123 && virtualenv .venv', state_dir=d)
        raw, records = _log_records(d)
    assert rc == 2
    assert len(records) == 1, records
    assert set(records[0]) == {'ts', 'hook', 'verdict', 'matched', 'session'}, records[0]
    assert records[0]['hook'] == 'uv_enforce'
    assert records[0]['verdict'] == 'block'
    assert records[0]['matched'] == 'virtualenv'
    assert records[0]['session'] == 's1'
    assert 'secret-token-123' not in raw


def test_main_allow_logs_nothing():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        assert _run_main(REPORTED_HEREDOC, state_dir=d) == (0, '')
        assert _run_main('pip install x', uv_project=False, state_dir=d) == (0, '')
        assert _log_records(d) == (None, [])


def test_main_block_still_exits_2_when_the_log_cannot_be_written():
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        blocker = os.path.join(d, 'a-file')
        with open(blocker, 'w', encoding='utf-8') as fh:
            fh.write('')
        rc, err = _run_main('pip install requests', state_dir=blocker)
    assert rc == 2
    assert '`pip install`' in err, err


def test_main_allows_the_reported_heredoc():
    assert _run_main(REPORTED_HEREDOC) == (0, '')


def test_main_block_names_the_matched_word():
    rc, err = _run_main('virtualenv .venv')
    assert rc == 2
    assert '`virtualenv`' in err, err
    assert 'uv add' in err, err


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('ok: all uv_enforce tests passed')

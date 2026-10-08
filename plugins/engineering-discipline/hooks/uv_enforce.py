#!/usr/bin/env python3
"""PreToolUse hook: steer Bash toward uv inside uv-managed projects.

Blocks `pip install`, `poetry add/install`, `virtualenv`, and `python -m venv`
when the cwd is a uv project (uv.lock, or [tool.uv]/uv_build in pyproject.toml),
unless CLAUDE_ALLOW_PIP=1. Exits 2 (blocking, stderr fed to Claude, naming the
matched words) on a block; otherwise 0. Never fires outside a uv project. Quoted
spans, comments and heredoc bodies are data, not commands, and are not scanned,
except a heredoc body fed to a shell (`bash <<EOF`), which is executed.
Stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import hook_log

# Commands redirected to uv when inside a uv project. Word boundaries keep
# `pip`/`conda`/`pipenv` from matching as substrings of unrelated words. Each
# alternative is anchored at a *command position* (start of string, or right
# after a shell separator — see `_CMD_POS`) so a mere mention of "pip install"
# inside an argument (`grep "pip install"`) is not a match. The `pip` arm carries
# a negative lookbehind for `uv ` so uv's own `uv pip install` interface is left
# alone (only bare `pip`/`pip3 install` is redirected). `python -m pip install`
# is the same act in module form and needs its own arm: there the *interpreter*
# sits at the command position, so the bare-pip arm cannot see it. The Windows
# py-launcher (`py`, optionally `-3` or `-3.N`) is the same interpreter-form
# again under a different name and needs its own arms too; because it is
# anchored at the command position the same way, a longer word merely ending in
# "py" (numpy, happy) at that position is not "py" and does not match.
_CMD_POS = r'(?:^|(?<=[\n;|&])|(?<=\|\|)|(?<=&&)|(?<=\$\())\s*'
_PY_LAUNCHER_VERSION = r'(?:\s+-3(?:\.\d+)?)?'
_BLOCKED = re.compile(
    _CMD_POS + r'(?:'
    r'(?<!uv )pip3?\s+install'
    r'|python3?\s+-m\s+pip\s+install'
    r'|poetry\s+(?:add|install|update)'
    r'|pipenv\b'
    r'|conda\s+install'
    r'|virtualenv\b'
    r'|python3?\s+-m\s+venv'
    r'|py' + _PY_LAUNCHER_VERSION + r'\s+-m\s+pip\s+install'
    r'|py' + _PY_LAUNCHER_VERSION + r'\s+-m\s+venv'
    r')\b'
)

# Strip quoted regions (their contents are data, not a command) and trailing
# `#`-comments before scanning, so a documented or logged "pip install" mention
# cannot trip the matcher. This is a deliberately coarse shell approximation:
# it neutralizes the false-positive surface without pretending to be a real
# parser. A quoted span becomes a single space so it can still act as a
# separator (`echo "x" && pip install` keeps the `&&`). A `#` starts a comment
# only at the start of a word (input start or after whitespace), matching bash:
# `url#frag` is literal data, and what follows it must stay scannable.
_QUOTED_OR_COMMENT = re.compile(
    r""""[^"]*"|'[^']*'|(?:^|(?<=\s))\#[^\n]*""",
)
_QUOTED = re.compile(r""""[^"]*"|'[^']*'""")

# Heredoc bodies are data too (a markdown table written with `cat <<EOF` put
# `| virtualenv |` at a command position after the row's leading pipe). The
# operator is `<<` or `<<-` followed by a bare, 'quoted', "quoted" or
# backslashed word; `<<<` (a here-string) and a digit after `<<` (an arithmetic
# shift such as `$((1<<2))`) are not heredocs.
_HEREDOC_OP = re.compile(
    r"""(?<!<)<<(?!<)(-?)[ \t]*(?:'([A-Za-z_]\w*)'|"([A-Za-z_]\w*)"|\\?([A-Za-z_]\w*))"""
)
# A body fed to a shell interpreter is executed, so it stays scannable: the
# command word before the operator, or a pipe into a shell after it.
_SHELLS = frozenset({'sh', 'bash', 'zsh', 'dash', 'ksh', 'source', '.', 'eval', 'ssh'})
_PIPE_TO_SHELL = re.compile(r'\|\s*(?:\S*/)?(?:sh|bash|zsh|dash|ksh|ssh)(?![\w.-])')
_SEGMENT_SPLIT = re.compile(r'[;&|(`{]')
_ASSIGNMENT = re.compile(r'[A-Za-z_]\w*=')


def _shell_state(text: str) -> str:
    """The quoting state at the end of `text`: '' (code), a quote char, or '#'.

    The same coarse model as `_QUOTED_OR_COMMENT`: no escapes, and `#` opens a
    comment only at the start of a word.
    """
    state, prev = '', '\n'
    for ch in text:
        if state in ('"', "'"):
            if ch == state:
                state = ''
        elif state == '#':
            if ch == '\n':
                state = ''
        elif ch in '"\'':
            state = ch
        elif ch == '#' and prev.isspace():
            state = '#'
        prev = ch
    return state


def _feeds_a_shell(line_prefix: str, line_rest: str) -> bool:
    segment = _SEGMENT_SPLIT.split(_QUOTED.sub(' ', line_prefix))[-1]
    words = [w for w in segment.split() if not _ASSIGNMENT.match(w)]
    if words and words[0].rsplit('/', 1)[-1] in _SHELLS:
        return True
    return bool(_PIPE_TO_SHELL.search(_QUOTED.sub(' ', line_rest)))


def _heredoc_ops(shell_text: str, line: str) -> list[tuple[str, bool, bool]]:
    """`(word, dash, executed)` for each heredoc operator on `line`, in order.

    `shell_text` is the command text kept so far, so an operator inside a quoted
    span that opened on an earlier line, or inside a comment, does not count.
    """
    ops = []
    for m in _HEREDOC_OP.finditer(line):
        prefix = line[: m.start()]
        if _shell_state(shell_text + prefix):
            continue
        if prefix.count('$((') > prefix.count('))'):
            continue
        word = m.group(2) or m.group(3) or m.group(4)
        ops.append((word, m.group(1) == '-', _feeds_a_shell(prefix, line[m.end() :])))
    return ops


def _strip_heredoc_bodies(command: str) -> str:
    """Blank the body and terminator lines of each heredoc, keeping all else.

    A line-based walk with a FIFO of pending terminators, as bash reads them:
    the bodies of several operators on one line follow in order. A terminator
    is the exact word on its own line (`\\r` ignored; leading tabs too after
    `<<-`). An unterminated heredoc runs to the end of input, as in bash.
    """
    out: list[str] = []
    pending: list[tuple[str, bool, bool]] = []
    shell_text = ''
    for line in command.split('\n'):
        if pending:
            word, dash, executed = pending[0]
            probe = line.rstrip('\r')
            if dash:
                probe = probe.lstrip('\t')
            if probe == word:
                pending.pop(0)
                out.append('')
            else:
                out.append(line if executed else '')
            continue
        pending.extend(_heredoc_ops(shell_text, line))
        shell_text += line + '\n'
        out.append(line)
    return '\n'.join(out)


def _strip_noncommand(command: str) -> str:
    """Blank out heredoc bodies, quoted spans and `#`-comments, leaving command text."""
    return _QUOTED_OR_COMMENT.sub(' ', _strip_heredoc_bodies(command))


def cwd_is_uv_project(cwd: str | None) -> bool:
    d = Path(cwd) if cwd else Path.cwd()
    if (d / 'uv.lock').is_file():
        return True
    pyproject = d / 'pyproject.toml'
    if pyproject.is_file():
        text = pyproject.read_text(encoding='utf-8', errors='ignore')
        return '[tool.uv]' in text or 'uv_build' in text
    return False


def blocked_match(command: str) -> str | None:
    """The blocked words found at a command position (`pip install`), or None.

    Whitespace inside the match is collapsed to one space. Ignores the cwd and
    the override; `verdict` applies those.
    """
    m = _BLOCKED.search(_strip_noncommand(command or ''))
    return ' '.join(m.group(0).split()) if m else None


def verdict(command: str, cwd_has_uv: bool, allow_env: bool) -> str:
    """Return 'block' or 'allow' for a Bash command."""
    if allow_env or not cwd_has_uv:
        return 'allow'
    return 'block' if blocked_match(command) else 'allow'


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = (payload.get('tool_input') or {}).get('command', '')
    allow = os.environ.get('CLAUDE_ALLOW_PIP') == '1'
    if verdict(command, cwd_is_uv_project(payload.get('cwd')), allow) == 'block':
        matched = blocked_match(command)
        session = payload.get('session_id')
        hook_log.append(
            {
                'hook': 'uv_enforce',
                'verdict': 'block',
                'matched': matched,
                'session': session if isinstance(session, str) else None,
            }
        )
        print(
            f'Blocked `{matched}`. '
            'This is a uv-managed project. Use `uv add <pkg>` for dependencies '
            'or `uv venv` / `uv sync` for environments, instead of '
            'pip/poetry/virtualenv. Set CLAUDE_ALLOW_PIP=1 to override.',
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

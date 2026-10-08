#!/usr/bin/env python3
"""PreToolUse hook: steer Bash toward uv inside uv-managed projects.

Blocks `pip install`, `poetry add/install`, `virtualenv`, and `python -m venv`
when the cwd is a uv project (uv.lock, or [tool.uv]/uv_build in pyproject.toml),
unless CLAUDE_ALLOW_PIP=1. Exits 2 (blocking, stderr fed to Claude, naming the
matched words) on a block; otherwise 0. Never fires outside a uv project. Quoted
spans and comments are data, not commands, and are not scanned; so is a heredoc
body written by one simple command into cat, tee, git or gh that cannot run code
(see `_data_heredocs`). Stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
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

# Heredoc bodies are data when nothing can run them: a markdown table written
# with `cat > b.md <<EOF` put `| virtualenv |` at a command position after the
# row's leading pipe. The rule is narrow on purpose. A body is skipped only when
# its operator line is one simple command (outside quotes: no `;`, `&`, `|`,
# parentheses, braces, `$(` or backtick, and no trailing backslash) whose
# program is a data sink, and the body cannot run code (a quoted delimiter, or no
# `$(` or backtick in it). Every other heredoc is scanned as before, and so is
# everything after a line that leaves a quote open: a shape the rule does not
# recognise keeps the 0.6.0 behaviour.
_DATA_SINKS = frozenset({'cat', 'tee', 'git', 'gh'})
_HEREDOC_OP = re.compile(
    r"""(?<![<\\])<<(?!<)(-?)[ \t]*"""
    r"""(?:'([^'\n]+)'|"([^"\n]+)"|(\\?)([A-Za-z_][\w.-]*))"""
    r"""(?=[\s;&|()<>]|$)"""
)
_QUOTED_SPAN = re.compile(r""""(?:[^"\\\n]|\\.)*"|'[^'\n]*'""")
_COMMENT_START = re.compile(r'(?:^|(?<=\s))#')
_NOT_SIMPLE = re.compile(r'[;&|(){}`]')
_ASSIGNMENT = re.compile(r'[A-Za-z_]\w*=')
_BARE_REDIRECT = re.compile(r'\d*(?:>>|>\||>|<)')
_ATTACHED_REDIRECT = re.compile(r'\d*(?:>>|>\||>|<)\S')


@dataclass
class _Heredoc:
    word: str
    dash: bool  # `<<-`: leading tabs are stripped before the terminator check
    literal: bool  # a quoted or backslashed delimiter: no expansion in the body


def _program(words: list[str]) -> str | None:
    """The command word of a simple command, past assignments and redirections."""
    skip_next = False
    for word in words:
        if skip_next:
            skip_next = False
        elif _BARE_REDIRECT.fullmatch(word):
            skip_next = True
        elif not (_ASSIGNMENT.match(word) or _ATTACHED_REDIRECT.match(word)):
            return word.rsplit('/', 1)[-1]
    return None


def _data_heredocs(line: str) -> list[_Heredoc] | None:
    """The heredocs opened on `line` whose bodies are data.

    Empty when the line opens none, or is not one simple command into a data
    sink. None when the line leaves a quote open or ends in a backslash: the
    walk cannot follow the command past it, so it stops stripping there.
    """
    masked = _QUOTED_SPAN.sub(lambda m: ' ' * len(m.group(0)), line.rstrip('\r'))
    if '"' in masked or "'" in masked or masked.endswith('\\'):
        return None
    comment = _COMMENT_START.search(masked)
    if comment:
        masked = masked[: comment.start()]
    ops = [m for m in _HEREDOC_OP.finditer(line) if masked[m.start() : m.start() + 2] == '<<']
    rest = masked
    for m in ops:
        rest = rest[: m.start()] + ' ' * (m.end() - m.start()) + rest[m.end() :]
    if not ops or _NOT_SIMPLE.search(rest) or '$(' in rest:
        return []
    if _program(rest.split()) not in _DATA_SINKS:
        return []
    return [
        _Heredoc(
            word=m.group(2) or m.group(3) or m.group(5),
            dash=m.group(1) == '-',
            literal=not m.group(5) or bool(m.group(4)),
        )
        for m in ops
    ]


def _strip_heredoc_bodies(command: str) -> str:
    """Blank the body and terminator lines of each data heredoc, keeping all else.

    A line walk; the bodies of several heredocs on one line follow in order, as
    bash reads them. A terminator is the exact word on its own line (`\\r`
    ignored, and leading tabs after `<<-`); an unterminated body runs to the end
    of input. An unquoted body holding `$(` or a backtick is kept for scanning.
    """
    lines = command.split('\n')
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        docs = _data_heredocs(line)
        if docs is None:
            out.extend(lines[i:])
            break
        for doc in docs:
            body: list[str] = []
            ended = False
            while i < len(lines) and not ended:
                probe = lines[i].rstrip('\r')
                ended = (probe.lstrip('\t') if doc.dash else probe) == doc.word
                body.append(lines[i])
                i += 1
            runs_code = not doc.literal and any('$(' in b or '`' in b for b in body)
            out.extend(body if runs_code else [''] * len(body))
    return '\n'.join(out)


def _strip_noncommand(command: str) -> str:
    """Blank out data heredoc bodies, quoted spans and `#`-comments, leaving command text."""
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

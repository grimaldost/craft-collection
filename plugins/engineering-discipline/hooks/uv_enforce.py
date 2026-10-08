#!/usr/bin/env python3
"""PreToolUse hook: steer Bash toward uv inside uv-managed projects.

Blocks `pip install`, `poetry add/install`, `virtualenv`, and `python -m venv`
when the cwd is a uv project (uv.lock, or [tool.uv]/uv_build in pyproject.toml),
unless CLAUDE_ALLOW_PIP=1. Exits 2 (blocking, stderr fed to Claude, naming the
matched words) on a block; otherwise 0. Never fires outside a uv project. Quoted
spans and comments are data, not commands, and are not scanned; so is a heredoc
body written by one simple command into cat or tee that cannot run code (see
`_heredocs`). Stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
import shlex
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
# row's leading pipe. The rule is narrow and the walk is fail-closed. Each
# command line is read with quotes, backslash escapes and a `#`-comment masked,
# and the walk stops, leaving the rest of the command to the 0.6.0 scan, at the
# first line it cannot follow exactly: a quote left open or a trailing
# backslash; a parenthesis, brace or backtick outside `${...}`, or a compound or
# command-redefining keyword (`do`, `then`, `case`, `function`, `exec`, ...),
# any of which can send a later `cat` somewhere else; a `<<` it cannot parse;
# or a heredoc operator on a line holding more than one command. On a plain
# line, the heredocs are read in order up to their terminators. A body is
# skipped only when the line's program is `cat` or `tee` and the body cannot
# run code: a quoted delimiter, or no `$(` or backtick in it. Every other body
# is passed to the scan whole and not read for heredocs of its own, and an
# unquoted body line ending in a backslash stops the walk.
_DATA_SINKS = frozenset({'cat', 'tee'})
_STOP_WORDS = frozenset(
    {
        'if',
        'then',
        'else',
        'elif',
        'fi',
        'for',
        'while',
        'until',
        'do',
        'done',
        'case',
        'esac',
        'select',
        'function',
        'coproc',
        'exec',
        'alias',
        'hash',
        'enable',
    }
)
_HEREDOC_OP = re.compile(
    r"""(?<![<\\])<<(?!<)(-?)[ \t]*"""
    r"""(?:'([^'\n]+)'|"([^"\n]+)"|(\\?)([A-Za-z_][\w.-]*))"""
    r"""(?=[\s;&|()<>]|$)"""
)
_ANY_HEREDOC_OP = re.compile(r'(?<!<)<<(?!<)')
_PARAM_EXPANSION = re.compile(r'\$\{[^{}()`]*\}')
_OPENERS = re.compile(r'[(){}`]')
_MULTI = re.compile(r'[;&|]')
_ASSIGNMENT = re.compile(r'[A-Za-z_]\w*=')
_BARE_REDIRECT = re.compile(r'\d*(?:>>|>\||<>|>|<)')
_ATTACHED_REDIRECT = re.compile(r'\d*(?:>>|>\||<>|>|<)\S')


@dataclass
class _Heredoc:
    word: str
    dash: bool  # `<<-`: leading tabs are stripped before the terminator check
    literal: bool  # a quoted or backslashed delimiter: no expansion in the body
    data: bool  # opened by one simple command into a data sink


def _mask(line: str) -> tuple[str, bool]:
    """`line` with quoted spans and escaped characters blanked, cut at a comment.

    Positions match `line` up to the cut. The flag is true when the line leaves
    a quote open or ends in a backslash, so the next line continues it.
    """
    out: list[str] = []
    quote = ''
    word_start = True
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            step = 2 if quote == '"' and ch == '\\' and i + 1 < len(line) else 1
            out.append(' ' * step)
            if step == 1 and ch == quote:
                quote = ''
            word_start = False
            i += step
            continue
        if ch == '\\':
            if i + 1 == len(line):
                return ''.join(out), True
            out.append('  ')
            word_start = False
            i += 2
            continue
        if ch == '#' and word_start:
            break
        if ch in '\'"':
            quote = ch
        out.append(' ' if ch in '\'"' else ch)
        word_start = ch in ' \t;&|()<>'
        i += 1
    return ''.join(out), bool(quote)


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


def _heredocs(line: str) -> list[_Heredoc] | None:
    """The heredocs opened on `line`, in order, each marked data or not.

    None when the walk has to stop at this line (see the comment above).
    """
    text = line.rstrip('\r')
    masked, continues = _mask(text)
    if continues:
        return None
    plain = _PARAM_EXPANSION.sub(lambda m: ' ' * len(m.group(0)), masked)
    if _OPENERS.search(plain) or _STOP_WORDS.intersection(plain.split()):
        return None
    ops = [m for m in _HEREDOC_OP.finditer(text) if masked[m.start() : m.start() + 2] == '<<']
    if len(ops) != len(_ANY_HEREDOC_OP.findall(masked)):
        return None
    if not ops:
        return []
    command = text[: len(masked)]
    for m in reversed(ops):
        command = command[: m.start()] + ' ' + command[m.end() :]
    if _MULTI.search(_mask(command)[0]):
        return None
    try:
        program = _program(shlex.split(command))
    except ValueError:
        return None
    return [
        _Heredoc(
            word=m.group(2) or m.group(3) or m.group(5),
            dash=m.group(1) == '-',
            literal=not m.group(5) or bool(m.group(4)),
            data=program in _DATA_SINKS,
        )
        for m in ops
    ]


def _strip_heredoc_bodies(command: str) -> str:
    """Blank the body and terminator lines of each data heredoc, keeping all else.

    A line walk; the bodies of several heredocs on one line follow in order, as
    bash reads them. A terminator is the exact word on its own line (`\\r`
    ignored, and leading tabs after `<<-`); an unterminated body runs to the end
    of input.
    """
    lines = command.split('\n')
    out: list[str] = []
    i = 0
    while i < len(lines):
        docs = _heredocs(lines[i])
        if docs is None:
            return '\n'.join(out + lines[i:])
        out.append(lines[i])
        i += 1
        for doc in docs:
            body: list[str] = []
            ended = False
            while i < len(lines) and not ended:
                probe = lines[i].rstrip('\r')
                if not doc.literal and probe.endswith('\\'):
                    # bash joins a backslash-newline in an unquoted body before it
                    # expands it or looks for the terminator; the walk does not.
                    return '\n'.join(out + body + lines[i:])
                ended = (probe.lstrip('\t') if doc.dash else probe) == doc.word
                body.append(lines[i])
                i += 1
            runs_code = not doc.literal and any('$(' in b or '`' in b for b in body)
            out.extend([''] * len(body) if doc.data and not runs_code else body)
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

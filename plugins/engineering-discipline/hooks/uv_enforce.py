#!/usr/bin/env python3
"""PreToolUse hook: steer Bash toward uv inside uv-managed projects.

Blocks `pip install`, `poetry add/install`, `virtualenv`, and `python -m venv`
when the cwd is a uv project (uv.lock, or [tool.uv]/uv_build in pyproject.toml),
unless CLAUDE_ALLOW_PIP=1. Exits 2 (blocking, stderr fed to Claude, naming the
matched words) on a block; otherwise 0. Never fires outside a uv project. Quoted
spans, comments and heredoc bodies are data, not commands, and are not scanned,
with two exceptions that run: a heredoc body fed to a shell (`bash <<EOF`), and
the `$(...)` and backtick spans in the body of an unquoted heredoc (`<<EOF`).
Stdlib-only.
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

# Heredoc bodies are data too (a markdown table written with `cat <<EOF` put
# `| virtualenv |` at a command position after the row's leading pipe). The
# operator is `<<` or `<<-` followed by a bare, 'quoted', "quoted" or
# backslashed word, which ends at a shell metacharacter; any other word shape
# is left unstripped. `<<<` (a here-string) and a `<<` inside an arithmetic
# context (`$((1<<2))`, `(( x << y ))`) are not heredocs.
_HEREDOC_OP = re.compile(
    r"""(?<!<)<<(?!<)(-?)[ \t]*"""
    r"""(?:'([^'\n]+)'|"([^"\n]+)"|(\\?)([A-Za-z_][\w.-]*))"""
    r"""(?=[\s|&;()<>]|$)"""
)
# A body fed to a shell interpreter is executed, so it stays scannable: the
# simple command holding the operator is a shell or names one (`sudo bash`,
# `env X=1 sh -s`, `<<EOF bash`), the operator redirects a group or loop that
# runs one (`{ bash; } <<EOF`), or the operator line pipes into one
# (`| sudo bash`, `| (bash)`). A quoted shell name counts (`"bash"`).
_SHELL_PROGRAMS = frozenset({'sh', 'bash', 'zsh', 'dash', 'ksh', 'ssh'})
_SHELLS = _SHELL_PROGRAMS | {'source', '.', 'eval'}
_SEGMENT_SPLIT = re.compile(r'[;&|(`{\n]')
_COMMAND_END = re.compile(r'[;&|)}`\n]')
_ANY_SPLIT = re.compile(r'[;&|(){}`\n]')
_GROUP_ENDS = frozenset({'done', 'fi', 'esac'})
_KEYWORDS = frozenset({'!', 'do', 'then', 'else', 'elif', 'if', 'while', 'until', 'time'})
_QUOTED_WORD = re.compile(r""""([^"]*)"|'([^']*)'""")
_PLAIN = re.compile(r'[^\s;&|()<>`$]*')
_ASSIGNMENT = re.compile(r'[A-Za-z_]\w*=')
# Contexts in which `<<` is a redirection: top-level code, a subshell, and a
# command substitution (`$(...)` or backticks, also inside double quotes).
_CODE = frozenset({'code', 'paren', 'subst', 'backtick'})
_ESCAPED = ('escaped',)
# A `#` starts a comment at the start of a word: after whitespace or a
# metacharacter (`true;#`), never inside one (`url#frag`, `${#x}`).
_WORD_START = frozenset(' \t\r\n;&|()<>')


class _Context:
    """A coarse shell context tracker, fed the command text line by line.

    Tracks quotes, backslash escapes, `#`-comments, `$(`, backticks, `(` and
    arithmetic `((`/`$((`/`$[` as a stack. Not a parser: it only has to say whether
    a `<<` sits in code and whether a line leaves a quote open.
    """

    def __init__(self) -> None:
        self.stack = ['code']
        self.prev = '\n'
        self.escaped_newline = False

    def _push_expansion(self, text: str, i: int) -> int:
        """Push `$((`, `$[` or `$(` at `i`; return its length, or 0 if none."""
        if text.startswith('$((', i):
            self.stack.append('arith')
            return 3
        if text.startswith('$[', i):
            self.stack.append('arith[')
            return 2
        if text.startswith('$(', i):
            self.stack.append('subst')
            return 2
        return 0

    def feed(self, text: str) -> list[tuple[str, ...]]:
        """Consume `text`; return the context stack before each character."""
        snaps: list[tuple[str, ...]] = []
        self.escaped_newline = False
        i = 0
        while i < len(text):
            snaps.append(tuple(self.stack))
            ch, top, step = text[i], self.stack[-1], 1
            if top == "'":
                if ch == "'":
                    self.stack.pop()
            elif top == '#':
                if ch == '\n':
                    self.stack.pop()
            elif ch == '\\':
                step = 2
                self.escaped_newline = text[i + 1 : i + 2] == '\n' and i + 2 == len(text)
                snaps.append(_ESCAPED)
            elif top == '"':
                if ch == '"':
                    self.stack.pop()
                elif ch == '`':
                    self.stack.append('backtick')
                else:
                    step = self._push_expansion(text, i) or 1
            elif ch in '"\'':
                self.stack.append(ch)
            elif ch == '`':
                if top == 'backtick':
                    self.stack.pop()
                else:
                    self.stack.append('backtick')
            elif ch == '#' and self.prev in _WORD_START and not top.startswith('arith'):
                self.stack.append('#')
            elif text.startswith(('$(', '$['), i):
                step = self._push_expansion(text, i)
            elif ch in '[]' and top == 'arith[':
                if ch == '[':
                    self.stack.append('arith[')
                else:
                    self.stack.pop()
            elif text.startswith('((', i):
                self.stack.append('arith')
                step = 2
            elif ch == '(':
                self.stack.append('paren')
            elif ch == ')':
                if top == 'arith' and text.startswith('))', i):
                    self.stack.pop()
                    step = 2
                elif top in ('paren', 'subst'):
                    self.stack.pop()
            while len(snaps) < min(i + step, len(text)):
                snaps.append(snaps[-1])
            # An escaped character is part of a word, never a word boundary.
            self.prev = 'x' if snaps[-1] == _ESCAPED else text[min(i + step, len(text)) - 1]
            i += step
        return snaps

    def continues(self) -> bool:
        """Whether the text fed so far leaves the current command line open."""
        return self.stack[-1] in ('"', "'") or self.escaped_newline


def _unquote(text: str) -> str:
    """Join continued lines; unquote a plain quoted word, blank any other quoted span."""

    def plain(m: re.Match[str]) -> str:
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        return inner if _PLAIN.fullmatch(inner) else ' '

    return _QUOTED_WORD.sub(plain, text.replace('\\\n', ' '))


def _runs_a_shell(segment: str) -> bool:
    names = [w.rsplit('/', 1)[-1] for w in segment.split() if not _ASSIGNMENT.match(w)]
    while names and names[0] in _KEYWORDS:
        names.pop(0)
    return bool(names) and (names[0] in _SHELLS or bool(_SHELL_PROGRAMS.intersection(names)))


def _feeds_a_shell(prefix: str, rest: str) -> bool:
    prefix, rest = _unquote(prefix), _unquote(rest)
    head = _SEGMENT_SPLIT.split(prefix)[-1]
    if _runs_a_shell(head + ' ' + _COMMAND_END.split(rest, 1)[0]):
        return True
    # The operator redirects a group or loop: what runs inside it reads the body.
    group = ')' in head or '}' in head or (head.split() or [''])[0] in _GROUP_ENDS
    if group and any(_runs_a_shell(s) for s in _ANY_SPLIT.split(prefix)):
        return True
    _, pipe, piped = rest.partition('|')
    return bool(pipe) and any(_runs_a_shell(s) for s in _ANY_SPLIT.split(piped))


def _substitution_end(ctx: _Context, text: str) -> int | None:
    """Feed `text` to the open substitution in `ctx`; where it closes, or None."""
    snaps = ctx.feed(text)
    return next((j for j, s in enumerate(snaps) if s == ('code',)), None)


def _expansions_only(line: str, state: list) -> str:
    """Keep the `$(...)` and backtick spans of an unquoted-heredoc body line.

    Those run; the rest of the line is literal text and becomes spaces. A
    backtick becomes `;` so its contents sit at a command position. A `$(...)`
    span is code, read with the same context tracker, so a quoted or escaped
    `)` does not close it. `state` is `[open substitution's _Context or None,
    inside backticks]`, carried from line to line.
    """
    out: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if state[0] is not None:
            end = _substitution_end(state[0], line[i:] + '\n')
            stop = len(line) if end is None else min(i + end, len(line))
            out.append(line[i:stop])
            state[0] = state[0] if end is None else None
            i = stop
            continue
        if state[1]:
            state[1] = int(ch != '`')
            out.append(';' if ch == '`' else ch)
        elif ch == '\\':
            out.append('  ')
            i += 1
        elif line.startswith('$(', i):
            state[0] = _Context()
            state[0].stack.append('subst')
            out.append('$(')
            i += 1
        elif ch == '`':
            state[1] = 1
            out.append(';')
        else:
            out.append(' ')
        i += 1
    return ''.join(out)


@dataclass
class _Heredoc:
    word: str
    dash: bool  # `<<-`: leading tabs are stripped before the terminator check
    literal: bool  # a quoted delimiter: no expansion in the body
    nested: bool  # the operator sits inside `$(...)` or backticks
    span: tuple[int, int]  # the operator's place in its logical line
    executed: bool = False  # the body is fed to a shell


def _strip_heredoc_bodies(command: str) -> str:
    """Blank the body and terminator lines of each heredoc, keeping all else.

    A line-based walk with a FIFO of pending terminators, as bash reads them:
    the bodies of several operators on one line follow in order, starting after
    the line that ends the command (a quote left open or a trailing backslash
    continues it). A terminator is the exact word on its own line (`\\r`
    ignored; leading tabs too after `<<-`); inside `$(...)` or backticks, a line
    that starts with the word and closes the substitution ends the body too, and
    the rest of that line is code. An unterminated heredoc runs to the end of
    input, as in bash. A quoted delimiter makes the body literal; an unquoted one
    leaves its `$(...)` and backticks running, so those are kept.
    """
    out: list[str] = []
    pending: list[_Heredoc] = []
    ctx = _Context()
    logical = ''
    fresh: list[_Heredoc] = []
    expand: list = [None, 0]
    body_open = False
    for raw in command.split('\n'):
        line = raw
        if body_open:
            doc = pending[0]
            probe = line.rstrip('\r')
            if doc.dash:
                probe = probe.lstrip('\t')
            rest = probe[len(doc.word) :] if probe.startswith(doc.word) else None
            if probe == doc.word:
                pending.pop(0)
                expand = [None, 0]
                body_open = bool(pending)
                out.append('')
                continue
            if doc.nested and rest is not None and (')' in rest or '`' in rest):
                pending.pop(0)
                expand = [None, 0]
                body_open = bool(pending)
                line = rest
            else:
                if doc.executed:
                    out.append(line)
                elif doc.literal:
                    out.append('')
                else:
                    out.append(_expansions_only(line, expand))
                continue
        start = len(logical)
        snaps = ctx.feed(line + '\n')
        logical += line + '\n'
        for m in _HEREDOC_OP.finditer(line):
            stack = snaps[m.start()]
            if stack[-1] not in _CODE or 'arith' in stack:
                continue
            word = m.group(2) or m.group(3) or m.group(5)
            literal = not m.group(5) or bool(m.group(4))
            nested = 'subst' in stack or 'backtick' in stack
            span = (start + m.start(), start + m.end())
            fresh.append(_Heredoc(word, m.group(1) == '-', literal, nested, span))
        out.append(line)
        if ctx.continues():
            continue
        for doc in fresh:
            doc.executed = _feeds_a_shell(logical[: doc.span[0]], logical[doc.span[1] :])
        pending.extend(fresh)
        logical, fresh = '', []
        body_open = bool(pending)
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

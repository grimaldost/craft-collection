#!/usr/bin/env python3
"""PreToolUse hook: steer Bash toward uv inside uv-managed projects.

Blocks `pip install`, `poetry add/install`, `virtualenv`, and `python -m venv`
when the cwd is a uv project (uv.lock, or [tool.uv]/uv_build in pyproject.toml),
unless CLAUDE_ALLOW_PIP=1. Exits 2 (blocking, stderr fed to Claude) on a block;
otherwise 0. Never fires outside a uv project. Stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

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


def _strip_noncommand(command: str) -> str:
    """Blank out quoted spans and `#`-comments so only real command text remains."""
    return _QUOTED_OR_COMMENT.sub(' ', command)


def cwd_is_uv_project(cwd: str | None) -> bool:
    d = Path(cwd) if cwd else Path.cwd()
    if (d / 'uv.lock').is_file():
        return True
    pyproject = d / 'pyproject.toml'
    if pyproject.is_file():
        text = pyproject.read_text(encoding='utf-8', errors='ignore')
        return '[tool.uv]' in text or 'uv_build' in text
    return False


def verdict(command: str, cwd_has_uv: bool, allow_env: bool) -> str:
    """Return 'block' or 'allow' for a Bash command."""
    if allow_env or not cwd_has_uv:
        return 'allow'
    scannable = _strip_noncommand(command or '')
    return 'block' if _BLOCKED.search(scannable) else 'allow'


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = (payload.get('tool_input') or {}).get('command', '')
    allow = os.environ.get('CLAUDE_ALLOW_PIP') == '1'
    if verdict(command, cwd_is_uv_project(payload.get('cwd')), allow) == 'block':
        print(
            'This is a uv-managed project. Use `uv add <pkg>` for dependencies '
            'or `uv venv` / `uv sync` for environments, instead of '
            'pip/poetry/virtualenv. Set CLAUDE_ALLOW_PIP=1 to override.',
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

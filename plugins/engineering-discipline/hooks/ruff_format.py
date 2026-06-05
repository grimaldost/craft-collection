#!/usr/bin/env python3
"""PostToolUse hook: format and autofix a Python file after Claude edits it.

Reads the PostToolUse payload on stdin; if the edited file is a `.py`, runs
`uvx ruff format` then `uvx ruff check --fix`. ALWAYS exits 0 — formatting is
mechanical and must never block the session. Stdlib-only; shells out to uv.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def target_file(payload: dict) -> str | None:
    """Return the edited `.py` file path from a PostToolUse payload, or None."""
    tool_input = payload.get('tool_input') or {}
    fp = tool_input.get('file_path') or tool_input.get('path')
    if fp and str(fp).endswith('.py'):
        return str(fp)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    f = target_file(payload)
    if not f or not Path(f).is_file():
        return 0
    for args in (['uvx', 'ruff', 'format', f], ['uvx', 'ruff', 'check', '--fix', f]):
        try:
            subprocess.run(args, capture_output=True, check=False)  # noqa: S603
        except FileNotFoundError:
            # uv/uvx not on PATH — formatting is best-effort, never fatal.
            print('ruff_format hook: uv not found; skipping', file=sys.stderr)
            return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())

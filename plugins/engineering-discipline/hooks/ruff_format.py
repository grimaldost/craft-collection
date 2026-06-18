#!/usr/bin/env python3
"""PostToolUse hook: format a Python file after Claude edits it.

Reads the PostToolUse payload on stdin; if the edited file is a `.py`, runs
`uvx ruff format` on it. ALWAYS exits 0 — formatting is mechanical and must
never block the session. Stdlib-only; shells out to uv.

Deliberately format-only: the import-removing autofix (`ruff check --fix`) is
NOT run per-edit — see `ruff_commands`. Per-edit automation must be idempotent
and non-destructive; `--fix` is owned by the pre-commit/CI gate, where the file
is complete.
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


def ruff_commands(file_path: str) -> list[list[str]]:
    """The ruff invocations the hook runs on `file_path`, in order — format only.

    `ruff check --fix` is deliberately excluded: F401 ("imported but unused") is a
    false positive on a file mid-edit-sequence (an import added in one edit and
    used in a later one looks unused in between), so a per-edit `--fix` strips it
    and breaks the next edit. Per-edit automation must be idempotent and
    non-destructive; `--fix` is owned by the pre-commit/CI gate, where the file is
    complete. Do NOT add a `check --fix` command here (the test guards it).
    """
    return [['uvx', 'ruff', 'format', file_path]]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    f = target_file(payload)
    if not f or not Path(f).is_file():
        return 0
    for args in ruff_commands(f):
        try:
            subprocess.run(args, capture_output=True, check=False)  # noqa: S603
        except FileNotFoundError:
            # uv/uvx not on PATH — formatting is best-effort, never fatal.
            print('ruff_format hook: uv not found; skipping', file=sys.stderr)
            return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())

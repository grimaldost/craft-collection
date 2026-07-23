#!/usr/bin/env python3
"""PostToolBatch hook: format the Python files edited in an assistant turn.

Reads the PostToolBatch payload on stdin (one `tool_calls` list per turn,
firing once after all of the turn's per-call PostToolUse hooks) and runs a
SINGLE `uvx ruff format` invocation across every `.py` file that a `Write` or
`Edit` call in that turn touched. This replaces the old per-call PostToolUse
registration deliberately: formatting between two batched edits invalidates
the later edit's `old_string` match (the strip-between-batched-edits race).
Batching the format to the end of the turn removes the race outright.

The legacy single-payload shape (a top-level `tool_input`, as produced by a
manual invocation or an older PostToolUse registration) is still accepted
unchanged, so this script keeps working if re-registered on PostToolUse.

ALWAYS exits 0 — formatting is mechanical and must never block the session.
Stdlib-only; shells out to uv.

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
    """Return the edited `.py` file path from a PostToolUse-shaped payload, or None.

    Also used per-element against each `tool_calls[i]` entry in a PostToolBatch
    payload, since each entry carries its own `tool_input` the same way.
    """
    tool_input = payload.get('tool_input') or {}
    fp = tool_input.get('file_path') or tool_input.get('path')
    if fp and str(fp).endswith('.py'):
        return str(fp)
    return None


def batch_files(payload: dict) -> list[str]:
    """Deduped `.py` file paths (first-seen order) from a PostToolBatch payload.

    Only `Write`/`Edit` entries in `tool_calls` are considered; non-`.py` paths
    are dropped by `target_file`. Does not touch the filesystem — see
    `existing_files` for the existence filter.
    """
    tool_calls = payload.get('tool_calls')
    if not isinstance(tool_calls, list):
        # A non-list `tool_calls` (contract violation or payload drift) means
        # nothing to format — never a traceback; the hook always exits 0.
        return []
    seen: list[str] = []
    for call in tool_calls:
        if not isinstance(call, dict) or call.get('tool_name') not in ('Write', 'Edit'):
            continue
        f = target_file(call)
        if f and f not in seen:
            seen.append(f)
    return seen


def existing_files(paths: list[str]) -> list[str]:
    """Filter `paths` down to those that exist on disk, order preserved."""
    return [p for p in paths if Path(p).is_file()]


def batch_command(paths: list[str]) -> list[list[str]]:
    """The single `uvx ruff format p1 p2 ...` invocation for `paths`.

    Returns `[]` (no command) when `paths` is empty — an empty surviving set
    means no subprocess call. Format-only, same doctrine as `ruff_commands`.
    """
    if not paths:
        return []
    return [['uvx', 'ruff', 'format', *paths]]


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
    if not isinstance(payload, dict):
        return 0

    if 'tool_calls' in payload:
        commands = batch_command(existing_files(batch_files(payload)))
    else:
        f = target_file(payload)
        commands = ruff_commands(f) if f and Path(f).is_file() else []

    for args in commands:
        try:
            subprocess.run(args, capture_output=True, check=False)  # noqa: S603
        except FileNotFoundError:
            # uv/uvx not on PATH — formatting is best-effort, never fatal.
            print('ruff_format hook: uv not found; skipping', file=sys.stderr)
            return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())

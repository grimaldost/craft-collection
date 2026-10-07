#!/usr/bin/env python3
"""PostToolBatch hook: format the Python files edited in an assistant turn.

Reads the PostToolBatch payload on stdin (one `tool_calls` list per turn,
firing once after all of the turn's per-call PostToolUse hooks) and runs a
SINGLE `uvx ruff format` invocation across every `.py` file that a `Write` or
`Edit` call in that turn touched, in a project that declares ruff. This
replaces the old per-call PostToolUse registration deliberately: formatting
between two batched edits invalidates the later edit's `old_string` match (the
strip-between-batched-edits race). Batching the format to the end of the turn
removes the race outright.

Scope: a file is formatted only when its project declares ruff (`declares_ruff`:
a `ruff.toml`, a `.ruff.toml`, or a `[tool.ruff]` table in a `pyproject.toml`,
found walking up from the file to the repository root). A file outside any
project, or in a repository that never asked for ruff, keeps its bytes: another
project's formatting, or a frozen file whose sha is recorded, is not ours to
rewrite.

The legacy single-payload shape (a top-level `tool_input`, as produced by a
manual invocation or an older PostToolUse registration) is still accepted,
with the same scope, so this script keeps working if re-registered on PostToolUse.

ALWAYS exits 0 — formatting is mechanical and must never block the session.
Stdlib-only; shells out to uv.

Deliberately format-only: the import-removing autofix (`ruff check --fix`) is
NOT run per-edit — see `ruff_commands`. Per-edit automation must be idempotent
and non-destructive; `--fix` is owned by the pre-commit/CI gate, where the file
is complete.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

RUFF_CONFIG_FILES = ('ruff.toml', '.ruff.toml')
# A `[tool.ruff]` or `[tool.ruff.<sub>]` table header at the start of a line.
# A line regex rather than tomllib: the hook's interpreter is not pinned (tomllib
# is 3.11+), and a malformed pyproject.toml must never raise here.
_RUFF_TABLE = re.compile(r'^[ \t]*\[[ \t]*tool[ \t]*\.[ \t]*ruff[ \t]*[\].]', re.MULTILINE)


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


def declares_ruff(path: str, stop_at: str | None = None) -> bool:
    """True when the project holding `path` declares ruff.

    Walks up from the file's directory. A directory declares ruff when it holds a
    `ruff.toml` or `.ruff.toml`, or a `pyproject.toml` with a `[tool.ruff]` or
    `[tool.ruff.*]` table. A `pyproject.toml` without one does not stop the walk,
    as in ruff's own discovery, so a monorepo subpackage under a root `ruff.toml`
    still counts. The walk ends, False, after checking a directory that holds
    `.git` (a directory in a clone, a file in a worktree or submodule: the
    repository boundary), at the filesystem root, or at `stop_at` (for tests).

    Never raises: any OSError or ValueError (an unreadable file, a path the OS
    cannot represent) means False, with nothing printed, so the hook's
    always-exit-0 contract holds.
    """
    try:
        here = Path(path).resolve().parent
        stop = Path(stop_at).resolve() if stop_at is not None else None
        for d in (here, *here.parents):
            if any((d / name).is_file() for name in RUFF_CONFIG_FILES):
                return True
            pyproject = d / 'pyproject.toml'
            if pyproject.is_file():
                text = pyproject.read_text(encoding='utf-8-sig', errors='ignore')
                if _RUFF_TABLE.search(text):
                    return True
            if (d / '.git').exists() or d == stop:
                return False
    except (OSError, ValueError):
        return False
    return False


def declared_ruff_files(paths: list[str], stop_at: str | None = None) -> list[str]:
    """Filter `paths` down to those whose project declares ruff, order preserved."""
    return [p for p in paths if declares_ruff(p, stop_at)]


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


def main(stop_at: str | None = None) -> int:
    """Hook entry point. `stop_at` bounds the config walk (tests only)."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    if 'tool_calls' in payload:
        commands = batch_command(declared_ruff_files(existing_files(batch_files(payload)), stop_at))
    else:
        f = target_file(payload)
        in_scope = f and Path(f).is_file() and declares_ruff(f, stop_at)
        commands = ruff_commands(f) if in_scope else []

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

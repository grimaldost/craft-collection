#!/usr/bin/env python3
"""Harness adapters: the seam between hook cores and hook envelopes (ADR-0003).

The decision logic lives (and stays) in the hook modules — `target_file` and
`ruff_commands` in `ruff_format.py`, `verdict` and `cwd_is_uv_project` in
`uv_enforce.py`, `_load_payload` in `stop_nudge.py`. This module wraps those
functions behind harness-agnostic entry points, so a harness other than Claude
Code can reuse the tested semantics by writing one thin adapter: a function
from that harness's event payload to the core call, plus a mapping from the
core verdict to that harness's blocking convention.

An adapter translates payloads ONLY (the adapter-thinness invariant,
ADR-0003) — any logic change lands in the hook modules, where the tests are.
The Claude Code envelope stays in each hook's `main()`; this module does not
alter CC behavior. Enforcement degrades down the documented ladder: act-time
block (a hook-capable harness, via these adapters) -> commit-time block (the
pre-commit floor in `adapters/pre-commit/`) -> advisory (the generated
AGENTS.md). Stdlib-only.

Worked example (a harness whose edit event carries `{"file": ...}`):

    from harness_adapters import format_decision
    cmds = format_decision(payload.get('file'))   # [] or the ruff invocations
"""

from __future__ import annotations

import io

import ruff_format
import stop_nudge
import uv_enforce

# ---------------------------------------------------------------------------
# Harness-agnostic core entry points (plain arguments, no envelope assumptions)
# ---------------------------------------------------------------------------


def format_decision(file_path: str | None) -> list[list[str]]:
    """Commands to run after an edit to `file_path` ([] when none apply).

    Non-blocking by contract: run them best-effort and never fail the edit.
    """
    if not file_path or not str(file_path).endswith('.py'):
        return []
    return ruff_format.ruff_commands(str(file_path))


def bash_verdict(command: str, cwd: str | None = None, *, allow_override: bool = False) -> str:
    """'block' or 'allow' for a shell command about to run in `cwd`.

    A blocking harness maps 'block' to its own convention (CC: exit 2 with the
    guidance on stderr); a non-blocking harness may surface the message
    advisory-style instead.
    """
    return uv_enforce.verdict(command, uv_enforce.cwd_is_uv_project(cwd), allow_override)


def block_message() -> str:
    """The guidance a 'block' verdict should surface, harness-neutral."""
    return (
        'This is a uv-managed project. Use `uv add <pkg>` for dependencies '
        'or `uv venv` / `uv sync` for environments, instead of pip/poetry/virtualenv.'
    )


def parse_json_payload(raw: str) -> dict:
    """Parse a raw event body into a dict ({} on empty/malformed) — wraps the
    tolerant reader the Stop hook already tests."""
    return stop_nudge._load_payload(io.StringIO(raw))


# ---------------------------------------------------------------------------
# Per-harness payload adapters (translation only — keep these thin)
# ---------------------------------------------------------------------------


def claude_code_edited_file(payload: dict) -> str | None:
    """Claude Code PostToolUse payload -> the edited .py path (or None)."""
    return ruff_format.target_file(payload)


def claude_code_bash_command(payload: dict) -> str:
    """Claude Code PreToolUse payload -> the Bash command string."""
    return (payload.get('tool_input') or {}).get('command', '')

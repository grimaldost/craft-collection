#!/usr/bin/env python3
"""Feedback-debt Stop nudge, founded on the session transcript.

    python feedback_nudge.py --stop-nudge     # Stop: at most one nudge per session

It ships ON; `SESSION_WORKFLOW_FEEDBACK_NUDGE=0` is the documented opt-out. What
makes default-on safe is the binding check: the nudge stays silent unless a
feedback-targets file resolves, so an install with no registered tools never sees
it. Registered targets come from `$FEEDBACK_TARGETS_FILE`, else
`~/.claude/feedback-targets.toml` -- the same file the tool-feedback skill reads.

It fires when all of these hold, and then only once per session:
  - a feedback-targets file exists (there is somewhere to report to);
  - the transcript shows a `Skill` or plugin-MCP tool call;
  - none of those calls was `tool-feedback` (invoking it is what clears the debt);
  - the session has at least SESSION_WORKFLOW_NUDGE_MIN_TURNS (default 8) real
    human turns.

The transcript is the native record and the single input. A PostToolUse hook used
to append one JSONL entry per skill call so this nudge had something to read; that
was a second write path for a fact the transcript already carried, and it is gone
-- one fewer hook, one fewer state directory. A report written WITHOUT the skill
is still not detected (accepted imprecision, unchanged).

House rules: stdlib only; ASCII-only runtime output (json.dumps escapes non-ASCII);
every failure path exits 0; the block is printed before the marker persists so a
delivery failure never burns the once-per-session slot.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

NUDGE_GATE = 'SESSION_WORKFLOW_FEEDBACK_NUDGE'
MIN_TURNS_ENV = 'SESSION_WORKFLOW_NUDGE_MIN_TURNS'
STATE_DIR_ENV = 'SESSION_WORKFLOW_NUDGE_STATE_DIR'
TARGETS_FILE_ENV = 'FEEDBACK_TARGETS_FILE'
DEFAULT_TARGETS_FILE = Path.home() / '.claude' / 'feedback-targets.toml'
DEFAULT_MIN_TURNS = 8
# A tool call that counts as exercising a plugin tool: the Skill tool, or any
# plugin-provided MCP tool.
TOOL_PATTERN = re.compile(r'^Skill$|^mcp__plugin_.*')
# Subagent-completion prompts pass through as user records (verified 2026-07-23);
# they are not human turns and must not count toward the nudge gate.
SYNTHETIC_PREFIXES = ('[SYSTEM NOTIFICATION', '<task-notification>')
DEBT_CLEARING_MARK = 'tool-feedback'


def _load_stdin_json() -> dict:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8-sig', errors='replace')
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'feedback-nudge'


def targets_file() -> Path | None:
    """The registered feedback-targets file, or None when none resolves. The
    binding check that makes a default-on nudge safe: with nowhere to report to,
    the nudge has nothing to ask for."""
    override = os.environ.get(TARGETS_FILE_ENV)
    candidate = Path(override) if override else DEFAULT_TARGETS_FILE
    try:
        return candidate if candidate.is_file() else None
    except OSError:
        return None


def _safe_session(session_id: object) -> str:
    sid = session_id if isinstance(session_id, str) and session_id else 'unknown'
    safe = ''.join(c for c in sid if c.isalnum() or c in '-_') or 'unknown'
    return safe[:64]


def _user_text(msg: dict) -> str | None:
    """Human prompt text of a `user` transcript record; None when there is none.
    Most type=="user" records in a real transcript are TOOL RESULTS (content
    blocks with no `type: "text"` entry) -- they must yield None so the turn gate
    counts humans, not tool calls (~64 of 71 user records in the reviewed
    sample were tool results)."""
    content = msg.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get('type') == 'text'
                and isinstance(block.get('text'), str)
            ):
                return block['text']
    return None


def _tool_names(msg: dict) -> list[str]:
    """Plugin tools invoked in one assistant record. A `Skill` call reports the
    skill it named (`input.skill`); a plugin-MCP call reports the tool name."""
    content = msg.get('content')
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get('type') != 'tool_use':
            continue
        name = block.get('name')
        if not isinstance(name, str) or not TOOL_PATTERN.search(name):
            continue
        if name == 'Skill':
            skill = (block.get('input') or {}).get('skill')
            out.append(skill[:200] if isinstance(skill, str) and skill else name)
        else:
            out.append(name[:200])
    return out


def read_transcript(transcript_path: object) -> tuple[int, list[str]]:
    """One pass over the transcript -> (human turns, plugin tools exercised in
    order, deduplicated). Any error yields (0, []), which HOLDS the nudge:
    fail-silent, never fail-noisy."""
    turns = 0
    skills: list[str] = []
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0, []
    try:
        p = Path(transcript_path)
        if not p.is_file():
            return 0, []
        for line in p.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict):
                continue
            msg = rec.get('message')
            if not isinstance(msg, dict):
                continue
            kind = rec.get('type')
            if kind == 'user':
                text = _user_text(msg)
                if text is not None and not text.lstrip().startswith(SYNTHETIC_PREFIXES):
                    turns += 1
            elif kind == 'assistant':
                for name in _tool_names(msg):
                    if name not in skills:
                        skills.append(name)
    except Exception:
        return 0, []
    return turns, skills


def _min_turns() -> int:
    try:
        v = int(os.environ.get(MIN_TURNS_ENV, ''))
    except (TypeError, ValueError):
        return DEFAULT_MIN_TURNS
    return v if v >= 1 else DEFAULT_MIN_TURNS


def nudge_reason(skills: list[str]) -> str:
    shown = ', '.join(skills[:3]) + (' and more' if len(skills) > 3 else '')
    return (
        f'feedback debt: this session exercised plugin tools ({shown}) and no '
        'tool-feedback invocation is on record. Apply the tool-feedback skill '
        'now (write directly under a standing directive; otherwise emit its '
        'one-line offer), or finish if nothing is worth recording. This nudge '
        'fires once per session.'
    )


def _stop_nudge() -> int:
    if os.environ.get(NUDGE_GATE) == '0':
        return 0
    if targets_file() is None:
        return 0  # no registered tools: nothing to report to, so nothing to ask
    payload = _load_stdin_json()
    if payload.get('stop_hook_active'):
        return 0
    safe = _safe_session(payload.get('session_id'))
    marker = _state_dir() / f'{safe}.nudged'
    with contextlib.suppress(Exception):
        if marker.exists():
            return 0
    turns, skills = read_transcript(payload.get('transcript_path'))
    if not skills:
        return 0
    if any(DEBT_CLEARING_MARK in s for s in skills):
        return 0
    if turns < _min_turns():
        return 0
    print(json.dumps({'decision': 'block', 'reason': nudge_reason(skills)}))
    with contextlib.suppress(Exception):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('1', encoding='utf-8')
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if '--stop-nudge' in argv:
            return _stop_nudge()
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

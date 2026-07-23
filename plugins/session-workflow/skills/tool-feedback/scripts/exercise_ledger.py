#!/usr/bin/env python3
"""Skill-exercise ledger + feedback-debt Stop nudge. Both modes inert by default.

    python exercise_ledger.py --record       # PostToolUse (async): append one entry
    python exercise_ledger.py --stop-nudge   # Stop: at most one nudge per session

--record (gate: SESSION_WORKFLOW_EXERCISE_LEDGER=1) appends {ts, tool, skill,
prompt_id} to <data>/exercise-ledger/<session_id>.jsonl for every Skill or
plugin-MCP tool call -- the substrate for real-session activation telemetry
and the evidence the Stop nudge reads. Registered async: verified (2.1.218)
that async hooks still receive the full stdin payload.

--stop-nudge (gate: SESSION_WORKFLOW_FEEDBACK_NUDGE=1) mechanizes the standing
tool-feedback default: when the ledger shows plugin tools were exercised, no
tool-feedback invocation is on record, and the session has at least
SESSION_WORKFLOW_NUDGE_MIN_TURNS (default 8) real user turns, it emits a
Stop block whose reason asks the model to apply the tool-feedback skill (or
finish if nothing is worth recording). `stop_hook_active` exits early so a
block never compounds; a marker file caps the nudge at once per session.
Invoking the tool-feedback skill is what clears the debt -- a report written
without the skill is not detected (accepted imprecision, documented here).

House rules: stdlib only; ASCII-only runtime output (json.dumps escapes
non-ASCII); every failure path exits 0; the block is printed before the
marker persists so a delivery failure never burns the once-per-session slot.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

LEDGER_GATE = 'SESSION_WORKFLOW_EXERCISE_LEDGER'
NUDGE_GATE = 'SESSION_WORKFLOW_FEEDBACK_NUDGE'
MIN_TURNS_ENV = 'SESSION_WORKFLOW_NUDGE_MIN_TURNS'
LEDGER_DIR_ENV = 'SESSION_WORKFLOW_LEDGER_DIR'
DEFAULT_MIN_TURNS = 8
# Mirrors the hooks.json PostToolUse matcher, for manual/matcher-less runs.
TOOL_PATTERN = re.compile(r'^Skill$|^mcp__plugin_.*')
# Subagent-completion prompts pass through as user records (verified 2026-07-23);
# they are not human turns and must not count toward the nudge gate.
SYNTHETIC_PREFIXES = ('[SYSTEM NOTIFICATION', '<task-notification>')
DEBT_CLEARING_MARK = 'tool-feedback'


def _gate_on(name: str) -> bool:
    return os.environ.get(name, '') == '1'


def _load_stdin_json() -> dict:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8-sig', errors='replace')
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _ledger_dir() -> Path:
    override = os.environ.get(LEDGER_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'exercise-ledger'


def _safe_session(session_id: object) -> str:
    sid = session_id if isinstance(session_id, str) and session_id else 'unknown'
    safe = ''.join(c for c in sid if c.isalnum() or c in '-_') or 'unknown'
    return safe[:64]


def _record() -> int:
    if not _gate_on(LEDGER_GATE):
        return 0
    payload = _load_stdin_json()
    tool = payload.get('tool_name')
    if not isinstance(tool, str) or not TOOL_PATTERN.search(tool):
        return 0
    tool_input = payload.get('tool_input')
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    skill = tool_input.get('skill') if tool == 'Skill' else tool
    skill = skill if isinstance(skill, str) and skill else tool
    entry: dict = {'ts': round(time.time()), 'tool': tool, 'skill': skill[:200]}
    prompt_id = payload.get('prompt_id')
    if isinstance(prompt_id, str):
        entry['prompt_id'] = prompt_id[:64]
    path = _ledger_dir() / f'{_safe_session(payload.get("session_id"))}.jsonl'
    with contextlib.suppress(Exception):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry) + '\n')
    return 0


def _read_entries(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _user_text(rec: dict) -> str | None:
    """Human prompt text of a `user` transcript record; None when there is
    none. Most type=="user" records in a real transcript are TOOL RESULTS
    (content blocks with no `type: "text"` entry) -- they must yield None so
    the turn gate counts humans, not tool calls (~64 of 71 user records in
    the reviewed sample were tool results)."""
    msg = rec.get('message')
    if not isinstance(msg, dict):
        return None
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


def _count_user_turns(transcript_path: object) -> int:
    """`type == "user"` records that carry real human text -- textless records
    (tool results) and synthetic notifications do not count. Any error -> 0,
    which HOLDS the nudge (fail-silent, never fail-noisy)."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0
    try:
        p = Path(transcript_path)
        if not p.is_file():
            return 0
        n = 0
        for line in p.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict) or rec.get('type') != 'user':
                continue
            text = _user_text(rec)
            if text is None or text.lstrip().startswith(SYNTHETIC_PREFIXES):
                continue
            n += 1
        return n
    except Exception:
        return 0


def _min_turns() -> int:
    try:
        v = int(os.environ.get(MIN_TURNS_ENV, ''))
    except (TypeError, ValueError):
        return DEFAULT_MIN_TURNS
    return v if v >= 1 else DEFAULT_MIN_TURNS


def _stop_nudge() -> int:
    if not _gate_on(NUDGE_GATE):
        return 0
    payload = _load_stdin_json()
    if payload.get('stop_hook_active'):
        return 0
    safe = _safe_session(payload.get('session_id'))
    ledger = _ledger_dir() / f'{safe}.jsonl'
    marker = _ledger_dir() / f'{safe}.nudged'
    with contextlib.suppress(Exception):
        if marker.exists():
            return 0
    entries = _read_entries(ledger)
    if not entries:
        return 0
    skills = [e.get('skill') for e in entries if isinstance(e.get('skill'), str)]
    if not skills:
        return 0
    if any(DEBT_CLEARING_MARK in s for s in skills):
        return 0
    if _count_user_turns(payload.get('transcript_path')) < _min_turns():
        return 0
    names: list[str] = []
    for s in skills:
        if s not in names:
            names.append(s)
    shown = ', '.join(names[:3]) + (' and more' if len(names) > 3 else '')
    text = (
        f'feedback debt: this session exercised plugin tools ({shown}) and no '
        'tool-feedback invocation is on record. Apply the tool-feedback skill '
        'now (write directly under a standing directive; otherwise emit its '
        'one-line offer), or finish if nothing is worth recording. This nudge '
        'fires once per session.'
    )
    print(json.dumps({'decision': 'block', 'reason': text}))
    with contextlib.suppress(Exception):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('1', encoding='utf-8')
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if '--record' in argv:
            return _record()
        if '--stop-nudge' in argv:
            return _stop_nudge()
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

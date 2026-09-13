#!/usr/bin/env python3
"""PreToolUse hook: name the routing decision at the moment a spawn takes it.

`choosing-models` governs one moment - the moment a (model, effort) pair is
chosen for someone else's run - and had no trigger there. Measured: ZERO
invocations across a 40-hour, 139-subagent programme, against a written owner
order transcribed verbatim three times and repeated in the anchor's every cursor
block, with 65% of output and 81% of uncached input left at the top tier. Twenty
subagents at the frontier tier in one day ($14.48, ten of them mechanical
rewriters); 23 more the next, killed by the owner mid-run. Prose has now failed
against the strongest instruction channel there is, so this is the rung below it.

It scales with a fan-out, which is the reason it is a hook and not a sentence: a
54-item batch is reminded ONCE, at the script, instead of once per agent or not
at all.

  --pre-tool-use   Matched on the spawn surface (`Agent`; `Workflow` where the
                   harness has one). Injects a short advisory block naming the
                   activation test and the batch counter-rule. Ships ON;
                   HUMBLEPOWERS_SPAWN_ROUTING_HINT=0 is the opt-out.

Three silences keep it from becoming the noise that gets hooks switched off:

  - a spawn that already carries `model` has been routed. The field is present
    in `tool_input` only when the caller passed one, so its presence IS the
    evidence that a decision was taken rather than inherited;
  - at most one hint per session per HINT_COOLDOWN_S;
  - anything that is not a spawn surface.

It is ADVISORY: the payload is `additionalContext` with no `permissionDecision`,
which is the documented way to add context from PreToolUse without voting on the
allow/deny outcome. `allow` would skip a permission prompt the operator
configured, and `deny` would block real work over a reminder; neither is this
hook's business. One consequence to know: context added during a turn reaches the
model's NEXT turn, so the hint does not stop the spawn that triggered it - it
stands in front of the rest of the batch and the rest of the run, which is where
the measured loss actually accumulated.

The block names the activation test and points at the skill; it does NOT restate
the tier thresholds. `models.toml` owns those, and a second copy inside a hook is
exactly the drift this corpus already pays for elsewhere.

Contract, inherited from `choosing-tools/scripts/inject_dispatch.py`: stdlib
only, no subprocesses, no network, ASCII-only output (hook stdout encoding
follows the host console), and every path returns 0 - a PreToolUse hook that
errors or hangs costs the tool call it was meant to annotate.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

GATE = 'HUMBLEPOWERS_SPAWN_ROUTING_HINT'
STATE_DIR_ENV = 'HUMBLEPOWERS_SPAWN_HINT_STATE_DIR'
STATE_NAME = 'spawn-hint.json'
# Tool names that spawn someone else's run. `Agent` is the spawner (renamed from
# `Task` in CC 2.1.63; the TaskCreate/TaskGet family is the separate todo system
# and must never match here). `Workflow` is carried because the skill's emission
# surfaces name `workflow agent()` as a routed surface; where no such tool
# exists the entry simply never matches.
SPAWN_TOOLS = ('Agent', 'Workflow')
HINT_COOLDOWN_S = 600  # one reminder per session per 10 minutes
MAX_TRACKED_SESSIONS = 50  # the state file is a cooldown, not a history

HINT = (
    'This spawn names no model, so the agent inherits this session tier: a '
    "(model, effort) pair is being set for someone else's run by default "
    'rather than by decision.\n'
    'Activation test: is a (model, effort) pair about to be chosen for someone '
    "else's run? If yes, score it with the humblepowers:choosing-models rubric "
    'and pass an explicit model - that skill and its models.toml own the '
    'thresholds, which this hook deliberately does not restate.\n'
    'Two or more agents dispatched in one decision are a batch, and the '
    'single-task exception does not apply to a batch.\n'
    f'(Once per session per {HINT_COOLDOWN_S // 60} min; {GATE}=0 silences it.)'
)


def _ascii(text: str) -> str:
    """Collapse to ASCII for output; hook stdout may be a codepage-limited console."""
    return text.encode('ascii', 'replace').decode('ascii')


def _state_path() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    base = override or os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / ('' if override else 'humblepowers-spawn-routing') / STATE_NAME


def is_spawn(tool_name: str) -> bool:
    return tool_name in SPAWN_TOOLS


def needs_hint(tool_name: str, tool_input: dict) -> bool:
    """True when this call is a spawn that has NOT been routed. `model` absent
    means the subagent's model is resolved later from its frontmatter, an env
    var, or the parent conversation - none of which is a decision taken here."""
    return is_spawn(tool_name) and not tool_input.get('model')


def due(last_ts: float, now: float, cooldown_s: int = HINT_COOLDOWN_S) -> bool:
    """Whether the cooldown has elapsed. Pure, so the window is testable without
    sleeping through it."""
    return now - last_ts >= cooldown_s


def _read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, state: dict) -> None:
    # Best-effort by contract: an unwritable state dir must cost the reminder
    # nothing. It fails toward reminding again, never toward silence.
    with contextlib.suppress(Exception):
        if len(state) > MAX_TRACKED_SESSIONS:
            newest = sorted(state.items(), key=lambda kv: kv[1], reverse=True)
            state = dict(newest[:MAX_TRACKED_SESSIONS])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding='utf-8')


def _pre_tool_use() -> int:
    if os.environ.get(GATE) == '0':
        return 0
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8-sig'))
    except (ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get('tool_name')
    tool_name = tool_name if isinstance(tool_name, str) else ''
    tool_input = payload.get('tool_input')
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if not needs_hint(tool_name, tool_input):
        return 0

    session = payload.get('session_id')
    session = session if isinstance(session, str) and session else 'unknown'
    path = _state_path()
    state = _read_state(path)
    last = state.get(session)
    now = time.time()
    if isinstance(last, (int, float)) and not due(float(last), now):
        return 0

    # Emit FIRST - the injection is the hook's entire purpose - then record.
    print(
        json.dumps(
            {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'additionalContext': _ascii(HINT),
                }
            }
        )
    )
    state[session] = now
    _write_state(path, state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Spawn-time model-routing hint (PreToolUse).')
    parser.add_argument('--pre-tool-use', action='store_true', help='PreToolUse entry point')
    args = parser.parse_args(argv)
    try:
        if args.pre_tool_use:
            return _pre_tool_use()
        parser.print_help()
        return 0
    except Exception:
        return 0  # fail open: a hook error must never cost the tool call


if __name__ == '__main__':
    sys.exit(main())

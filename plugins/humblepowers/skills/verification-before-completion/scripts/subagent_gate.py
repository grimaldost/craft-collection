#!/usr/bin/env python3
"""Opt-in SubagentStop gate for verification-before-completion.

The skill ships as prose in a suite whose own measured pattern is that gates
beat reminders. This is the gate: it blocks a subagent's first stop once and
hands back a discipline reconsideration, then gets out of the way.

Wording. `RECONSIDER` is the `subagent-generic-gate` arm verbatim. That matters
more than it looks: a prescriptively-worded sibling, measured on the same bank,
demanded a test on trivial edits often enough to be rejected, while this
wording names no artifact and stayed clean. The words are the treatment, so
`test_subagent_gate.py` pins them byte-for-byte.

Arming. Silent unless `HUMBLEPOWERS_VERIFICATION_SUBAGENT_GATE=1`. A
stop-blocking hook on every subagent in someone's environment is a larger bet
than one bank of evidence funds, so the default is off and stays off until a
replication on a second task family says otherwise.

Environment:
  HUMBLEPOWERS_VERIFICATION_SUBAGENT_GATE=1   arm the gate (default: off)
  HUMBLEPOWERS_VERIFICATION_GATE_STATE_DIR    where the one-shot counters live
                                              (default: a temp subdirectory)
  HUMBLEPOWERS_VERIFICATION_GATE_SKIP_MODELS  PROVISIONAL, see below

PROVISIONAL — the tier predicate. `..._SKIP_MODELS` takes comma-separated
substrings matched against the model named in the stop payload; a match no-ops
the gate. It exists because a tier fact, if one is ever measured, is
implementable here and nowhere else — the harness cannot condition a skill's
activation on a subagent's model, so the same claim written into a description
would be a sentence nothing can act on. Two things are true of it today and
both are load-bearing: no measurement licenses any particular value, so it is
inert unless an operator sets it; and the payload key it reads is unconfirmed,
so an absent model gates rather than skips. Unset it and this file behaves
exactly like the fixture that was measured.

Stdlib only. Fails open on anything unexpected: a hook that cannot decide must
never be the reason a subagent cannot stop.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

RECONSIDER = (
    'Before you finish: are you actually confident this is correct, or are you '
    'assuming it is? Take one more pass over what you changed and satisfy yourself '
    'that it genuinely works and that you would find out if it stopped working.'
)

ARM_VAR = 'HUMBLEPOWERS_VERIFICATION_SUBAGENT_GATE'
STATE_VAR = 'HUMBLEPOWERS_VERIFICATION_GATE_STATE_DIR'
SKIP_MODELS_VAR = 'HUMBLEPOWERS_VERIFICATION_GATE_SKIP_MODELS'

DEFAULT_STATE_DIRNAME = 'humblepowers-verification-gate'
MARKER_TTL_S = 24 * 60 * 60
UNSAFE = re.compile(r'[^A-Za-z0-9_-]+')


def is_armed(env: dict[str, str]) -> bool:
    return env.get(ARM_VAR, '').strip() == '1'


def token(value: object, fallback: str) -> str:
    """A payload field reduced to a filename-safe token. The session and agent
    ids come from outside this process; they name a file, so they are filtered
    rather than trusted. Pure."""
    text = UNSAFE.sub('-', str(value or '')).strip('-')
    return text[:64] or fallback


def model_of(payload: dict) -> str:
    """The model named in the stop payload, '' when it names none. The key is
    unconfirmed across harness versions, so several plausible spellings are
    read; none of them existing is a real and expected outcome. Pure."""
    for key in ('model', 'model_id', 'modelId'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    nested = payload.get('agent')
    if isinstance(nested, dict):
        return model_of(nested)
    return ''


def skipped_by_tier(payload: dict, env: dict[str, str]) -> bool:
    """PROVISIONAL. True only when an operator configured skip substrings AND the
    payload names a matching model. An unconfigured predicate never skips, and a
    payload with no model never skips — a silent no-op would otherwise read as a
    clean false-positive rate the gate never earned. Pure."""
    raw = env.get(SKIP_MODELS_VAR, '')
    needles = [n.strip().lower() for n in raw.split(',') if n.strip()]
    if not needles:
        return False
    model = model_of(payload)
    return bool(model) and any(n in model for n in needles)


def state_dir(env: dict[str, str]) -> Path:
    configured = env.get(STATE_VAR, '').strip()
    return Path(configured) if configured else Path(tempfile.gettempdir()) / DEFAULT_STATE_DIRNAME


def prune(directory: Path, now: float, ttl_s: int = MARKER_TTL_S) -> None:
    """Best-effort removal of counters past their retention window. The one
    deliberate divergence from the measured fixture, which left every counter
    behind forever: an opt-in hook should not accumulate files in a user's temp
    dir for the life of the machine. A pruned counter can at worst cost one
    extra block to a subagent that stopped a day ago, which does not happen."""
    for marker in directory.glob('*.txt'):
        try:
            if now - marker.stat().st_mtime > ttl_s:
                marker.unlink()
        except OSError:
            continue


def bump(marker: Path) -> int:
    """Read the stop count for this subagent, write it back incremented, and
    return the value BEFORE the bump. Zero means this is the first stop."""
    try:
        count = int(marker.read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        count = 0
    marker.write_text(str(count + 1), encoding='utf-8')
    return count


def decide(payload: dict, env: dict[str, str], now: float) -> dict | None:
    """The block decision, or None to stay silent. Raises on an unusable state
    directory; `main` turns that into a fail-open."""
    if not is_armed(env) or skipped_by_tier(payload, env):
        return None
    directory = state_dir(env)
    directory.mkdir(parents=True, exist_ok=True)
    prune(directory, now)
    sid = token(payload.get('session_id'), 'nosid')
    aid = token(payload.get('agent_id'), 'noaid')
    if bump(directory / f'{sid}-{aid}.txt') != 0:
        return None  # second stop passes: the block cannot loop
    return {'decision': 'block', 'reason': RECONSIDER}


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            payload = {}
        decision = decide(payload, dict(os.environ), time.time())
        if decision is not None:
            print(json.dumps(decision))
    except Exception:
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""SubagentStop verification gate - off by default, fails open.

Work handed to a subagent loses verification the parent would have applied: measured
footprint drops from 0.48/0.59 (main agent) to 0.44 when the same task is delegated.
This hook holds each subagent once before it finishes and asks it to satisfy itself
the change works. Measured lift +0.56 on both weak and mid tiers, with zero
over-triggering on trivial edits (2026-07-25, 165+648 trials; see the README).

Design constraints this file honors:

* **Off unless HUMBLEPOWERS_SUBAGENT_VERIFY_GATE=1.** A Stop-blocking hook costs an
  extra turn per delegation; it is opt-in.
* **Fails open.** Any error, any unreadable payload, any un-writable marker means
  print nothing and exit 0. A gate that cannot prove it has already fired must not
  fire, because the failure mode of a Stop hook is an infinite block loop.
* **Blocks once per (session, agent).** The marker write happens BEFORE the block is
  emitted, so a crash between them leaves the subagent un-blocked rather than looped.
* **Skips read-only agent types.** Research/planning subagents make no edits to
  verify. This skip-list is a conservative addition: the measurement covered
  general-purpose subagents making code edits, not read-only ones.
* **ASCII payload**, per the plugin's hook convention.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ENV_FLAG = 'HUMBLEPOWERS_SUBAGENT_VERIFY_GATE'

# The wording is load-bearing and measured. It states the discipline and names no
# artifact. An earlier variant that prescribed one ("add a regression check now")
# scored higher on the primary metric and then performed the work on 58% of trivial
# edits; this one lifted real behavior at zero over-trigger cost. Do not "sharpen" it
# into an instruction without re-running the paired null measurement.
RECONSIDER = (
    'Before you finish: are you actually confident this is correct, or are you '
    'assuming it is? Take one more pass over what you changed and satisfy yourself '
    'that it genuinely works and that you would find out if it stopped working.'
)

# Read-only by charter - nothing they produce needs verifying.
SKIP_AGENT_TYPES = {'Explore', 'Plan', 'statusline-setup'}


def _enabled() -> bool:
    return os.environ.get(ENV_FLAG, '').strip() == '1'


def main() -> int:
    if not _enabled():
        return 0
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    agent_type = str(payload.get('agent_type', ''))
    if agent_type in SKIP_AGENT_TYPES:
        return 0

    session = str(payload.get('session_id', ''))
    agent = str(payload.get('agent_id', ''))
    if not session or not agent:
        return 0  # cannot key a guard -> cannot guarantee one block -> stay silent

    try:
        state = Path(tempfile.gettempdir()) / 'humblepowers-subagent-verify-gate'
        state.mkdir(exist_ok=True)
        marker = state / f'{session}-{agent}.txt'
        if marker.exists():
            return 0  # already blocked this subagent once
        marker.write_text('1', encoding='ascii')
    except Exception:
        return 0

    print(json.dumps({'decision': 'block', 'reason': RECONSIDER}))
    return 0


if __name__ == '__main__':
    sys.exit(main())

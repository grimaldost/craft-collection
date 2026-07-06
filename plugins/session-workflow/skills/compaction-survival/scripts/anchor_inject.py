"""SessionStart(compact|resume) anchor re-injection hook — memory-suite v2, C2.

Reads the hook input JSON on stdin, finds the newest non-closed control anchor
under <cwd>/.claude/anchors/, and emits it as SessionStart additionalContext so
a freshly compacted or resumed session re-reads its own state mechanically —
never relying on the compaction summary to carry constraints and decisions
(evidence base: docs/design/2026-07-04-memory-suite-research.md).

Ships INERT: does nothing unless SESSION_WORKFLOW_ANCHOR_HOOKS=1 (house
precedent — hooks are enabled deliberately, never by install). Hot-path
discipline: stdlib only, no LLM, no network, append-only telemetry, and every
failure path exits 0 — a broken hook must never break a session start.

Evidence that motivated shipping this (2026-07-04): 32 real sessions with
compaction events in ~30 days of this user's history, plus two same-day CC
restarts that wiped in-session state while the on-disk anchor survived.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ENV_GATE = 'SESSION_WORKFLOW_ANCHOR_HOOKS'
MAX_CONTEXT_CHARS = 8_000
STALE_AFTER_S = 24 * 3600


def find_anchor(anchors_dir: Path):
    """Newest *.md that is not closed and not housekeeping."""
    if not anchors_dir.is_dir():
        return None
    candidates = [f for f in anchors_dir.glob('*.md') if not f.name.endswith('.closed.md')]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


def build_context(anchor: Path, stale_s: float) -> str:
    text = anchor.read_text(encoding='utf-8', errors='ignore')
    truncated = False
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS]
        truncated = True

    header = [
        '<control-anchor>',
        f'A control anchor for this project exists at {anchor} '
        '(compaction-survival protocol). Re-read it before acting: verify the '
        'real state (git log, files on disk), then continue from its cursor. '
        'Treat it as the source of truth for run state over any summary above.',
    ]
    if stale_s > STALE_AFTER_S:
        hours = int(stale_s // 3600)
        header.append(
            f'WARNING - STALE: this anchor was last updated ~{hours}h ago. '
            'Validate it against external reality before trusting the cursor; '
            'the world may have moved on.'
        )
    body = [text]
    if truncated:
        body.append('[anchor truncated for injection - read the file for the rest]')
    return '\n'.join(header) + '\n---\n' + '\n'.join(body) + '\n</control-anchor>'


def append_telemetry(anchors_dir: Path, record: dict) -> None:
    try:
        log = anchors_dir / 'log.ndjson'
        with log.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError:
        pass  # telemetry is best-effort, never load-bearing


def main() -> int:
    if os.environ.get(ENV_GATE) != '1':
        return 0

    # Hook runners on Windows hand this script a cp1252 stdout; campaign anchors
    # essentially always carry non-ASCII (arrows, accented prose), so the print
    # below would raise and the fail-safe would swallow the whole injection.
    # Force UTF-8 at the seam instead of trusting the platform default.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    try:
        payload = json.loads(sys.stdin.read() or '{}')
    except json.JSONDecodeError:
        return 0

    cwd = Path(payload.get('cwd') or os.getcwd())
    anchors_dir = cwd / '.claude' / 'anchors'
    anchor = find_anchor(anchors_dir)
    if anchor is None:
        return 0

    stale_s = max(0.0, time.time() - anchor.stat().st_mtime)
    context = build_context(anchor, stale_s)

    record = {
        'event': 'anchor-inject',
        'source': payload.get('source', 'unknown'),
        'session': payload.get('session_id', ''),
        'file': anchor.name,
        'stale': stale_s > STALE_AFTER_S,
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    try:
        print(
            json.dumps(
                {
                    'hookSpecificOutput': {
                        'hookEventName': 'SessionStart',
                        'additionalContext': context,
                    }
                },
                ensure_ascii=False,
            )
        )
    except Exception as e:
        # Never break a session start, but never log success for an injection
        # that emitted nothing: a distinct failure event is the difference
        # between a 5-minute fix and a state-loss postmortem.
        append_telemetry(
            anchors_dir, {**record, 'event': 'anchor-inject-failed', 'error': type(e).__name__}
        )
        return 0
    # Success telemetry only after the payload actually reached stdout.
    append_telemetry(anchors_dir, record)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never break a session start

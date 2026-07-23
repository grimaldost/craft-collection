"""SessionStart(compact|resume|clear|startup) anchor re-injection hook.

Reads the hook input JSON on stdin, finds the newest open control anchor under
<cwd>/.claude/anchors/ (open = not renamed *.closed.md), and emits it as
SessionStart additionalContext, warning when other anchors are open in the
same directory (concurrent tracks). A freshly compacted or resumed session
thus re-reads its own live state mechanically — never relying on the
compaction summary to carry constraints and decisions (evidence base:
docs/design/2026-07-04-memory-suite-research.md).

Lifecycle gates (T22a hardening):
- FULL tier (anchor updated within STALE_AFTER_S): the HEAD — content above
  the `<!-- anchor:tail -->` marker; whole file when marker-less.
- POINTER tier (older): path + title + age + a confirm-to-expand line + the
  close command. A dead track costs a paragraph, never 8K chars, until a
  session confirms it — and it is never silently dropped either.
- source=startup (fresh process, the crash-restart path) proceeds only when
  the anchor was updated within STARTUP_RECENT_S; an ordinary new session in
  a cwd with an old anchor stays untaxed. compact/resume/clear — explicit
  continuation or reset signals — always evaluate.

Ships INERT: does nothing unless SESSION_WORKFLOW_ANCHOR_HOOKS=1 (house
precedent — hooks are enabled deliberately, never by install). Hot-path
discipline: stdlib only, no LLM, no network, append-only telemetry, and every
failure path exits 0 — a broken hook must never break a session start.

Evidence that motivated shipping this (2026-07-04): 32 real sessions with
compaction events in ~30 days of this user's history, plus two same-day CC
restarts that wiped in-session state while the on-disk anchor survived.
"""

# Annotations must not be evaluated at import time: this hook can run under any
# python a hook runner resolves, and a def-time `X | Y` union on 3.9 would fail
# the import itself — before the exit-0 guard exists.
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ENV_GATE = 'SESSION_WORKFLOW_ANCHOR_HOOKS'
MAX_CONTEXT_CHARS = 8_000
STALE_AFTER_S = 24 * 3600  # older than this -> pointer tier, not the full body
STARTUP_RECENT_S = 6 * 3600  # source=startup injects only within this window
MAX_NAMED_OPEN = 5  # cap the multi-track warning's name list; count the rest
# anchor/v1 two-tier structure: content above this marker line is the live HEAD
# (mission, cursor, invariants, last-known-good, resume steps) and is injected;
# the TAIL below (append-only decisions log, resolved history) stays on disk.
# Marker-less anchors keep the whole-file behavior.
TAIL_MARKER = '<!-- anchor:tail -->'


def _mtime(f: Path) -> float:
    """Race-safe mtime: a file renamed/deleted between glob and stat must not
    raise on this hot path (it would cost the whole injection)."""
    try:
        return f.stat().st_mtime
    except OSError:
        return 0.0


def _read(f: Path) -> str:
    """Race-safe read for classification: a file renamed/deleted between glob and
    read must not raise on this hot path."""
    try:
        return f.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''


# A track declares itself finished in-content with a whole-anchor status line whose
# VALUE is a terminal marker — `**Status:** CLOSED`, `status: landed on main` — (bold
# and heading markers stripped first). The terminal word must be the whole value
# (plus an optional "on/to <where>"), so an imperative or progress note that merely
# starts with the word — `Status: complete the migration`, `Status: landed X, now Y` —
# stays live. This never *stops* injection (the rename to *.closed.md is the only
# close signal); it only de-ranks the anchor below live tracks and drives the rename
# offer, so a terminal-but-unrenamed anchor stops shadowing active work.
_TERMINAL_STATUS = re.compile(
    r'^status\s*:?\s*(?:closed|done|complete|completed|landed|shipped|merged)'
    r'(?:\s+(?:on|to)\s+\w+)?[.\s]*$'
)


def is_content_terminal(text: str) -> bool:
    """True when an anchor's HEAD marks the whole track done but the file was never
    renamed (the accumulation root cause: seven such anchors stranded across ~8
    tracks). Scans only the HEAD (above the tail marker) — a folded per-phase status
    line in the append-only TAIL must not mark a live anchor terminal."""
    head, _ = split_head(text)
    for line in head.splitlines():
        if _TERMINAL_STATUS.match(line.replace('*', '').replace('#', '').strip().lower()):
            return True
    return False


def find_open_anchors(anchors_dir: Path) -> list[Path]:
    """All open (not renamed *.closed.md) anchors, newest first. The rename is
    the only close signal honored here — a prose "status: CLOSED" line does not
    stop injection."""
    if not anchors_dir.is_dir():
        return []
    candidates = [f for f in anchors_dir.glob('*.md') if not f.name.endswith('.closed.md')]
    return sorted(candidates, key=_mtime, reverse=True)


def select_anchor(open_anchors: list[Path]) -> tuple[Path, list[Path]]:
    """Choose the anchor to inject plus the others to warn about. The primary is the
    newest genuinely-active anchor; a content-terminal-but-unrenamed anchor is
    de-ranked and becomes primary only when nothing active remains (the recovery
    path never drops to zero bytes). `open_anchors` is newest-first; `others` keeps
    that order minus the primary."""
    active = [a for a in open_anchors if not is_content_terminal(_read(a))]
    primary = active[0] if active else open_anchors[0]
    return primary, [a for a in open_anchors if a != primary]


def list_stale(anchors_dir: Path) -> list[str]:
    """Rename commands for content-terminal-but-unrenamed anchors — the mechanical
    core of the /anchor close --stale cycle-end sweep. Returns the exact `mv` lines;
    it never runs them (the rename is the operator's deliberate close action)."""
    return [
        f'mv {f.name} {f.stem}.closed.md'
        for f in find_open_anchors(anchors_dir)
        if is_content_terminal(_read(f))
    ]


def split_head(text: str) -> tuple[str, bool]:
    """Return (head, has_tail): the content above the first TAIL_MARKER line,
    or the whole text when no marker exists. A marker with an empty HEAD is a
    malformed v1 anchor — fall back to whole-file rather than inject nothing
    (0 useful bytes on the recovery path is the protocol's cardinal failure)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == TAIL_MARKER:
            head = '\n'.join(lines[:i])
            if not head.strip():
                return text, False
            return head, True
    return text, False


def _other_open_warning(other_open: list[Path] | None) -> str:
    """The concurrent-tracks warning block, shared by both tiers; '' when alone."""
    if not other_open:
        return ''
    names = ', '.join(f.name for f in other_open[:MAX_NAMED_OPEN])
    if len(other_open) > MAX_NAMED_OPEN:
        names += f' and {len(other_open) - MAX_NAMED_OPEN} more'
    warn = (
        f'WARNING - {len(other_open)} other open anchor(s) in this dir: {names}. '
        'Concurrent tracks share this cwd; if this anchor is not your '
        "track's, read the right one before acting."
    )
    terminal = [f for f in other_open if is_content_terminal(_read(f))]
    if terminal:
        cmds = '; '.join(f'mv {f.name} {f.stem}.closed.md' for f in terminal[:MAX_NAMED_OPEN])
        more = len(terminal) - MAX_NAMED_OPEN
        warn += (
            f' {len(terminal)} read as closed in-content but were never renamed; '
            f'close each: {cmds}' + (f' (+{more} more)' if more > 0 else '')
        )
    return warn


def anchor_title(text: str) -> str:
    """First markdown heading (or first non-empty line) of the HEAD, minus any
    leading frontmatter block — the one-line identity the pointer tier shows."""
    head, _ = split_head(text)
    lines = head.splitlines()
    start = 0
    if lines and lines[0].strip() == '---':
        for j in range(1, len(lines)):
            if lines[j].strip() == '---':
                start = j + 1
                break
    for line in lines[start:]:
        s = line.strip()
        if s.startswith('#'):
            title = s.lstrip('#').strip()
            if title:
                return title[:120]
    for line in lines[start:]:
        s = line.strip()
        if s and s.lstrip('#').strip():
            return s[:120]
    return '(untitled)'


def build_context(anchor: Path, other_open: list[Path] | None = None) -> str:
    """FULL tier: the anchor HEAD (bounded), plus the concurrent-tracks warning.
    Race-safe read: an anchor renamed/deleted after selection (a concurrent
    session closing it) degrades to a path-only context — never a raise that
    would skip both the injection AND the failure telemetry."""
    text, has_tail = split_head(_read(anchor))
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
    warn = _other_open_warning(other_open)
    if warn:
        header.append(warn)
    body = [text]
    if has_tail:
        body.append(
            '[anchor tail (decisions log / resolved history) on disk - read the file if needed]'
        )
    if truncated:
        body.append('[anchor truncated for injection - read the file for the rest]')
    return '\n'.join(header) + '\n---\n' + '\n'.join(body) + '\n</control-anchor>'


def build_pointer(anchor: Path, stale_s: float, other_open: list[Path] | None = None) -> str:
    """POINTER tier for a stale anchor: identity + age + confirm-to-expand +
    the close command — a short pointer, never the 8K body, and never silence.
    (The title is capped; the shared concurrent-tracks warning can extend the
    total when many terminal anchors accumulate — still far under the bound.)"""
    hours = int(stale_s // 3600)
    lines = [
        '<control-anchor>',
        f'A control anchor exists at {anchor} but is STALE: last updated '
        f'~{hours}h ago, so its body is withheld to spare context.',
        f'Title: {anchor_title(_read(anchor))}',
        'If you are continuing that track, read the file now - it is the source '
        'of truth for its run state. If the track is finished, close it: '
        f'mv {anchor.name} {anchor.stem}.closed.md',
    ]
    warn = _other_open_warning(other_open)
    if warn:
        lines.append(warn)
    lines.append('</control-anchor>')
    return '\n'.join(lines)


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
    open_anchors = find_open_anchors(anchors_dir)
    if not open_anchors:
        return 0
    anchor, other_open = select_anchor(open_anchors)

    stale_s = max(0.0, time.time() - _mtime(anchor))
    source = payload.get('source')
    source = source if isinstance(source, str) else ''
    # Crash-restart branch: a fresh process only gets the anchor when it was
    # updated recently enough to plausibly be the interrupted run. Explicit
    # continuation/reset signals (compact/resume/clear) always evaluate.
    if source == 'startup' and stale_s > STARTUP_RECENT_S:
        return 0
    pointer = stale_s > STALE_AFTER_S
    context = (
        build_pointer(anchor, stale_s, other_open) if pointer else build_context(anchor, other_open)
    )

    record = {
        'event': 'anchor-inject',
        'source': payload.get('source', 'unknown'),
        'session': payload.get('session_id', ''),
        'file': anchor.name,
        'stale': pointer,
        'tier': 'pointer' if pointer else 'full',
        'open_anchors': len(open_anchors),
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
    # Explicit sweep entry: `python anchor_inject.py --list-stale [anchors_dir]` prints
    # the rename commands for the cycle-end /anchor close --stale sweep and exits.
    if len(sys.argv) > 1 and sys.argv[1] == '--list-stale':
        base = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd() / '.claude' / 'anchors'
        for cmd in list_stale(base):
            print(cmd)
        sys.exit(0)
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never break a session start

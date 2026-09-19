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
  the `<!-- anchor:tail -->` marker; whole file when marker-less. Over budget,
  the cursor section is reserved first and the rest of the HEAD is spent
  top-down on whole sections, with the dropped ones named: document order is the
  drop order for everything except the one section a resuming session cannot do
  without. Measure a draft against that budget with `--head-fit <anchor>`.
- POINTER tier (older): path + title + age + the cursor the anchor still
  asserts + a confirm-to-expand line + the close command. A dead track costs a
  paragraph, never 8K chars, until a session confirms it — and it is never
  silently dropped either.
- source=startup (fresh process, the crash-restart path) proceeds only when
  the anchor was updated within STARTUP_RECENT_S; an ordinary new session in
  a cwd with an old anchor stays untaxed. compact/resume/clear — explicit
  continuation or reset signals — always evaluate.

Ships ON. `SESSION_WORKFLOW_ANCHOR_HOOKS=0` is the documented opt-out. It shipped
inert behind an unset variable until 2026-08, which meant the mechanism carrying
this plugin's strongest claim had never run anywhere while the claim rested on
it — and the no-anchor path already returns zero with no output, so a default-on
hook costs a subprocess and nothing else. Hot-path discipline: stdlib only, no
LLM, no network, append-only telemetry, and every failure path exits 0 — a broken
hook must never break a session start.

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
from typing import NamedTuple

ENV_GATE = 'SESSION_WORKFLOW_ANCHOR_HOOKS'
MAX_CONTEXT_CHARS = 8_000
STALE_AFTER_S = 24 * 3600  # older than this -> pointer tier, not the full body
STARTUP_RECENT_S = 6 * 3600  # source=startup injects only within this window
DORMANT_AFTER_S = 72 * 3600  # --list-dormant threshold: still active, long untouched
MAX_NAMED_OPEN = 5  # cap the multi-track warning's name list; count the rest
MAX_NAMED_DROPPED = 6  # cap the dropped-section name list the same way
# A HEAD section boundary. Order is priority: the budget is spent top-down and
# the first section that does not fit ends the injection, so what an author
# writes first is what survives a cut — the cursor excepted, which `fit_head`
# reserves before spending the rest.
HEADING_RE = re.compile(r'^#{1,6}\s+(\S.*)$')
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
# The frontmatter line `/anchor` writes on every snapshot; one of the two signals
# that a `*.md` in anchors/ is an anchor rather than a document parked there.
_FORMAT_LINE = re.compile(r'^\s*format\s*:\s*anchor/', re.I)


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


def is_anchor_shaped(text: str) -> bool:
    """True when a file in `anchors/` actually looks like one: the
    `format: anchor/...` frontmatter `/anchor` writes, or a cursor section.

    A 79 KB design document dropped into the directory was selected purely
    because it was the newest `*.md`, and the whole injection budget went to a
    file with no cursor in it. Two signals rather than one because the v0
    anchors in the wild carry no `format:` line, and a predicate that silenced
    them would silence exactly the long-running tracks this protocol is for."""
    head, _ = split_head(text)
    lines = head.splitlines()
    if lines and lines[0].strip() == '---':
        for line in lines[1:]:
            if line.strip() == '---':
                break
            if _FORMAT_LINE.match(line):
                return True
    return any(_is_cursor_section(name) for name, _ in split_sections(head))


def select_anchor(open_anchors: list[Path]) -> tuple[Path, list[Path]]:
    """Choose the anchor to inject plus the others to warn about. The primary is the
    newest genuinely-active anchor; a file that is not shaped like an anchor at all,
    and a content-terminal-but-unrenamed anchor, are de-ranked and become primary
    only when nothing better remains (the recovery path never drops to zero bytes).
    `open_anchors` is newest-first; the sort is stable, so recency still decides
    within a rank, and `others` keeps that order minus the primary."""

    def rank(a: Path) -> tuple[bool, bool]:
        text = _read(a)
        return (not is_anchor_shaped(text), is_content_terminal(text))

    primary = sorted(open_anchors, key=rank)[0]
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


def split_sections(head: str) -> list[tuple[str, str]]:
    """(name, block) pairs in document order, lossless: joining the blocks with
    newlines reproduces `head`. Content before the first heading is the preamble
    and is named ''. Headings inside fenced code are not boundaries — an anchor
    that pastes a shell transcript would otherwise be shredded at every `#`."""
    sections: list[tuple[str, str]] = []
    name = ''
    block: list[str] = []
    in_fence = False
    for line in head.splitlines():
        if line.lstrip().startswith('```'):
            in_fence = not in_fence
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            if block:
                sections.append((name, '\n'.join(block)))
            name = match.group(1).strip()
            block = [line]
        else:
            block.append(line)
    if block:
        sections.append((name, '\n'.join(block)))
    return sections


class HeadFit(NamedTuple):
    """What `fit_head` decided: the text to inject, the sections it could not
    afford, whether it had to cut inside one, and the cursor section it reserved
    ('' when the HEAD names none). A named tuple rather than a bare triple
    because the drop line has to SAY the cursor was held back: a manifest that
    reads the same whether or not the reserve happened is the manifest the
    operator already learned to distrust."""

    text: str
    dropped: list[str]
    byte_cut: bool
    cursor_reserved: str


def _is_cursor_section(name: str) -> bool:
    """The one matcher for "this heading is the cursor", shared by the reserve
    and by `anchor_cursor` so the two can never disagree about which section
    the protocol's load-bearing one is."""
    return 'cursor' in name.lower()


def fit_head(head: str) -> HeadFit:
    """Reserve the cursor, then spend the rest of the injection budget top-down
    on whole sections.

    Document order is still the drop order for everything else: the first
    section that does not fit ends the injection and everything after it is
    dropped, so a HEAD written worst-loss-first degrades predictably instead of
    being cut mid-sentence.

    The cursor is the exception, and it is the reason this function changed. Pure
    document order lost the cursor on four separate nights AFTER the survival-order
    doctrine and the drop manifest shipped, because the natural anchor grows
    chronologically and an author who obeys the order still writes a standing-
    directives block above the cursor. Naming a section in a manifest does not
    return it to the reader; the cursor is the one section a resuming session
    cannot do without, so it is taken off the top of the budget and re-inserted in
    its own document position — the reserve changes what survives, not where it
    appears.

    The byte cut survives as the floor, for the cases sections cannot help: an
    anchor with no headings to cut on, a first section that alone overruns, and a
    cursor that alone overruns (kept and cut, because a bloated cursor still beats
    no cursor). Injecting nothing on the recovery path is the protocol's cardinal
    failure, so a cut always beats silence — and the signals stay distinct, because
    "I dropped History", "I held the cursor back" and "I cut you off mid-word" are
    different things to tell a reader."""
    if len(head) <= MAX_CONTEXT_CHARS:
        return HeadFit(head, [], False, '')
    sections = split_sections(head)
    if len(sections) < 2:
        return HeadFit(head[:MAX_CONTEXT_CHARS], [], True, '')
    cursor_idx = next((i for i, (name, _) in enumerate(sections) if _is_cursor_section(name)), None)
    if cursor_idx is not None:
        cursor_name, cursor_block = sections[cursor_idx]
        if len(cursor_block) + 1 > MAX_CONTEXT_CHARS:
            others = [n or '(preamble)' for i, (n, _) in enumerate(sections) if i != cursor_idx]
            return HeadFit(cursor_block[:MAX_CONTEXT_CHARS], others, True, cursor_name)
    return _spend_budget(head, sections, cursor_idx)


def _spend_budget(head: str, sections: list[tuple[str, str]], cursor_idx: int | None) -> HeadFit:
    """Fill the budget in document order, with the cursor section (if any) already
    paid for. Kept sections are re-joined in document order, so the injected HEAD
    still reads as the file it came from."""
    reserved = 0 if cursor_idx is None else len(sections[cursor_idx][1]) + 1
    kept: set[int] = set() if cursor_idx is None else {cursor_idx}
    used = reserved
    overran = False
    for i, (_name, block) in enumerate(sections):
        if i == cursor_idx:
            continue
        cost = len(block) + 1
        if overran or used + cost > MAX_CONTEXT_CHARS:
            overran = True  # order is a priority, not a packing problem
            continue
        kept.add(i)
        used += cost
    dropped = [name or '(preamble)' for i, (name, _) in enumerate(sections) if i not in kept]
    if not kept:
        # No cursor to reserve and the first section alone overruns. Cut inside
        # it, and still name the sections beyond it that were lost whole.
        return HeadFit(head[:MAX_CONTEXT_CHARS], dropped[1:], True, '')
    text = '\n'.join(sections[i][1] for i in sorted(kept))
    return HeadFit(text, dropped, False, '' if cursor_idx is None else sections[cursor_idx][0])


def anchor_cursor(text: str) -> str:
    """The cursor section's first content line — what a reader needs to judge
    whether a dormant anchor's claim is still true. A pointer that shows only
    path, title and age cannot be acted on; one that shows "Phase 1 IN PROGRESS"
    against a four-day-old file can. '' when the HEAD names no cursor."""
    head, _ = split_head(text)
    for name, block in split_sections(head):
        if 'cursor' in name.lower():
            for line in block.splitlines()[1:]:
                stripped = line.strip().lstrip('-*').strip()
                if stripped:
                    return stripped[:160]
    return ''


def head_fit_report(anchor: Path) -> list[str]:
    """What the injection would do to this anchor at its current size: head
    characters, the budget, the cursor section reserved, and the sections that
    would drop.

    The hook computes exactly this on every injection and the author had no way to
    ask for it — so the byte counter was hand-written three times in one session
    and a head still went out 118 bytes over budget. Measuring the HEAD, not the
    file, is the point: the TAIL stays on disk and shrinking it buys nothing.

    The unit is characters because that is what `fit_head` spends: `len()` over a
    str. A figure labelled bytes differs from it on any non-ASCII anchor, and near
    the budget that difference decides whether the author trims.

    The cursor line reads the HEAD itself rather than `fit.cursor_reserved`: a head
    within budget returns early with nothing reserved, and reading that empty
    reservation as "no cursor" told an author a false thing about the anchor on
    the common case."""
    head, has_tail = split_head(_read(anchor))
    fit = fit_head(head)
    over = len(head) - MAX_CONTEXT_CHARS
    verdict = f'OVER by {over}' if over > 0 else f'headroom {-over}'
    lines = [f'head: {len(head)} chars / budget {MAX_CONTEXT_CHARS} chars  {verdict}']
    if has_tail:
        lines.append('tail: below the marker, on disk, not injected')
    cursor = next((name for name, _ in split_sections(head) if _is_cursor_section(name)), '')
    if fit.cursor_reserved:
        lines.append(f'cursor reserved: {fit.cursor_reserved}')
    elif not cursor:
        lines.append('cursor reserved: (none - this HEAD names no cursor)')
    elif over <= 0:
        lines.append(f'cursor: {cursor} (no reservation needed - the head fits)')
    else:
        lines.append(f'cursor: {cursor} (not reserved - no other section to drop)')
    lines.append(f'would drop: {", ".join(fit.dropped) if fit.dropped else "(nothing)"}')
    if fit.byte_cut:
        lines.append('and would still be cut mid-section: one section alone overruns the budget')
    return lines


def list_dormant(anchors_dir: Path, min_age_s: float = DORMANT_AFTER_S) -> list[str]:
    """Open, still-ACTIVE anchors untouched beyond min_age_s: name, age, title and
    the cursor each still asserts. `list_stale` cannot reach these — it keys on
    content that reads as done, and an anchor abandoned mid-cursor never says so.
    Read at the moment a new anchor is armed, which is the one moment a human is
    reliably present to answer close-or-adopt."""
    now = time.time()
    out = []
    for f in find_open_anchors(anchors_dir):
        age_s = now - _mtime(f)
        if age_s < min_age_s:
            continue
        text = _read(f)
        if is_content_terminal(text):
            continue  # list_stale owns the closed-but-unrenamed ones
        line = f'{f.name}  {int(age_s // 3600)}h  {anchor_title(text)}'
        cursor = anchor_cursor(text)
        if cursor:
            line += f'  | cursor: {cursor}'
        out.append(line)
    return out


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
    strays = [f for f in other_open if not is_anchor_shaped(_read(f))]
    if strays:
        names = ', '.join(f.name for f in strays[:MAX_NAMED_OPEN])
        more = len(strays) - MAX_NAMED_OPEN
        warn += (
            f' {len(strays)} of them read as "not an anchor" (no format: anchor/... line and '
            f'no cursor section): {names}' + (f' (+{more} more)' if more > 0 else '') + '.'
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
    raw = _read(anchor)
    text, has_tail = split_head(raw)
    fit = fit_head(text)
    text = fit.text

    header = [
        '<control-anchor>',
        f'A control anchor for this project exists at {anchor} '
        '(compaction-survival protocol). Re-read it before acting: verify the '
        'real state (git log, files on disk), then continue from its cursor. '
        'Treat it as the source of truth for run state over any summary above.',
    ]
    if not is_anchor_shaped(raw):
        # It was the best candidate in the directory, so it is injected - but say
        # that it does not read as an anchor, rather than letting a design document
        # arrive wearing the anchor's authority.
        header.append(
            'CAUTION - this file reads as "not an anchor" (no format: anchor/... '
            'line and no cursor section); it was injected because nothing better '
            'was open in that directory.'
        )
    warn = _other_open_warning(other_open)
    if warn:
        header.append(warn)
    body = [text]
    if has_tail:
        body.append(
            '[anchor tail (decisions log / resolved history) on disk - read the file if needed]'
        )
    if fit.dropped:
        names = ', '.join(fit.dropped[:MAX_NAMED_DROPPED])
        if len(fit.dropped) > MAX_NAMED_DROPPED:
            names += f' and {len(fit.dropped) - MAX_NAMED_DROPPED} more'
        note = f'[dropped from injection, in HEAD order: {names}'
        if fit.cursor_reserved:
            # Say the reserve happened. A manifest that reads identically whether
            # or not the cursor was held back cannot tell the reader which of the
            # two worlds they are in, and the cursor is the whole question.
            note += f' - cursor reserved ahead of them ("{fit.cursor_reserved}")'
        body.append(note + ' - read the file for them]')
    if fit.byte_cut:
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
    # The cursor is what makes a stale pointer actionable: path/title/age cannot be
    # checked against reality, but "Phase 1 IN PROGRESS - workflow wf_..." on a
    # four-day-old file can be, and was once wrong while the durable state said so.
    cursor = anchor_cursor(_read(anchor))
    if cursor:
        lines.append(f'Cursor it still asserts: {cursor}')
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


def _force_utf8_stdout() -> None:
    """Hook runners on Windows hand this script a cp1252 stdout; campaign anchors
    essentially always carry non-ASCII (arrows, accented prose), so any print of
    anchor content would raise. Force UTF-8 at the seam instead of trusting the
    platform default."""
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')


def main() -> int:
    if os.environ.get(ENV_GATE) == '0':
        return 0

    _force_utf8_stdout()

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
    # Before any CLI arm prints: both sweeps emit anchor CONTENT (titles, cursors),
    # and campaign anchors essentially always carry non-ASCII. On a cp1252 console
    # an arrow in a cursor raised UnicodeEncodeError and the sweep died with a
    # traceback -- the same seam main() already forces, applied one scope out.
    _force_utf8_stdout()
    # Explicit sweep entry: `python anchor_inject.py --list-stale [anchors_dir]` prints
    # the rename commands for the cycle-end /anchor close --stale sweep and exits.
    if len(sys.argv) > 1 and sys.argv[1] == '--list-stale':
        base = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd() / '.claude' / 'anchors'
        for cmd in list_stale(base):
            print(cmd)
        sys.exit(0)
    # Arm-time sweep entry: `python anchor_inject.py --list-dormant [anchors_dir]`
    # prints the still-ACTIVE anchors nobody has touched in DORMANT_AFTER_S, with
    # the cursor each still asserts, so arming a new track can offer close-or-adopt.
    if len(sys.argv) > 1 and sys.argv[1] == '--list-dormant':
        base = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd() / '.claude' / 'anchors'
        for line in list_dormant(base):
            print(line)
        sys.exit(0)
    # Authoring entry: `python anchor_inject.py --head-fit <anchor>` prints the fit
    # the hook would compute, so a head is measured before it ships rather than
    # after a night's cursor is named in a drop line. A reporter, not a gate: it
    # exits 0 whatever the verdict, and 2 only when it was pointed at nothing (a
    # path typo must not render as a clean measurement).
    if len(sys.argv) > 1 and sys.argv[1] == '--head-fit':
        target = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        if target is None or not target.is_file():
            print(
                f'error: --head-fit needs the path to one anchor file (got: {target})',
                file=sys.stderr,
            )
            sys.exit(2)
        for line in head_fit_report(target):
            print(line)
        sys.exit(0)
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never break a session start

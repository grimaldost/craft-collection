#!/usr/bin/env python3
"""Rebuild a feedback dir's INDEX.md — one section per report with its numbered
proposal titles — so an `extends`-lookup during capture (tool-feedback) or triage
(feedback-triage) is one Read instead of N speculative, phrasing-fragile greps (the
recurrence-grep robustness fix). Stdlib only; best-effort parsing of the report
template's "## Proposed promotions" section. The output (INDEX.md) is a generated
artifact — regenerate it, do not hand-edit.

    uv run --no-project python build_feedback_index.py <feedback-dir> [--force]

Use `uv run --no-project python` (not a bare `python` / `python3`): on Windows
without Python on PATH, both resolve to the Microsoft-Store app-execution stub
and abort.

The index is the loop's memory, so the write defends itself. An existing index
stamped with a NEWER builder version is not overwritten: the run exits non-zero
naming both versions and the file, because an older cached copy silently
downgrading a newer index is a structural loss nobody sees. `--force` is the
deliberate-rollback escape hatch. Every write prints the report and finding
delta, so a loss is visible even when the two versions match.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

# The triage-doc detection rule this generator applies (stamped into the INDEX
# header): a doc is a triage doc iff its H1 starts with '# Triage'. A stale
# plugin cache re-applies its old rule forever — the stamp makes that visible.
DETECTION_RULE = 'H1-rule'


def _plugin_version() -> str:
    """Version of the copy that is actually running (cache or working tree) —
    that is the point: a stale cache stamps its own, older version."""
    try:
        manifest = Path(__file__).resolve().parents[3] / '.claude-plugin' / 'plugin.json'
        return str(json.loads(manifest.read_text(encoding='utf-8')).get('version', 'unknown'))
    except (OSError, ValueError):
        return 'unknown'


# A top-level numbered proposal is flush-left (`^\d+\.`, no leading whitespace) — the
# template writes proposals at indent 0. An indented number is a sub-list item, and a
# numbered line inside a fenced code block is a code sample; neither is a proposal, so
# neither may mint a (duplicate or phantom) finding ID.
_PROPOSAL = re.compile(r'^(\d+)\.\s+(.+?)\s*$')
_FENCE = re.compile(r'^\s*(```|~~~)')
# A leading severity tag — **[MED]** / **[HIGH]** / **[P1]** / **[P2-HIGH]** — including
# digit and hyphen forms, not only alpha ones (`[A-Za-z/]+` left `**[P1]**` glued on).
# Captured, not merely stripped: the digest's consumer clusters by severity, and a
# stripped tag cost one `extends` delta four full report reads.
_SEVERITY = re.compile(r'\*\*\[([A-Za-z0-9/-]+)\]\*\*\s*')
# The template's two repeat forms: "extends `<stem>#<n>`" and "extends `<stem>` section".
_EXTENDS = re.compile(
    r'^extends\s+`([^`]+)`(?:\s*§\s*([A-Za-z]+))?\s*(?:[-—:]\s*)?',  # ascii-ok: report text
    re.IGNORECASE,
)
# "phase: gate" / "phase: pre-mortem" — the miss's own account of what should have
# caught it. Lifted out of the prose when it trails the bullet, read in place otherwise.
_PHASE_ANY = re.compile(r'\bphase:\s*([A-Za-z][\w-]*)', re.IGNORECASE)
_PHASE_TRAILING = re.compile(r'\s*[(\[]?\s*phase:\s*([A-Za-z][\w-]*)\s*[)\]]?\s*$', re.IGNORECASE)


class Proposal(NamedTuple):
    number: str
    severity: str  # 'MED' — '' when the proposal carries no tag
    extends: str  # 'prior-stem#3' — '' when the finding is fresh
    title: str


class Stub(NamedTuple):
    section: str  # 'Misses' | 'Friction'
    severity: str
    phase: str  # 'gate' — '' when the bullet names none
    extends: str
    title: str


def _split_severity(text: str) -> tuple[str, str]:
    m = _SEVERITY.search(text)
    return (m.group(1) if m else ''), _SEVERITY.sub('', text).strip()


def _split_extends(text: str) -> tuple[str, str]:
    m = _EXTENDS.match(text)
    if not m:
        return '', text
    ref = m.group(1) + (f' §{m.group(2)}' if m.group(2) else '')  # ascii-ok: index content
    return ref, text[m.end() :].strip()


def _split_phase(text: str) -> tuple[str, str]:
    trailing = _PHASE_TRAILING.search(text)
    if trailing:
        return trailing.group(1), text[: trailing.start()].rstrip(' ([,;')
    anywhere = _PHASE_ANY.search(text)
    return (anywhere.group(1) if anywhere else ''), text


def extract_proposals(text: str) -> list[Proposal]:
    """Return [Proposal(number, severity, extends, title)] from the report's
    "## Proposed promotions" section. Only flush-left numbered lines outside fenced code
    blocks count; indented sub-lists and fenced numbered lines are ignored. The severity
    tag and any leading `extends` reference become fields rather than title prose, and
    the remainder is capped; parsing stops at the next `## ` heading. Best-effort: a
    report without the section yields []."""
    out: list[Proposal] = []
    in_section = False
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if stripped.startswith('## '):
            in_section = stripped[3:].strip().lower().startswith('proposed')
            continue
        if in_section:
            m = _PROPOSAL.match(line)
            if m:
                severity, rest = _split_severity(m.group(2))
                extends, title = _split_extends(rest)
                out.append(Proposal(m.group(1), severity, extends, title[:140]))
    return out


# Flush-left bullets under `## Misses` / `## Friction` become §-stub entries: the
# capture/triage skills sanction `extends <stem> §Misses` as a recurrence target,
# so those sections must be greppable in the index, not only `## Proposed`.
_BULLET = re.compile(r'^-\s+(.+?)\s*$')
_STUB_SECTIONS = ('misses', 'friction')


def extract_section_bullets(text: str) -> list[Stub]:
    """Return [Stub(section, severity, phase, extends, bullet)] for flush-left `- `
    bullets under the `## Misses` / `## Friction` sections — the §-stub twins of
    extract_proposals. Fence-aware; indented sub-bullets ignored; severity, phase and
    any leading `extends` reference lifted into fields; remainder capped."""
    out: list[Stub] = []
    section: str | None = None
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if stripped.startswith('## '):
            low = stripped[3:].strip().lower()
            section = next((s.capitalize() for s in _STUB_SECTIONS if low.startswith(s)), None)
            continue
        if section:
            m = _BULLET.match(line)
            if m:
                severity, rest = _split_severity(m.group(1))
                extends, rest = _split_extends(rest)
                phase, title = _split_phase(rest)
                out.append(Stub(section, severity, phase, extends, title.strip()[:140]))
    return out


def _is_triage_doc(p: Path) -> bool:
    """A triage doc (a loop OUTPUT, not a source report) declares itself with a
    `# Triage` H1 — detect it by that, not by a 'triage' substring in the filename.
    A substring match also catches legitimate INPUT reports: a tool-feedback report
    ABOUT the `feedback-triage` tool, or a `<date>-triage-round-<tool>` wave slug,
    both open with a `# <tool> feedback` H1 and must still be indexed (the old filter
    silently dropped them — e.g. `2026-06-14-feedback-triage-batch-run.md`). Reads
    only the file head; on a read error returns False (index it, never silently
    drop)."""
    try:
        with p.open(encoding='utf-8', errors='replace') as fh:
            head = fh.read(512)
    except OSError:
        return False
    for line in head.splitlines():
        s = line.strip()
        if s.startswith('# '):
            return s[2:].lstrip().lower().startswith('triage')
    return False  # no H1 found -> not a triage doc


def _is_report(p: Path) -> bool:
    """A source report — not the index/readme/backlog, not a digest, and not a triage
    doc (those are OUTPUTS of the loop, not inputs to index). The index, readme, and a
    consolidated `BACKLOG.md` status doc are excluded by exact name; triage docs are
    detected by their `# Triage` H1 (see `_is_triage_doc`), so a legitimate report whose
    slug contains 'triage' is still indexed."""
    name = p.name.lower()
    return (
        p.suffix == '.md'
        and name not in ('index.md', 'readme.md', 'backlog.md')
        and 'digest' not in name
        and not _is_triage_doc(p)
    )


_COVERAGE_HEADING = re.compile(r'^#{2,4}\s+(?:inputs\b|addendum\b)', re.IGNORECASE)
_ANY_HEADING = re.compile(r'^#{1,6}\s')


def _coverage_text(text: str) -> str:
    """Body text of a triage doc's coverage-bearing sections — the `## Inputs` list
    plus any dated `## Addendum …` sections. Whole-section (not list-items-only) on
    purpose: a report is sometimes closed in Inputs *prose* rather than a list item
    (e.g. "two earlier un-listed reports closed here for the input-list test"), and
    that disposition must count. The cost is that a stem merely *named in passing* in
    a coverage section ("unlike report-x") is also credited — the authoring
    convention is to name in a coverage section only reports the pass dispositions.
    Fence-aware, so a `#`-comment inside a fenced command block does not
    end the section and silently drop the inputs after it. The addendum flow appends a
    later wave's inputs under an Addendum heading rather than editing the frozen Inputs
    list, so coverage read from Inputs alone under-reports addendum-handled reports —
    they resurface as untriaged (v19-sw#2). An `### Inputs` nested inside an addendum
    re-opens capture, so it is not lost."""
    out: list[str] = []
    capturing = False
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _ANY_HEADING.match(line):
            capturing = bool(_COVERAGE_HEADING.match(line))
            continue
        if capturing:
            out.append(line)
    return '\n'.join(out)


def extract_inputs_coverage(text: str, report_stems: list[str]) -> list[str]:
    """Report stems a triage doc covers: any known stem appearing in its coverage
    sections (`## Inputs` + dated `## Addendum …`) — matched at a name boundary (not
    followed by another stem character), because the corpus has prefix-colliding
    stems (`...-refresh-on-read` vs `...-refresh-on-read-execution`) and a bare
    substring test would mark the shorter one covered by accident. Otherwise
    phrasing-robust: bullets, numbering, and annotations all match."""
    section = _coverage_text(text)
    if not section:
        return []
    return [s for s in report_stems if re.search(re.escape(s) + r'(?![A-Za-z0-9_-])', section)]


def _render_finding(ref: str, severity: str, phase: str, extends: str, title: str) -> str:
    """One digest line. Fields in a fixed order and omitted when empty, so `[HIGH]`,
    `(phase: gate)` and `extends \\`x#3\\`` are greppable positions rather than prose."""
    bits = [f'- `{ref}`']
    if severity:
        bits.append(f'[{severity}]')
    if phase:
        bits.append(f'(phase: {phase})')
    if extends:
        bits.append(f'extends `{extends}`')
    bits.append(f'— {title}')  # ascii-ok: index content
    return ' '.join(bits)


# The generator stamp in an existing index's header — the provenance line this script
# has always written and never read (its own docstring documented the hazard).
_INDEX_VERSION = re.compile(r'generated by build_feedback_index\.py \(session-workflow ([^,\s)]+)')
# A digest line, told apart from a coverage or untriaged line by its `#<n>` / ` §Sec` ref.
_INDEX_FINDING = re.compile(r'^- `[^`]+(?:#\d+| §[A-Za-z]+)`')  # ascii-ok: index content
MAX_NAMED_DELTA = 5  # cap the arrived/left name list; count the rest


def _version_key(v: str) -> tuple[int, ...] | None:
    m = re.match(r'^(\d+(?:\.\d+)*)', v.strip())
    return tuple(int(x) for x in m.group(1).split('.')) if m else None


def downgrade_blocker(existing_text: str, running_version: str) -> str | None:
    """The version stamped in an existing index when it is NEWER than the copy about
    to overwrite it; None when the write is safe. Unstamped or unparseable versions
    return None — refusing on a version this script cannot read would make every
    hand-rolled index unbuildable."""
    m = _INDEX_VERSION.search(existing_text)
    if not m:
        return None
    existing, running = _version_key(m.group(1)), _version_key(running_version)
    if existing is None or running is None:
        return None
    return m.group(1) if existing > running else None


def index_counts(text: str) -> tuple[int, int]:
    """(reports, findings) read back out of an index — the two numbers a silent
    structural loss shows up in."""
    reports = findings = 0
    for line in text.splitlines():
        if line.startswith('## ') and line.strip() != '## Triage coverage':
            reports += 1
        elif _INDEX_FINDING.match(line):
            findings += 1
    return reports, findings


def index_stems(text: str) -> list[str]:
    """Report stems an index names — the identity the counts cannot show."""
    return [
        line[3:].strip()
        for line in text.splitlines()
        if line.startswith('## ') and line.strip() != '## Triage coverage'
    ]


def _named_delta(old_text: str, new_text: str) -> str:
    """Which stems arrived and which left. Counts alone hide identity: a rename is
    `+0` on both numbers while a stem is silently rewritten, and a simultaneous
    add and remove reads as "nothing happened" — both observed. The counts are
    what a reader checks, so the names ride the same line."""
    was, now = set(index_stems(old_text)), set(index_stems(new_text))
    bits = []
    for sign, names in (('+', sorted(now - was)), ('-', sorted(was - now))):
        if not names:
            continue
        shown = ', '.join(names[:MAX_NAMED_DELTA])
        if len(names) > MAX_NAMED_DELTA:
            shown += f' and {len(names) - MAX_NAMED_DELTA} more'
        bits.append(f'{sign}{shown}')
    return f' [{"; ".join(bits)}]' if bits else ''


def delta_line(old_text: str, new_text: str) -> str:
    """One line naming what the write changed. Versions matching is not enough: a
    parser change can drop findings while the stamp stays identical."""
    reports, findings = index_counts(new_text)
    if not old_text.strip():
        return f'{reports} report(s), {findings} finding(s) (new index)'
    was_reports, was_findings = index_counts(old_text)
    return (
        f'{reports} report(s) ({reports - was_reports:+d}), '
        f'{findings} finding(s) ({findings - was_findings:+d})'
        f'{_named_delta(old_text, new_text)}'
    )


def build_index(feedback_dir: Path) -> str:
    reports = sorted(p for p in feedback_dir.glob('*.md') if _is_report(p))
    triage_docs = sorted(
        p for p in feedback_dir.glob('*.md') if p.name.lower() != 'index.md' and _is_triage_doc(p)
    )
    lines = [
        '# Feedback index',
        '',
        # This header and the digest lines below go to INDEX.md, never to a console.
        f'{len(reports)} report(s) — generated by build_feedback_index.py '  # ascii-ok
        f'(session-workflow {_plugin_version()}, {DETECTION_RULE}); do not hand-edit. '  # ascii-ok
        'Each entry is a report stem with its numbered proposals and its '
        '§Misses/§Friction bullet stubs; grep here for an `extends` target before '  # ascii-ok
        'restating a finding. `## Triage coverage` maps each triage doc to the '
        'reports its Inputs and dated Addendum sections list; `### Untriaged` is '
        "the scope step's input list.",
        '',
    ]
    for p in reports:
        lines.append(f'## {p.stem}')
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
        except OSError:
            lines += ['- (unreadable)', '']
            continue
        props = extract_proposals(text)
        stubs = extract_section_bullets(text)
        if props:
            lines += [
                _render_finding(f'{p.stem}#{pr.number}', pr.severity, '', pr.extends, pr.title)
                for pr in props
            ]
        elif not stubs:
            lines.append('- (no numbered proposals)')
        for s in stubs:
            ref = f'{p.stem} §{s.section}'  # ascii-ok: index content
            lines.append(_render_finding(ref, s.severity, s.phase, s.extends, s.title))
        lines.append('')

    report_stems = [p.stem for p in reports]
    covered: set[str] = set()
    lines += ['## Triage coverage', '']
    for t in triage_docs:
        lines.append(f'### {t.stem}')
        try:
            stems = extract_inputs_coverage(
                t.read_text(encoding='utf-8', errors='replace'), report_stems
            )
        except OSError:
            stems = []
        lines += [f'- covers: `{s}`' for s in stems] or ['- (no Inputs / Addendum coverage parsed)']
        lines.append('')
        covered.update(stems)
    untriaged = [s for s in report_stems if s not in covered]
    lines += ['### Untriaged', '']
    lines += [f'- `{s}`' for s in untriaged] or ['- (none)']
    lines.append('')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    # Piped Windows stdout defaults to cp1252; the docstring and report excerpts
    # carry em-dashes, which mojibake in UTF-8 terminals. Emit UTF-8 regardless
    # of the platform default (in-process callers redirecting stdout to a
    # StringIO lack `reconfigure` and are left untouched).
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    force = '--force' in argv
    argv = [a for a in argv if a != '--force']
    if not argv:
        print('usage: build_feedback_index.py <feedback-dir> [--force]')
        return 2
    d = Path(argv[0])
    if not d.is_dir():
        print(f'not a directory: {d}')
        return 1
    out = d / 'INDEX.md'
    try:
        old = out.read_text(encoding='utf-8', errors='replace') if out.is_file() else ''
    except OSError:
        old = ''
    running = _plugin_version()
    if not force:
        newer = downgrade_blocker(old, running)
        if newer:
            print(
                f'refusing to write {out}: it was built by session-workflow {newer} and '
                f'this copy is {running}. An older builder overwriting a newer index is a '
                f'silent structural downgrade. Re-run from the {newer} copy, or pass '
                f'--force to roll back on purpose.'
            )
            return 3
    new = build_index(d)
    out.write_text(new, encoding='utf-8')
    print(f'wrote {out}: {delta_line(old, new)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

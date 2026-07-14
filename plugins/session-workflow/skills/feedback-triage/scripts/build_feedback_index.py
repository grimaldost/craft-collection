#!/usr/bin/env python3
"""Rebuild a feedback dir's INDEX.md — one section per report with its numbered
proposal titles — so an `extends`-lookup during capture (tool-feedback) or triage
(feedback-triage) is one Read instead of N speculative, phrasing-fragile greps (the
recurrence-grep robustness fix). Stdlib only; best-effort parsing of the report
template's "## Proposed promotions" section. The output (INDEX.md) is a generated
artifact — regenerate it, do not hand-edit.

    uv run --no-project python build_feedback_index.py <feedback-dir>

Use `uv run --no-project python` (not a bare `python` / `python3`): on Windows
without Python on PATH, both resolve to the Microsoft-Store app-execution stub
and abort.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

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
_SEVERITY = re.compile(r'\*\*\[[A-Za-z0-9/-]+\]\*\*\s*')


def extract_proposals(text: str) -> list[tuple[str, str]]:
    """Return [(number, title)] from the report's "## Proposed promotions" section.
    Only flush-left numbered lines outside fenced code blocks count; indented sub-lists
    and fenced numbered lines are ignored. The title is stripped of a leading severity
    tag and capped; parsing stops at the next `## ` heading. Best-effort: a report
    without the section yields []."""
    out: list[tuple[str, str]] = []
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
                title = _SEVERITY.sub('', m.group(2)).strip()
                out.append((m.group(1), title[:140]))
    return out


# Flush-left bullets under `## Misses` / `## Friction` become §-stub entries: the
# capture/triage skills sanction `extends <stem> §Misses` as a recurrence target,
# so those sections must be greppable in the index, not only `## Proposed`.
_BULLET = re.compile(r'^-\s+(.+?)\s*$')
_STUB_SECTIONS = ('misses', 'friction')


def extract_section_bullets(text: str) -> list[tuple[str, str]]:
    """Return [(SectionName, bullet)] for flush-left `- ` bullets under the
    `## Misses` / `## Friction` sections — the §-stub twins of extract_proposals.
    Fence-aware; indented sub-bullets ignored; severity tag stripped; capped."""
    out: list[tuple[str, str]] = []
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
                out.append((section, _SEVERITY.sub('', m.group(1)).strip()[:140]))
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


def build_index(feedback_dir: Path) -> str:
    reports = sorted(p for p in feedback_dir.glob('*.md') if _is_report(p))
    triage_docs = sorted(
        p for p in feedback_dir.glob('*.md') if p.name.lower() != 'index.md' and _is_triage_doc(p)
    )
    lines = [
        '# Feedback index',
        '',
        f'{len(reports)} report(s) — generated by build_feedback_index.py '
        f'(session-workflow {_plugin_version()}, {DETECTION_RULE}); do not hand-edit. '
        'Each entry is a report stem with its numbered proposals and its '
        '§Misses/§Friction bullet stubs; grep here for an `extends` target before '
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
            lines += [f'- `{p.stem}#{num}` — {title}' for num, title in props]
        elif not stubs:
            lines.append('- (no numbered proposals)')
        lines += [f'- `{p.stem} §{sec}` — {title}' for sec, title in stubs]
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
    if not argv:
        print('usage: build_feedback_index.py <feedback-dir>')
        return 2
    d = Path(argv[0])
    if not d.is_dir():
        print(f'not a directory: {d}')
        return 1
    out = d / 'INDEX.md'
    out.write_text(build_index(d), encoding='utf-8')
    print(f'wrote {out}')  # the index header carries the report count
    return 0


if __name__ == '__main__':
    sys.exit(main())

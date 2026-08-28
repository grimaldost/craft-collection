#!/usr/bin/env python3
"""Audit a triage corpus: assert a doc's coverage, and read the open-row set.

Two readings a triage pass currently performs from memory, and gets wrong.

**coverage** -- every finding of every report a doc names under `## Inputs` must
appear in that doc under some disposition. The section doubles as the input list
and as the coverage claim, so an author who names a report there has closed it;
if the doc never dispositions its findings, they leave the loop by omission. Two
consecutive passes shipped drafts with exactly that defect and both were caught
by luck: once by a step-7 rebuild written to catch the opposite failure, once by
a reader noticing an unrelated line. The most recent pass asserted coverage by
hand across seventeen reports against 1,238 indexed findings.

**open-rows** -- every promotion row any triage doc has ever proposed, with the
status the newest doc gives it. Rows orphan: a whole document's rows were never
carried into the next doc and four sat unbuilt for five weeks, and a later pass
DECLINED three findings for want of a home that was already a promoted row it
could not see. Grounding against source answers "is it there?"; it cannot answer
"was this already decided?", and only the row set can.

    python triage_audit.py coverage <triage-doc> [feedback-dir]
    python triage_audit.py open-rows [feedback-dir]

Exit 0 when clean, 1 on findings (coverage) -- open-rows is a read and exits 0
unless the corpus cannot be read. Stdlib only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_feedback_index import (
    _is_report,
    _is_triage_doc,
    extract_inputs_coverage,
    extract_proposals,
    extract_section_bullets,
)

# A promotion row in a cluster table: `| T58a | ... | ... | ... | proposed |`.
# Row ids are minted by the triage pass (T<n><letter>); report finding ids are a
# different namespace and are deliberately not matched here.
_ROW = re.compile(r'^\|\s*(T\d+[a-z]?)\s*\|(.+)\|\s*([A-Za-z][A-Za-z0-9_.()\- ]*?)\s*\|\s*$')
_OPEN_STATUSES = ('proposed', 'watch', 'accepted')


def report_stems(feedback_dir: Path) -> list[str]:
    return sorted(p.stem for p in feedback_dir.glob('*.md') if _is_report(p))


def finding_ids(report: Path) -> list[str]:
    """Every finding id a report declares: numbered proposals and the section
    stubs the capture and triage skills sanction as `extends` targets."""
    text = report.read_text(encoding='utf-8', errors='replace')
    ids = [f'{report.stem}#{p.number}' for p in extract_proposals(text)]
    # The section sign is part of the finding-id format the index defines and
    # matches on, so it cannot be substituted; main() forces UTF-8 on stdout for
    # the same reason anchor_inject.py does.
    sep = ' §'  # ascii-ok: index finding-id format
    ids += [f'{report.stem}{sep}{s.section}' for s in extract_section_bullets(text)]
    seen: set[str] = set()
    out = []
    for ref in ids:
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return out


def uncovered(doc: Path, feedback_dir: Path) -> tuple[list[str], list[str]]:
    """(stems the doc claims to close, finding ids it never mentions)."""
    text = doc.read_text(encoding='utf-8', errors='replace')
    stems = extract_inputs_coverage(text, report_stems(feedback_dir))
    missing = []
    for stem in stems:
        for ref in finding_ids(feedback_dir / f'{stem}.md'):
            # A doc may write the id with or without backticks, and may compress
            # a section ref. Match the whole id; the coverage claim is exact by
            # design, because a fuzzy match is how a stem fragment reads as
            # covered when nothing dispositioned it.
            if ref not in text:
                missing.append(ref)
    return stems, missing


def rows_in(doc: Path) -> list[tuple[str, str]]:
    """(row id, status) pairs a triage doc declares, in document order."""
    out = []
    for line in doc.read_text(encoding='utf-8', errors='replace').splitlines():
        match = _ROW.match(line.strip())
        if match:
            out.append((match.group(1), match.group(3).strip()))
    return out


def open_rows(feedback_dir: Path) -> list[tuple[str, str, str]]:
    """(row id, latest status, the doc that set it) for every row still open.

    Docs are read oldest-first by filename, so the newest mention of a row wins
    -- which is the rule the delta form already states in prose and no pass has
    been able to apply without re-reading every document."""
    latest: dict[str, tuple[str, str]] = {}
    for doc in sorted(p for p in feedback_dir.glob('*.md') if _is_triage_doc(p)):
        for row_id, status in rows_in(doc):
            latest[row_id] = (status, doc.stem)
    return sorted(
        (row_id, status, source)
        for row_id, (status, source) in latest.items()
        if status.lower().startswith(_OPEN_STATUSES)
    )


def _row_sort_key(row: tuple[str, str, str]) -> tuple[int, str]:
    match = re.match(r'^T(\d+)([a-z]?)$', row[0])
    return (int(match.group(1)), match.group(2)) if match else (0, row[0])


def cmd_emit(doc: Path, feedback_dir: Path) -> int:
    """Print the coverage checklist for a doc's Inputs, ready to annotate.

    The claim has to carry FULL finding ids to be checkable -- an abbreviated
    stem is exactly the fragmentation that already reads as zero coverage to the
    index parser. Sixty-one ids is not something to retype from memory, which is
    how the hand-written version came to be unverifiable, so the list is read out
    of the index instead."""
    text = doc.read_text(encoding='utf-8', errors='replace')
    stems = extract_inputs_coverage(text, report_stems(feedback_dir))
    for stem in stems:
        for ref in finding_ids(feedback_dir / f'{stem}.md'):
            print(f'- `{ref}` -> ')
    return 0


def cmd_coverage(doc: Path, feedback_dir: Path) -> int:
    if not _is_triage_doc(doc):
        print(f'error: {doc.name} has no `# Triage` H1 - not a triage doc', file=sys.stderr)
        return 1
    stems, missing = uncovered(doc, feedback_dir)
    if not stems:
        print(f'error: {doc.name} names no known report under `## Inputs`', file=sys.stderr)
        return 1
    for ref in missing:
        print(f'  uncovered: {ref}')
    if missing:
        print(
            f'FAIL: {len(missing)} finding(s) across {len(stems)} claimed report(s) have no '
            'disposition in the doc. Name each one, or move its report out of `## Inputs`.'
        )
        return 1
    print(f'ok: every finding of the {len(stems)} report(s) claimed under `## Inputs` is named')
    return 0


def cmd_open_rows(feedback_dir: Path) -> int:
    rows = sorted(open_rows(feedback_dir), key=_row_sort_key)
    if not rows:
        print('no open rows')
        return 0
    width = max(len(r[0]) for r in rows)
    for row_id, status, source in rows:
        print(f'  {row_id.ljust(width)}  {status:<9}  set by {source}')
    print(f'{len(rows)} open row(s)')
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Finding ids carry a section sign; a cp1252 console would raise on the way
    # out and lose the whole report.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    emit = '--emit' in argv
    argv = [a for a in argv if a != '--emit']
    if not argv or argv[0] not in ('coverage', 'open-rows'):
        print(
            'usage: triage_audit.py {coverage [--emit] <doc> | open-rows} [feedback-dir]',
            file=sys.stderr,
        )
        return 2
    if argv[0] == 'coverage':
        if len(argv) < 2:
            print('error: name the triage doc to check', file=sys.stderr)
            return 2
        doc = Path(argv[1])
        feedback_dir = Path(argv[2]) if len(argv) > 2 else doc.parent
        if not doc.is_file():
            print(f'error: no such doc: {doc}', file=sys.stderr)
            return 2
        return cmd_emit(doc, feedback_dir) if emit else cmd_coverage(doc, feedback_dir)
    feedback_dir = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    if not feedback_dir.is_dir():
        print(f'error: no such feedback dir: {feedback_dir}', file=sys.stderr)
        return 2
    return cmd_open_rows(feedback_dir)


if __name__ == '__main__':
    sys.exit(main())

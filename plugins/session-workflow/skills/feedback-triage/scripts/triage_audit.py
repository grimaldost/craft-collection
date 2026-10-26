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

coverage also fails a ROUTE OUT that was never delivered. A routed finding leaves
this tool's loop, so it is closed only when a report exists in the target's
feedback dir: each routed row names that report's path, absolute or relative to
the registered `feedback_dir` of a target the row names (every registered dir
when it names none; `$FEEDBACK_TARGETS_FILE`, else
`~/.claude/feedback-targets.toml`), and a row none of whose paths exists fails.
A routed row is a bullet or table row under `## Routed out` (a bullet that opens
"Nothing" or "None" routes nothing), a cluster heading whose disposition says
ROUTE OUT (with the body up to the next heading), or a `T<n>` row whose status
opens "routed" or "route out". Route-outs used to be recorded in the triage doc
only, where the target's own loop never reads them.

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

import os
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
#
# The status cell takes anything but a pipe. A narrower character class dropped
# every QUALIFIED status -- `watch - pending a second measurement` -- which is
# the exact shape the skill's own `watch` rule asks for ("a row whose sole
# evidence is one measured wave names the replication it is pending"). A reader
# of open rows that silently loses the rows most likely to be forgotten is worse
# than no reader at all.
_ROW = re.compile(r'^\|\s*(T\d+[a-z]?)\s*\|(.+)\|\s*([A-Za-z][^|]*?)\s*\|\s*$')
_OPEN_STATUSES = ('proposed', 'watch', 'accepted')

# A table row keyed by another prefix (`SW26`, `E3`, `Q6b`, ...). open-rows does not
# read these -- that waits for the ledger (T48a) -- but it counts them, so a doc
# that keeps its rows under other ids is reported as partly unread, not as empty
# (T309a).
_OTHER_ROW = re.compile(r'^\|\s*(?!T\d)[A-Z]{1,4}\d+[a-z]?\s*\|')
_SUCCESSOR = re.compile(r'T\d+[a-z]?')


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


def rows_in(doc: Path) -> list[tuple[str, str, str]]:
    """(row id, description, status) triples a triage doc declares, in document
    order. `description` is the row's own middle cells (proposed promotion, fix
    shape, home) verbatim -- it is never displayed, only compared, so a row
    reused under the same id can be told apart from a genuine restatement of
    the same row (T94b)."""
    out = []
    for line in doc.read_text(encoding='utf-8', errors='replace').splitlines():
        match = _ROW.match(line.strip())
        if match:
            out.append((match.group(1), match.group(2).strip(), match.group(3).strip()))
    return out


# Where row ids are known to be unique, and from which number. craft-collection's
# triage passes minted a local `T1a`, `T2a`, ... per doc until T67; from T67 on
# the numbering is shared, so an id is one row however a later doc words it.
# Another tool's feedback dir has its own numbering (convoy, fathom, keel and
# mantis-research each re-mint per doc, and none had reached T67 when this was written), so a corpus
# not listed here keeps the (id, description) keying throughout.
_UNIQUE_IDS_FROM = {'craft-collection': 67}


def _row_number(row_id: str) -> int:
    return int(re.findall(r'\d+', row_id)[0])


def open_rows(feedback_dir: Path) -> list[tuple[str, str, str]]:
    """(row id, latest status, the doc that set it) for every row still open.

    A row's identity depends on how its id was minted. In the craft-collection
    namespace, ids are globally unique from T67 on (`_UNIQUE_IDS_FROM`): the id
    alone names the row, so a later doc that restates it under shorter or
    reworded text, or a doc that states it twice, updates that one row and the
    newest status wins -- the rule the delta form states in prose ("a row named
    in a table below takes the status given here"). Keyed by description there,
    every rewording was a separate lineage and the older, open one never closed
    (T94c; measured: 426 open lineages in a corpus whose real open set is far
    smaller). One exception, id-keyed mode only: a later statement whose status
    begins `superseded` and names no successor id (no `T<n>` in the cell) does not
    overwrite an existing lineage, because a row superseded for an old wording
    only is not closed; `superseded by T263a` closes it (T309b).

    Below that cut, and in every other feedback dir, each triage pass re-minted
    its own local `T1a`, `T2a`, ... -- so the same bare id can name two unrelated
    rows from two unrelated docs, not one row restated. Keying purely by id let a
    later doc's unrelated row silently replace an earlier doc's still-open one
    (T94b; measured: 2026-06-09 and 2026-06-13's distinct, both-`proposed` T1a
    rows were both hidden behind 2026-07-23's T1a). There a row is tracked per
    (id, description): the same id with the same description is one row and the
    later status wins; a changed description under a repeated id is read as a
    distinct row, set by whichever doc most recently stated it, rather than
    assumed to be a reworded carry. That doubt is left for the reconciliation
    read rather than resolved by guessing here."""
    unique_from = _UNIQUE_IDS_FROM.get(feedback_dir.resolve().name)
    lineages: dict[tuple[str, str], dict[str, str]] = {}
    for doc in sorted(p for p in feedback_dir.glob('*.md') if _is_triage_doc(p)):
        for row_id, description, status in rows_in(doc):
            unique = unique_from is not None and _row_number(row_id) >= unique_from
            key = (row_id, '' if unique else description)
            if (
                unique
                and key in lineages
                and status.lower().startswith('superseded')
                and not _SUCCESSOR.search(status)
            ):
                continue
            lineages[key] = {'status': status, 'doc': doc.stem}
    return sorted(
        (row_id, lineage['status'], lineage['doc'])
        for (row_id, _), lineage in lineages.items()
        if lineage['status'].lower().startswith(_OPEN_STATUSES)
    )


def unread_row_counts(feedback_dir: Path) -> list[tuple[str, int]]:
    """(doc stem, count) for each triage doc holding table rows keyed by a
    non-T prefix, which `rows_in` does not read."""
    out = []
    for doc in sorted(p for p in feedback_dir.glob('*.md') if _is_triage_doc(p)):
        lines = doc.read_text(encoding='utf-8', errors='replace').splitlines()
        count = sum(1 for line in lines if _OTHER_ROW.match(line.strip()))
        if count:
            out.append((doc.stem, count))
    return out


def _row_sort_key(row: tuple[str, str, str]) -> tuple[int, str]:
    match = re.match(r'^T(\d+)([a-z]?)$', row[0])
    return (int(match.group(1)), match.group(2)) if match else (0, row[0])


def cmd_emit(doc: Path, feedback_dir: Path) -> int:
    """Print the coverage checklist for a doc's Inputs, ready to annotate.

    The claim has to carry FULL finding ids to be checkable -- `uncovered`
    matches whole ids, so an abbreviated one reads as undispositioned. Sixty-one
    ids is not something to retype from memory, which is how the hand-written
    version came to be unverifiable, so the list is read out of the index
    instead."""
    text = doc.read_text(encoding='utf-8', errors='replace')
    stems = extract_inputs_coverage(text, report_stems(feedback_dir))
    for stem in stems:
        for ref in finding_ids(feedback_dir / f'{stem}.md'):
            print(f'- `{ref}` -> ')
    return 0


_TARGET_HEADER = re.compile(r'^\s*\[targets\.([^\]]+)\]\s*$')
_FEEDBACK_DIR = re.compile(r'^\s*feedback_dir\s*=\s*[\'"](.+?)[\'"]\s*$')
_FENCE = re.compile(r'^\s*(```|~~~)')
_ROUTED_SECTION = re.compile(r'^##\s+routed\s+out\b', re.IGNORECASE)
_ROUTE_OUT_HEADING = re.compile(r'^#{3,4}\s.*\broute[ds]?[\s-]+out\b', re.IGNORECASE)
_ROUTED_STATUS = re.compile(r'^rout(?:ed|e)[\s-]+out\b|^routed\b', re.IGNORECASE)
_NOTHING_ROUTED = re.compile(r'^[-*\s]*(?:nothing|none)\b', re.IGNORECASE)
_TABLE_RULE = re.compile(r'^\|[\s:|-]+\|$')
# Path candidates in a row: a backticked span, a markdown link target, or a bare
# token ending in `.md`. A finding id or a prose word is never a path (no `.md`,
# no separator), so it is never tried.
_CANDIDATE = re.compile(r'`([^`\n]+)`|\]\(([^)\s]+)\)|(\S+\.md)\b')


def registered_feedback_dirs(targets: Path | None = None) -> dict[str, Path]:
    """{target name: feedback dir} from the feedback-targets file, line-parsed as
    the tool-feedback nudge parses it (no TOML library needed)."""
    if targets is None:
        override = os.environ.get('FEEDBACK_TARGETS_FILE')
        targets = Path(override) if override else Path.home() / '.claude' / 'feedback-targets.toml'
    out: dict[str, Path] = {}
    name = None
    try:
        lines = targets.read_text(encoding='utf-8').splitlines()
    except OSError:
        return {}
    for line in lines:
        header = _TARGET_HEADER.match(line)
        if header:
            name = header.group(1).strip()
            continue
        found = _FEEDBACK_DIR.match(line) if name else None
        if found:
            out[name] = Path(found.group(1))
    return out


def routed_rows(text: str) -> list[str]:
    """The ROUTE OUT rows of a triage doc, each as its own text (see the module
    docstring for the three shapes). Fence-aware."""
    rows: list[list[str]] = []
    block: list[str] | None = None  # a ROUTE OUT cluster: every line to the next heading
    item: list[str] | None = None  # a Routed-out bullet and its indented continuation
    header: str | None = None
    in_routed = in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        fence = bool(_FENCE.match(line))
        in_fence = in_fence != fence
        if in_fence or fence:
            for target in (block, item):
                if target is not None:
                    target.append(stripped)
            continue
        if stripped.startswith('#'):
            block = item = None
            in_routed = bool(_ROUTED_SECTION.match(stripped))
            if _ROUTE_OUT_HEADING.match(stripped):
                block = [stripped]
                rows.append(block)
            continue
        if block is not None:
            block.append(stripped)
        row = _ROW.match(stripped)
        if row and _ROUTED_STATUS.match(row.group(3)) and block is None:
            rows.append([stripped])
            continue
        if not in_routed:
            continue
        if _TABLE_RULE.match(stripped):
            if rows and rows[-1] == [header]:
                rows.pop()  # the row above a table rule is the table's header
            continue
        if stripped.startswith(('- ', '|')):
            header = stripped
            item = None if _NOTHING_ROUTED.match(stripped[1:]) else [stripped]
            if item is not None:
                rows.append(item)
        elif item is not None and stripped and line[:1].isspace():
            item.append(stripped)
        else:
            item = None
    return ['\n'.join(r) for r in rows]


def _delivered(row: str, dirs: dict[str, Path]) -> bool:
    named = [d for name, d in dirs.items() if re.search(rf'\b{re.escape(name)}\b', row)]
    bases = named or list(dirs.values())
    for m in _CANDIDATE.finditer(row):
        raw = (m.group(1) or m.group(2) or m.group(3) or '').strip()
        if not raw or not (raw.endswith('.md') or '/' in raw or '\\' in raw):
            continue
        path = Path(raw).expanduser()
        try:
            if path.is_absolute():
                if path.is_file():
                    return True
                continue
            if any((base / path).is_file() for base in bases):
                return True
        except OSError:
            continue
    return False


def undelivered_route_outs(doc_text: str, dirs: dict[str, Path] | None = None) -> list[str]:
    """The routed rows of a triage doc none of whose paths names an existing report."""
    dirs = registered_feedback_dirs() if dirs is None else dirs
    return [row for row in routed_rows(doc_text) if not _delivered(row, dirs)]


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
    undelivered = undelivered_route_outs(doc.read_text(encoding='utf-8', errors='replace'))
    for row in undelivered:
        print(f'  undelivered route-out: {row.splitlines()[0][:160]}')
    if missing:
        print(
            f'FAIL: {len(missing)} finding(s) across {len(stems)} claimed report(s) have no '
            'disposition in the doc. Name each one, or move its report out of `## Inputs`.'
        )
    if undelivered:
        print(
            f'FAIL: {len(undelivered)} route-out(s) name no delivered report. Write a short '
            "report into the target's feedback dir and name its path in the row (absolute, "
            "or relative to the target's registered feedback_dir)."
        )
    if missing or undelivered:
        return 1
    print(f'ok: every finding of the {len(stems)} report(s) claimed under `## Inputs` is named')
    return 0


def cmd_open_rows(feedback_dir: Path) -> int:
    for stem, count in unread_row_counts(feedback_dir):
        print(
            f'{stem}: {count} table row(s) with non-T ids not read (open-rows reads T ids only)',
            file=sys.stderr,
        )
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

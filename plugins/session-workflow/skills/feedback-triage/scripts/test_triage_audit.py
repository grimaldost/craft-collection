"""Tests for triage_audit.py.

Contract under test:
- coverage FAILS when a report named under `## Inputs` has a finding the doc
  never mentions -- the over-coverage direction, which is how a report gets
  closed without being dispositioned;
- coverage PASSES when every finding id appears, in any surrounding prose;
- a stem named in Inputs but absent from the doc's body still fails, because
  naming a report there is what closes it - including a stem abbreviated with
  an ellipsis, which the index credits when it names one report;
- a doc with no `# Triage` H1 is not a triage doc;
- `--emit` prints one line per finding, so the claim is read rather than typed;
- open-rows reports the newest status per row and names the doc that set it;
- a row later restated as shipped/declined leaves the open set;
- from T67 on, in the craft-collection namespace only, a row is keyed by its id
  alone: a reworded restatement or a same-doc repeat is one row (T94c).

The red proof is `test_an_undispositioned_finding_reddens_coverage`: it seeds the
observed defect -- a report named under Inputs whose findings the doc never
mentions -- and watches the check exit 1.

Stdlib-runnable: `python test_triage_audit.py`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import triage_audit as ta

SCRIPT = Path(__file__).resolve().parent / 'triage_audit.py'

REPORT = """# demo feedback

## Friction

- **[LOW]** something rubbed.

## Proposed promotions / changes

1. **[MED]** first proposal.
2. **[LOW]** second proposal.
"""


def _corpus(root: Path, doc_body: str) -> tuple[Path, Path]:
    (root / 'r-one.md').write_text(REPORT, encoding='utf-8')
    doc = root / '2026-01-01-triage-demo.md'
    doc.write_text(doc_body, encoding='utf-8')
    return doc, root


def run_cli(*args: str):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        encoding='utf-8',
        timeout=60,
    )


COVERED = """# Triage - demo

## Inputs

- `r-one`

## Clusters

`r-one#1` -> T1a, `r-one#2` -> declined, `r-one §Friction` -> T1b.
"""

UNCOVERED = """# Triage - demo

## Inputs

- `r-one`

## Clusters

Nothing here disposes of anything.
"""


def test_covered_doc_passes():
    with tempfile.TemporaryDirectory() as d:
        doc, root = _corpus(Path(d), COVERED)
        proc = run_cli('coverage', str(doc), str(root))
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_an_undispositioned_finding_reddens_coverage():
    # THE RED PROOF. A report named under `## Inputs` is credited as covered by
    # the index builder; if the doc never dispositions its findings they leave
    # the loop by omission. Two consecutive passes shipped this defect.
    with tempfile.TemporaryDirectory() as d:
        doc, root = _corpus(Path(d), UNCOVERED)
        proc = run_cli('coverage', str(doc), str(root))
        assert proc.returncode == 1
        assert 'r-one#1' in proc.stdout
        assert 'r-one#2' in proc.stdout
        assert 'Friction' in proc.stdout


def test_a_partially_dispositioned_report_still_fails():
    with tempfile.TemporaryDirectory() as d:
        body = COVERED.replace('`r-one#2` -> declined, ', '')
        doc, root = _corpus(Path(d), body)
        proc = run_cli('coverage', str(doc), str(root))
        assert proc.returncode == 1
        assert 'r-one#2' in proc.stdout
        assert 'r-one#1' not in proc.stdout, 'a dispositioned finding must not be reported'


def test_a_report_closed_by_an_abbreviated_stem_is_still_audited():
    # The index credits `...one` (date elided, one report matches) as covered, so
    # the audit must see the same claim: a report closed by abbreviation whose
    # findings the doc never dispositions has to redden, not slip past.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '2026-01-01-r-one.md').write_text(REPORT, encoding='utf-8')
        doc = root / '2026-01-02-triage-demo.md'
        doc.write_text(
            f'# Triage - demo\n\n## Inputs\n\n- `{chr(0x2026)}r-one`\n\n## Clusters\n\nnothing.\n',
            encoding='utf-8',
        )
        proc = run_cli('coverage', str(doc), str(root))
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert '2026-01-01-r-one#1' in proc.stdout


def test_a_doc_without_a_triage_h1_is_refused():
    with tempfile.TemporaryDirectory() as d:
        doc, root = _corpus(Path(d), COVERED.replace('# Triage - demo', '# demo feedback'))
        proc = run_cli('coverage', str(doc), str(root))
        assert proc.returncode == 1
        assert 'Triage' in proc.stderr


def test_emit_lists_every_finding_once():
    with tempfile.TemporaryDirectory() as d:
        doc, root = _corpus(Path(d), UNCOVERED)
        proc = run_cli('coverage', '--emit', str(doc), str(root))
        assert proc.returncode == 0
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert len(lines) == 3
        assert all(ln.startswith('- `r-one') for ln in lines)


OLD_DOC = """# Triage - old

| # | proposed promotion | fix shape | home | status |
|---|---|---|---|---|
| T1a | a thing | prose | somewhere | proposed |
| T1b | another | mechanize | elsewhere | watch |
| T2a | done one | prose | here | proposed |
"""

NEW_DOC = """# Triage - new

| # | proposed promotion | fix shape | home | status |
|---|---|---|---|---|
| T2a | done one | prose | here | shipped(0.3.0) |
| T3a | fresh | prose | here | proposed |
"""


def test_open_rows_takes_the_newest_status_and_names_its_doc():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '2026-01-01-triage-old.md').write_text(OLD_DOC, encoding='utf-8')
        (root / '2026-02-01-triage-new.md').write_text(NEW_DOC, encoding='utf-8')
        rows = {r[0]: (r[1], r[2]) for r in ta.open_rows(root)}
        assert rows['T1a'] == ('proposed', '2026-01-01-triage-old')
        assert rows['T1b'] == ('watch', '2026-01-01-triage-old')
        assert rows['T3a'] == ('proposed', '2026-02-01-triage-new')
        assert 'T2a' not in rows, 'a row restated as shipped leaves the open set'


def test_open_rows_cli_reports_the_count():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '2026-01-01-triage-old.md').write_text(OLD_DOC, encoding='utf-8')
        proc = run_cli('open-rows', str(root))
        assert proc.returncode == 0
        assert '3 open row(s)' in proc.stdout
        assert 'T1a' in proc.stdout


COLLISION_DOC_A = """# Triage - collision-a

| # | proposed promotion | fix shape | home | status |
|---|---|---|---|---|
| T1a | verify a subagent's completion claim | prose | here | proposed |
"""

COLLISION_DOC_B = """# Triage - collision-b

| # | proposed promotion | fix shape | home | status |
|---|---|---|---|---|
| T1a | a fabricated telemetry failure mode | prose | here | proposed |
"""


def test_a_bare_id_reused_by_an_unrelated_doc_does_not_mask_the_earlier_row():
    # THE RED PROOF for T94b. Before ids became globally unique (T67), each
    # triage pass re-minted its own local `T1a`, `T2a`, ... for unrelated rows.
    # Keying `open_rows` by the bare id alone let a later doc's unrelated `T1a`
    # silently replace an earlier doc's still-open `T1a` -- exactly the failure
    # measured against the real corpus (2026-06-09 and 2026-06-13's T1a rows,
    # both `proposed`, hidden behind 2026-07-23's T1a). Both rows are genuinely
    # open and distinct (different description text under the same id), so both
    # must surface, each naming the doc that set it.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '2026-06-09-triage-craft-collection.md').write_text(
            COLLISION_DOC_A, encoding='utf-8'
        )
        (root / '2026-06-13-triage-craft-collection.md').write_text(
            COLLISION_DOC_B, encoding='utf-8'
        )
        rows = ta.open_rows(root)
        t1a_rows = [r for r in rows if r[0] == 'T1a']
        sources = {r[2] for r in t1a_rows}
        assert sources == {
            '2026-06-09-triage-craft-collection',
            '2026-06-13-triage-craft-collection',
        }, 'a bare id reused by an unrelated doc must not mask the earlier row'
        assert len(t1a_rows) == 2, 'both unrelated T1a rows must surface, not just the newest'


def _doc(rows: str) -> str:
    return (
        '# Triage - demo\n\n'
        '| # | proposed promotion | fix shape | home | status |\n'
        '|---|---|---|---|---|\n' + rows
    )


# A post-T67 row proposed under a long wording, then restated by a later doc under
# shorter text with a closed status -- the shape the real corpus has 22 times.
LONG_WORDING = '| T70a | `plugin_version.py` globs the parent and reports every copy | mechanize | x | proposed |\n'
SHORT_WORDING = '| T70a | `plugin_version.py` names every copy | mechanize | x | shipped(0.1.0) |\n'


def _namespace_corpus(root: Path, name: str, first: str, second: str) -> Path:
    corpus = root / name
    corpus.mkdir()
    (corpus / '2026-09-13-triage-a.md').write_text(_doc(first), encoding='utf-8')
    (corpus / '2026-09-19-triage-b.md').write_text(_doc(second), encoding='utf-8')
    return corpus


def test_a_post_t67_row_reworded_by_a_later_doc_leaves_the_open_set():
    # THE RED PROOF for T94c. From T67 on, craft-collection row ids are globally
    # unique, so the same id is the same row however a later doc words it. Keyed
    # by (id, description), the long proposed wording and the short shipped one
    # read as two rows and the long one stayed open for good -- the reader
    # listed 426 lineages for a corpus with far fewer open rows.
    with tempfile.TemporaryDirectory() as d:
        corpus = _namespace_corpus(Path(d), 'craft-collection', LONG_WORDING, SHORT_WORDING)
        assert [r for r in ta.open_rows(corpus) if r[0] == 'T70a'] == []


def test_a_post_t67_row_stated_twice_in_one_doc_counts_once():
    # Same defect, same-doc form: two wordings of one id in one doc were two
    # lineages. One id is one row; the later statement sets the status.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        corpus = root / 'craft-collection'
        corpus.mkdir()
        (corpus / '2026-09-13-triage-a.md').write_text(
            _doc(LONG_WORDING + LONG_WORDING.replace('globs the parent', 'scans the parent')),
            encoding='utf-8',
        )
        assert len([r for r in ta.open_rows(corpus) if r[0] == 'T70a']) == 1


def test_the_t67_cut_leaves_earlier_ids_keyed_by_description():
    # Below T67 ids were re-minted per doc, so a reworded id is not provably the
    # same row; the (id, description) keying of T94b stays in force there.
    with tempfile.TemporaryDirectory() as d:
        corpus = _namespace_corpus(
            Path(d),
            'craft-collection',
            LONG_WORDING.replace('T70a', 'T66a'),
            SHORT_WORDING.replace('T70a', 'T66a'),
        )
        assert [r[0] for r in ta.open_rows(corpus)] == ['T66a']


def test_the_t67_cut_is_scoped_to_the_craft_collection_namespace():
    # Another tool's feedback dir has its own id numbering, re-minted per doc;
    # a number past 66 there is not evidence of uniqueness. The same corpus
    # under a different directory name keeps the (id, description) keying.
    with tempfile.TemporaryDirectory() as d:
        corpus = _namespace_corpus(Path(d), 'other-tool', LONG_WORDING, SHORT_WORDING)
        assert [r[0] for r in ta.open_rows(corpus)] == ['T70a']


def test_open_rows_on_a_corpus_with_no_triage_docs():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / 'r-one.md').write_text(REPORT, encoding='utf-8')
        proc = run_cli('open-rows', str(root))
        assert proc.returncode == 0
        assert 'no open rows' in proc.stdout


def test_usage_error_without_a_mode():
    proc = run_cli()
    assert proc.returncode == 2
    assert 'usage' in proc.stderr


QUALIFIED_DOC = """# Triage - qualified

| # | proposed promotion | fix shape | home | status |
|---|---|---|---|---|
| T9a | plain | prose | here | watch |
| T9b | qualified with an em dash | prose | here | watch — pending a second measurement |
| T9c | qualified with a hyphen | prose | here | proposed - blocked on the keel row |
| T9d | shipped, qualified | prose | here | shipped(0.23.0) — landed in #127 |
"""


def test_a_qualified_status_is_still_an_open_row():
    # The skill's own `watch` rule asks a single-wave row to NAME the replication
    # it waits for, so the status cell routinely reads "watch - pending X". A
    # status pattern that only accepted bare words dropped exactly those rows --
    # the ones most likely to be forgotten -- and reported them as nothing.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '2026-01-01-triage-q.md').write_text(QUALIFIED_DOC, encoding='utf-8')
        rows = {r[0]: r[1] for r in ta.open_rows(root)}
        assert 'T9a' in rows
        assert 'T9b' in rows, 'an em-dash-qualified watch must not vanish'
        assert 'T9c' in rows, 'a hyphen-qualified proposed must not vanish'
        assert rows['T9b'].startswith('watch')
        assert 'T9d' not in rows, 'a qualified shipped status is still closed'


if __name__ == '__main__':
    test_covered_doc_passes()
    test_an_undispositioned_finding_reddens_coverage()
    test_a_partially_dispositioned_report_still_fails()
    test_a_report_closed_by_an_abbreviated_stem_is_still_audited()
    test_a_doc_without_a_triage_h1_is_refused()
    test_emit_lists_every_finding_once()
    test_open_rows_takes_the_newest_status_and_names_its_doc()
    test_a_bare_id_reused_by_an_unrelated_doc_does_not_mask_the_earlier_row()
    test_open_rows_cli_reports_the_count()
    test_a_post_t67_row_reworded_by_a_later_doc_leaves_the_open_set()
    test_a_post_t67_row_stated_twice_in_one_doc_counts_once()
    test_the_t67_cut_leaves_earlier_ids_keyed_by_description()
    test_the_t67_cut_is_scoped_to_the_craft_collection_namespace()
    test_open_rows_on_a_corpus_with_no_triage_docs()
    test_usage_error_without_a_mode()
    test_a_qualified_status_is_still_an_open_row()
    print('ok: all triage_audit tests passed')

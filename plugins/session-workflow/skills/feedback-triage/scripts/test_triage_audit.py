"""Tests for triage_audit.py.

Contract under test:
- coverage FAILS when a report named under `## Inputs` has a finding the doc
  never mentions -- the over-coverage direction, which is how a report gets
  closed without being dispositioned;
- coverage PASSES when every finding id appears, in any surrounding prose;
- a stem named in Inputs but absent from the doc's body still fails, because
  naming a report there is what closes it;
- a doc with no `# Triage` H1 is not a triage doc;
- `--emit` prints one line per finding, so the claim is read rather than typed;
- open-rows reports the newest status per row and names the doc that set it;
- a row later restated as shipped/declined leaves the open set.

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


if __name__ == '__main__':
    test_covered_doc_passes()
    test_an_undispositioned_finding_reddens_coverage()
    test_a_partially_dispositioned_report_still_fails()
    test_a_doc_without_a_triage_h1_is_refused()
    test_emit_lists_every_finding_once()
    test_open_rows_takes_the_newest_status_and_names_its_doc()
    test_open_rows_cli_reports_the_count()
    test_open_rows_on_a_corpus_with_no_triage_docs()
    test_usage_error_without_a_mode()
    print('ok: all triage_audit tests passed')

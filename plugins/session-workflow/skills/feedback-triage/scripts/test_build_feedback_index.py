"""Tests for build_feedback_index (pure parsing + render; no I/O on the real tree).
Runnable with pytest or `python test_build_feedback_index.py`."""

from __future__ import annotations

import tempfile
from pathlib import Path

from build_feedback_index import build_index, extract_proposals


def test_extract_proposals_pulls_numbered_titles():
    text = (
        '# report\n'
        '## Proposed promotions / changes\n'
        '1. **[MED]** First fix here. Home: x.\n'
        '2. **[LOW]** extends `foo#3` — second fix.\n'
        '## Cost\n'
        '3. not a proposal (outside the section)\n'
    )
    assert extract_proposals(text) == [
        ('1', 'First fix here. Home: x.'),
        ('2', 'extends `foo#3` — second fix.'),
    ]


def test_extract_proposals_empty_when_no_section():
    assert extract_proposals('# report\njust prose, no proposals\n') == []


def test_build_index_lists_reports_and_excludes_meta():
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-01-foo.md').write_text(
            '# foo\n## Proposed promotions / changes\n1. **[MED]** Do the thing.\n',
            encoding='utf-8',
        )
        (dd / '2026-01-02-bar.md').write_text('# bar\nno proposals here\n', encoding='utf-8')
        (dd / '2026-01-03-triage-x.md').write_text('# Triage — x\n', encoding='utf-8')  # excluded
        (dd / 'README.md').write_text('# readme\n', encoding='utf-8')  # excluded
        (dd / 'INDEX.md').write_text('# stale self\n', encoding='utf-8')  # excluded (self)
        idx = build_index(dd)
    assert '`2026-01-01-foo#1` — Do the thing.' in idx
    assert '## 2026-01-02-bar' in idx and 'no numbered proposals' in idx
    assert 'triage-x' not in idx  # triage docs/digests are outputs, not source reports
    assert 'stale self' not in idx  # the old INDEX.md is never indexed into itself


def test_misses_and_friction_indexed_as_section_stubs():
    # The capture/triage skills sanction `extends <stem> §Misses` as a recurrence
    # target — the index must surface Misses/Friction bullets, or that affordance
    # points at nothing greppable. Flush-left bullets only; fences ignored.
    text = (
        '# report\n'
        '## Friction\n'
        '- Setup took three tries.\n'
        '## Misses\n'
        '- **[MED]** The gate never fired on X.\n'
        '  - indented sub-bullet ignored\n'
        '```\n'
        '- fenced bullet ignored\n'
        '```\n'
        '## Proposed promotions / changes\n'
        '1. **[MED]** Fix the gate.\n'
    )
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-05-z.md').write_text(text, encoding='utf-8')
        idx = build_index(dd)
    assert '`2026-01-05-z#1` — Fix the gate.' in idx
    assert '`2026-01-05-z §Misses` — The gate never fired on X.' in idx
    assert '`2026-01-05-z §Friction` — Setup took three tries.' in idx
    assert 'indented sub-bullet' not in idx
    assert 'fenced bullet' not in idx


def test_build_index_excludes_consolidated_backlog():
    # A consolidated BACKLOG.md is a loop OUTPUT (a status digest), not a source
    # report -- excluded by exact name like INDEX.md / README.md. (Regression: it was
    # counted as a report, inflating the count and emitting a spurious '## BACKLOG'
    # section whenever a feedback dir keeps a consolidated backlog beside its reports.)
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-09-real.md').write_text(
            '# real feedback - z\n## Proposed promotions / changes\n1. **[MED]** x.\n',
            encoding='utf-8',
        )
        (dd / 'BACKLOG.md').write_text(
            '# pr-pilot backlog -- consolidated status\n## SHIPPED\n', encoding='utf-8'
        )
        idx = build_index(dd)
    assert '## 2026-01-09-real' in idx  # the one real report is indexed
    assert 'BACKLOG' not in idx  # the consolidated backlog is not a report
    assert '1 report' in idx  # counted as one report, not two


def test_build_index_handles_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        assert '0 report' in build_index(Path(d))


def test_build_index_survives_non_utf8_file():
    # A non-UTF-8 byte in one report must not abort the whole index (UnicodeDecodeError
    # is a ValueError, not OSError — read with errors='replace').
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-04-good.md').write_text(
            '# good\n## Proposed promotions\n1. **[MED]** ok.\n', encoding='utf-8'
        )
        (dd / '2026-01-05-bad.md').write_bytes(b'# bad\n\xff\xfe not utf-8\n')
        idx = build_index(dd)  # must not raise
    assert '`2026-01-04-good#1` — ok.' in idx
    assert '## 2026-01-05-bad' in idx  # the bad file is still listed, not a crash


def test_triage_named_input_report_is_indexed():
    # A legitimate input report whose SLUG contains 'triage' — a tool-feedback report
    # ABOUT feedback-triage, or a '<date>-triage-round-<tool>' wave — opens with a
    # '# <tool> feedback' H1 and must still be indexed. (Regression: the old substring
    # filter silently dropped these, incl. 2026-06-14-feedback-triage-batch-run.md.)
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-06-triage-round-foo.md').write_text(
            '# foo feedback — bar\n## Proposed promotions / changes\n1. **[MED]** Do it.\n',
            encoding='utf-8',
        )
        idx = build_index(dd)
    assert '## 2026-01-06-triage-round-foo' in idx  # indexed despite 'triage' in the name
    assert '`2026-01-06-triage-round-foo#1` — Do it.' in idx


def test_triage_doc_detected_by_h1_not_filename():
    # A triage doc is identified by its '# Triage' H1, not its filename — so a file
    # WITHOUT 'triage' in the name but WITH a '# Triage' H1 is still excluded.
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-07-weekly-summary.md').write_text(
            '# Triage — craft backlog\n## Proposed promotions / changes\n1. **[MED]** x.\n',
            encoding='utf-8',
        )
        (dd / '2026-01-08-real.md').write_text('# real feedback — y\n', encoding='utf-8')
        idx = build_index(dd)
    assert 'weekly-summary' not in idx  # excluded by its '# Triage' H1, not its name
    assert '## 2026-01-08-real' in idx


def test_extract_proposals_ignores_nested_and_fenced_numbers():
    # A proposal body may contain an indented numbered sub-list and a fenced code
    # block with numbered lines; neither may mint a phantom finding ID. Only the two
    # flush-left `1.`/`2.` top-level proposals are real. (Regression: `^\s*` matched
    # any indented number, and the parser was fence-unaware, so `foo#1` mapped to two
    # titles and `foo#3`/`foo#4` phantoms appeared.)
    text = (
        '# report\n'
        '## Proposed promotions / changes\n'
        '1. **[MED]** First real proposal.\n'
        '   Sub-steps for the first:\n'
        '   1. an indented sub-item (not a proposal)\n'
        '   2. another indented sub-item\n'
        '   ```python\n'
        '   1. this looks numbered but is inside a fence\n'
        '   ```\n'
        '2. **[LOW]** Second real proposal.\n'
        '## Cost\n'
    )
    assert extract_proposals(text) == [
        ('1', 'First real proposal.'),
        ('2', 'Second real proposal.'),
    ]


def test_extract_proposals_strips_digit_hyphen_severity_tag():
    # The severity tag charset must strip digit/hyphen forms like **[P1]** and
    # **[P2-HIGH]**, not only alpha ones like **[MED]**. (Regression: `[A-Za-z/]+`
    # left the whole `**[P1]**` glued to the title.)
    text = (
        '# report\n'
        '## Proposed promotions\n'
        '1. **[P1]** Priority-one fix.\n'
        '2. **[P2-HIGH]** Another tagged fix.\n'
    )
    assert extract_proposals(text) == [
        ('1', 'Priority-one fix.'),
        ('2', 'Another tagged fix.'),
    ]


if __name__ == '__main__':
    test_extract_proposals_pulls_numbered_titles()
    test_extract_proposals_empty_when_no_section()
    test_build_index_lists_reports_and_excludes_meta()
    test_misses_and_friction_indexed_as_section_stubs()
    test_build_index_excludes_consolidated_backlog()
    test_build_index_handles_empty_dir()
    test_build_index_survives_non_utf8_file()
    test_triage_named_input_report_is_indexed()
    test_triage_doc_detected_by_h1_not_filename()
    test_extract_proposals_ignores_nested_and_fenced_numbers()
    test_extract_proposals_strips_digit_hyphen_severity_tag()
    print('ok: all build_feedback_index tests passed')

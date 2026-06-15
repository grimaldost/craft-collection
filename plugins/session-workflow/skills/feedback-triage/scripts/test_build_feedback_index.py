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


def test_build_index_handles_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        assert '0 report' in build_index(Path(d))


if __name__ == '__main__':
    test_extract_proposals_pulls_numbered_titles()
    test_extract_proposals_empty_when_no_section()
    test_build_index_lists_reports_and_excludes_meta()
    test_build_index_handles_empty_dir()
    print('ok: all build_feedback_index tests passed')

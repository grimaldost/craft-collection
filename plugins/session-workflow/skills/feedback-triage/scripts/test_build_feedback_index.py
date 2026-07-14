"""Tests for build_feedback_index (pure parsing + render; no I/O on the real tree).
Runnable with pytest or `python test_build_feedback_index.py`."""

from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

from build_feedback_index import build_index, extract_proposals, main


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
    # A triage doc is an OUTPUT: no report section (## ), only a coverage entry (### ).
    assert '\n## 2026-01-03-triage-x' not in idx
    assert '\n### 2026-01-03-triage-x' in idx
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
    # Excluded from report sections by its '# Triage' H1, not its name; it still
    # appears as a coverage entry, because it IS a triage doc.
    assert '\n## 2026-01-07-weekly-summary' not in idx
    assert '\n### 2026-01-07-weekly-summary' in idx
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


def test_header_stamps_generator_version_and_rule():
    # A stale plugin cache re-applies its old detection rule forever, invisibly —
    # the INDEX must announce which generator/version/rule built it, so a
    # stale-built INDEX is visibly stale instead of quietly narrower.
    with tempfile.TemporaryDirectory() as d:
        idx = build_index(Path(d))
    assert 'generated by build_feedback_index.py (session-workflow ' in idx
    assert 'H1-rule' in idx


def test_triage_coverage_and_untriaged_sections():
    # The INDEX must also carry each triage doc's resolved input list plus the
    # computed untriaged remainder, so the triage scope step is one Read
    # (INDEX-minus-INDEX) instead of N phrasing-fragile header reads — the
    # by-hand subtraction lost 6 reports across three passes.
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-01-covered.md').write_text(
            '# foo feedback — a\n## Proposed promotions / changes\n1. **[MED]** x.\n',
            encoding='utf-8',
        )
        (dd / '2026-01-02-orphan.md').write_text('# bar feedback — b\n', encoding='utf-8')
        (dd / '2026-01-03-triage-pass.md').write_text(
            '# Triage — foo backlog (1 report)\n'
            '## Inputs\n'
            '1. `2026-01-01-covered.md` — with an annotation\n'
            '## Headline\nwords\n',
            encoding='utf-8',
        )
        idx = build_index(dd)
    assert '## Triage coverage' in idx
    assert '\n### 2026-01-03-triage-pass' in idx
    assert '- covers: `2026-01-01-covered`' in idx
    assert '\n### Untriaged' in idx
    # Line-anchored split: the header PROSE also mentions `### Untriaged`, so a
    # naive first-occurrence split lands in the header, not the section.
    untriaged = idx.split('\n### Untriaged', 1)[1]
    assert '`2026-01-02-orphan`' in untriaged
    assert '`2026-01-01-covered`' not in untriaged


def test_coverage_stem_match_is_boundary_aware():
    # Real corpus has prefix-colliding stems (2026-06-08-refresh-on-read vs
    # ...-refresh-on-read-execution). A triage doc listing only the LONGER one
    # must not mark the shorter one covered by substring accident.
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-04-foo.md').write_text('# foo feedback — a\n', encoding='utf-8')
        (dd / '2026-01-04-foo-execution.md').write_text('# foo feedback — b\n', encoding='utf-8')
        (dd / '2026-01-05-triage-x.md').write_text(
            '# Triage — x\n## Inputs\n1. `2026-01-04-foo-execution.md`\n## Headline\n',
            encoding='utf-8',
        )
        idx = build_index(dd)
    untriaged = idx.split('\n### Untriaged', 1)[1]
    assert '`2026-01-04-foo`' in untriaged  # NOT covered — only the longer stem was listed
    assert '- covers: `2026-01-04-foo-execution`' in idx


def test_triage_doc_without_inputs_covers_nothing():
    # A triage doc with no parseable ## Inputs section covers nothing — every
    # report stays in the untriaged remainder rather than being silently absorbed.
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-01-r.md').write_text('# r feedback — x\n', encoding='utf-8')
        (dd / '2026-01-02-triage-thin.md').write_text(
            '# Triage — thin\n## Headline\nno inputs section here\n', encoding='utf-8'
        )
        idx = build_index(dd)
    untriaged = idx.split('\n### Untriaged', 1)[1]
    assert '`2026-01-01-r`' in untriaged
    assert '(no Inputs / Addendum coverage parsed)' in idx


def test_addendum_section_credits_coverage():
    # A triage doc's dated ## Addendum handles a later wave in place, without editing
    # the frozen ## Inputs list; those reports must still count as covered, or the
    # scope step re-triages them (v19-sw#2: four addendum-handled reports read as
    # untriaged because coverage was read from ## Inputs alone).
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-01-01-a.md').write_text('# a feedback — x\n', encoding='utf-8')
        (dd / '2026-01-02-b.md').write_text('# b feedback — y\n', encoding='utf-8')
        (dd / '2026-01-03-triage.md').write_text(
            '# Triage — backlog (1 report)\n'
            '## Inputs\n'
            '1. `2026-01-01-a.md`\n'
            '## Addendum 2026-01-04\n'
            'A later wave, triaged in place:\n'
            '- `2026-01-02-b.md` — clustered under T7.\n'
            '## Headline\nwords\n',
            encoding='utf-8',
        )
        idx = build_index(dd)
    assert '- covers: `2026-01-01-a`' in idx
    assert '- covers: `2026-01-02-b`' in idx  # credited via the addendum, not Inputs
    untriaged = idx.split('\n### Untriaged', 1)[1]
    assert '`2026-01-02-b`' not in untriaged


def test_coverage_is_fence_aware_and_credits_prose_disposition():
    # #2 fence-awareness: a '#'-comment inside a fenced block in a coverage section
    # must not flip capture off and drop the inputs listed after it.
    # Prose disposition (the 2026-06-17 pattern): a report closed in Inputs PROSE,
    # not as a list item, still counts as covered — whole-section capture, not
    # list-items-only, or a deliberate prose close resurfaces as untriaged forever.
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / '2026-02-01-listed.md').write_text('# a feedback — x\n', encoding='utf-8')
        (dd / '2026-02-02-after-fence.md').write_text('# b feedback — y\n', encoding='utf-8')
        (dd / '2026-02-03-prose.md').write_text('# c feedback — z\n', encoding='utf-8')
        (dd / '2026-02-04-triage.md').write_text(
            '# Triage — backlog\n'
            '## Inputs\n'
            'Rebuilt via:\n'
            '```sh\n'
            '# rebuild the index\n'
            'uv run build_feedback_index.py .\n'
            '```\n'
            '1. `2026-02-01-listed.md`\n'
            '2. `2026-02-02-after-fence.md`\n'
            'Also closed here in prose: `2026-02-03-prose.md` (findings shipped earlier).\n'
            '## Headline\n',
            encoding='utf-8',
        )
        idx = build_index(dd)
    for stem in ('2026-02-01-listed', '2026-02-02-after-fence', '2026-02-03-prose'):
        assert f'- covers: `{stem}`' in idx  # fenced '#' did not drop the list; prose close counts
    untriaged = idx.split('\n### Untriaged', 1)[1]
    assert '`2026-02-01-listed`' not in untriaged


def test_help_flag_returns_zero_not_swallowed_as_dir():
    # --help / -h must print usage and exit 0, not be read as a positional dir arg
    # (regression: `--help` -> `Path('--help')` -> "not a directory: --help", exit 1).
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert main(['--help']) == 0
        assert main(['-h']) == 0
    assert 'build_feedback_index' in buf.getvalue()  # the docstring was printed
    with contextlib.redirect_stdout(io.StringIO()):
        assert main([]) == 2  # no args still prints usage and returns 2


def test_help_emits_utf8_bytes_under_cp1252():
    # The docstring carries em-dashes; a piped Windows stdout defaults to cp1252,
    # which used to emit them as cp1252 bytes — mojibake in UTF-8 terminals. The
    # script must emit UTF-8 regardless of the platform default; PYTHONIOENCODING
    # reproduces the cp1252 pipe on any platform.
    import os
    import subprocess
    import sys

    script = Path(__file__).resolve().parent / 'build_feedback_index.py'
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'cp1252'
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(script), '--help'],
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0
    assert '—'.encode() in proc.stdout


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
    test_header_stamps_generator_version_and_rule()
    test_triage_coverage_and_untriaged_sections()
    test_coverage_stem_match_is_boundary_aware()
    test_triage_doc_without_inputs_covers_nothing()
    test_addendum_section_credits_coverage()
    test_coverage_is_fence_aware_and_credits_prose_disposition()
    test_help_flag_returns_zero_not_swallowed_as_dir()
    test_help_emits_utf8_bytes_under_cp1252()
    print('ok: all build_feedback_index tests passed')

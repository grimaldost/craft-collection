"""Tests for scripts/word_budget.py — the skill-body word-budget ratchet (issue #54).
Stdlib-only; runnable with pytest or `python test_word_budget.py`."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from word_budget import (  # noqa: E402
    REFERENCE_BUDGET_FILE,
    body_word_count,
    check_budgets,
    check_reference_budgets,
    current_reference_counts,
    load_baselines,
    main,
    reference_report_rows,
    reference_word_count,
    report_rows,
    section_counts,
    section_rows,
)


def test_body_word_count_excludes_frontmatter():
    # The frontmatter (name/description) is budgeted separately (DESC_CAP); only the
    # body after the closing --- is counted.
    text = '---\nname: x\ndescription: one two three four five\n---\nbody has four words\n'
    assert body_word_count(text) == 4  # 'body has four words'


def test_body_word_count_no_frontmatter_counts_all():
    assert body_word_count('just some plain body text here') == 6


def test_body_word_count_preserves_body_horizontal_rules():
    # A --- horizontal rule INSIDE the body must not re-trigger the frontmatter split
    # (split maxsplit=2 stops after the two frontmatter delimiters).
    text = '---\nname: x\n---\nalpha beta\n\n---\n\ngamma delta epsilon\n'
    assert (
        body_word_count(text) == 6
    )  # alpha beta --- gamma delta epsilon -> 6 tokens incl the rule


def test_check_budgets_flags_over_baseline():
    errors = check_budgets({'a/SKILL.md': 120}, {'a/SKILL.md': 100})
    assert len(errors) == 1
    assert '120 words > budget 100' in errors[0]
    assert 'displaces' in errors[0]  # names the doctrine obligation


def test_check_budgets_flags_missing_baseline():
    errors = check_budgets({'new/SKILL.md': 50}, {})
    assert len(errors) == 1
    assert 'no word-budget baseline' in errors[0]


def test_check_budgets_passes_at_or_under_baseline():
    # Equal is fine (the seeded state); shrinking is always fine.
    assert (
        check_budgets({'a/SKILL.md': 100, 'b/SKILL.md': 40}, {'a/SKILL.md': 100, 'b/SKILL.md': 90})
        == []
    )


def test_report_shows_headroom_so_nobody_has_to_subtract_by_hand():
    # The recorded failure: an audit reported "body 2,658, gate 2,736, so 78
    # words of headroom" when the gate's own count of that body was 2,736 -
    # zero headroom. Both numbers came from the same single counter; only one
    # of them came from running it.
    rows = report_rows({'a/SKILL.md': 2736}, {'a/SKILL.md': 2736})
    assert len(rows) == 1
    assert '2736' in rows[0] and 'headroom' in rows[0]
    assert 'headroom      0' in rows[0]


def test_report_puts_the_tightest_budget_first():
    rows = report_rows(
        {'loose/SKILL.md': 10, 'tight/SKILL.md': 99}, {'loose/SKILL.md': 100, 'tight/SKILL.md': 100}
    )
    assert 'tight/SKILL.md' in rows[0]
    assert 'loose/SKILL.md' in rows[1]


def test_report_names_an_unbaselined_body_first_rather_than_omitting_it():
    rows = report_rows({'new/SKILL.md': 5, 'old/SKILL.md': 5}, {'old/SKILL.md': 10})
    assert 'new/SKILL.md' in rows[0]
    assert '?' in rows[0]


def test_report_is_ascii_because_it_prints_to_a_cp1252_console():
    for line in report_rows({'a/SKILL.md': 1}, {'a/SKILL.md': 2}):
        line.encode('ascii')


def test_cli_report_mode_exits_zero_and_does_not_gate():
    assert main(['--report']) == 0


# Frontmatter, a preamble, two '##' sections, a '###' subsection, a fenced block with a
# '#' line, and a heading with an em dash (written as an escape: this file stays ASCII).
SECTIONED = (
    '---\nname: x\ndescription: d\n---\n'
    'preamble words here\n'
    '\n## Alpha\none two three\n'
    '\n### Alpha child\nfour five\n'
    '\n## Beta — dash\n'
    '```\n# not a heading\nsix seven eight nine ten\n```\n'
    'eleven twelve\n'
)


def test_section_counts_orders_longest_first_and_sums_to_the_body():
    sections = section_counts(SECTIONED)
    assert [heading for _, heading, _ in sections] == [
        '## Beta — dash',
        '## Alpha',
        '### Alpha child',
        '(before first heading)',
    ]
    by_heading = {heading: words for _, heading, words in sections}
    # Flat sections: Alpha counts '##', 'Alpha' and its own three words, not its child.
    assert by_heading['## Alpha'] == 5
    assert by_heading['### Alpha child'] == 5
    # Sections partition the body lines, so the words add up to the gate's own count.
    assert sum(words for _, _, words in sections) == body_word_count(SECTIONED)


def test_section_counts_breaks_ties_by_line_number():
    sections = section_counts('## A\nx\n## B\nx\n')
    assert [heading for _, heading, _ in sections] == ['## A', '## B']


def test_a_fenced_hash_line_is_not_a_section():
    headings = [heading for _, heading, _ in section_counts(SECTIONED)]
    assert not any('not a heading' in heading for heading in headings)
    tilde = '## T\n~~~\n# inside\n~~~\nafter\n'
    assert [heading for _, heading, _ in section_counts(tilde)] == ['## T']


def test_section_report_is_ascii_for_a_non_ascii_heading():
    lines = section_rows('skills/x/SKILL.md', SECTIONED, 100)
    assert len(lines) > 2
    for line in lines:
        line.encode('ascii')
    assert any('\\u2014' in line for line in lines)


def test_cli_report_with_a_skill_name_lists_its_sections():
    assert main(['--report', 'experiment-rigor']) == 0


def test_cli_report_with_an_unknown_skill_exits_2():
    assert main(['--report', 'no-such-skill-anywhere']) == 2


def test_reference_word_count_is_recursive_and_counts_md_only():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / 'a.md').write_text('one two three', encoding='utf-8')
        (d / 'sub').mkdir()
        (d / 'sub' / 'b.md').write_text('four five', encoding='utf-8')
        (d / 'c.txt').write_text('not counted at all here', encoding='utf-8')
        assert reference_word_count(d) == (5, 2)


def test_current_reference_counts_marks_a_missing_directory():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / 'refs').mkdir()
        (root / 'refs' / 'a.md').write_text('w w w', encoding='utf-8')
        counts = current_reference_counts({'refs': 9, 'gone': 9}, root)
    assert counts == {'refs': (3, 1), 'gone': None}


def test_check_reference_budgets_flags_over_ceiling():
    errors = check_reference_budgets({'p/refs': (10, 2)}, {'p/refs': 9})
    assert len(errors) == 1, errors
    assert 'p/refs' in errors[0] and '10' in errors[0] and '9' in errors[0], errors
    assert 'displaces' in errors[0], errors
    errors[0].encode('ascii')


def test_check_reference_budgets_passes_at_or_under_ceiling():
    assert check_reference_budgets({'p/refs': (9, 2)}, {'p/refs': 9}) == []
    assert check_reference_budgets({'p/refs': (1, 1)}, {'p/refs': 9}) == []


def test_check_reference_budgets_flags_a_missing_directory():
    errors = check_reference_budgets({'p/refs': None}, {'p/refs': 9})
    assert len(errors) == 1 and 'p/refs' in errors[0] and 'missing' in errors[0], errors


def test_check_reference_budgets_flags_a_directory_with_no_files():
    errors = check_reference_budgets({'p/refs': (0, 0)}, {'p/refs': 9})
    assert len(errors) == 1 and 'p/refs' in errors[0] and 'no .md files' in errors[0], errors


def test_recorded_reference_ceilings_cover_real_files():
    # The shipped ceiling file is not vacuous: every recorded directory exists,
    # holds files, and is within its ceiling.
    ceilings = load_baselines(REFERENCE_BUDGET_FILE)
    assert ceilings, REFERENCE_BUDGET_FILE
    counts = current_reference_counts(ceilings)
    for path in ceilings:
        assert counts[path] is not None and counts[path][1] > 0, (path, counts[path])
    assert check_reference_budgets(counts, ceilings) == []


def test_reference_report_rows_show_headroom_in_ascii():
    rows = reference_report_rows({'p/refs': (7, 2), 'q/gone': None}, {'p/refs': 9, 'q/gone': 4})
    assert any('7 /     9  headroom      2  p/refs' in r for r in rows), rows
    assert any('q/gone' in r and 'missing' in r for r in rows), rows
    for r in rows:
        r.encode('ascii')


if __name__ == '__main__':
    test_body_word_count_excludes_frontmatter()
    test_body_word_count_no_frontmatter_counts_all()
    test_body_word_count_preserves_body_horizontal_rules()
    test_check_budgets_flags_over_baseline()
    test_check_budgets_flags_missing_baseline()
    test_check_budgets_passes_at_or_under_baseline()
    test_report_shows_headroom_so_nobody_has_to_subtract_by_hand()
    test_report_puts_the_tightest_budget_first()
    test_report_names_an_unbaselined_body_first_rather_than_omitting_it()
    test_report_is_ascii_because_it_prints_to_a_cp1252_console()
    test_cli_report_mode_exits_zero_and_does_not_gate()
    test_section_counts_orders_longest_first_and_sums_to_the_body()
    test_section_counts_breaks_ties_by_line_number()
    test_a_fenced_hash_line_is_not_a_section()
    test_section_report_is_ascii_for_a_non_ascii_heading()
    test_cli_report_with_a_skill_name_lists_its_sections()
    test_cli_report_with_an_unknown_skill_exits_2()
    test_reference_word_count_is_recursive_and_counts_md_only()
    test_current_reference_counts_marks_a_missing_directory()
    test_check_reference_budgets_flags_over_ceiling()
    test_check_reference_budgets_passes_at_or_under_ceiling()
    test_check_reference_budgets_flags_a_missing_directory()
    test_check_reference_budgets_flags_a_directory_with_no_files()
    test_recorded_reference_ceilings_cover_real_files()
    test_reference_report_rows_show_headroom_in_ascii()
    print('ok: all word_budget tests passed')

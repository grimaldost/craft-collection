"""Tests for scripts/word_budget.py — the skill-body word-budget ratchet (issue #54).
Stdlib-only; runnable with pytest or `python test_word_budget.py`."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

from word_budget import body_word_count, check_budgets, main, report_rows  # noqa: E402


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
    print('ok: all word_budget tests passed')

#!/usr/bin/env python3
"""Tests for holdout_check CLI guards — pure, no agent spawns.

Run from this directory (run_tests.py does: cwd = the test's own dir):

    python test_holdout_check.py
"""

from __future__ import annotations

import holdout_check


def test_no_args_returns_usage_code() -> None:
    assert holdout_check.main([]) == 2


def test_missing_holdout_returns_1() -> None:
    # A skill with no evals/trigger/holdout/<skill>.json exits 1 *before* any
    # spawn or plugin lookup, so this never touches the network.
    assert holdout_check.main(['no-such-skill-xyz']) == 1


def test_holdout_comparison_flags_drop() -> None:
    out = holdout_check.holdout_comparison(0.90, [0.70, 0.98], 0.50)
    assert 'DROP' in out and 'overfit' in out  # held-out below dev's lower CI bound


def test_holdout_comparison_ok_within_ci() -> None:
    out = holdout_check.holdout_comparison(0.90, [0.70, 0.98], 0.80)
    assert 'within' in out and 'DROP' not in out


def test_holdout_comparison_no_dev_entry() -> None:
    assert 'dev recall n/a' in holdout_check.holdout_comparison(None, None, 0.80)


def test_holdout_comparison_drop_driven_by_errors_is_not_overfit() -> None:
    # The strict held-out point (0.75) sits below dev's lower CI bound (0.80) ONLY
    # because errored-before-activation runs depressed it; excluding them it is 1.00,
    # within CI. The verdict must name the infra cause and ask for a re-run, not
    # declare overfit off a number the errors produced. (The 2026-07-14 birth
    # baseline this guards: 3 identical `Prompt is too long` errors on one query.)
    out = holdout_check.holdout_comparison(
        0.90, [0.80, 0.98], 0.75, holdout_recall_excl=1.00, n_err=3
    )
    assert 'errored-before-activation' in out and 'overfit' not in out
    assert 'Re-run' in out


def test_holdout_comparison_real_drop_survives_error_exclusion() -> None:
    # Even excluding the one error the point stays below the dev bound -> a real
    # DROP, still flagged as possible overfit. Errors are not a blanket excuse.
    out = holdout_check.holdout_comparison(
        0.90, [0.80, 0.98], 0.50, holdout_recall_excl=0.55, n_err=1
    )
    assert 'DROP beyond dev CI' in out and 'overfit' in out


def test_holdout_comparison_errors_ignored_when_no_strict_drop() -> None:
    # Errors present but the strict point already clears the bound -> the normal
    # "generalizes" verdict, no infra-artifact noise added.
    out = holdout_check.holdout_comparison(
        0.90, [0.80, 0.98], 0.85, holdout_recall_excl=1.00, n_err=2
    )
    assert 'generalizes' in out and 'errored-before-activation' not in out


def test_holdout_excl_point_pooled_path_uses_pooled_excl() -> None:
    # Pooled comparison: feed the pooled error-excluded recall into the rescue.
    score = {'recall': 0.75, 'recall_excl_errors': 1.0}
    assert holdout_check.holdout_excl_point(score, 'pooled') == 1.0


def test_holdout_excl_point_query_path_returns_none_not_mismatched_units() -> None:
    # Query comparison: the strict point and dev bound are query-level, but
    # recall_excl_errors is pooled. Returning it would compare mismatched units, so the
    # rescue must be skipped (None), not fed a pooled value against a query-level bound.
    score = {'recall': 0.75, 'recall_query': 0.75, 'recall_excl_errors': 1.0}
    assert holdout_check.holdout_excl_point(score, 'query') is None


def test_dev_recall_pair_prefers_matched_query_units() -> None:
    # The dev POINT and dev CI must come from the same estimator. Pairing the
    # pooled point (0.9) with the query-level interval ([0.5, 0.9]) let the point
    # sit at its own upper bound and tripped false DROP verdicts.
    dev = {
        'recall': 0.9,
        'recall_ci': [0.8, 0.95],
        'recall_query': 0.75,
        'recall_ci_query': [0.5, 0.9],
    }
    point, ci, units = holdout_check.dev_recall_pair(dev)
    assert point == 0.75 and ci == [0.5, 0.9] and units == 'query'


def test_dev_recall_pair_falls_back_to_pooled_pair() -> None:
    # An older report without the query-level point must pair pooled with pooled
    # — never the pooled point with the query-level interval.
    dev = {'recall': 0.9, 'recall_ci': [0.8, 0.95], 'recall_ci_query': [0.5, 0.9]}
    point, ci, units = holdout_check.dev_recall_pair(dev)
    assert point == 0.9 and ci == [0.8, 0.95] and units == 'pooled'


# --- stratified holdouts (T41e) -------------------------------------------
# A holdout set whose cases are not all equally unseen has no single recall.
# The 2026-08-11 data-engineering-discipline read is the case: 6 genuinely
# unseen cases scored 0.75, 7 re-used spent-dev cases scored 0.50, and the
# harness printed the pooled 0.62 as its headline. BASELINES.md then had to
# say, in prose, that the printed number must not be read. A tool that
# volunteers a figure its own doctrine forbids will have that figure quoted.

STRATIFIED = [
    {'query': 'a', 'should_trigger': True, 'stratum': 'unseen'},
    {'query': 'b', 'should_trigger': True, 'stratum': 'unseen'},
    {'query': 'c', 'should_trigger': True, 'stratum': 'spent-dev'},
    {'query': 'd', 'should_trigger': False, 'stratum': 'unseen'},
    {'query': 'e', 'should_trigger': False, 'stratum': 'spent-dev'},
]

PER_QUERY = [
    {'query': 'a', 'should_trigger': True, 'k': 3, 'repeats': 3},
    {'query': 'b', 'should_trigger': True, 'k': 0, 'repeats': 3},
    {'query': 'c', 'should_trigger': True, 'k': 0, 'repeats': 3},
    {'query': 'd', 'should_trigger': False, 'k': 0, 'repeats': 3},
    {'query': 'e', 'should_trigger': False, 'k': 3, 'repeats': 3},
]


def test_strata_of_reads_the_declared_label_and_ignores_undeclared_sets() -> None:
    assert holdout_check.strata_of(STRATIFIED)['a'] == 'unseen'
    assert holdout_check.strata_of([{'query': 'x', 'should_trigger': True}]) == {}


def test_stratify_reports_each_stratum_separately() -> None:
    rows = holdout_check.stratify(PER_QUERY, holdout_check.strata_of(STRATIFIED))
    by = {r['stratum']: r for r in rows}
    assert set(by) == {'unseen', 'spent-dev'}
    # unseen positives: a 3/3 + b 0/3 -> 3/6
    assert by['unseen']['recall'] == 0.5
    assert by['unseen']['n_positive_runs'] == 6
    # spent-dev positives: c 0/3 -> 0/3
    assert by['spent-dev']['recall'] == 0.0
    # unseen negative d stayed quiet 3/3; spent-dev negative e fired every time
    assert by['unseen']['specificity'] == 1.0
    assert by['spent-dev']['specificity'] == 0.0


def test_stratify_is_empty_when_the_set_declares_one_stratum_or_none() -> None:
    # Nothing to separate: the pooled figure IS the finding, and the extra
    # apparatus would be noise.
    assert holdout_check.stratify(PER_QUERY, {}) == []
    one = {q['query']: 'unseen' for q in STRATIFIED}
    assert holdout_check.stratify(PER_QUERY, one) == []


def test_a_stratum_with_no_positives_reports_none_rather_than_zero() -> None:
    rows = holdout_check.stratify(
        [
            {'query': 'd', 'should_trigger': False, 'k': 0, 'repeats': 3},
            {'query': 'a', 'should_trigger': True, 'k': 3, 'repeats': 3},
        ],
        {'d': 'neg-only', 'a': 'unseen'},
    )
    by = {r['stratum']: r for r in rows}
    assert by['neg-only']['recall'] is None
    assert by['neg-only']['specificity'] == 1.0


def test_the_pooled_line_is_labelled_unreadable_when_strata_disagree() -> None:
    rows = holdout_check.stratify(PER_QUERY, holdout_check.strata_of(STRATIFIED))
    line = holdout_check.pooled_caveat(rows)
    assert 'POOLED' in line
    assert 'not the finding' in line
    assert '2 strata' in line


def test_there_is_no_pooled_caveat_when_there_is_nothing_to_pool_over() -> None:
    assert holdout_check.pooled_caveat([]) == ''


def test_the_caveat_is_ascii_because_it_prints_to_a_cp1252_console() -> None:
    rows = holdout_check.stratify(PER_QUERY, holdout_check.strata_of(STRATIFIED))
    holdout_check.pooled_caveat(rows).encode('ascii')
    for r in rows:
        holdout_check.format_stratum(r).encode('ascii')


if __name__ == '__main__':
    test_no_args_returns_usage_code()
    test_missing_holdout_returns_1()
    test_holdout_comparison_flags_drop()
    test_holdout_comparison_ok_within_ci()
    test_holdout_comparison_no_dev_entry()
    test_holdout_comparison_drop_driven_by_errors_is_not_overfit()
    test_holdout_comparison_real_drop_survives_error_exclusion()
    test_holdout_comparison_errors_ignored_when_no_strict_drop()
    test_holdout_excl_point_pooled_path_uses_pooled_excl()
    test_holdout_excl_point_query_path_returns_none_not_mismatched_units()
    test_dev_recall_pair_prefers_matched_query_units()
    test_dev_recall_pair_falls_back_to_pooled_pair()
    test_strata_of_reads_the_declared_label_and_ignores_undeclared_sets()
    test_stratify_reports_each_stratum_separately()
    test_stratify_is_empty_when_the_set_declares_one_stratum_or_none()
    test_a_stratum_with_no_positives_reports_none_rather_than_zero()
    test_the_pooled_line_is_labelled_unreadable_when_strata_disagree()
    test_there_is_no_pooled_caveat_when_there_is_nothing_to_pool_over()
    test_the_caveat_is_ascii_because_it_prints_to_a_cp1252_console()
    print('ok: holdout_check')

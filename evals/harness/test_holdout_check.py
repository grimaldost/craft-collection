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


if __name__ == '__main__':
    test_no_args_returns_usage_code()
    test_missing_holdout_returns_1()
    test_holdout_comparison_flags_drop()
    test_holdout_comparison_ok_within_ci()
    test_holdout_comparison_no_dev_entry()
    test_holdout_comparison_drop_driven_by_errors_is_not_overfit()
    test_holdout_comparison_real_drop_survives_error_exclusion()
    test_holdout_comparison_errors_ignored_when_no_strict_drop()
    test_dev_recall_pair_prefers_matched_query_units()
    test_dev_recall_pair_falls_back_to_pooled_pair()
    print('ok: holdout_check')

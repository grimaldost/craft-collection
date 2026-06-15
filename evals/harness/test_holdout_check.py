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


if __name__ == '__main__':
    test_no_args_returns_usage_code()
    test_missing_holdout_returns_1()
    test_holdout_comparison_flags_drop()
    test_holdout_comparison_ok_within_ci()
    test_holdout_comparison_no_dev_entry()
    print('ok: holdout_check')

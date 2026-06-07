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


if __name__ == '__main__':
    test_no_args_returns_usage_code()
    test_missing_holdout_returns_1()
    print('ok: holdout_check')

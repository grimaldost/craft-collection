"""Tests for stats. Runnable with pytest or `python test_stats.py`."""

from __future__ import annotations

from stats import majority, wilson_interval


def test_wilson_known_values():
    lo, hi = wilson_interval(8, 10)
    assert 0.49 < lo < 0.50 and 0.94 < hi < 0.95
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_majority():
    assert majority([True, True, False]) is True
    assert majority([False, False, True]) is False
    assert majority([]) is None


if __name__ == '__main__':
    test_wilson_known_values()
    test_majority()
    print('ok: all stats tests passed')

"""Tests for freshness_check. Runnable with pytest or `python test_freshness_check.py`.

Encodes the review-hardened contract: a stuck cursor FAILS, an unassessable
input is `ok=None` (never a false PASS), string/tz-mismatched cursors are
rejected as uncomparable rather than silently mis-ordered, and per-group
staleness is detectable.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from freshness_check import check_freshness, check_freshness_groups, main


def test_advance_ok():
    rep = check_freshness(1000, 1500)
    assert rep['ok'] is True
    assert rep['advanced'] is True


def test_stuck_cursor_fails():
    # The originating 06-19 bug: cache built once, cursor frozen, run reports success.
    rep = check_freshness(1000, 1000)
    assert rep['ok'] is False
    assert rep['advanced'] is False
    assert 'stale' in rep['reason']


def test_source_lag_fails_even_without_advance_check():
    # curr == prev (no advance asserted) but source has moved ahead -> stale.
    rep = check_freshness(1000, 1000, 1500, require_advance=False)
    assert rep['ok'] is False
    assert rep['lag'] == 500


def test_source_caught_up_ok():
    rep = check_freshness(1000, 1500, 1500, require_advance=False)
    assert rep['ok'] is True
    assert rep['lag'] == 0


def test_max_lag_tolerance():
    rep = check_freshness(None, 1400, 1500, require_advance=False, max_lag=100)
    assert rep['ok'] is True  # 100 behind, tolerance 100
    rep2 = check_freshness(None, 1399, 1500, require_advance=False, max_lag=100)
    assert rep2['ok'] is False  # 101 behind


def test_unknown_is_not_a_pass():
    # No prior snapshot and no source -> cannot assess. Must NOT be ok=True (FM-6).
    rep = check_freshness(None, 1500)
    assert rep['ok'] is None
    assert 'unknown' in rep['reason']


def test_string_cursor_rejected_not_misordered():
    # Naive '9' > '10' is True (lexical) -> a false "advanced". The gate must refuse.
    rep = check_freshness('9', '10')
    assert rep['ok'] is False
    assert 'uncomparable' in rep['reason']


def test_tz_aware_vs_naive_rejected():
    aware = datetime(2026, 6, 19, tzinfo=timezone.utc)
    naive = datetime(2026, 6, 18)
    rep = check_freshness(naive, aware)
    assert rep['ok'] is False
    assert 'uncomparable' in rep['reason']


def test_mixed_types_rejected():
    rep = check_freshness(1000, datetime(2026, 6, 19))
    assert rep['ok'] is False
    assert 'uncomparable' in rep['reason']


def test_datetime_advance_ok():
    rep = check_freshness(datetime(2026, 6, 18), datetime(2026, 6, 19))
    assert rep['ok'] is True
    assert rep['advanced'] is True


def test_max_lag_temporal_cursor_within_tolerance_passes():
    # A date cursor 2 days behind source, allowed lag 7 days. Previously --max-lag
    # was a bare float, so `timedelta(days=2) <= 7.0` raised TypeError and the run
    # reported a FALSE "STALE: uncomparable (tz-aware vs naive?)". For a temporal
    # cursor, max_lag is interpreted as a number of DAYS -> comparable, passes.
    rep = check_freshness(
        None, date(2026, 6, 17), date(2026, 6, 19), require_advance=False, max_lag=7
    )
    assert rep['ok'] is True
    assert 'uncomparable' not in rep['reason']


def test_max_lag_temporal_cursor_beyond_tolerance_fails_honestly():
    # 5 days behind, allowed 2 -> genuinely stale, and NOT a bogus tz message.
    rep = check_freshness(
        None, datetime(2026, 6, 14), datetime(2026, 6, 19), require_advance=False, max_lag=2
    )
    assert rep['ok'] is False
    assert 'uncomparable' not in rep['reason']
    assert 'stale' in rep['reason']


def test_cli_max_lag_datetime_within_tolerance_passes():
    # End-to-end through main(): a datetime cursor within the day-lag allowance
    # must exit 0 (FRESH), not blow up on the float/timedelta mismatch.
    rc = main(
        ['--curr', '2026-06-18', '--source', '2026-06-19', '--max-lag', '7', '--no-require-advance']
    )
    assert rc == 0


def test_per_group_one_stale_fails():
    # Global max would advance (g2 moved), but g1 is frozen -> per-group catches it.
    groups = [
        {'group': 'tenant_a', 'prev': 1000, 'curr': 1000},  # frozen
        {'group': 'tenant_b', 'prev': 1000, 'curr': 1500},  # advanced
    ]
    rep = check_freshness_groups(groups)
    assert rep['ok'] is False
    assert 'tenant_a' in rep['stale']
    assert 'tenant_b' not in rep['stale']


def test_per_group_all_fresh_ok():
    groups = [
        {'group': 'a', 'prev': 1, 'curr': 2},
        {'group': 'b', 'prev': 5, 'curr': 9},
    ]
    rep = check_freshness_groups(groups)
    assert rep['ok'] is True
    assert rep['stale'] == []


if __name__ == '__main__':
    test_advance_ok()
    test_stuck_cursor_fails()
    test_source_lag_fails_even_without_advance_check()
    test_source_caught_up_ok()
    test_max_lag_tolerance()
    test_unknown_is_not_a_pass()
    test_string_cursor_rejected_not_misordered()
    test_tz_aware_vs_naive_rejected()
    test_mixed_types_rejected()
    test_datetime_advance_ok()
    test_max_lag_temporal_cursor_within_tolerance_passes()
    test_max_lag_temporal_cursor_beyond_tolerance_fails_honestly()
    test_cli_max_lag_datetime_within_tolerance_passes()
    test_per_group_one_stale_fails()
    test_per_group_all_fresh_ok()
    print('ok: all freshness_check tests passed')

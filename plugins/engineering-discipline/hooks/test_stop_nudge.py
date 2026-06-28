"""Tests for stop_nudge.should_nudge. Runnable with pytest or `python test_stop_nudge.py`."""

from __future__ import annotations

from stop_nudge import nudge_message, should_nudge


def test_matches_pipeline_files():
    assert should_nudge(['models/stg_orders.sql']) is True
    assert should_nudge(['src/pipeline_runner.py']) is True
    assert should_nudge(['dbt_project/models/x.sql']) is True


def test_no_match_on_plain_code():
    assert should_nudge(['src/app/main.py', 'README.md']) is False


def test_nudge_message_names_freshness_check():
    # The runnable cursor-advance checker must be named, not just the generic checklist.
    msg = nudge_message()
    assert 'freshness_check.py' in msg


if __name__ == '__main__':
    test_matches_pipeline_files()
    test_no_match_on_plain_code()
    test_nudge_message_names_freshness_check()
    print('ok: all stop_nudge tests passed')

"""Tests for stop_nudge.should_nudge. Runnable with pytest or `python test_stop_nudge.py`."""

from __future__ import annotations

import io
import json

from stop_nudge import decide, main, nudge_message, should_nudge


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


def test_decide_emits_block_json_for_pipeline_change():
    # The Stop-hook contract only routes a nudge to Claude via {"decision":"block"}
    # JSON on STDOUT (a bare stderr print on exit 0 is discarded). So when a
    # pipeline file changed, decide must return that JSON payload.
    out = decide(
        payload={},
        changed_files=['models/stg_orders.sql'],
        globs=None,
        enabled=True,
    )
    assert out is not None
    obj = json.loads(out)
    assert obj['decision'] == 'block'
    assert 'freshness_check.py' in obj['reason']


def test_decide_silent_when_disabled():
    assert decide(payload={}, changed_files=['models/x.sql'], globs=None, enabled=False) is None


def test_decide_silent_on_plain_code():
    assert decide(payload={}, changed_files=['src/app/main.py'], globs=None, enabled=True) is None


def test_decide_guards_against_loop():
    # If we already blocked once (stop_hook_active), do NOT block again — that
    # would loop the Stop hook forever.
    out = decide(
        payload={'stop_hook_active': True},
        changed_files=['models/x.sql'],
        globs=None,
        enabled=True,
    )
    assert out is None


def test_main_writes_json_to_stdout_not_stderr():
    # End-to-end: the nudge must land on STDOUT as JSON, never only on stderr.
    stdin = io.StringIO('{}')
    stdout = io.StringIO()
    stderr = io.StringIO()
    rc = main(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        enabled=True,
        changed_files=['models/stg_orders.sql'],
    )
    assert rc == 0
    payload = json.loads(stdout.getvalue())
    assert payload['decision'] == 'block'
    assert 'freshness_check.py' in payload['reason']
    assert stderr.getvalue() == ''  # nothing routed to the discarded stream


if __name__ == '__main__':
    test_matches_pipeline_files()
    test_no_match_on_plain_code()
    test_nudge_message_names_freshness_check()
    test_decide_emits_block_json_for_pipeline_change()
    test_decide_silent_when_disabled()
    test_decide_silent_on_plain_code()
    test_decide_guards_against_loop()
    test_main_writes_json_to_stdout_not_stderr()
    print('ok: all stop_nudge tests passed')

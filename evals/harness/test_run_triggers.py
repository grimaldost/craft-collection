"""Tests for run_triggers.score_skill (pure scorer; no agents). Runnable with
pytest or `python test_run_triggers.py`."""

from __future__ import annotations

from run_triggers import score_skill


def fake_run(query, repeats):  # fires only on queries containing "journal"
    return 3 if 'journal' in query else 0


def test_scoring_recall_specificity():
    queries = [
        {'query': 'journal this', 'should_trigger': True},
        {'query': "what's 2+2", 'should_trigger': False},
    ]
    r = score_skill(queries, repeats=3, trigger_counter=fake_run)
    assert r['recall'] == 1.0 and r['specificity'] == 1.0
    assert 'recall_ci' in r and 'specificity_ci' in r


def test_specificity_failure_when_negative_fires():
    # counter fires on everything: positive recall perfect, negative specificity zero
    queries = [
        {'query': 'journal this', 'should_trigger': True},
        {'query': 'journal that too', 'should_trigger': False},
    ]
    r = score_skill(queries, repeats=3, trigger_counter=lambda q, n: 3)
    assert r['recall'] == 1.0
    assert r['specificity'] == 0.0
    lo, hi = r['specificity_ci']
    assert 0.0 <= lo <= hi <= 1.0


def test_partial_recall_pools_across_repeats():
    # one positive fires 1/3 -> pooled recall 1/3
    queries = [{'query': 'p', 'should_trigger': True}]
    r = score_skill(queries, repeats=3, trigger_counter=lambda q, n: 1)
    assert abs(r['recall'] - 1 / 3) < 1e-9
    assert r['per_query'][0]['k'] == 1


def test_error_counter_decomposes_recall():
    # One positive, 3 repeats: fired once, and one of the two non-firing runs errored.
    # Strict recall (gated) stays 1/3; excluding the errored run it is 1/2.
    queries = [{'query': 'p', 'should_trigger': True}]
    r = score_skill(
        queries,
        repeats=3,
        trigger_counter=lambda q, n: 1,
        error_counter=lambda q, n: 1,
    )
    assert abs(r['recall'] - 1 / 3) < 1e-9
    assert abs(r['recall_excl_errors'] - 1 / 2) < 1e-9
    assert r['per_query'][0]['errors_no_activation'] == 1
    assert r['errors_no_activation_positive'] == 1


def test_error_counter_defaults_to_zero():
    queries = [{'query': 'p', 'should_trigger': True}]
    r = score_skill(queries, repeats=3, trigger_counter=lambda q, n: 2)
    assert r['recall_excl_errors'] == r['recall']
    assert r['per_query'][0]['errors_no_activation'] == 0
    assert r['errors_no_activation_positive'] == 0


def test_all_positive_runs_errored_yields_none():
    # Every non-firing positive run errored: no valid evidence either way.
    queries = [{'query': 'p', 'should_trigger': True}]
    r = score_skill(
        queries,
        repeats=2,
        trigger_counter=lambda q, n: 0,
        error_counter=lambda q, n: 2,
    )
    assert r['recall'] == 0.0  # strict stays conservative
    assert r['recall_excl_errors'] is None  # zero valid runs -> no rate


if __name__ == '__main__':
    test_scoring_recall_specificity()
    test_specificity_failure_when_negative_fires()
    test_partial_recall_pools_across_repeats()
    test_error_counter_decomposes_recall()
    test_error_counter_defaults_to_zero()
    test_all_positive_runs_errored_yields_none()
    print('ok: all run_triggers tests passed')

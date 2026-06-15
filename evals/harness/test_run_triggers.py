"""Tests for run_triggers.score_skill (pure scorer; no agents). Runnable with
pytest or `python test_run_triggers.py`."""

from __future__ import annotations

from run_triggers import merge_report, score_skill, validate_queries


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


def test_expected_hard_excluded_from_gated_recall():
    # A hard positive that never fires must NOT drag the gated recall; its rate is
    # reported as recall_hard instead, so a tuning round stops re-spending on it.
    queries = [
        {'query': 'normal', 'should_trigger': True},
        {'query': 'canonical imperative', 'should_trigger': True, 'expected_hard': True},
    ]
    counter = lambda q, n: 3 if q == 'normal' else 0  # noqa: E731 - test stub
    r = score_skill(queries, repeats=3, trigger_counter=counter)
    assert r['recall'] == 1.0  # gated recall over non-hard positives only -> perfect
    assert r['recall_hard'] == 0.0  # the hard one is reported, not gated
    assert r['recall_hard_ci'] is not None
    assert r['n_positive'] == 2 and r['n_positive_hard'] == 1
    hard_pq = next(pq for pq in r['per_query'] if pq['query'] == 'canonical imperative')
    assert hard_pq['expected_hard'] is True


def test_no_hard_queries_leaves_recall_unchanged():
    queries = [{'query': 'p', 'should_trigger': True}]
    r = score_skill(queries, repeats=3, trigger_counter=lambda q, n: 3)
    assert r['recall'] == 1.0
    assert r['recall_hard'] is None and r['n_positive_hard'] == 0
    assert r['per_query'][0]['expected_hard'] is False


def test_validate_queries_accepts_well_formed():
    queries = [
        {'query': 'a', 'should_trigger': True},
        {'query': 'b', 'should_trigger': False},
        {
            'query': 'c',
            'should_trigger': True,
            'expected_hard': True,
            'note': 'documented immovable',
        },
    ]
    assert validate_queries(queries) == []


def test_validate_queries_flags_problems():
    queries = [
        {'query': '', 'should_trigger': True},  # empty query
        {'query': 'x', 'should_trigger': 'yes'},  # non-bool should_trigger
        {'query': 'y', 'should_trigger': False, 'expected_hard': True, 'note': 'n'},  # hard on neg
        {'query': 'z', 'should_trigger': True, 'expected_hard': True},  # hard without a note
        {'query': 'x', 'should_trigger': True},  # duplicate 'x'
    ]
    problems = validate_queries(queries)
    assert any('expected_hard' in p and 'positive' in p for p in problems)
    assert any('note' in p for p in problems)
    assert any('duplicate' in p for p in problems)
    assert any('should_trigger' in p for p in problems)


def test_merge_report_adds_and_preserves_without_mutating():
    blob = {'a': {'total_runs': 10}}
    new, clobbered = merge_report(blob, 'b', {'total_runs': 5})
    assert new['a'] == {'total_runs': 10} and new['b'] == {'total_runs': 5}
    assert clobbered is False  # a new skill clobbers nothing
    assert blob == {'a': {'total_runs': 10}}  # input not mutated


def test_merge_report_flags_partial_overwriting_fuller():
    blob = {'s': {'total_runs': 48}}  # a full run already on disk
    _, clobbered = merge_report(blob, 's', {'total_runs': 6})  # a --limit partial
    assert clobbered is True


def test_merge_report_full_over_partial_is_fine():
    _, clobbered = merge_report({'s': {'total_runs': 6}}, 's', {'total_runs': 48})
    assert clobbered is False


if __name__ == '__main__':
    test_scoring_recall_specificity()
    test_specificity_failure_when_negative_fires()
    test_partial_recall_pools_across_repeats()
    test_error_counter_decomposes_recall()
    test_error_counter_defaults_to_zero()
    test_all_positive_runs_errored_yields_none()
    test_expected_hard_excluded_from_gated_recall()
    test_no_hard_queries_leaves_recall_unchanged()
    test_validate_queries_accepts_well_formed()
    test_validate_queries_flags_problems()
    test_merge_report_adds_and_preserves_without_mutating()
    test_merge_report_flags_partial_overwriting_fuller()
    test_merge_report_full_over_partial_is_fine()
    print('ok: all run_triggers tests passed')

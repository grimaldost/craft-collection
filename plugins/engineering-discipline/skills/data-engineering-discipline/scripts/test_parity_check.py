"""Tests for parity_check.compare. Runnable with pytest or `python test_parity_check.py`."""

from __future__ import annotations

import tempfile
from pathlib import Path

from parity_check import compare, main, two_producer_check


def test_identical_tables_ok():
    rows = [{'id': '1', 'amt': '10'}, {'id': '2', 'amt': '20'}]
    rep = compare(rows, rows, keys=['id'])
    assert rep['ok'] is True
    assert rep['row_count']['delta'] == 0


def test_row_count_mismatch_fails():
    a = [{'id': '1', 'amt': '10'}]
    b = [{'id': '1', 'amt': '10'}, {'id': '2', 'amt': '20'}]
    rep = compare(a, b, keys=['id'])
    assert rep['ok'] is False
    assert rep['row_count']['delta'] == 1


def test_sum_delta_detected():
    a = [{'id': '1', 'amt': '10'}]
    b = [{'id': '1', 'amt': '11'}]
    rep = compare(a, b, keys=['id'])
    assert rep['ok'] is False
    assert abs(rep['sum_delta']['amt']['delta'] - 1.0) < 1e-9


def test_all_null_column_fails_even_at_loose_sum_tol():
    # A column going 100% NULL is a semantic regression. The sum `--tol` must NOT
    # gate the null-rate check: a huge tol (1.0) that makes sum drift irrelevant
    # must still leave the null-rate delta of +1.0 a FAILURE. (`label` here is a
    # non-numeric column, so it contributes no sum drift — only a null-rate jump.)
    a = [{'id': '1', 'label': 'x'}, {'id': '2', 'label': 'y'}]
    b = [{'id': '1', 'label': ''}, {'id': '2', 'label': ''}]
    rep = compare(a, b, keys=['id'], tol=1.0)
    assert rep['null_rate_delta']['label'] == 1.0
    assert rep['ok'] is False


def test_null_tol_gates_null_rate_independently():
    # A small null-rate wobble is tolerable under an explicit --null-tol, while the
    # sum tol stays tight. Here one of two rows goes null -> delta 0.5.
    a = [{'id': '1', 'label': 'x'}, {'id': '2', 'label': 'y'}]
    b = [{'id': '1', 'label': 'x'}, {'id': '2', 'label': ''}]
    assert compare(a, b, keys=['id'], null_tol=0.0)['ok'] is False
    assert compare(a, b, keys=['id'], null_tol=0.5)['ok'] is True


def test_literal_nan_inf_cells_do_not_poison_sums():
    # 'nan'/'inf' strings pass float() but poison every sum they touch (nan-nan
    # = nan fails every tolerance). Identical tables must compare PARITY OK:
    # non-finite cells are ignored as non-numeric, like text.
    rows = [{'id': '1', 'amt': 'nan'}, {'id': '2', 'amt': 'inf'}, {'id': '3', 'amt': '10'}]
    rep = compare(rows, rows, keys=['id'])
    assert rep['ok'] is True
    # a real numeric difference alongside them is still caught
    b = [{'id': '1', 'amt': 'nan'}, {'id': '2', 'amt': 'inf'}, {'id': '3', 'amt': '11'}]
    assert compare(rows, b, keys=['id'])['ok'] is False


def test_unknown_key_raises_instead_of_vacuous_parity():
    # A typo'd --keys column made every row key (None,), collapsing both sides
    # to cardinality 1 == 1 — a silent false PARITY OK. It must raise instead.
    rows = [{'id': '1', 'amt': '10'}]
    try:
        compare(rows, rows, keys=['idd'])
    except ValueError as e:
        assert 'idd' in str(e)
    else:
        raise AssertionError('expected ValueError for unknown key column')


def test_null_mismatch_catches_a_compensating_null_swap():
    # The recorded null-blindness: row 1 loses its 0 to NULL while row 2 gains a 0.
    # Row count, group cardinality, aggregate sum AND per-column null RATE are all
    # identical, so every aggregate metric reads clean while half the rows changed
    # meaning. Aligning on the key is the only thing that sees it.
    a = [{'id': '1', 'amt': '0'}, {'id': '2', 'amt': ''}]
    b = [{'id': '1', 'amt': ''}, {'id': '2', 'amt': '0'}]
    rep = compare(a, b, keys=['id'])
    assert rep['null_rate_delta']['amt'] == 0.0
    assert 'amt' not in rep['sum_delta']
    assert rep['null_mismatch'] == {'amt': 2}
    assert rep['ok'] is False


def test_null_mismatch_answers_to_the_same_null_tol_knob():
    # Placement is the sharper view of the property --null-tol already gates, so a
    # caller who explicitly tolerates a null-rate wobble is not failed by the
    # row-level view of that same wobble. One moved null in two aligned rows = 0.5.
    a = [{'id': '1', 'label': 'x'}, {'id': '2', 'label': 'y'}]
    b = [{'id': '1', 'label': 'x'}, {'id': '2', 'label': ''}]
    assert compare(a, b, keys=['id'])['null_mismatch'] == {'label': 1}
    assert compare(a, b, keys=['id'], null_tol=0.5)['ok'] is True
    assert compare(a, b, keys=['id'], null_tol=0.4)['ok'] is False


def test_null_mismatch_not_assessed_says_so_instead_of_passing_quietly():
    # Without keys the rows cannot be aligned. The check reports UNASSESSED with a
    # reason AND withholds the pass -- freshness's ok=None doctrine, which is a
    # non-pass (its CLI exits 1), not a quiet green. This test used to assert
    # ok is True and cited that doctrine while contradicting it.
    rows = [{'id': '1', 'amt': '0'}]
    rep = compare(rows, rows)
    assert rep['null_mismatch'] is None
    assert 'keys' in rep['null_mismatch_reason']
    assert rep['ok'] is None
    assert rep['unassessed']


def test_opting_out_of_null_mismatch_is_a_clean_pass_not_an_unassessed_one():
    # The caller said "compare aggregates only". That is a decision on the record,
    # not a comparison that failed to run, so it must not be penalised.
    rows = [{'id': '1', 'amt': '0'}]
    rep = compare(rows, rows, null_mismatch=False)
    assert rep['ok'] is True
    assert rep['unassessed'] == []


def test_null_mismatch_not_assessed_when_keys_are_not_unique():
    rows = [{'id': '1', 'amt': '0'}, {'id': '1', 'amt': ''}]
    rep = compare(rows, rows, keys=['id'])
    assert rep['null_mismatch'] is None
    assert 'unique' in rep['null_mismatch_reason']
    assert rep['ok'] is None


def test_duplicate_keys_do_not_buy_a_silent_pass_on_a_real_null_swap():
    # The reproduction that was live: a null-placement swap the aggregates cannot
    # see, under a non-unique key. Every aggregate reads clean, the placement
    # comparison cannot run -- and the verdict must NOT be PARITY OK.
    a = [{'id': '1', 'amt': '0'}, {'id': '1', 'amt': ''}, {'id': '2', 'amt': '5'}]
    b = [{'id': '1', 'amt': ''}, {'id': '1', 'amt': '0'}, {'id': '2', 'amt': '5'}]
    rep = compare(a, b, keys=['id'])
    assert rep['null_rate_delta']['amt'] == 0.0
    assert rep['null_mismatch'] is None
    assert rep['ok'] is not True
    # the control: the identical drift with a unique key is a hard FAIL
    ua = [{'id': '1', 'amt': '0'}, {'id': '2', 'amt': ''}]
    ub = [{'id': '1', 'amt': ''}, {'id': '2', 'amt': '0'}]
    assert compare(ua, ub, keys=['id'])['ok'] is False


def test_cli_exits_nonzero_when_a_requested_comparison_could_not_be_made():
    import tempfile
    from pathlib import Path

    from parity_check import main

    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / 'a.csv'
        b = Path(d) / 'b.csv'
        a.write_text('id,amt\n1,0\n1,\n2,5\n', encoding='utf-8')
        b.write_text('id,amt\n1,\n1,0\n2,5\n', encoding='utf-8')
        assert main([str(a), str(b), '--keys', 'id']) == 1
        # opting out is the caller's call and stays a clean 0
        assert main([str(a), str(b), '--keys', 'id', '--no-null-mismatch']) == 0


def test_tol_col_overrides_the_global_tolerance_per_column():
    # One uniform tolerance either false-fails a known-noisy column or masks a
    # whole-value swap elsewhere. A per-column atol loosens exactly one column.
    a = [{'id': '1', 'noisy': '10', 'exact': '5'}]
    b = [{'id': '1', 'noisy': '10.5', 'exact': '5'}]
    assert compare(a, b, keys=['id'])['ok'] is False
    assert compare(a, b, keys=['id'], tol_col={'noisy': 1.0})['ok'] is True
    # the loosened column must not loosen its neighbours
    c = [{'id': '1', 'noisy': '10.5', 'exact': '6'}]
    assert compare(a, c, keys=['id'], tol_col={'noisy': 1.0})['ok'] is False


def test_residual_zero_is_a_cardinality_hazard_not_a_value_tolerance():
    # A residual column sits at 0 by construction; downstream reads it as
    # `WHERE resid > 0`. Float residue smaller than any sane value tolerance
    # still changes the ROW COUNT that filter returns, so it is counted, not
    # tolerated.
    a = [{'id': '1', 'resid': '0'}, {'id': '2', 'resid': '0'}]
    b = [{'id': '1', 'resid': '0'}, {'id': '2', 'resid': '1e-12'}]
    assert compare(a, b, keys=['id'])['ok'] is True  # sum delta is inside --tol
    rep = compare(a, b, keys=['id'], residual_zero=['resid'])
    assert rep['residual_zero']['resid'] == {'a': 0, 'b': 1, 'delta': 1}
    assert rep['ok'] is False


def test_two_producer_join_is_asserted_before_any_value_comparison():
    # The recorded HIGH finding: one writer renders the shared key as a date, the
    # other as a datetime. Both producer-local suites are green. The join matches
    # nothing, so a value comparison over the survivors would read perfectly clean.
    a = [{'settled_on': '2026-01-01', 'amount': '10'}]
    b = [{'settled_on': '2026-01-01 00:00:00', 'amount': '10'}]
    rep = two_producer_check(a, b, 'settled_on')
    assert rep['join_ok'] is False
    assert rep['matched'] == 0
    assert rep['values'] is None, 'values must not be compared over an unproven join'
    assert 'join' in rep['reason']
    assert rep['ok'] is False


def test_two_producer_join_names_the_key_shape_disagreement():
    a = [{'settled_on': '2026-01-01'}]
    b = [{'settled_on': '2026-01-01 00:00:00'}]
    rep = two_producer_check(a, b, 'settled_on')
    assert rep['key_shape'] == {'a': ['date'], 'b': ['datetime']}


def test_two_producer_partial_join_fails_even_when_every_survivor_agrees():
    # Two of three keys match and agree exactly; the third is dropped by the join.
    # Comparing survivors alone would report parity on a table missing a third of it.
    a = [{'k': '1', 'v': '5'}, {'k': '2', 'v': '5'}, {'k': '3', 'v': '5'}]
    b = [{'k': '1', 'v': '5'}, {'k': '2', 'v': '5'}, {'k': '9', 'v': '5'}]
    rep = two_producer_check(a, b, 'k')
    assert rep['join_ok'] is False
    assert rep['only_a'] == ['3'] and rep['only_b'] == ['9']
    assert rep['values'] is None


def test_two_producer_clean_join_then_compares_the_values():
    a = [{'k': '1', 'v': '5'}, {'k': '2', 'v': '5'}]
    b = [{'k': '1', 'v': '5'}, {'k': '2', 'v': '6'}]
    rep = two_producer_check(a, b, 'k')
    assert rep['join_ok'] is True
    assert rep['values'] is not None
    assert rep['values']['ok'] is False  # the value drift is caught, once the join earns it
    assert rep['ok'] is False
    same = two_producer_check(a, a, 'k')
    assert same['ok'] is True and same['values']['ok'] is True


def test_two_producer_fails_a_join_key_that_fans_out():
    # Set equality says WHICH keys appear on both sides, never HOW MANY rows carry
    # each. Two 2-row sides sharing one key value used to print `matched: 1` beside
    # `a=2 b=2` and then TWO-PRODUCER OK -- while a real SQL join on that key
    # produces four rows. COUNT(*) vs COUNT(DISTINCT key) is the assertion.
    a = [{'k': '1', 'v': '5'}, {'k': '1', 'v': '5'}]
    b = [{'k': '1', 'v': '5'}, {'k': '1', 'v': '5'}]
    rep = two_producer_check(a, b, 'k')
    assert rep['ok'] is False
    assert rep['join_ok'] is False
    assert rep['values'] is None, 'values must not be compared across a fan-out'
    assert rep['a_distinct_keys'] == 1 and rep['a_rows'] == 2
    assert 'not unique' in rep['reason']


def test_two_producer_empty_input_is_not_a_clean_join():
    # Two empty extracts join perfectly and agree on every value.
    rep = two_producer_check([], [], 'k')
    assert rep['ok'] is False
    assert 'empty' in rep['reason']


def test_cli_two_producer_mode_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / 'orders.csv'
        b = Path(d) / 'settlements.csv'
        a.write_text('settled_on,amount\n2026-01-01,10\n', encoding='utf-8')
        b.write_text('settled_on,amount\n2026-01-01 00:00:00,10\n', encoding='utf-8')
        assert main(['--two-producer', str(a), str(b), '--join-key', 'settled_on']) == 1
        b.write_text('settled_on,amount\n2026-01-01,10\n', encoding='utf-8')
        assert main(['--two-producer', str(a), str(b), '--join-key', 'settled_on']) == 0
        # a mode flag with no join key is a usage error, not a silent aggregate run
        assert main(['--two-producer', str(a), str(b)]) == 2
        assert main([str(a)]) == 2


if __name__ == '__main__':
    test_identical_tables_ok()
    test_row_count_mismatch_fails()
    test_sum_delta_detected()
    test_all_null_column_fails_even_at_loose_sum_tol()
    test_null_tol_gates_null_rate_independently()
    test_literal_nan_inf_cells_do_not_poison_sums()
    test_unknown_key_raises_instead_of_vacuous_parity()
    test_null_mismatch_catches_a_compensating_null_swap()
    test_null_mismatch_answers_to_the_same_null_tol_knob()
    test_null_mismatch_not_assessed_says_so_instead_of_passing_quietly()
    test_opting_out_of_null_mismatch_is_a_clean_pass_not_an_unassessed_one()
    test_null_mismatch_not_assessed_when_keys_are_not_unique()
    test_duplicate_keys_do_not_buy_a_silent_pass_on_a_real_null_swap()
    test_cli_exits_nonzero_when_a_requested_comparison_could_not_be_made()
    test_tol_col_overrides_the_global_tolerance_per_column()
    test_residual_zero_is_a_cardinality_hazard_not_a_value_tolerance()
    test_two_producer_join_is_asserted_before_any_value_comparison()
    test_two_producer_join_names_the_key_shape_disagreement()
    test_two_producer_partial_join_fails_even_when_every_survivor_agrees()
    test_two_producer_clean_join_then_compares_the_values()
    test_two_producer_fails_a_join_key_that_fans_out()
    test_two_producer_empty_input_is_not_a_clean_join()
    test_cli_two_producer_mode_end_to_end()
    print('ok: all parity_check tests passed')

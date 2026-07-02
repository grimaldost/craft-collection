"""Tests for parity_check.compare. Runnable with pytest or `python test_parity_check.py`."""

from __future__ import annotations

from parity_check import compare


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


if __name__ == '__main__':
    test_identical_tables_ok()
    test_row_count_mismatch_fails()
    test_sum_delta_detected()
    test_all_null_column_fails_even_at_loose_sum_tol()
    test_null_tol_gates_null_rate_independently()
    print('ok: all parity_check tests passed')

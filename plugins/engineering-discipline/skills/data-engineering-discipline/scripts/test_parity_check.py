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


if __name__ == '__main__':
    test_identical_tables_ok()
    test_row_count_mismatch_fails()
    test_sum_delta_detected()
    print('ok: all parity_check tests passed')

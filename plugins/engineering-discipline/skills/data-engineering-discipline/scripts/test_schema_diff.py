"""Tests for schema_diff.diff. Runnable with pytest or `python test_schema_diff.py`."""

from __future__ import annotations

from schema_diff import diff


def test_added_removed_retyped():
    a = {'id': 'int64', 'amount': 'float64', 'name': 'object'}
    b = {'id': 'int64', 'amount': 'int64', 'created': 'datetime64'}
    d = diff(a, b)
    assert d['added'] == ['created']
    assert d['removed'] == ['name']
    assert d['retyped'] == [('amount', 'float64', 'int64')]


def test_identical():
    a = {'id': 'int64'}
    assert diff(a, a) == {'added': [], 'removed': [], 'retyped': []}


if __name__ == '__main__':
    test_added_removed_retyped()
    test_identical()
    print('ok: all schema_diff tests passed')

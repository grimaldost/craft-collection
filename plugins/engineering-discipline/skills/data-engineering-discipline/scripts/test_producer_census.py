"""Tests for producer_census. Runnable with pytest or `python test_producer_census.py`."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from producer_census import census, load_inventory, main


def test_single_producer_per_column_is_clean():
    findings = census({'amount': ['orders.emit'], 'region': ['regions.emit']}, [])
    assert findings == []


def test_two_producers_without_a_joint_run_is_a_finding():
    findings = census({'settled_on': ['orders.emit', 'settlements.emit']}, [])
    assert len(findings) == 1
    assert findings[0]['column'] == 'settled_on'
    assert set(findings[0]['producers']) == {'orders.emit', 'settlements.emit'}


def test_a_joint_run_covering_every_producer_clears_the_column():
    findings = census(
        {'settled_on': ['orders.emit', 'settlements.emit']},
        [['orders.emit', 'settlements.emit']],
    )
    assert findings == []


def test_a_joint_run_covering_only_some_producers_does_not_clear_it():
    # Two of three writers were exercised together; the third has never been
    # compared against either, which is exactly the gap that ships a dtype drift.
    findings = census(
        {'settled_on': ['orders.emit', 'settlements.emit', 'regions.emit']},
        [['orders.emit', 'settlements.emit']],
    )
    assert len(findings) == 1
    assert 'regions.emit' in findings[0]['uncovered']


def test_empty_inventory_is_an_error_not_a_clean_pass():
    # An inventory that names nothing is the vacuous-gate shape: a census over
    # zero columns would exit 0 and be quoted as evidence.
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'inventory.json'
        path.write_text(json.dumps({'columns': {}}), encoding='utf-8')
        assert main([str(path)]) == 2


def test_flat_inventory_shape_is_accepted():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'inventory.json'
        path.write_text(
            json.dumps({'settled_on': ['orders.emit', 'settlements.emit']}), encoding='utf-8'
        )
        columns, joint = load_inventory(path)
        assert columns == {'settled_on': ['orders.emit', 'settlements.emit']}
        assert joint == []
        assert main([str(path)]) == 1


def test_clean_inventory_exits_zero():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'inventory.json'
        path.write_text(
            json.dumps(
                {
                    'columns': {'settled_on': ['orders.emit', 'settlements.emit']},
                    'joint_runs': [['orders.emit', 'settlements.emit']],
                }
            ),
            encoding='utf-8',
        )
        assert main([str(path)]) == 0


if __name__ == '__main__':
    test_single_producer_per_column_is_clean()
    test_two_producers_without_a_joint_run_is_a_finding()
    test_a_joint_run_covering_every_producer_clears_the_column()
    test_a_joint_run_covering_only_some_producers_does_not_clear_it()
    test_empty_inventory_is_an_error_not_a_clean_pass()
    test_flat_inventory_shape_is_accepted()
    test_clean_inventory_exits_zero()
    print('ok: all producer_census tests passed')

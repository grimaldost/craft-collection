"""Tests for contract_check.validate. Runnable with pytest or `python test_contract_check.py`."""

from __future__ import annotations

from contract_check import validate

CONTRACT = {
    'id': {'required': True, 'nullable': False, 'unique': True, 'dtype': 'int'},
    'status': {'enum': ['open', 'closed']},
}


def test_clean_passes():
    rows = [{'id': '1', 'status': 'open'}, {'id': '2', 'status': 'closed'}]
    assert validate(rows, CONTRACT) == []


def test_violations_detected():
    rows = [
        {'id': '1', 'status': 'open'},
        {'id': '1', 'status': 'paused'},
        {'id': '', 'status': 'open'},
    ]
    v = validate(rows, CONTRACT)
    assert any('null' in x for x in v)  # blank id but nullable=false
    assert any('enum' in x for x in v)  # 'paused' not in enum
    assert any('unique' in x for x in v)  # duplicate id '1'


if __name__ == '__main__':
    test_clean_passes()
    test_violations_detected()
    print('ok: all contract_check tests passed')

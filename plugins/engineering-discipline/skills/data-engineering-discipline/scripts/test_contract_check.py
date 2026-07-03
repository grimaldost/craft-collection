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


def test_numeric_enum_matches_string_csv_values():
    # A JSON contract enum of ints ([1, 2, 3]) vs. CSV values (always strings:
    # '1', '2', '3') must MATCH — comparison is normalized on both sides. The
    # raw `'1' in [1, 2, 3]` membership test wrongly flagged every valid row.
    contract = {'priority': {'enum': [1, 2, 3]}}
    rows = [{'priority': '1'}, {'priority': '2'}, {'priority': '3'}]
    assert validate(rows, contract) == []
    # A genuinely out-of-enum value is still caught.
    assert validate([{'priority': '4'}], contract) != []


def test_numeric_enum_consistent_with_int_dtype():
    # dtype:'int' accepts the warehouse rendering '1.0'; a numeric enum [1, 2]
    # on the same column must accept it too — the two rules must not contradict
    # each other on the same value.
    contract = {'n': {'enum': [1, 2], 'dtype': 'int'}}
    assert validate([{'n': '1.0'}], contract) == []
    # float enums match their string renderings, including trailing zeros
    assert validate([{'x': '1.5'}, {'x': '2.50'}], {'x': {'enum': [1.5, 2.5]}}) == []
    # genuinely out-of-enum numerics and non-numerics are still caught
    assert validate([{'n': '3.0'}], contract) != []
    assert validate([{'n': 'abc'}], contract) != []
    # non-numeric enums still compare as plain strings
    assert validate([{'s': 'open'}], {'s': {'enum': ['open']}}) == []
    assert validate([{'s': 'openx'}], {'s': {'enum': ['open']}}) != []


if __name__ == '__main__':
    test_clean_passes()
    test_violations_detected()
    test_numeric_enum_matches_string_csv_values()
    test_numeric_enum_consistent_with_int_dtype()
    print('ok: all contract_check tests passed')

"""The skill's own non-vacuity gate: every shipped check is held RED on a seeded
defect and GREEN on the clean copy. Runnable with pytest or `python test_mutate_check.py`.

This is the in-repo instance of Recipe 13 ("prove the check can fail"). The
2026-07-02 adversarial panel found four vacuous-gate defects in these very
scripts, so the doctrine is enforced here rather than restated.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from contract_check import validate
from freshness_check import check_freshness
from mutate_check import (
    ADVERSARIAL,
    KNOWN_GAPS,
    MUTATIONS,
    SHAPE_MUTATIONS,
    VALUE_MUTATIONS,
    coarse_schema,
    main,
    mutate,
    parity_checker,
    prove_can_fail,
    schema_checker,
)
from producer_census import census

CLEAN = ADVERSARIAL['clean']


# --- the harness proves itself first ---------------------------------------


def test_every_mutation_actually_changes_the_fixture():
    for kind in MUTATIONS:
        assert mutate(CLEAN, 'amount', kind) != CLEAN, f'{kind} left the fixture untouched'


def test_an_always_green_check_is_reported_vacuous_not_passed():
    report = prove_can_fail(lambda a, b: True, CLEAN, 'amount')
    assert report['ok'] is False
    assert sorted(report['slept_through']) == sorted(VALUE_MUTATIONS)


def test_a_check_that_reds_on_the_clean_copy_fails_too():
    # A check that fails everything catches nothing; its reds are worthless.
    report = prove_can_fail(lambda a, b: False, CLEAN, 'amount')
    assert report['clean_green'] is False
    assert report['ok'] is False


def test_a_no_op_mutation_is_not_credited_as_a_catch():
    # 'region' is constant across these two rows, so swapping it changes nothing.
    constant = [{'id': '1', 'region': 'north'}, {'id': '2', 'region': 'north'}]
    report = prove_can_fail(parity_checker(['id']), constant, 'region', ['swap_values'])
    assert report['no_op'] == ['swap_values']
    assert report['ok'] is False


# --- each shipped check, RED on the defect and GREEN on the clean copy ------


def test_parity_check_reddens_on_every_value_mutation_except_its_documented_gap():
    report = prove_can_fail(
        parity_checker(['id']), CLEAN, 'amount', VALUE_MUTATIONS, KNOWN_GAPS['parity']
    )
    assert report['ok'] is True
    assert report['slept_through'] == []
    # parity_check.py's docstring says a sum- and count-preserving value swap
    # passes it. That claim is pinned here: if the gap ever closes, the docstring
    # is wrong and this test says so.
    assert report['known_gaps_confirmed'] == ['swap_values']
    assert report['gaps_closed'] == []


def test_schema_check_reddens_on_every_shape_mutation_except_its_documented_gap():
    report = prove_can_fail(
        schema_checker(), CLEAN, 'amount', SHAPE_MUTATIONS, KNOWN_GAPS['schema']
    )
    assert report['ok'] is True
    assert report['slept_through'] == []
    # schema_diff.py says a stdlib (no-pandas) read cannot see a retype: '10' and
    # '10.0' are one class to it. The blind spot is pinned, not papered over -
    # which is why that tool exits NON-ZERO rather than claiming 'schemas match'.
    assert report['known_gaps_confirmed'] == ['retype_column']


CONTRACT = {
    'id': {'dtype': 'int', 'nullable': False},
    'region': {'dtype': 'str', 'enum': ['north', 'south']},
    'amount': {'dtype': 'float', 'nullable': False},
}


def test_contract_check_is_green_on_clean_and_red_on_the_seeded_defects():
    assert validate(CLEAN, CONTRACT) == []
    assert validate(ADVERSARIAL['invalid_types'], CONTRACT) != []  # 'n/a' in a float column
    assert validate(ADVERSARIAL['nulls'], CONTRACT) != []  # blanks under nullable=false


def test_contract_check_accepts_warehouse_int_rendering():
    # '1.0' for an int column is a rendering, not a violation - the enum/int
    # contradiction the adversarial panel filed. It must stay GREEN here so the
    # reds above are informative.
    assert validate(ADVERSARIAL['int_rendering'], {'id': {'dtype': 'int', 'nullable': False}}) == []


def test_a_contract_shape_the_validator_cannot_read_is_not_a_pass():
    # Found by this harness: a nested contract validated nothing and returned
    # green over rows that violate it.
    try:
        validate(ADVERSARIAL['invalid_types'], {'columns': CONTRACT})
    except ValueError:
        pass
    else:
        raise AssertionError('a nested contract must raise, not validate nothing')


def test_freshness_check_is_green_on_advance_and_red_on_the_seeded_defects():
    assert check_freshness(1, 2)['ok'] is True
    assert check_freshness(2, 2)['ok'] is False  # frozen cursor
    naive = datetime(2026, 1, 31)
    aware = datetime(2026, 1, 31, tzinfo=timezone.utc)
    assert check_freshness(naive, aware)['ok'] is False  # tz-mixed cursors
    assert check_freshness('2026-01-30', '2026-01-31')['ok'] is False  # string cursors
    assert check_freshness(None, None)['ok'] is not True  # unassessable is never a pass


def test_parity_check_is_green_on_literal_nan_and_red_on_real_drift():
    nan_rows = ADVERSARIAL['literal_nan']
    checker = parity_checker(['id'])
    assert checker(nan_rows, nan_rows) is True
    drifted = [dict(r) for r in nan_rows]
    drifted[2]['amount'] = '11'
    assert checker(nan_rows, drifted) is False


def test_producer_census_is_green_on_one_writer_and_red_on_two():
    assert census({'amount': ['orders.emit']}, []) == []
    assert census({'settled_on': ['orders.emit', 'settlements.emit']}, []) != []


def test_duplicate_keys_do_not_buy_a_silent_parity_pass():
    # The duplicates fixture cannot be aligned one-to-one, so the null-placement
    # comparison must report UNASSESSED rather than contribute a quiet pass.
    from parity_check import compare

    rep = compare(ADVERSARIAL['duplicates'], ADVERSARIAL['duplicates'], keys=['id'])
    assert rep['null_mismatch'] is None
    assert 'unique' in rep['null_mismatch_reason']


# --- the CLI ---------------------------------------------------------------


def test_cli_runs_the_harness_and_refuses_an_empty_fixture():
    with tempfile.TemporaryDirectory() as d:
        good = Path(d) / 'fixture.csv'
        good.write_text(
            'id,region,amount\n1,north,10.5\n2,south,20.25\n3,north,0\n', encoding='utf-8'
        )
        assert main([str(good), '--check', 'parity', '--keys', 'id', '--column', 'amount']) == 0
        empty = Path(d) / 'empty.csv'
        empty.write_text('id,amount\n', encoding='utf-8')
        assert main([str(empty), '--column', 'amount']) == 2
        assert main([str(good), '--column', 'nope']) == 2


def test_coarse_schema_names_the_columns_it_saw():
    assert coarse_schema(CLEAN) == {
        'id': 'number',
        'region': 'text',
        'amount': 'number',
        'settled_on': 'text',
    }


if __name__ == '__main__':
    test_every_mutation_actually_changes_the_fixture()
    test_an_always_green_check_is_reported_vacuous_not_passed()
    test_a_check_that_reds_on_the_clean_copy_fails_too()
    test_a_no_op_mutation_is_not_credited_as_a_catch()
    test_parity_check_reddens_on_every_value_mutation_except_its_documented_gap()
    test_schema_check_reddens_on_every_shape_mutation_except_its_documented_gap()
    test_contract_check_is_green_on_clean_and_red_on_the_seeded_defects()
    test_contract_check_accepts_warehouse_int_rendering()
    test_a_contract_shape_the_validator_cannot_read_is_not_a_pass()
    test_freshness_check_is_green_on_advance_and_red_on_the_seeded_defects()
    test_parity_check_is_green_on_literal_nan_and_red_on_real_drift()
    test_producer_census_is_green_on_one_writer_and_red_on_two()
    test_duplicate_keys_do_not_buy_a_silent_parity_pass()
    test_cli_runs_the_harness_and_refuses_an_empty_fixture()
    test_coarse_schema_names_the_columns_it_saw()
    print('ok: all mutate_check tests passed')

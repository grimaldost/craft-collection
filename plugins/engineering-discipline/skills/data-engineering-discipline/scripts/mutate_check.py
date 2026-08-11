#!/usr/bin/env python3
"""Mutation harness: prove a data check can fail before trusting it green.

A check seen only green is indistinguishable from one that tests nothing. This
repo's own adversarial panel found four such defects IN THESE VERY SCRIPTS,
including a parity gate that silently disabled its cardinality check when the
key column was misnamed -- a vacuous pass on exactly the regression the check
exists to catch. So the recipe becomes a runnable harness: perturb one column of
a fixture, assert the named check REDDENS, and report the mutations it slept
through.

The harness verifies itself two ways. A mutation that leaves the fixture
byte-identical is reported as `no_op` rather than counted as a caught defect
(the vacuous-harness shape), and the check must be GREEN on the unmutated copy
before any red is credited -- a check that fails everything catches nothing.

    python mutate_check.py fixture.csv --check parity --keys id --column amount
    python mutate_check.py fixture.csv --check schema --column amount

`ADVERSARIAL` ships the seeded fixtures the shipped checks are held against:
nulls beside zeros, boundary timestamps, duplicate keys, late arrivals, invalid
types, tz-mixed cursors, literal `nan`, and warehouse `'1.0'` int rendering.

Exit 0 when every mutation reddened the check, 1 when any slept through, 2 on a
usage error. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable, Sequence

from parity_check import compare
from schema_diff import diff

# --- the seeded fixture set ------------------------------------------------
# Each entry is a small table whose defect is the one named by its key. They are
# data, not tests: the paired test module holds each shipped check against them.
ADVERSARIAL: dict[str, list[dict]] = {
    'clean': [
        {'id': '1', 'region': 'north', 'amount': '10.5', 'settled_on': '2026-01-31'},
        {'id': '2', 'region': 'south', 'amount': '20.25', 'settled_on': '2026-02-28'},
        {'id': '3', 'region': 'north', 'amount': '0', 'settled_on': '2026-03-31'},
    ],
    'nulls': [
        {'id': '1', 'region': 'north', 'amount': '', 'settled_on': '2026-01-31'},
        {'id': '2', 'region': '', 'amount': '0', 'settled_on': '2026-02-28'},
        {'id': '3', 'region': 'north', 'amount': '0', 'settled_on': '2026-03-31'},
    ],
    'boundary_timestamps': [
        {'id': '1', 'region': 'north', 'amount': '1', 'settled_on': '2025-12-31'},
        {'id': '2', 'region': 'south', 'amount': '1', 'settled_on': '2026-01-01'},
        {'id': '3', 'region': 'north', 'amount': '1', 'settled_on': '2026-02-29'},
    ],
    'duplicates': [
        {'id': '1', 'region': 'north', 'amount': '10.5', 'settled_on': '2026-01-31'},
        {'id': '1', 'region': 'north', 'amount': '10.5', 'settled_on': '2026-01-31'},
        {'id': '2', 'region': 'south', 'amount': '20.25', 'settled_on': '2026-02-28'},
    ],
    'late_arrivals': [
        {'id': '4', 'region': 'north', 'amount': '5', 'settled_on': '2025-11-30'},
        {'id': '5', 'region': 'south', 'amount': '5', 'settled_on': '2025-10-31'},
    ],
    'invalid_types': [
        {'id': '1', 'region': 'north', 'amount': 'n/a', 'settled_on': '2026-01-31'},
        {'id': '2', 'region': 'south', 'amount': '20.25', 'settled_on': 'unknown'},
    ],
    'tz_mixed_cursors': [
        {'id': '1', 'region': 'north', 'amount': '1', 'settled_on': '2026-01-31 00:00:00'},
        {'id': '2', 'region': 'south', 'amount': '1', 'settled_on': '2026-01-31 00:00:00+00:00'},
    ],
    'literal_nan': [
        {'id': '1', 'region': 'north', 'amount': 'nan', 'settled_on': '2026-01-31'},
        {'id': '2', 'region': 'south', 'amount': 'inf', 'settled_on': '2026-02-28'},
        {'id': '3', 'region': 'north', 'amount': '10', 'settled_on': '2026-03-31'},
    ],
    'int_rendering': [
        {'id': '1.0', 'region': 'north', 'amount': '10.0', 'settled_on': '2026-01-31'},
        {'id': '2.0', 'region': 'south', 'amount': '20.0', 'settled_on': '2026-02-28'},
    ],
}


# --- mutations -------------------------------------------------------------


def drop_row(rows: list[dict], column: str) -> list[dict]:
    return [dict(r) for r in rows[:-1]]


def null_column(rows: list[dict], column: str) -> list[dict]:
    out = [dict(r) for r in rows]
    if out:
        out[0][column] = ''
    return out


def perturb_cell(rows: list[dict], column: str) -> list[dict]:
    out = [dict(r) for r in rows]
    if not out:
        return out
    value = out[0].get(column)
    try:
        out[0][column] = str(float(value) + 1)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        out[0][column] = f'{value}X'
    return out


def swap_values(rows: list[dict], column: str) -> list[dict]:
    out = [dict(r) for r in rows]
    if len(out) >= 2:
        out[0][column], out[1][column] = out[1].get(column), out[0].get(column)
    return out


def duplicate_row(rows: list[dict], column: str) -> list[dict]:
    out = [dict(r) for r in rows]
    if out:
        out.append(dict(out[0]))
    return out


def drop_column(rows: list[dict], column: str) -> list[dict]:
    return [{k: v for k, v in r.items() if k != column} for r in rows]


def retype_column(rows: list[dict], column: str) -> list[dict]:
    """Render a numeric column the way a warehouse export does ('1' -> '1.0')."""
    out = [dict(r) for r in rows]
    for r in out:
        try:
            r[column] = f'{float(r[column]):.1f}'
        except (TypeError, ValueError, KeyError):
            r[column] = f'{r.get(column)}!'
    return out


def retype_to_text(rows: list[dict], column: str) -> list[dict]:
    """Move a numeric column out of its type class entirely ('10.5' -> '10.5 USD')."""
    out = [dict(r) for r in rows]
    for r in out:
        r[column] = f'{r.get(column)} USD'
    return out


MUTATIONS: dict[str, Callable[[list[dict], str], list[dict]]] = {
    'drop_row': drop_row,
    'null_column': null_column,
    'perturb_cell': perturb_cell,
    'swap_values': swap_values,
    'duplicate_row': duplicate_row,
    'drop_column': drop_column,
    'retype_column': retype_column,
    'retype_to_text': retype_to_text,
}

VALUE_MUTATIONS = ('drop_row', 'null_column', 'perturb_cell', 'swap_values', 'duplicate_row')
SHAPE_MUTATIONS = ('drop_column', 'retype_column', 'retype_to_text')

# Mutations a shipped check DOCUMENTS that it cannot see. Declared, not
# discovered: `parity_check.py`'s own docstring says a sum- and count-preserving
# value swap passes it, and `schema_diff.py` says a stdlib read cannot see a
# retype at all. So the harness must not report those as vacuities - and must
# report them if they ever stop being true.
KNOWN_GAPS: dict[str, tuple[str, ...]] = {
    'parity': ('swap_values',),
    'schema': ('retype_column',),
}


def mutate(rows: list[dict], column: str, kind: str) -> list[dict]:
    if kind not in MUTATIONS:
        raise ValueError(f'unknown mutation {kind!r}; known: {sorted(MUTATIONS)}')
    return MUTATIONS[kind](rows, column)


# --- the harness -----------------------------------------------------------


def prove_can_fail(
    check: Callable[[list[dict], list[dict]], bool],
    rows: list[dict],
    column: str,
    kinds: Sequence[str] = VALUE_MUTATIONS,
    known_gaps: Sequence[str] = (),
) -> dict:
    """Run `check(clean, mutated)` for each mutation. `check` returns True = GREEN.

    Returns {'clean_green', 'results', 'slept_through', 'no_op',
    'known_gaps_confirmed', 'gaps_closed', 'ok'}. `ok` requires the check to be
    green on the unmutated copy AND red on every mutation that actually changed
    the fixture. A mutation that changed nothing is recorded under `no_op` and
    fails the run: crediting it as a catch is the harness's own vacuous-gate
    shape.

    `known_gaps` names mutations the check DOCUMENTS that it cannot see (an
    aggregate parity diff cannot see a sum-preserving value swap). They do not
    fail the run, but they are reported either way -- confirmed, or closed, which
    means the docstring that claims the gap is now wrong. Pure apart from `check`.
    """
    results: dict[str, bool] = {}
    no_op: list[str] = []
    for kind in kinds:
        mutated = mutate(rows, column, kind)
        if mutated == rows:
            no_op.append(kind)
            continue
        results[kind] = bool(check(rows, mutated))
    clean_green = bool(check(rows, rows))
    gaps = set(known_gaps)
    slept = sorted(k for k, green in results.items() if green and k not in gaps)
    return {
        'clean_green': clean_green,
        'results': results,
        'slept_through': slept,
        'no_op': no_op,
        'known_gaps_confirmed': sorted(k for k in gaps if results.get(k) is True),
        'gaps_closed': sorted(k for k in gaps if results.get(k) is False),
        'ok': clean_green and not slept and not no_op,
    }


def parity_checker(keys: list[str], **kwargs) -> Callable[[list[dict], list[dict]], bool]:
    return lambda a, b: bool(compare(a, b, keys=keys, **kwargs)['ok'])


def coarse_schema(rows: list[dict]) -> dict[str, str]:
    """{column: 'number'|'text'|'empty'} over a list[dict]. Coarse on purpose:
    a CSV read has no dtypes, and this exists to give the schema check something
    a retype can move, not to replace a real dtype diff."""
    cols: list[str] = []
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)
    schema: dict[str, str] = {}
    for c in cols:
        values = [r.get(c) for r in rows if r.get(c) not in (None, '')]
        if not values:
            schema[c] = 'empty'
            continue
        numeric = all(_is_number(v) for v in values)
        schema[c] = 'number' if numeric else 'text'
    return schema


def _is_number(v: object) -> bool:
    try:
        float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def schema_checker() -> Callable[[list[dict], list[dict]], bool]:
    return lambda a, b: not any(diff(coarse_schema(a), coarse_schema(b)).values())


def _read_csv(path: str) -> list[dict]:
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Prove a data check can fail.')
    parser.add_argument('fixture', help='CSV the check is run against')
    parser.add_argument('--check', choices=('parity', 'schema'), default='parity')
    parser.add_argument('--column', required=True, help='column to perturb')
    parser.add_argument('--keys', default='', help='comma-separated key columns (parity)')
    args = parser.parse_args(argv)

    rows = _read_csv(args.fixture)
    if not rows:
        print('error: fixture has no rows - a mutation harness over nothing proves nothing')
        return 2
    if args.column not in coarse_schema(rows):
        print(f'error: column {args.column!r} is not in the fixture')
        return 2
    if args.check == 'parity':
        checker = parity_checker([k for k in args.keys.split(',') if k])
        kinds: Sequence[str] = VALUE_MUTATIONS
    else:
        checker = schema_checker()
        kinds = SHAPE_MUTATIONS

    gaps = KNOWN_GAPS[args.check]
    report = prove_can_fail(checker, rows, args.column, kinds, gaps)
    print(f'clean copy: {"GREEN" if report["clean_green"] else "RED"} (must be GREEN)')
    for kind, green in sorted(report['results'].items()):
        if kind in gaps:
            state = 'GREEN - documented gap' if green else 'RED - documented gap now closed'
        else:
            state = 'GREEN - slept through' if green else 'RED - caught'
        print(f'  {kind}: {state}')
    for kind in report['no_op']:
        print(f'  {kind}: NO-OP - the mutation changed nothing, so it proves nothing')
    if report['ok']:
        print('MUTATION OK: the check reddened on every seeded defect')
        return 0
    print('MUTATION FAILED: this check is vacuous for the mutations listed above')
    return 1


if __name__ == '__main__':
    sys.exit(main())

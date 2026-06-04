#!/usr/bin/env python3
"""Validate a dataset against a contract.

Pure core `validate(rows, contract)` works on list[dict] + a contract dict:

    {column: {required?: bool, nullable?: bool, enum?: [...],
              unique?: bool, dtype?: 'int' | 'float' | 'str'}}

Returns a list of violation strings. The CLI reads a CSV + a contract JSON.

Usage:
    python contract_check.py data.csv contract.json

Exit 1 if any violation. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys


def _blank(v: object) -> bool:
    return v is None or v == ''


def _typed_ok(v: object, dtype: str) -> bool:
    if dtype == 'str':
        return True
    if dtype == 'int':
        # Accept integer-VALUED numerics ('1.0', 2.0, '2') — the normal CSV/warehouse
        # rendering of an int column — while rejecting non-integers ('1.5') and
        # non-numbers. (int('1.0') raises, so the naive int(v) cried wolf on valid data.)
        try:
            return float(v).is_integer()  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    try:
        float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


def validate(rows: list[dict], contract: dict) -> list[str]:
    """Return a list of contract violation strings (empty == valid)."""
    violations: list[str] = []
    for col, rule in contract.items():
        values = [r.get(col) for r in rows]

        if rule.get('required') and rows and not all(col in r for r in rows):
            violations.append(f'{col}: required column missing from some rows')

        if not rule.get('nullable', True):
            n = sum(_blank(v) for v in values)
            if n:
                violations.append(f'{col}: {n} null value(s) but nullable=false')

        enum = rule.get('enum')
        if enum is not None:
            bad = sorted({str(v) for v in values if not _blank(v) and v not in enum})
            if bad:
                violations.append(f'{col}: values outside enum: {bad[:5]}')

        if rule.get('unique'):
            nonblank = [v for v in values if not _blank(v)]
            if len(set(nonblank)) != len(nonblank):
                violations.append(f'{col}: duplicate values but unique=true')

        dtype = rule.get('dtype')
        if dtype:
            bad_n = sum(not _typed_ok(v, dtype) for v in values if not _blank(v))
            if bad_n:
                violations.append(f'{col}: {bad_n} value(s) not {dtype}')

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate a CSV against a contract JSON.')
    parser.add_argument('data', help='CSV file')
    parser.add_argument('contract', help='contract JSON file')
    args = parser.parse_args(argv)

    with open(args.data, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    with open(args.contract, encoding='utf-8') as fh:
        contract = json.load(fh)

    violations = validate(rows, contract)
    for v in violations:
        print(f'  ! {v}')
    print('CONTRACT OK' if not violations else f'{len(violations)} violation(s)')
    return 1 if violations else 0


if __name__ == '__main__':
    sys.exit(main())

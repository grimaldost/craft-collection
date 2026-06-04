#!/usr/bin/env python3
"""Parity check between two datasets.

Compares row count, group cardinality (distinct key combos), per-column null
rate, and numeric aggregate sums within a tolerance. Pure core
`compare(rows_a, rows_b, keys, tol)` works on list[dict]; the CLI reads two CSVs.

Usage:
    python parity_check.py baseline.csv candidate.csv --keys id,as_of --tol 1e-6

Exit 1 if any metric is out of tolerance. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import sys


def _is_blank(v: object) -> bool:
    return v is None or v == ''


def _to_float(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def compare(rows_a: list[dict], rows_b: list[dict],
            keys: list[str] | None = None, tol: float = 1e-9) -> dict:
    """Compare two list[dict] tables. Returns a report dict with an 'ok' flag."""
    keys = keys or []
    report: dict = {'row_count': {'a': len(rows_a), 'b': len(rows_b),
                                  'delta': len(rows_b) - len(rows_a)}}

    def card(rows: list[dict]) -> int | None:
        return len({tuple(r.get(k) for k in keys) for r in rows}) if keys else None

    report['group_cardinality'] = {'a': card(rows_a), 'b': card(rows_b)}

    cols: set[str] = set()
    for r in (*rows_a, *rows_b):
        cols.update(r)

    def null_rate(rows: list[dict], c: str) -> float:
        return sum(_is_blank(r.get(c)) for r in rows) / len(rows) if rows else 0.0

    report['null_rate_delta'] = {
        c: null_rate(rows_b, c) - null_rate(rows_a, c) for c in sorted(cols)
    }

    def col_sum(rows: list[dict], c: str) -> float:
        return sum(v for v in (_to_float(r.get(c)) for r in rows) if v is not None)

    sums: dict[str, dict] = {}
    for c in sorted(cols):
        sa, sb = col_sum(rows_a, c), col_sum(rows_b, c)
        if sa or sb:
            sums[c] = {'a': sa, 'b': sb, 'delta': sb - sa}
    report['sum_delta'] = sums

    report['ok'] = (
        report['row_count']['delta'] == 0
        and report['group_cardinality']['a'] == report['group_cardinality']['b']
        and all(abs(v) <= tol for v in report['null_rate_delta'].values())
        and all(abs(s['delta']) <= tol for s in sums.values())
    )
    return report


def _read_csv(path: str) -> list[dict]:
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Parity-check two datasets.')
    parser.add_argument('baseline')
    parser.add_argument('candidate')
    parser.add_argument('--keys', default='', help='comma-separated key columns')
    parser.add_argument('--tol', type=float, default=1e-9)
    args = parser.parse_args(argv)

    keys = [k for k in args.keys.split(',') if k]
    rep = compare(_read_csv(args.baseline), _read_csv(args.candidate), keys, args.tol)
    rc = rep['row_count']
    print(f"row count: {rc['a']} -> {rc['b']} (delta {rc['delta']})")
    gc = rep['group_cardinality']
    print(f"group cardinality: {gc['a']} -> {gc['b']}")
    for c, s in rep['sum_delta'].items():
        if abs(s['delta']) > args.tol:
            print(f"  sum {c}: delta {s['delta']}")
    print('PARITY OK' if rep['ok'] else 'PARITY FAILED')
    return 0 if rep['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())

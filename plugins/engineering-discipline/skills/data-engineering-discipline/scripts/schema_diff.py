#!/usr/bin/env python3
"""Diff two dataset schemas (columns + dtypes).

Pure core `diff(schema_a, schema_b)` works on {column: dtype} dicts. The CLI
compares two CSV files (dtypes via pandas if installed, else column presence).

Usage:
    python schema_diff.py baseline.csv candidate.csv

Exit 1 if schemas differ. Stdlib-first; pandas optional.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def diff(schema_a: dict[str, str], schema_b: dict[str, str]) -> dict:
    """Return {added, removed, retyped} comparing baseline `a` -> candidate `b`."""
    a, b = dict(schema_a), dict(schema_b)
    return {
        'added': sorted(set(b) - set(a)),
        'removed': sorted(set(a) - set(b)),
        'retyped': sorted((c, a[c], b[c]) for c in set(a) & set(b) if a[c] != b[c]),
    }


def _csv_schema(path: Path) -> dict[str, str]:
    """Infer {column: dtype} from a CSV. dtype is 'unknown' without pandas."""
    try:
        import pandas as pd  # optional dependency
    except ImportError:
        with Path(path).open(newline='', encoding='utf-8') as fh:
            return {c: 'unknown' for c in next(csv.reader(fh), [])}
    frame = pd.read_csv(path, nrows=1000)
    return {str(c): str(t) for c, t in frame.dtypes.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Diff two dataset schemas.')
    parser.add_argument('baseline')
    parser.add_argument('candidate')
    args = parser.parse_args(argv)

    d = diff(_csv_schema(Path(args.baseline)), _csv_schema(Path(args.candidate)))
    for col in d['added']:
        print(f'+ added   {col}')
    for col in d['removed']:
        print(f'- removed {col}')
    for col, old, new in d['retyped']:
        print(f'~ retyped {col}: {old} -> {new}')
    changed = any(d.values())
    print('\nschemas differ' if changed else '\nschemas match')
    return 1 if changed else 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Diff two dataset schemas (columns + dtypes).

Pure core `diff(schema_a, schema_b)` works on {column: dtype} dicts. The CLI
compares two CSV files: real dtypes via pandas when installed (a full read by
default; cap with --nrows), else COLUMN NAMES ONLY. Without pandas the tool does
NOT claim a dtype-level match it never checked — it exits non-zero with a loud
"dtype comparison SKIPPED" notice, because an int->str retype is invisible to a
header-only read and a false "schemas match" is the failure this guards.

Usage:
    python schema_diff.py baseline.csv candidate.csv
    python schema_diff.py baseline.csv candidate.csv --nrows 5000

Exit 1 if schemas differ; exit 2 if columns match but dtypes were unchecked
(no pandas). Stdlib-first; pandas optional.
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


def _csv_schema(path: Path, nrows: int | None = None) -> tuple[dict[str, str], bool]:
    """Infer ({column: dtype}, dtypes_checked) from a CSV.

    With pandas: real dtypes over `nrows` rows (None = the full file) and
    dtypes_checked=True. Without pandas: column names only, every dtype 'unknown'
    and dtypes_checked=False — so the caller must NOT report a dtype-level match
    it never verified (an int->str retype is invisible to a header-only read).
    """
    try:
        import pandas as pd  # optional dependency
    except ImportError:
        with Path(path).open(newline='', encoding='utf-8') as fh:
            return dict.fromkeys(next(csv.reader(fh), []), 'unknown'), False
    frame = pd.read_csv(path, nrows=nrows)
    return {str(c): str(t) for c, t in frame.dtypes.items()}, True


def verdict(d: dict, dtypes_checked: bool) -> tuple[list[str], int]:
    """Summary lines + exit code for a diff result.

    Columns changed -> 'schemas differ' (exit 1). Columns match AND dtypes were
    verified -> 'schemas match' (exit 0). Columns match but dtypes were NOT
    verified (no pandas) -> a loud SKIPPED notice and a NON-ZERO exit, never a
    silent 'schemas match' — the retype the tool couldn't see must not read clean.
    """
    if any(d.values()):
        return (['', 'schemas differ'], 1)
    if dtypes_checked:
        return (['', 'schemas match'], 0)
    return (
        [
            '',
            'dtype comparison SKIPPED (pandas not installed) - column-presence only.',
            'Columns match, but a retype (e.g. int -> str) cannot be seen without pandas.',
            'Install pandas (uv add --group dev pandas) for a real dtype diff.',
        ],
        2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Diff two dataset schemas.')
    parser.add_argument('baseline')
    parser.add_argument('candidate')
    parser.add_argument(
        '--nrows',
        type=int,
        default=None,
        help='rows to scan for dtype inference (pandas only); default: full file. '
        'A cap can hide a retype that only appears in later rows.',
    )
    args = parser.parse_args(argv)

    schema_a, checked_a = _csv_schema(Path(args.baseline), args.nrows)
    schema_b, checked_b = _csv_schema(Path(args.candidate), args.nrows)
    d = diff(schema_a, schema_b)
    for col in d['added']:
        print(f'+ added   {col}')
    for col in d['removed']:
        print(f'- removed {col}')
    for col, old, new in d['retyped']:
        print(f'~ retyped {col}: {old} -> {new}')
    lines, code = verdict(d, checked_a and checked_b)
    for line in lines:
        print(line)
    return code


if __name__ == '__main__':
    sys.exit(main())

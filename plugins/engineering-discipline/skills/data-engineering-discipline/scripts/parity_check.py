#!/usr/bin/env python3
"""Parity check between two datasets.

Compares row count, group cardinality (distinct key combos), per-column null
rate, and numeric aggregate sums within a tolerance. Pure core
`compare(rows_a, rows_b, keys, tol)` works on list[dict]; the CLI reads two CSVs.

AGGREGATE-LEVEL ONLY — and not sufficient on its own. A value swap or duplicate
substitution that preserves sums and counts passes here, and float() coercion can
miss sub-cent Decimal drift. Treat PARITY OK as necessary-not-sufficient: confirm
with a row-level diff (parity-recipes.md, Recipe 6) before declaring true parity.

Usage:
    python parity_check.py baseline.csv candidate.csv --keys id,as_of --tol 1e-6
    python parity_check.py --two-producer orders.csv settlements.csv --join-key settled_on

Beyond the aggregates: `--tol-col NAME=ATOL` loosens one column without loosening
its neighbours; `--residual-zero NAME` compares the NON-ZERO ROW COUNT of a column
that sits at zero by construction (a downstream `> 0` filter turns residue into a
cardinality change); the key-aligned null-placement comparison runs by default and
answers to `--null-tol` (`--no-null-mismatch` opts out); `--two-producer` asserts
the join between two writers of one shared column BEFORE comparing any value.

Exit 1 if any metric is out of tolerance. Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys


def _is_blank(v: object) -> bool:
    return v is None or v == ''


def _to_float(v: object) -> float | None:
    # Literal 'nan'/'inf' cells pass float() but poison every sum they touch
    # (nan - nan = nan fails all tolerances, so identical tables would FAIL).
    # Treat non-finite values as non-numeric, like text: excluded from sums.
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _key_of(row: dict, keys: list[str]) -> tuple:
    return tuple(row.get(k) for k in keys)


def null_mismatch_counts(
    rows_a: list[dict], rows_b: list[dict], keys: list[str], cols: list[str]
) -> tuple[dict[str, int] | None, int, str]:
    """Per-column count of key-aligned rows whose blank/non-blank state DIFFERS.

    Returns (counts, aligned_rows, reason). `counts` is None when the comparison
    could not be made and `reason` says why -- never a silent skip: null
    placement is the drift an aggregate null RATE cannot see (row 1 loses its 0
    to NULL while row 2 gains one, and every aggregate reads clean). Pure.
    """
    if not keys:
        return None, 0, 'no keys given: rows cannot be aligned, so null placement is not compared'
    ka = [_key_of(r, keys) for r in rows_a]
    kb = [_key_of(r, keys) for r in rows_b]
    if len(set(ka)) != len(ka) or len(set(kb)) != len(kb):
        return None, 0, 'key columns are not unique: rows cannot be aligned one-to-one'
    ia = dict(zip(ka, rows_a, strict=True))
    ib = dict(zip(kb, rows_b, strict=True))
    shared = ia.keys() & ib.keys()
    counts = {}
    for c in cols:
        n = sum(1 for k in shared if _is_blank(ia[k].get(c)) != _is_blank(ib[k].get(c)))
        if n:
            counts[c] = n
    return counts, len(shared), ''


def _nonzero_count(rows: list[dict], col: str) -> int:
    """Rows whose `col` is numeric and not exactly zero."""
    return sum(1 for r in rows if (f := _to_float(r.get(col))) is not None and f != 0.0)


def compare(
    rows_a: list[dict],
    rows_b: list[dict],
    keys: list[str] | None = None,
    tol: float = 1e-9,
    null_tol: float = 0.0,
    *,
    tol_col: dict[str, float] | None = None,
    residual_zero: list[str] | None = None,
    null_mismatch: bool = True,
) -> dict:
    """Compare two list[dict] tables. Returns a report dict with an 'ok' flag.

    `tol` gates the numeric-sum deltas; `null_tol` gates the per-column null-rate
    deltas SEPARATELY (default 0.0 = no null-rate change tolerated). Keeping them
    separate is deliberate: a loose sum `tol` must never silence a null-rate jump,
    or a column going 100% NULL would pass PARITY OK while its sums stay flat.

    `tol_col` overrides `tol` for named columns, because one uniform tolerance
    either false-fails a known-noisy column or masks a whole-value swap elsewhere.
    `residual_zero` names columns that sit at zero by construction: their NON-ZERO
    ROW COUNT is compared, since a downstream `> 0` filter turns residue smaller
    than any value tolerance into rows appearing or disappearing -- a cardinality
    hazard, not a value one. `null_mismatch` (default on) compares blank placement
    row by row and needs unique `keys`; without them it reports UNASSESSED.
    """
    keys = keys or []
    report: dict = {
        'row_count': {'a': len(rows_a), 'b': len(rows_b), 'delta': len(rows_b) - len(rows_a)}
    }

    cols: set[str] = set()
    for r in (*rows_a, *rows_b):
        cols.update(r)

    # A key column absent from BOTH tables would make every row key (None,),
    # collapsing both sides to cardinality 1 and vacuously passing the check —
    # a typo'd --keys must be an error, never a silent PARITY OK.
    missing = [k for k in keys if k not in cols]
    if missing and cols:
        raise ValueError(f'key column(s) not found in either table: {missing}')

    def card(rows: list[dict]) -> int | None:
        return len({tuple(r.get(k) for k in keys) for r in rows}) if keys else None

    report['group_cardinality'] = {'a': card(rows_a), 'b': card(rows_b)}

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
    tol_col = tol_col or {}
    report['tol_col'] = tol_col

    mismatch, aligned, reason = (
        null_mismatch_counts(rows_a, rows_b, keys, sorted(cols))
        if null_mismatch
        else (None, 0, 'disabled by --no-null-mismatch')
    )
    report['null_mismatch'] = mismatch
    report['null_mismatch_rows'] = aligned
    report['null_mismatch_reason'] = reason

    resid: dict[str, dict] = {}
    for c in residual_zero or []:
        na, nb = _nonzero_count(rows_a, c), _nonzero_count(rows_b, c)
        resid[c] = {'a': na, 'b': nb, 'delta': nb - na}
    report['residual_zero'] = resid

    # The explicit isfinite guard keeps a non-finite delta (sum overflow to inf,
    # inf - inf = nan) a FAILURE even if a refactor ever inverts the comparison —
    # nan compares False both ways, so `not (abs > tol)` would silently pass it.
    report['ok'] = (
        report['row_count']['delta'] == 0
        and report['group_cardinality']['a'] == report['group_cardinality']['b']
        and all(abs(v) <= null_tol for v in report['null_rate_delta'].values())
        and all(
            math.isfinite(s['delta']) and abs(s['delta']) <= tol_col.get(c, tol)
            for c, s in sums.items()
        )
        # Placement is the sharper view of the SAME property the null-rate delta
        # gates, so it answers to the same knob: --null-tol 0 (the default) admits
        # no moved null, and a caller who explicitly tolerates null-rate wobble is
        # not then failed by the row-level view of that wobble.
        and all(n / aligned <= null_tol for n in (mismatch or {}).values() if aligned)
        and all(r['delta'] == 0 for r in resid.values())
    )
    return report


_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}')


def _shape(v: object) -> str:
    """Coarse rendering class of a key cell. Names the disagreement a bare
    'joined 0 rows' hides: a Date and a Datetime writing the same logical day."""
    if _is_blank(v):
        return 'blank'
    s = str(v)
    if _DATE.match(s):
        return 'date'
    if _DATETIME.match(s):
        return 'datetime'
    return 'number' if _to_float(s) is not None else 'text'


def two_producer_check(
    rows_a: list[dict], rows_b: list[dict], join_key: str, **compare_kwargs
) -> dict:
    """Two producers of one shared column: ASSERT THE JOIN, THEN the values.

    A dtype or rendering disagreement on the join key drops rows silently, and a
    value comparison over the survivors reads clean -- which is how a `Date` vs
    `Datetime` drift between two writers survived a large suite, a full review and
    an audit. So the join is the first-class result here: unless every row on both
    sides matched, `values` stays None and nothing is claimed about the values.
    Two empty extracts join perfectly, so an empty side is a failure, not a pass.
    """
    ka = [str(r.get(join_key)) for r in rows_a]
    kb = [str(r.get(join_key)) for r in rows_b]
    sa, sb = {_shape(r.get(join_key)) for r in rows_a}, {_shape(r.get(join_key)) for r in rows_b}
    only_a, only_b = sorted(set(ka) - set(kb)), sorted(set(kb) - set(ka))
    matched = len(set(ka) & set(kb))
    report: dict = {
        'a_rows': len(rows_a),
        'b_rows': len(rows_b),
        'matched': matched,
        'only_a': only_a,
        'only_b': only_b,
        'key_shape': {'a': sorted(sa), 'b': sorted(sb)},
        'join_ok': False,
        'values': None,
        'reason': '',
        'ok': False,
    }
    if not rows_a or not rows_b:
        report['reason'] = 'empty input: an empty side joins perfectly and proves nothing'
        return report
    if only_a or only_b or matched != len(set(ka)) or matched != len(set(kb)):
        shapes = (
            f' (key shapes {report["key_shape"]["a"]} vs {report["key_shape"]["b"]})'
            if sa != sb
            else ''
        )
        report['reason'] = (
            f'join failed: {matched} key(s) matched, {len(only_a)} only in a, '
            f'{len(only_b)} only in b{shapes} - values not compared'
        )
        return report
    report['join_ok'] = True
    report['values'] = compare(rows_a, rows_b, keys=[join_key], **compare_kwargs)
    report['ok'] = bool(report['values']['ok'])
    report['reason'] = 'join clean' if report['ok'] else 'join clean, values differ'
    return report


def _parse_tol_col(specs: list[str]) -> dict[str, float]:
    """Parse repeated `NAME=ATOL` flags. A malformed spec is a usage error, never
    a silently-ignored tolerance that leaves the column on the global --tol."""
    out: dict[str, float] = {}
    for spec in specs:
        name, sep, value = spec.partition('=')
        if not sep or not name:
            raise ValueError(f'--tol-col expects NAME=ATOL, got {spec!r}')
        try:
            out[name] = float(value)
        except ValueError:
            raise ValueError(f'--tol-col {name}: {value!r} is not a number') from None
    return out


def _read_csv(path: str) -> list[dict]:
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def _run_two_producer(args, tol_col: dict[str, float]) -> int:
    a_path, b_path = args.two_producer
    rep = two_producer_check(
        _read_csv(a_path),
        _read_csv(b_path),
        args.join_key,
        tol=args.tol,
        null_tol=args.null_tol,
        tol_col=tol_col,
        residual_zero=args.residual_zero,
        null_mismatch=not args.no_null_mismatch,
    )
    print(f'rows: a={rep["a_rows"]} b={rep["b_rows"]}, joined on {args.join_key}: {rep["matched"]}')
    print(f'key shape: a={rep["key_shape"]["a"]} b={rep["key_shape"]["b"]}')
    if not rep['join_ok']:
        print(f'JOIN FAILED: {rep["reason"]}')
        return 1
    values = rep['values']
    for c, s in values['sum_delta'].items():
        if abs(s['delta']) > tol_col.get(c, args.tol):
            print(f'  sum {c}: delta {s["delta"]}')
    print('TWO-PRODUCER OK' if rep['ok'] else 'TWO-PRODUCER FAILED: values differ')
    return 0 if rep['ok'] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Parity-check two datasets.')
    parser.add_argument('baseline', nargs='?')
    parser.add_argument('candidate', nargs='?')
    parser.add_argument(
        '--two-producer',
        nargs=2,
        metavar=('A', 'B'),
        help='two producers of one shared column: assert the join, then the values',
    )
    parser.add_argument('--join-key', help='shared column the two producers both write')
    parser.add_argument('--keys', default='', help='comma-separated key columns')
    parser.add_argument('--tol', type=float, default=1e-9, help='numeric-sum delta tolerance')
    parser.add_argument(
        '--null-tol',
        type=float,
        default=0.0,
        help='per-column null-rate delta tolerance (separate from --tol; default 0.0)',
    )
    parser.add_argument(
        '--tol-col',
        action='append',
        default=[],
        metavar='NAME=ATOL',
        help='per-column sum tolerance overriding --tol (repeatable)',
    )
    parser.add_argument(
        '--residual-zero',
        action='append',
        default=[],
        metavar='NAME',
        help='column that sits at zero by construction: compare its non-zero ROW COUNT '
        '(a > 0 filter downstream makes residue a cardinality hazard). Repeatable.',
    )
    parser.add_argument(
        '--no-null-mismatch',
        action='store_true',
        help='skip the key-aligned null-placement comparison (on by default)',
    )
    args = parser.parse_args(argv)

    keys = [k for k in args.keys.split(',') if k]
    try:
        tol_col = _parse_tol_col(args.tol_col)
        if args.two_producer:
            if not args.join_key:
                raise ValueError('--two-producer needs --join-key')
            return _run_two_producer(args, tol_col)
        if not args.baseline or not args.candidate:
            raise ValueError('give two dataset paths, or --two-producer A B --join-key K')
        rep = compare(
            _read_csv(args.baseline),
            _read_csv(args.candidate),
            keys,
            args.tol,
            args.null_tol,
            tol_col=tol_col,
            residual_zero=args.residual_zero,
            null_mismatch=not args.no_null_mismatch,
        )
    except ValueError as e:
        # usage error (e.g. typo'd --keys), distinct from a parity failure (1)
        print(f'error: {e}', file=sys.stderr)
        return 2
    rc = rep['row_count']
    print(f'row count: {rc["a"]} -> {rc["b"]} (delta {rc["delta"]})')
    gc = rep['group_cardinality']
    print(f'group cardinality: {gc["a"]} -> {gc["b"]}')
    for c, s in rep['sum_delta'].items():
        if abs(s['delta']) > tol_col.get(c, args.tol):
            print(f'  sum {c}: delta {s["delta"]}')
    for c, d in rep['null_rate_delta'].items():
        if abs(d) > args.null_tol:
            print(f'  null-rate {c}: delta {d:+.4f}')
    if rep['null_mismatch'] is None:
        print(f'  null-mismatch: NOT ASSESSED ({rep["null_mismatch_reason"]})')
    else:
        for c, n in rep['null_mismatch'].items():
            print(f'  null-mismatch {c}: {n} row(s) blank on one side only')
    for c, r in rep['residual_zero'].items():
        if r['delta']:
            print(f'  residual-zero {c}: non-zero rows {r["a"]} -> {r["b"]} (a > 0 filter moves)')
    ok = rep['ok']
    print('PARITY OK' if ok else 'PARITY FAILED')
    if ok:
        print(
            '  (aggregate-level only: a sum/count-preserving value swap also passes '
            '- confirm with a row-level diff, parity-recipes.md Recipe 6)'
        )
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

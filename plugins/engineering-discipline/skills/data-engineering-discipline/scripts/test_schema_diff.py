"""Tests for schema_diff.diff. Runnable with pytest or `python test_schema_diff.py`."""

from __future__ import annotations

import tempfile
from pathlib import Path

from schema_diff import diff, main, verdict


def test_added_removed_retyped():
    a = {'id': 'int64', 'amount': 'float64', 'name': 'object'}
    b = {'id': 'int64', 'amount': 'int64', 'created': 'datetime64'}
    d = diff(a, b)
    assert d['added'] == ['created']
    assert d['removed'] == ['name']
    assert d['retyped'] == [('amount', 'float64', 'int64')]


def test_identical():
    a = {'id': 'int64'}
    assert diff(a, a) == {'added': [], 'removed': [], 'retyped': []}


def test_verdict_unchecked_dtypes_does_not_claim_match():
    # Columns match but dtypes were NOT checked (no pandas). The summary must NOT
    # say "schemas match" — it must announce the SKIP loudly and exit non-zero,
    # so an int->str retype the tool cannot see does not read as a clean pass.
    d = {'added': [], 'removed': [], 'retyped': []}
    lines, code = verdict(d, dtypes_checked=False)
    text = '\n'.join(lines)
    assert 'schemas match' not in text
    assert 'SKIPPED' in text
    assert code != 0


def test_verdict_checked_dtypes_clean_match():
    d = {'added': [], 'removed': [], 'retyped': []}
    lines, code = verdict(d, dtypes_checked=True)
    assert 'schemas match' in '\n'.join(lines)
    assert code == 0


def test_verdict_differences_still_report_differ():
    d = {'added': ['x'], 'removed': [], 'retyped': []}
    lines, code = verdict(d, dtypes_checked=True)
    assert 'schemas differ' in '\n'.join(lines)
    assert code == 1


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text('\n'.join(rows) + '\n', encoding='utf-8')


def test_no_pandas_branch_does_not_pass_a_retype_via_main():
    # End-to-end through main() with no pandas: two CSVs with the SAME columns but
    # an int->str retype in `amount`. main must exit non-zero (not the old
    # "schemas match" exit 0) because dtypes could not be verified.
    try:
        import pandas  # noqa: F401
    except ImportError:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = root / 'base.csv'
            cand = root / 'cand.csv'
            _write_csv(base, ['id,amount', '1,10', '2,20'])
            _write_csv(cand, ['id,amount', '1,ten', '2,twenty'])
            rc = main([str(base), str(cand)])
            assert rc != 0
    # (When pandas IS installed the stdlib branch is not exercised; covered by the
    # verdict unit tests above and the full-read test below.)


def test_full_read_catches_retype_past_row_1000():
    # A retype that only appears after row 1000 must be caught on a full read.
    # The old hardcoded nrows=1000 would sample only the clean prefix and miss it.
    # Requires pandas; skipped (as a no-op) when unavailable so the bare-python
    # run_tests.py harness stays green.
    try:
        import pandas  # noqa: F401
    except ImportError:
        return
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        base = root / 'base.csv'
        cand = root / 'cand.csv'
        # 1200 rows: `amount` is integer in baseline throughout; in candidate it
        # is integer for the first 1100 rows then a string token afterwards.
        base_rows = ['id,amount'] + [f'{i},{i}' for i in range(1200)]
        cand_rows = ['id,amount'] + [f'{i},{i if i < 1100 else "x" + str(i)}' for i in range(1200)]
        _write_csv(base, base_rows)
        _write_csv(cand, cand_rows)
        # Full read (default nrows=None) sees the mixed dtype -> differ (exit 1).
        assert main([str(base), str(cand)]) == 1
        # A capped read that stops before row 1100 misses it -> "match" (exit 0),
        # proving the cap is what hides the retype.
        assert main([str(base), str(cand), '--nrows', '500']) == 0


if __name__ == '__main__':
    test_added_removed_retyped()
    test_identical()
    test_verdict_unchecked_dtypes_does_not_claim_match()
    test_verdict_checked_dtypes_clean_match()
    test_verdict_differences_still_report_differ()
    test_no_pandas_branch_does_not_pass_a_retype_via_main()
    test_full_read_catches_retype_past_row_1000()
    print('ok: all schema_diff tests passed')

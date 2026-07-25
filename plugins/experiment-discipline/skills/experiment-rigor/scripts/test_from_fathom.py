"""Tests for from_fathom.py -- the fathom-ledger bridge (spec section 3).

Runnable with pytest or `python test_from_fathom.py` (run_tests.py runs the latter
and requires an `ok:` sentinel on success).

Provenance: the load-bearing fixture fixtures/ledger/model-tier-excerpt.jsonl is a
VERBATIM 12-line excerpt (6 run + 6 trial rows) copied unmodified from the real fathom
ledger ledger/model-tier-v1.jsonl (its haiku scenario rows -- hence the name, not the
founding RG-2x2 case). Nothing is scrubbed -- the rows carry no secrets, only
cost/usage/verifier bookkeeping. Its derived footprint is fixed and asserted below, so
a reader drift is caught.
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import from_fathom

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / 'fixtures' / 'ledger' / 'model-tier-excerpt.jsonl'

# Independently computed from the verbatim excerpt (see the module docstring).
EXPECTED_N = 6
EXPECTED_PASSED = 2
EXPECTED_FAILED = 4
EXPECTED_COST = 0.6734971
EXPECTED_SCENARIOS = ['haiku']
EXPECTED_PIN = 'strong'


def test_is_pass_matches_fathom_predicate():
    # All-truthy non-empty mapping passes; any false value or emptiness fails; None fails.
    assert from_fathom.is_pass({'a': True, 'b': True}) is True
    assert from_fathom.is_pass({'a': True, 'b': False}) is False
    assert from_fathom.is_pass({}) is False
    assert from_fathom.is_pass(None) is False
    assert from_fathom.is_pass(True) is True


def test_reads_verbatim_excerpt_cost_n_and_disposition():
    summary = from_fathom.summarize_ledger(FIXTURE)
    assert summary.n == EXPECTED_N, summary
    assert summary.passed == EXPECTED_PASSED, summary
    assert summary.failed == EXPECTED_FAILED, summary
    assert summary.disposition == {'passed': 2, 'failed': 4, 'total': 6}, summary.disposition
    assert summary.cost_usd_est is not None
    assert math.isclose(summary.cost_usd_est, EXPECTED_COST, rel_tol=1e-9, abs_tol=1e-9), summary
    assert summary.completed == EXPECTED_N  # every excerpt trial is status=completed
    assert summary.excluded == 0


def test_model_tier_from_pin_and_scenarios():
    summary = from_fathom.summarize_ledger(FIXTURE)
    assert summary.pin_level == EXPECTED_PIN, summary.pin_level
    assert summary.scenarios == EXPECTED_SCENARIOS, summary.scenarios


def test_cost_sums_multiple_run_rows():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'l.jsonl'
        path.write_text(
            '\n'.join(
                [
                    json.dumps({'kind': 'run', 'cost_usd_est': 1.5}),
                    json.dumps({'kind': 'run', 'cost_usd_est': 2.25}),
                    json.dumps(
                        {'kind': 'trial', 'status': 'completed', 'verifier_results': {'a': True}}
                    ),
                ]
            )
            + '\n',
            encoding='utf-8',
        )
        summary = from_fathom.summarize_ledger(path)
        assert math.isclose(summary.cost_usd_est, 3.75), summary.cost_usd_est
        assert summary.n == 1


def test_cost_none_when_no_run_row_carries_it():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'l.jsonl'
        path.write_text(
            json.dumps({'kind': 'trial', 'status': 'completed', 'verifier_results': {'a': True}})
            + '\n',
            encoding='utf-8',
        )
        summary = from_fathom.summarize_ledger(path)
        assert summary.cost_usd_est is None
        assert summary.n == 1


def test_errored_trials_are_excluded_from_completed():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'l.jsonl'
        path.write_text(
            '\n'.join(
                [
                    json.dumps(
                        {'kind': 'trial', 'status': 'completed', 'verifier_results': {'a': True}}
                    ),
                    json.dumps({'kind': 'trial', 'status': 'errored', 'verifier_results': None}),
                ]
            )
            + '\n',
            encoding='utf-8',
        )
        summary = from_fathom.summarize_ledger(path)
        assert summary.n == 2  # trial-row count
        assert summary.completed == 1
        assert summary.excluded == 1
        assert summary.passed == 1  # the errored/None trial does not pass


def test_blank_and_malformed_lines_skipped():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'l.jsonl'
        path.write_text(
            '\n'.join(
                [
                    json.dumps({'kind': 'run', 'cost_usd_est': 1.0}),
                    '',
                    'not json at all',
                    json.dumps(
                        {'kind': 'trial', 'status': 'completed', 'verifier_results': {'a': True}}
                    ),
                ]
            )
            + '\n',
            encoding='utf-8',
        )
        summary = from_fathom.summarize_ledger(path)
        assert summary.n == 1
        assert math.isclose(summary.cost_usd_est, 1.0)


if __name__ == '__main__':
    import sys

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
            except Exception as exc:  # report any failure; never emit the ok: sentinel
                failed += 1
                print(f'FAIL {name}: {exc!r}')
    if failed:
        print(f'{failed} test(s) failed')
        sys.exit(1)
    print('ok: all from_fathom tests passed')

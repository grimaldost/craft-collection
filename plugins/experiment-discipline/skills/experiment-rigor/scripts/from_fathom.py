#!/usr/bin/env python3
"""The fathom-ledger bridge (craft side, spec section 3): read a real fathom
ledger JSONL into the run-derived fields an experiment-rigor record cross-checks.

This is the authoritative ledger reader. validate.py's ER-XCHECK gate delegates
its cost/n read to summarize_ledger here rather than carrying a second copy of the
row-shape logic (the section-3 de-duplication of section 2's inline TODO reader).

Real fathom ledger shape (verified against C:/Users/grima/Documents/fathom):
  - Each line is one JSON object; the row kind is the `kind` field, not `type`
    (the nested usage.iterations[].type == 'message' is unrelated bookkeeping).
  - `kind: run`   rows carry `cost_usd_est` (the per-spawn USD estimate; there is
    no `cost_usd` key), plus usage/turns/duration/exit_code/pin_level.
  - `kind: trial` rows carry `verifier_results` (the graded checks), `status`
    ('completed' | 'errored'), `scenario`, and `pin_level`. There is no
    `disposition` or `model_versions` field on any row.
  - n is the trial-row count; the pass/fail disposition is derived from each
    trial's `verifier_results` via the same predicate fathom's report.py uses.
  - The model tier is read from `pin_level` (and the distinct trial `scenario`s);
    a concrete model-version string is source: hand unless the bank/scenario
    config carries it, so this reader does not invent one.

Stdlib only (JSONL, no YAML); Python 3.13+.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple


class LedgerSummary(NamedTuple):
    cost_usd_est: float | None  # sum of run-row cost_usd_est, or None if no row carries it
    n: int  # trial-row count (the graded-cell count)
    passed: int  # trials passing the verifier predicate
    failed: int  # n - passed
    completed: int  # trials with status == 'completed'
    excluded: int  # trials with status != 'completed' (errored / infra)
    pin_level: str | None  # the single pin_level if the rows agree, else None
    scenarios: list[str]  # distinct trial scenarios, sorted

    @property
    def disposition(self) -> dict[str, int]:
        """The verifier-derived disposition: pass/fail over the graded trials."""
        return {'passed': self.passed, 'failed': self.failed, 'total': self.n}


def is_pass(verifier_results: Any) -> bool:
    """The fathom pass predicate (report.py:_is_pass, held identical here): a trial
    passes when its verifier_results is a non-empty mapping whose every value is
    truthy. None (an ungraded / silent-fail trial) is not a pass."""
    if verifier_results is None:
        return False
    if isinstance(verifier_results, dict):
        return bool(verifier_results) and all(bool(v) for v in verifier_results.values())
    return bool(verifier_results)


def iter_rows(path: str | Path) -> list[dict[str, Any]]:
    """Parse a ledger JSONL into a list of row dicts, skipping blank and malformed
    lines (an append-only ledger tolerates a torn final write)."""
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def summarize_ledger(path: str | Path) -> LedgerSummary:
    """Read a fathom ledger into run-derived fields: summed cost, trial-row n, and
    the verifier-derived pass/fail disposition. This is the single reader the
    ER-XCHECK cross-check and any report derivation share.

    Note: n counts ALL trial rows; errored / infra trials are tagged into `excluded`
    separately (not dropped from n). This deliberately will NOT reconcile with a
    fathom scorecard denominator on a ledger that contains infra errors -- fathom's
    report.py drops those from its pass-rate N, this reader keeps them in n."""
    rows = iter_rows(path)
    costs = [r['cost_usd_est'] for r in rows if r.get('kind') == 'run' and 'cost_usd_est' in r]
    cost = float(sum(costs)) if costs else None

    trials = [r for r in rows if r.get('kind') == 'trial']
    n = len(trials)
    passed = sum(1 for t in trials if is_pass(t.get('verifier_results')))
    completed = sum(1 for t in trials if t.get('status') == 'completed')
    excluded = n - completed

    pins = {t.get('pin_level') for t in trials if t.get('pin_level') is not None}
    pin_level = next(iter(pins)) if len(pins) == 1 else None
    scenarios = sorted({str(t['scenario']) for t in trials if t.get('scenario') is not None})

    return LedgerSummary(
        cost_usd_est=cost,
        n=n,
        passed=passed,
        failed=n - passed,
        completed=completed,
        excluded=excluded,
        pin_level=pin_level,
        scenarios=scenarios,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Summarize a fathom ledger for a record cross-check.')
    ap.add_argument('ledger', help='path to a fathom ledger JSONL')
    args = ap.parse_args(argv)
    summary = summarize_ledger(args.ledger)
    print(
        json.dumps(
            {
                'cost_usd_est': summary.cost_usd_est,
                'n': summary.n,
                'disposition': summary.disposition,
                'completed': summary.completed,
                'excluded': summary.excluded,
                'pin_level': summary.pin_level,
                'scenarios': summary.scenarios,
            },
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

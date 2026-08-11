#!/usr/bin/env python3
"""Cross-producer census: find contract columns written by more than one producer.

A producer-local test suite cannot see two writers of one column disagreeing.
A `Date` from one emitter and a `Datetime` from another are each correct in
isolation; the disagreement only exists in the join, so every producer-local
gate stays green while the shared column silently drops rows downstream.
This reads a lineage/emitter inventory and fails when a column has two or more
producers that were never recorded as having run TOGETHER.

Inventory JSON, either shape:

    {"columns": {"settled_on": ["orders.emit", "settlements.emit"]},
     "joint_runs": [["orders.emit", "settlements.emit"]]}

    {"settled_on": ["orders.emit", "settlements.emit"]}      # flat, no joint runs

HONEST LIMITATION -- this sees only what the inventory records. A producer
missing from the inventory is invisible to it, and a recorded joint run is a
claim that the two ran together, not proof they AGREED: clearing a column here
means the pair is comparable, and `parity_check.py --two-producer` is what
compares them. An empty inventory is an ERROR (exit 2), never a clean pass.

    python producer_census.py inventory.json

Exit 0 clean, 1 findings, 2 usage/empty-inventory error. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_inventory(path: str | Path) -> tuple[dict[str, list[str]], list[list[str]]]:
    """Read either inventory shape into (columns, joint_runs). Raises ValueError
    on a shape that is neither, rather than coercing it to an empty census."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('inventory must be a JSON object')
    if 'columns' in data:
        columns = data.get('columns') or {}
        joint = data.get('joint_runs') or []
    else:
        columns, joint = data, []
    if not isinstance(columns, dict) or not all(isinstance(v, list) for v in columns.values()):
        raise ValueError('inventory columns must map column -> [producer_id, ...]')
    return columns, [list(run) for run in joint]


def census(
    columns: dict[str, list[str]], joint_runs: list[list[str]], min_producers: int = 2
) -> list[dict]:
    """Columns with >= min_producers writers not covered by one recorded joint run.

    A joint run clears a column only when it covers EVERY producer of that column:
    two of three writers exercised together still leaves the third never compared
    against either. Pure -- feed it the inventory, no I/O.
    """
    findings: list[dict] = []
    for column, producers in sorted(columns.items()):
        distinct = sorted(set(producers))
        if len(distinct) < min_producers:
            continue
        covered = [run for run in joint_runs if set(distinct) <= set(run)]
        if covered:
            continue
        best: set[str] = set()
        for run in joint_runs:
            overlap = set(distinct) & set(run)
            if len(overlap) > len(best):
                best = overlap
        findings.append(
            {
                'column': column,
                'producers': distinct,
                'uncovered': sorted(set(distinct) - best),
            }
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Cross-producer census over a lineage inventory.')
    parser.add_argument('inventory', help='JSON inventory of column -> producers')
    parser.add_argument(
        '--min-producers',
        type=int,
        default=2,
        help='producers per column that make it a finding (default 2)',
    )
    args = parser.parse_args(argv)

    try:
        columns, joint_runs = load_inventory(args.inventory)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    if not columns:
        print(
            'error: inventory names no columns - a census over nothing is not a pass',
            file=sys.stderr,
        )
        return 2

    findings = census(columns, joint_runs, args.min_producers)
    print(f'census: {len(columns)} column(s), {len(joint_runs)} recorded joint run(s)')
    for f in findings:
        print(f'  {f["column"]}: {len(f["producers"])} producers {f["producers"]}')
        print(f'    never run jointly with the rest: {f["uncovered"]}')
    if findings:
        print(
            f'CENSUS FAILED: {len(findings)} shared column(s) with no joint run - '
            'run the producers together and compare them (parity_check.py --two-producer)'
        )
        return 1
    print('CENSUS OK')
    print(
        '  (a recorded joint run means the pair is comparable, not that it agreed - '
        'compare the values with parity_check.py --two-producer)'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

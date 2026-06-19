#!/usr/bin/env python3
"""Freshness gate for an incremental cursor / watermark.

Asserts that an incremental load's cursor MOVED — the failure where a cache
builds once and never re-pulls, so `max(cursor)` stays frozen while the run
self-reports `success: true`. Pure core `check_freshness(prev_max, curr_max,
source_max, ...)` returns a report dict with an `ok` flag; `check_freshness_groups`
runs it per partition; the CLI reads three scalars.

WATERMARK-ADVANCE / MAX-CURSOR-LAG ONLY — necessary, not sufficient. Like
`parity_check`, treat FRESH OK as a floor. A single global `max(cursor)` is BLIND to:
  - per-partition staleness (one tenant/region frozen while the global max advances)
    -> use `check_freshness_groups` with a per-partition max;
  - watermark advances but rows were skipped (late data below the mark, `>` vs `>=`
    boundary) -> reconcile row-count-per-bucket (parity-recipes.md, freshness recipe);
  - late-arriving / lookback-window loads (correct rows below the current max);
  - soft-deletes / tombstones (no new cursor value);
  - event-time vs ingestion-time cursors on different clocks.

Comparability is ENFORCED, not assumed: cursors must be int / float / date /
datetime of one type. A string cursor (silently mis-orders `'9' > '10'` and
unpadded ISO dates) and a tz-aware-vs-naive mix are rejected as `uncomparable`
rather than compared wrongly — the silent-drift class this gate exists to stop.
When freshness cannot be assessed (no prior snapshot AND no source max), `ok` is
`None` ("unknown") — never a pass.

Usage:
    python freshness_check.py --prev 1000 --curr 1000 --source 1500   # stale
    python freshness_check.py --prev 2026-06-18 --curr 2026-06-19     # advanced
Exit 1 if stale, unknown, or uncomparable. Stdlib only.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime


def _classify(v: object) -> str | None:
    """Comparability tag. `None` for missing; 'other' for anything non-temporal/numeric."""
    if v is None:
        return None
    if isinstance(v, bool):  # bool is an int subclass; a bool cursor is a bug, not a number
        return 'other'
    if isinstance(v, datetime):  # datetime is a date subclass — check it first
        return 'datetime'
    if isinstance(v, date):
        return 'date'
    if isinstance(v, (int, float)):
        return 'number'
    return 'other'


def check_freshness(
    prev_max: object,
    curr_max: object,
    source_max: object = None,
    *,
    require_advance: bool = True,
    max_lag: object = None,
) -> dict:
    """Did the cursor move? Returns a report dict with an `ok` flag.

    `ok` is True (fresh), False (stale/uncomparable), or None (unassessable —
    never treat as a pass). `require_advance` asserts curr > prev (default on,
    so a frozen cursor fails closed); pass a `source_max` to also assert curr is
    not behind source by more than `max_lag` (default: curr >= source).
    """
    report: dict = {
        'prev': prev_max,
        'curr': curr_max,
        'source': source_max,
        'advanced': None,
        'lag': None,
        'ok': None,
        'reason': '',
    }
    if curr_max is None:
        report['ok'] = False
        report['reason'] = 'no curr_max supplied'
        return report

    tags = {_classify(v) for v in (prev_max, curr_max, source_max) if v is not None}
    if 'other' in tags:
        report['ok'] = False
        report['reason'] = (
            'uncomparable: cursor must be int/float/date/datetime (pass a typed value, not a string)'
        )
        return report
    if len(tags) > 1:
        report['ok'] = False
        report['reason'] = f'uncomparable: mixed cursor types {sorted(tags)}'
        return report

    within = None
    try:
        if prev_max is not None:
            report['advanced'] = curr_max > prev_max
        if source_max is not None:
            report['lag'] = source_max - curr_max
            within = (
                (curr_max >= source_max) if max_lag is None else (source_max - curr_max <= max_lag)
            )
    except TypeError as exc:
        report['ok'] = False
        report['reason'] = f'uncomparable: {exc} (tz-aware vs naive, or a bad max_lag type?)'
        return report

    checks: list[tuple[str, bool]] = []
    if require_advance and prev_max is not None:
        checks.append(('advanced', report['advanced'] is True))
    if within is not None:
        checks.append(('lag', within))

    if not checks:
        report['ok'] = None
        report['reason'] = (
            'unknown: no prior snapshot and no source_max — freshness cannot be assessed'
        )
        return report
    report['ok'] = all(passed for _, passed in checks)
    report['reason'] = (
        'fresh' if report['ok'] else 'stale: ' + ', '.join(n for n, p in checks if not p)
    )
    return report


def check_freshness_groups(
    groups: list[dict], *, require_advance: bool = True, max_lag: object = None
) -> dict:
    """Run `check_freshness` per partition. `groups`: dicts of
    {'group', 'prev', 'curr', optional 'source'}. The aggregate fails if ANY
    group is stale and is unknown if any group is unassessable (and none stale)
    — a global max would hide a single frozen partition; this does not."""
    per_group: dict = {}
    stale: list = []
    unknown: list = []
    for g in groups:
        name = g.get('group')
        rep = check_freshness(
            g.get('prev'),
            g.get('curr'),
            g.get('source'),
            require_advance=require_advance,
            max_lag=max_lag,
        )
        per_group[name] = rep
        if rep['ok'] is False:
            stale.append(name)
        elif rep['ok'] is None:
            unknown.append(name)
    ok: bool | None = False if stale else (None if unknown else True)
    return {
        'ok': ok,
        'n_groups': len(groups),
        'stale': stale,
        'unknown': unknown,
        'per_group': per_group,
    }


def _parse_cursor(s: str | None) -> object:
    """Parse a CLI string into a typed cursor (int -> float -> datetime -> date)."""
    if s is None:
        return None
    for parse in (int, float, datetime.fromisoformat, date.fromisoformat):
        try:
            return parse(s)  # type: ignore[arg-type]
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f'cursor {s!r} is not int/float/ISO-date/ISO-datetime')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Assert an incremental cursor advanced.')
    parser.add_argument(
        '--prev', type=_parse_cursor, default=None, help='prior snapshot max(cursor)'
    )
    parser.add_argument(
        '--curr', type=_parse_cursor, required=True, help='current output max(cursor)'
    )
    parser.add_argument('--source', type=_parse_cursor, default=None, help='source max(cursor)')
    parser.add_argument(
        '--max-lag', type=float, default=None, help='allowed numeric lag behind source'
    )
    parser.add_argument(
        '--no-require-advance', action='store_true', help='skip the curr>prev assertion'
    )
    args = parser.parse_args(argv)

    rep = check_freshness(
        args.prev,
        args.curr,
        args.source,
        require_advance=not args.no_require_advance,
        max_lag=args.max_lag,
    )
    print(
        f'prev={rep["prev"]} curr={rep["curr"]} source={rep["source"]} '
        f'advanced={rep["advanced"]} lag={rep["lag"]}'
    )
    label = {True: 'FRESH OK', False: 'STALE', None: 'UNKNOWN'}[rep['ok']]
    print(f'{label}: {rep["reason"]}')
    if rep['ok'] is True:
        print(
            '  (watermark-advance only: per-partition staleness and skipped rows still pass '
            '- see freshness_check docstring + parity-recipes.md)'
        )
    return 0 if rep['ok'] is True else 1


if __name__ == '__main__':
    sys.exit(main())

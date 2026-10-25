#!/usr/bin/env python3
"""Pins for the shipped lineup in models.toml (no pytest required).

The tier rows are what a direct-API or series-file author reads, so the shipped
model per tier is pinned here and changed only together with this test. The
calibration note has to say that the three earlier runs predate the 5.5 lineup and
record the 2026-10-25 run on it: no threshold moves, the cut verdict is inconclusive,
the floor verdict is LIFT, and the bank is saturated. The cost rows no longer call
the 5.5 tiers unmeasured.
"""

from __future__ import annotations

import sys
from pathlib import Path

import tomllib

SKILL = Path(__file__).resolve().parent.parent
MODELS = SKILL / 'models.toml'

EXPECTED = {
    'weak': ('claude-haiku-5-5', 'Haiku 5.5'),
    'mid': ('claude-sonnet-5-5', 'Sonnet 5.5'),
    'strong': ('claude-opus-5-5', 'Opus 5.5'),
}


def _data() -> dict:
    with MODELS.open('rb') as fh:
        return tomllib.load(fh)


def _row(tier: str) -> dict:
    return next(m for m in _data()['models'] if m['tier'] == tier)


def test_shipped_lineup_per_tier():
    for tier, (api, display) in EXPECTED.items():
        row = _row(tier)
        assert row['api_string'] == api, f'{tier}: {row["api_string"]} != {api}'
        assert row['display'] == display, f'{tier}: {row["display"]} != {display}'


def test_new_rows_mark_unmeasured_what_is_unmeasured():
    for tier in ('weak', 'mid'):
        notes = _row(tier)['notes']
        assert 'unmeasured' in notes, f'{tier} note does not mark what is unmeasured'
        assert 'measured 2026-10-08' in notes, f'{tier} note lacks the alias measurement'
        assert 'legacy' in notes, f'{tier} note does not name the superseded model as legacy'
    assert '200K' not in _row('weak')['notes'], 'Haiku 4.5 context window carried over'


def test_calibration_note_records_the_5_5_run():
    data = _data()
    calibration = data['meta']['calibration']
    assert '\n' not in calibration
    assert 'predate the 5.5 lineup' in calibration, 'calibration note missing'
    for needle in (
        'run of 2026-10-25',
        '450 scored trials',
        'moves no threshold',
        'Cut verdict inconclusive',
        'LIFT: Haiku 5.5 read A',
        'effort high only',
        'gated PR implementers, gate runners and exploration agents are unmeasured',
        'verifier and challenger roles stay strong',
        "the rubric's cross-shape and role floors are unaffected",
        'CLAUDE_CODE_SUBAGENT_MODEL=sonnet',
        'saturated',
        'one-sided Fisher p = 1.0',
    ):
        assert needle in calibration, needle
    assert data['thresholds']['weak'] == '0-25', 'LIFT moves no threshold'
    for tier in ('weak', 'mid', 'strong'):
        assert 'unmeasured' not in data['typical_cost'][tier], f'{tier} cost still unmeasured'
        assert '2026-10-25' in data['typical_cost'][tier], f'{tier} cost not dated'


def test_review_stamp():
    meta = _data()['meta']
    assert meta['last_reviewed'] == '2026-10-08', meta['last_reviewed']
    assert meta['review_by'] == '2027-01-08', meta['review_by']
    assert '2026-10-08' in meta['lineup_reconciled']


def main() -> int:
    test_shipped_lineup_per_tier()
    test_new_rows_mark_unmeasured_what_is_unmeasured()
    test_calibration_note_records_the_5_5_run()
    test_review_stamp()
    print('ok: shipped_lineup')
    return 0


if __name__ == '__main__':
    sys.exit(main())

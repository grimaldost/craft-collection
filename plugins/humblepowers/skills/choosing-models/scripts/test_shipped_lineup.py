#!/usr/bin/env python3
"""Pins for the shipped lineup in models.toml (no pytest required).

The tier rows are what a direct-API or series-file author reads, so the shipped
model per tier is pinned here and changed only together with this test. The
calibration note has to say that the recorded calibration predates the 5.5
lineup: the weak and mid rows name models no bank has measured.
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


def test_calibration_note_predates_the_5_5_lineup():
    calibration = _data()['meta']['calibration']
    assert '\n' not in calibration
    assert 'predates the 5.5 lineup' in calibration, 'calibration note missing'


def test_review_stamp():
    meta = _data()['meta']
    assert meta['last_reviewed'] == '2026-10-08', meta['last_reviewed']
    assert meta['review_by'] == '2027-01-08', meta['review_by']
    assert '2026-10-08' in meta['lineup_reconciled']


def main() -> int:
    test_shipped_lineup_per_tier()
    test_new_rows_mark_unmeasured_what_is_unmeasured()
    test_calibration_note_predates_the_5_5_lineup()
    test_review_stamp()
    print('ok: shipped_lineup')
    return 0


if __name__ == '__main__':
    sys.exit(main())

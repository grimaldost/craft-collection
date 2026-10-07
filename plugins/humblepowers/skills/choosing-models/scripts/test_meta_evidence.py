#!/usr/bin/env python3
"""Pins for two evidence records in models.toml `[meta]` (no pytest required).

`oracle_discount` carries the first measured point against its labelled hypothesis:
both counts with their Wilson 95% intervals (recomputed here from the counts), the
bank and config_hash prefixes, the bank v1 caveat and the test that decides it. It
cites the bank, the hash prefixes and n, never a path into the data repository.

`verifier_observations` records that strong-tier verifiers handed the finder's
evidence act as second finders, cited by report stem with the reports' counts, as
evidence for keeping verify roles at strong and not as a threshold change.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import tomllib

SKILL = Path(__file__).resolve().parent.parent
MODELS = SKILL / 'models.toml'
Z95 = 1.959964


def _meta() -> dict:
    with MODELS.open('rb') as fh:
        return tomllib.load(fh)['meta']


def _wilson(k: int, n: int) -> tuple[float, float]:
    p = k / n
    den = 1 + Z95 * Z95 / n
    centre = (p + Z95 * Z95 / (2 * n)) / den
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def test_oracle_discount_records_the_measured_point():
    text = _meta()['oracle_discount']
    assert '\n' not in text
    for k, n in ((16, 16), (2, 16)):
        lo, hi = _wilson(k, n)
        assert f'{k}/{n}' in text, f'{k}/{n} missing'
        assert f'[{lo:.2f}, {hi:.2f}]' in text, f'Wilson [{lo:.2f}, {hi:.2f}] for {k}/{n}'
    for needle in (
        'multiagent-composition-v2',
        '686bf6f6025f',
        '2b3f299c1f4f',
        'n = 16',
        '14/16',
        'held_out_clean',
        'bank v1',
        'iteration 2',
    ):
        assert needle in text, needle


def test_oracle_discount_cites_no_path():
    text = _meta()['oracle_discount']
    for fragment in ('.jsonl', 'ledger/', 'docs/reports/'):
        assert fragment not in text, f'path fragment {fragment!r} in oracle_discount'


def test_verifier_observations_cite_reports_with_counts():
    obs = _meta().get('verifier_observations')
    assert isinstance(obs, str) and obs, 'meta.verifier_observations missing'
    assert '\n' not in obs
    for stem in (
        '2026-10-06 health-audit#1',
        '2026-10-06 audit-followups#1',
        '2026-10-06 fathom-split-cleanup',
        '2026-09-26 dead-man-probe',
        '2026-09-20 routing-outcome',
    ):
        assert stem in obs, stem
    for count in (
        '2 defects the auditors missed',
        '4 mid-tier overstatements',
        'confounded cause',
        '16 MAJOR',
    ):
        assert count in obs, count
    assert 'not a threshold' in obs


def test_verifier_observations_sit_next_to_effort_observations():
    keys = list(_meta())
    assert keys.index('verifier_observations') == keys.index('effort_observations') + 1
    text = MODELS.read_text(encoding='utf-8')
    assert text.index('verifier_observations') < text.index('[[models]]')


def main() -> int:
    test_oracle_discount_records_the_measured_point()
    test_oracle_discount_cites_no_path()
    test_verifier_observations_cite_reports_with_counts()
    test_verifier_observations_sit_next_to_effort_observations()
    print('ok: meta_evidence')
    return 0


if __name__ == '__main__':
    sys.exit(main())

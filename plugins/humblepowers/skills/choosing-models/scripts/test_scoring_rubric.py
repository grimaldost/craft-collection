#!/usr/bin/env python3
"""Docs-truth checks for references/scoring-rubric.md (no pytest required).

Each `### <axis> (+a to +b)` heading states the range its table can produce;
recompute that range from the table and compare. The rubric also states that an
additive total is clamped to 0-100, with the largest and smallest totals the
tables allow, so those figures are recomputed too.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RUBRIC = Path(__file__).resolve().parent.parent / 'references' / 'scoring-rubric.md'
HEADING = re.compile(r'^### (?P<name>.+?) \((?P<lo>[+-]\d+) to (?P<hi>[+-]\d+)\)\s*$')
CELL = re.compile(r'^(?P<lo>[+-]\d+)(?:-(?P<hi>\d+))?$')
BASE = re.compile(r'^\| (?:Has any logic.*|Pure text/config.*?)\|\s*(\d+)\s*\|$', re.M)


def _text(path: Path = RUBRIC) -> str:
    return path.read_text(encoding='utf-8')


def axes(text: str) -> dict[str, tuple[tuple[int, int], list[tuple[int, int]]]]:
    """name -> (stated (lo, hi), one (lo, hi) per Points cell) for each ranged heading."""
    out = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        cells = []
        for row in lines[i + 1 :]:
            if row.startswith('###') or row.startswith('---'):
                break
            parts = [p.strip() for p in row.strip().strip('|').split('|')]
            c = CELL.match(parts[-1]) if row.startswith('|') and len(parts) >= 2 else None
            if c:
                lo = int(c['lo'])
                hi = int(c['hi']) if c['hi'] else lo
                # `+20-25` is a range of positives; `-5` is a single negative.
                cells.append((lo, hi) if lo >= 0 else (lo, lo))
        out[m['name']] = ((int(m['lo']), int(m['hi'])), cells)
    return out


def computed(cells: list[tuple[int, int]], signed: bool) -> tuple[int, int]:
    """Range the table can produce. A signed axis (adjustments) sums every row of
    each sign; an unsigned one takes the smallest and largest single row."""
    if signed:
        return sum(c[0] for c in cells if c[0] < 0), sum(c[1] for c in cells if c[1] > 0)
    return min(c[0] for c in cells), max(c[1] for c in cells)


def test_found_the_axes():
    found = axes(_text())
    assert len(found) == 6, sorted(found)
    for name, (_, cells) in found.items():
        assert cells, f'no Points rows parsed under {name!r}'


def test_each_heading_range_matches_its_table():
    for name, (stated, cells) in axes(_text()).items():
        got = computed(cells, signed=stated[0] < 0)
        assert got == stated, f'{name}: heading says {stated}, table gives {got}'


def test_clamp_sentence_is_present_and_its_totals_are_true():
    text = _text()
    found = axes(text)
    bases = [int(b) for b in BASE.findall('\n'.join(text.splitlines()))]
    assert sorted(bases) == [15, 30], bases
    additive = [r for n, (r, _) in found.items() if n != 'Adjustment factors']
    adj_lo, adj_hi = next(r for n, (r, _) in found.items() if n == 'Adjustment factors')
    top = max(bases) + sum(hi for _, hi in additive) + adj_hi
    bottom = min(bases) + adj_lo
    flat = ' '.join(text.split())
    assert re.search(r'total above 100 is read as 100', flat), 'upper clamp not stated'
    assert re.search(r'one below 0 as 0', flat), 'lower clamp not stated'
    assert f'maximum is {top}' in flat, f'stated maximum is not {top}'
    assert f'minimum is {bottom}' in flat, f'stated minimum is not {bottom}'


def main() -> int:
    test_found_the_axes()
    test_each_heading_range_matches_its_table()
    test_clamp_sentence_is_present_and_its_totals_are_true()
    print('ok: scoring_rubric')
    return 0


if __name__ == '__main__':
    sys.exit(main())

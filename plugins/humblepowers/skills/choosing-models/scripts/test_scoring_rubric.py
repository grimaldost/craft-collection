#!/usr/bin/env python3
"""Docs-truth checks for references/scoring-rubric.md (no pytest required).

Each `### <axis> (+a to +b)` heading states the range its table can produce;
recompute that range from the table and compare. The rubric also states that an
additive total is clamped to 0-100, with the largest and smallest totals the
tables allow, so those figures are recomputed too. The two role floors are pinned by
their rule text and their place between the cross-shape floor and the axes.
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


def test_role_floors_hold_whatever_the_score():
    """Two floors added in humblepowers 0.18.0 from maintenance-run observations: a
    fix round answering review findings, and prose other people read in public, run
    at mid or above. Both sit after the cross-shape floor and before the axes."""
    text = _text()
    order = [
        text.index(h) for h in ('## Cross-shape floor', '## Role floors', '## Scoring Signals')
    ]
    assert order == sorted(order), order
    section = text.split('## Role floors', 1)[1].split('## Scoring Signals', 1)[0]
    flat = ' '.join(section.split())
    assert 'Two floors act on the tier after scoring' in flat, 'floors not stated'
    assert 'change no points, base or floor of the score' in flat, 'floors touch the score'
    bullets = [' '.join(b.split('\n\n')[0].split()) for b in section.split('\n- ')[1:]]
    assert len(bullets) == 2, bullets
    assert 'fix round answering a review' in bullets[0], 'fix-round floor missing'
    assert 'prose other people read in public' in bullets[1], 'public-prose floor missing'
    for bullet in bullets:
        assert 'runs at `mid` or above' in bullet, bullet
    for surface in ('README', 'CHANGELOG', 'PR or issue bod'):
        assert surface in bullets[1], surface
    # SKILL.md says the rubric never moves without calibration evidence. The
    # floors rest on observations, so they have to sit outside the score, and
    # the two files have to keep saying so.
    assert 'not a calibrated threshold' in flat
    assert 'floors sit outside the score' in flat, 'floors not placed outside the score'
    skill = ' '.join((RUBRIC.parent.parent / 'SKILL.md').read_text(encoding='utf-8').split())
    assert 'never moves without calibration evidence' in skill, 'SKILL.md calibration rule'


def public_surfaces(text: str) -> list[str]:
    """The surfaces the public-prose floor names, as lower-case word stems: the
    bullet's list after `--`, articles dropped, `A or B body` split in two, a
    plural `docs` cut to `doc` so `documentation` matches too."""
    section = text.split('## Role floors', 1)[1].split('## Scoring Signals', 1)[0]
    bullet = next(b for b in section.split('\n- ')[1:] if 'read in public' in b)
    listed = ' '.join(bullet.split('\n\n')[0].split()).split(' -- ', 1)[1]
    listed = listed.split(' runs at ', 1)[0]
    stems = []
    for item in listed.replace(' or ', ', ').split(','):
        words = [w for w in item.lower().split() if w not in ('a', 'an', 'the', 'body')]
        if words:
            stems.append(words[0][:-1] if words[0] == 'docs' else words[0])
    return stems


def test_shortcuts_defer_to_the_role_floors():
    """The keyword shortcuts are a first guess: no surface the public-prose floor
    names may appear in the weak list, and the section says the role floors still
    apply to whatever the shortcuts suggest."""
    text = _text()
    stems = public_surfaces(text)
    assert stems == ['readme', 'changelog', 'doc', 'pr', 'issue'], stems
    section = text.split('## Quick Heuristic Shortcuts', 1)[1].split('---', 1)[0]
    weak = section.split('**Likely weak', 1)[1].split('**Likely mid', 1)[0]
    for stem in stems:
        # A stem of three letters or more matches as a word prefix (`doc` covers
        # `documentation`); `pr` only as a whole word, so `process` does not trip it.
        pattern = rf'\b{stem}\w*' if len(stem) >= 3 else rf'\b{stem}s?\b'
        hit = re.search(pattern, weak, re.IGNORECASE)
        assert not hit, f'a weak shortcut still covers {stem!r}: {hit.group(0)!r}'
    assert 'role floors still apply' in ' '.join(section.split()), 'no pointer to floors'


def main() -> int:
    test_found_the_axes()
    test_each_heading_range_matches_its_table()
    test_clamp_sentence_is_present_and_its_totals_are_true()
    test_role_floors_hold_whatever_the_score()
    test_shortcuts_defer_to_the_role_floors()
    print('ok: scoring_rubric')
    return 0


if __name__ == '__main__':
    sys.exit(main())

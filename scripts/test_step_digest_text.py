"""Pins the parts of the step-digest output style that an edit could lose
without any other check failing.

The style is the final-block specification agreed on 2026-10-25 after
measuring 499 turns of the operator's own sessions: the block a reader who
skipped the whole turn can act on. What is pinned is the shape that the
measurement found missing, not the prose around it:

- the frontmatter keeps Claude Code's coding instructions, so the style only
  changes how the agent reports;
- the four fields appear in this order: Outcome, Decisions, Next, Ask;
- Decisions repeats every ask raised anywhere in the turn and never points to
  an earlier message, which is the measured failure (a third of the asks were
  first raised before the final block and 36% of those were absent from it);
- a decision carries its options and a recommendation, the two items a fresh
  reader most often could not recover from the actual final blocks;
- there is no total word cap, because the shortest final blocks in the data
  were the ones that dropped the most asks;
- text between tool calls is named as narration, not a channel.

Stdlib-runnable: `python scripts/test_step_digest_text.py` prints `ok:`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE = ROOT / 'plugins' / 'session-workflow' / 'output-styles' / 'step-digest.md'

FIELDS = ['**Outcome**', '**Decisions**', '**Next**', '**Ask**']
REPEATED_IN_FULL = 'is repeated here in full'
NO_POINTER = 'never points to an earlier message'
OPTIONS_AND_RECOMMENDATION = 'the options; the recommendation with its reason'
NO_TOTAL_CAP = 'no total word cap'
NOT_A_CHANNEL = 'not a channel'
ONE_QUESTION_LAST = 'as the last line'


def _parts() -> tuple[str, str]:
    text = STYLE.read_text(encoding='utf-8')
    _, front, body = text.split('---', 2)
    return front, body


def test_frontmatter_keeps_the_coding_instructions():
    front, _ = _parts()
    assert re.search(r'^keep-coding-instructions:\s*true\s*$', front, re.M), (
        "step-digest must keep Claude Code's coding instructions"
    )
    assert re.search(r'^name:\s*step-digest\s*$', front, re.M)


def test_the_four_fields_appear_in_order():
    _, body = _parts()
    section = body.split('## The final block', 1)
    assert len(section) == 2, 'the style has no "## The final block" section'
    positions = [section[1].find(f) for f in FIELDS]
    found = dict(zip(FIELDS, positions, strict=True))
    assert all(p >= 0 for p in positions), f'missing field(s): {found}'
    assert positions == sorted(positions), f'fields out of order: {found}'


def test_decisions_repeat_every_ask_and_never_point_back():
    _, body = _parts()
    flat = re.sub(r'\s+', ' ', body)
    assert REPEATED_IN_FULL in flat
    assert NO_POINTER in flat


def test_a_decision_carries_options_and_a_recommendation():
    _, body = _parts()
    flat = re.sub(r'\s+', ' ', body)
    assert OPTIONS_AND_RECOMMENDATION in flat


def test_no_total_word_cap_and_one_question_last():
    _, body = _parts()
    flat = re.sub(r'\s+', ' ', body)
    assert NO_TOTAL_CAP in flat
    assert ONE_QUESTION_LAST in flat
    assert not re.search(r'\b\d{2,4} words\b', flat), 'a numeric word cap crept back in'


def test_interim_text_is_named_as_narration():
    _, body = _parts()
    flat = re.sub(r'\s+', ' ', body)
    assert NOT_A_CHANNEL in flat


if __name__ == '__main__':
    test_frontmatter_keeps_the_coding_instructions()
    test_the_four_fields_appear_in_order()
    test_decisions_repeat_every_ask_and_never_point_back()
    test_a_decision_carries_options_and_a_recommendation()
    test_no_total_word_cap_and_one_question_last()
    test_interim_text_is_named_as_narration()
    print('ok: step-digest keeps its four fields, the repeat-every-ask rule and no total cap')

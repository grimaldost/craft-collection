"""Pins two parts of review-panel's text that an edit could lose without any
other check failing.

- The description's hand-off trigger (T88a) and its draft negative. The case
  that cost the most in the 2026-09-19 triage was a finished design or
  assessment handed to someone who acts on it; the description names that case
  and excludes a draft still being worked. Both phrases are trigger surface, so
  they are pinned verbatim.
- The body's default rung. Level 1, one reviewer subagent that did not see the
  session and is briefed to refute, is the default; Levels 2 and 3 are
  escalations for higher stakes, and the four-lens quartet is the Level 3
  default rather than the skill's. The reference files and the grading
  rubric follow it: no persona pack calls the quartet the skill's default, and
  the correct-usage rubric grades the rung chosen by stakes rather than
  requiring several lenses for a prompt with no stated high stakes.

Stdlib-runnable: `python scripts/test_review_panel_text.py` prints `ok:`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / 'plugins' / 'session-workflow' / 'skills' / 'review-panel' / 'SKILL.md'
REFERENCES = SKILL.parent / 'references'
RUBRIC = ROOT / 'evals' / 'tasks' / 'review-panel' / 'rubric.json'

HANDOFF = (
    'before handing a design, assessment or recommendation you wrote to someone who will act on it'
)
DRAFT_NEGATIVE = 'a first-pass review of a draft still being worked'
DEFAULT_RUNG = (
    'Level 1 is the default: one reviewer subagent that did not see the session, briefed to refute.'
)
LEVEL3_QUARTET = 'Level 3 default quartet'


def _parts():
    text = SKILL.read_text(encoding='utf-8')
    _, front, body = text.split('---', 2)
    match = re.search(r'^description:\s*(.+)$', front, re.M)
    assert match, 'review-panel has no one-line description'
    return match.group(1), re.sub(r'\s+', ' ', body)


def test_description_keeps_the_handoff_trigger_verbatim():
    description, _ = _parts()
    assert HANDOFF in description


def test_description_keeps_the_draft_negative_verbatim():
    description, _ = _parts()
    assert DRAFT_NEGATIVE in description


def test_body_names_level_one_as_the_default_rung():
    _, body = _parts()
    assert DEFAULT_RUNG in body


def test_quartet_is_the_level_three_default():
    _, body = _parts()
    assert LEVEL3_QUARTET in body
    assert 'Default quartet' not in body


def test_no_reference_calls_the_quartet_the_skill_default():
    stale = [
        md.name
        for md in sorted(REFERENCES.glob('*.md'))
        if 'the default quartet' in md.read_text(encoding='utf-8').lower()
    ]
    assert not stale, f'references still call the quartet the default: {stale}'


def test_rubric_grades_the_rung_by_stakes():
    rubric = json.loads(RUBRIC.read_text(encoding='utf-8'))
    text = ' '.join(c['text'] for c in rubric)
    assert 'Level 1' in text, 'the rubric does not name the default rung'
    assert 'Picks several appropriate adversarial lenses' not in text


if __name__ == '__main__':
    test_description_keeps_the_handoff_trigger_verbatim()
    test_description_keeps_the_draft_negative_verbatim()
    test_body_names_level_one_as_the_default_rung()
    test_quartet_is_the_level_three_default()
    test_no_reference_calls_the_quartet_the_skill_default()
    test_rubric_grades_the_rung_by_stakes()
    print('ok: review-panel keeps its hand-off trigger and its one-reviewer default')

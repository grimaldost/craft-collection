#!/usr/bin/env python3
"""Pins for the effort guidance in models.toml and references/emission-and-effort.md
(no pytest required).

The weak tier's response to effort is unmeasured on Haiku 5.5; that Haiku 4.5
accepted the flag and ignored it survives only as dated history in the reference.
Agreement work keeps the `high` default at any tier.
An Agent-tool spawn's effort is counted as inherited. The effort observations behind
the agreement qualifier sit in `[meta]` as one single-line key.
"""

from __future__ import annotations

import sys
from pathlib import Path

import tomllib

SKILL = Path(__file__).resolve().parent.parent
MODELS = SKILL / 'models.toml'
REFERENCE = SKILL / 'references' / 'emission-and-effort.md'


def _models() -> dict:
    with MODELS.open('rb') as fh:
        return tomllib.load(fh)


def _reference() -> str:
    return ' '.join(REFERENCE.read_text(encoding='utf-8').split())


def test_weak_tier_note_marks_effort_unmeasured():
    data = _models()
    weak = next(m for m in data['models'] if m['tier'] == 'weak')
    notes = weak['notes']
    assert 'errors if set' not in notes, notes
    assert 'accepted and ignored' not in notes, 'Haiku 4.5 behaviour carried over to Haiku 5.5'
    assert 'effort behaviour' in notes and 'unmeasured' in notes, notes
    assert 'direct API' not in notes, 'the note must not assert unmeasured surfaces'


def test_reference_keeps_the_haiku_4_5_reading_as_dated_history():
    text = _reference()
    assert 'no effort knob at all' not in text
    assert 'weak tier has no effort dimension' not in text
    assert 'unmeasured on Haiku 5.5' in text
    assert 'Haiku 4.5 accepted the flag and ignored it (measured 2026-09-13' in text


def test_agreement_work_keeps_the_high_default():
    text = _reference()
    assert 'agreement between two independent statements of one rule' in text
    assert 'any tier and any diff size' in text
    for example in (
        'two readers of one domain rule',
        'a pin and its vocabulary',
        'a docstring promise and its binding',
        'a mirror and its source',
    ):
        assert example in text, example


def test_agent_tool_effort_is_counted_as_inherited():
    text = _reference()
    assert 'inherited, not chosen' in text
    assert '110 of 127' in text
    assert 'effort-sensitive batch' in text


def test_effort_observations_recorded_in_meta():
    meta = _models()['meta']
    obs = meta.get('effort_observations')
    assert isinstance(obs, str) and obs, 'meta.effort_observations missing'
    assert '\n' not in obs
    for needle in (
        'A: 50, sonnet/medium, 2 rounds',
        'B: 73, opus/medium, 3 rounds',
        'C: 88, opus/high, 1 round',
        'D1: 60, opus/medium, 0 rounds',
        'D2: 96, opus/high, 1 round',
        'PR-G: small diff, sonnet/medium, 2 rounds',
    ):
        assert needle in obs, needle
    assert '2026-09-20' in obs and '2026-09-28' in obs


def test_new_key_sits_above_the_first_model_block():
    text = MODELS.read_text(encoding='utf-8')
    assert text.index('effort_observations') < text.index('[[models]]')


def main() -> int:
    test_weak_tier_note_marks_effort_unmeasured()
    test_reference_keeps_the_haiku_4_5_reading_as_dated_history()
    test_agreement_work_keeps_the_high_default()
    test_agent_tool_effort_is_counted_as_inherited()
    test_effort_observations_recorded_in_meta()
    test_new_key_sits_above_the_first_model_block()
    print('ok: effort_guidance')
    return 0


if __name__ == '__main__':
    sys.exit(main())

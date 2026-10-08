"""Drift test: every copy of the anchor's authority rule says the same thing.

The rule has three parts. The anchor has authority over task position only (the
cursor). It records the owner's authorizations as dated, literal quotes: a record
of what the owner said and when, never a grant the anchor makes itself. And a rule
that must never be broken belongs in a hook that enforces it, because an anchor is
prose that a compaction summary or a later edit can lose.

The rule is written in three places a writer reads: the skill body, the reference
spec and the /anchor command's snapshot recipe. Only the section order was pinned
across them before (test_anchor_section_order.py), so a copy could drop the rule
without any check noticing.

Stdlib-runnable: `python test_anchor_authority.py` runs every test and prints `ok:`.
"""

import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PLUGIN_DIR = SKILL_DIR.parent.parent
SKILL = SKILL_DIR / 'SKILL.md'
SPEC = SKILL_DIR / 'references' / 'anchor-spec.md'
FAILURES = SKILL_DIR / 'references' / 'failure-modes.md'
COMMAND = PLUGIN_DIR / 'commands' / 'anchor.md'

COPIES = (SKILL, SPEC, COMMAND)

KEY_SENTENCE = (
    'A rule that must never be broken belongs in a hook that enforces it, not in the anchor.'
)
AUTHORITY = 'authority over task position only'
AUTHORIZATIONS = 'dated, literal quotes'
FREEZE = 'New anchor features are frozen as of 0.26.0'


def _flat(path):
    """File text with every whitespace run collapsed, so a re-wrap is not drift."""
    return re.sub(r'\s+', ' ', path.read_text(encoding='utf-8'))


def _missing(phrase):
    return [p.name for p in COPIES if phrase not in _flat(p)]


def test_key_sentence_in_every_copy():
    assert not _missing(KEY_SENTENCE), _missing(KEY_SENTENCE)


def test_authority_is_task_position_only_in_every_copy():
    assert not _missing(AUTHORITY), _missing(AUTHORITY)


def test_authorizations_are_dated_literal_quotes_in_every_copy():
    assert not _missing(AUTHORIZATIONS), _missing(AUTHORIZATIONS)


def test_failure_modes_name_both_misses():
    text = _flat(FAILURES).lower()
    assert 'authorization' in text and 'undated' in text, 'no row for an undated authorization'
    assert 'kept only in the anchor' in text, 'no row for a never-break rule kept only in prose'


def test_skill_states_the_feature_freeze_once():
    assert _flat(SKILL).count(FREEZE) == 1


if __name__ == '__main__':
    test_key_sentence_in_every_copy()
    test_authority_is_task_position_only_in_every_copy()
    test_authorizations_are_dated_literal_quotes_in_every_copy()
    test_failure_modes_name_both_misses()
    test_skill_states_the_feature_freeze_once()
    print('ok: the anchor authority rule agrees across the skill, spec and command')

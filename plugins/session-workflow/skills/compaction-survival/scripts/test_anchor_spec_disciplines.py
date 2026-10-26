"""The anchor spec carries the disciplines in force (spec 2026-10-25, section 2).

A compaction drops the skill bodies a run had loaded along with the rest of its
context, and the anchor named only where the run was, not how it was working. The
reference spec therefore asks the Invariants section for a "Disciplines in force"
line (each governing skill and the phase it governs) and the Resume steps for the
instruction to load each of them before the first action.

Stdlib-runnable: `python test_anchor_spec_disciplines.py` runs every test and prints `ok:`.
"""

import re
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / 'references' / 'anchor-spec.md'


def _section(name: str) -> str:
    """The text of one `### <name>` section of the spec, whitespace collapsed."""
    text = SPEC.read_text(encoding='utf-8')
    m = re.search(rf'^### {re.escape(name)}\n(.*?)(?=^#{{2,3}} |\Z)', text, re.M | re.S)
    assert m, f'anchor-spec.md has no ### {name} section'
    return re.sub(r'\s+', ' ', m.group(1))


def test_invariants_ask_for_a_disciplines_in_force_line_naming_skill_and_phase():
    body = _section('Invariants')
    assert 'Disciplines in force' in body, body
    assert 'each skill that governs the work and the phase it governs' in body, body


def test_resume_steps_load_each_discipline_before_the_first_action():
    body = _section('Resume steps')
    assert 'Disciplines in force' in body, body
    assert 'before the first action' in body, body


if __name__ == '__main__':
    test_invariants_ask_for_a_disciplines_in_force_line_naming_skill_and_phase()
    test_resume_steps_load_each_discipline_before_the_first_action()
    print('ok: the anchor spec names the disciplines in force and loads them on resume')

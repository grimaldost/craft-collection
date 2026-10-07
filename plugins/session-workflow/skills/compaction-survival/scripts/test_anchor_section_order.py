"""Drift test: every file that lists the anchor's HEAD sections lists them in
the same order.

The order is the survival order (the injection spends the budget top-down), so
a copy that lists the sections differently teaches a writer to put the wrong
section first. The reference spec is the source; the other three are copies:

- references/anchor-spec.md: the `### ` headings under `## HEAD`;
- SKILL.md: the numbered list between the `HEAD` lead-in and the `TAIL` lead-in;
- commands/anchor.md: the bold-led bullets of the snapshot step, minus the
  frontmatter bullet and the tail's decisions log;
- references/cold-start.md: the parenthetical section list in the by-hand recipe.

Stdlib-runnable: `python test_anchor_section_order.py` runs every test and
prints `ok:`.
"""

import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PLUGIN_DIR = SKILL_DIR.parent.parent
SPEC = SKILL_DIR / 'references' / 'anchor-spec.md'
COLD_START = SKILL_DIR / 'references' / 'cold-start.md'
SKILL = SKILL_DIR / 'SKILL.md'
COMMAND = PLUGIN_DIR / 'commands' / 'anchor.md'

# Bullets in the command's snapshot step that are not HEAD sections.
NOT_HEAD = {'frontmatter', 'decisions log'}


def _norm(name):
    return re.sub(r'\s+', ' ', name).strip().rstrip('.').lower()


def _read(path):
    return path.read_text(encoding='utf-8')


def spec_order():
    text = _read(SPEC)
    head = text.split('\n## HEAD', 1)[1].split('\n## ', 1)[0]
    return [_norm(m) for m in re.findall(r'^### (.+)$', head, re.M)]


def skill_order():
    text = _read(SKILL)
    start = text.index('HEAD — bounded')
    end = text.index('TAIL —', start)
    return [_norm(m) for m in re.findall(r'^\d+\. \*\*([^*]+)\*\*', text[start:end], re.M)]


def command_order():
    text = _read(COMMAND)
    step = text.split('## Otherwise: snapshot', 1)[1]
    step = step.split('\n4. ', 1)[1].split('\n5. ', 1)[0]
    names = [_norm(m) for m in re.findall(r'^\s+- \*\*([^*]+)\*\*', step, re.M)]
    return [n for n in names if n not in NOT_HEAD]


def cold_start_order():
    text = re.sub(r'\s+', ' ', _read(COLD_START))
    m = re.search(r'section list \(([^)]*)\)', text)
    assert m, 'cold-start.md no longer carries a parenthetical section list'
    return [_norm(p) for p in m.group(1).split(',')]


def test_spec_lists_the_eight_head_sections():
    order = spec_order()
    assert order[0] == 'mission' and order[1] == 'cursor', order
    assert len(order) == len(set(order)) >= 8, order


def test_skill_body_order_matches_the_spec():
    assert skill_order() == spec_order(), (skill_order(), spec_order())


def test_command_snapshot_order_matches_the_spec():
    assert command_order() == spec_order(), (command_order(), spec_order())


def test_cold_start_section_list_matches_the_spec():
    assert cold_start_order() == spec_order(), (cold_start_order(), spec_order())


def test_command_states_no_section_count():
    step = _read(COMMAND).split('## Otherwise: snapshot', 1)[1]
    assert not re.search(r'\b(all )?(six|seven|eight|nine|\d+) (categories|sections)\b', step)


if __name__ == '__main__':
    test_spec_lists_the_eight_head_sections()
    test_skill_body_order_matches_the_spec()
    test_command_snapshot_order_matches_the_spec()
    test_cold_start_section_list_matches_the_spec()
    test_command_states_no_section_count()
    print('ok: anchor section order agrees across the spec, skill, command and cold start')

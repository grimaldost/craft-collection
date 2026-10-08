"""Manual-only skills and commands stay manual-only, and the eval engine does not
try to measure their auto-activation.

`disable-model-invocation: true` keeps a skill or command out of the model's
reach: only the owner runs it, as a slash command. Two things drift silently
without a check:

- a later frontmatter edit drops the flag, and the model starts invoking a
  maintenance pass (or the /anchor snapshot) on its own again;
- a manual-only skill stays in `evals/config.json`'s `plugin_of_skill`, so the
  trigger arm scores its by-design silence as a recall failure. The rule is
  prose in evaluate-skill's references/eval-harness.md; this makes it a check.

Stdlib-runnable: `python scripts/test_manual_only_skills.py` prints `ok:`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SW = ROOT / 'plugins' / 'session-workflow'

MANUAL_ONLY = (
    SW / 'skills' / 'feedback-triage' / 'SKILL.md',
    SW / 'skills' / 'consolidate-knowledge' / 'SKILL.md',
    SW / 'skills' / 'evaluate-skill' / 'SKILL.md',
    SW / 'commands' / 'anchor.md',
)

FLAG = re.compile(r'^disable-model-invocation:\s*true\s*$', re.M)
NAME = re.compile(r'^name:\s*(\S+)\s*$', re.M)


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    assert text.startswith('---'), f'{path} has no frontmatter'
    return text.split('---', 2)[1]


def manual_only_skill_names(root: Path = ROOT) -> set[str]:
    names = set()
    for skill in sorted(root.glob('plugins/*/skills/*/SKILL.md')):
        block = frontmatter(skill)
        if FLAG.search(block):
            match = NAME.search(block)
            names.add(match.group(1) if match else skill.parent.name)
    return names


def test_the_four_manual_only_files_carry_the_flag():
    missing = [
        p.relative_to(ROOT).as_posix() for p in MANUAL_ONLY if not FLAG.search(frontmatter(p))
    ]
    assert not missing, f'disable-model-invocation: true is missing from {missing}'


def test_no_plugin_of_skill_key_names_a_manual_only_skill():
    cfg = json.loads((ROOT / 'evals' / 'config.json').read_text(encoding='utf-8'))
    clash = sorted(manual_only_skill_names() & set(cfg['plugin_of_skill']))
    assert not clash, f'manual-only skills listed in evals/config.json plugin_of_skill: {clash}'


def test_the_scan_sees_the_known_manual_only_skills():
    # Guards the check above against going vacuous: if the frontmatter scan stops
    # finding the flag, the intersection is empty for the wrong reason.
    assert {'refresh-stack', 'refresh-models'} <= manual_only_skill_names()


if __name__ == '__main__':
    test_the_four_manual_only_files_carry_the_flag()
    test_no_plugin_of_skill_key_names_a_manual_only_skill()
    test_the_scan_sees_the_known_manual_only_skills()
    print('ok: manual-only skills carry the flag and are out of plugin_of_skill')

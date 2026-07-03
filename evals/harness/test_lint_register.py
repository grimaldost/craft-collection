#!/usr/bin/env python3
"""Self-contained checks for scripts/lint_register.py (no pytest required)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import lint_register  # noqa: E402


def _lint_text(text: str) -> list[str]:
    with tempfile.TemporaryDirectory() as td:
        sample = Path(td) / 'sample.md'
        sample.write_text(text, encoding='utf-8')
        return lint_register.lint_file(sample)


def main() -> int:
    # Denied phrases are caught.
    assert _lint_text('You MUST USE this skill.'), 'MUST USE not flagged'
    assert _lint_text('This is EXTREMELY-IMPORTANT.'), 'importance banner not flagged'
    assert _lint_text('The IRON LAW applies here.'), 'IRON LAW not flagged'

    # `non-negotiable` is a SELECTION-surface rule: flagged in a description
    # (frontmatter), where it is always a salience buy; allowed in body prose,
    # where 'the four non-negotiables of a data contract' is domain terminology,
    # not coercion. (Genuine body coercion is still caught by the always-on
    # patterns below.)
    fm = '---\nname: s\ndescription: {desc}\n---\n# S\n'
    assert _lint_text(fm.format(desc='Using this skill is non-negotiable.')), (
        'non-negotiable in a description not flagged'
    )
    assert _lint_text(fm.format(desc='It is Not Negotiable.')), (
        'mixed-case non-negotiable in a description not flagged'
    )
    assert not _lint_text('# S\n\nThe four non-negotiables of a data contract.\n'), (
        'non-negotiable in body prose (no frontmatter) wrongly flagged'
    )
    assert not _lint_text(
        '---\nname: s\ndescription: ok.\n---\n\nThese rules are non-negotiable.\n'
    ), 'non-negotiable in body prose (after frontmatter) wrongly flagged'
    # Always-on coercion is still caught in the body, so scoping non-negotiable
    # did not over-widen into "bodies are unlinted".
    assert _lint_text('---\nname: s\ndescription: ok.\n---\n\nYou MUST USE this.\n'), (
        'body imperative-obedience no longer flagged (over-scoped)'
    )

    # Caps runs: three consecutive non-acronym caps words flag; acronyms do not.
    assert _lint_text('FOLLOW THESE RULES exactly.'), 'caps banner run not flagged'
    assert not _lint_text('Use TDD with CI on every PR.'), 'acronym sequence wrongly flagged'
    assert not _lint_text('TWO CAPS words are fine.'), 'two-word run wrongly flagged'

    # Code is exempt.
    assert not _lint_text('```\nYOU MUST USE CAPS IN CODE\n```\n'), 'fenced code not exempt'
    assert not _lint_text('Set `YOU MUST` in the config.'), 'inline code not exempt'

    # Line-start importance banners (below the caps-run threshold) are flagged;
    # a lowercase word mid-sentence is not.
    assert _lint_text('IMPORTANT: Always read this first.'), 'IMPORTANT banner not flagged'
    assert _lint_text('**CRITICAL:** do the thing.'), 'CRITICAL banner not flagged'
    assert not _lint_text('It is important to test edge cases.'), 'lowercase word wrongly flagged'

    # Salience/priority phrasings are flagged case-insensitively.
    assert _lint_text('This skill takes priority over the others.'), 'priority claim not flagged'
    assert _lint_text('Always use this skill before any other.'), 'obedience phrase not flagged'

    # Banner terminators beyond ':' / '!' — dash, comma, end-of-clause, bare line —
    # and emphasis beyond '**' ('_', '*', '***') buy the same salience.
    assert _lint_text('IMPORTANT — read this first.'), 'em-dash banner not flagged'
    assert _lint_text('IMPORTANT, always do this.'), 'comma banner not flagged'
    assert _lint_text('_CRITICAL_: do the thing.'), 'underscore-emphasis banner not flagged'
    assert _lint_text('*CRITICAL*: do the thing.'), 'single-star-emphasis banner not flagged'
    assert _lint_text('***MANDATORY*** - follow the steps.'), 'triple-star banner not flagged'
    assert _lint_text('MANDATORY. Then continue.'), 'period-terminated banner not flagged'
    assert _lint_text('FORBIDDEN\n'), 'bare standalone banner word not flagged'
    # A capitalized word merely STARTING a sentence is not a banner.
    assert not _lint_text('CRITICAL failures need a rollback plan.'), (
        'caps word starting a sentence wrongly flagged'
    )

    # Fence desync: an unpaired inner marker (a ~~~ line inside a ``` block) must NOT
    # disable linting for the rest of the file — the CommonMark rule closes a fence
    # only on the same marker char with length >= the opener.
    desync = '```text\n~~~\n```\nYOU MUST USE this skill.\n'
    assert _lint_text(desync), 'deny pattern after a desyncing inner fence marker not flagged'

    # The ENTIRE plugins tree passes under the repo-wide default scope — the
    # register doctrine governs the shared selection pool, not just humblepowers.
    tree = lint_register.lint_paths([ROOT / 'plugins'])
    assert not tree, f'plugins tree fails the register linter: {tree}'

    print('ok: lint_register')
    return 0


if __name__ == '__main__':
    sys.exit(main())

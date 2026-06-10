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
    assert _lint_text('This rule is non-negotiable.'), 'non-negotiable not flagged'
    assert _lint_text('It is Not Negotiable.'), 'mixed-case non-negotiable not flagged'

    # Caps runs: three consecutive non-acronym caps words flag; acronyms do not.
    assert _lint_text('FOLLOW THESE RULES exactly.'), 'caps banner run not flagged'
    assert not _lint_text('Use TDD with CI on every PR.'), 'acronym sequence wrongly flagged'
    assert not _lint_text('TWO CAPS words are fine.'), 'two-word run wrongly flagged'

    # Code is exempt.
    assert not _lint_text('```\nYOU MUST USE CAPS IN CODE\n```\n'), 'fenced code not exempt'
    assert not _lint_text('Set `YOU MUST` in the config.'), 'inline code not exempt'

    # The shipped plugin passes its own linter.
    findings = lint_register.lint_paths([ROOT / 'plugins' / 'humblepowers'])
    assert not findings, f'humblepowers fails its own register linter: {findings}'

    print('ok: lint_register')
    return 0


if __name__ == '__main__':
    sys.exit(main())

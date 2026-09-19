#!/usr/bin/env python3
"""Docs-truth check: the non-executable-artifact Red exception (T86a) stays worded.

Owner decision (2026-09-19 triage, T86a): the substitution -- restore the
artifact's previous version from version control, watch the new assertions
fail against it, then restore the change -- is sanctioned as a watched red
ONLY for non-executable artifacts (docs, templates, prompt/directive text,
configuration read as data). Code keeps the delete-and-redo rule. This script
guards the SKILL.md body against losing either half of that boundary --
silently, in a later edit, with no test noticing.

    python check_red_exception.py [skill_dir]

`skill_dir` defaults to this script's own skill (test-driven-development).
Stdlib only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = (
    'non-executable artifacts only',
    "restore the artifact's previous version from version control",
    'watch the new assertions',
    'restore the change',
)
# The boundary must still name code as excluded from the substitution.
CODE_BOUNDARY = ('no such substitute', 'never code')


def check(text: str) -> list[str]:
    """Findings for a SKILL.md body missing the exception or its boundary. Pure.

    Markdown prose wraps at line boundaries, so a required phrase is matched
    against whitespace-normalized text (newlines folded to single spaces) --
    otherwise a harmless reflow would falsely redden this check.
    """
    normalized = ' '.join(text.split())
    findings = []
    for phrase in REQUIRED:
        if phrase not in normalized:
            findings.append(f'missing required phrase: {phrase!r}')
    if not any(phrase in normalized for phrase in CODE_BOUNDARY):
        findings.append(
            f'the code exclusion is missing: neither {CODE_BOUNDARY!r} phrase is present'
        )
    return findings


def run(skill_dir: Path) -> list[str]:
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.is_file():
        return [f'{skill_md}: not found']
    return check(skill_md.read_text(encoding='utf-8'))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    skill_dir = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent
    findings = run(skill_dir)
    for finding in findings:
        print(f'  {finding}')
    if findings:
        print(f'FAIL: {len(findings)} finding(s) against the T86a Red exception')
        return 1
    print('ok: the non-executable-artifact Red exception is worded and bounded')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

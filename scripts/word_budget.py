#!/usr/bin/env python3
"""Word-budget ratchet for skill bodies (issue #54).

A skill's eager body accretes silently over time — `feedback-triage` grew 806 -> 1621
words in 19 days. This records a per-skill body word-count baseline in `word_budget.json`;
`validate_plugins` fails when a body exceeds its baseline. Growing a body means bumping
its baseline in a visible, reviewed diff — which is exactly where the change names what
the growth displaces (the "a prose append names what it displaces" doctrine, mechanized).

The **body** is everything after the SKILL.md frontmatter block; the frontmatter
`description` has its own budget (`DESC_CAP` in `validate_plugins.py`). A word is a
whitespace-separated token — reproducible, not a proxy for rendered length. Shrinking a
body is always fine; only growth past the baseline trips.

    python scripts/word_budget.py            # check the tree against word_budget.json
    python scripts/word_budget.py --seed     # (re)write word_budget.json from the tree

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / 'scripts' / 'word_budget.json'


def body_word_count(text: str) -> int:
    """Words in a SKILL.md BODY — everything after the frontmatter block. The
    frontmatter is delimited by the first two `---` lines; a `---` horizontal rule
    inside the body is preserved (split stops after two delimiters). A file without
    frontmatter counts whole. Words are whitespace-separated tokens. Pure."""
    if text.startswith('---'):
        parts = text.split('---', 2)
        body = parts[2] if len(parts) == 3 else text
    else:
        body = text
    return len(body.split())


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def skill_files(root: Path = ROOT) -> list[Path]:
    return sorted(root.glob('plugins/*/skills/*/SKILL.md'))


def current_counts(root: Path = ROOT) -> dict[str, int]:
    """{skill-path: body-word-count} for every SKILL.md in the tree."""
    out: dict[str, int] = {}
    for p in skill_files(root):
        out[p.relative_to(root).as_posix()] = body_word_count(p.read_text(encoding='utf-8'))
    return out


def load_baselines(path: Path = BUDGET_FILE) -> dict[str, int]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def check_budgets(counts: dict[str, int], baselines: dict[str, int]) -> list[str]:
    """Return budget violations (empty == all within budget). A body over its baseline
    fails; a body with no baseline fails (a new skill must record one). Equal or smaller
    passes. Pure — feed it counts and baselines, no I/O."""
    errors: list[str] = []
    for path, count in sorted(counts.items()):
        base = baselines.get(path)
        if base is None:
            errors.append(f'{path}: no word-budget baseline — add one to word_budget.json')
        elif count > base:
            errors.append(
                f'{path}: body {count} words > budget {base} — either shrink it, or bump '
                f'the baseline in word_budget.json and name what the growth displaces'
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Skill-body word-budget ratchet (issue #54)')
    ap.add_argument(
        '--seed', action='store_true', help='(re)write word_budget.json from the current tree'
    )
    args = ap.parse_args(argv)
    counts = current_counts()
    if args.seed:
        BUDGET_FILE.write_text(
            json.dumps(dict(sorted(counts.items())), indent=2) + '\n', encoding='utf-8'
        )
        print(f'seeded {len(counts)} baseline(s) -> {_rel(BUDGET_FILE)}')
        return 0
    errors = check_budgets(counts, load_baselines())
    if errors:
        print('WORD BUDGET EXCEEDED:')
        for e in errors:
            print(f'  - {e}')
        return 1
    print(f'word budget: {len(counts)} skill bodies within budget')
    return 0


if __name__ == '__main__':
    sys.exit(main())

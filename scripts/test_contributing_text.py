"""Pins two statements of CONTRIBUTING.md that an edit could lose unnoticed.

- The "Stacked PRs" bullet states both outcomes: the base merges and GitHub
  retargets the stacked pull request, or the base closes and the stack needs a
  rebase. The earlier text promised no rebase in every case.
- The hook counts the release check compares are the root README's summaries
  only; a hooks.json description carries no count word.

Stdlib-runnable: `python scripts/test_contributing_text.py` prints `ok:`.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRIBUTING = ROOT / 'CONTRIBUTING.md'


def _text() -> str:
    return ' '.join(CONTRIBUTING.read_text(encoding='utf-8').split())


def _stacked_bullet() -> str:
    text = _text()
    start = text.index('**Stacked PRs:**')
    end = text.find(' ## ', start)
    return text[start : end if end > 0 else len(text)]


def test_the_stacked_pr_bullet_states_both_outcomes():
    bullet = _stacked_bullet()
    assert 'retargets' in bullet, bullet
    assert 'closes' in bullet, bullet
    assert 'no rebase dance needed' not in bullet, bullet


def test_the_hook_counts_checked_are_the_root_readme_summaries_only():
    assert 'hook counts in a `hooks.json` description' not in _text()


if __name__ == '__main__':
    test_the_stacked_pr_bullet_states_both_outcomes()
    test_the_hook_counts_checked_are_the_root_readme_summaries_only()
    print(
        'ok: CONTRIBUTING states both stacked-PR outcomes and the root README as the only hook-count source'
    )

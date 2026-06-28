"""Tests that the bundled evaluate-skill engine matches this harness verbatim.

The plugin ships `plugins/session-workflow/skills/evaluate-skill/scripts/*.py` as a
distribution template (users copy them into their own project's `evals/harness/`).
Those copies must not drift behind this harness — a stale template ships a regressed
engine (missing preflight_auth, action-discipline gating, error sampling, ...).

Runnable with pytest or `python test_scripts_in_sync.py`.
"""

from __future__ import annotations

from pathlib import Path

HARNESS = Path(__file__).resolve().parent
REPO = HARNESS.parents[1]
BUNDLED = REPO / 'plugins' / 'session-workflow' / 'skills' / 'evaluate-skill' / 'scripts'
SYNCED = (
    'aggregate.py',
    'claude_runner.py',
    'grade_tasks.py',
    'judge.py',
    'run_all.py',
    'run_triggers.py',
    'stats.py',
)


def _norm(p: Path) -> str:
    return p.read_text(encoding='utf-8').replace('\r\n', '\n')


def test_bundled_matches_harness():
    for name in SYNCED:
        h, b = HARNESS / name, BUNDLED / name
        assert b.exists(), f'bundled copy missing: {b}'
        assert _norm(b) == _norm(h), (
            f'{name}: bundled copy has drifted from evals/harness/{name}. '
            f'Re-copy: cp evals/harness/{name} {b}'
        )


def test_no_unsynced_engine_file():
    # A new bundled .py with no harness twin would silently escape the check above.
    bundled = {p.name for p in BUNDLED.glob('*.py')}
    assert bundled == set(SYNCED), f'bundled engine set changed: {bundled ^ set(SYNCED)}'


if __name__ == '__main__':
    test_bundled_matches_harness()
    test_no_unsynced_engine_file()
    print('ok: bundled evaluate-skill engine in sync with harness')

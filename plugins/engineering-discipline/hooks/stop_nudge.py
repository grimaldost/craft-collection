#!/usr/bin/env python3
"""Optional Stop hook: nudge to run the data pre-shipping checklist.

INERT by default — prints only if DATAENG_CHECKLIST_NUDGE=1 AND the session's
git diff touched files that look like data-pipeline code. Non-blocking: always
exits 0 (the reminder goes to stderr). Stdlib only.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys

# Default "looks like pipeline code" globs; override via DATAENG_PIPELINE_GLOBS.
DEFAULT_GLOBS = ('*.sql', '*dbt*', '*pipeline*', '*etl*', 'models/*', '*/models/*')


def should_nudge(changed_files: list[str], globs: tuple[str, ...] = DEFAULT_GLOBS) -> bool:
    """True if any changed path matches a pipeline-ish glob."""
    return any(fnmatch.fnmatch(f, g) for f in changed_files for g in globs)


def _changed_files() -> list[str]:
    try:
        out = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD'],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return []
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def main() -> int:
    try:
        sys.stdin.read()  # drain the Stop payload; content is not needed
    except OSError:
        pass
    if os.environ.get('DATAENG_CHECKLIST_NUDGE') != '1':
        return 0
    env_globs = tuple(g for g in os.environ.get('DATAENG_PIPELINE_GLOBS', '').split(',') if g)
    if should_nudge(_changed_files(), env_globs or DEFAULT_GLOBS):
        print(
            'Data-pipeline files changed - run the pre-shipping checklist '
            '(schema, row count, group cardinality, null rates, sums, replay) '
            'before declaring done.',
            file=sys.stderr,
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())

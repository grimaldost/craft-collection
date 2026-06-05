#!/usr/bin/env python3
"""Discover and run every `test_*.py` under plugins/ and evals/.

Each test module is self-contained (no pytest required): it prints an `ok:` line
on success and raises on failure. Run from the repo root:

    python scripts/run_tests.py

Exits non-zero if any module fails. Used by CI and the pre-push hook.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = ('plugins', 'evals')


def discover() -> list[Path]:
    return sorted(t for d in SEARCH_DIRS for t in (ROOT / d).rglob('test_*.py'))


def main() -> int:
    tests = discover()
    if not tests:
        print('no test_*.py files found')
        return 1
    failed: list[str] = []
    for t in tests:
        rel = t.relative_to(ROOT)
        # Each test imports its siblings by module name, so run it from its own dir.
        proc = subprocess.run(  # noqa: S603 - test paths come from rglob, not user input
            [sys.executable, t.name], cwd=t.parent, capture_output=True, text=True
        )
        print(f'{"PASS" if proc.returncode == 0 else "FAIL"} {rel}')
        if proc.returncode != 0:
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            failed.append(str(rel))
    print('---')
    print(f'{len(tests) - len(failed)}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Discover and run every `test_*.py` under plugins/ and evals/.

Each test module is self-contained (no pytest required): it prints an `ok:`
line on success (or an explicit `skip: <reason>` when a dependency is
missing) and raises on failure. The sentinel is enforced, not just convention:
a module that exits 0 without printing one ran zero tests (the vacuous-gate
class — e.g. a pytest-fixture-only file that bare python collects nothing
from) and FAILS the suite. Run from the repo root:

    python scripts/run_tests.py [root]

`root` (optional) points the discovery at another tree — used by the runner's
own tests. Exits non-zero if any module fails. Used by CI and the pre-push hook.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = ('plugins', 'evals')


def discover(root: Path = ROOT) -> list[Path]:
    return sorted(t for d in SEARCH_DIRS for t in (root / d).rglob('test_*.py'))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]).resolve() if argv else ROOT
    tests = discover(root)
    if not tests:
        print('no test_*.py files found')
        return 1
    failed: list[str] = []
    for t in tests:
        rel = t.relative_to(root)
        # Each test imports its siblings by module name, so run it from its own dir.
        proc = subprocess.run(  # noqa: S603 - test paths come from rglob, not user input
            [sys.executable, t.name], cwd=t.parent, capture_output=True, text=True
        )
        has_sentinel = any(line.startswith(('ok:', 'skip:')) for line in proc.stdout.splitlines())
        ok = proc.returncode == 0 and has_sentinel
        print(f'{"PASS" if ok else "FAIL"} {rel}')
        if not ok:
            if proc.returncode == 0:
                print(
                    "  exit 0 without an 'ok:'/'skip:' sentinel on stdout — "
                    'the module ran zero tests (vacuous pass)'
                )
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            failed.append(str(rel))
    print('---')
    print(f'{len(tests) - len(failed)}/{len(tests)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

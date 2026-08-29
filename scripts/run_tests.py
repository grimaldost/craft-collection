#!/usr/bin/env python3
"""Discover and run every `test_*.py` under plugins/, evals/, and scripts/.

Each test module is self-contained (no pytest required): it prints an `ok:`
line on success (or an explicit `skip: <reason>` when a dependency is
missing) and raises on failure. The sentinel is enforced, not just convention:
a module that exits 0 without printing one ran zero tests (the vacuous-gate
class — e.g. a pytest-fixture-only file that bare python collects nothing
from) and FAILS the suite. Run from the repo root:

    python scripts/run_tests.py [root]

`root` (optional) points the discovery at another tree — used by the runner's
own tests. Exits non-zero if any module fails. Used by CI and the pre-push hook.

Discovery walks the working tree (`rglob`), not the git index, so untracked or
gitignored test files run locally and do not run in CI — the local module count
can legitimately exceed CI's.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = ('plugins', 'evals', 'scripts')


def discover(root: Path = ROOT) -> list[Path]:
    return sorted(t for d in SEARCH_DIRS for t in (root / d).rglob('test_*.py'))


def working_tree_state(root: Path) -> str | None:
    """`git status --porcelain` for `root`, or None when it cannot be read.

    GIT_* is scrubbed so `-C` is authoritative: git exports the repository
    location into every hook it runs, and an ambient GIT_DIR would answer about
    the OUTER repository instead -- the same trap the repo scripts scrub for.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ['git', '-C', str(root), 'status', '--porcelain'],  # noqa: S607 - PATH git
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]).resolve() if argv else ROOT
    tests = discover(root)
    if not tests:
        print('no test_*.py files found')
        return 1
    # The cheaper, stronger invariant beside the per-script isolation tests: a
    # full suite run must leave the working tree byte-identical. A test that
    # writes into the repo instead of a temp dir -- or a script that resolves git
    # against the wrong tree and mutates it -- shows up here even when every
    # module passes, which is exactly the shape those failures take.
    before = working_tree_state(root)
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
    after = working_tree_state(root)
    if before is not None and after is not None and before != after:
        print('WORKING TREE CHANGED during the suite run (tests must not write into the repo):')
        before_lines = set(before.splitlines())
        for line in after.splitlines():
            if line not in before_lines:
                print(f'  + {line}')
        after_lines = set(after.splitlines())
        for line in before.splitlines():
            if line not in after_lines:
                print(f'  - {line}')
        return 1
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

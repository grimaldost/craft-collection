"""Self-contained checks for scripts/run_tests.py — the pre-push/CI runner.

The gate under test: a module that exits 0 without printing an `ok:` (or an
explicit `skip:`) sentinel ran zero tests and must FAIL the suite. This is the
vacuous-gate class — a pytest-fixture-only module under bare python collects
nothing, prints nothing, exits 0, and a green suite hides a disconnected
safety net (test_anchor_inject shipped that way for three releases).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / 'scripts' / 'run_tests.py'


def _run_suite(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(RUNNER), str(root)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def _fixture(root: Path, name: str, body: str) -> None:
    d = root / 'plugins' / 'x'
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding='utf-8')


def test_silent_exit0_module_fails_the_suite():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _fixture(root, 'test_silent.py', 'x = 1\n')  # exits 0, prints nothing
        proc = _run_suite(root)
    assert proc.returncode == 1, proc.stdout
    assert 'FAIL' in proc.stdout and 'test_silent.py' in proc.stdout
    assert 'sentinel' in proc.stdout  # the reason is named, not just a bare FAIL


def test_ok_and_skip_sentinels_pass():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _fixture(root, 'test_good.py', "print('ok: good')\n")
        _fixture(root, 'test_skipped.py', "print('skip: optional dependency not installed')\n")
        proc = _run_suite(root)
    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.count('PASS') == 2


def test_raising_module_still_fails():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _fixture(root, 'test_boom.py', "print('ok: lies')\nraise AssertionError('boom')\n")
        proc = _run_suite(root)
    assert proc.returncode == 1
    assert 'FAIL' in proc.stdout  # a sentinel never outweighs a non-zero exit


def _git(cwd: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(cwd), *args],  # noqa: S607 - git resolved from PATH
        check=True,
        capture_output=True,
        timeout=60,
        env=env,
    )


def test_a_test_that_dirties_the_repo_fails_the_suite():
    """The cheaper, stronger invariant beside the per-script GIT_* isolation
    tests: a full run leaves the working tree byte-identical. A module that
    writes into the repo instead of a temp dir passes on its own and is caught
    only here -- and it is made to fail on purpose, since a clean-tree assertion
    that has never gone red proves nothing."""
    if not shutil.which('git'):
        return
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _git(root, 'init', '-q')
        body = (
            'import pathlib\n'
            "pathlib.Path(__file__).parent.joinpath('residue.txt').write_text('x')\n"
            "print('ok: but it left something behind')\n"
        )
        _fixture(root, 'test_writes.py', body)
        _git(root, 'add', '-A')
        _git(root, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'fixture')
        proc = _run_suite(root)
    assert proc.returncode == 1, proc.stdout
    assert 'WORKING TREE CHANGED' in proc.stdout, proc.stdout
    assert 'residue.txt' in proc.stdout, proc.stdout


if __name__ == '__main__':
    test_silent_exit0_module_fails_the_suite()
    test_ok_and_skip_sentinels_pass()
    test_raising_module_still_fails()
    test_a_test_that_dirties_the_repo_fails_the_suite()
    print('ok: run_tests gate checks passed')

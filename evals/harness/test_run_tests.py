"""Self-contained checks for scripts/run_tests.py — the pre-push/CI runner.

The gate under test: a module that exits 0 without printing an `ok:` (or an
explicit `skip:`) sentinel ran zero tests and must FAIL the suite. This is the
vacuous-gate class — a pytest-fixture-only module under bare python collects
nothing, prints nothing, exits 0, and a green suite hides a disconnected
safety net (test_anchor_inject shipped that way for three releases).
"""

from __future__ import annotations

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


if __name__ == '__main__':
    test_silent_exit0_module_fails_the_suite()
    test_ok_and_skip_sentinels_pass()
    test_raising_module_still_fails()
    print('ok: run_tests gate checks passed')

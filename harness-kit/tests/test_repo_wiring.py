#!/usr/bin/env python3
"""Checks that the repository's discovery and lint roots reach `harness-kit/`.

Contract under test:
- `run_tests.discover` finds a `test_*.py` under `harness-kit/` and skips one
  under any `.venv` folder, so a virtual environment's own tests never run;
- `ascii_runtime_lint` and, through it, `subprocess_encoding_lint` scan
  `harness-kit/`.

Each check runs against a fixture tree, never the real repository.

Stdlib-runnable: `python test_repo_wiring.py`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))

import ascii_runtime_lint
import run_tests


def _touch(base: Path, rel: str, text: str = '') -> None:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def test_discover_finds_a_test_under_harness_kit():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _touch(base, 'harness-kit/tests/test_a.py')
        found = [p.relative_to(base).as_posix() for p in run_tests.discover(base)]
    assert found == ['harness-kit/tests/test_a.py'], found


def test_discover_skips_a_test_under_a_venv_folder():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _touch(base, 'harness-kit/tests/test_a.py')
        _touch(base, 'harness-kit/.venv/lib/site-packages/pkg/test_b.py')
        _touch(base, 'plugins/p/.venv/test_c.py')
        _touch(base, 'plugins/p/skills/test_d.py')
        found = [p.relative_to(base).as_posix() for p in run_tests.discover(base)]
    assert found == ['harness-kit/tests/test_a.py', 'plugins/p/skills/test_d.py'], found


def test_ascii_lint_scans_harness_kit():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _touch(base, 'harness-kit/src/harness_kit/mod.py', 'X = 1\n')
        _touch(base, 'harness-kit/src/harness_kit/test_mod.py', 'X = 1\n')
        found = [p.relative_to(base).as_posix() for p in ascii_runtime_lint.iter_target_files(base)]
    assert found == ['harness-kit/src/harness_kit/mod.py'], found


if __name__ == '__main__':
    test_discover_finds_a_test_under_harness_kit()
    test_discover_skips_a_test_under_a_venv_folder()
    test_ascii_lint_scans_harness_kit()
    print('ok: harness-kit wiring')

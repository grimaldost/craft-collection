#!/usr/bin/env python3
"""Checks of the `kit` entry point: version output and module entry.

Stdlib-runnable: `python test_cli.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src'


def _run(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, 'PYTHONPATH': str(SRC)}
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=60,
    )


def test_version_flag_prints_kit_0_1_0():
    proc = _run('--version')
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == 'kit 0.1.0', proc.stdout


def test_package_version_matches():
    sys.path.insert(0, str(SRC))
    import harness_kit

    assert harness_kit.__version__ == '0.1.0'


if __name__ == '__main__':
    test_version_flag_prints_kit_0_1_0()
    test_package_version_matches()
    print('ok: kit entry point')

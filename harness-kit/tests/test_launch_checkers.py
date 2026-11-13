#!/usr/bin/env python3
"""Checks of `kit run` with a version 2 policy, whose checkers the preflight loads.

Contract under test, with a fake harness named through `KIT_HARNESS_ARGV_*`:
- a checker with a syntax error, one that defines no `check`, and one that
  sleeps 10 s while it loads each make `kit run` exit 64 with one stderr line,
  before the canary (no folder under `runs/`) and before any harness process
  (the fake's marker is absent); the slow load is refused within its
  `budget_ms` plus 2 s;
- with a sound checker the harness starts; what it writes to standard output
  and standard error reaches the caller of `kit run`, and so does the
  launcher's own message after the load, while what the checker prints during
  its load does not.

Stdlib-runnable: `python test_launch_checkers.py`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import test_launcher as tl
from kit_fixtures import run_module

PRINTING_HARNESS = Path(__file__).resolve().parent / 'printing_fake_harness.py'
BUDGET_MS = 250
SOUND = (
    'import os\n'
    'print("CHECKER-LOAD-STDOUT")\n'
    'os.write(2, b"CHECKER-LOAD-STDERR\\n")\n'
    'def check(act, observation):\n'
    '    return {"result": "no-match"}\n'
)


def write_v2_policy(case: tl.Case, source: str) -> None:
    """A version 2 policy whose one rule calls a checker holding `source`."""
    checker = case.base / 'checker.py'
    checker.write_bytes(source.encode('utf-8'))
    digest = hashlib.sha256(checker.read_bytes()).hexdigest()
    case.policy.write_text(
        'version = 2\n\n'
        '[launcher]\n'
        f'test_roots = [{json.dumps(str(case.tests))}]\n'
        'forbidden_roots = []\n\n'
        '[[checker]]\n'
        'id = "probe-checker"\n'
        f'file = {json.dumps(checker.as_posix())}\n'
        f'sha256 = "{digest}"\n'
        f'budget_ms = {BUDGET_MS}\n\n'
        '[[rule]]\n'
        'id = "probe-rule"\n'
        'effect = "deny"\n'
        'governed = false\n'
        'kinds = ["shell"]\n'
        'check = "probe-checker"\n'
        'reason = "probe"\n',
        encoding='utf-8',
    )


def no_run_folder(case: tl.Case) -> bool:
    runs = case.state / 'runs'
    return not runs.is_dir() or not any(runs.iterdir())


def refused_by_checker(harness: str, label: str, source: str, needle: str) -> float:
    base = tl.scratch()
    try:
        case = tl.Case(base, harness)
        write_v2_policy(case, source)
        started = time.monotonic()
        proc = case.run()
        elapsed = time.monotonic() - started
        try:
            tl.assert_refused(case, proc, needle)
            assert 'probe-checker' in proc.stderr, proc.stderr
            assert no_run_folder(case), list((case.state / 'runs').iterdir())
        except AssertionError as exc:
            raise AssertionError(f'{harness}: {label}: {exc}') from None
        return elapsed
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_checker_with_a_syntax_error_is_refused_before_the_canary():
    for harness in ('claude-code', 'opencode'):
        refused_by_checker(harness, 'syntax error', 'def check(:\n', 'does not execute')


def test_a_checker_without_check_is_refused_before_the_canary():
    for harness in ('claude-code', 'opencode'):
        refused_by_checker(harness, 'no check', 'VALUE = 1\n', 'check')


def test_a_checker_that_hangs_while_it_loads_is_refused_within_its_budget():
    source = 'import time\ntime.sleep(10)\ndef check(act, observation):\n    return {}\n'
    elapsed = refused_by_checker('opencode', 'slow load', source, 'did not load')
    assert elapsed < BUDGET_MS / 1000 + 2, elapsed


def test_a_sound_checker_lets_the_harness_start_and_its_output_through():
    for harness in ('claude-code', 'opencode'):
        base = tl.scratch()
        try:
            case = tl.Case(base, harness)
            # A version past the pin makes the launcher print once, after the load.
            case.argv = [
                sys.executable,
                str(PRINTING_HARNESS),
                str(case.out),
                '9.9.9',
                '0',
                'guarded',
            ]
            write_v2_policy(case, SOUND)
            proc = case.run()
            child = tl.assert_started(case, proc)
            assert child['args'] == tl.SESSION_ARGS[harness], child['args']
            assert 'SESSION-STDOUT' in proc.stdout, (harness, proc.stdout)
            assert 'SESSION-STDERR' in proc.stderr, (harness, proc.stderr)
            assert 'differs from the pinned' in proc.stderr, (harness, proc.stderr)
            for noise in ('CHECKER-LOAD-STDOUT', 'CHECKER-LOAD-STDERR'):
                assert noise not in proc.stdout + proc.stderr, (harness, noise)
            assert case.run_json()['outcome'] == 'ended', case.run_json()
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'launch with checkers')

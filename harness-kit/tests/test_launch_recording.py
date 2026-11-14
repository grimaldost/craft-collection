#!/usr/bin/env python3
"""Checks of `kit run` with a version 3 policy whose checker records notes.

Contract under test, with a fake harness named through `KIT_HARNESS_ARGV_*`:
- a recording checker that defines no callable `record` makes `kit run` exit
  64 with one stderr line naming it, before the canary (no folder under
  `runs/`) and before any harness process (the fake's marker is absent);
- a recording checker that defines both `check` and `record` lets the harness
  start.

Stdlib-runnable: `python test_launch_recording.py`.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import test_launcher as tl
from kit_fixtures import run_module

CHECK = 'def check(act, observation):\n    return {"result": "no-match"}\n'
RECORDING = CHECK + 'def record(note, facts):\n    return {"result": "unchanged"}\n'


def write_v3_policy(case: tl.Case, source: str) -> None:
    """A version 3 policy whose one rule calls a checker that records outcome notes."""
    checker = case.base / 'series_rule.py'
    checker.write_bytes(source.encode('utf-8'))
    digest = hashlib.sha256(checker.read_bytes()).hexdigest()
    case.policy.write_text(
        'version = 3\n\n'
        '[launcher]\n'
        f'test_roots = [{json.dumps(str(case.tests))}]\n'
        'forbidden_roots = []\n\n'
        '[[checker]]\n'
        'id = "series-check"\n'
        f'file = {json.dumps(checker.as_posix())}\n'
        f'sha256 = "{digest}"\n'
        'budget_ms = 250\n'
        'records = ["outcome"]\n\n'
        '[[rule]]\n'
        'id = "series-rule"\n'
        'effect = "deny"\n'
        'governed = false\n'
        'kinds = ["shell"]\n'
        'check = "series-check"\n'
        'reason = "probe"\n',
        encoding='utf-8',
    )


def test_a_recording_checker_without_record_is_refused_before_the_canary():
    for harness in ('claude-code', 'opencode'):
        base = tl.scratch()
        try:
            case = tl.Case(base, harness)
            write_v3_policy(case, CHECK)
            proc = case.run()
            try:
                tl.assert_refused(case, proc, "checker 'series-check' defines no callable record")
                runs = case.state / 'runs'
                assert not runs.is_dir() or not any(runs.iterdir()), list(runs.iterdir())
            except AssertionError as exc:
                raise AssertionError(f'{harness}: {exc}') from None
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_recording_checker_with_record_lets_the_harness_start():
    for harness in ('claude-code', 'opencode'):
        base = tl.scratch()
        try:
            case = tl.Case(base, harness)
            write_v3_policy(case, RECORDING)
            proc = case.run()
            child = tl.assert_started(case, proc)
            assert child['args'] == tl.SESSION_ARGS[harness], child['args']
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'launch with a recording checker')

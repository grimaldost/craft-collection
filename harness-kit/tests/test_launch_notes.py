#!/usr/bin/env python3
"""Checks of the refusals `kit run` adds for a policy that records notes.

Contract under test, with a fake harness named through `KIT_HARNESS_ARGV_*`:
- for a policy with a recording checker, `kit run` exits 64 before the canary
  (no folder under `runs/`) and before any harness process when the contract
  of the harness gives a recorded kind `state = "absent"` (naming the checker,
  its rules, the kind and the state); when the home has no `note_config.json`
  or one that lacks a recorded kind; when a Claude Code home's `settings.json`
  lacks a note entry for a recorded kind (a result entry's matcher may be
  `Bash|PowerShell` or `*`); and when `SESSION_WORKFLOW_GOVERNED_HOME` lies
  under no test root of the policy, a sibling folder whose name starts with a
  test root's name included;
- a contract with no `[notes]` entry for a recorded kind launches, with one
  line on standard error;
- `SESSION_WORKFLOW_GOVERNED_HOME` under a test root reaches the harness;
  the two switches of the cores never do;
- a policy that records nothing launches as before, whatever the home and the
  variable hold, and its harness does not see the variable.

Stdlib-runnable: `python test_launch_notes.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import test_launcher as tl
from kit_fixtures import SRC, run_module

RECORDING = (
    'def check(act, observation, facts):\n    return {"result": "no-match"}\n'
    'def record(note, facts):\n    return {"result": "unchanged"}\n'
)
GOVERNED = 'SESSION_WORKFLOW_GOVERNED_HOME'
SWITCHES = ('SESSION_WORKFLOW_SERIES_GUARD', 'SESSION_WORKFLOW_OWNER_ACTS_GATE')
CONTRACT_FILES = {'claude-code': 'claude_code.toml', 'opencode': 'opencode.toml'}
HARNESSES = ('claude-code', 'opencode')


def write_recording_policy(case: tl.Case, records: tuple[str, ...]) -> None:
    """A version 3 policy whose one checker records `records`, used by two rules."""
    checker = case.base / 'rec_rule.py'
    checker.write_bytes(RECORDING.encode('utf-8'))
    digest = hashlib.sha256(checker.read_bytes()).hexdigest()
    rules = ''.join(
        '[[rule]]\n'
        f'id = "{rule_id}"\n'
        'effect = "deny"\n'
        'governed = false\n'
        'kinds = ["shell"]\n'
        'check = "rec-check"\n'
        'reason = "probe"\n\n'
        for rule_id in ('rec-rule-one', 'rec-rule-two')
    )
    case.policy.write_text(
        'version = 3\n\n'
        '[launcher]\n'
        f'test_roots = [{json.dumps(str(case.tests))}]\n'
        'forbidden_roots = []\n\n'
        '[[checker]]\n'
        'id = "rec-check"\n'
        f'file = {json.dumps(checker.as_posix())}\n'
        f'sha256 = "{digest}"\n'
        'budget_ms = 250\n'
        f'records = {json.dumps(list(records))}\n\n' + rules,
        encoding='utf-8',
    )


def render_with_policy(case: tl.Case) -> Path:
    """A home rendered with `--policy`, which becomes the case's home."""
    home = case.base / f'home-notes-{case.harness}'
    proc = tl.kit(
        case,
        'home',
        'render',
        '--harness',
        case.harness,
        '--dir',
        str(home),
        '--endpoint',
        tl.ENDPOINT,
        '--policy',
        str(case.policy),
    )
    assert proc.returncode == 0, proc.stderr
    case.home = home
    return home


def recording_case(
    harness: str, records: tuple[str, ...] = ('prompt', 'outcome'), render: bool = True
) -> tuple[Path, tl.Case]:
    base = tl.scratch()
    case = tl.Case(base, harness)
    write_recording_policy(case, records)
    if render:
        render_with_policy(case)
    return base, case


def package_copy(base: Path, harness: str, notes: str | None) -> Path:
    """A copy of the package whose contract for `harness` has `notes` in place of its `[notes]`."""
    copy = base / 'pkg'
    shutil.copytree(SRC, copy, ignore=shutil.ignore_patterns('__pycache__'))
    path = copy / 'harness_kit' / 'contracts' / CONTRACT_FILES[harness]
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'(?ms)^\[notes\.[a-z]+\]\n.*?(?=^\[|\Z)', '', text)
    path.write_text(text.rstrip('\n') + '\n' + (notes or ''), encoding='utf-8')
    return copy


def assert_no_canary(case: tl.Case) -> None:
    runs = case.state / 'runs'
    assert not runs.is_dir() or not any(runs.iterdir()), list(runs.iterdir())


def refused(case: tl.Case, needle: str, **env: str) -> None:
    proc = case.run(**env)
    tl.assert_refused(case, proc, needle)
    assert_no_canary(case)


# ---- the contract's [notes]


def test_an_absent_kind_in_the_contract_is_refused():
    for harness in HARNESSES:
        base, case = recording_case(harness, ('outcome',))
        try:
            notes = '\n[notes.outcome]\nstate = "absent"\nmark = "measured"\nevidence = "x"\n'
            copy = package_copy(base, harness, notes)
            proc = case.run(PYTHONPATH=str(copy))
            tl.assert_refused(case, proc, 'rec-check')
            line = proc.stderr.strip()
            for word in ('rec-rule-one', 'rec-rule-two', 'outcome', 'absent'):
                assert word in line, (harness, word, line)
            assert_no_canary(case)
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_contract_without_the_entry_launches_with_one_line_on_stderr():
    for harness in HARNESSES:
        base, case = recording_case(harness, ('prompt',))
        try:
            copy = package_copy(base, harness, None)
            proc = case.run(PYTHONPATH=str(copy))
            tl.assert_started(case, proc)
            lines = proc.stderr.splitlines()
            assert len(lines) == 1, (harness, lines)
            assert 'prompt' in lines[0] and 'contract' in lines[0], (harness, lines)
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_tested_kind_launches_with_nothing_on_stderr():
    for harness in HARNESSES:
        base, case = recording_case(harness)
        try:
            notes = ''.join(
                f'\n[notes.{kind}]\nstate = "tested"\nmark = "measured"\nevidence = "x"\n'
                for kind in ('prompt', 'outcome')
            )
            copy = package_copy(base, harness, notes)
            proc = case.run(PYTHONPATH=str(copy))
            tl.assert_started(case, proc)
            assert proc.stderr == '', (harness, proc.stderr)
        finally:
            shutil.rmtree(base, ignore_errors=True)


# ---- the rendered home


def test_a_home_rendered_without_the_policy_is_refused():
    for harness in HARNESSES:
        base, case = recording_case(harness, render=False)
        try:
            refused(case, 'kit home render --policy')
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_note_config_without_a_recorded_kind_is_refused():
    for harness in HARNESSES:
        base, case = recording_case(harness)
        try:
            home = json.loads((case.home / 'home.json').read_text(encoding='utf-8'))
            path = Path(home['shell_config']).parent / 'note_config.json'
            config = json.loads(path.read_text(encoding='utf-8'))
            config['records'] = ['prompt']
            path.write_text(json.dumps(config), encoding='utf-8')
            refused(case, 'kit home render --policy')
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_malformed_note_config_is_refused():
    for harness in HARNESSES:
        base, case = recording_case(harness)
        try:
            home = json.loads((case.home / 'home.json').read_text(encoding='utf-8'))
            path = Path(home['shell_config']).parent / 'note_config.json'
            path.write_text('{"kit_note_config": 1', encoding='utf-8')
            refused(case, 'kit home render --policy')
        finally:
            shutil.rmtree(base, ignore_errors=True)


def _edit_settings(case: tl.Case, edit) -> None:
    home = json.loads((case.home / 'home.json').read_text(encoding='utf-8'))
    path = Path(home['config_file'])
    settings = json.loads(path.read_text(encoding='utf-8'))
    edit(settings['hooks'])
    path.write_text(json.dumps(settings, indent=2), encoding='utf-8')


def test_a_claude_code_home_without_a_note_entry_is_refused():
    for event in ('PostToolUseFailure', 'PostToolUse', 'UserPromptSubmit'):
        base, case = recording_case('claude-code')
        try:
            _edit_settings(case, lambda hooks, e=event: hooks.pop(e))
            refused(case, 'kit home render --policy')
        except AssertionError as exc:
            raise AssertionError(f'{event}: {exc}') from None
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_claude_code_result_entry_with_another_matcher_is_refused():
    base, case = recording_case('claude-code', ('outcome',))
    try:

        def edit(hooks: dict) -> None:
            hooks['PostToolUse'][0]['matcher'] = 'Write'

        _edit_settings(case, edit)
        refused(case, 'kit home render --policy')
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_claude_code_result_entry_matching_every_tool_is_not_refused():
    base, case = recording_case('claude-code', ('outcome',))
    try:

        def edit(hooks: dict) -> None:
            for name in ('PostToolUse', 'PostToolUseFailure'):
                hooks[name][0]['matcher'] = '*'

        _edit_settings(case, edit)
        tl.assert_started(case, case.run())
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- the governed-home override


def test_a_governed_home_outside_the_test_roots_is_refused():
    for harness in HARNESSES:
        base, case = recording_case(harness)
        try:
            outside = base / 'elsewhere' / 'governed-home'
            sibling = Path(str(case.tests) + '-sibling') / 'governed-home'
            for value in (outside, sibling):
                refused(case, GOVERNED, **{GOVERNED: str(value)})
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_governed_home_under_a_test_root_reaches_the_harness_and_no_switch_does():
    for harness in HARNESSES:
        base, case = recording_case(harness)
        try:
            governed = case.tests / 'work' / 'governed-home'
            env = {GOVERNED: str(governed), SWITCHES[0]: 'off', SWITCHES[1]: 'off'}
            child = tl.assert_started(case, case.run(**env))
            upper = {k.upper(): v for k, v in child['env'].items()}
            assert upper.get(GOVERNED) == str(governed), (harness, upper.get(GOVERNED))
            for name in SWITCHES:
                assert name not in upper, (harness, name)
        finally:
            shutil.rmtree(base, ignore_errors=True)


def test_a_policy_that_records_nothing_launches_as_before():
    for harness in HARNESSES:
        base = tl.scratch()
        try:
            case = tl.Case(base, harness)
            outside = base / 'elsewhere' / 'governed-home'
            child = tl.assert_started(case, case.run(**{GOVERNED: str(outside)}))
            upper = {k.upper() for k in child['env']}
            assert GOVERNED not in upper, harness
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'kit run refusals for a recording policy')

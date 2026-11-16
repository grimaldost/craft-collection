#!/usr/bin/env python3
"""Checks of the note configuration of a rendered home (`kit home render --policy`).

Contract under test:
- `kit home render --policy FILE` loads the policy; an unreadable one exits 64
  and writes nothing;
- the recorded kinds are the union of the checkers' `records`, in the order
  `prompt`, `outcome`; when there is any, both drivers write
  `note_config.json` beside `shell_config.json`, holding exactly
  `kit_note_config` 1, `note_argv` (`cli_argv` with `note` in place of its last
  element), `timeout_s` (the shell timeout) and `records`;
- without `--policy`, or with a policy that records nothing, the render writes
  the same `home.json`, `shell_config.json` and harness configuration as
  before, and no `note_config.json`;

Stdlib-runnable: `python test_home_notes.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import harnesses
from kit_fixtures import SAMPLE_POLICY, SRC, run_module

ENDPOINT = 'http://127.0.0.1:43210'
HARNESSES = ('claude-code', 'opencode')
CHECK = 'def check(act, observation):\n    return {"result": "no-match"}\n'
RECORDING = CHECK + 'def record(note, facts):\n    return {"result": "unchanged"}\n'
NOTE_KEYS = ['kit_note_config', 'note_argv', 'timeout_s', 'records']


def _kit(*args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=60,
    )


def _render(harness: str, folder: Path, *extra: str) -> subprocess.CompletedProcess:
    return _kit(
        'home', 'render', '--harness', harness, '--dir', str(folder), '--endpoint', ENDPOINT, *extra
    )


def _policy(folder: Path, *records: str | None, name: str = 'policy.toml') -> Path:
    """A version 3 policy with one checker per entry of `records` (None: no `records` key)."""
    file = folder / 'rule.py'
    file.write_bytes(RECORDING.encode('utf-8'))
    sha = hashlib.sha256(file.read_bytes()).hexdigest()
    text = 'version = 3\n\n'
    for n, kinds in enumerate(records):
        text += (
            f'[[checker]]\nid = "c{n}"\nfile = "{file.as_posix()}"\nsha256 = "{sha}"\n'
            + ('' if kinds is None else f'records = {kinds}\n')
            + '\n'
        )
    path = folder / name
    path.write_text(text, encoding='utf-8')
    return path


def _note_config(home: dict) -> Path:
    return Path(home['shell_config']).parent / 'note_config.json'


def _assert_note_config(home: dict, records: list[str]) -> None:
    path = _note_config(home)
    data = json.loads(path.read_text(encoding='utf-8'))
    assert list(data) == NOTE_KEYS, data
    shell = json.loads(Path(home['shell_config']).read_text(encoding='utf-8'))
    assert data['kit_note_config'] == 1, data
    assert data['note_argv'] == [*shell['cli_argv'][:-1], 'note'], data
    assert shell['cli_argv'][-1] == 'judge', shell
    assert data['timeout_s'] == harnesses.SHELL_TIMEOUT_S == shell['timeout_s'], data
    assert data['records'] == records, data


def test_a_recording_policy_writes_note_config_for_each_harness():
    cases = (
        (('["outcome"]', None, '["prompt"]'), ['prompt', 'outcome']),
        (('["outcome", "prompt"]',), ['prompt', 'outcome']),
        (('["prompt"]',), ['prompt']),
        ((None, '["outcome"]'), ['outcome']),
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for n, (records, expected) in enumerate(cases):
            policy = _policy(root, *records, name=f'p{n}.toml')
            for harness in HARNESSES:
                folder = root / f'home-{harness}-{n}'
                proc = _render(harness, folder, '--policy', str(policy))
                assert proc.returncode == 0, (harness, records, proc.stderr)
                home = json.loads(proc.stdout)
                _assert_note_config(home, expected)


def test_an_unreadable_policy_exits_64_and_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        junk = root / 'junk.toml'
        junk.write_text('version = 4\n', encoding='utf-8')
        for harness in HARNESSES:
            for policy in (junk, root / 'missing.toml'):
                folder = root / f'home-{harness}'
                proc = _render(harness, folder, '--policy', str(policy))
                assert proc.returncode == 64, (harness, proc.returncode, proc.stderr)
                assert proc.stdout == '', proc.stdout
                assert not folder.exists(), sorted(folder.rglob('*'))


def _bytes_of(home: dict) -> dict[str, bytes]:
    return {
        'home.json': (Path(home['dir']) / 'home.json').read_bytes(),
        'shell_config.json': Path(home['shell_config']).read_bytes(),
        'config': Path(home['config_file']).read_bytes(),
    }


def test_no_policy_or_one_that_records_nothing_renders_the_same_home():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        quiet = _policy(root, None, name='quiet.toml')
        v1 = root / 'v1.toml'
        v1.write_text(SAMPLE_POLICY, encoding='utf-8')
        folder = root / 'home'
        for harness in HARNESSES:
            seen = []
            for extra in ((), ('--policy', str(quiet)), ('--policy', str(v1))):
                shutil.rmtree(folder, ignore_errors=True)
                proc = _render(harness, folder, *extra)
                assert proc.returncode == 0, (harness, extra, proc.stderr)
                home = json.loads(proc.stdout)
                assert not _note_config(home).exists(), (harness, extra)
                assert not list(folder.rglob('note_config.json')), (harness, extra)
                seen.append(_bytes_of(home))
            assert seen[0] == seen[1] == seen[2], harness


def test_a_policy_recording_prompt_and_outcome_registers_the_four_claude_code_hooks():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        policy = _policy(root, '["prompt", "outcome"]')
        folder = root / 'cc'
        assert _render('claude-code', folder, '--policy', str(policy)).returncode == 0
        settings = json.loads((folder / 'claude-config' / 'settings.json').read_text('utf-8'))
        assert list(settings['hooks']) == [
            'PreToolUse',
            'UserPromptSubmit',
            'PostToolUse',
            'PostToolUseFailure',
        ], settings


def test_render_home_keeps_two_arguments_and_takes_records():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for harness in HARNESSES:
            driver = harnesses.get(harness)
            home = driver.render_home(root / f'{harness}-plain', ENDPOINT)
            assert not _note_config(home).exists()
            home = driver.render_home(root / f'{harness}-notes', ENDPOINT, ('prompt', 'outcome'))
            _assert_note_config(home, ['prompt', 'outcome'])


if __name__ == '__main__':
    run_module(globals(), 'note configuration of a home')

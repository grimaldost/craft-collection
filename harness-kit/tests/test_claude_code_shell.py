#!/usr/bin/env python3
"""Checks of the Claude Code shell, `shells/claude_code/kit_hook.py`.

Contract under test:
- the shell reads the raw PreToolUse payload on stdin, builds one neutral event
  and runs `cli_argv` of the `shell_config.json` beside it with the event on
  stdin; shell tools, write tools and any other tool map to the exact event,
  and no payload key leaks into it;
- effect allow prints nothing and exits 0; effect deny prints the
  hookSpecificOutput deny, ASCII-escaped, and exits 0;
- an unreadable payload, a missing or malformed config, a CLI that does not
  start, exits non-zero, prints nothing or prints something that is not a
  verdict each print a deny whose reason starts `kit could not judge:`;
- a hung CLI is ended with its whole tree at the deadline: the shell returns
  within 4.5 seconds and the grandchild's late marker never appears, with
  System32 off PATH and with KIT_SHELL_NO_JOB=1 too; on Windows an orphaned
  grandchild is ended by the Job Object and survives under the seam;
- the file imports neither harness_kit nor tomllib, calls TerminateJobObject,
  uses no shell=True, names taskkill only by absolute path and stays within
  160 non-blank lines;
- with the real CLI and the sample policy, a governed command is denied with
  the rule's reason.

Stdlib-runnable: `python test_claude_code_shell.py`.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.event import check_event
from kit_fixtures import SRC, run_module

HOOK = SRC / 'harness_kit' / 'shells' / 'claude_code' / 'kit_hook.py'
STANDIN = Path(__file__).resolve().parent / 'shell_standin.py'
PREFIX = 'kit could not judge:'
CWD = os.path.abspath(os.sep + 'w')
WINDOWS = os.name == 'nt'


def _payload(tool: str, tool_input: dict, **extra: object) -> bytes:
    body = {
        'session_id': 'sess-1',
        'transcript_path': os.path.join(CWD, 't.jsonl'),
        'cwd': CWD,
        'permission_mode': 'default',
        'hook_event_name': 'PreToolUse',
        'tool_name': tool,
        'tool_input': tool_input,
        'tool_use_id': 'toolu_1',
        'prompt_id': 'p1',
        'effort': 'high',
    }
    body.update(extra)
    return json.dumps(body).encode('utf-8')


def _config(argv: list[str], timeout_s: float = 3) -> dict:
    return {
        'kit_shell_config': 1,
        'cli_argv': argv,
        'timeout_s': timeout_s,
        'harness_version': '2.1.316',
    }


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONPATH', None)
    env.update(extra)
    return env


def _install(td: Path, config: dict | str | None) -> Path:
    folder = td / 'kit-shell'
    folder.mkdir()
    hook = folder / 'kit_hook.py'
    shutil.copyfile(HOOK, hook)
    if isinstance(config, dict):
        (folder / 'shell_config.json').write_text(json.dumps(config), encoding='utf-8')
    elif isinstance(config, str):
        (folder / 'shell_config.json').write_text(config, encoding='utf-8')
    return hook


def _run(
    hook: Path, payload: bytes, env: dict | None = None
) -> tuple[subprocess.CompletedProcess, float]:
    start = time.monotonic()
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-I', str(hook)],
        input=payload,
        capture_output=True,
        env=env or _env(),
        timeout=30,
    )
    return proc, time.monotonic() - start


def _standin(td: Path, mode: str, *args: str) -> tuple[list[str], Path]:
    capture = td / 'captured.json'
    return [sys.executable, '-I', str(STANDIN), str(capture), mode, *args], capture


def _deny_reason(proc: subprocess.CompletedProcess) -> str:
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    out = json.loads(proc.stdout.decode('ascii'))
    assert list(out) == ['hookSpecificOutput'], out
    spec = out['hookSpecificOutput']
    assert list(spec) == ['hookEventName', 'permissionDecision', 'permissionDecisionReason'], spec
    assert spec['hookEventName'] == 'PreToolUse', spec
    assert spec['permissionDecision'] == 'deny', spec
    return spec['permissionDecisionReason']


def _event_for(payload: bytes, act: dict, observation: dict, run_id: str | None = None) -> dict:
    return {
        'kit_event': 1,
        'run_id': run_id,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': 'sess-1', 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': {
            'session': 'observed',
            'parent': 'unavailable',
            'root': 'unavailable',
            'origin': 'unavailable',
            **observation,
        },
        'act': {
            **act,
            'argv': None,
            'cwd': CWD,
            'payload_sha256': hashlib.sha256(payload).hexdigest(),
        },
    }


def _captured(tool: str, tool_input: dict, **env: str) -> tuple[dict, bytes]:
    payload = _payload(tool, tool_input)
    with tempfile.TemporaryDirectory() as td:
        argv, capture = _standin(Path(td), 'allow')
        hook = _install(Path(td), _config(argv))
        proc, _ = _run(hook, payload, _env(**env))
        assert proc.returncode == 0 and proc.stdout == b'', (proc.stdout, proc.stderr)
        sent = capture.read_bytes()
    return json.loads(sent), payload


SHELL_OBS = {'command': 'observed', 'paths': 'not_applicable'}
WRITE_OBS = {'command': 'not_applicable', 'paths': 'observed'}
OTHER_OBS = {'command': 'not_applicable', 'paths': 'not_applicable'}


def test_bash_maps_to_a_shell_event():
    sent, payload = _captured('Bash', {'command': 'echo hi', 'description': 'say hi'})
    act = {'kind': 'shell', 'command': 'echo hi', 'paths': []}
    assert sent == _event_for(payload, act, SHELL_OBS), sent
    check_event(sent)


def test_powershell_maps_to_a_shell_event_with_the_run_id():
    run_id = '20261109T120000Z-0123456789ab'
    sent, payload = _captured('PowerShell', {'command': 'Get-Item x'}, KIT_RUN_ID=run_id)
    act = {'kind': 'shell', 'command': 'Get-Item x', 'paths': []}
    assert sent == _event_for(payload, act, SHELL_OBS, run_id), sent


def test_write_tools_map_to_a_file_write_joined_to_cwd():
    for tool, key in (
        ('Write', 'file_path'),
        ('Edit', 'file_path'),
        ('MultiEdit', 'file_path'),
        ('NotebookEdit', 'notebook_path'),
    ):
        sent, payload = _captured(tool, {key: 'sub/../conf/settings.json', 'content': 'x'})
        path = os.path.normpath(os.path.join(CWD, 'conf', 'settings.json'))
        act = {'kind': 'file_write', 'command': None, 'paths': [path]}
        assert sent == _event_for(payload, act, WRITE_OBS), (tool, sent)
        check_event(sent)


def test_other_tools_map_to_kind_other():
    sent, payload = _captured('Read', {'file_path': 'a.txt'})
    act = {'kind': 'other', 'command': None, 'paths': []}
    assert sent == _event_for(payload, act, OTHER_OBS), sent
    check_event(sent)


def test_no_payload_key_leaks_into_the_event():
    sent, _ = _captured('Bash', {'command': 'echo hi'})
    text = json.dumps(sent)
    for key in ('hook_event_name', 'tool_input', 'tool_name', 'tool_use_id', 'transcript_path'):
        assert key not in text, key


def test_allow_prints_nothing_and_deny_prints_the_exact_json():
    with tempfile.TemporaryDirectory() as td:
        argv, _ = _standin(Path(td), 'deny', 'no é here')
        hook = _install(Path(td), _config(argv))
        proc, _ = _run(hook, _payload('Bash', {'command': 'x'}))
        expected = {
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': 'no é here',
            }
        }
        proc.stdout.decode('ascii')
        assert json.loads(proc.stdout) == expected, proc.stdout
        assert _deny_reason(proc) == 'no é here'


def _assert_could_not_judge(config: dict | str | None, payload: bytes | None = None) -> None:
    with tempfile.TemporaryDirectory() as td:
        hook = _install(Path(td), config)
        proc, _ = _run(hook, payload if payload is not None else _payload('Bash', {'command': 'x'}))
        reason = _deny_reason(proc)
        assert reason.startswith(PREFIX), (config, reason)


def test_each_failure_class_denies():
    with tempfile.TemporaryDirectory() as td:
        capture = str(Path(td) / 'c.json')
        cli = [sys.executable, '-I', str(STANDIN), capture]
        _assert_could_not_judge(_config([*cli, 'allow']), b'not json')
        _assert_could_not_judge(_config([*cli, 'allow']), b'[1, 2]')
        _assert_could_not_judge(
            _config([*cli, 'allow']), json.dumps({'tool_name': 'Bash'}).encode()
        )
        _assert_could_not_judge(None)
        _assert_could_not_judge('{not json')
        _assert_could_not_judge({'kit_shell_config': 1})
        _assert_could_not_judge({**_config([*cli, 'allow']), 'kit_shell_config': 2})
        _assert_could_not_judge(_config([]))
        _assert_could_not_judge(_config([str(Path(td) / 'no-such-cli.exe')]))
        for mode in ('exit3', 'silent', 'garbage', 'notverdict'):
            _assert_could_not_judge(_config([*cli, mode]))


def _hung_case(mode: str, extra_env: dict, late_expected: bool) -> str | None:
    with tempfile.TemporaryDirectory() as td:
        late = Path(td) / 'late.marker'
        argv, _ = _standin(Path(td), mode, str(late))
        hook = _install(Path(td), _config(argv))
        start = time.monotonic()
        proc, elapsed = _run(hook, _payload('Bash', {'command': 'x'}), _env(**extra_env))
        try:
            reason = _deny_reason(proc)
        except AssertionError as exc:
            return f'{mode} {extra_env}: {exc}'
        if not reason.startswith(PREFIX):
            return f'{mode} {extra_env}: reason {reason!r}'
        if elapsed >= 4.5:
            return f'{mode} {extra_env}: returned after {elapsed:.2f} s'
        time.sleep(max(0.0, start + 9 - time.monotonic()))
        if late.exists() != late_expected:
            return f'{mode} {extra_env}: late marker present={late.exists()}'
    return None


def test_a_hung_cli_is_ended_with_its_tree():
    no_system32 = os.pathsep.join(
        p for p in os.environ.get('PATH', '').split(os.pathsep) if 'system32' not in p.lower()
    )
    cases = [
        ('hang', {}, False),
        ('hang', {'PATH': no_system32}, False),
        ('hang', {'KIT_SHELL_NO_JOB': '1'}, False),
    ]
    if WINDOWS:
        cases += [('orphan', {}, False), ('orphan', {'KIT_SHELL_NO_JOB': '1'}, True)]
    with ThreadPoolExecutor(len(cases)) as pool:
        errors = [e for e in pool.map(lambda c: _hung_case(*c), cases) if e]
    assert not errors, errors


def test_the_file_holds_the_shell_rules():
    text = HOOK.read_text(encoding='utf-8')
    tree = ast.parse(text)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or '').split('.')[0])
    assert 'harness_kit' not in imported and 'tomllib' not in imported, imported
    callees = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            callees.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None))
            for kw in node.keywords:
                is_true = isinstance(kw.value, ast.Constant) and kw.value.value is True
                assert not (kw.arg == 'shell' and is_true), 'shell=True'
    assert 'TerminateJobObject' in callees, callees
    for line in text.splitlines():
        if 'taskkill' in line.lower():
            assert 'taskkill.exe' in line and 'System32' in line, line
    assert sum(1 for line in text.splitlines() if line.strip()) <= 160


SHELL_POLICY = """version = 1

[launcher]
test_roots = []
forbidden_roots = []

[[rule]]
id = "no-config-write"
effect = "deny"
governed = true
kinds = ["shell", "file_write"]
command_regex = 'settings\\.json'
path_glob = ["**/settings.json"]
reason = "configuration writes are governed"
"""


def test_the_real_cli_denies_a_governed_command():
    bootstrap = (
        'import sys; sys.path.insert(0, sys.argv[1]); del sys.argv[1]; '
        'from harness_kit.cli import main; sys.exit(main())'
    )
    with tempfile.TemporaryDirectory() as td:
        policy = Path(td) / 'policy.toml'
        policy.write_bytes(SHELL_POLICY.encode('utf-8'))
        argv = [sys.executable, '-I', '-c', bootstrap, str(SRC), 'judge']
        hook = _install(Path(td), _config(argv))
        env = _env(KIT_POLICY=str(policy), KIT_STATE_ROOT=str(Path(td) / 'state'))
        proc, _ = _run(hook, _payload('Bash', {'command': 'cat settings.json'}), env)
        reason = _deny_reason(proc)
        assert reason == 'configuration writes are governed', reason
        proc, _ = _run(hook, _payload('Write', {'file_path': 'conf/settings.json'}), env)
        reason = _deny_reason(proc)
        assert reason == 'configuration writes are governed', reason
        proc, _ = _run(hook, _payload('Bash', {'command': 'echo hi'}), env)
        assert proc.returncode == 0 and proc.stdout == b'', (proc.stdout, proc.stderr)


if __name__ == '__main__':
    run_module(globals(), 'claude code shell')

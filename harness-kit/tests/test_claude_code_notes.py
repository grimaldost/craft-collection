#!/usr/bin/env python3
"""Checks of the Claude Code shell's note mode (`kit_hook.py --note`) and its registration.

Contract under test:
- run with `--note`, the shell reads `note_config.json` and `shell_config.json`
  beside it and the raw payload on stdin, and sends one note to `note_argv`:
  a prompt note for UserPromptSubmit, an outcome note for PostToolUse and
  PostToolUseFailure on Bash or PowerShell, each valid under the note
  contract, with the act built as the judgement event's act;
- a prompt keeps its first 20000 code points and an output its last 65536,
  `truncated` true when cut; a `backgroundTaskId` gives `background`, a null
  output and `truncated` false; PostToolUseFailure gives `failed` and a null
  output;
- any other event or tool, a kind not in `records`, a payload without a
  string `session_id`, or a missing or malformed config sends nothing;
- whatever the CLI does (exits 1, prints garbage, is missing, hangs with a
  grandchild), the mode prints nothing, exits 0 and returns within 4.5 s, and
  the hung tree is ended;
- `render_home` with records adds UserPromptSubmit, PostToolUse and
  PostToolUseFailure entries after the PreToolUse entry, which stays first and
  unchanged; no note entry has `onFailure`; the result entries' matcher is
  `Bash|PowerShell` or `*`.

Stdlib-runnable: `python test_claude_code_notes.py`.
"""

from __future__ import annotations

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

from harness_kit import harnesses
from harness_kit.notes import check_note
from kit_fixtures import SRC, run_module

HOOK = SRC / 'harness_kit' / 'shells' / 'claude_code' / 'kit_hook.py'
STANDIN = Path(__file__).resolve().parent / 'shell_standin.py'
CWD = os.path.abspath(os.sep + 'w')
WINDOWS = os.name == 'nt'
SESSION = '00000000-0000-4000-8000-000000000001'
URL = 'https://github.com/example/repo/pull/1'
ENDPOINT = 'http://127.0.0.1:43210'
RESULT_MATCHERS = ('Bash|PowerShell', '*')


def _common(event: str) -> dict:
    return {
        'session_id': SESSION,
        'transcript_path': os.path.join(CWD, 't.jsonl'),
        'cwd': CWD,
        'prompt_id': 'p1',
        'permission_mode': 'default',
        'hook_event_name': event,
    }


def _prompt_payload(text: str) -> bytes:
    return json.dumps({**_common('UserPromptSubmit'), 'prompt': text}).encode('utf-8')


def _post_payload(tool: str, command: str, response: dict | None, **extra: object) -> bytes:
    event = 'PostToolUse' if response is not None else 'PostToolUseFailure'
    body = {**_common(event), 'effort': 'high', 'tool_name': tool}
    body['tool_input'] = {'command': command, 'description': 'run it'}
    if response is not None:
        body['tool_response'] = response
    else:
        body.update(error='Exit code 3\nout\nerr', is_interrupt=False)
    body.update(tool_use_id='toolu_1', duration_ms=12, **extra)
    return json.dumps(body).encode('utf-8')


def _bash_response(stdout: str, **extra: object) -> dict:
    return {
        'stdout': stdout,
        'stderr': '',
        'interrupted': False,
        'isImage': False,
        'noOutputExpected': False,
        **extra,
    }


def _shell_config() -> dict:
    return {
        'kit_shell_config': 1,
        'cli_argv': [sys.executable, '-c', 'raise SystemExit(9)', 'judge'],
        'timeout_s': 3,
        'harness_version': '2.1.316',
    }


def _note_config(argv: list[str], records: list[str], timeout_s: float = 3) -> dict:
    return {'kit_note_config': 1, 'note_argv': argv, 'timeout_s': timeout_s, 'records': records}


def _install(td: Path, note_config: dict | str | None, shell_config: dict | str | None) -> Path:
    folder = td / 'kit-shell'
    folder.mkdir()
    hook = folder / 'kit_hook.py'
    shutil.copyfile(HOOK, hook)
    for name, value in (('note_config.json', note_config), ('shell_config.json', shell_config)):
        if value is not None:
            text = value if isinstance(value, str) else json.dumps(value)
            (folder / name).write_text(text, encoding='utf-8')
    return hook


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONPATH', None)
    env.update(extra)
    return env


def _run(
    hook: Path, payload: bytes, env: dict | None = None
) -> tuple[subprocess.CompletedProcess, float]:
    start = time.monotonic()
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-I', str(hook), '--note'],
        input=payload,
        capture_output=True,
        env=env or _env(),
        timeout=30,
    )
    return proc, time.monotonic() - start


def _assert_silent(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    assert proc.stdout == b'', proc.stdout


def _sent(
    payload: bytes,
    records: tuple[str, ...] = ('prompt', 'outcome'),
    note_config: dict | str | None = None,
    shell_config: dict | str | None = None,
    **env: str,
) -> dict | None:
    """The note the stand-in CLI received, or None when nothing was sent."""
    with tempfile.TemporaryDirectory() as td:
        capture = Path(td) / 'captured.json'
        argv = [sys.executable, '-I', str(STANDIN), str(capture), 'allow']
        if note_config is None:
            note_config = _note_config(argv, list(records))
        if shell_config is None:
            shell_config = _shell_config()
        hook = _install(Path(td), note_config, shell_config)
        proc, _ = _run(hook, payload, _env(**env))
        _assert_silent(proc)
        if not capture.exists():
            return None
        data = capture.read_bytes()
    data.decode('ascii')
    return json.loads(data)


def _head(run_id: str | None = None, command: str = 'not_applicable') -> dict:
    return {
        'kit_note': 1,
        'run_id': run_id,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': SESSION, 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': {
            'session': 'observed',
            'parent': 'unavailable',
            'root': 'unavailable',
            'origin': 'unavailable',
            'command': command,
            'paths': 'not_applicable',
        },
    }


def _outcome(
    payload: bytes, command: str, status: str, output: str | None, truncated: bool
) -> dict:
    act = {'kind': 'shell', 'command': command, 'argv': None, 'paths': [], 'cwd': CWD}
    act['payload_sha256'] = hashlib.sha256(payload).hexdigest()
    body = {'kind': 'outcome', 'act': act, 'status': status, 'output': output}
    return {**_head(command='observed'), 'note': {**body, 'truncated': truncated}}


def test_a_submitted_prompt_sends_the_exact_prompt_note():
    run_id = '20260101T000000Z-0123456789ab'
    text = 'Run the tool call. é'
    sent = _sent(_prompt_payload(text), KIT_RUN_ID=run_id)
    body = {'kind': 'prompt', 'text': text, 'truncated': False}
    assert sent == {**_head(run_id), 'note': body}, sent
    check_note(sent)


def test_a_long_prompt_keeps_its_first_20000_code_points():
    text = '\U0001f600' + 'p' * 19999 + 'z'
    sent = _sent(_prompt_payload(text))
    assert sent['note'] == {'kind': 'prompt', 'text': text[:20000], 'truncated': True}, sent['note']
    check_note(sent)


def test_a_bash_result_sends_the_exact_outcome_note():
    command = 'gh pr create -R example/repo --title t --body b'
    payload = _post_payload('Bash', command, _bash_response(URL))
    sent = _sent(payload)
    assert sent == _outcome(payload, command, 'completed', URL, False), sent
    check_note(sent)


def test_a_powershell_result_sends_the_exact_outcome_note():
    response = {'stdout': 'probe-ps', 'stderr': '', 'interrupted': False, 'isImage': False}
    payload = _post_payload('PowerShell', 'Write-Output probe-ps', response)
    sent = _sent(payload)
    assert sent == _outcome(payload, 'Write-Output probe-ps', 'completed', 'probe-ps', False), sent
    check_note(sent)


def test_a_failed_call_sends_status_failed_and_no_output():
    payload = _post_payload('Bash', 'exit 3', None)
    sent = _sent(payload)
    assert sent == _outcome(payload, 'exit 3', 'failed', None, False), sent
    check_note(sent)


def test_a_subagent_result_keeps_the_parent_session():
    payload = _post_payload(
        'Bash', 'echo sub', _bash_response('sub'), agent_id='agent-1', agent_type='helper'
    )
    sent = _sent(payload)
    assert sent == _outcome(payload, 'echo sub', 'completed', 'sub', False), sent
    assert 'agent_id' not in json.dumps(sent)


def test_a_long_output_keeps_its_last_65536_code_points():
    stdout = 'a' * (70000 - len(URL)) + URL
    payload = _post_payload('Bash', 'gh pr create', _bash_response(stdout))
    sent = _sent(payload)
    assert sent == _outcome(payload, 'gh pr create', 'completed', stdout[-65536:], True), sent
    assert len(sent['note']['output']) == 65536
    check_note(sent)


def test_a_background_call_sends_background_with_no_output():
    for stdout in ('', URL):
        payload = _post_payload('Bash', 'sleep 9', _bash_response(stdout, backgroundTaskId='bg1'))
        sent = _sent(payload)
        assert sent == _outcome(payload, 'sleep 9', 'background', None, False), (stdout, sent)
        check_note(sent)


def test_an_empty_background_id_is_completed():
    payload = _post_payload('Bash', 'echo x', _bash_response('x', backgroundTaskId=''))
    assert _sent(payload) == _outcome(payload, 'echo x', 'completed', 'x', False)


def test_other_events_tools_and_bad_payloads_send_nothing():
    write = json.loads(_post_payload('Bash', 'x', _bash_response('')))
    write.update(tool_name='Write', tool_input={'file_path': 'a.txt', 'content': 'x'})
    pre = json.loads(_post_payload('Bash', 'x', _bash_response('')))
    pre['hook_event_name'] = 'PreToolUse'
    del pre['tool_response']
    no_session = json.loads(_prompt_payload('hi'))
    del no_session['session_id']
    numeric_session = {**json.loads(_prompt_payload('hi')), 'session_id': 7}
    no_event = json.loads(_prompt_payload('hi'))
    del no_event['hook_event_name']
    stop = {**_common('Stop'), 'stop_hook_active': False}
    cases = [write, pre, no_session, numeric_session, no_event, stop, [1, 2], 'x']
    for case in cases:
        assert _sent(json.dumps(case).encode('utf-8')) is None, case
    assert _sent(b'not json') is None
    assert _sent(b'\xff\xfe') is None
    prompt_not_text = {**json.loads(_prompt_payload('hi')), 'prompt': None}
    assert _sent(json.dumps(prompt_not_text).encode('utf-8')) is None


def test_a_kind_not_in_records_sends_nothing():
    outcome = _post_payload('Bash', 'echo x', _bash_response('x'))
    failure = _post_payload('Bash', 'exit 3', None)
    assert _sent(outcome, records=('prompt',)) is None
    assert _sent(failure, records=('prompt',)) is None
    assert _sent(_prompt_payload('hi'), records=('outcome',)) is None
    assert _sent(outcome, records=('outcome',)) is not None
    assert _sent(_prompt_payload('hi'), records=('prompt',)) is not None


def test_a_missing_or_malformed_config_sends_nothing():
    payload = _prompt_payload('hi')
    argv = [sys.executable, '-c', 'pass']
    good = _note_config(argv, ['prompt'])
    bad_notes: list[dict | str] = [
        '{not json',
        {**good, 'kit_note_config': 2},
        {**good, 'note_argv': []},
        {**good, 'note_argv': [1]},
        {**good, 'timeout_s': 0},
        {**good, 'timeout_s': True},
        {**good, 'records': ['prompt', 'other']},
        {**good, 'records': 'prompt'},
    ]
    for bad in bad_notes:
        assert _sent(payload, note_config=bad) is None, bad
    with tempfile.TemporaryDirectory() as td:
        capture = Path(td) / 'c.json'
        live = _note_config([sys.executable, '-I', str(STANDIN), str(capture), 'allow'], ['prompt'])
        for shell in ('{not json', {'kit_shell_config': 1}):
            assert _sent(payload, note_config=live, shell_config=shell) is None, shell
            assert not capture.exists(), shell
        hook = _install(Path(td), None, _shell_config())
        _assert_silent(_run(hook, payload)[0])
        shutil.rmtree(Path(td) / 'kit-shell')
        hook = _install(Path(td), live, None)
        _assert_silent(_run(hook, payload)[0])
        assert not capture.exists()


def _failing_case(td: Path, mode: str, extra_env: dict, late_expected: bool) -> str | None:
    late = td / f'late-{mode}-{len(extra_env)}.marker'
    capture = td / f'capture-{mode}-{len(extra_env)}.json'
    if mode == 'missing':
        argv = [str(td / 'no-such-cli.exe')]
    else:
        argv = [sys.executable, '-I', str(STANDIN), str(capture), mode, str(late)]
    folder = td / f'{mode}-{len(extra_env)}'
    folder.mkdir()
    hook = _install(folder, _note_config(argv, ['prompt', 'outcome']), _shell_config())
    start = time.monotonic()
    proc, elapsed = _run(hook, _prompt_payload('hi'), _env(**extra_env))
    if proc.returncode != 0 or proc.stdout != b'':
        return f'{mode} {extra_env}: exit {proc.returncode}, stdout {proc.stdout!r}'
    if elapsed >= 4.5:
        return f'{mode} {extra_env}: returned after {elapsed:.2f} s'
    if mode in ('hang', 'orphan'):
        time.sleep(max(0.0, start + 9 - time.monotonic()))
        if late.exists() != late_expected:
            return f'{mode} {extra_env}: late marker present={late.exists()}'
    return None


def test_a_failing_cli_leaves_the_mode_silent_and_quick():
    no_system32 = os.pathsep.join(
        p for p in os.environ.get('PATH', '').split(os.pathsep) if 'system32' not in p.lower()
    )
    cases = [
        ('exit3', {}, False),
        ('garbage', {}, False),
        ('missing', {}, False),
        ('hang', {}, False),
        ('hang', {'PATH': no_system32, 'KIT_X': '1'}, False),
        ('hang', {'KIT_SHELL_NO_JOB': '1'}, False),
    ]
    if WINDOWS:
        cases += [('orphan', {}, False), ('orphan', {'KIT_SHELL_NO_JOB': '1'}, True)]
    with tempfile.TemporaryDirectory() as td, ThreadPoolExecutor(len(cases)) as pool:
        errors = [e for e in pool.map(lambda c: _failing_case(Path(td), *c), cases) if e]
    assert not errors, errors


def _settings(records: tuple[str, ...], folder: Path | None = None) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as td:
        home_dir = folder or Path(td) / 'home'
        shutil.rmtree(home_dir, ignore_errors=True)
        home = harnesses.get('claude-code').render_home(home_dir, ENDPOINT, records)
        settings = json.loads(Path(home['config_file']).read_text(encoding='utf-8'))
    return settings['hooks'], home


def test_registration_adds_the_note_entries_after_pretooluse():
    with tempfile.TemporaryDirectory() as td:
        plain, _ = _settings((), Path(td) / 'home')
        hooks, home = _settings(('prompt', 'outcome'), Path(td) / 'home')
    assert list(hooks) == ['PreToolUse', 'UserPromptSubmit', 'PostToolUse', 'PostToolUseFailure']
    assert hooks['PreToolUse'] == plain['PreToolUse'], hooks['PreToolUse']
    pre = hooks['PreToolUse'][0]['hooks'][0]
    entry = {
        'type': 'command',
        'command': pre['command'],
        'args': [*pre['args'], '--note'],
        'timeout': 30,
    }
    assert pre['args'] == ['-I', home['shell_entry']], pre
    assert hooks['UserPromptSubmit'] == [{'hooks': [entry]}], hooks['UserPromptSubmit']
    for name in ('PostToolUse', 'PostToolUseFailure'):
        groups = hooks[name]
        assert len(groups) == 1 and list(groups[0]) == ['matcher', 'hooks'], groups
        assert groups[0]['matcher'] in RESULT_MATCHERS, groups
        assert groups[0]['hooks'] == [entry], groups
        assert 'onFailure' not in json.dumps(groups)


def test_registration_follows_records():
    hooks, _ = _settings(('prompt',))
    assert list(hooks) == ['PreToolUse', 'UserPromptSubmit'], hooks
    hooks, _ = _settings(('outcome',))
    assert list(hooks) == ['PreToolUse', 'PostToolUse', 'PostToolUseFailure'], hooks
    hooks, _ = _settings(())
    assert list(hooks) == ['PreToolUse'], hooks


def test_the_rendered_note_entry_runs_the_note_mode():
    with tempfile.TemporaryDirectory() as td:
        home = harnesses.get('claude-code').render_home(Path(td) / 'home', ENDPOINT, ('prompt',))
        folder = Path(home['shell_config']).parent
        capture = Path(td) / 'captured.json'
        argv = [sys.executable, '-I', str(STANDIN), str(capture), 'allow']
        (folder / 'note_config.json').write_text(
            json.dumps(_note_config(argv, ['prompt'])), encoding='utf-8'
        )
        settings = json.loads(Path(home['config_file']).read_text(encoding='utf-8'))
        entry = settings['hooks']['UserPromptSubmit'][0]['hooks'][0]
        proc = subprocess.run(  # noqa: S603 - argv from the rendered entry, no shell
            [entry['command'], *entry['args']],
            input=_prompt_payload('hello'),
            capture_output=True,
            env=_env(),
            timeout=30,
        )
        _assert_silent(proc)
        assert json.loads(capture.read_bytes())['note']['text'] == 'hello'


if __name__ == '__main__':
    run_module(globals(), 'claude code note mode')

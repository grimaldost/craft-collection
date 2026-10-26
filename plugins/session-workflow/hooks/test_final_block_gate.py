"""Tests for final_block_gate.py: the pending-asks gate on Stop.

The gate exists because a measurement over 499 turns of long sessions found
that a third of the questions the agent asks the operator are first raised in
a message the agent then continues past (a stop that a notification wakes), and
36% of those never reach the final block. The gate keeps a per-session ledger of
the asks each stop message carried and, at a stop with nothing in flight, tells
the model which earlier asks its last message dropped, once per ask, through
`hookSpecificOutput.additionalContext` (guidance, not a hook error).

Stdlib-runnable: `python plugins/session-workflow/hooks/test_final_block_gate.py` prints `ok:`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import final_block_gate as gate

HERE = Path(__file__).resolve().parent

SCRIPT = HERE / 'final_block_gate.py'
HOOKS_JSON = HERE / 'hooks.json'

SESSION = 'test-session-0001'
ASK = 'Posso apagar os seis itens da tabela agora? Libera cerca de 2,4 GB.'
NO_ASK = 'Lote 7 despachado. A bateria passou em 19 de 19 e o commit a7cb5539 esta no branch.'
RESTATED = 'Continuo esperando o seu sim para apagar os seis itens da tabela.'
# Non-ASCII the Windows console codepage (cp1252) cannot encode, and one it can.
UNICODE_ASK = 'Você aprova trocar o lote A → B agora, antes do merge?'
TASK_NOTIFICATION = (
    '<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n'
    '<summary>Background command completed (exit code 0)</summary>\n</task-notification>'
)
HAND_BACK = (
    'Another Claude session sent a message:\n<agent-message from="a1">\n'
    '[Subagent hand-back] The text below is the final report of a subagent.\n</agent-message>'
)


@contextlib.contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def _fresh_state(mode: str | None = 'on'):
    with (
        tempfile.TemporaryDirectory() as tmp,
        _env(**{gate.STATE_DIR_ENV: tmp, gate.GATE: mode, 'CLAUDE_PLUGIN_DATA': None}),
    ):
        yield Path(tmp)


def _stop(message: str, background: list | None = (), active: bool = False) -> dict:
    payload = {
        'session_id': SESSION,
        'hook_event_name': 'Stop',
        'stop_hook_active': active,
        'last_assistant_message': message,
    }
    if background is not None:
        payload['background_tasks'] = list(background)
    return payload


def _context(out: dict | None) -> str:
    assert out is not None, 'expected hook output, got none'
    return out['hookSpecificOutput']['additionalContext']


def test_off_switch_does_nothing():
    with _fresh_state('0') as tmp:
        assert gate.handle_stop(_stop(ASK)) is None
        assert gate.handle_stop(_stop(NO_ASK)) is None
        assert not list(tmp.rglob('*.json')), 'off means no ledger is written'


def test_first_stop_records_the_ask_and_stays_silent():
    with _fresh_state() as tmp:
        assert gate.handle_stop(_stop(ASK)) is None
        ledger = json.loads(next(tmp.rglob('*.json')).read_text(encoding='utf-8'))
        assert [a['text'] for a in ledger['asks']] == [ASK.split('. ')[0] + '?'] or len(
            ledger['asks']
        ) >= 1


def test_later_stop_without_the_ask_advises_once():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        out = gate.handle_stop(_stop(NO_ASK))
        text = _context(out)
        assert 'apagar os seis itens' in text, text
        assert out['hookSpecificOutput']['hookEventName'] == 'Stop'
        assert 'decision' not in out, 'guidance travels as additionalContext, never as a block'
        assert gate.handle_stop(_stop(NO_ASK)) is None, 'each ask is advised once'


def test_a_restated_ask_is_not_advised():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        assert gate.handle_stop(_stop(RESTATED)) is None


def test_background_tasks_defer_the_advice_but_keep_the_ledger():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        assert gate.handle_stop(_stop(NO_ASK, background=[{'id': 't1', 'type': 'shell'}])) is None
        assert 'apagar os seis itens' in _context(gate.handle_stop(_stop(NO_ASK)))


def test_a_missing_background_key_still_advises():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        assert gate.handle_stop(_stop(NO_ASK, background=None)) is not None


def test_prompt_submit_resets_the_ledger():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        gate.handle_prompt_submit({'session_id': SESSION, 'prompt': 'sim, pode apagar'})
        assert gate.handle_stop(_stop(NO_ASK)) is None


def test_observe_mode_records_without_output():
    with _fresh_state('observe') as tmp:
        gate.handle_stop(_stop(ASK))
        assert gate.handle_stop(_stop(NO_ASK)) is None
        ledger = json.loads(next(tmp.rglob('*.json')).read_text(encoding='utf-8'))
        assert any(e['kind'] == 'observed' for e in ledger['events']), ledger['events']


def test_an_empty_final_message_never_advises():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        assert gate.handle_stop(_stop('')) is None
        assert gate.handle_stop(_stop(NO_ASK)) is not None, 'the ask survived the empty stop'


def test_waits_on_subagents_and_ci_are_not_asks():
    assert gate.ask_sentences('Aguardo o PR13 e o oraculo dele. Volto quando o lote fechar.') == []
    assert gate.ask_sentences('Should I merge the PR now, or wait for your review?') != []
    assert gate.ask_sentences('Com o seu sim, faco o merge e apago o worktree.') != []


def test_cli_stop_prints_json_and_exits_zero():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        payload = json.dumps(_stop(NO_ASK)).encode('utf-8')
        stdin = io.TextIOWrapper(io.BytesIO(payload), encoding='utf-8')
        out = io.StringIO()
        saved = sys.stdin
        try:
            sys.stdin = stdin
            with contextlib.redirect_stdout(out):
                code = gate.main(['--stop'])
        finally:
            sys.stdin = saved
        assert code == 0
        printed = json.loads(out.getvalue())
        assert 'apagar os seis itens' in printed['hookSpecificOutput']['additionalContext']


def test_the_switch_values():
    for value, expected in (
        (None, 'observe'),
        ('observe', 'observe'),
        ('on', 'on'),
        ('0', 'off'),
        ('1', 'observe'),
        ('', 'observe'),
    ):
        with _env(**{gate.GATE: value}):
            assert gate.mode() == expected, (value, gate.mode())


def test_a_synthetic_prompt_keeps_the_ledger():
    # A task notification or a hand-back is not a new owner turn: the ask raised
    # before it is still owed, so the next stop that drops it is advised.
    for synthetic in (TASK_NOTIFICATION, HAND_BACK):
        with _fresh_state():
            gate.handle_stop(_stop(ASK))
            gate.handle_prompt_submit({'session_id': SESSION, 'prompt': synthetic})
            assert 'apagar os seis itens' in _context(gate.handle_stop(_stop(NO_ASK)))


def test_an_owner_prompt_after_a_notification_still_resets():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        gate.handle_prompt_submit({'session_id': SESSION, 'prompt': TASK_NOTIFICATION})
        gate.handle_prompt_submit({'session_id': SESSION, 'prompt': 'pode seguir'})
        assert gate.handle_stop(_stop(NO_ASK)) is None


class _BrokenStdout(io.StringIO):
    def write(self, text):
        raise UnicodeEncodeError('charmap', str(text), 0, 1, 'character maps to <undefined>')


def _cli(argv: list[str], payload: dict, stdout) -> int:
    stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode('utf-8')), encoding='utf-8')
    saved_in, saved_out = sys.stdin, sys.stdout
    try:
        sys.stdin, sys.stdout = stdin, stdout
        return gate.main(argv)
    finally:
        sys.stdin, sys.stdout = saved_in, saved_out


def test_an_ask_is_marked_advised_only_after_the_advice_was_written():
    # The 0.28.0 defect: the ledger marked the ask advised before printing, and a
    # print that raised (cp1252 console) lost the advice for good.
    with _fresh_state() as tmp:
        gate.handle_stop(_stop(ASK))
        assert _cli(['--stop'], _stop(NO_ASK), _BrokenStdout()) == 0
        ledger = json.loads(next(tmp.rglob('*.json')).read_text(encoding='utf-8'))
        assert not any(a['advised'] for a in ledger['asks']), ledger['asks']
        out = io.StringIO()
        assert _cli(['--stop'], _stop(NO_ASK), out) == 0
        assert (
            'apagar os seis itens'
            in json.loads(out.getvalue())['hookSpecificOutput']['additionalContext']
        )


# ------------------------------------------------- the real hook contract (subprocess)


def _child_env(state_dir: Path, mode: str | None) -> dict:
    """The child sees a Windows console: stdout encoded as cp1252, no UTF-8 mode."""
    drop = {'PYTHONUTF8', gate.GATE, gate.STATE_DIR_ENV, 'CLAUDE_PLUGIN_DATA'}
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env['PYTHONIOENCODING'] = 'cp1252'
    env[gate.STATE_DIR_ENV] = str(state_dir)
    if mode is not None:
        env[gate.GATE] = mode
    return env


def _hook(flag: str, payload, env: dict) -> subprocess.CompletedProcess:
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), flag],
        input=data,
        capture_output=True,
        env=env,
        timeout=60,
    )


def _prompt(text: str) -> dict:
    return {'session_id': SESSION, 'hook_event_name': 'UserPromptSubmit', 'prompt': text}


def _sequence(env: dict, ask: str = ASK) -> list[subprocess.CompletedProcess]:
    """Stop with an ask, a task-notification prompt, a stop without the ask."""
    return [
        _hook('--stop', _stop(ask), env),
        _hook('--prompt-submit', _prompt(TASK_NOTIFICATION), env),
        _hook('--stop', _stop(NO_ASK), env),
    ]


def test_subprocess_on_advises_once_across_a_task_notification():
    with tempfile.TemporaryDirectory() as tmp:
        outs = _sequence(_child_env(Path(tmp), 'on'))
        assert [p.returncode for p in outs] == [0, 0, 0]
        assert outs[0].stdout == b'' and outs[1].stdout == b'', outs
        context = json.loads(outs[2].stdout.decode('utf-8'))['hookSpecificOutput'][
            'additionalContext'
        ]
        assert 'apagar os seis itens' in context, context
        assert sum(1 for line in context.splitlines() if line.startswith('- ')) == 1, context


def test_subprocess_default_prints_nothing_and_records_the_would_be_advice():
    with tempfile.TemporaryDirectory() as tmp:
        outs = _sequence(_child_env(Path(tmp), None))
        assert [p.returncode for p in outs] == [0, 0, 0]
        assert [p.stdout for p in outs] == [b'', b'', b''], outs
        ledger = json.loads(next(Path(tmp).rglob('*.json')).read_text(encoding='utf-8'))
        observed = [e for e in ledger['events'] if e['kind'] == 'observed']
        assert len(observed) == 1, ledger['events']
        assert any('apagar os seis itens' in a for a in observed[0]['asks']), observed


def test_subprocess_a_unicode_ask_arrives_byte_exact_in_utf8():
    with tempfile.TemporaryDirectory() as tmp:
        outs = _sequence(_child_env(Path(tmp), 'on'), ask=UNICODE_ASK)
        assert [p.returncode for p in outs] == [0, 0, 0]
        assert UNICODE_ASK.encode('utf-8') in outs[2].stdout, outs[2].stdout
        assert (
            UNICODE_ASK
            in json.loads(outs[2].stdout.decode('utf-8'))['hookSpecificOutput']['additionalContext']
        )


def test_subprocess_a_malformed_payload_exits_zero_with_no_output():
    bad = (b'{not json', b'[1, 2]', b'"text"', b'\xff\xfe\x00garbage', b'')
    with tempfile.TemporaryDirectory() as tmp:
        for mode in ('on', None):
            env = _child_env(Path(tmp), mode)
            for flag in ('--stop', '--prompt-submit'):
                for payload in bad:
                    proc = _hook(flag, payload, env)
                    assert proc.returncode == 0, (flag, payload, proc.stderr)
                    assert proc.stdout == b'', (flag, payload, proc.stdout)


def test_subprocess_without_its_helper_module_still_fails_open():
    # A hook that fails exits 0 with no output (ADR-0003), even when a stale or
    # partial install lacks prompt_kind.py beside the script.
    with tempfile.TemporaryDirectory() as tmp:
        lone = Path(tmp) / 'final_block_gate.py'
        lone.write_text(SCRIPT.read_text(encoding='utf-8'), encoding='utf-8')
        env = _child_env(Path(tmp) / 'state', 'on')
        for flag, payload in (('--prompt-submit', _prompt('sim')), ('--stop', _stop(ASK))):
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [sys.executable, str(lone), flag],
                input=json.dumps(payload).encode('utf-8'),
                capture_output=True,
                env=env,
                timeout=60,
            )
            assert proc.returncode == 0, proc.stderr
            assert proc.stdout == b'' and proc.stderr == b'', (proc.stdout, proc.stderr)


def _command_hooks(manifest: dict, event: str) -> list[tuple[str | None, dict]]:
    return [
        (group.get('matcher'), hook)
        for group in manifest['hooks'].get(event, [])
        for hook in group['hooks']
        if hook.get('type') == 'command'
    ]


def test_hooks_json_wires_the_gate_without_the_wrap_up_entry():
    manifest = json.loads(HOOKS_JSON.read_text(encoding='utf-8'))
    text = json.dumps(manifest['hooks'])
    # The series guard has its own --post-tool-use arm; the gate's own entries are
    # pinned exactly below, so the box entry's absence is checked there too.
    assert 'wrap_up' not in text, 'the box entry is gone'
    prefix = [
        'run',
        '--no-project',
        '--',
        'python',
        '${CLAUDE_PLUGIN_ROOT}/hooks/final_block_gate.py',
    ]
    wired = {}
    for event in manifest['hooks']:
        for matcher, hook in _command_hooks(manifest, event):
            if hook['args'][: len(prefix)] == prefix:
                wired.setdefault(event, []).append((matcher, hook['command'], hook['args'][5:]))
    assert wired == {
        'UserPromptSubmit': [(None, 'uv', ['--prompt-submit'])],
        'Stop': [(None, 'uv', ['--stop'])],
    }, wired


if __name__ == '__main__':
    test_the_switch_values()
    test_a_synthetic_prompt_keeps_the_ledger()
    test_an_owner_prompt_after_a_notification_still_resets()
    test_an_ask_is_marked_advised_only_after_the_advice_was_written()
    test_subprocess_on_advises_once_across_a_task_notification()
    test_subprocess_default_prints_nothing_and_records_the_would_be_advice()
    test_subprocess_a_unicode_ask_arrives_byte_exact_in_utf8()
    test_subprocess_a_malformed_payload_exits_zero_with_no_output()
    test_subprocess_without_its_helper_module_still_fails_open()
    test_hooks_json_wires_the_gate_without_the_wrap_up_entry()
    test_off_switch_does_nothing()
    test_first_stop_records_the_ask_and_stays_silent()
    test_later_stop_without_the_ask_advises_once()
    test_a_restated_ask_is_not_advised()
    test_background_tasks_defer_the_advice_but_keep_the_ledger()
    test_a_missing_background_key_still_advises()
    test_prompt_submit_resets_the_ledger()
    test_observe_mode_records_without_output()
    test_an_empty_final_message_never_advises()
    test_waits_on_subagents_and_ci_are_not_asks()
    test_cli_stop_prints_json_and_exits_zero()
    print('ok: final_block_gate records asks per stop and advises each dropped ask once')

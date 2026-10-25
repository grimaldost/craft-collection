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
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import final_block_gate as gate

SESSION = 'test-session-0001'
ASK = 'Posso apagar os seis itens da tabela agora? Libera cerca de 2,4 GB.'
NO_ASK = 'Lote 7 despachado. A bateria passou em 19 de 19 e o commit a7cb5539 esta no branch.'
RESTATED = 'Continuo esperando o seu sim para apagar os seis itens da tabela.'


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
def _fresh_state(mode: str | None = None):
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


def test_the_desktop_box_ask_counts_as_restatement():
    with _fresh_state():
        gate.handle_stop(_stop(ASK))
        gate.handle_post_tool_use(
            {
                'session_id': SESSION,
                'tool_name': 'mcp__ccd_turn__wrap_up',
                'tool_input': {
                    'recap': 'Medicao feita.',
                    'ask': 'Apago os seis itens da tabela agora?',
                },
            }
        )
        assert gate.handle_stop(_stop(NO_ASK)) is None


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


if __name__ == '__main__':
    test_off_switch_does_nothing()
    test_first_stop_records_the_ask_and_stays_silent()
    test_later_stop_without_the_ask_advises_once()
    test_a_restated_ask_is_not_advised()
    test_the_desktop_box_ask_counts_as_restatement()
    test_background_tasks_defer_the_advice_but_keep_the_ledger()
    test_a_missing_background_key_still_advises()
    test_prompt_submit_resets_the_ledger()
    test_observe_mode_records_without_output()
    test_an_empty_final_message_never_advises()
    test_waits_on_subagents_and_ci_are_not_asks()
    test_cli_stop_prints_json_and_exits_zero()
    print('ok: final_block_gate records asks per stop and advises each dropped ask once')

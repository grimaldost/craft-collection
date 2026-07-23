"""Tests for inject_dispatch. Runnable with pytest or `python test_inject_dispatch.py`.

Covers the --prompt-submit cadence machine, its gates, fail-open behavior, the
--session-start demotion, and --reset-state. Every path must exit 0 — a
UserPromptSubmit hook that exits nonzero or hangs blocks the user's prompt.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from contextlib import redirect_stdout

import inject_dispatch


class _Env:
    """Scoped env + state-dir override for a single simulated session."""

    def __init__(self, tmpdir, **extra):
        self.values = {
            'HUMBLEPOWERS_DISPATCH_PROMPT_INJECT': '1',
            'HUMBLEPOWERS_DISPATCH_STATE_DIR': str(tmpdir),
            **extra,
        }
        self.saved = {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return self

    def __exit__(self, *exc):
        for key, old in self.saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


class _FakeStdin:
    """A stdin stand-in exposing the .buffer bytes stream the script reads."""

    def __init__(self, text):
        self.buffer = io.BytesIO(text.encode('utf-8'))


def _submit(prompt, session='s1'):
    payload = json.dumps(
        {
            'session_id': session,
            'cwd': os.getcwd(),
            'hook_event_name': 'UserPromptSubmit',
            'prompt': prompt,
        }
    )
    out = io.StringIO()
    old_stdin = sys.stdin
    sys.stdin = _FakeStdin(payload)
    try:
        with redirect_stdout(out):
            code = inject_dispatch.main(['--prompt-submit'])
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue()


def _run(args, stdin_text=''):
    out = io.StringIO()
    old_stdin = sys.stdin
    sys.stdin = _FakeStdin(stdin_text)
    try:
        with redirect_stdout(out):
            code = inject_dispatch.main(args)
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue()


SUBSTANTIVE = 'Migrate the billing pipeline to the new warehouse without changing output'


def test_inert_without_gate(tmp_path):
    with _Env(tmp_path, HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=None):
        code, out = _submit(SUBSTANTIVE)
    assert code == 0 and out == ''


def test_first_prompt_gets_full_protocol(tmp_path):
    with _Env(tmp_path):
        code, out = _submit(SUBSTANTIVE)
    assert code == 0
    assert '<toolkit-dispatch>' in out
    assert 'Name the task in one phrase' in out, 'first prompt should carry the full protocol'


def test_second_prompt_gets_micro(tmp_path):
    with _Env(tmp_path):
        _submit(SUBSTANTIVE)
        code, out = _submit('Now refactor the transform that feeds the finance dashboard')
    assert code == 0
    assert '<toolkit-dispatch>' in out
    assert 'Name the task in one phrase' not in out, 'second prompt should be the micro tier'


def test_full_reescalates_after_n_prompts(tmp_path):
    with _Env(tmp_path, HUMBLEPOWERS_DISPATCH_FULL_EVERY='3'):
        _submit(SUBSTANTIVE)
        _submit('Refactor the transform behind the finance dashboard now')
        _submit('Backfill the sessions table and replay the history please')
        code, out = _submit('Design the data contract for the customer events dataset')
    assert code == 0
    assert 'Name the task in one phrase' in out, '4th prompt (N=3) should re-escalate to full'


def test_full_reescalates_after_stale_minutes(tmp_path):
    with _Env(tmp_path, HUMBLEPOWERS_DISPATCH_FULL_MINUTES='1'):
        _submit(SUBSTANTIVE)
        state_file = inject_dispatch._state_path('s1')
        state = json.loads(state_file.read_text(encoding='utf-8'))
        state['last_full_ts'] = time.time() - 120
        state_file.write_text(json.dumps(state), encoding='utf-8')
        _code, out = _submit('Backfill the sessions table and replay the history please')
    assert 'Name the task in one phrase' in out


def test_slash_commands_are_silent(tmp_path):
    with _Env(tmp_path):
        code, out = _submit('/review-panel the caching design')
    assert code == 0 and out == ''


def test_short_followups_are_silent(tmp_path):
    with _Env(tmp_path):
        for prompt in ('yes', 'continue', 'ok go ahead', 'hang on'):
            code, out = _submit(prompt)
            assert code == 0 and out == '', f'short follow-up {prompt!r} must be gated'


def test_router_hint_appended_on_match(tmp_path):
    with _Env(tmp_path):
        _submit(
            'hello there my good friend, how are you doing today'
        )  # ungated: burns the full tier
        _code, out = _submit('Backfill six months of history into the sessions table and replay it')
    assert 'matches triggers for' in out
    assert 'data-engineering-discipline' in out


def test_router_can_be_disabled(tmp_path):
    with _Env(tmp_path, HUMBLEPOWERS_DISPATCH_ROUTER='0'):
        _submit(SUBSTANTIVE)
        _code, out = _submit('Backfill six months of history into the sessions table and replay it')
    assert 'matches triggers for' not in out


def test_payload_is_ascii(tmp_path):
    with _Env(tmp_path):
        _, out1 = _submit(SUBSTANTIVE)
        _, out2 = _submit('Backfill six months of history into the sessions table and replay it')
    out1.encode('ascii')
    out2.encode('ascii')


def test_malformed_stdin_fails_open(tmp_path):
    with _Env(tmp_path):
        code, out = _run(['--prompt-submit'], stdin_text='{not json')
    assert code == 0 and out == ''


def test_reset_state_reescalates(tmp_path):
    with _Env(tmp_path):
        _submit(SUBSTANTIVE)
        _submit('Refactor the transform behind the finance dashboard now')
        payload = json.dumps(
            {'session_id': 's1', 'hook_event_name': 'SessionStart', 'source': 'compact'}
        )
        code, _ = _run(['--reset-state'], stdin_text=payload)
        assert code == 0
        _, out = _submit('Backfill the sessions table and replay the history please')
    assert 'Name the task in one phrase' in out, 'post-reset prompt should re-escalate to full'


def test_session_start_demoted_when_prompt_inject_on(tmp_path):
    with _Env(tmp_path):
        code, out = _run(['--session-start'])
    assert code == 0 and out == ''


def test_session_start_unchanged_when_prompt_inject_off(tmp_path):
    with _Env(
        tmp_path,
        HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=None,
        HUMBLEPOWERS_DISPATCH_INJECT='1',
    ):
        code, out = _run(['--session-start'])
    assert code == 0 and 'Name the task in one phrase' in out


def test_synthetic_prompts_are_silent(tmp_path):
    tail = (
        ' Subagent task complete: the migration finished successfully with '
        'all tests passing and no errors reported anywhere in the pipeline'
    )
    for i, prefix in enumerate(inject_dispatch.SYNTHETIC_PREFIXES):
        session = f'synth{i}'
        with _Env(tmp_path):
            code, out = _submit(prefix + tail, session=session)
            state_file = inject_dispatch._state_path(session)
            log_file = inject_dispatch._state_dir() / 'dispatch-log.ndjson'
        assert code == 0 and out == '', f'{prefix!r} prompt must be silent'
        assert not state_file.exists(), f'{prefix!r} prompt must not create session state'
        assert not log_file.exists(), f'{prefix!r} prompt must not append telemetry'


def test_normal_long_prompt_still_injects_regression(tmp_path):
    with _Env(tmp_path):
        code, out = _submit(SUBSTANTIVE)
        state_file = inject_dispatch._state_path('s1')
        state = json.loads(state_file.read_text(encoding='utf-8'))
    assert code == 0
    assert '<toolkit-dispatch>' in out
    assert 'Name the task in one phrase' in out
    assert state['n'] == 1


if __name__ == '__main__':
    import tempfile
    from pathlib import Path

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            with tempfile.TemporaryDirectory() as td:
                try:
                    fn(Path(td))
                except AssertionError as exc:
                    failed += 1
                    print(f'FAIL {name}: {exc}')
    if failed:
        sys.exit(1)
    print('ok: all inject_dispatch tests passed')

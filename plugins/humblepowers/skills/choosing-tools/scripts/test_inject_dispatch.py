"""Tests for inject_dispatch. Runnable with pytest or `python test_inject_dispatch.py`.

Covers the --prompt-submit router-hint injector, its gates, fail-open behavior,
telemetry, and the --health reader. Every path must exit 0 - a UserPromptSubmit
hook that exits nonzero or hangs blocks the user's prompt.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout

import inject_dispatch

# A prompt whose wording lexically triggers the router (data-engineering-discipline).
ROUTING = 'Backfill six months of history into the sessions table and replay it'
# Substantive (>= 4 words, >= 15 chars, non-slash) but hits no router rule.
NON_ROUTING = 'tell me a fun fact about the history of typography please'


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


def _log_records(tmp_path):
    log = inject_dispatch._log_path()
    if not log.exists():
        return []
    return [
        json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()
    ]


# --- --prompt-submit -------------------------------------------------------


def test_inert_without_gate(tmp_path):
    with _Env(tmp_path, HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=None):
        code, out = _submit(ROUTING)
    assert code == 0 and out == ''


def test_routing_prompt_gets_hint(tmp_path):
    with _Env(tmp_path):
        code, out = _submit(ROUTING)
    assert code == 0
    assert '<toolkit-dispatch>' in out
    assert 'matches triggers for' in out
    assert 'data-engineering-discipline' in out


def test_non_routing_prompt_is_silent(tmp_path):
    with _Env(tmp_path):
        code, out = _submit(NON_ROUTING)
    assert code == 0 and out == '', 'a substantive but non-matching prompt must inject nothing'


def test_slash_commands_are_silent(tmp_path):
    with _Env(tmp_path):
        code, out = _submit('/review-panel the caching design and the router rules')
    assert code == 0 and out == ''


def test_short_followups_are_silent(tmp_path):
    with _Env(tmp_path):
        for prompt in ('yes', 'continue', 'ok go ahead', 'hang on'):
            code, out = _submit(prompt)
            assert code == 0 and out == '', f'short follow-up {prompt!r} must be gated'


def test_router_can_be_disabled(tmp_path):
    with _Env(tmp_path, HUMBLEPOWERS_DISPATCH_ROUTER='0'):
        code, out = _submit(ROUTING)
    assert code == 0 and out == '', 'ROUTER=0 leaves nothing to inject, so the hook is silent'


def test_payload_is_ascii(tmp_path):
    with _Env(tmp_path):
        _, out = _submit(ROUTING)
    out.encode('ascii')  # must not raise


def test_malformed_stdin_fails_open(tmp_path):
    with _Env(tmp_path):
        code, out = _run(['--prompt-submit'], stdin_text='{not json')
    assert code == 0 and out == ''


def test_synthetic_prompts_are_silent(tmp_path):
    tail = (
        ' Subagent task complete: the migration finished successfully with '
        'all tests passing and no errors reported anywhere in the pipeline'
    )
    for i, prefix in enumerate(inject_dispatch.SYNTHETIC_PREFIXES):
        with _Env(tmp_path):
            code, out = _submit(prefix + tail, session=f'synth{i}')
            log_file = inject_dispatch._log_path()
        assert code == 0 and out == '', f'{prefix!r} prompt must be silent'
        assert not log_file.exists(), f'{prefix!r} prompt must not append telemetry'


def test_telemetry_records_hit_and_miss(tmp_path):
    with _Env(tmp_path):
        _submit(ROUTING)
        _submit(NON_ROUTING)
        records = _log_records(tmp_path)
    assert len(records) == 2, 'each gated-through prompt logs exactly one record'
    hit, miss = records
    assert hit['injected'] is True and any('data-engineering' in s for s in hit['router_hits'])
    assert miss['injected'] is False and miss['router_hits'] == []


# --- --health --------------------------------------------------------------


def test_health_no_records(tmp_path):
    with _Env(tmp_path):
        code, out = _run(['--health'])
    assert code == 0 and 'no records yet' in out


def test_health_summarizes_after_submits(tmp_path):
    with _Env(tmp_path):
        _submit(ROUTING)
        _submit(ROUTING, session='s2')
        _submit(NON_ROUTING)
        code, out = _run(['--health'])
    assert code == 0
    assert 'prompts logged: 3' in out
    assert 'hint injected:  2' in out
    assert 'data-engineering-discipline' in out
    out.encode('ascii')  # health output must be ASCII


def test_health_fails_open_on_corrupt_log(tmp_path):
    with _Env(tmp_path):
        _submit(ROUTING)  # one good record + creates the dir
        log = inject_dispatch._log_path()
        with log.open('a', encoding='utf-8') as fh:
            fh.write('{ this is not json\n')
        code, out = _run(['--health'])
    assert code == 0, 'a corrupt telemetry line must not crash --health'
    assert 'prompts logged: 1' in out, 'the corrupt line is skipped, the good one counted'


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

#!/usr/bin/env python3
"""Self-contained checks for exercise_ledger.py (no pytest required)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exercise_ledger as el


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


@contextlib.contextmanager
def _env(**kv):
    saved = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
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


def _run(argv: list[str], payload: object) -> tuple[int, str]:
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    old_stdin = sys.stdin
    out = io.StringIO()
    try:
        sys.stdin = _FakeStdin(raw)
        with contextlib.redirect_stdout(out):
            rc = el.main(argv)
    finally:
        sys.stdin = old_stdin
    return rc, out.getvalue()


def _write_transcript(path: Path, prompts: list[str]) -> None:
    lines = [json.dumps({'type': 'user', 'message': {'content': p}}) for p in prompts]
    lines.append(json.dumps({'type': 'assistant', 'message': {'content': 'x'}}))
    lines.append('{ not json')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _seed_ledger(td: Path, session: str, skills: list[str]) -> None:
    p = td / f'{session}.jsonl'
    with p.open('a', encoding='utf-8') as fh:
        for s in skills:
            fh.write(json.dumps({'ts': 0, 'tool': 'Skill', 'skill': s}) + '\n')
        fh.write('corrupt line\n')


def test_record_gate_off_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        with _env(SESSION_WORKFLOW_EXERCISE_LEDGER=None, SESSION_WORKFLOW_LEDGER_DIR=td):
            rc, out = _run(
                ['--record'],
                {'tool_name': 'Skill', 'tool_input': {'skill': 's:a'}, 'session_id': 'sid'},
            )
        assert rc == 0 and out == ''
        assert list(Path(td).iterdir()) == []


def test_record_skill_and_plugin_mcp_append_entries():
    with tempfile.TemporaryDirectory() as td:
        with _env(SESSION_WORKFLOW_EXERCISE_LEDGER='1', SESSION_WORKFLOW_LEDGER_DIR=td):
            _run(
                ['--record'],
                {
                    'tool_name': 'Skill',
                    'tool_input': {'skill': 'session-workflow:review-panel'},
                    'session_id': 'sid-1',
                    'prompt_id': 'p1',
                },
            )
            _run(
                ['--record'],
                {'tool_name': 'mcp__plugin_convoy_convoy__convoy_run', 'session_id': 'sid-1'},
            )
        entries = [
            json.loads(line)
            for line in (Path(td) / 'sid-1.jsonl').read_text(encoding='utf-8').splitlines()
        ]
    assert len(entries) == 2, entries
    assert entries[0]['skill'] == 'session-workflow:review-panel'
    assert entries[0]['prompt_id'] == 'p1'
    assert entries[1]['skill'] == 'mcp__plugin_convoy_convoy__convoy_run'


def test_record_ignores_non_matching_and_malformed():
    with tempfile.TemporaryDirectory() as td:
        with _env(SESSION_WORKFLOW_EXERCISE_LEDGER='1', SESSION_WORKFLOW_LEDGER_DIR=td):
            for payload in (
                {'tool_name': 'Bash', 'session_id': 'sid-2'},
                {'tool_name': 'mcp__other__x', 'session_id': 'sid-2'},
                {'tool_name': 7, 'session_id': 'sid-2'},
                {'session_id': 'sid-2'},
                b'{ not json',
                {'tool_name': 'Skill', 'tool_input': 'not-a-dict', 'session_id': 'sid-2'},
            ):
                rc, out = _run(['--record'], payload)
                assert rc == 0 and out == '', payload
        written = list(Path(td).iterdir())
        # Only the Skill-with-bad-input payload records (falls back to the tool name).
        assert len(written) == 1, written
        entries = [json.loads(x) for x in written[0].read_text(encoding='utf-8').splitlines()]
        assert [e['skill'] for e in entries] == ['Skill']


def test_record_sanitizes_hostile_session_id():
    with tempfile.TemporaryDirectory() as td:
        with _env(SESSION_WORKFLOW_EXERCISE_LEDGER='1', SESSION_WORKFLOW_LEDGER_DIR=td):
            _run(
                ['--record'],
                {'tool_name': 'Skill', 'tool_input': {'skill': 'a'}, 'session_id': '../../x' * 40},
            )
        names = [p.name for p in Path(td).iterdir()]
    assert len(names) == 1 and names[0].endswith('.jsonl')
    assert '..' not in names[0] and len(names[0]) <= 64 + len('.jsonl')


def _nudge_env(td: str, min_turns: str = '2'):
    return _env(
        SESSION_WORKFLOW_FEEDBACK_NUDGE='1',
        SESSION_WORKFLOW_EXERCISE_LEDGER=None,
        SESSION_WORKFLOW_LEDGER_DIR=td,
        SESSION_WORKFLOW_NUDGE_MIN_TURNS=min_turns,
    )


def test_stop_nudge_fires_once_with_debt():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _seed_ledger(tdp, 'sid', ['humblepowers:choosing-tools', 'mcp__plugin_fathom_fathom__plan'])
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['first prompt', 'second prompt'])
        payload = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _nudge_env(td):
            rc, out = _run(['--stop-nudge'], payload)
            assert rc == 0, out
            block = json.loads(out)
            assert block['decision'] == 'block'
            assert 'humblepowers:choosing-tools' in block['reason']
            assert out == out.encode('ascii', errors='replace').decode('ascii'), 'non-ASCII output'
            assert (tdp / 'sid.nudged').is_file()
            rc2, out2 = _run(['--stop-nudge'], payload)
            assert rc2 == 0 and out2 == '', 'second stop must be silent (marker)'


def test_stop_nudge_silent_paths():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _seed_ledger(tdp, 'sid', ['humblepowers:choosing-tools'])
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'])
        base = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _env(SESSION_WORKFLOW_FEEDBACK_NUDGE=None, SESSION_WORKFLOW_LEDGER_DIR=td):
            assert _run(['--stop-nudge'], base) == (0, ''), 'gate off'
        with _nudge_env(td):
            assert _run(['--stop-nudge'], {**base, 'stop_hook_active': True}) == (0, ''), (
                'stop_hook_active'
            )
            assert _run(['--stop-nudge'], {**base, 'session_id': 'other'}) == (0, ''), 'no ledger'
        with _nudge_env(td, min_turns='3'):
            assert _run(['--stop-nudge'], base) == (0, ''), 'below turn threshold'
        with _nudge_env(td):
            assert _run(['--stop-nudge'], {'session_id': 'sid'}) == (0, ''), 'no transcript path'
        assert not (tdp / 'sid.nudged').exists(), 'no silent path may burn the marker'


def test_stop_nudge_debt_cleared_by_tool_feedback():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _seed_ledger(tdp, 'sid', ['humblepowers:choosing-tools', 'session-workflow:tool-feedback'])
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two', 'three'])
        with _nudge_env(td):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert (rc, out) == (0, ''), 'tool-feedback invocation must clear the debt'


def test_synthetic_user_records_do_not_count_as_turns():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _seed_ledger(tdp, 'sid', ['humblepowers:choosing-tools'])
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['real prompt', '[SYSTEM NOTIFICATION - NOT USER INPUT] done', '<task-notification>x'],
        )
        with _nudge_env(td):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert (rc, out) == (0, ''), 'synthetic records counted toward the turn gate'


def test_count_user_turns_shapes():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        blocks = json.dumps(
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'block prompt'}]}}
        )
        no_msg = json.dumps({'type': 'user'})
        p.write_text('\n'.join([blocks, no_msg]) + '\n', encoding='utf-8')
        assert el._count_user_turns(str(p)) == 1, 'textless user record must NOT count'
        assert el._count_user_turns(str(Path(td) / 'missing.jsonl')) == 0
        assert el._count_user_turns(None) == 0


def test_tool_result_user_records_do_not_count_as_turns():
    # In a real transcript most type=="user" records are tool results (content
    # blocks with no human text) - ~64 of 71 in the reviewed sample. Counting
    # them makes the min-turns gate inert.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        human = {'type': 'user', 'message': {'content': 'real prompt'}}
        tool_result = {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tu1',
                        'content': [{'type': 'text', 'text': 'file contents here'}],
                    }
                ]
            },
        }
        titled_tool_result = {
            'type': 'user',
            'message': {'content': [{'type': 'tool_result', 'text': 'flat result text'}]},
        }
        lines = (
            [json.dumps(human)] + [json.dumps(tool_result)] * 5 + [json.dumps(titled_tool_result)]
        )
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        assert el._count_user_turns(str(p)) == 1, 'tool_result records counted as human turns'


def test_transcript_bom_and_crlf_tolerated():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        recs = [
            json.dumps({'type': 'user', 'message': {'content': f'prompt {i}'}}) for i in range(3)
        ]
        p.write_bytes(b'\xef\xbb\xbf' + '\r\n'.join(recs).encode('utf-8') + b'\r\n')
        assert el._count_user_turns(str(p)) == 3, 'BOM/CRLF transcript undercounted'


def test_nudge_output_ascii_with_non_ascii_skill_name():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _seed_ledger(tdp, 'sid', ['plugin:habilitação-中文'])
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'])
        with _nudge_env(td):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert rc == 0 and out, 'nudge must fire'
    out.encode('ascii')  # raises -> non-ASCII leaked to stdout (cp1252 hazard)


def test_failed_print_does_not_burn_the_marker():
    class _Boom:
        def write(self, *a):
            raise OSError('console gone')

        def flush(self):
            pass

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        _seed_ledger(tdp, 'sid', ['humblepowers:choosing-tools'])
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'])
        payload = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _nudge_env(td):
            old_stdin = sys.stdin
            try:
                sys.stdin = _FakeStdin(json.dumps(payload).encode('utf-8'))
                with contextlib.redirect_stdout(_Boom()):
                    rc = el.main(['--stop-nudge'])
            finally:
                sys.stdin = old_stdin
            assert rc == 0, 'a delivery failure must still exit 0'
            assert not (tdp / 'sid.nudged').exists(), 'failed delivery burned the slot'
            rc2, out2 = _run(['--stop-nudge'], payload)
            assert rc2 == 0 and out2, 'retry after failed delivery must re-fire'


def test_min_turns_garbage_falls_back():
    for raw, want in (('abc', 8), ('0', 8), ('-3', 8), ('5', 5), (None, 8)):
        with _env(SESSION_WORKFLOW_NUDGE_MIN_TURNS=raw):
            assert el._min_turns() == want, (raw, want)


def test_main_unknown_mode_and_garbage_stdin_exit_0():
    assert _run([], {}) == (0, '')
    assert _run(['--stop-nudge'], b'\xff\xfe garbage')[0] == 0


def main() -> int:
    test_record_gate_off_writes_nothing()
    test_record_skill_and_plugin_mcp_append_entries()
    test_record_ignores_non_matching_and_malformed()
    test_record_sanitizes_hostile_session_id()
    test_stop_nudge_fires_once_with_debt()
    test_stop_nudge_silent_paths()
    test_stop_nudge_debt_cleared_by_tool_feedback()
    test_synthetic_user_records_do_not_count_as_turns()
    test_count_user_turns_shapes()
    test_tool_result_user_records_do_not_count_as_turns()
    test_transcript_bom_and_crlf_tolerated()
    test_nudge_output_ascii_with_non_ascii_skill_name()
    test_failed_print_does_not_burn_the_marker()
    test_min_turns_garbage_falls_back()
    test_main_unknown_mode_and_garbage_stdin_exit_0()
    print('ok: exercise_ledger')
    return 0


if __name__ == '__main__':
    sys.exit(main())

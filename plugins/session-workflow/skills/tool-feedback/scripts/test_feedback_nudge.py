#!/usr/bin/env python3
"""Self-contained checks for feedback_nudge.py (no pytest required)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import feedback_nudge as fn


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
            rc = fn.main(argv)
    finally:
        sys.stdin = old_stdin
    return rc, out.getvalue()


def _skill_call(name: str) -> dict:
    """One assistant record carrying a Skill tool_use -- the real transcript shape
    (verified against six live transcripts, 2026-08-11)."""
    return {
        'type': 'assistant',
        'message': {
            'content': [
                {'type': 'tool_use', 'id': 'tu1', 'name': 'Skill', 'input': {'skill': name}}
            ]
        },
    }


def _mcp_call(name: str) -> dict:
    return {
        'type': 'assistant',
        'message': {'content': [{'type': 'tool_use', 'id': 'tu2', 'name': name, 'input': {}}]},
    }


def _write_transcript(path: Path, prompts: list[str], records: list[dict] | None = None) -> None:
    lines = [json.dumps({'type': 'user', 'message': {'content': p}}) for p in prompts]
    lines += [json.dumps(r) for r in records or []]
    lines.append(json.dumps({'type': 'assistant', 'message': {'content': 'plain text turn'}}))
    lines.append('{ not json')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _targets(td: Path) -> Path:
    p = td / 'feedback-targets.toml'
    p.write_text('[keel]\nrepo = "/tmp/keel"\n', encoding='utf-8')
    return p


def _nudge_env(td: str, targets: str, min_turns: str = '2'):
    return _env(
        SESSION_WORKFLOW_FEEDBACK_NUDGE=None,  # default ON: nothing set
        SESSION_WORKFLOW_NUDGE_STATE_DIR=td,
        FEEDBACK_TARGETS_FILE=targets,
        SESSION_WORKFLOW_NUDGE_MIN_TURNS=min_turns,
    )


def test_fires_once_with_no_env_set():
    """The hook ships ON: an unset gate is not a default, and this one had never
    fired anywhere. The binding check below is what makes that safe."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['first prompt', 'second prompt'],
            [
                _skill_call('humblepowers:choosing-tools'),
                _mcp_call('mcp__plugin_fathom_fathom__plan'),
            ],
        )
        payload = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _nudge_env(td, str(_targets(tdp))):
            rc, out = _run(['--stop-nudge'], payload)
            assert rc == 0, out
            block = json.loads(out)
            assert block['decision'] == 'block'
            assert 'humblepowers:choosing-tools' in block['reason']
            assert 'mcp__plugin_fathom_fathom__plan' in block['reason']
            assert out == out.encode('ascii', errors='replace').decode('ascii'), 'non-ASCII output'
            assert (tdp / 'sid.nudged').is_file()
            rc2, out2 = _run(['--stop-nudge'], payload)
            assert rc2 == 0 and out2 == '', 'second stop must be silent (marker)'


def test_silent_without_a_registered_targets_file():
    """The binding check. With no feedback-targets file there is nowhere to report
    to, so a default-on nudge must cost an install with no registered tools
    nothing at all."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['a', 'b'], [_skill_call('humblepowers:choosing-tools')])
        with _env(
            SESSION_WORKFLOW_FEEDBACK_NUDGE=None,
            SESSION_WORKFLOW_NUDGE_STATE_DIR=td,
            FEEDBACK_TARGETS_FILE=str(tdp / 'does-not-exist.toml'),
            SESSION_WORKFLOW_NUDGE_MIN_TURNS='2',
        ):
            assert _run(
                ['--stop-nudge'], {'session_id': 's', 'transcript_path': str(transcript)}
            ) == (
                0,
                '',
            )
        assert not (tdp / 's.nudged').exists()


def test_silent_paths():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        targets = str(_targets(tdp))
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'], [_skill_call('humblepowers:choosing-tools')])
        base = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _env(
            SESSION_WORKFLOW_FEEDBACK_NUDGE='0',
            SESSION_WORKFLOW_NUDGE_STATE_DIR=td,
            FEEDBACK_TARGETS_FILE=targets,
        ):
            assert _run(['--stop-nudge'], base) == (0, ''), 'opt-out'
        with _nudge_env(td, targets):
            assert _run(['--stop-nudge'], {**base, 'stop_hook_active': True}) == (0, ''), (
                'stop_hook_active'
            )
        with _nudge_env(td, targets, min_turns='3'):
            assert _run(['--stop-nudge'], base) == (0, ''), 'below turn threshold'
        with _nudge_env(td, targets):
            assert _run(['--stop-nudge'], {'session_id': 'sid'}) == (0, ''), 'no transcript path'
        with _nudge_env(td, targets):
            bare = tdp / 'bare.jsonl'
            _write_transcript(bare, ['one', 'two'])
            assert _run(['--stop-nudge'], {**base, 'transcript_path': str(bare)}) == (0, ''), (
                'no plugin tool exercised'
            )
        assert not (tdp / 'sid.nudged').exists(), 'no silent path may burn the marker'


def test_debt_cleared_by_tool_feedback():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['one', 'two', 'three'],
            [
                _skill_call('humblepowers:choosing-tools'),
                _skill_call('session-workflow:tool-feedback'),
            ],
        )
        with _nudge_env(td, str(_targets(tdp))):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert (rc, out) == (0, ''), 'tool-feedback invocation must clear the debt'


def test_synthetic_user_records_do_not_count_as_turns():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['real prompt', '[SYSTEM NOTIFICATION - NOT USER INPUT] done', '<task-notification>x'],
            [_skill_call('humblepowers:choosing-tools')],
        )
        with _nudge_env(td, str(_targets(tdp))):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert (rc, out) == (0, ''), 'synthetic records counted toward the turn gate'


def test_read_transcript_shapes():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        blocks = json.dumps(
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'block prompt'}]}}
        )
        no_msg = json.dumps({'type': 'user'})
        p.write_text('\n'.join([blocks, no_msg]) + '\n', encoding='utf-8')
        assert fn.read_transcript(str(p)) == (1, []), 'textless user record must NOT count'
        assert fn.read_transcript(str(Path(td) / 'missing.jsonl')) == (0, [])
        assert fn.read_transcript(None) == (0, [])


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
        lines = [json.dumps(human)] + [json.dumps(tool_result)] * 5
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        assert fn.read_transcript(str(p))[0] == 1, 'tool_result records counted as human turns'


def test_non_plugin_tool_calls_are_not_debt():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        rec = {
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'ls'}},
                    {'type': 'tool_use', 'name': 'mcp__other__thing', 'input': {}},
                ]
            },
        }
        p.write_text(json.dumps(rec) + '\n', encoding='utf-8')
        assert fn.read_transcript(str(p))[1] == [], 'ordinary tools counted as plugin exercise'


def test_transcript_bom_and_crlf_tolerated():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        recs = [
            json.dumps({'type': 'user', 'message': {'content': f'prompt {i}'}}) for i in range(3)
        ]
        p.write_bytes(b'\xef\xbb\xbf' + '\r\n'.join(recs).encode('utf-8') + b'\r\n')
        assert fn.read_transcript(str(p))[0] == 3, 'BOM/CRLF transcript undercounted'


def test_output_ascii_with_non_ascii_skill_name():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'], [_skill_call('plugin:habilitação-中文')])
        with _nudge_env(td, str(_targets(tdp))):
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
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'], [_skill_call('humblepowers:choosing-tools')])
        payload = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _nudge_env(td, str(_targets(tdp))):
            old_stdin = sys.stdin
            try:
                sys.stdin = _FakeStdin(json.dumps(payload).encode('utf-8'))
                with contextlib.redirect_stdout(_Boom()):
                    rc = fn.main(['--stop-nudge'])
            finally:
                sys.stdin = old_stdin
            assert rc == 0, 'a delivery failure must still exit 0'
            assert not (tdp / 'sid.nudged').exists(), 'failed delivery burned the slot'
            rc2, out2 = _run(['--stop-nudge'], payload)
            assert rc2 == 0 and out2, 'retry after failed delivery must re-fire'


def test_min_turns_garbage_falls_back():
    for raw, want in (('abc', 8), ('0', 8), ('-3', 8), ('5', 5), (None, 8)):
        with _env(SESSION_WORKFLOW_NUDGE_MIN_TURNS=raw):
            assert fn._min_turns() == want, (raw, want)


def test_main_unknown_mode_and_garbage_stdin_exit_0():
    assert _run([], {}) == (0, '')
    assert _run(['--stop-nudge'], b'\xff\xfe garbage')[0] == 0


def _real_registry(td: Path) -> Path:
    """A feedback-targets file in the shipped v1 shape, with one target whose
    repo actually ships a plugin and one that does not."""
    craft = td / 'craft-collection'
    (craft / 'plugins' / 'session-workflow').mkdir(parents=True)
    convoy = td / 'convoy'
    convoy.mkdir()
    p = td / 'real-targets.toml'
    p.write_text(
        '[targets.craft-collection]\n'
        f'repo = "{craft.as_posix()}"\n'
        'feedback_dir = "/tmp/fb"\n'
        '\n'
        '[targets.convoy]\n'
        f'repo = "{convoy.as_posix()}"\n',
        encoding='utf-8',
    )
    return p


def test_registered_repos_parses_the_targets_file():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert sorted(repos) == ['convoy', 'craft-collection']


def test_a_plugin_skill_resolves_through_the_repo_that_ships_it():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert fn.is_registered('session-workflow:compaction-survival', repos)


def test_a_bare_personal_skill_is_not_registered():
    # The observed defect: the nudge named `mantis-wisdom` -- a personal skill
    # under ~/.claude/skills, in no registry -- as a "plugin tool", sending the
    # reader to the registry to confirm a non-target.
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert not fn.is_registered('mantis-wisdom', repos)


def test_a_target_named_directly_is_registered():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert fn.is_registered('convoy', repos)


def test_an_mcp_plugin_tool_resolves_to_its_plugin():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert fn.is_registered('mcp__plugin_convoy_convoy__convoy_run', repos)


def test_filtering_drops_only_the_unregistered():
    with tempfile.TemporaryDirectory() as td:
        targets = _real_registry(Path(td))
        tools = ['mantis-wisdom', 'session-workflow:compaction-survival', 'other-skill']
        assert fn.registered_only(tools, targets) == ['session-workflow:compaction-survival']


def test_the_filter_fails_open_when_no_repo_resolves():
    # A registry whose checkouts moved must not silence a real debt: saying too
    # much is a smaller failure than going quiet on a report that is owed.
    with tempfile.TemporaryDirectory() as td:
        targets = Path(td) / 'moved.toml'
        targets.write_text('[targets.gone]\nrepo = "/nowhere/at/all"\n', encoding='utf-8')
        tools = ['mantis-wisdom', 'session-workflow:compaction-survival']
        assert fn.registered_only(tools, targets) == tools


def test_a_session_of_only_unregistered_skills_owes_nothing():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        targets = _real_registry(tdp)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript, ['first prompt', 'second prompt'], [_skill_call('mantis-wisdom')]
        )
        with _nudge_env(td, str(targets)):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'unreg', 'transcript_path': str(transcript)}
            )
        assert rc == 0
        assert out.strip() == '', 'no registered tool ran, so there is no debt to nudge about'


def test_a_registered_skill_beside_an_unregistered_one_still_nudges():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        targets = _real_registry(tdp)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['first prompt', 'second prompt'],
            [_skill_call('mantis-wisdom'), _skill_call('session-workflow:compaction-survival')],
        )
        with _nudge_env(td, str(targets)):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'mixed', 'transcript_path': str(transcript)}
            )
        assert rc == 0
        assert 'compaction-survival' in out
        assert 'mantis-wisdom' not in out, 'a non-target must not be named as a registered tool'


def main() -> int:
    test_fires_once_with_no_env_set()
    test_silent_without_a_registered_targets_file()
    test_silent_paths()
    test_debt_cleared_by_tool_feedback()
    test_synthetic_user_records_do_not_count_as_turns()
    test_read_transcript_shapes()
    test_tool_result_user_records_do_not_count_as_turns()
    test_non_plugin_tool_calls_are_not_debt()
    test_transcript_bom_and_crlf_tolerated()
    test_output_ascii_with_non_ascii_skill_name()
    test_failed_print_does_not_burn_the_marker()
    test_min_turns_garbage_falls_back()
    test_main_unknown_mode_and_garbage_stdin_exit_0()
    test_registered_repos_parses_the_targets_file()
    test_a_plugin_skill_resolves_through_the_repo_that_ships_it()
    test_a_bare_personal_skill_is_not_registered()
    test_a_target_named_directly_is_registered()
    test_an_mcp_plugin_tool_resolves_to_its_plugin()
    test_filtering_drops_only_the_unregistered()
    test_the_filter_fails_open_when_no_repo_resolves()
    test_a_session_of_only_unregistered_skills_owes_nothing()
    test_a_registered_skill_beside_an_unregistered_one_still_nudges()
    print('ok: feedback_nudge')
    return 0


if __name__ == '__main__':
    sys.exit(main())

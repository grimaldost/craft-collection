"""Tests for claude_runner.parse_stream. Runnable with pytest or `python test_parse_stream.py`."""

from __future__ import annotations

import json

from claude_runner import parse_stream

LINES = [
    json.dumps({'type': 'system', 'subtype': 'init',
                'plugins': [{'name': 'session-workflow'}], 'plugin_errors': []}),
    json.dumps({'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Skill',
         'input': {'name': 'session-workflow:journaling-sessions'}}]}}),
    json.dumps({'type': 'result', 'result': 'done',
                'total_cost_usd': 0.01, 'num_turns': 2, 'is_error': False}),
]


def test_parses_activation_and_result():
    run = parse_stream(LINES)
    assert 'journaling-sessions' in ' '.join(run.activated_skills)
    assert run.plugin_loaded('session-workflow') and not run.plugin_errors
    assert run.cost_usd == 0.01 and run.num_turns == 2 and run.is_error is False
    assert run.activated('journaling-sessions') is True


def test_tolerates_garbage_lines():
    run = parse_stream(['not json', '', *LINES])
    assert run.activated_skills


# A skill that writes its deliverable to a file + a mid-stream message, ending on a
# terse confirmation — the shape that floored journaling's measured usage.
WRITE_LINES = [
    json.dumps({'type': 'assistant', 'message': {'content': [
        {'type': 'text', 'text': 'Here are the entries.'},
        {'type': 'tool_use', 'name': 'Write',
         'input': {'file_path': 'j.md',
                   'content': '--- ENTRY_START ---\nbody\n--- ENTRY_END ---'}}]}}),
    json.dumps({'type': 'assistant', 'message': {'content': [
        {'type': 'text', 'text': 'Done, 1 entry written.'}]}}),
    json.dumps({'type': 'result', 'result': 'Done, 1 entry written.',
                'total_cost_usd': 0.02, 'num_turns': 3, 'usage': {'output_tokens': 50}}),
]


def test_captures_assistant_text_and_written_content():
    run = parse_stream(WRITE_LINES)
    # Mid-stream and final assistant text are both captured, not just result_text.
    assert 'Here are the entries.' in run.assistant_text
    assert 'Done, 1 entry written.' in run.assistant_text
    # The real deliverable (Write content) is captured even though it never appears
    # in result_text — this is the artifact-3 fix.
    assert 'ENTRY_START' in run.written_text
    assert run.usage.get('output_tokens') == 50


if __name__ == '__main__':
    test_parses_activation_and_result()
    test_tolerates_garbage_lines()
    test_captures_assistant_text_and_written_content()
    print('ok: all parse_stream tests passed')

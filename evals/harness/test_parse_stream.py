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


if __name__ == '__main__':
    test_parses_activation_and_result()
    test_tolerates_garbage_lines()
    print('ok: all parse_stream tests passed')

"""Tests for run_agent's timeout handling: the stream captured before the kill
must still be parsed, so a pre-timeout Skill activation counts instead of
silently reading as a trigger miss. Runnable with pytest or
`python test_timeout_partial.py`."""

from __future__ import annotations

import json
import subprocess

import claude_runner
from claude_runner import run_agent

_PARTIAL_STREAM = (
    json.dumps(
        {
            'type': 'assistant',
            'message': {
                'content': [
                    {
                        'type': 'tool_use',
                        'name': 'Skill',
                        'input': {'skill': 'session-workflow:tool-feedback'},
                    }
                ]
            },
        }
    )
    + '\n'
)


def _raise_timeout(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd=['claude'], timeout=300, output=_PARTIAL_STREAM)


def _raise_timeout_no_output(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd=['claude'], timeout=300)


def test_partial_stream_keeps_activation():
    original = claude_runner.subprocess.run
    claude_runner.subprocess.run = _raise_timeout
    try:
        run = run_agent('q', allowed_tools='Skill', stream=True)
    finally:
        claude_runner.subprocess.run = original
    assert run.is_error  # a timeout is still an error run
    assert run.activated('tool-feedback'), run.activated_skills
    assert 'TIMEOUT' in run.result_text


def test_timeout_without_output_is_plain_error():
    original = claude_runner.subprocess.run
    claude_runner.subprocess.run = _raise_timeout_no_output
    try:
        run = run_agent('q', allowed_tools='Skill', stream=True)
    finally:
        claude_runner.subprocess.run = original
    assert run.is_error
    assert not run.activated_skills
    assert 'TIMEOUT' in run.result_text


if __name__ == '__main__':
    test_partial_stream_keeps_activation()
    test_timeout_without_output_is_plain_error()
    print('ok: all timeout_partial tests passed')

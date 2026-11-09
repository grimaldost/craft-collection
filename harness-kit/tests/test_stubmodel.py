#!/usr/bin/env python3
"""Checks of `kit stub`: the scripted local model server.

Contract under test:
- the first stdout line is `{"port": N}` and the server answers on 127.0.0.1;
- the Anthropic and chat wires, streaming and not, answer a scripted tool call and then text;
- only a request that offers tools consumes a step; one without tools gets `stub-aux`;
- every request appends one JSON line to the log; the log file exists only after a first request;
- CONNECT and absolute-URL requests are refused with 403 and logged;
- a key other than the literal fake one is flagged in `auth`.

Stdlib-runnable: `python test_stubmodel.py`.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / 'src'
FAKE = 'stub-not-a-key'

TOOL_STEP = {'tool': 'Bash', 'args': {'command': 'echo hi'}}
TEXT_STEP = {'text': 'all done'}
TOOLS = [{'name': 'Bash'}]
AUTH = {'x-api-key': FAKE, 'content-type': 'application/json'}


@contextmanager
def stub(script, extra=()):
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        script_path = base / 'script.json'
        script_path.write_text(json.dumps(script), encoding='utf-8')
        log = base / 'out' / 'requests.jsonl'
        env = {**os.environ, 'PYTHONPATH': str(SRC)}
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                '-m',
                'harness_kit',
                'stub',
                '--log',
                str(log),
                '--script',
                str(script_path),
                *extra,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            env=env,
        )
        try:
            first = proc.stdout.readline()
            port = json.loads(first)['port']
            yield port, log
        finally:
            proc.kill()
            proc.communicate()


def call(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
    try:
        data = None if body is None else json.dumps(body)
        conn.request(method, path, body=data, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, resp.read().decode('utf-8')
    finally:
        conn.close()


def rows(log):
    if not log.exists():
        return []
    return [
        json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()
    ]


def sse(text):
    events = []
    for block in text.split('\n\n'):
        data = [ln[5:].strip() for ln in block.splitlines() if ln.startswith('data:')]
        if data and data[0] != '[DONE]':
            events.append(json.loads(data[0]))
    return events


@contextmanager
def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        number = s.getsockname()[1]
    yield number


def test_first_stdout_line_is_the_port():
    with stub([]) as (port, _log):
        assert isinstance(port, int) and port > 0


def test_anthropic_plain_tool_call_then_text():
    with stub([TOOL_STEP, TEXT_STEP]) as (port, _log):
        body = {'model': 'm', 'tools': TOOLS, 'messages': []}
        status, raw = call(port, 'POST', '/v1/messages', body, AUTH)
        assert status == 200, raw
        block = json.loads(raw)['content'][0]
        assert block['type'] == 'tool_use' and block['name'] == 'Bash', block
        assert block['input'] == {'command': 'echo hi'}, block
        status, raw = call(port, 'POST', '/v1/messages', body, AUTH)
        block = json.loads(raw)['content'][0]
        assert block == {'type': 'text', 'text': 'all done'}, block
        status, raw = call(port, 'POST', '/messages', body, AUTH)
        assert json.loads(raw)['content'][0]['text'] == 'stub-final', raw


def test_anthropic_streaming_tool_call_then_text():
    with stub([TOOL_STEP, TEXT_STEP]) as (port, _log):
        body = {'model': 'm', 'tools': TOOLS, 'stream': True, 'messages': []}
        status, raw = call(port, 'POST', '/v1/messages', body, AUTH)
        assert status == 200, raw
        events = sse(raw)
        start = next(e for e in events if e['type'] == 'content_block_start')
        assert start['content_block']['type'] == 'tool_use', start
        assert start['content_block']['name'] == 'Bash', start
        delta = next(e for e in events if e['type'] == 'content_block_delta')
        assert json.loads(delta['delta']['partial_json']) == {'command': 'echo hi'}, delta
        assert events[-1]['type'] == 'message_stop', events[-1]
        status, raw = call(port, 'POST', '/v1/messages', body, AUTH)
        delta = next(e for e in sse(raw) if e['type'] == 'content_block_delta')
        assert delta['delta'] == {'type': 'text_delta', 'text': 'all done'}, delta


def test_chat_plain_tool_call_then_text():
    with stub([TOOL_STEP, TEXT_STEP]) as (port, _log):
        body = {'model': 'm', 'tools': TOOLS, 'messages': []}
        status, raw = call(port, 'POST', '/v1/chat/completions', body, AUTH)
        assert status == 200, raw
        choice = json.loads(raw)['choices'][0]
        tool_call = choice['message']['tool_calls'][0]
        assert choice['finish_reason'] == 'tool_calls', choice
        assert tool_call['function']['name'] == 'Bash', tool_call
        assert json.loads(tool_call['function']['arguments']) == {'command': 'echo hi'}, tool_call
        status, raw = call(port, 'POST', '/chat/completions', body, AUTH)
        choice = json.loads(raw)['choices'][0]
        assert choice['message']['content'] == 'all done', choice
        assert choice['finish_reason'] == 'stop', choice


def test_chat_streaming_tool_call_then_text():
    with stub([TOOL_STEP, TEXT_STEP]) as (port, _log):
        body = {'model': 'm', 'tools': TOOLS, 'stream': True, 'messages': []}
        status, raw = call(port, 'POST', '/v1/chat/completions', body, AUTH)
        assert status == 200, raw
        assert raw.rstrip().endswith('data: [DONE]'), raw[-40:]
        chunks = sse(raw)
        tool_call = chunks[0]['choices'][0]['delta']['tool_calls'][0]
        assert tool_call['function']['name'] == 'Bash', tool_call
        assert json.loads(tool_call['function']['arguments']) == {'command': 'echo hi'}, tool_call
        status, raw = call(port, 'POST', '/v1/chat/completions', body, AUTH)
        assert sse(raw)[0]['choices'][0]['delta']['content'] == 'all done', raw


def test_requests_without_tools_get_aux_text_and_consume_nothing():
    with stub([TOOL_STEP]) as (port, log):
        plain = {'model': 'm', 'messages': []}
        for path in ('/v1/messages', '/v1/chat/completions'):
            status, raw = call(port, 'POST', path, plain, AUTH)
            assert status == 200, raw
            assert 'stub-aux' in raw, raw
        status, raw = call(port, 'POST', '/v1/messages', {**plain, 'tools': TOOLS}, AUTH)
        assert json.loads(raw)['content'][0]['name'] == 'Bash', raw
        posts = [r for r in rows(log) if r['kind'] == 'POST']
        assert [r['decision'] for r in posts] == ['aux-no-tools', 'aux-no-tools', 'scripted'], posts
        assert posts[2]['step_index'] == 0, posts[2]


def test_log_has_one_line_per_request_with_the_named_keys():
    with stub([TOOL_STEP]) as (port, log):
        assert not log.exists()
        body = {'model': 'm', 'tools': TOOLS, 'messages': []}
        call(port, 'POST', '/v1/messages', body, AUTH)
        call(port, 'POST', '/v1/chat/completions', body, AUTH)
        call(port, 'GET', '/v1/models', None, AUTH)
        call(port, 'GET', '/models', None, AUTH)
        call(port, 'POST', '/v1/messages/count_tokens', body, AUTH)
        call(port, 'GET', '/nowhere', None, AUTH)
        call(port, 'POST', '/nowhere', body, AUTH)
        lines = rows(log)
        assert len(lines) == 7, lines
        assert [r['n'] for r in lines] == [1, 2, 3, 4, 5, 6, 7], lines
        for r in lines:
            assert {'kind', 'n', 't', 'path', 'auth'} <= set(r), r
        first = lines[0]
        assert first['wire'] == 'anthropic' and first['decision'] == 'scripted', first
        assert first['step_index'] == 0 and first['body']['model'] == 'm', first
        assert lines[1]['wire'] == 'chat', lines[1]
        assert lines[1]['step_index'] == 1, lines[1]
        assert lines[2]['kind'] == 'GET' and lines[2]['path'] == '/v1/models', lines[2]


def test_models_listing_and_token_count():
    with stub([]) as (port, _log):
        for path in ('/v1/models', '/models'):
            status, raw = call(port, 'GET', path, None, AUTH)
            assert status == 200, raw
            assert json.loads(raw)['data'], raw
        status, raw = call(port, 'POST', '/v1/messages/count_tokens', {'messages': []}, AUTH)
        assert status == 200 and 'input_tokens' in json.loads(raw), raw


def test_connect_and_absolute_urls_get_403_and_are_logged():
    with stub([]) as (port, log):
        status, _ = call(port, 'CONNECT', 'example.com:443')
        assert status == 403, status
        status, _ = call(port, 'GET', 'http://example.com/v1/models')
        assert status == 403, status
        status, _ = call(port, 'POST', 'http://example.com/v1/messages', {'model': 'm'})
        assert status == 403, status
        lines = rows(log)
        assert len(lines) == 3, lines
        assert lines[0]['kind'] == 'CONNECT-refused', lines[0]
        assert lines[0]['path'] == 'example.com:443', lines[0]
        assert lines[1]['kind'] == 'PROXY-GET-refused', lines[1]
        assert lines[2]['kind'] == 'PROXY-POST-refused', lines[2]
        assert all('auth' in r for r in lines), lines


def test_any_other_method_is_logged():
    with stub([]) as (port, log):
        status, _ = call(port, 'DELETE', '/v1/models/x')
        assert status == 404, status
        lines = rows(log)
        assert len(lines) == 1 and lines[0]['kind'] == 'DELETE', lines


def test_a_method_the_stub_does_not_serve_is_still_logged():
    with stub([]) as (port, log):
        status, _ = call(port, 'TRACE', '/v1/models')
        assert status == 404, status
        status, _ = call(port, 'PROPFIND', '/anything')
        assert status == 404, status
        assert [r['kind'] for r in rows(log)] == ['TRACE', 'PROPFIND'], rows(log)


def test_a_malformed_request_is_logged_and_the_stub_keeps_serving():
    with stub([]) as (port, log):
        with socket.create_connection(('127.0.0.1', port), timeout=30) as conn:
            conn.sendall(b'this is not http\r\n\r\n')
            conn.recv(4096)
        assert len(rows(log)) == 1, rows(log)
        status, _ = call(port, 'GET', '/v1/models', None, AUTH)
        assert status == 200, status
        assert len(rows(log)) == 2, rows(log)


def test_a_body_that_cannot_be_decoded_is_logged():
    with stub([TOOL_STEP]) as (port, log):
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
        conn.request(
            'POST', '/v1/messages', body=b'not gzip', headers={**AUTH, 'Content-Encoding': 'gzip'}
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        lines = rows(log)
        assert len(lines) == 1 and lines[0]['kind'] == 'POST', lines
        assert lines[0]['decision'] == 'aux-no-tools', lines


def test_a_foreign_key_is_flagged_and_the_fake_one_is_not():
    with stub([]) as (port, log):
        call(port, 'GET', '/v1/models', None, {'x-api-key': FAKE})
        call(port, 'GET', '/v1/models', None, {'Authorization': f'Bearer {FAKE}'})
        call(port, 'GET', '/v1/models', None, {'x-api-key': 'sk-real-looking'})
        call(port, 'GET', '/v1/models', None, {'Authorization': 'Bearer sk-other'})
        call(port, 'GET', '/v1/models')
        lines = rows(log)
        assert 'NOT-THE-FAKE-KEY' not in json.dumps(lines[0]['auth']), lines[0]
        assert 'NOT-THE-FAKE-KEY' not in json.dumps(lines[1]['auth']), lines[1]
        assert 'NOT-THE-FAKE-KEY' in json.dumps(lines[2]['auth']), lines[2]
        assert 'NOT-THE-FAKE-KEY' in json.dumps(lines[3]['auth']), lines[3]
        assert 'NOT-THE-FAKE-KEY' not in json.dumps(lines[4]['auth']), lines[4]
        for r in lines:
            assert 'sk-real-looking' not in json.dumps(r), r
            assert 'sk-other' not in json.dumps(r), r


def test_a_stub_that_receives_nothing_leaves_no_log_file():
    with stub([TOOL_STEP]) as (_port, log):
        assert not log.exists()
        assert not log.parent.exists()


def test_a_fixed_port_is_honoured():
    with free_port() as wanted, stub([], ('--port', str(wanted))) as (port, _log):
        assert port == wanted, (port, wanted)


def test_an_invalid_script_exits_non_zero_before_serving():
    env = {**os.environ, 'PYTHONPATH': str(SRC)}
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / 'script.json'
        for bad in ('not json', '{"tool": "x"}', '[{"tool": "x"}]', '[{"nothing": 1}]', '[3]'):
            script.write_text(bad, encoding='utf-8')
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [
                    sys.executable,
                    '-m',
                    'harness_kit',
                    'stub',
                    '--log',
                    str(Path(td) / 'l'),
                    '--script',
                    str(script),
                ],
                capture_output=True,
                text=True,
                encoding='utf-8',
                env=env,
                timeout=60,
            )
            assert proc.returncode != 0, bad
            assert proc.stdout == '', (bad, proc.stdout)
            assert proc.stderr.strip(), bad


def test_output_is_ascii_for_non_ascii_script_text():
    with stub([{'text': 'caf\u00e9'}]) as (port, log):
        body = {'model': 'm', 'tools': TOOLS, 'messages': []}
        _, raw = call(port, 'POST', '/v1/messages', body, AUTH)
        assert raw.isascii(), raw
        assert json.loads(raw)['content'][0]['text'] == 'caf\u00e9', raw
        assert log.read_bytes().isascii()


if __name__ == '__main__':
    test_first_stdout_line_is_the_port()
    test_anthropic_plain_tool_call_then_text()
    test_anthropic_streaming_tool_call_then_text()
    test_chat_plain_tool_call_then_text()
    test_chat_streaming_tool_call_then_text()
    test_requests_without_tools_get_aux_text_and_consume_nothing()
    test_log_has_one_line_per_request_with_the_named_keys()
    test_models_listing_and_token_count()
    test_connect_and_absolute_urls_get_403_and_are_logged()
    test_any_other_method_is_logged()
    test_a_method_the_stub_does_not_serve_is_still_logged()
    test_a_malformed_request_is_logged_and_the_stub_keeps_serving()
    test_a_body_that_cannot_be_decoded_is_logged()
    test_a_foreign_key_is_flagged_and_the_fake_one_is_not()
    test_a_stub_that_receives_nothing_leaves_no_log_file()
    test_a_fixed_port_is_honoured()
    test_an_invalid_script_exits_non_zero_before_serving()
    test_output_is_ascii_for_non_ascii_script_text()
    print('ok: stub model')

"""Scripted local model server for tests: `kit stub --log FILE --script FILE [--port N]`.

A script is a JSON array of steps, `{"tool": NAME, "args": {...}}` or `{"text": STRING}`. A model request that
offers tools consumes the next step, then `{"text": "stub-final"}` once the script ends; a model request with no
tools gets `stub-aux` and consumes nothing. Every request of any kind appends one JSON line to the log, and the
log file is created by the first request, so a stub that receives nothing leaves no file.
"""

from __future__ import annotations

import gzip
import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path
from typing import Any

FAKE_KEY = 'stub-not-a-key'
FOREIGN_KEY = 'NOT-THE-FAKE-KEY'
FINAL_STEP = {'text': 'stub-final'}
AUX_STEP = {'text': 'stub-aux'}

WIRES = {
    '/v1/chat/completions': 'chat',
    '/chat/completions': 'chat',
    '/v1/messages': 'anthropic',
    '/messages': 'anthropic',
}
NOT_FOUND = {'error': {'message': 'stub: no such path', 'type': 'not_found'}}


def _dump(value: Any) -> str:
    return json.dumps(value)


def chat_payload(step: dict, model: str, stream: bool) -> tuple[str, str]:
    base = {'id': 'chatcmpl-stub', 'created': int(time.time()), 'model': model}
    usage = {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}
    if 'tool' in step:
        call = {
            'index': 0,
            'id': step.get('id', 'call_stub'),
            'type': 'function',
            'function': {'name': step['tool'], 'arguments': _dump(step['args'])},
        }
        delta: dict = {'role': 'assistant', 'content': None, 'tool_calls': [call]}
        finish = 'tool_calls'
    else:
        delta = {'role': 'assistant', 'content': step.get('text', 'stub-final')}
        finish = 'stop'
    if not stream:
        body = {
            **base,
            'object': 'chat.completion',
            'usage': usage,
            'choices': [{'index': 0, 'message': delta, 'finish_reason': finish}],
        }
        return _dump(body), 'application/json'
    chunk = {**base, 'object': 'chat.completion.chunk'}
    chunks = [
        {**chunk, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
        {**chunk, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
        {**chunk, 'choices': [], 'usage': usage},
    ]
    text = ''.join(f'data: {_dump(c)}\n\n' for c in chunks) + 'data: [DONE]\n\n'
    return text, 'text/event-stream'


def anthropic_payload(step: dict, n: int, model: str, stream: bool) -> tuple[str, str]:
    usage = {
        'input_tokens': 1,
        'output_tokens': 1,
        'cache_creation_input_tokens': 0,
        'cache_read_input_tokens': 0,
    }
    if 'tool' in step:
        block: dict = {
            'type': 'tool_use',
            'id': step.get('id', f'toolu_stub{n}'),
            'name': step['tool'],
            'input': {},
        }
        delta = {'type': 'input_json_delta', 'partial_json': _dump(step['args'])}
        stop = 'tool_use'
    else:
        block = {'type': 'text', 'text': ''}
        delta = {'type': 'text_delta', 'text': step.get('text', 'stub-final')}
        stop = 'end_turn'
    message = {'id': f'msg_stub{n}', 'type': 'message', 'role': 'assistant', 'model': model}
    if not stream:
        full = dict(block)
        if 'tool' in step:
            full['input'] = step['args']
        else:
            full['text'] = step.get('text', 'stub-final')
        body = {
            **message,
            'content': [full],
            'stop_reason': stop,
            'stop_sequence': None,
            'usage': usage,
        }
        return _dump(body), 'application/json'
    events = [
        (
            'message_start',
            {
                'type': 'message_start',
                'message': {
                    **message,
                    'content': [],
                    'stop_reason': None,
                    'stop_sequence': None,
                    'usage': usage,
                },
            },
        ),
        (
            'content_block_start',
            {'type': 'content_block_start', 'index': 0, 'content_block': block},
        ),
        ('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': delta}),
        ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
        (
            'message_delta',
            {
                'type': 'message_delta',
                'delta': {'stop_reason': stop, 'stop_sequence': None},
                'usage': {'output_tokens': 1},
            },
        ),
        ('message_stop', {'type': 'message_stop'}),
    ]
    return ''.join(f'event: {k}\ndata: {_dump(v)}\n\n' for k, v in events), 'text/event-stream'


def has_tools(body: Any) -> bool:
    return isinstance(body, dict) and bool(body.get('tools'))


class Stub(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    request_queue_size = 256  # the library default of 5 refuses a burst of concurrent clients

    def __init__(self, log_path: Path, script: list[dict], port: int = 0) -> None:
        super().__init__(('127.0.0.1', port), Handler)
        self.port = self.server_address[1]
        self.log_path = Path(log_path)
        self.script = list(script)
        self.pos = 0
        self.lock = threading.Lock()
        self.n = 0

    def next_step(self) -> tuple[int, dict]:
        with self.lock:
            index = self.pos
            self.pos += 1
            return index, (self.script[index] if index < len(self.script) else FINAL_STEP)

    def record(self, rec: dict) -> int:
        with self.lock:
            self.n += 1
            rec['n'] = self.n
            rec['t'] = round(time.time(), 3)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'a', encoding='utf-8') as fh:
                fh.write(_dump(rec) + '\n')
            return self.n


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server: Stub

    def log_message(self, *args: Any) -> None:
        pass

    def auth_class(self) -> list[str]:
        classes = []
        for name in ('Authorization', 'x-api-key', 'api-key'):
            value = self.headers.get(name)
            if value is None:
                continue
            ok = value in (f'Bearer {FAKE_KEY}', FAKE_KEY)
            classes.append(f'{name}:{"fake" if ok else FOREIGN_KEY}')
        return classes or ['none']

    def reply(self, code: int, data: str | bytes, ctype: str = 'application/json') -> None:
        raw = data.encode('utf-8') if isinstance(data, str) else data
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def read_body(self) -> bytes:
        if (self.headers.get('Transfer-Encoding') or '').lower() == 'chunked':
            parts = []
            while True:
                size = int(self.rfile.readline().strip() or b'0', 16)
                if size == 0:
                    self.rfile.readline()
                    break
                parts.append(self.rfile.read(size))
                self.rfile.readline()
            raw = b''.join(parts)
        else:
            raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        if (self.headers.get('Content-Encoding') or '').lower() == 'gzip':
            try:
                raw = gzip.decompress(raw)
            except (OSError, EOFError):
                pass  # logged as an unparsed body below
        return raw

    def refuse(self, kind: str) -> None:
        self.server.record({'kind': kind, 'path': self.path, 'auth': self.auth_class()})
        self.reply(403, 'refused by stub\n', 'text/plain')

    def do_CONNECT(self) -> None:
        self.refuse('CONNECT-refused')

    def handle_other(self) -> None:
        """Any method the stub does not serve: read the body, log, refuse or answer 404."""
        self.read_body()
        if self.path.startswith('http'):
            return self.refuse(f'PROXY-{self.command}-refused')
        self.server.record({'kind': self.command, 'path': self.path, 'auth': self.auth_class()})
        self.reply(404, _dump(NOT_FOUND))

    def __getattr__(self, name: str) -> Any:
        # http.server answers an unknown verb with 501 before any handler runs; every verb is handled here instead.
        if name.startswith('do_'):
            return self.handle_other
        raise AttributeError(name)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """A request the server library rejects (a malformed line, an oversized header) is logged too."""
        auth = self.auth_class() if hasattr(self, 'headers') else ['none']
        self.server.record(
            {'kind': f'ERROR-{code}', 'path': getattr(self, 'path', ''), 'auth': auth}
        )
        super().send_error(code, message, explain)

    def do_HEAD(self) -> None:
        if self.path.startswith('http'):
            return self.refuse('PROXY-HEAD-refused')
        self.server.record({'kind': 'HEAD', 'path': self.path, 'auth': self.auth_class()})
        self.reply(200, b'')

    def do_GET(self) -> None:
        if self.path.startswith('http'):
            return self.refuse('PROXY-GET-refused')
        self.server.record({'kind': 'GET', 'path': self.path, 'auth': self.auth_class()})
        route = self.path.split('?', 1)[0]
        if route in ('/v1/models', '/models'):
            models = [{'id': 'stub-model', 'object': 'model'}]
            return self.reply(200, _dump({'object': 'list', 'models': [], 'data': models}))
        self.reply(404, _dump(NOT_FOUND))

    def do_POST(self) -> None:
        raw = self.read_body()
        if self.path.startswith('http'):
            return self.refuse('PROXY-POST-refused')
        path = self.path.split('?', 1)[0]
        try:
            body = json.loads(raw.decode('utf-8'))
        except ValueError:
            body = {'_unparsed_bytes': len(raw)}
        if not isinstance(body, dict):
            body = {'_not_an_object': True}
        rec = {
            'kind': 'POST',
            'path': self.path,
            'auth': self.auth_class(),
            'stream': bool(body.get('stream')),
        }
        if path.endswith('/messages/count_tokens'):
            self.server.record({**rec, 'wire': 'anthropic-count'})
            return self.reply(200, _dump({'input_tokens': 1}))
        wire = WIRES.get(path)
        if wire is None:
            self.server.record({**rec, 'wire': None, 'body': body})
            return self.reply(404, _dump(NOT_FOUND))
        if has_tools(body):
            index, step = self.server.next_step()
            rec.update({'decision': 'scripted', 'step_index': index, 'step': step})
        else:
            step = AUX_STEP
            rec.update({'decision': 'aux-no-tools', 'step': step})
        rec.update({'wire': wire, 'body': body})
        n = self.server.record(rec)
        model = body.get('model', 'stub-model')
        stream = bool(body.get('stream'))
        if wire == 'chat':
            data, ctype = chat_payload(step, model, stream)
        else:
            data, ctype = anthropic_payload(step, n, model, stream)
        self.reply(200, data, ctype)


def load_script(path: str) -> list[dict]:
    """Read a script file; raise ValueError naming the first thing wrong."""
    try:
        steps = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'cannot read script {path}: {exc}') from exc
    if not isinstance(steps, list):
        raise ValueError('script must be a JSON array of steps')
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f'step {i} is not an object')
        if 'tool' in step:
            if not isinstance(step['tool'], str) or not isinstance(step.get('args'), dict):
                raise ValueError(f'step {i} needs a string tool and an object args')
        elif not isinstance(step.get('text'), str):
            raise ValueError(f'step {i} needs a tool with args, or a string text')
    return steps


def run(log: str, script: str, port: int = 0) -> int:
    """Serve until killed; the first stdout line is `{"port": N}`."""
    try:
        steps = load_script(script)
    except ValueError as exc:
        print(f'kit stub: {exc}', file=sys.stderr)
        return 64
    try:
        server = Stub(Path(log), steps, port)
    except OSError as exc:
        print(f'kit stub: cannot bind 127.0.0.1:{port}: {exc}', file=sys.stderr)
        return 1
    print(_dump({'port': server.port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

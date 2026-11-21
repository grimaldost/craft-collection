#!/usr/bin/env python3
"""Checks of the relay: `kit relay serve` and `kit relay summary`.

Contract under test:
- the relay reads `{"key": KEY, "capability": CAP}` from its first line of standard input, takes
  the state root's relay lock, replays the ledger, binds 127.0.0.1 and prints
  `{"relay": 1, "port": N, "pid": P}`; a malformed line, a held lock or a refused daily file
  exits 3 and echoes no value;
- a forwarded request reaches the upstream with `Authorization: Bearer KEY` and no other incoming
  header, the model unchanged, the configured `provider` and `usage`, the output limit capped,
  and the upstream finds the request's `reserve` line in the ledger on arrival; whole and
  streamed answers reach the client byte for byte; other statuses pass with the relay's body;
- settlement takes the larger of the reported cost and the priced usage, else the reservation;
- each refusal of the surface answers its status and reason without contacting the upstream,
  and is logged; after `key_in_request` every request is refused `stopped`;
- each ceiling refuses with its reason; a restarted relay replays the totals, and settles a
  reservation a killed relay left open, which `kit relay summary --json` then counts;
- the key, the capability, a request's body and its header values reach no file under the state
  root and no standard output or error; a request whose handling raises writes only the fixed
  line to standard error;
- end of standard input stops the relay, settling what is still open at its reservation.

Every daily file here has `test = true` and an upstream that this file runs on 127.0.0.1, but
for the refusals that need another value, which keep the state root under the temporary
folder. The key is a made-up value.

Stdlib-runnable: `python test_relay.py`.
"""

from __future__ import annotations

import gzip
import http.client
import http.server
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import cli, daily, relay
from kit_fixtures import SRC, run_module

KEY = 'made-up-provider-key-7d41c0e2'
CAP = '0123456789abcdef' * 4
RUN = '20261118T120000Z-0123456789ab'
PLANT_BODY = 'planted-body-text-4f1c88'
PLANT_HEADER = 'planted-header-value-9a2e17'
PATH = '/v1/chat/completions'
MODEL = 'vendor/model-a'
# The numbers below are an example; they make a reservation of 2 USD per million body bytes plus
# 1000 tokens at 8 USD per million.
SETTINGS = {
    'route': '/api/v1/chat/completions',
    'key_env': 'TEST_PROVIDER_KEY',
    'test': True,
    'usage_include': True,
    'default_model': MODEL,
    'upstream_timeout_s': 30,
    'provider': {'order': ['vendor'], 'allow_fallbacks': False, 'data_collection': 'deny'},
    'ceilings': {'run_usd': 5.0, 'day_usd': 50.0, 'month_usd': 500.0},
    'model': [
        {
            'id': MODEL,
            'input_usd_per_mtok': 2.0,
            'output_usd_per_mtok': 8.0,
            'max_output_tokens': 1000,
        }
    ],
}
FIXED = 'kit relay: request failed'
# Every session's folder, removed when the module ends.
SCRATCH = Path(tempfile.mkdtemp(prefix='kit-relay-test-'))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    return '[' + ', '.join(_toml(v) for v in value) + ']'


def daily_text(table: dict) -> str:
    """A daily file holding `table` as its `[relay]` table."""
    lines = ['daily = 1', '', '[relay]']
    for key, value in table.items():
        if key not in ('provider', 'ceilings', 'model'):
            lines.append(f'{key} = {_toml(value)}')
    for name in ('provider', 'ceilings'):
        if name in table:
            lines += ['', f'[relay.{name}]']
            lines += [f'{k} = {_toml(v)}' for k, v in table[name].items()]
    for model in table['model']:
        lines += ['', '[[relay.model]]'] + [f'{k} = {_toml(v)}' for k, v in model.items()]
    lines += ['', '[git]', 'name = "Test Person"', 'email = "test@example.invalid"', '']
    return '\n'.join(lines)


def chat_body(**over: object) -> dict:
    body = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': PLANT_BODY}],
        'max_tokens': 999999,
        'provider': {'order': ['someone-else']},
    }
    body.update(over)
    return {k: v for k, v in body.items() if v is not ...}


def reservation(nbytes: int) -> float:
    return nbytes * 2.0 / 1e6 + 1000 * 8.0 / 1e6


# ---- the stub upstream, in this process


class Upstream(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def __init__(self, ledger: Path) -> None:
        super().__init__(('127.0.0.1', 0), UpstreamHandler)
        self.port = self.server_address[1]
        self.ledger = ledger
        self.seen: list[dict] = []
        self.answer = whole(json.dumps({'id': 'x', 'usage': {}}).encode())
        self.release = threading.Event()
        self.arrived = threading.Event()

    def handle_error(self, request, client_address) -> None:
        pass  # a client the test ended on purpose


class UpstreamHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server: Upstream

    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        ledger = self.server.ledger
        lines = ledger.read_text(encoding='utf-8').splitlines() if ledger.is_file() else []
        self.server.seen.append(
            {
                'path': self.path,
                'headers': [(k.lower(), v) for k, v in self.headers.items()],
                'body': json.loads(body),
                'size': len(body),
                'ledger': [json.loads(x) for x in lines if x.strip()],
            }
        )
        self.server.arrived.set()
        self.server.answer(self)


def whole(data: bytes, status: int = 200, ctype: str = 'application/json', extra=()):
    def answer(h: UpstreamHandler) -> None:
        h.send_response(status)
        h.send_header('Content-Type', ctype)
        h.send_header('Content-Length', str(len(data)))
        for name, value in extra:
            h.send_header(name, value)
        h.end_headers()
        h.wfile.write(data)

    return answer


def stream(chunks: list[bytes], hold_after: int | None = None):
    def answer(h: UpstreamHandler) -> None:
        h.send_response(200)
        h.send_header('Content-Type', 'text/event-stream')
        h.send_header('Transfer-Encoding', 'chunked')
        h.end_headers()
        for i, chunk in enumerate(chunks):
            h.wfile.write(b'%x\r\n%s\r\n' % (len(chunk), chunk))
            h.wfile.flush()
            if hold_after is not None and i == hold_after:
                h.server.release.wait(30)
        h.wfile.write(b'0\r\n\r\n')

    return answer


def hold_then(answer):
    def held(h: UpstreamHandler) -> None:
        h.server.release.wait(30)
        answer(h)

    return held


def drop(h: UpstreamHandler) -> None:
    h.close_connection = True


def sse(usage: dict | None) -> list[bytes]:
    chunks = [
        b'data: {"choices": [{"delta": {"content": "hel"}}]}\n\n',
        b'data: {"choices": [{"delta": {"content": "lo"}}]}\n',
        b'\n',
    ]
    if usage is not None:
        chunks.append(b'data: ' + json.dumps({'choices': [], 'usage': usage}).encode() + b'\n\n')
    return [*chunks, b'data: [DONE]\n\n']


# ---- the relay, a child process


def child_env(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('KIT_')}
    env['PYTHONPATH'] = str(SRC)
    env['KIT_STATE_ROOT'] = str(root)
    return env


class Relay:
    """One `kit relay serve` child; `ready` is its ready line, or None."""

    def __init__(self, base: Path, table: dict, *, run_id: str = RUN, line: bytes | None = None):
        self.base, self.root = base, base / 'state'
        self.port = table['listen_port']
        config = base / f'daily-{self.port}.toml'
        config.write_text(daily_text(table), encoding='utf-8')
        first = json.dumps({'key': KEY, 'capability': CAP}).encode() + b'\n'
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                '-m',
                'harness_kit',
                'relay',
                'serve',
                '--config',
                str(config),
                '--state-root',
                str(self.root),
                '--run-id',
                run_id,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env(self.root),
        )
        try:
            self.proc.stdin.write(first if line is None else line)
            self.proc.stdin.flush()
        except OSError:
            pass
        text = self.proc.stdout.readline()
        self.ready = json.loads(text) if text.strip() else None
        self.out, self.err, self.code = text, b'', None

    def close(self, timeout: float = 40) -> int:
        if self.code is None:
            try:
                out, err = self.proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                out, err = self.proc.communicate()
                raise AssertionError('the relay did not stop at end of standard input') from None
            self.out += out
            self.err += err
            self.code = self.proc.returncode
        return self.code

    def kill(self) -> None:
        self.proc.kill()
        out, err = self.proc.communicate()
        self.out, self.err, self.code = self.out + out, self.err + err, self.proc.returncode


@contextmanager
def session(answer=None, **over: object):
    """A stub upstream and a relay forwarding to it; yields (relay, upstream).

    The relay's folder outlives the block, so its files can be read after the relay stopped.
    """
    base = Path(tempfile.mkdtemp(dir=SCRATCH))
    upstream = Upstream(base / 'state' / 'relay' / 'ledger.ndjson')
    if answer is not None:
        upstream.answer = answer
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    table = settings(upstream.port, **over)
    child = Relay(base, table)
    try:
        assert child.ready is not None, child.close() or child.err
        yield child, upstream
    finally:
        upstream.release.set()
        child.close()
        upstream.shutdown()
        upstream.server_close()
        no_secret_anywhere(child)


def settings(upstream_port: int, **over: object) -> dict:
    table = json.loads(json.dumps(SETTINGS))
    table['listen_port'] = free_port()
    table['upstream_base'] = f'http://127.0.0.1:{upstream_port}'
    for dotted, value in over.items():
        node = table
        *parents, leaf = dotted.split('__')
        for key in parents:
            node = node[key]
        if value is ...:
            del node[leaf]
        else:
            node[leaf] = value
    return table


def no_secret_anywhere(child: Relay) -> None:
    planted = [x.encode() for x in (KEY, CAP, PLANT_BODY, PLANT_HEADER)]
    for path in child.root.rglob('*') if child.root.exists() else []:
        if path.is_file():
            data = path.read_bytes()
            for word in planted:
                assert word not in data, (path, word)
    for stream_bytes in (child.out, child.err):
        for word in planted:
            assert word not in stream_bytes, word


def post(port: int, body, *, cap: str | None = CAP, headers=None, path: str = PATH):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    sent = {'Content-Type': 'application/json'}
    if cap is not None:
        sent['Authorization'] = f'Bearer {cap}'
    sent.update(headers or {})
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
    try:
        conn.request('POST', path, body=data, headers=sent)
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
    finally:
        conn.close()


def raw(port: int, data: bytes) -> bytes:
    with socket.create_connection(('127.0.0.1', port), timeout=30) as s:
        s.sendall(data)
        got = b''
        while True:
            part = s.recv(65536)
            if not part:
                return got
            got += part


def error_body(status: int, reason: str) -> dict:
    message = f'kit relay: {reason}'
    return {'error': {'message': message, 'type': 'kit_relay', 'code': status}}


def log_lines(child: Relay, run_id: str = RUN) -> list[dict]:
    path = child.root / 'runs' / run_id / 'relay-log.ndjson'
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding='ascii').splitlines()]


def ledger_lines(root: Path) -> list[dict]:
    path = root / 'relay' / 'ledger.ndjson'
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding='ascii').splitlines() if x.strip()]


LOG_KEYS = {
    'ts_utc',
    'decision',
    'reason',
    'status',
    'model',
    'req_bytes',
    'resp_bytes',
    'prompt_tokens',
    'completion_tokens',
    'reserved_usd',
    'settled_usd',
    'settle_source',
    'proxy_host',
    'query_names',
    'duration_ms',
}
LEDGER_KEYS = {'ts_utc', 'kind', 'id', 'run_id', 'model', 'usd'}


def summary(root: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', 'relay', 'summary', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=child_env(root),
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---- the checks


def test_the_parser_has_relay_serve_and_summary():
    parser = cli.build_parser()
    args = parser.parse_args(
        ['relay', 'serve', '--config', 'f', '--state-root', 'r', '--run-id', 'i']
    )
    assert (args.command, args.relay_command) == ('relay', 'serve'), args
    assert (args.config, args.state_root, args.run_id) == ('f', 'r', 'i'), args
    args = parser.parse_args(['relay', 'summary', '--json'])
    assert (args.relay_command, args.json) == ('summary', True), args


def test_a_forwarded_request_reaches_the_upstream_rewritten_after_its_reservation():
    answer = json.dumps({'id': 'r1', 'choices': [], 'usage': {}}, indent=1).encode()
    with session(whole(answer)) as (child, upstream):
        assert child.ready['relay'] == 1 and child.ready['port'] == child.port, child.ready
        # The interpreter may run behind a launcher process, so the pid is not Popen's.
        pid = child.ready['pid']
        assert isinstance(pid, int) and pid > 0, child.ready
        line = b'{"relay": 1, "port": %d, "pid": %d}' % (child.port, pid)
        assert child.out.rstrip(b'\r\n') == line, child.out
        status, headers, body = post(
            child.port, chat_body(), headers={'X-Planted': PLANT_HEADER}, path=PATH + '?a=1&b=2'
        )
        assert (status, body) == (200, answer), (status, body)
        assert headers['content-type'] == 'application/json', headers
        [seen] = upstream.seen
        assert seen['path'] == '/api/v1/chat/completions', seen['path']
        sent = dict(seen['headers'])
        assert sent['authorization'] == f'Bearer {KEY}', sent
        assert sent['content-type'] == 'application/json', sent
        assert PLANT_HEADER not in json.dumps(seen['headers']), seen['headers']
        assert not [k for k in sent if k.startswith('x-')], sent
        got = seen['body']
        assert got['model'] == MODEL and got['messages'][0]['content'] == PLANT_BODY, got
        assert got['max_tokens'] == 1000, got
        assert got['provider'] == SETTINGS['provider'], got
        assert got['usage'] == {'include': True}, got
        [reserve] = seen['ledger']
        assert set(reserve) == LEDGER_KEYS and reserve['kind'] == 'reserve', reserve
        assert reserve['run_id'] == RUN and reserve['model'] == MODEL, reserve
        # The reservation prices the body's bytes as forwarded and its capped output limit.
        assert abs(reserve['usd'] - reservation(seen['size'])) < 1e-12, (reserve, seen['size'])
    reserve, settle = ledger_lines(child.root)
    assert settle['kind'] == 'settle' and settle['id'] == reserve['id'], settle
    assert set(settle) == LEDGER_KEYS, settle
    [line] = log_lines(child)
    assert set(line) == LOG_KEYS, line
    assert line['decision'] == 'forwarded' and line['status'] == 200, line
    assert line['model'] == MODEL and line['query_names'] == ['a', 'b'], line
    assert line['resp_bytes'] == len(answer) and line['proxy_host'] is None, line
    assert child.code == 0 and child.err == b'', (child.code, child.err)


def test_the_output_limit_is_set_when_absent_and_kept_when_smaller():
    with session(usage_include=False, provider=...) as (child, upstream):
        post(child.port, chat_body(max_tokens=..., provider=...))
        post(child.port, chat_body(max_tokens=..., max_completion_tokens=5000))
        post(child.port, chat_body(max_tokens=10))
    first, second, third = (s['body'] for s in upstream.seen)
    assert first['max_tokens'] == 1000 and 'provider' not in first and 'usage' not in first, first
    assert second['max_completion_tokens'] == 1000 and 'max_tokens' not in second, second
    assert third['max_tokens'] == 10, third


def test_the_reservation_prices_the_forwarded_body_and_its_output_limit():
    with session() as (child, upstream):
        post(child.port, chat_body(max_tokens=10))
        post(child.port, chat_body(max_tokens=..., max_completion_tokens=20))
    for seen, limit in zip(upstream.seen, (10, 20), strict=True):
        [reserve] = [x for x in seen['ledger'] if x['kind'] == 'reserve'][-1:]
        want = seen['size'] * 2.0 / 1e6 + limit * 8.0 / 1e6
        assert abs(reserve['usd'] - want) < 1e-12, (reserve, seen['size'], limit)
    assert [x['reserved_usd'] for x in log_lines(child)] == [
        x['usd'] for x in ledger_lines(child.root) if x['kind'] == 'reserve'
    ]


def test_a_streamed_answer_passes_byte_for_byte_and_settles_from_its_usage():
    chunks = sse({'prompt_tokens': 1000, 'completion_tokens': 1000, 'cost': 0.0001})
    with session(stream(chunks)) as (child, _upstream):
        status, headers, body = post(child.port, chat_body(stream=True))
        assert status == 200 and body == b''.join(chunks), body
        assert headers['content-type'] == 'text/event-stream', headers
    [line] = log_lines(child)
    assert (line['prompt_tokens'], line['completion_tokens']) == (1000, 1000), line
    assert line['settle_source'] == 'priced', line
    assert abs(line['settled_usd'] - (1000 * 2.0 + 1000 * 8.0) / 1e6) < 1e-12, line
    assert ledger_lines(child.root)[-1]['usd'] == line['settled_usd']


def test_settlement_takes_the_larger_of_reported_and_priced_else_the_reservation():
    cases = (
        ({'prompt_tokens': 100, 'completion_tokens': 50, 'cost': 0.5}, 'reported', 0.5),
        ({'cost': 0.25}, 'reported', 0.25),
        ({'prompt_tokens': 1000, 'completion_tokens': 0}, 'priced', 0.002),
        # Each readable count is priced on its own.
        ({'prompt_tokens': 1000}, 'priced', 0.002),
        ({'prompt_tokens': 'n/a', 'completion_tokens': 250, 'cost': 0.001}, 'priced', 0.002),
        ({}, 'reservation', None),
        (None, 'reservation', None),
    )
    for usage, source, usd in cases:
        doc = {'id': 'r', 'choices': []} if usage is None else {'id': 'r', 'usage': usage}
        with session(whole(json.dumps(doc).encode())) as (child, _upstream):
            post(child.port, chat_body())
        [line] = log_lines(child)
        assert line['settle_source'] == source, (usage, line)
        want = line['reserved_usd'] if usd is None else usd
        assert abs(line['settled_usd'] - want) < 1e-12, (usage, line)
        assert ledger_lines(child.root)[-1]['usd'] == line['settled_usd'], usage


def test_another_status_passes_with_the_relay_body_and_retry_after():
    answer = whole(
        b'upstream says ' + PLANT_BODY.encode(), 429, 'text/plain', [('Retry-After', '7')]
    )
    with session(answer) as (child, _upstream):
        status, headers, body = post(child.port, chat_body())
    assert status == 429 and headers.get('retry-after') == '7', (status, headers)
    assert json.loads(body) == error_body(429, 'upstream 429'), body
    [line] = log_lines(child)
    assert line['decision'] == 'forwarded' and line['settle_source'] == 'reservation', line


def padded(size: int) -> bytes:
    """A JSON object of exactly `size` bytes."""
    return b'{' + b' ' * (size - 2) + b'}'


def test_each_refusal_answers_its_status_and_reason_without_the_upstream():
    mib = 1024 * 1024
    cases = [
        # A client sends its whole body before it reads the answer, so a refusal reads it first.
        ({'body': padded(32 * mib + 1)}, 413, 'too_large'),
        ({'path': '/v1/models', 'body': padded(4 * mib)}, 404, 'not_forwarded'),
        ({'cap': None, 'body': padded(4 * mib)}, 401, 'no_capability'),
        ({'path': '/v1/models'}, 404, 'not_forwarded'),
        ({'path': '/v1/chat/completions/x'}, 404, 'not_forwarded'),
        ({'cap': None}, 401, 'no_capability'),
        ({'cap': 'f' * 64}, 401, 'no_capability'),
        ({'body': b'{not json'}, 400, 'bad_body'),
        ({'body': b'[1, 2]'}, 400, 'bad_body'),
        ({'body': chat_body(models=['a', 'b'])}, 403, 'forbidden_field'),
        ({'body': chat_body(route='fallback')}, 403, 'forbidden_field'),
        ({'body': chat_body(plugins=[])}, 403, 'forbidden_field'),
        ({'body': chat_body(transforms=[])}, 403, 'forbidden_field'),
        ({'body': chat_body(preset='p')}, 403, 'forbidden_field'),
        ({'body': chat_body(web_search_options={})}, 403, 'forbidden_field'),
        ({'body': chat_body(n=2)}, 403, 'forbidden_field'),
        ({'body': chat_body(tools=[{'type': 'web_search'}])}, 403, 'server_tool'),
        ({'body': chat_body(model='vendor/' + PLANT_BODY)}, 403, 'unpriced_model'),
        ({'body': chat_body(model=...)}, 403, 'unpriced_model'),
    ]
    with session() as (child, upstream):
        for kwargs, status, reason in cases:
            body = kwargs.pop('body', chat_body())
            got, _, data = post(child.port, body, **kwargs)
            assert (got, json.loads(data)) == (status, error_body(status, reason)), kwargs
        ok, _, _ = post(child.port, chat_body(n=1, tools=[{'type': 'function', 'function': {}}]))
        assert ok == 200, ok
        conn = http.client.HTTPConnection('127.0.0.1', child.port, timeout=60)
        chunks = (b' ' * mib for _ in range(33))
        headers = {'Authorization': f'Bearer {CAP}', 'Transfer-Encoding': 'chunked'}
        conn.request('POST', PATH, body=chunks, headers=headers, encode_chunked=True)
        resp = conn.getresponse()
        assert (resp.status, json.loads(resp.read())) == (413, error_body(413, 'too_large'))
        conn.close()
        for request in (b'GET /v1/chat/completions HTTP/1.1\r\nHost: x\r\n\r\n',):
            assert raw(child.port, request).startswith(b'HTTP/1.1 404'), request
        assert len(upstream.seen) == 1, len(upstream.seen)
    lines = log_lines(child)
    refused = [x for x in lines if x['decision'] == 'refused']
    assert len(refused) == len(cases) + 2, len(refused)
    assert all(x['reserved_usd'] is None and x['settled_usd'] is None for x in refused), refused
    assert {x['model'] for x in refused} == {None, MODEL}, refused


def test_a_refusal_answers_before_a_body_the_client_has_not_sent():
    head = (
        'POST %s HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer %s\r\n'
        'Content-Type: application/json\r\nContent-Length: %d\r\n\r\n'
    )
    with session() as (child, upstream):
        for path, size, status in ((PATH, 32 * 1024 * 1024 + 1, 413), ('/v1/models', 100, 404)):
            with socket.create_connection(('127.0.0.1', child.port), timeout=10) as s:
                s.sendall((head % (path, CAP, size)).encode())
                started = time.monotonic()
                got = s.recv(65536)
                assert got.startswith(b'HTTP/1.1 %d' % status), got
                assert time.monotonic() - started < 3, path
        assert not upstream.seen


def whole_answer(s: socket.socket) -> bytes:
    """One answer read from `s` up to the end of its Content-Length body, the socket kept open."""
    got = b''
    while b'\r\n\r\n' not in got:
        part = s.recv(65536)
        assert part, got
        got += part
    head, _, body = got.partition(b'\r\n\r\n')
    length = next(
        int(line.split(b':', 1)[1])
        for line in head.split(b'\r\n')
        if line.lower().startswith(b'content-length:')
    )
    while len(body) < length:
        part = s.recv(65536)
        assert part, got
        body += part
    return head + b'\r\n\r\n' + body


def test_a_refusal_is_logged_by_the_time_its_answer_arrives():
    head = (
        f'POST {PATH} HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {CAP}\r\n'
        f'Content-Type: application/json\r\nContent-Length: {32 * 1024 * 1024 + 1}\r\n\r\n'
    )

    def too_large(lines: list[dict]) -> list[dict]:
        return [
            x
            for x in lines
            if (x['decision'], x['reason'], x['status']) == ('refused', 'too_large', 413)
        ]

    with session() as (child, upstream):
        with socket.create_connection(('127.0.0.1', child.port), timeout=10) as s:
            s.sendall(head.encode())
            answer = whole_answer(s)
            assert answer.startswith(b'HTTP/1.1 413'), answer
            # The socket is still open and no body byte was sent.
            lines = log_lines(child)
            assert len(too_large(lines)) == 1, lines
        assert len(too_large(log_lines(child))) == 1, log_lines(child)
        assert not upstream.seen
    lines = log_lines(child)
    assert len(too_large(lines)) == 1 and len(lines) == 1, lines


def test_proxy_requests_are_refused_naming_the_host():
    with session() as (child, upstream):
        got = raw(child.port, b'CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n')
        assert got.startswith(b'HTTP/1.1 403'), got
        assert json.loads(got.split(b'\r\n\r\n', 1)[1]) == error_body(403, 'proxy'), got
        request = b'POST http://other.example/v1/chat/completions HTTP/1.1\r\nHost: x\r\n\r\n'
        assert raw(child.port, request).startswith(b'HTTP/1.1 403')
        assert not upstream.seen
    hosts = [(x['reason'], x['proxy_host']) for x in log_lines(child)]
    assert hosts == [('proxy', 'example.com'), ('proxy', 'other.example')], hosts


def test_the_key_in_a_request_stops_the_relay():
    places = (
        {'headers': {'X-Leak': 'see ' + KEY}},
        {'path': PATH + '?k=' + KEY},
        {'body': chat_body(messages=[{'role': 'user', 'content': KEY}])},
        {
            'body': gzip.compress(json.dumps(chat_body(note=KEY)).encode()),
            'headers': {'Content-Encoding': 'gzip'},
        },
    )
    for place in places:
        with session() as (child, upstream):
            body = place.pop('body', chat_body())
            status, _, data = post(child.port, body, **place)
            assert (status, json.loads(data)) == (403, error_body(403, 'key_in_request')), place
            status, _, data = post(child.port, chat_body())
            assert (status, json.loads(data)) == (403, error_body(403, 'stopped')), place
            assert not upstream.seen
        stop = ledger_lines(child.root)[-1]
        assert stop['kind'] == 'stop' and stop['reason'] == 'key_in_request', stop
        assert set(stop) == {'ts_utc', 'kind', 'id', 'run_id', 'usd', 'reason'}, stop
        assert [x['reason'] for x in log_lines(child)] == ['key_in_request', 'stopped']


def test_each_ceiling_refuses_with_its_reason_and_no_upstream_request():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000000Z')
    spent = {'ts_utc': today, 'kind': 'settle', 'id': 'e1', 'run_id': 'other', 'model': MODEL}
    cases = (
        ({'ceilings__run_usd': 0.005}, 'ceiling_run'),
        ({'ceilings__day_usd': 3.005}, 'ceiling_day'),
        ({'ceilings__month_usd': 3.005}, 'ceiling_month'),
    )
    for over, reason in cases:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            ledger = base / 'state' / 'relay' / 'ledger.ndjson'
            ledger.parent.mkdir(parents=True)
            ledger.write_text(json.dumps({**spent, 'usd': 3.0}) + '\n', encoding='ascii')
            upstream = Upstream(ledger)
            threading.Thread(target=upstream.serve_forever, daemon=True).start()
            child = Relay(base, settings(upstream.port, **over))
            try:
                status, _, data = post(child.port, chat_body())
                assert (status, json.loads(data)) == (403, error_body(403, reason)), over
                assert not upstream.seen
            finally:
                child.close()
                upstream.shutdown()
                upstream.server_close()
            assert [x['kind'] for x in ledger_lines(child.root)] == ['settle'], over


def test_a_restarted_relay_replays_the_day_and_month_and_counts_its_run_from_zero():
    # One reservation here is about 0.0085 USD; the ceilings below allow one, or two.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        upstream = Upstream(base / 'state' / 'relay' / 'ledger.ndjson')
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        children: list[Relay] = []
        table = settings(upstream.port, ceilings__run_usd=0.012)
        try:
            children.append(Relay(base, table))
            assert post(children[-1].port, chat_body())[0] == 200
            # A refusal closes the connection on the relay's side first.
            assert raw(children[-1].port, b'GET / HTTP/1.1\r\nHost: x\r\n\r\n').startswith(
                b'HTTP/1.1 404'
            )
            children[-1].close()
            # The same run on the same port: its run total lives in the new relay's memory.
            children.append(Relay(base, table))
            assert children[-1].ready is not None, children[-1].close() or children[-1].err
            assert post(children[-1].port, chat_body())[0] == 200
            status, _, data = post(children[-1].port, chat_body())
            assert (status, json.loads(data)) == (403, error_body(403, 'ceiling_run'))
            children[-1].close()
            for ceiling, reason in (('day_usd', 'ceiling_day'), ('month_usd', 'ceiling_month')):
                tight = settings(upstream.port, **{f'ceilings__{ceiling}': 0.02})
                children.append(Relay(base, tight, run_id=RUN[:-1] + 'c'))
                status, _, data = post(children[-1].port, chat_body())
                children[-1].close()
                assert (status, json.loads(data)) == (403, error_body(403, reason)), ceiling
            assert len(upstream.seen) == 2, len(upstream.seen)
        finally:
            end(children, upstream)


def test_a_killed_relay_leaves_a_reservation_the_next_start_settles():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        upstream = Upstream(base / 'state' / 'relay' / 'ledger.ndjson')
        upstream.answer = stream(sse(None), hold_after=0)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        children: list[Relay] = []
        try:
            first = Relay(base, settings(upstream.port))
            children.append(first)
            client = threading.Thread(target=lambda: _quiet_post(first.port), daemon=True)
            client.start()
            assert upstream.arrived.wait(30)
            time.sleep(0.3)
            first.kill()
            upstream.release.set()
            [reserve] = ledger_lines(first.root)
            second = Relay(base, settings(upstream.port))
            children.append(second)
            assert second.ready is not None, second.close() or second.err
            settle = ledger_lines(second.root)[-1]
            assert settle['kind'] == 'settle' and settle['id'] == reserve['id'], settle
            for key in ('run_id', 'model', 'usd'):
                assert settle[key] == reserve[key], key
            code, out, err = summary(second.root, '--json')
            assert code == 0 and err == '', (code, err)
            got = json.loads(out)
            assert set(got) == {'run', 'day', 'month', 'all', 'open', 'stops'}, got
            assert got['day'] == got['month'] == got['all'] == reserve['usd'], got
            assert got['run'] == {RUN: reserve['usd']} and got['open'] == 0, got
            second.close()
        finally:
            end(children, upstream)


def end(children: list[Relay], upstream: Upstream) -> None:
    """Kill every relay still running, then stop the upstream."""
    upstream.release.set()
    for child in children:
        if child.code is None:
            child.kill()
    upstream.shutdown()
    upstream.server_close()


def _quiet_post(port: int) -> None:
    try:
        post(port, chat_body(stream=True))
    except (OSError, http.client.HTTPException):
        pass


def test_a_malformed_first_line_exits_3_and_echoes_neither_value():
    lines = (
        json.dumps({'key': 'has space', 'capability': CAP}),
        json.dumps({'key': 'has\rreturn', 'capability': CAP}),
        json.dumps({'key': KEY + chr(0xE9), 'capability': CAP}),
        json.dumps({'key': '', 'capability': CAP}),
        json.dumps({'key': 'k' * 513, 'capability': CAP}),
        json.dumps({'key': KEY, 'capability': CAP.upper()}),
        json.dumps({'key': KEY, 'capability': CAP[:-1]}),
        json.dumps({'key': KEY, 'capability': CAP, 'other': 1}),
        json.dumps([KEY, CAP]),
        'key=' + KEY,
        '',
    )
    for line in lines:
        with tempfile.TemporaryDirectory() as td:
            child = Relay(Path(td), settings(free_port()), line=line.encode() + b'\n')
            code = child.close()
            assert code == 3 and child.ready is None, (line, code, child.out)
            for word in ('has space', 'has\rreturn', KEY, CAP, CAP.upper()):
                assert word.encode() not in child.out + child.err, (line, word)
            assert child.err.count(b'\n') == 1, child.err
            assert not (child.root / 'relay').exists(), line


def test_a_second_relay_on_the_same_state_root_exits_3_naming_the_holder():
    with session() as (child, upstream):
        second = Relay(child.base, settings(upstream.port))
        assert second.close() == 3 and second.ready is None
        assert f'pid {child.ready["pid"]}'.encode() in second.err, second.err
        assert second.err.count(b'\n') == 1, second.err


def test_end_of_standard_input_stops_the_relay_and_releases_the_lock():
    with session() as (child, upstream):
        assert post(child.port, chat_body())[0] == 200
        started = time.monotonic()
        assert child.close() == 0
        assert time.monotonic() - started < 10
        again = Relay(child.base, settings(upstream.port))
        assert again.ready is not None, again.close() or again.err
        assert again.close() == 0


def test_a_request_whose_handling_raises_writes_only_the_fixed_line():
    with session(drop) as (child, _upstream):
        status, _, data = post(child.port, chat_body())
        assert (status, json.loads(data)) == (502, error_body(502, 'upstream_failed')), data
    assert child.err.decode('ascii').splitlines() == [FIXED], child.err
    [line] = log_lines(child)
    assert line['settle_source'] == 'reservation' and line['status'] == 502, line


def test_refused_daily_files_exit_3_before_anything_binds():
    cases = (
        {'upstream_base': 'http://relay-upstream.invalid:1'},
        {'upstream_base': 'http://relay-upstream.invalid:1', 'test': False},
        {'upstream_base': 'https' + '://127.0.0.1:1', 'test': False},
        {'key_env': 'STUB_API_KEY'},
        {'key_env': 'PATH'},
    )
    for over in cases:
        with tempfile.TemporaryDirectory() as td:
            table = settings(free_port())
            table.update(over)
            child = Relay(Path(td), table)
            assert child.close() == 3 and child.ready is None, over
            assert child.err.startswith(b'kit relay: daily file refused: '), child.err
            assert not (child.root / 'relay').exists(), over


def test_end_of_input_settles_what_is_still_open_at_its_reservation():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        upstream = Upstream(root / 'relay' / 'ledger.ndjson')
        upstream.answer = hold_then(whole(b'{"usage": {"cost": 0.75}}'))
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        table = settings(upstream.port)
        config = daily.check_relay(table, root)
        (root / 'relay').mkdir(parents=True)
        state = relay.Relay(config, root, RUN, KEY, CAP)
        state.replay()
        server = relay.RelayServer(state)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            client = threading.Thread(target=lambda: _quiet_post(table['listen_port']))
            client.start()
            assert upstream.arrived.wait(30)
            relay.stop(server, 0.3)
            reserve, settle = ledger_lines(root)
            assert settle['kind'] == 'settle' and settle['usd'] == reserve['usd'], settle
            upstream.release.set()
            client.join(30)
            assert [x['kind'] for x in ledger_lines(root)] == ['reserve', 'settle']
        finally:
            upstream.release.set()
            upstream.shutdown()
            upstream.server_close()


def test_summary_prints_the_stated_keys_and_totals():
    today = datetime.now(timezone.utc)
    stamp = today.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
    old = '2001-02-03T04:05:06.000000Z'
    rows = [
        {'ts_utc': old, 'kind': 'reserve', 'id': 'a', 'run_id': 'r1', 'model': MODEL, 'usd': 1.0},
        {'ts_utc': old, 'kind': 'settle', 'id': 'a', 'run_id': 'r1', 'model': MODEL, 'usd': 0.5},
        {'ts_utc': stamp, 'kind': 'reserve', 'id': 'b', 'run_id': 'r2', 'model': MODEL, 'usd': 2.0},
        {'ts_utc': stamp, 'kind': 'settle', 'id': 'b', 'run_id': 'r2', 'model': MODEL, 'usd': 1.25},
        {
            'ts_utc': stamp,
            'kind': 'reserve',
            'id': 'c',
            'run_id': 'r2',
            'model': MODEL,
            'usd': 0.25,
        },
        {
            'ts_utc': stamp,
            'kind': 'stop',
            'id': 'd',
            'run_id': 'r2',
            'usd': 0,
            'reason': 'key_in_request',
        },
    ]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        code, out, _ = summary(root, '--json')
        assert code == 0, out
        empty = {'run': {}, 'day': 0, 'month': 0, 'all': 0, 'open': 0, 'stops': {}}
        assert json.loads(out) == empty, out
        assert not (root / 'relay').exists()
        (root / 'relay').mkdir(parents=True)
        text = ''.join(json.dumps(r) + '\n' for r in rows) + '{"partial'
        (root / 'relay' / 'ledger.ndjson').write_text(text, encoding='ascii')
        code, out, _ = summary(root, '--json')
        got = json.loads(out)
        assert got == {
            'run': {'r1': 0.5, 'r2': 1.25},
            'day': 1.25,
            'month': 1.25,
            'all': 1.75,
            'open': 0.25,
            'stops': {'r2': 'key_in_request'},
        }, got
        code, out, _ = summary(root)
        assert code == 0 and 'r2' in out and '1.75' in out, out


if __name__ == '__main__':
    try:
        run_module(globals(), 'the relay')
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)

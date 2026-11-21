"""The relay: `kit relay serve --config FILE --state-root ROOT --run-id ID` and `kit relay summary`.

A local HTTP server on 127.0.0.1, standard library only, and the only process given the provider
key. It forwards a harness's chat requests to one upstream, reserves each request's worst cost
before forwarding it, settles it from the answer, and keeps an append-only ledger,
`ROOT/relay/ledger.ndjson`, one JSON line per `reserve`, `settle` and `stop`.

Start: the relay checks the daily file's `[relay]` table (`daily.py`), reads one line from
standard input, `{"key": KEY, "capability": CAP}`, takes an exclusive lock on
`ROOT/relay/relay.lock` for its whole life, replays the ledger into the day and month totals
it keeps in its memory from then on (settling at its reservation every `reserve` no `settle`
follows, by a line appended before it binds), binds 127.0.0.1 and prints `{"relay": 1, "port": N, "pid": P}`.
Each fatal error before that writes one line to standard error and exits 3, echoing neither the
key nor the capability. At end of standard input the relay refuses new requests, waits at most
30 s for those in flight, settles what is still open at its reservation, releases the lock and
exits 0.

Each request, in order: a stopped relay refuses it; the key in its request line or a header value
stops the relay (`key_in_request`); a proxy request is refused naming its host; only
`POST /v1/chat/completions` is served, with this run's capability as its bearer; the body is one
JSON object of at most 32 MiB, the key in it stops the relay too, and forbidden fields, server
tools and unpriced models are refused; the output limit, `provider` and `usage` are rewritten;
the reservation is appended to the ledger and flushed to disk under one in-process lock that
also keeps the ceilings, and only then is the request forwarded with `http.client`, which reads
no proxy variable, carrying `Authorization: Bearer KEY` and no incoming header. The settlement is
the larger of the reported cost and the priced usage, else the reservation.

Every request gets one line in `ROOT/runs/ID/relay-log.ndjson`: never a body, a header value, the
key, the capability, a query value or a path. Standard error receives nothing but the fatal
lines and, for a request whose handling raised, the fixed line `kit relay: request failed`.
"""

from __future__ import annotations

import errno
import hmac
import http.client
import http.server
import json
import math
import os
import re
import secrets
import socket
import socketserver
import ssl
import sys
import threading
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from harness_kit import daily, state

WINDOWS = os.name == 'nt'
HARNESS_ROUTE = '/v1/chat/completions'
MAX_BODY = 32 * 1024 * 1024
# A larger body is read and dropped up to this size after its refusal, within DRAIN_READ_S a read.
MAX_DRAIN = 4 * MAX_BODY
DRAIN_READ_S = 5.0
MAX_LINE = 4096
MAX_REQUEST_LINE = 65536
KEY_RE = re.compile(r'[\x21-\x7e]{1,512}')
CAPABILITY_RE = re.compile(r'[0-9a-f]{64}')
RUN_ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
FORBIDDEN_FIELDS = ('models', 'route', 'plugins', 'transforms', 'preset', 'web_search_options')
DRAIN_S = 30.0
LOCK_OFFSET = 4096
EPSILON_USD = 1e-9
LEDGER = 'ledger.ndjson'
LOCK = 'relay.lock'
LOG = 'relay-log.ndjson'
EXIT_FATAL = 3
EXIT_INTERNAL = 70
REQUEST_FAILED = 'kit relay: request failed'
MAX_SSE_LINE = 4 * 1024 * 1024


def _stamp(now: datetime) -> str:
    return now.strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _ascii(text: str) -> str:
    return text.encode('ascii', 'backslashreplace').decode('ascii')


def _say(line: str) -> None:
    try:
        sys.stderr.write(line + '\n')
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def _amount(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
    )


def _tokens(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


# ---- the ledger


@dataclass
class Totals:
    """Settled amounts per run, per UTC day and month and in all; open reservations; stops."""

    run: dict[str, float] = field(default_factory=dict)
    day: dict[str, float] = field(default_factory=dict)
    month: dict[str, float] = field(default_factory=dict)
    all: float = 0.0
    open: dict[str, dict] = field(default_factory=dict)
    stops: dict[str, str] = field(default_factory=dict)
    settled: set[str] = field(default_factory=set)

    def add(self, record: dict) -> None:
        """Count one ledger line; a line that is not one of the three kinds is skipped."""
        kind, rid, run_id = record.get('kind'), record.get('id'), record.get('run_id')
        stamp, usd = record.get('ts_utc'), record.get('usd')
        if not (isinstance(rid, str) and isinstance(run_id, str) and isinstance(stamp, str)):
            return
        if kind == 'stop':
            reason = record.get('reason')
            self.stops.setdefault(run_id, reason if isinstance(reason, str) else '')
        elif not _amount(usd) or len(stamp) < 10:
            return
        elif kind == 'reserve' and rid not in self.settled:
            self.open[rid] = record
        elif kind == 'settle' and rid not in self.settled:
            self.settled.add(rid)
            self.open.pop(rid, None)
            self.run[run_id] = self.run.get(run_id, 0.0) + usd
            self.day[stamp[:10]] = self.day.get(stamp[:10], 0.0) + usd
            self.month[stamp[:7]] = self.month.get(stamp[:7], 0.0) + usd
            self.all += usd

    def open_usd(self, run_id: str | None = None) -> float:
        return sum(r['usd'] for r in self.open.values() if run_id in (None, r['run_id']))


def fold(data: bytes) -> Totals:
    """The totals of a ledger's bytes; a line that does not parse is skipped."""
    totals = Totals()
    for line in data.split(b'\n'):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            totals.add(record)
    return totals


def read_ledger(root: Path) -> bytes:
    path = Path(root) / 'relay' / LEDGER
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return b''


# ---- the relay's state


class Relay:
    """What one relay holds in memory: its settings, run, key, capability and totals."""

    def __init__(self, settings: daily.RelaySettings, root: Path, run_id: str, key: str, cap: str):
        self.settings = settings
        self.root = Path(root)
        self.run_id = run_id
        self._key = key.encode('ascii')
        self._bearer = f'Bearer {cap}'.encode('ascii')
        self.ledger = self.root / 'relay' / LEDGER
        self.log_path = self.root / 'runs' / run_id / LOG
        self.lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.idle = threading.Condition()
        self.busy = 0
        self.totals = Totals()
        # The run's total lives in this relay's memory only, from zero: a ledger truncated by a
        # shell command resets the day and month totals at the next start, never this one.
        self.run_settled = 0.0
        self.stopped = False
        self.closing = False

    def holds_key(self, data: bytes) -> bool:
        return self._key in data

    def authorized(self, values: list) -> bool:
        if len(values) != 1:
            return False
        return hmac.compare_digest(str(values[0]).encode('latin-1', 'replace'), self._bearer)

    def upstream_auth(self) -> str:
        return 'Bearer ' + self._key.decode('ascii')

    def _append(self, record: dict) -> None:
        line = (json.dumps(record, ensure_ascii=True) + '\n').encode('ascii')
        with open(self.ledger, 'ab') as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def replay(self) -> None:
        """Read the ledger once, then settle at its reservation each reserve left open."""
        data = read_ledger(self.root)
        self.totals = fold(data)
        with self.lock:
            if data and not data.endswith(b'\n'):
                with open(self.ledger, 'ab') as fh:
                    fh.write(b'\n')
            for rid in list(self.totals.open):
                self._settle(rid, self.totals.open[rid]['usd'])

    def reserve(self, model: daily.Model, usd: float) -> tuple[str | None, str | None]:
        """(reservation id, None), or (None, the ceiling it would pass)."""
        s, t = self.settings, self.totals
        with self.lock:
            now = datetime.now(timezone.utc)
            day, month = now.strftime('%Y-%m-%d'), now.strftime('%Y-%m')
            run_total = self.run_settled + t.open_usd(self.run_id) + usd
            if run_total > s.run_usd + EPSILON_USD:
                return None, 'ceiling_run'
            if t.day.get(day, 0.0) + t.open_usd() + usd > s.day_usd + EPSILON_USD:
                return None, 'ceiling_day'
            if t.month.get(month, 0.0) + t.open_usd() + usd > s.month_usd + EPSILON_USD:
                return None, 'ceiling_month'
            rid = secrets.token_hex(8)
            record = {
                'ts_utc': _stamp(now),
                'kind': 'reserve',
                'id': rid,
                'run_id': self.run_id,
                'model': model.id,
                'usd': usd,
            }
            self._append(record)
            t.add(record)
            return rid, None

    def _settle(self, rid: str, usd: float) -> None:
        reserved = self.totals.open[rid]
        record = {
            'ts_utc': _stamp(datetime.now(timezone.utc)),
            'kind': 'settle',
            'id': rid,
            'run_id': reserved['run_id'],
            'model': reserved['model'],
            'usd': usd,
        }
        self._append(record)
        self.totals.add(record)

    def settle(self, rid: str, usd: float) -> bool:
        """Settle an open reservation; False when it was settled already."""
        with self.lock:
            if rid not in self.totals.open:
                return False
            self._settle(rid, usd)
            self.run_settled += usd
            return True

    def settle_open(self) -> None:
        with self.lock:
            for rid in list(self.totals.open):
                self._settle(rid, self.totals.open[rid]['usd'])

    def stop(self, reason: str) -> None:
        with self.lock:
            if self.stopped:
                return
            self.stopped = True
            self._append(
                {
                    'ts_utc': _stamp(datetime.now(timezone.utc)),
                    'kind': 'stop',
                    'id': secrets.token_hex(8),
                    'run_id': self.run_id,
                    'usd': 0.0,
                    'reason': reason,
                }
            )

    def log(self, record: dict) -> None:
        line = (json.dumps(record, ensure_ascii=True) + '\n').encode('ascii')
        with self.log_lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'ab') as fh:
                fh.write(line)


# ---- answers to the harness


def settlement(usage: object, model: daily.Model, reserved: float) -> tuple[float, str]:
    """(amount, source): the larger of the reported cost and the priced usage, else the reservation.

    The usage is priced from whichever of its two token counts are readable.
    """
    usage = usage if isinstance(usage, dict) else {}
    cost = usage.get('cost')
    reported = float(cost) if _amount(cost) else None
    prompt, completion = (
        _tokens(usage.get('prompt_tokens')),
        _tokens(usage.get('completion_tokens')),
    )
    priced = None
    if prompt is not None or completion is not None:
        priced = (prompt or 0) * model.input_usd_per_mtok / 1e6 + (
            completion or 0
        ) * model.output_usd_per_mtok / 1e6
    if reported is None and priced is None:
        return reserved, 'reservation'
    if priced is None or (reported is not None and reported >= priced):
        return reported, 'reported'
    return priced, 'priced'


class UsageScanner:
    """The last `usage` object of a stream of server-sent events, read as it passes."""

    def __init__(self) -> None:
        self.buffer = b''
        self.usage: dict | None = None

    def feed(self, data: bytes) -> None:
        self.buffer += data
        *lines, self.buffer = self.buffer.split(b'\n')
        if len(self.buffer) > MAX_SSE_LINE:
            self.buffer = b''
        for line in lines:
            line = line.strip()
            if not line.startswith(b'data:'):
                continue
            try:
                doc = json.loads(line[5:])
            except ValueError:
                continue
            if isinstance(doc, dict) and isinstance(doc.get('usage'), dict):
                self.usage = doc['usage']


def _usage_of(data: bytes, encoding: str | None) -> dict | None:
    try:
        if (encoding or '').strip().lower() == 'gzip':
            data = zlib.decompress(data, 16 + zlib.MAX_WBITS)
        doc = json.loads(data)
    except (ValueError, zlib.error):
        return None
    usage = doc.get('usage') if isinstance(doc, dict) else None
    return usage if isinstance(usage, dict) else None


def _gunzip(raw: bytes) -> bytes | None:
    """The decoded body, or None when it is not gzip or decodes past MAX_BODY."""
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = inflater.decompress(raw, MAX_BODY + 1)
    except zlib.error:
        return None
    if len(data) > MAX_BODY or inflater.unconsumed_tail or not inflater.eof:
        return None
    return data


def proxy_host(command: str, target: str) -> str:
    """The host a proxy request names, without its port."""
    if command == 'CONNECT':
        host = target.rsplit(':', 1)[0] if not target.endswith(']') else target
    else:
        try:
            host = urlsplit(target).hostname or ''
        except ValueError:
            host = ''
    return _ascii(host.strip('[]').lower())[:255]


def _cap_tokens(value: object, limit: int) -> int:
    ok = isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= limit
    return value if ok else limit


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server: RelayServer

    def log_message(self, format: str, *args: object) -> None:
        pass  # a request line never reaches standard error

    def handle_one_request(self) -> None:
        self.raw_requestline = self.rfile.readline(MAX_REQUEST_LINE + 1)
        if not self.raw_requestline:
            self.close_connection = True
            return
        relay = self.server.relay
        started = time.monotonic()
        self.started = False
        self.body_read = False
        self.unread = 0
        # A request the library rejects before its headers keeps no earlier request's headers.
        self.headers = None  # type: ignore[assignment]
        self.usage: dict | None = None
        self.record = {
            'ts_utc': _stamp(datetime.now(timezone.utc)),
            'decision': 'refused',
            'reason': None,
            'status': None,
            'model': None,
            'req_bytes': 0,
            'resp_bytes': 0,
            'prompt_tokens': None,
            'completion_tokens': None,
            'reserved_usd': None,
            'settled_usd': None,
            'settle_source': None,
            'proxy_host': None,
            'query_names': [],
            'duration_ms': 0,
        }
        with relay.idle:
            relay.busy += 1
        raised = True
        try:
            if len(self.raw_requestline) > MAX_REQUEST_LINE:
                self.send_error(414)
            elif self.parse_request():
                self.serve()
            else:
                self.close_connection = True
            raised = False
        finally:
            self.record['duration_ms'] = int((time.monotonic() - started) * 1000)
            try:
                if raised or self.record['status'] is not None:
                    relay.log(self.record)
            finally:
                with relay.idle:
                    relay.busy -= 1
                    relay.idle.notify_all()

    def send_error(self, code: int, message: str | None = None, explain: str | None = None):
        """A request the server library rejects: refused, its text never echoed."""
        if self.server.relay.holds_key(self.raw_requestline):
            return self.key_found()
        self.refuse(400, 'bad_request')

    def reply_error(self, status: int, reason: str, extra=(), close: bool = True) -> None:
        body = {'error': {'message': f'kit relay: {reason}', 'type': 'kit_relay', 'code': status}}
        data = json.dumps(body).encode('ascii')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        for name, value in extra:
            self.send_header(name, value)
        if close:
            self.send_header('Connection', 'close')
            self.close_connection = True
        self.end_headers()
        self.started = True
        self.record['status'], self.record['resp_bytes'] = status, len(data)
        self.wfile.write(data)

    def refuse(self, status: int, reason: str) -> None:
        self.record['decision'], self.record['reason'] = 'refused', reason
        self.reply_error(status, reason)
        self.drain_body()

    def key_found(self) -> None:
        self.server.relay.stop('key_in_request')
        self.refuse(403, 'key_in_request')

    def serve(self) -> None:
        relay, record = self.server.relay, self.record
        if relay.closing:
            return self.refuse(503, 'closing')
        if relay.stopped:
            return self.refuse(403, 'stopped')
        values = [str(v).encode('latin-1', 'replace') for v in self.headers.values()]
        if relay.holds_key(self.raw_requestline) or any(relay.holds_key(v) for v in values):
            return self.key_found()
        target = self.path
        if self.command == 'CONNECT' or target.lower().startswith(('http://', 'https://')):
            record['proxy_host'] = proxy_host(self.command, target)
            return self.refuse(403, 'proxy')
        path, _, query = target.partition('?')
        names = [_ascii(n) for n, _ in parse_qsl(query, keep_blank_values=True)]
        record['query_names'] = names[:100]
        if self.command != 'POST' or path != HARNESS_ROUTE:
            return self.refuse(404, 'not_forwarded')
        if not relay.authorized(self.headers.get_all('Authorization') or []):
            return self.refuse(401, 'no_capability')
        raw, reason = self.read_body()
        if reason is not None:
            return self.refuse(413 if reason == 'too_large' else 400, reason)
        record['req_bytes'] = len(raw)
        data, reason = self.decode_body(raw)
        if reason is not None:
            return self.refuse(413 if reason == 'too_large' else 400, reason)
        if relay.holds_key(raw) or relay.holds_key(data):
            return self.key_found()
        try:
            doc = json.loads(data.decode('utf-8'))
        except (UnicodeDecodeError, ValueError, RecursionError):
            doc = None
        if not isinstance(doc, dict):
            return self.refuse(400, 'bad_body')
        model = relay.settings.model(doc.get('model'))
        record['model'] = model.id if model is not None else None
        n = doc.get('n', 1)
        if any(k in doc for k in FORBIDDEN_FIELDS) or type(n) is not int or n != 1:
            return self.refuse(403, 'forbidden_field')
        tools = doc.get('tools')
        if tools is not None and (
            not isinstance(tools, list)
            or any(not isinstance(t, dict) or t.get('type') != 'function' for t in tools)
        ):
            return self.refuse(403, 'server_tool')
        if model is None:
            return self.refuse(403, 'unpriced_model')
        body, limit = self.rewrite(doc, model)
        if relay.holds_key(body):
            return self.key_found()
        self.forward_reserved(body, model, limit)

    def read_body(self) -> tuple[bytes, str | None]:
        """The request body, or a reason. A body over MAX_BODY is read and dropped up to
        MAX_DRAIN after the refusal, so a client that sends it whole before reading still gets
        the answer."""
        self.body_read = True
        coding = (self.headers.get('Transfer-Encoding') or '').strip().lower()
        if coding:
            if coding != 'chunked':
                return b'', 'bad_body'
            parts, size = [], 0
            while True:
                line = self.rfile.readline(1024)
                try:
                    count = int(line.split(b';', 1)[0].strip(), 16)
                except ValueError:
                    return b'', 'bad_body'
                if count == 0:
                    while self.rfile.readline(65537) not in (b'\r\n', b'\n', b''):
                        pass
                    return (b'', 'too_large') if size > MAX_BODY else (b''.join(parts), None)
                size += count
                if size > MAX_DRAIN:
                    return b'', 'too_large'
                if size > MAX_BODY:
                    parts.clear()
                    self._discard(count)
                else:
                    parts.append(self.rfile.read(count))
                self.rfile.readline(3)
        length = self.headers.get('Content-Length')
        if length is None:
            return b'', None
        try:
            count = int(length)
        except ValueError:
            return b'', 'bad_body'
        if count < 0:
            return b'', 'bad_body'
        if count > MAX_BODY:
            # Left unread: the refusal answers first, then drops it (`drain_body`).
            self.unread = count if count <= MAX_DRAIN else 0
            return b'', 'too_large'
        raw = self.rfile.read(count)
        return (raw, None) if len(raw) == count else (b'', 'bad_body')

    def _discard(self, count: int) -> None:
        while count > 0:
            piece = self.rfile.read(min(count, 65536))
            if not piece:
                return
            count -= len(piece)

    def drain_body(self) -> None:
        """Read and drop, after a refusal answered, a body no step read, before the connection
        closes.

        A connection closed with unread data is reset, and a client that sends its whole
        body before it reads would lose the answer; a client that sends no body has its
        answer already, since the refusal is written first.
        """
        if self.headers is None:
            return
        try:
            self.connection.settimeout(DRAIN_READ_S)
            if not self.body_read:
                self.read_body()
            self._discard(self.unread)
        except (OSError, ValueError):
            pass
        self.unread = 0

    def decode_body(self, raw: bytes) -> tuple[bytes, str | None]:
        coding = (self.headers.get('Content-Encoding') or '').strip().lower()
        if coding in ('', 'identity'):
            return raw, None
        if coding != 'gzip':
            return b'', 'bad_body'
        data = _gunzip(raw)
        if data is None:
            return b'', 'bad_body' if len(raw) <= MAX_BODY else 'too_large'
        return data, None

    def rewrite(self, doc: dict, model: daily.Model) -> tuple[bytes, int]:
        """(the body to forward, its output limit once capped at the model's)."""
        s = self.server.relay.settings
        cap, limits = model.max_output_tokens, []
        for name in ('max_tokens', 'max_completion_tokens'):
            if name in doc:
                doc[name] = _cap_tokens(doc[name], cap)
                limits.append(doc[name])
        if not limits:
            doc['max_tokens'] = cap
            limits.append(cap)
        if s.provider is not None:
            doc['provider'] = json.loads(json.dumps(s.provider))
        if s.usage_include:
            doc['usage'] = {'include': True}
        body = json.dumps(doc, separators=(',', ':'), ensure_ascii=True).encode('ascii')
        return body, max(limits)

    def forward_reserved(self, body: bytes, model: daily.Model, limit: int) -> None:
        """Reserve the worst cost, forward `body`, settle. The reservation prices the bytes of
        the body as forwarded and its output limit."""
        relay, record = self.server.relay, self.record
        usd = len(body) * model.input_usd_per_mtok / 1e6 + limit * model.output_usd_per_mtok / 1e6
        rid, reason = relay.reserve(model, usd)
        if reason is not None:
            return self.refuse(403, reason)
        record['decision'], record['reserved_usd'] = 'forwarded', usd
        try:
            self.forward(body)
        except BaseException:
            record['reason'] = 'upstream_failed'
            if not self.started:
                try:
                    self.reply_error(502, 'upstream_failed')
                except OSError:
                    pass
            raise
        finally:
            usage = self.usage if isinstance(self.usage, dict) else {}
            record['prompt_tokens'] = _tokens(usage.get('prompt_tokens'))
            record['completion_tokens'] = _tokens(usage.get('completion_tokens'))
            settled, source = settlement(usage, model, usd)
            if not relay.settle(rid, settled):
                settled, source = usd, 'reservation'
            record['settled_usd'], record['settle_source'] = settled, source

    def forward(self, body: bytes) -> None:
        relay, record = self.server.relay, self.record
        s = relay.settings
        parts = urlsplit(s.upstream_base)
        if parts.scheme == 'https':
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                parts.hostname,
                parts.port or 443,
                timeout=s.upstream_timeout_s,
                context=ssl.create_default_context(),
            )
        else:
            conn = http.client.HTTPConnection(
                parts.hostname, parts.port or 80, timeout=s.upstream_timeout_s
            )
        try:
            headers = {'Content-Type': 'application/json', 'Authorization': relay.upstream_auth()}
            conn.request('POST', parts.path.rstrip('/') + s.route, body=body, headers=headers)
            resp = conn.getresponse()
            ctype = resp.getheader('Content-Type') or 'application/json'
            if resp.status == 200 and ctype.split(';')[0].strip().lower() == 'text/event-stream':
                return self.pass_stream(resp, ctype)
            if resp.status == 200:
                data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(data)))
                encoding = resp.getheader('Content-Encoding')
                if encoding:
                    self.send_header('Content-Encoding', encoding)
                self.end_headers()
                self.started = True
                record['status'], record['resp_bytes'] = 200, len(data)
                self.usage = _usage_of(data, encoding)
                self.wfile.write(data)
                return None
            resp.read()
            retry = resp.getheader('Retry-After')
            extra = [('Retry-After', retry)] if retry else []
            record['reason'] = f'upstream {resp.status}'
            self.reply_error(resp.status, f'upstream {resp.status}', extra, close=False)
            return None
        finally:
            conn.close()

    def pass_stream(self, resp: http.client.HTTPResponse, ctype: str) -> None:
        chunked = self.request_version == 'HTTP/1.1'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        if chunked:
            self.send_header('Transfer-Encoding', 'chunked')
        else:
            self.send_header('Connection', 'close')
            self.close_connection = True
        self.end_headers()
        self.started = True
        self.record['status'] = 200
        scanner = UsageScanner()
        while True:
            piece = resp.read1(65536)
            if not piece:
                break
            scanner.feed(piece)
            self.usage = scanner.usage
            self.record['resp_bytes'] += len(piece)
            self.wfile.write(b'%x\r\n%s\r\n' % (len(piece), piece) if chunked else piece)
        if chunked:
            self.wfile.write(b'0\r\n\r\n')


class RelayServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    # On POSIX this lets a restarted relay bind its port while closed connections wait out
    # their time; on Windows the same option would let a second socket take a bound port, so
    # there the socket takes the port exclusively instead.
    allow_reuse_address = not WINDOWS
    request_queue_size = 64

    def __init__(self, relay: Relay) -> None:
        self.relay = relay
        super().__init__(('127.0.0.1', relay.settings.listen_port), Handler)

    def server_bind(self) -> None:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        socketserver.TCPServer.server_bind(self)  # no name lookup of the address
        self.server_name, self.server_port = '127.0.0.1', self.server_address[1]

    def handle_error(self, request, client_address) -> None:
        _say(REQUEST_FAILED)


def stop(server: RelayServer, wait_s: float = DRAIN_S) -> None:
    """Refuse new requests, wait at most `wait_s` for those in flight, settle what is open."""
    relay = server.relay
    relay.closing = True
    server.shutdown()
    server.server_close()
    end = time.monotonic() + wait_s
    with relay.idle:
        while relay.busy and end - time.monotonic() > 0:
            relay.idle.wait(end - time.monotonic())
    relay.settle_open()


# ---- the lock


def _try_lock(fd: int) -> bool:
    if WINDOWS:
        import msvcrt

        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
            return False
        raise
    return True


def _unlock(fd: int) -> None:
    if WINDOWS:
        import msvcrt

        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def _holder(fd: int) -> str:
    """The pid the lock's holder wrote at the head of the lock file."""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        text = os.read(fd, 32).decode('ascii', 'replace').strip()
    except OSError:
        return 'unknown'
    return text if text.isdigit() else 'unknown'


# ---- the commands


def read_first_line(stream) -> tuple[str, str] | None:
    """(key, capability) from `{"key": KEY, "capability": CAP}`, or None for anything else."""
    line = stream.readline(MAX_LINE + 1)
    if len(line) > MAX_LINE:
        return None
    try:
        doc = json.loads(line.decode('ascii'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(doc, dict) or set(doc) != {'key', 'capability'}:
        return None
    key, cap = doc['key'], doc['capability']
    if not (isinstance(key, str) and KEY_RE.fullmatch(key)):
        return None
    if not (isinstance(cap, str) and CAPABILITY_RE.fullmatch(cap)):
        return None
    return key, cap


def _fatal(message: str, code: int = EXIT_FATAL) -> int:
    _say(f'kit relay: {message}')
    return code


def serve_main(config: str, state_root: str, run_id: str) -> int:
    """`kit relay serve`: 3 for a fatal error before the ready line, else 0 at end of input."""
    root = Path(os.path.realpath(state_root))
    refusal = state.refusal(str(root), os.environ, resolve=os.path.realpath)
    if refusal is not None:
        return _fatal(f'state root refused: {refusal}')
    if not RUN_ID_RE.fullmatch(run_id) or '..' in run_id:
        return _fatal('the run id is not a run id')
    try:
        settings = daily.load_relay(config, root)
    except daily.DailyError as exc:
        return _fatal(f'daily file refused: {exc}')
    pair = read_first_line(sys.stdin.buffer)
    if pair is None:
        return _fatal(
            'the first line of standard input is not {"key": KEY, "capability": CAP} with a '
            'key of 1 to 512 printable characters and 64 lowercase hex characters'
        )
    folder = root / 'relay'
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd = state.open_lock(folder / LOCK)
    except OSError:
        return _fatal('the relay folder of the state root could not be opened')
    if not _try_lock(fd):
        return _fatal(f'the relay lock of this state root is held by pid {_holder(fd)}')
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f'{os.getpid():<20}\n'.encode('ascii'))
        relay = Relay(settings, root, run_id, *pair)
        relay.replay()
    except OSError:
        return _fatal('the ledger could not be read or written')
    try:
        server = RelayServer(relay)
    except OSError:
        return _fatal(f'cannot listen on 127.0.0.1:{settings.listen_port}')
    ready = {'relay': 1, 'port': server.server_address[1], 'pid': os.getpid()}
    sys.stdout.write(json.dumps(ready) + '\n')
    sys.stdout.flush()
    code = 0
    try:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        while sys.stdin.buffer.read(65536):
            pass
        stop(server)
        _unlock(fd)
        os.close(fd)
    except Exception:
        code = _fatal('internal error', EXIT_INTERNAL)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(code)  # a handler thread past the wait never holds the exit


def summary_main(as_json: bool) -> int:
    """`kit relay summary [--json]`: the ledger's totals, read without the relay's lock."""
    try:
        root = state.state_root()
    except state.StateRootError as exc:
        return _fatal(_ascii(str(exc)), 64)
    try:
        totals = fold(read_ledger(root))
    except OSError:
        return _fatal('the ledger could not be read', EXIT_INTERNAL)
    now = datetime.now(timezone.utc)
    out = {
        'run': dict(totals.run),
        'day': totals.day.get(now.strftime('%Y-%m-%d'), 0.0),
        'month': totals.month.get(now.strftime('%Y-%m'), 0.0),
        'all': totals.all,
        'open': totals.open_usd(),
        'stops': dict(totals.stops),
    }
    if as_json:
        sys.stdout.write(json.dumps(out, ensure_ascii=True) + '\n')
        return 0
    lines = [f'{name} {out[name]:.6f} USD' for name in ('day', 'month', 'all', 'open')]
    lines += [f'run {_ascii(r)} {usd:.6f} USD' for r, usd in sorted(out['run'].items())]
    lines += [f'stopped {_ascii(r)} {_ascii(why)}' for r, why in sorted(out['stops'].items())]
    sys.stdout.write('\n'.join(lines) + '\n')
    return 0

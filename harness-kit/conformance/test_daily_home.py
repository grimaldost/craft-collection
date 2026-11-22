#!/usr/bin/env python3
"""Daily cells: opencode in a daily home under `kit run`, through the relay to a stub upstream.

Each cell writes a daily file whose `test` is true and whose upstream is a stub the cell runs on
127.0.0.1 (`kit stub`, its log `stub.jsonl` in the cell's folder), renders a daily home with
`kit home render --daily`, and runs `kit run` with the daily file's key variable holding a
made-up test value (`TEST_KEY`). The session's model requests go through the relay, which the
run starts after the canary passed; the canary itself never reaches the relay. The policy is the
conformance base policy (`test_conformance.policy_text`). Every `kit run` uses the state root
`<base>/daily-state`, whose `relay/ledger.ndjson` the relay keeps.

- daily-guard (headless): a call the base policy denies, then text. The canary passed; the
  denied call's marker is absent and the run's journal holds its deny; the run's relay log
  holds forwarded requests, and the ledger a `reserve` and a `settle` line of the run;
  `run.json` holds `relay`.
- daily-no-key (headless): a shell call writes the session's environment to `env.txt`. Its names
  hold `KIT_RELAY_CAPABILITY` and not the key variable's; the test key's text is in no file under
  the home, the working folder, the run folder or the state root's `relay/` folder, nor in the
  stub's log.
- daily-ceiling (headless): `run_usd` below one reservation. No request reached the stub; the
  run's relay log holds `ceiling_run`.
- daily-proxy (headless): `curl.exe -s -o NUL https://example.com` in the shell. The call was
  allowed; the relay log holds a `proxy` refusal naming `example.com`; the stub's log holds no
  proxy request.
- daily-git (headless): in a git work tree with no remote, `git commit --allow-empty -m kit-cell`.
  The work tree's HEAD commit (read from its object files) has the daily file's identity as its
  author.
- daily-interactive (interactive, under the pseudo console of `conpty.py`): the calls of
  daily-guard, daily-no-key, daily-proxy and daily-git in one session, then text; the cell
  writes one Ctrl+C once the stub served the last step. Each of those cells' expectations holds
  for the run, `outcome` is `ended` and no opencode process of the cell is left.

The canary's journal lines (rules `canary.deny` and `canary.allow`, and every line of its
session) are left out of every count. The account's governed files are hashed before the first
cell and after the last; a change fails the run.

A run writes `daily-results.json` under KIT_CONFORMANCE_BASE. A row has exactly `cell`,
`harness`, `harness_version`, `passed`, `stub_log`, `work_dir` and `run_id`; `passed` is
`derive(row, state)`, a pure function of the files the row names, never an exit code. The
derivation is checked on fixture trees before anything starts, on every platform.

Every `kit run` of a cell passes `accept_args()`: `--accept-version` with the value of
`KIT_CONFORMANCE_ACCEPT_VERSION` when it is set, so the cells run on a version the contract
does not name yet. `harness_version` is the version the driver's probe reads for the binary
named by KIT_HARNESS_ARGV_OPENCODE, the one the cells run.

Prints `skip:` unless KIT_CONFORMANCE_BASE and KIT_HARNESS_ARGV_OPENCODE are set and the platform
is Windows. The base must be an existing folder.

Stdlib-runnable: `python test_daily_home.py`.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import zlib
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from test_conformance import (  # noqa: E402 - the sibling module, found through HERE
    SESSION_TIMEOUT_S,
    SRC,
    accept_args,
    find_run,
    kit,
    kit_env,
    policy_text,
    read_json,
    start_stub,
)
from test_guards import governed_hashes  # noqa: E402

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness_kit import harnesses  # noqa: E402

WINDOWS = os.name == 'nt'
BASE_ENV = 'KIT_CONFORMANCE_BASE'
ARGV_ENV = 'KIT_HARNESS_ARGV_OPENCODE'
HARNESS = 'opencode'
CELLS = (
    'daily-guard',
    'daily-interactive',
    'daily-no-key',
    'daily-ceiling',
    'daily-proxy',
    'daily-git',
)
# Only opencode's driver renders a daily home; the Claude Code driver runs no cell here.
CELLS_BY_HARNESS = {'claude-code': (), 'opencode': CELLS}
RESULTS = 'daily-results.json'
STATE_DIR = 'daily-state'
ROW_KEYS = ('cell', 'harness', 'harness_version', 'passed', 'stub_log', 'work_dir', 'run_id')
CANARY_RULES = ('canary.deny', 'canary.allow')
DENY_RULE = 'conformance-deny-shell'
PROMPT = 'Run each scripted tool call.'
# The daily file's key variable and its made-up test value; no provider ever sees either.
KEY_ENV = 'KIT_DAILY_CELL_KEY'
TEST_KEY = 'made-up-daily-cell-key-6f2c9a41d3'
CAPABILITY_NAME = 'KIT_RELAY_CAPABILITY'
MODEL_ID = 'cell/stub-model'
GIT_NAME = 'Daily Cell'
GIT_EMAIL = 'daily.cell@example.invalid'
PROXY_HOST = 'example.com'
ENV_FILE = 'env.txt'
PROCESSES_LEFT = 'processes-left.json'
DENY_MARKER = 'deny-shell.marker'
CEILING_MARKER = 'ceiling.marker'
# A shell call of opencode runs in PowerShell on Windows.
ENV_COMMAND = (
    '[Environment]::GetEnvironmentVariables() | ConvertTo-Json -Compress '
    f'| Out-File -Encoding utf8 {ENV_FILE}'
)
PROXY_COMMAND = f'curl.exe -s -o NUL https://{PROXY_HOST}'
GIT_COMMAND = 'git commit --allow-empty -m kit-cell'
RUN_USD = {'daily-ceiling': '0.000001'}
SERVED_WAIT_S = 150
SETTLE_S = 3.0
EXIT_WAIT_S = 90
LEFT_WAIT_S = 10
RUN_ID = '20261119T120000Z-0123456789ab'


def _shell(command: str) -> dict:
    return {'tool': 'shell', 'args': {'command': command}}


def stub_steps(cell: str) -> list[dict]:
    """The stub's script: the cell's calls in order, each request with tools taking the next."""
    if cell == 'daily-guard':
        calls = [f'echo probe > {DENY_MARKER}']
    elif cell == 'daily-no-key':
        calls = [ENV_COMMAND]
    elif cell == 'daily-ceiling':
        calls = [f'echo probe > {CEILING_MARKER}']
    elif cell == 'daily-proxy':
        calls = [PROXY_COMMAND]
    elif cell == 'daily-git':
        calls = [GIT_COMMAND]
    else:
        calls = [f'echo probe > {DENY_MARKER}', ENV_COMMAND, PROXY_COMMAND, GIT_COMMAND]
    return [*(_shell(c) for c in calls), {'text': 'done'}]


def daily_text(cell: str, listen_port: int, upstream_port: int) -> str:
    """The cell's daily file: `test` true, a loopback upstream, a made-up key variable."""
    run_usd = RUN_USD.get(cell, '100.0')
    # The numbers below are an example.
    return f"""\
daily = 1

[relay]
listen_port = {listen_port}
upstream_base = "http://127.0.0.1:{upstream_port}"
route = "/v1/chat/completions"
key_env = "{KEY_ENV}"
test = true
usage_include = true
default_model = "{MODEL_ID}"
upstream_timeout_s = 60

[relay.ceilings]
run_usd = {run_usd}
day_usd = 1000.0
month_usd = 10000.0

[[relay.model]]
id = "{MODEL_ID}"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 1.0
max_output_tokens = 4096

[git]
name = "{GIT_NAME}"
email = "{GIT_EMAIL}"
"""


# ---- deriving a row from its files


def _ndjson(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = []
    for text in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            line = json.loads(text) if text.strip() else None
        except ValueError:
            continue
        if isinstance(line, dict):
            lines.append(line)
    return lines


def _read_any_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def cell_journal(run_dir: Path) -> list[dict]:
    """The run's judgements but the canary's: its two rules and every line of its session."""
    lines = _ndjson(run_dir / 'journal.ndjson')
    canary = {line.get('session_id') for line in lines if line.get('rule') in CANARY_RULES}
    return [
        line
        for line in lines
        if line.get('rule') not in CANARY_RULES and line.get('session_id') not in canary
    ]


def _has(lines: list[dict], verdict: str, rule: str | None) -> bool:
    return any(
        x.get('act_kind') == 'shell' and x.get('verdict') == verdict and x.get('rule') == rule
        for x in lines
    )


def _relay_stats(record: dict) -> bool:
    stats = record.get('relay')
    return isinstance(stats, dict) and set(stats) == {
        'requests',
        'refused',
        'settled_usd',
        'stopped',
    }


def _canary(run_dir: Path) -> bool:
    return read_json(run_dir / 'canary' / 'canary.json').get('passed') is True


def _guard(run_dir: Path, record: dict, work: Path, state: Path) -> bool:
    denied = not (work / DENY_MARKER).exists() and _has(cell_journal(run_dir), 'deny', DENY_RULE)
    log = _ndjson(run_dir / 'relay-log.ndjson')
    forwarded = any(x.get('decision') == 'forwarded' for x in log)
    ledger = _ndjson(state / 'relay' / 'ledger.ndjson')
    run_id = run_dir.name
    kinds = {x.get('kind') for x in ledger if x.get('run_id') == run_id}
    return all(
        (_canary(run_dir), denied, forwarded, {'reserve', 'settle'} <= kinds, _relay_stats(record))
    )


def _files_under(*tops: Path) -> list[Path]:
    found = []
    for top in tops:
        if top.is_file():
            found.append(top)
        elif top.is_dir():
            found += [p for p in top.rglob('*') if p.is_file()]
    return found


def _no_key(row: dict, run_dir: Path, record: dict, work: Path, state: Path) -> bool:
    seen = _read_any_json(work / ENV_FILE)
    if not isinstance(seen, dict) or not record.get('home'):
        return False
    names = {str(k).upper() for k in seen}
    if CAPABILITY_NAME not in names or KEY_ENV in names:
        return False
    key = TEST_KEY.encode('ascii')
    tops = (Path(record['home']), work, run_dir, state / 'relay', Path(row['stub_log']))
    for path in _files_under(*tops):
        try:
            if key in path.read_bytes():
                return False
        except OSError:
            return False
    return True


def _ceiling(row: dict, run_dir: Path) -> bool:
    reached = _ndjson(Path(row['stub_log']))
    refused = any(x.get('reason') == 'ceiling_run' for x in _ndjson(run_dir / 'relay-log.ndjson'))
    return _canary(run_dir) and not reached and refused


def _proxy(row: dict, run_dir: Path) -> bool:
    log = _ndjson(run_dir / 'relay-log.ndjson')
    refused = any(
        x.get('reason') == 'proxy'
        and x.get('decision') == 'refused'
        and x.get('proxy_host') == PROXY_HOST
        for x in log
    )
    stub = _ndjson(Path(row['stub_log']))
    tunnel = any(
        'PROXY' in str(x.get('kind'))
        or 'CONNECT' in str(x.get('kind'))
        or PROXY_HOST in str(x.get('path'))
        for x in stub
    )
    return refused and not tunnel and _has(cell_journal(run_dir), 'allow', None)


def head_author(repo: Path) -> str | None:
    """`NAME <EMAIL>` of the author of the work tree's HEAD commit, read from its files."""
    git = repo / '.git'
    try:
        head = (git / 'HEAD').read_text(encoding='utf-8').strip()
        if head.startswith('ref: '):
            ref = head[len('ref: ') :]
            path = git / ref
            if path.is_file():
                sha = path.read_text(encoding='utf-8').strip()
            else:
                packed = (git / 'packed-refs').read_text(encoding='utf-8').splitlines()
                sha = next(x.split()[0] for x in packed if x.endswith(' ' + ref))
        else:
            sha = head
        data = zlib.decompress((git / 'objects' / sha[:2] / sha[2:]).read_bytes())
    except (OSError, ValueError, StopIteration, zlib.error):
        return None
    header, _, body = data.partition(b'\x00')
    if not header.startswith(b'commit '):
        return None
    for line in body.split(b'\n'):
        if line.startswith(b'author '):
            text = line[len(b'author ') :].decode('utf-8', 'replace')
            return text.rsplit(' ', 2)[0]
        if not line:
            break
    return None


def _git(work: Path) -> bool:
    return head_author(work) == f'{GIT_NAME} <{GIT_EMAIL}>'


def _no_opencode_left(folder: Path) -> bool:
    left = _read_any_json(folder / PROCESSES_LEFT)
    if not isinstance(left, list):
        return False
    for entry in left:
        image = entry.get('image') if isinstance(entry, dict) else None
        if not isinstance(image, str) or image.lower().startswith('opencode'):
            return False
    return True


def derive(row: dict, state: Path) -> bool:
    """Re-derive one row's `passed` from the files it names, by the cell table."""
    run_id = row.get('run_id')
    if not run_id:
        return False
    state = Path(state)
    run_dir = state / 'runs' / run_id
    record = read_json(run_dir / 'run.json')
    if not record:
        return False
    folder, work = Path(row['stub_log']).parent, Path(row['work_dir'])
    cell = row.get('cell')
    if cell == 'daily-guard':
        return _guard(run_dir, record, work, state)
    if cell == 'daily-no-key':
        return _no_key(row, run_dir, record, work, state)
    if cell == 'daily-ceiling':
        return _ceiling(row, run_dir)
    if cell == 'daily-proxy':
        return _proxy(row, run_dir)
    if cell == 'daily-git':
        return _git(work)
    if cell == 'daily-interactive':
        return all(
            (
                _guard(run_dir, record, work, state),
                _no_key(row, run_dir, record, work, state),
                _proxy(row, run_dir),
                _git(work),
                record.get('outcome') == 'ended',
                _no_opencode_left(folder),
            )
        )
    return False


# ---- fixture trees for the derivation (run on every platform, before any skip)

CANARY_SESSION = 'canary-session'
CELL_SESSION = 'cell-session'
GIT_CELLS = ('daily-git', 'daily-interactive')


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _lines(*items: dict) -> str:
    return ''.join(json.dumps(item) + '\n' for item in items)


def _judged(verdict: str, rule: str | None, session: str = CELL_SESSION) -> dict:
    return {'session_id': session, 'act_kind': 'shell', 'verdict': verdict, 'rule': rule}


def _journal_text(*items: dict) -> str:
    canary = (
        _judged('deny', 'canary.deny', CANARY_SESSION),
        _judged('allow', 'canary.allow', CANARY_SESSION),
    )
    return _lines(*canary, *items)


def _relay_line(decision: str, reason: str | None = None, host: str | None = None) -> dict:
    return {'decision': decision, 'reason': reason, 'status': 200, 'proxy_host': host}


def _commit(repo: Path, author: str) -> None:
    """A loose commit object and the branch HEAD names, as git writes them."""
    body = (
        'tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904\n'
        f'author {author} 1700000000 +0000\n'
        f'committer {author} 1700000000 +0000\n\nkit-cell\n'
    ).encode()
    data = b'commit ' + str(len(body)).encode('ascii') + b'\x00' + body
    import hashlib

    sha = hashlib.sha1(data).hexdigest()  # noqa: S324 - git's object name, no security use
    path = repo / '.git' / 'objects' / sha[:2] / sha[2:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zlib.compress(data))
    _write(repo / '.git' / 'HEAD', 'ref: refs/heads/main\n')
    _write(repo / '.git' / 'refs' / 'heads' / 'main', sha + '\n')


def make_row(cell: str, base: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the state root."""
    state, folder = base / 'state', base / 'cell'
    run_dir = state / 'runs' / RUN_ID
    home, work = folder / 'home', folder / 'work'
    work.mkdir(parents=True)
    _write(home / 'conf' / 'opencode.jsonc', '{}')
    record = {
        'run_id': RUN_ID,
        'outcome': 'ended',
        'home': str(home),
        'workdir': str(work),
        'relay': {'requests': 2, 'refused': 0, 'settled_usd': 0.1, 'stopped': False},
    }
    _write(run_dir / 'run.json', json.dumps(record))
    _write(run_dir / 'canary' / 'canary.json', json.dumps({'passed': True}))
    _write(folder / PROCESSES_LEFT, '[]')
    stub = [{'kind': 'POST', 'path': '/v1/chat/completions', 'decision': 'scripted'}]
    relay_log = [_relay_line('forwarded')]
    journal = []
    ledger = [
        {'kind': 'reserve', 'id': 'a', 'run_id': RUN_ID, 'usd': 0.1},
        {'kind': 'settle', 'id': 'a', 'run_id': RUN_ID, 'usd': 0.1},
    ]
    if cell in ('daily-guard', 'daily-interactive'):
        journal.append(_judged('deny', DENY_RULE))
    if cell in ('daily-no-key', 'daily-interactive'):
        seen = {CAPABILITY_NAME: 'a' * 64, 'Path': 'C:/bin'}
        (work / ENV_FILE).write_bytes(b'\xef\xbb\xbf' + json.dumps(seen).encode('utf-8'))
    if cell == 'daily-ceiling':
        stub, ledger = [], []
        relay_log = [_relay_line('refused', 'ceiling_run')]
    if cell in ('daily-proxy', 'daily-interactive'):
        relay_log.append(_relay_line('refused', 'proxy', PROXY_HOST))
        journal.append(_judged('allow', None))
    if cell in GIT_CELLS:
        _commit(work, f'{GIT_NAME} <{GIT_EMAIL}>')
    _write(run_dir / 'journal.ndjson', _journal_text(*journal))
    _write(run_dir / 'relay-log.ndjson', _lines(*relay_log))
    _write(state / 'relay' / 'ledger.ndjson', _lines(*ledger))
    if stub:
        _write(folder / 'stub.jsonl', _lines(*stub))
    row = {
        'cell': cell,
        'harness': HARNESS,
        'harness_version': '2.2.5',
        'passed': True,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': RUN_ID,
    }
    return row, state


def _run_dir(state: Path) -> Path:
    return state / 'runs' / RUN_ID


def _record(**over: object) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = _run_dir(state) / 'run.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record.update(over)
        _write(path, json.dumps(record))

    return change


def _run_file(name: str, text: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(_run_dir(state) / name, text)


def _state_file(rel: str, text: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(state / rel, text)


def _folder_file(name: str, text: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['stub_log']).parent / name, text)


def _work_file(name: str, text: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['work_dir']) / name, text)


def _home_file(rel: str, text: str) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        record = json.loads((_run_dir(state) / 'run.json').read_text(encoding='utf-8'))
        _write(Path(record['home']) / rel, text)

    return change


def _env_seen(**over: str) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = Path(row['work_dir']) / ENV_FILE
        seen = json.loads(path.read_text(encoding='utf-8-sig'))
        for key, value in over.items():
            if value is None:
                seen.pop(key, None)
            else:
                seen[key] = value
        _write(path, json.dumps(seen))

    return change


def _author(author: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _commit(Path(row['work_dir']), author)


_GUARD_BREAKS = [
    _run_file('canary/canary.json', '{"passed": false}'),
    _work_file(DENY_MARKER, 'probe'),
    _run_file('journal.ndjson', _journal_text(_judged('allow', None))),
    _run_file('relay-log.ndjson', _lines(_relay_line('refused', 'no_capability'))),
    _state_file('relay/ledger.ndjson', _lines({'kind': 'reserve', 'id': 'a', 'run_id': RUN_ID})),
    _state_file('relay/ledger.ndjson', _lines({'kind': 'settle', 'id': 'a', 'run_id': 'other'})),
    _record(relay=None),
    _record(relay={'requests': 1}),
]
_NO_KEY_BREAKS = [
    _env_seen(**{CAPABILITY_NAME: None}),
    _env_seen(**{KEY_ENV: 'x'}),
    _work_file('leak.txt', TEST_KEY),
    _home_file('xdg/data/log.txt', 'a ' + TEST_KEY),
    _run_file('canary/copied.txt', TEST_KEY),
    _state_file('relay/other.txt', TEST_KEY),
    _folder_file('stub.jsonl', json.dumps({'auth': TEST_KEY}) + '\n'),
    lambda row, state: (Path(row['work_dir']) / ENV_FILE).unlink(),
]
_PROXY_BREAKS = [
    _run_file('relay-log.ndjson', _lines(_relay_line('forwarded'))),
    _run_file('relay-log.ndjson', _lines(_relay_line('refused', 'proxy', 'other.example'))),
    _folder_file('stub.jsonl', json.dumps({'kind': 'CONNECT-refused', 'path': 'x'}) + '\n'),
    _run_file('journal.ndjson', _journal_text(_judged('deny', DENY_RULE))),
]
_GIT_BREAKS = [
    _author('Someone Else <someone@example.invalid>'),
    lambda row, state: (Path(row['work_dir']) / '.git' / 'HEAD').unlink(),
]
BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'daily-guard': _GUARD_BREAKS,
    'daily-no-key': _NO_KEY_BREAKS,
    'daily-ceiling': [
        _run_file('canary/canary.json', '{"passed": false}'),
        _folder_file('stub.jsonl', json.dumps({'kind': 'POST'}) + '\n'),
        _run_file('relay-log.ndjson', _lines(_relay_line('refused', 'ceiling_day'))),
    ],
    'daily-proxy': _PROXY_BREAKS,
    'daily-git': _GIT_BREAKS,
    'daily-interactive': [
        *_GUARD_BREAKS,
        *_NO_KEY_BREAKS,
        *_PROXY_BREAKS[:3],
        *_GIT_BREAKS,
        _record(outcome='launched'),
        _folder_file(PROCESSES_LEFT, '[{"pid": 7, "image": "opencode.exe"}]'),
        _folder_file(PROCESSES_LEFT, 'not json'),
    ],
}


def check_derive() -> None:
    """Every cell derives true from a passing tree, and false after each way it can break."""
    for cell in CELLS:
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            assert derive(row, state), f'{cell}: a passing tree derived false'
            assert set(row) == set(ROW_KEYS), row
        for index, broken in enumerate(BREAKS[cell]):
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, Path(tmp))
                broken(row, state)
                assert not derive(row, state), f'{cell}: break {index} derived true'
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            (_run_dir(state) / 'run.json').unlink()
            assert not derive(row, state), f'{cell}: no run derived true'
            row['run_id'] = None
            assert not derive(row, state), f'{cell}: no run id derived true'
    assert set(CELLS_BY_HARNESS[HARNESS]) == set(CELLS) and CELLS_BY_HARNESS['claude-code'] == ()


# ---- one cell on the real harness


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _served(log: Path, index: int) -> bool:
    for line in _ndjson(log):
        step = line.get('step_index')
        if line.get('decision') == 'scripted' and isinstance(step, int) and step >= index:
            return True
    return False


def _wait_served(log: Path, index: int, timeout_s: float = SERVED_WAIT_S) -> bool:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if _served(log, index):
            return True
        time.sleep(0.2)
    return False


def _wait_quiet(console, quiet_s: float = 1.5, limit_s: float = 10.0) -> None:
    """Wait until the interface has drawn nothing for `quiet_s` seconds, or `limit_s` passed."""
    end = time.monotonic() + limit_s
    while time.monotonic() < end and time.monotonic() - console.last_output < quiet_s:
        time.sleep(0.1)


def _work_folder(cell: str, folder: Path, env: dict) -> Path:
    if cell not in GIT_CELLS:
        work = folder / 'work'
        work.mkdir(parents=True)
        return work
    repo = folder / 'repo'
    repo.mkdir(parents=True)
    clean = {k: v for k, v in env.items() if not k.upper().startswith('GIT_')}
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(repo), 'init', '-q'],  # noqa: S607 - PATH git
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=clean,
    )
    return repo


def _run_headless(folder: Path, head: list[str], argv: list[str], env: dict, work: Path) -> None:
    with open(folder / 'kit.stdout', 'wb') as out, open(folder / 'kit.stderr', 'wb') as err:
        proc = subprocess.run(  # noqa: S603 - argv built by the cell, no shell
            [sys.executable, '-m', 'harness_kit', *head, *argv],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            env=env,
            cwd=str(work),
            timeout=SESSION_TIMEOUT_S,
            check=False,
        )
    (folder / 'kit-exit.json').write_text(
        json.dumps({'exit_code': proc.returncode}), encoding='utf-8'
    )


def _run_interactive(folder: Path, head: list[str], env: dict, work: Path, steps: int) -> list[str]:
    import conpty

    problems: list[str] = []
    argv = [sys.executable, '-m', 'harness_kit', *head, '--standalone', '--prompt', PROMPT]
    console = conpty.PseudoConsole(argv, env, work, folder / 'screen.log')
    try:
        if not _wait_served(folder / 'stub.jsonl', steps - 1):
            problems.append('the stub did not serve the last step')
        time.sleep(SETTLE_S)
        _wait_quiet(console)
        console.write(conpty.CTRL_C)
        code = console.wait(EXIT_WAIT_S)
        left = console.left()
        end = time.monotonic() + LEFT_WAIT_S
        while left and time.monotonic() < end:
            time.sleep(0.2)
            left = console.left()
        (folder / PROCESSES_LEFT).write_text(json.dumps(left), encoding='utf-8')
        (folder / 'kit-exit.json').write_text(json.dumps({'exit_code': code}), encoding='utf-8')
        if code is None:
            problems.append('kit run did not end after one Ctrl+C')
    finally:
        console.close()
    return problems


def run_cell(
    cell: str, version: str | None, base: Path, policy: Path, argv_env: dict
) -> tuple[dict, list[str]]:
    """Run one cell: its row, with `passed` derived from the files it names, and its problems."""
    state = base / STATE_DIR
    folder = base / 'daily-cells' / f'{HARNESS}-{cell}-{uuid.uuid4().hex[:8]}'
    folder.mkdir(parents=True)
    env = kit_env({'KIT_STATE_ROOT': str(state), **argv_env, KEY_ENV: TEST_KEY})
    work = _work_folder(cell, folder, env).resolve()
    row = {
        'cell': cell,
        'harness': HARNESS,
        'harness_version': version,
        'passed': False,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': None,
    }
    problems: list[str] = []
    home = folder / 'home'
    steps = stub_steps(cell)
    stub, port = start_stub(folder, steps, env)
    try:
        daily_file = folder / 'daily.toml'
        daily_file.write_text(daily_text(cell, free_port(), port), encoding='utf-8')
        rendered = kit(
            'home',
            'render',
            '--harness',
            HARNESS,
            '--dir',
            str(home),
            '--daily',
            str(daily_file),
            env=env,
        )
        head = ['run', '--harness', HARNESS, *accept_args()]
        head += ['--mode', 'interactive'] if cell == 'daily-interactive' else []
        head += ['--home', str(home), '--workdir', str(work), '--policy', str(policy), '--']
        if cell == 'daily-interactive':
            problems += [
                f'{HARNESS}/{cell}: {p}'
                for p in _run_interactive(folder, head, env, work, len(steps))
            ]
        else:
            argv = harnesses.get(HARNESS).canary_argv(PROMPT, json.loads(rendered))
            _run_headless(folder, head, argv, env, work)
    except Exception as exc:  # a failed cell is a row, not a crash of the suite
        problems.append(f'{HARNESS}/{cell}: the session failed: {type(exc).__name__}: {exc}')
    finally:
        stub.kill()
        stub.wait()
    row['run_id'] = find_run(state, work)
    try:
        row['passed'] = derive(row, state)
    except Exception as exc:
        problems.append(f'{HARNESS}/{cell}: derivation failed: {type(exc).__name__}: {exc}')
    return row, problems


def main() -> int:
    check_derive()
    base_raw = os.environ.get(BASE_ENV)
    argv_raw = os.environ.get(ARGV_ENV)
    if not base_raw or not argv_raw:
        names = [n for n, v in ((BASE_ENV, base_raw), (ARGV_ENV, argv_raw)) if not v]
        print(f'skip: the daily cells need {" and ".join(names)}')
        return 0
    if not WINDOWS:
        print('skip: the daily cells run on Windows only')
        return 0
    base = Path(base_raw)
    if not base.is_dir():
        print(f'FAIL: {BASE_ENV} is not an existing folder')
        return 1
    base = base.resolve()
    before = governed_hashes()
    argv_env = {ARGV_ENV: argv_raw}
    policy = base / 'daily-policy.toml'
    policy.write_text(policy_text(base), encoding='utf-8')
    rows: list[dict] = []
    problems: list[str] = []
    try:
        version = harnesses.get(HARNESS).version(kit_env(argv_env))
        for cell in CELLS_BY_HARNESS[HARNESS]:
            row, found = run_cell(cell, version, base, policy, argv_env)
            rows.append(row)
            problems += found
    finally:
        (base / RESULTS).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    after = governed_hashes()
    if after != before:
        problems.append(f'the account governed files changed: {before} -> {after}')
    print(json.dumps(rows, indent=2))
    bad = [f'{r["harness"]}/{r["cell"]}' for r in rows if not r['passed']]
    if bad or problems:
        print('FAIL: ' + '; '.join(bad + problems))
        return 1
    print(f'ok: daily cells passed on {HARNESS} ({len(rows)} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

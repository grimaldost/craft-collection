#!/usr/bin/env python3
"""Permission cells: opencode's native permissions rendered from a policy, on the real harness.

Every cell renders a test home with `kit home render --policy FILE` against a stub the cell
runs (`kit stub`, its log `stub.jsonl` in the cell's folder), under a version 4 policy whose
rules allow every act (it holds no rule), so only opencode's native layer refuses, and whose
`[permissions]` section is the cell's. Every cell starts with `kit run` under the state root
`<base>/permissions-state`; the stub scripts one call, then text. A cell leaves the canary's
two journal lines out of what it reads.

- perm-shell-deny: `shell` `echo probe > perm-deny*` deny. The marker is absent and the
  request after the call carries opencode's refusal.
- perm-shell-allow: `shell` `echo probe > perm-allow*` allow, default `ask`. The marker is
  present.
- perm-edit-deny: `edit` `locked/*` deny. A `write` to `work/locked/x.txt` is refused (the
  request after it carries the refusal) and the file is absent. opencode 2.2.5 matches an `edit`
  rule against the path relative to the session's folder, here `locked/x.txt`, which
  `*/locked/*` does not match.
- perm-webfetch-allow (the control): `webfetch` `*` allow. A `webfetch` of a loopback listener
  the cell runs: the listener received the request. Should opencode refuse a loopback fetch by
  itself (the call answered, without a permission refusal, and nothing received), the row
  carries `accepted_failure` `loopback-fetch-refused`.
- perm-webfetch-deny: `webfetch` `*` deny. The same `webfetch`: the request after the call
  carries opencode's refusal, and the listener received nothing. opencode 2.2.5 offers no tool
  whose every resource is denied, so its refusal here reads `No tool named "webfetch"`.
- perm-external-deny: `external_directory` `*` deny. A `write` outside the working folder (in
  the cell's folder) is refused and the file absent.
- perm-ask-headless: `shell` `echo probe > perm-ask*` ask; `opencode run` without `--auto`.
  The marker is absent and the session ended (`outcome` `ended`).
- perm-ask-interactive: the same rule, `kit run --mode interactive` under a Windows pseudo
  console. The marker is absent and no request with tools reached the stub in the 10 s after
  the one the call answered (`ask-wait.json` records the window); the cell then ends the
  session.
- perm-default-deny-allow: default `deny`; `shell` `echo probe > perm-dda*` allow, with allows
  for the canary's two commands. The marker is present (the last matching rule wins).

A run writes `permissions-results.json` under KIT_CONFORMANCE_BASE. A row has exactly `cell`,
`harness`, `harness_version`, `passed`, `stub_log`, `work_dir`, `run_id` and `journaled`
(whether the run's journal, the canary's lines left out, holds a verdict for the cell's call:
for a call the native layer refuses, whether opencode asked the kit's hook first), and
`accepted_failure` only on the failed control row its reason names; `passed` is
`derive(row, state)`, a pure function of the files the row names, never an exit code. The
derivation is checked on fixture trees before anything starts, on every platform. The
account's governed files are hashed before the first cell and after the last.

Every `kit run` of a cell passes `accept_args()`: `--accept-version` with the value of
`KIT_CONFORMANCE_ACCEPT_VERSION` when it is set, so the cells run on a version the contract
does not name yet. `harness_version` is the version the driver's probe reads for the binary
named by KIT_HARNESS_ARGV_OPENCODE, the one the cells run.

Prints `skip:` unless KIT_CONFORMANCE_BASE and KIT_HARNESS_ARGV_OPENCODE are set and the platform
is Windows. The base must be an existing folder.

Stdlib-runnable: `python test_permissions.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
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
    'perm-shell-deny',
    'perm-shell-allow',
    'perm-edit-deny',
    'perm-webfetch-allow',
    'perm-webfetch-deny',
    'perm-external-deny',
    'perm-ask-headless',
    'perm-ask-interactive',
    'perm-default-deny-allow',
)
# Only the opencode driver renders the section; the Claude Code driver runs no cell here.
CELLS_BY_HARNESS = {'claude-code': (), 'opencode': CELLS}
RESULTS = 'permissions-results.json'
STATE_DIR = 'permissions-state'
ROW_KEYS = (
    'cell',
    'harness',
    'harness_version',
    'passed',
    'stub_log',
    'work_dir',
    'run_id',
    'journaled',
)
CANARY_RULES = ('canary.deny', 'canary.allow')
ACCEPTED = 'loopback-fetch-refused'
CONTROL = 'perm-webfetch-allow'
PROMPT = 'Run the scripted tool call.'
MODEL = 'stub/stub-model'
CALL_ID = 'call_cell'
# opencode 2.2.5's answers to a call its permissions refuse: `Permission denied: ACTION` for a
# configured deny, `No tool named "TOOL" ...` for a tool a deny of every resource removes from
# the offered tools, the reason of a `tool.use` statement, and the one a headless run gives
# when it cannot ask.
REFUSALS = (
    'Permission denied',
    'No tool named',
    'Blocked by',
    'cannot ask the user for permission',
)
ASK_WAIT = 'ask-wait.json'
ASK_QUIET_S = 10.0
SERVED_WAIT_S = 150
SETTLE_S = 3.0
EXIT_WAIT_S = 30
LEFT_WAIT_S = 10
PROCESSES_LEFT = 'processes-left.json'
KIT_EXIT = 'kit-exit.json'
RUN_ID = '20261122T120000Z-0123456789ab'
LISTENER = 'listener'
OUTSIDE = 'outside'
CANARY_ALLOWS = (
    ('shell', 'echo probe > deny-*', 'allow'),
    ('shell', 'echo probe > allow-*', 'allow'),
)
# Each cell: its section (default, rules), the call's act kind, and its marker or file.
SECTIONS: dict[str, tuple[str, tuple[tuple[str, str, str], ...]]] = {
    'perm-shell-deny': ('allow', (('shell', 'echo probe > perm-deny*', 'deny'),)),
    'perm-shell-allow': ('ask', (('shell', 'echo probe > perm-allow*', 'allow'),)),
    'perm-edit-deny': ('allow', (('edit', 'locked/*', 'deny'),)),
    'perm-webfetch-allow': ('allow', (('webfetch', '*', 'allow'),)),
    'perm-webfetch-deny': ('allow', (('webfetch', '*', 'deny'),)),
    'perm-external-deny': ('allow', (('external_directory', '*', 'deny'),)),
    'perm-ask-headless': ('allow', (('shell', 'echo probe > perm-ask*', 'ask'),)),
    'perm-ask-interactive': ('allow', (('shell', 'echo probe > perm-ask*', 'ask'),)),
    'perm-default-deny-allow': (
        'deny',
        (('shell', 'echo probe > perm-dda*', 'allow'), *CANARY_ALLOWS),
    ),
}
MARKERS = {
    'perm-shell-deny': 'perm-deny.marker',
    'perm-shell-allow': 'perm-allow.marker',
    'perm-ask-headless': 'perm-ask.marker',
    'perm-ask-interactive': 'perm-ask.marker',
    'perm-default-deny-allow': 'perm-dda.marker',
}
CALL_KIND = {
    'perm-edit-deny': 'file_write',
    'perm-external-deny': 'file_write',
    'perm-webfetch-allow': 'other',
    'perm-webfetch-deny': 'other',
}


def policy_text(base: Path, cell: str) -> str:
    """A version 4 policy with no rule (every act allowed) and the cell's section."""
    default, rules = SECTIONS[cell]
    lines = [
        'version = 4',
        '',
        '[launcher]',
        f'test_roots = [{json.dumps(str(base))}]',
        'forbidden_roots = []',
        '',
        '[permissions]',
        f'default = "{default}"',
        '',
    ]
    for action, resource, effect in rules:
        lines += [
            '[[permissions.rule]]',
            f'action = "{action}"',
            f'resource = {json.dumps(resource)}',
            f'effect = "{effect}"',
            '',
        ]
    return '\n'.join(lines)


def _shell(command: str) -> dict:
    return {'tool': 'shell', 'id': CALL_ID, 'args': {'command': command}}


def call_step(cell: str, work: Path, folder: Path, listen: int | None) -> dict:
    """The one scripted call of a cell."""
    if cell in MARKERS:
        return _shell(f'echo probe > {MARKERS[cell]}')
    if cell == 'perm-edit-deny':
        target = work / 'locked' / 'x.txt'
        return {'tool': 'write', 'id': CALL_ID, 'args': {'path': str(target), 'content': 'probe'}}
    if cell == 'perm-external-deny':
        target = folder / OUTSIDE / 'x.txt'
        return {'tool': 'write', 'id': CALL_ID, 'args': {'path': str(target), 'content': 'probe'}}
    url = f'http://127.0.0.1:{listen}/probe'
    return {'tool': 'webfetch', 'id': CALL_ID, 'args': {'url': url, 'format': 'text'}}


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


def journaled(row: dict, state: Path) -> bool:
    """Whether the run's journal, the canary's lines left out, holds a verdict for the call."""
    run_id = row.get('run_id')
    if not run_id:
        return False
    kind = CALL_KIND.get(row.get('cell'), 'shell')
    lines = cell_journal(Path(state) / 'runs' / run_id)
    return any(line.get('act_kind') == kind for line in lines)


def tool_answer(log: Path, call_id: str = CALL_ID) -> str | None:
    """The text a request to the stub carries as the answer to the call `call_id`."""
    for line in _ndjson(log):
        body = line.get('body')
        messages = body.get('messages') if isinstance(body, dict) else None
        for message in messages if isinstance(messages, list) else []:
            if isinstance(message, dict) and message.get('tool_call_id') == call_id:
                content = message.get('content')
                return content if isinstance(content, str) else json.dumps(content)
    return None


def refused(log: Path) -> bool:
    answer = tool_answer(log) or ''
    return any(text in answer for text in REFUSALS)


def _received(folder: Path) -> bool:
    return bool(_ndjson(folder / LISTENER / 'stub.jsonl'))


def _quiet(folder: Path, log: Path) -> bool:
    """`ask-wait.json` spans at least 10 s from the request the call answered, and no request
    with tools reached the stub inside that window."""
    wait = _read_any_json(folder / ASK_WAIT)
    if not isinstance(wait, dict):
        return False
    start, end = wait.get('served_t'), wait.get('checked_t')
    if not all(isinstance(x, (int, float)) for x in (start, end)) or end - start < ASK_QUIET_S:
        return False
    lines = _ndjson(log)
    served = [x for x in lines if x.get('decision') == 'scripted' and x.get('step_index') == 0]
    if len(served) != 1 or served[0].get('t') != start:
        return False
    later = [
        x
        for x in lines
        if x.get('decision') == 'scripted'
        and isinstance(x.get('t'), (int, float))
        and start < x['t'] <= end
    ]
    return not later


def derive(row: dict, state: Path) -> bool:
    """Re-derive one row's `passed` from the files it names, by the cell table."""
    run_id = row.get('run_id')
    if not run_id:
        return False
    run_dir = Path(state) / 'runs' / run_id
    record = read_json(run_dir / 'run.json')
    if not record or read_json(run_dir / 'canary' / 'canary.json').get('passed') is not True:
        return False
    cell = row.get('cell')
    log = Path(row['stub_log'])
    folder, work = log.parent, Path(row['work_dir'])
    marker = work / MARKERS.get(cell, 'no-marker')
    if cell == 'perm-shell-deny':
        return not marker.exists() and refused(log)
    if cell in ('perm-shell-allow', 'perm-default-deny-allow'):
        return marker.is_file()
    if cell == 'perm-edit-deny':
        return not (work / 'locked' / 'x.txt').exists() and refused(log)
    if cell == 'perm-webfetch-allow':
        return _received(folder)
    if cell == 'perm-webfetch-deny':
        return not _received(folder) and refused(log)
    if cell == 'perm-external-deny':
        return not (folder / OUTSIDE / 'x.txt').exists() and refused(log)
    if cell == 'perm-ask-headless':
        return not marker.exists() and record.get('outcome') == 'ended'
    if cell == 'perm-ask-interactive':
        return not marker.exists() and _quiet(folder, log)
    return False


def accepted_failure(row: dict) -> str | None:
    """The reason a failed control row carries, when opencode refused the loopback fetch by
    itself: the call was answered without a permission refusal and the listener got nothing."""
    if row.get('cell') != CONTROL or row.get('passed'):
        return None
    log = Path(row['stub_log'])
    answer = tool_answer(log)
    if answer is None or refused(log) or _received(log.parent):
        return None
    return ACCEPTED


# ---- fixture trees for the derivation (run on every platform, before any skip)

CANARY_SESSION = 'canary-session'
CELL_SESSION = 'cell-session'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _lines(*items: dict) -> str:
    return ''.join(json.dumps(item) + '\n' for item in items)


def _judged(kind: str, verdict: str, rule: str | None, session: str = CELL_SESSION) -> dict:
    return {'session_id': session, 'act_kind': kind, 'verdict': verdict, 'rule': rule}


def _canary_lines() -> tuple[dict, dict]:
    return (
        _judged('shell', 'deny', 'canary.deny', CANARY_SESSION),
        _judged('shell', 'allow', 'canary.allow', CANARY_SESSION),
    )


def _request(index: int | None, t: float, answer: str | None = None) -> dict:
    messages = []
    if answer is not None:
        messages = [{'role': 'tool', 'tool_call_id': CALL_ID, 'content': answer}]
    return {
        'kind': 'POST',
        'decision': 'scripted',
        'step_index': index,
        't': t,
        'body': {'tools': [{}], 'messages': messages},
    }


def make_row(cell: str, base: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the state root."""
    state, folder = base / 'state', base / 'cell'
    run_dir = state / 'runs' / RUN_ID
    work = folder / 'work'
    work.mkdir(parents=True)
    record = {'run_id': RUN_ID, 'outcome': 'ended', 'workdir': str(work)}
    kind = CALL_KIND.get(cell, 'shell')
    stub = [_request(0, 100.0)]
    lines = [*_canary_lines(), _judged(kind, 'allow', None)]
    if cell == 'perm-webfetch-deny':
        stub.append(_request(1, 101.0, 'No tool named "webfetch" is currently available.'))
    elif cell in ('perm-shell-deny', 'perm-edit-deny', 'perm-external-deny'):
        stub.append(_request(1, 101.0, 'Permission denied: shell'))
    elif cell in ('perm-shell-allow', 'perm-default-deny-allow'):
        _write(work / MARKERS[cell], 'probe')
        stub.append(_request(1, 101.0, ''))
    elif cell == 'perm-webfetch-allow':
        _write(folder / LISTENER / 'stub.jsonl', _lines({'kind': 'GET', 'path': '/probe'}))
        stub.append(_request(1, 101.0, 'stub: no such path'))
    elif cell == 'perm-ask-headless':
        stub.append(_request(1, 101.0, 'Permission shell needs approval'))
    elif cell == 'perm-ask-interactive':
        _write(folder / ASK_WAIT, json.dumps({'served_t': 100.0, 'checked_t': 110.5}))
        stub.append(_request(1, 111.0, 'rejected'))
    _write(run_dir / 'run.json', json.dumps(record))
    _write(run_dir / 'canary' / 'canary.json', json.dumps({'passed': True}))
    _write(run_dir / 'journal.ndjson', _lines(*lines))
    _write(folder / 'stub.jsonl', _lines(*stub))
    row = {
        'cell': cell,
        'harness': HARNESS,
        'harness_version': '2.2.5',
        'passed': True,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': RUN_ID,
        'journaled': True,
    }
    return row, state


def _folder(row: dict) -> Path:
    return Path(row['stub_log']).parent


def _plant(rel: str, text: str = 'probe') -> Callable[[dict, Path], None]:
    return lambda row, state: _write(_folder(row) / rel, text)


def _drop(rel: str) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = _folder(row) / rel
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    return change


def _stub(*items: dict) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['stub_log']), _lines(*items))


def _record(**over: object) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = state / 'runs' / RUN_ID / 'run.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record.update(over)
        _write(path, json.dumps(record))

    return change


def _no_canary(row: dict, state: Path) -> None:
    _write(state / 'runs' / RUN_ID / 'canary' / 'canary.json', json.dumps({'passed': False}))


ANSWERED = _stub(_request(0, 100.0), _request(1, 101.0, 'Ran it.'))
BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'perm-shell-deny': [_plant('work/perm-deny.marker'), ANSWERED, _no_canary],
    'perm-shell-allow': [_drop('work/perm-allow.marker'), _no_canary],
    'perm-edit-deny': [_plant('work/locked/x.txt'), ANSWERED],
    'perm-webfetch-allow': [_drop(LISTENER)],
    'perm-webfetch-deny': [_plant(f'{LISTENER}/stub.jsonl', _lines({'kind': 'GET'})), ANSWERED],
    'perm-external-deny': [_plant(f'{OUTSIDE}/x.txt'), ANSWERED],
    'perm-ask-headless': [_plant('work/perm-ask.marker'), _record(outcome='launched')],
    'perm-ask-interactive': [
        _plant('work/perm-ask.marker'),
        _plant(ASK_WAIT, json.dumps({'served_t': 100.0, 'checked_t': 105.0})),
        _drop(ASK_WAIT),
        _stub(_request(0, 100.0), _request(1, 104.0, 'Ran it.')),
        _stub(_request(0, 99.0), _request(1, 111.0, 'x')),
    ],
    'perm-default-deny-allow': [_drop('work/perm-dda.marker')],
}


def check_derive() -> None:
    """Every cell derives true from a passing tree, and false after each way it can break."""
    for cell in CELLS:
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            assert derive(row, state), f'{cell}: a passing tree derived false'
            assert set(row) == set(ROW_KEYS), row
            assert journaled(row, state) is True, cell
            assert accepted_failure(row) is None, cell
        for index, broken in enumerate(BREAKS[cell]):
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, Path(tmp))
                broken(row, state)
                assert not derive(row, state), f'{cell}: break {index} derived true'
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            (state / 'runs' / RUN_ID / 'run.json').unlink()
            assert not derive(row, state), f'{cell}: no run derived true'
            row['run_id'] = None
            assert not derive(row, state) and journaled(row, state) is False, cell
    with tempfile.TemporaryDirectory() as tmp:
        row, state = make_row('perm-shell-deny', Path(tmp))
        (state / 'runs' / RUN_ID / 'journal.ndjson').write_text(
            _lines(*_canary_lines()), encoding='utf-8'
        )
        assert journaled(row, state) is False
    with tempfile.TemporaryDirectory() as tmp:
        row, state = make_row(CONTROL, Path(tmp))
        _drop(LISTENER)(row, state)
        row['passed'] = derive(row, state)
        assert accepted_failure(row) == ACCEPTED
        _stub(_request(0, 100.0), _request(1, 101.0, 'Permission denied: webfetch'))(row, state)
        assert accepted_failure(row) is None
        _stub(_request(0, 100.0))(row, state)
        assert accepted_failure(row) is None
    assert set(CELLS_BY_HARNESS[HARNESS]) == set(CELLS) and CELLS_BY_HARNESS['claude-code'] == ()
    assert set(SECTIONS) == set(CELLS)


# ---- running the cells on the real harness


def _headless(auto: bool = True) -> list[str]:
    head = ['run', '--standalone', '--format', 'json']
    return [*head, *(['--auto'] if auto else []), '--model', MODEL, PROMPT]


def _kit_run(folder: Path, home: Path, work: Path, policy: Path, env: dict, argv: list[str]):
    head = ['run', '--harness', HARNESS, *accept_args(), '--home', str(home)]
    head += ['--workdir', str(work), '--policy', str(policy), '--']
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
    (folder / KIT_EXIT).write_text(json.dumps({'exit_code': proc.returncode}), encoding='utf-8')


def _served_t(log: Path) -> float | None:
    for line in _ndjson(log):
        if line.get('decision') == 'scripted' and line.get('step_index') == 0:
            t = line.get('t')
            return float(t) if isinstance(t, (int, float)) else None
    return None


def _interactive(folder: Path, home: Path, work: Path, policy: Path, env: dict) -> list[str]:
    """Run the ask cell under a pseudo console; its problems."""
    import conpty

    problems: list[str] = []
    head = ['run', '--harness', HARNESS, *accept_args(), '--mode', 'interactive']
    head += ['--home', str(home), '--workdir', str(work), '--policy', str(policy), '--']
    argv = [sys.executable, '-m', 'harness_kit', *head, '--standalone', '--prompt', PROMPT]
    console = conpty.PseudoConsole(argv, env, work, folder / 'screen.log')
    try:
        log = folder / 'stub.jsonl'
        end = time.monotonic() + SERVED_WAIT_S
        served = _served_t(log)
        while served is None and time.monotonic() < end:
            time.sleep(0.2)
            served = _served_t(log)
        if served is None:
            problems.append('the call was never served')
        else:
            time.sleep(max(0.0, served + ASK_QUIET_S + 0.5 - time.time()))
            wait = {'served_t': served, 'checked_t': round(time.time(), 3)}
            (folder / ASK_WAIT).write_text(json.dumps(wait), encoding='utf-8')
        code = None
        for key in (conpty.CTRL_C, conpty.CTRL_C, '\x1b', conpty.CTRL_C):
            console.write(key)
            code = console.wait(EXIT_WAIT_S)
            if code is not None:
                break
        left = console.left()
        stop = time.monotonic() + LEFT_WAIT_S
        while left and time.monotonic() < stop:
            time.sleep(0.2)
            left = console.left()
        (folder / PROCESSES_LEFT).write_text(json.dumps(left), encoding='utf-8')
        (folder / KIT_EXIT).write_text(json.dumps({'exit_code': code}), encoding='utf-8')
        if code is None:
            problems.append('kit run did not end after the keys the cell wrote')
    finally:
        console.close()
    return problems


def run_cell(cell: str, version: str | None, base: Path, argv_env: dict) -> tuple[dict, list[str]]:
    """Run one cell: its row, with `passed` derived from the files it names, and its problems."""
    state = base / STATE_DIR
    folder = base / 'permission-cells' / f'{HARNESS}-{cell}-{uuid.uuid4().hex[:8]}'
    work = folder / 'work'
    work.mkdir(parents=True)
    work = work.resolve()
    folder = folder.resolve()
    env = kit_env({'KIT_STATE_ROOT': str(state), **argv_env})
    row = {
        'cell': cell,
        'harness': HARNESS,
        'harness_version': version,
        'passed': False,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': None,
        'journaled': False,
    }
    problems: list[str] = []
    policy = folder / 'policy.toml'
    policy.write_text(policy_text(base, cell), encoding='utf-8')
    stubs: list[subprocess.Popen] = []
    try:
        listen = None
        if cell in CALL_KIND and CALL_KIND[cell] == 'other':
            (folder / LISTENER).mkdir()
            listener, listen = start_stub(folder / LISTENER, [], env)
            stubs.append(listener)
        steps = [call_step(cell, work, folder, listen), {'text': 'done'}]
        stub, port = start_stub(folder, steps, env)
        stubs.append(stub)
        home = folder / 'home'
        render = ['home', 'render', '--harness', HARNESS, '--dir', str(home)]
        kit(*render, '--endpoint', f'http://127.0.0.1:{port}', '--policy', str(policy), env=env)
        if cell == 'perm-ask-interactive':
            problems += [
                f'{HARNESS}/{cell}: {p}' for p in _interactive(folder, home, work, policy, env)
            ]
        else:
            _kit_run(folder, home, work, policy, env, _headless(cell != 'perm-ask-headless'))
    except Exception as exc:  # a failed cell is a row, not a crash of the suite
        problems.append(f'{HARNESS}/{cell}: the cell failed: {type(exc).__name__}: {exc}')
    finally:
        for proc in stubs:
            proc.kill()
            proc.wait()
    row['run_id'] = find_run(state, work)
    try:
        row['passed'] = derive(row, state)
        row['journaled'] = journaled(row, state)
        reason = accepted_failure(row)
        if reason is not None:
            row['accepted_failure'] = reason
    except Exception as exc:
        problems.append(f'{HARNESS}/{cell}: derivation failed: {type(exc).__name__}: {exc}')
    return row, problems


def main() -> int:
    check_derive()
    base_raw = os.environ.get(BASE_ENV)
    argv_raw = os.environ.get(ARGV_ENV)
    if not base_raw or not argv_raw:
        names = [n for n, v in ((BASE_ENV, base_raw), (ARGV_ENV, argv_raw)) if not v]
        print(f'skip: the permission cells need {" and ".join(names)}')
        return 0
    if not WINDOWS:
        print('skip: the permission cells run on Windows only')
        return 0
    base = Path(base_raw)
    if not base.is_dir():
        print(f'FAIL: {BASE_ENV} is not an existing folder')
        return 1
    base = base.resolve()
    before = governed_hashes()
    argv_env = {ARGV_ENV: argv_raw}
    rows: list[dict] = []
    problems: list[str] = []
    try:
        version = harnesses.get(HARNESS).version(kit_env(argv_env))
        for cell in CELLS_BY_HARNESS[HARNESS]:
            row, found = run_cell(cell, version, base, argv_env)
            rows.append(row)
            problems += found
    finally:
        (base / RESULTS).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    after = governed_hashes()
    if after != before:
        problems.append(f'the account governed files changed: {before} -> {after}')
    print(json.dumps(rows, indent=2))
    bad = [
        f'{r["harness"]}/{r["cell"]}'
        for r in rows
        if not r['passed'] and r.get('accepted_failure') != ACCEPTED
    ]
    if bad or problems:
        print('FAIL: ' + '; '.join(bad + problems))
        return 1
    accepted = [r['cell'] for r in rows if r.get('accepted_failure')]
    note = f'; accepted failure: {", ".join(accepted)} ({ACCEPTED})' if accepted else ''
    print(f'ok: permission cells passed on {HARNESS} ({len(rows)} cells{note})')
    return 0


if __name__ == '__main__':
    sys.exit(main())

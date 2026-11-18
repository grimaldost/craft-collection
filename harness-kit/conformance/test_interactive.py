#!/usr/bin/env python3
"""Interactive cells: opencode's interface under `kit run --mode interactive`, against a stub model.

Each cell renders a test home with `kit home render` and starts
`kit run --mode interactive -- --standalone --prompt TEXT` under a Windows pseudo console
(`conpty.py`), which puts kit in a Job Object of its own. The stub scripts the cell's calls; once
it served the last step the cell writes one Ctrl+C, which ends the session, and then reads the
files. The policy is the conformance base policy (`test_conformance.policy_text`). Every
`kit run` uses the state root `<base>/interactive-state`.

- interactive-guard: a call the base policy denies, then an allowed call, then text. The canary
  passed; the denied call's marker is absent and the allowed one's present; the run's journal
  holds both verdicts; a request after the denied call carries the rule's reason;
  `home-hashes.json` equals the home's watched files; `outcome` is `ended`; no opencode process
  of the cell is left in its job once kit returned (`processes-left.json`).
- interactive-identity: a shell call writes the names and values of its environment to
  `env.txt`. `KIT_RUN_ID` holds the run id, and every isolation name kit run set for the session
  (the `KIT_`, `GIT_`, `OPENCODE_` and `XDG_` names, the proxy variables, `GH_CONFIG_DIR` and the
  profile and temporary-folder variables, recomputed by the cell as `build_env` does, into
  `expected-env.json`) holds the value kit set.
- interactive-subfolder: an allowed call, the working folder a subfolder of a git work tree
  with no remote. The call ran: its marker lies in the working folder, under the run's
  `work_tree_top`.
- interactive-switch-denied: a headless `kit run` first makes a second test folder known to the
  home; then, in the interface, Ctrl+O opens the open dialog, the cell types the folder's name
  and Enter, which opens a session there, and types a prompt whose scripted shell call is
  denied by `launcher.workdir`; its marker is absent. The cell also writes the name, size and
  modification time of every file under the home's `xdg/config/` before the switch, after it
  and after the call (`xdg-config-*.json`).

The canary's lines (rules `canary.deny` and `canary.allow`, and every line of its session) are
left out of every count. The account's governed files are hashed before the first cell and
after the last; a change fails the run.

A run writes `interactive-results.json` under KIT_CONFORMANCE_BASE. A row has exactly `cell`,
`harness`, `harness_version`, `passed`, `stub_log`, `work_dir` and `run_id`; `passed` is
`derive(row, state)`, a pure function of the files the row names, never an exit code. The
derivation is checked on fixture trees before anything starts, on every platform.

Prints `skip:` unless KIT_CONFORMANCE_BASE and KIT_HARNESS_ARGV_OPENCODE are set and the platform
is Windows. The base must be an existing folder. The harness's version is read through its
driver, whose probe keeps opencode's temporary files in a scratch folder.

Stdlib-runnable: `python test_interactive.py`.
"""

from __future__ import annotations

import json
import os
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
    REASON,
    SESSION_TIMEOUT_S,
    SRC,
    after_the_tool_call,
    find_run,
    kit,
    kit_env,
    policy_text,
    read_json,
    read_log,
    start_stub,
)
from test_guards import governed_hashes  # noqa: E402

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness_kit import harnesses, watch  # noqa: E402

WINDOWS = os.name == 'nt'
BASE_ENV = 'KIT_CONFORMANCE_BASE'
ARGV_ENV = 'KIT_HARNESS_ARGV_OPENCODE'
HARNESS = 'opencode'
CELLS = (
    'interactive-guard',
    'interactive-identity',
    'interactive-subfolder',
    'interactive-switch-denied',
)
# Only opencode's driver offers an interactive mode; the Claude Code driver runs no cell here.
CELLS_BY_HARNESS = {'claude-code': (), 'opencode': CELLS}
RESULTS = 'interactive-results.json'
STATE_DIR = 'interactive-state'
ROW_KEYS = ('cell', 'harness', 'harness_version', 'passed', 'stub_log', 'work_dir', 'run_id')
CANARY_RULES = ('canary.deny', 'canary.allow')
DENY_RULE = 'conformance-deny-shell'
WORKDIR_RULE = 'launcher.workdir'
PROMPT = 'Run each scripted tool call.'
SWITCH_PROMPT = 'Run the scripted tool call.'
SECOND_FOLDER = 'proj-bravo'
FIRST_FOLDER = 'proj-alpha'
SWITCH_FILTER = 'bravo'
PROCESSES_LEFT = 'processes-left.json'
EXPECTED_ENV = 'expected-env.json'
ENV_FILE = 'env.txt'
# A shell call of opencode runs in PowerShell on Windows.
ENV_COMMAND = (
    '[Environment]::GetEnvironmentVariables() | ConvertTo-Json -Compress '
    f'| Out-File -Encoding utf8 {ENV_FILE}'
)
MARKERS = {
    'deny': 'deny-shell.marker',
    'allow': 'allow-shell.marker',
    'sub': 'sub.marker',
    'switch': 'switch.marker',
}
# The isolation names a session gets from kit run: prefixes, then whole names.
ISOLATION_PREFIXES = ('KIT_', 'GIT_', 'OPENCODE_', 'XDG_')
ISOLATION_NAMES = (
    'HTTP_PROXY',
    'HTTPS_PROXY',
    'ALL_PROXY',
    'NO_PROXY',
    'GH_CONFIG_DIR',
    'HOME',
    'USERPROFILE',
    'HOMEDRIVE',
    'HOMEPATH',
    'APPDATA',
    'LOCALAPPDATA',
    'TEMP',
    'TMP',
)
SERVED_WAIT_S = 150
SETTLE_S = 3.0
EXIT_WAIT_S = 60
LEFT_WAIT_S = 10
RUN_ID = '20261118T120000Z-0123456789ab'


def _shell(command: str) -> dict:
    return {'tool': 'shell', 'args': {'command': command}}


def stub_steps(cell: str) -> list[dict]:
    """The stub's script: the cell's calls in order, each request with tools taking the next."""
    if cell == 'interactive-guard':
        return [
            _shell(f'echo probe > {MARKERS["deny"]}'),
            _shell(f'echo probe > {MARKERS["allow"]}'),
            {'text': 'done'},
        ]
    if cell == 'interactive-identity':
        return [_shell(ENV_COMMAND), {'text': 'done'}]
    if cell == 'interactive-subfolder':
        return [_shell(f'echo probe > {MARKERS["sub"]}'), {'text': 'done'}]
    # The headless session that makes the second folder known takes the first step.
    return [
        {'text': 'prepared'},
        {'text': 'ready'},
        _shell(f'echo probe > {MARKERS["switch"]}'),
        {'text': 'done'},
    ]


# ---- deriving a row from its files


def _ndjson(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = []
    for text in path.read_text(encoding='utf-8').splitlines():
        try:
            line = json.loads(text) if text.strip() else None
        except ValueError:
            continue
        if isinstance(line, dict):
            lines.append(line)
    return lines


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


def _read_any_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def _no_opencode_left(folder: Path) -> bool:
    left = _read_any_json(folder / PROCESSES_LEFT)
    if not isinstance(left, list):
        return False
    for entry in left:
        image = entry.get('image') if isinstance(entry, dict) else None
        if not isinstance(image, str) or image.lower().startswith('opencode'):
            return False
    return True


def _norm(path: object) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _under(path: object, top: object) -> bool:
    p, t = _norm(path), _norm(top)
    return p == t or p.startswith(t.rstrip(os.sep) + os.sep)


def _guard(row: dict, run_dir: Path, record: dict, folder: Path, work: Path) -> bool:
    canary = read_json(run_dir / 'canary' / 'canary.json').get('passed') is True
    markers = not (work / MARKERS['deny']).exists() and (work / MARKERS['allow']).is_file()
    lines = cell_journal(run_dir)
    verdicts = _has(lines, 'deny', DENY_RULE) and _has(lines, 'allow', None)
    carried = after_the_tool_call(read_log(Path(row['stub_log'])), REASON)
    home = record.get('home')
    hashes = _read_any_json(run_dir / watch.HOME_HASHES)
    same = bool(home) and hashes == watch.hash_files(home, harnesses.get(HARNESS))
    ended = record.get('outcome') == 'ended'
    return all((canary, markers, verdicts, carried, same, ended, _no_opencode_left(folder)))


def _identity(row: dict, folder: Path, work: Path) -> bool:
    seen = _read_any_json(work / ENV_FILE)
    expected = _read_any_json(folder / EXPECTED_ENV)
    if not isinstance(seen, dict) or not isinstance(expected, dict) or not expected:
        return False
    upper = {str(k).upper(): v for k, v in seen.items()}
    names = {k.upper() for k in expected}
    if 'KIT_RUN_ID' not in names or not names & set(ISOLATION_NAMES):
        return False
    held = all(upper.get(k.upper()) == v for k, v in expected.items())
    return held and upper.get('KIT_RUN_ID') == row['run_id']


def _subfolder(run_dir: Path, record: dict, work: Path) -> bool:
    top = record.get('work_tree_top')
    inside = bool(top) and _under(work, top) and _norm(work) != _norm(top)
    ran = (work / MARKERS['sub']).is_file()
    return inside and ran and _has(cell_journal(run_dir), 'allow', None)


def _switch(run_dir: Path, work: Path) -> bool:
    second = work.parent / SECOND_FOLDER
    absent = not (second / MARKERS['switch']).exists() and not (work / MARKERS['switch']).exists()
    return absent and _has(cell_journal(run_dir), 'deny', WORKDIR_RULE)


def derive(row: dict, state: Path) -> bool:
    """Re-derive one row's `passed` from the files it names, by the cell table."""
    run_id = row.get('run_id')
    if not run_id:
        return False
    run_dir = Path(state) / 'runs' / run_id
    record = read_json(run_dir / 'run.json')
    if not record:
        return False
    folder, work = Path(row['stub_log']).parent, Path(row['work_dir'])
    cell = row.get('cell')
    if cell == 'interactive-guard':
        return _guard(row, run_dir, record, folder, work)
    if cell == 'interactive-identity':
        return _identity(row, folder, work)
    if cell == 'interactive-subfolder':
        return _subfolder(run_dir, record, work)
    if cell == 'interactive-switch-denied':
        return _switch(run_dir, work)
    return False


# ---- fixture trees for the derivation (run on every platform, before any skip)

CANARY_SESSION = 'canary-session'
CELL_SESSION = 'cell-session'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _judged(verdict: str, rule: str | None, session: str = CELL_SESSION) -> dict:
    return {'session_id': session, 'act_kind': 'shell', 'verdict': verdict, 'rule': rule}


def _lines(*items: dict) -> str:
    canary = (
        _judged('deny', 'canary.deny', CANARY_SESSION),
        _judged('allow', 'canary.allow', CANARY_SESSION),
    )
    return ''.join(json.dumps(item) + '\n' for item in (*canary, *items))


def _log(*bodies: object) -> str:
    rows = [
        {'kind': 'POST', 'decision': 'scripted', 'step_index': i, 'body': body}
        for i, body in enumerate(bodies)
    ]
    return ''.join(json.dumps(r) + '\n' for r in rows)


def _fixture_home(home: Path) -> None:
    for rel in ('conf/opencode.jsonc', 'kit-shell/opencode-plugin/index.js', 'home.json'):
        _write(home / rel, rel)
    _write(home / 'xdg' / 'data' / 'o.db', 'not watched')


def make_row(cell: str, base: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the state root."""
    state, folder = base / 'state', base / 'cell'
    run_dir = state / 'runs' / RUN_ID
    home = folder / 'home'
    work = folder / FIRST_FOLDER
    if cell == 'interactive-subfolder':
        work = folder / 'repo' / 'sub'
    work.mkdir(parents=True)
    _fixture_home(home)
    record = {'run_id': RUN_ID, 'outcome': 'ended', 'home': str(home), 'workdir': str(work)}
    record['work_tree_top'] = str(work.parent) if cell == 'interactive-subfolder' else None
    _write(run_dir / 'run.json', json.dumps(record))
    _write(folder / 'stub.jsonl', _log({'messages': []}, {'messages': [REASON]}))
    _write(folder / PROCESSES_LEFT, '[]')
    if cell == 'interactive-guard':
        _write(run_dir / 'canary' / 'canary.json', json.dumps({'passed': True}))
        _write(work / MARKERS['allow'], 'probe')
        _write(
            run_dir / 'journal.ndjson', _lines(_judged('deny', DENY_RULE), _judged('allow', None))
        )
        hashes = watch.hash_files(home, harnesses.get(HARNESS))
        _write(run_dir / watch.HOME_HASHES, json.dumps(hashes))
    elif cell == 'interactive-identity':
        expected = {'KIT_RUN_ID': RUN_ID, 'HTTP_PROXY': 'http://127.0.0.1:1', 'TEMP': 'C:/t'}
        _write(folder / EXPECTED_ENV, json.dumps(expected))
        seen = {**expected, 'Path': 'C:/bin', 'OPENCODE_SESSION_ID': 'ses'}
        (work / ENV_FILE).write_bytes(b'\xef\xbb\xbf' + json.dumps(seen).encode('utf-8'))
    elif cell == 'interactive-subfolder':
        _write(work / MARKERS['sub'], 'probe')
        _write(run_dir / 'journal.ndjson', _lines(_judged('allow', None)))
    else:
        (folder / SECOND_FOLDER).mkdir()
        _write(run_dir / 'journal.ndjson', _lines(_judged('deny', WORKDIR_RULE)))
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


def _plant(name: str, where: str = 'work') -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        work = Path(row['work_dir'])
        folder = work.parent / SECOND_FOLDER if where == 'second' else work
        _write(folder / name, 'probe')

    return change


def _remove(name: str) -> Callable[[dict, Path], None]:
    return lambda row, state: (Path(row['work_dir']) / name).unlink()


def _journal(*items: dict) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(_run_dir(state) / 'journal.ndjson', _lines(*items))


def _record(**over: object) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = _run_dir(state) / 'run.json'
        record = json.loads(path.read_text(encoding='utf-8'))
        record.update(over)
        _write(path, json.dumps(record))

    return change


def _folder_file(name: str, text: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['stub_log']).parent / name, text)


def _home_file(rel: str, text: str) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        record = json.loads((_run_dir(state) / 'run.json').read_text(encoding='utf-8'))
        _write(Path(record['home']) / rel, text)

    return change


def _env_seen(**over: str) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = Path(row['work_dir']) / ENV_FILE
        seen = json.loads(path.read_text(encoding='utf-8-sig'))
        seen.update(over)
        _write(path, json.dumps(seen))

    return change


BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'interactive-guard': [
        lambda row, state: _write(_run_dir(state) / 'canary' / 'canary.json', '{"passed": false}'),
        _plant(MARKERS['deny']),
        _remove(MARKERS['allow']),
        _journal(_judged('allow', None)),
        _journal(_judged('deny', DENY_RULE)),
        _folder_file('stub.jsonl', _log({'messages': [REASON]}, {'messages': []})),
        _home_file('conf/opencode.jsonc', 'changed'),
        _home_file('kit-shell/added.js', 'added'),
        _record(outcome='launched'),
        _folder_file(PROCESSES_LEFT, '[{"pid": 7, "image": "opencode.exe"}]'),
        _folder_file(PROCESSES_LEFT, '[{"pid": 7, "image": null}]'),
        _folder_file(PROCESSES_LEFT, 'not json'),
    ],
    'interactive-identity': [
        _env_seen(KIT_RUN_ID='20261118T120000Z-ffffffffffff'),
        _env_seen(HTTP_PROXY='http://127.0.0.1:2'),
        _remove(ENV_FILE),
        _folder_file(EXPECTED_ENV, '{}'),
        _folder_file(EXPECTED_ENV, '{"TEMP": "C:/t"}'),
    ],
    'interactive-subfolder': [
        _remove(MARKERS['sub']),
        _record(work_tree_top=None),
        lambda row, state: _record(work_tree_top=row['work_dir'])(row, state),
        _journal(_judged('deny', DENY_RULE)),
    ],
    'interactive-switch-denied': [
        _plant(MARKERS['switch'], 'second'),
        _plant(MARKERS['switch']),
        _journal(_judged('allow', None)),
        _journal(_judged('deny', DENY_RULE)),
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


def _stat_tree(top: Path) -> dict:
    """Name, size and modification time in nanoseconds of every file under `top`."""
    found = {}
    if top.is_dir():
        for path in sorted(top.rglob('*')):
            if path.is_file():
                st = path.stat()
                found[path.relative_to(top).as_posix()] = [st.st_size, st.st_mtime_ns]
    return found


def _snapshot(folder: Path, home: Path, label: str) -> None:
    tree = _stat_tree(home / 'xdg' / 'config')
    (folder / f'xdg-config-{label}.json').write_text(json.dumps(tree, indent=2), encoding='utf-8')


def _work_folder(cell: str, folder: Path, env: dict) -> Path:
    if cell == 'interactive-subfolder':
        repo = folder / 'repo'
        (repo / 'sub').mkdir(parents=True)
        clean = {k: v for k, v in env.items() if not k.upper().startswith('GIT_')}
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            ['git', '-C', str(repo), 'init', '-q'],  # noqa: S607 - PATH git
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            env=clean,
        )
        return repo / 'sub'
    if cell == 'interactive-switch-denied':
        (folder / SECOND_FOLDER).mkdir(parents=True)
    work = folder / FIRST_FOLDER
    work.mkdir(parents=True)
    return work


def _prepare_second_folder(folder: Path, home: Path, policy: Path, env: dict) -> None:
    """A headless kit run in the second folder, so the interface lists it as a project."""
    second = folder / SECOND_FOLDER
    argv = harnesses.get(HARNESS).canary_argv('Answer with text.')
    head = ['run', '--harness', HARNESS, '--home', str(home), '--workdir', str(second)]
    head += ['--policy', str(policy), '--']
    with open(folder / 'prepare.stdout', 'wb') as out, open(folder / 'prepare.stderr', 'wb') as err:
        subprocess.run(  # noqa: S603 - argv built above, no shell
            [sys.executable, '-m', 'harness_kit', *head, *argv],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            env=env,
            cwd=str(second),
            timeout=SESSION_TIMEOUT_S,
            check=False,
        )


def _drive(cell: str, console, folder: Path, home: Path) -> None:
    """Wait for the scripted steps, write the cell's keystrokes, then one Ctrl+C."""
    import conpty

    log = folder / 'stub.jsonl'
    if cell == 'interactive-switch-denied':
        _wait_served(log, 1)
        time.sleep(SETTLE_S)
        _wait_quiet(console)
        _snapshot(folder, home, 'before')
        console.write(conpty.CTRL_O)
        time.sleep(2.0)
        _wait_quiet(console)
        console.type_slowly(SWITCH_FILTER)
        time.sleep(2.0)
        _wait_quiet(console)
        console.write(conpty.ENTER)
        time.sleep(3.0)
        _wait_quiet(console)
        _snapshot(folder, home, 'after-switch')
        console.type_slowly(SWITCH_PROMPT)
        time.sleep(0.5)
        console.write(conpty.ENTER)
        _wait_served(log, 3)
        time.sleep(SETTLE_S)
        _snapshot(folder, home, 'after-call')
    else:
        _wait_served(log, len(stub_steps(cell)) - 1)
        time.sleep(SETTLE_S)
    _wait_quiet(console)
    console.write(conpty.CTRL_C)


def _expected_env(state: Path, run_id: str, home: Path, policy: Path, work: Path, env: dict):
    """The isolation names `build_env` sets for the run, as `kit run` called it."""
    from harness_kit import launcher
    from harness_kit import state as kit_state

    driver = harnesses.get(HARNESS)
    rendered = json.loads((home / 'home.json').read_text(encoding='utf-8'))
    root = kit_state.state_root(env)
    built, _ = launcher.build_env(
        driver,
        rendered,
        env,
        run_dir=root / 'runs' / run_id,
        run_id=run_id,
        root=root,
        policy_path=Path(os.path.abspath(policy)),
        workdir=Path(os.path.realpath(work)),
    )
    return {
        k: v
        for k, v in built.items()
        if k.upper() in ISOLATION_NAMES or k.upper().startswith(ISOLATION_PREFIXES)
    }


def run_cell(
    cell: str, version: str | None, base: Path, policy: Path, argv_env: dict
) -> tuple[dict, list[str]]:
    """Run one cell: its row, with `passed` derived from the files it names, and its problems."""
    import conpty

    state = base / STATE_DIR
    folder = base / 'interactive-cells' / f'{HARNESS}-{cell}-{uuid.uuid4().hex[:8]}'
    folder.mkdir(parents=True)
    env = kit_env({'KIT_STATE_ROOT': str(state), **argv_env})
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
    stub, port = start_stub(folder, stub_steps(cell), env)
    console = None
    try:
        render = ['home', 'render', '--harness', HARNESS, '--dir', str(home)]
        kit(*render, '--endpoint', f'http://127.0.0.1:{port}', env=env)
        if cell == 'interactive-switch-denied':
            _prepare_second_folder(folder, home, policy, env)
        head = ['run', '--harness', HARNESS, '--mode', 'interactive', '--home', str(home)]
        head += ['--workdir', str(work), '--policy', str(policy), '--']
        argv = [sys.executable, '-m', 'harness_kit', *head, '--standalone', '--prompt', PROMPT]
        console = conpty.PseudoConsole(argv, env, work, folder / 'screen.log')
        _drive(cell, console, folder, home)
        code = console.wait(EXIT_WAIT_S)
        left = console.left()
        end = time.monotonic() + LEFT_WAIT_S
        while left and time.monotonic() < end:
            time.sleep(0.2)
            left = console.left()
        (folder / PROCESSES_LEFT).write_text(json.dumps(left), encoding='utf-8')
        (folder / 'kit-exit.json').write_text(json.dumps({'exit_code': code}), encoding='utf-8')
        if code is None:
            problems.append(f'{HARNESS}/{cell}: kit run did not end after one Ctrl+C')
    except Exception as exc:  # a failed cell is a row, not a crash of the suite
        problems.append(f'{HARNESS}/{cell}: the session failed: {type(exc).__name__}: {exc}')
    finally:
        if console is not None:
            console.close()
        stub.kill()
        stub.wait()
    row['run_id'] = find_run(state, work)
    try:
        if cell == 'interactive-identity' and row['run_id']:
            expected = _expected_env(state, row['run_id'], home, policy, work, env)
            (folder / EXPECTED_ENV).write_text(json.dumps(expected, indent=2), encoding='utf-8')
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
        print(f'skip: the interactive cells need {" and ".join(names)}')
        return 0
    if not WINDOWS:
        print('skip: the interactive cells run on Windows only')
        return 0
    base = Path(base_raw)
    if not base.is_dir():
        print(f'FAIL: {BASE_ENV} is not an existing folder')
        return 1
    base = base.resolve()
    before = governed_hashes()
    argv_env = {ARGV_ENV: argv_raw}
    policy = base / 'interactive-policy.toml'
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
    print(f'ok: interactive cells passed on {HARNESS} ({len(rows)} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

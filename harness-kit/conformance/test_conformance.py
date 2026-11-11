#!/usr/bin/env python3
"""Conformance suite: cells on both real harnesses, in rendered homes, against a stub model.

Each cell proves one objective of the harness contracts with markers on disk:

- guard-loaded: the presence canary of `kit run` passed and the session ran;
- deny-shell, deny-write: a governed call is refused, its marker or file is
  absent, and the next stub request carries the rule's reason;
- allow-shell: an ungoverned call runs;
- run-identity: a tool call sees the run's id in its environment;
- hung-guard: a stuck CLI is refused with `kit could not judge:`; the harness is
  started directly, with a run id minted by `kit state new-run`, never under
  `kit run` (a hung CLI cannot write the refused marker the canary requires);
- heartbeat: a session under `kit run` that lasts at least 5 seconds;
- not-launched (Claude Code) and launcher-required (opencode): no `kit run`,
  `KIT_POLICY` set.

The state root is `KIT_CONFORMANCE_BASE/state`. A run writes
`conformance-results.json` under the base, one row per cell with `cell`,
`harness`, `harness_version`, `passed`, `stub_log`, `work_dir` and `run_id`.
`passed` is derived by `derive` from the files the row names, never from an
exit code. The derivation is checked on fixture trees before anything starts,
on every platform.

Prints `skip:` unless KIT_CONFORMANCE_BASE, KIT_HARNESS_ARGV_CLAUDE_CODE and
KIT_HARNESS_ARGV_OPENCODE are set (and the platform is Windows); the base must
be an existing folder.

Stdlib-runnable: `python test_conformance.py`. With `--hang LATE_MARKER` this
file is the hanging CLI itself.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path

WINDOWS = os.name == 'nt'
SRC = Path(__file__).resolve().parents[1] / 'src'
REQUIRED = ('KIT_CONFORMANCE_BASE', 'KIT_HARNESS_ARGV_CLAUDE_CODE', 'KIT_HARNESS_ARGV_OPENCODE')
HARNESSES = ('claude-code', 'opencode')
RESULTS = 'conformance-results.json'
REASON = 'KIT-CONFORMANCE-REASON'
HUNG = 'kit could not judge:'
NOT_LAUNCHED_TEXT = 'not launched, guarantees unknown'
SECRET_NAME = re.compile(r'(^GH_|_KEY$|_TOKEN$|_SECRET$|_PASSWORD$)', re.IGNORECASE)
LATE_CODE = 'import sys, time; time.sleep(6); open(sys.argv[1], "w").write("late")'
SESSION_TIMEOUT_S = 300
RUN_ID = '20261110T120000Z-0123456789ab'
# Cells that run under `kit run`, then the two that run a bare harness, in the order they are run.
LAUNCHED = ('guard-loaded', 'deny-shell', 'deny-write', 'allow-shell', 'run-identity', 'heartbeat')
BARE = {
    'claude-code': ('hung-guard', 'not-launched'),
    'opencode': ('hung-guard', 'launcher-required'),
}
SHELL_COMMANDS = {
    'guard-loaded': 'echo probe > session.marker',
    'deny-shell': 'echo probe > deny-shell.marker',
    'allow-shell': 'echo probe > allow-shell.marker',
    'hung-guard': 'echo probe > hung.marker',
    'not-launched': 'echo probe > not-launched.marker',
    'launcher-required': 'echo probe > launcher-required.marker',
}
# The two shells read an environment variable differently, so these are written per harness.
RUN_ID_COMMANDS = {
    'claude-code': 'echo "$KIT_RUN_ID" > run-id.txt',
    'opencode': '$env:KIT_RUN_ID | Out-File -Encoding ascii run-id.txt',
}
SLEEP_COMMANDS = {'claude-code': 'sleep 6', 'opencode': 'Start-Sleep -Seconds 6'}


# ---- the hanging CLI


def hang(late_marker: str) -> int:
    """Start a grandchild that writes `late_marker` later, then hang."""
    subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-I', '-c', LATE_CODE, late_marker],
        stdin=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(60)
    return 0


# ---- deriving a row from its files


def read_log(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def after_the_tool_call(log: list[dict], needle: str) -> bool:
    """True when a request that follows the first scripted tool call carries `needle`."""
    later = [r for r in log if r.get('decision') == 'scripted' and (r.get('step_index') or 0) >= 1]
    return any(needle in json.dumps(r.get('body')) for r in later)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def not_launched_lines(state: Path, harness: str) -> list[dict]:
    lines = []
    for journal in sorted((state / 'not-launched').glob('*/journal.ndjson')):
        for text in journal.read_text(encoding='utf-8').splitlines():
            line = json.loads(text) if text else {}
            if line.get('harness') == harness and line.get('launched') is False:
                lines.append(line)
    return lines


def run_doctor(state: Path) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env['PYTHONPATH'] = str(SRC)
    env['KIT_STATE_ROOT'] = str(state)
    for name in REQUIRED[1:]:
        if name in os.environ:
            env[name] = os.environ[name]
    proc = subprocess.run(
        [sys.executable, '-m', 'harness_kit', 'doctor'],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=120,
        check=False,
    )
    return proc.stdout


def derive(row: dict, state: Path, *, doctor: Callable[[], str] | None = None) -> bool:
    """Re-derive one row's `passed` from the files it names, by the cell table of the spec."""
    cell, run_id = row['cell'], row['run_id']
    work, log = Path(row['work_dir']), read_log(Path(row['stub_log']))
    run_dir = state / 'runs' / run_id if run_id else None
    if cell in (*LAUNCHED, 'hung-guard') and (not run_id or not run_dir.is_dir()):
        return False
    if cell == 'guard-loaded':
        canary = read_json(run_dir / 'canary' / 'canary.json')
        return canary.get('passed') is True and (work / 'session.marker').is_file()
    if cell == 'deny-shell':
        return not (work / 'deny-shell.marker').exists() and after_the_tool_call(log, REASON)
    if cell == 'deny-write':
        return not (work / 'deny-write.txt').exists() and after_the_tool_call(log, REASON)
    if cell == 'allow-shell':
        return (work / 'allow-shell.marker').is_file()
    if cell == 'run-identity':
        saw = work / 'run-id.txt'
        text = saw.read_text(encoding='utf-8').strip() if saw.is_file() else None
        return text == run_id and (run_dir / 'run.json').is_file()
    if cell == 'hung-guard':
        return not (work / 'hung.marker').exists() and after_the_tool_call(log, HUNG)
    if cell == 'heartbeat':
        beat = read_json(run_dir / 'heartbeat.json')
        seq = beat.get('seq')
        ended = read_json(run_dir / 'run.json').get('outcome') == 'ended'
        return isinstance(seq, int) and seq >= 2 and ended
    lines = not_launched_lines(state, row['harness'])
    if cell == 'not-launched':
        journaled = any(x.get('verdict') == 'allow' and x.get('rule') is None for x in lines)
        text = (doctor or (lambda: run_doctor(state)))()
        return journaled and (work / 'not-launched.marker').is_file() and NOT_LAUNCHED_TEXT in text
    if cell == 'launcher-required':
        journaled = any(
            x.get('verdict') == 'deny' and x.get('rule') == 'launcher.required' for x in lines
        )
        return journaled and not (work / 'launcher-required.marker').exists()
    return False


# ---- fixture trees for the derivation (run on every platform, before any skip)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _log_text(*bodies: str) -> str:
    rows = [
        {'kind': 'model', 'decision': 'scripted', 'step_index': i, 'body': body}
        for i, body in enumerate(bodies)
    ]
    return ''.join(json.dumps(r) + '\n' for r in rows)


def _journal(state: Path, harness: str, verdict: str, rule: str | None) -> None:
    line = {'launched': False, 'harness': harness, 'verdict': verdict, 'rule': rule}
    _write(state / 'not-launched' / 'abc' / 'journal.ndjson', json.dumps(line) + '\n')


def make_row(cell: str, harness: str, folder: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the state root."""
    state, work = folder / 'state', folder / 'work'
    work.mkdir(parents=True)
    run_dir = state / 'runs' / RUN_ID
    after = HUNG if cell == 'hung-guard' else REASON
    _write(folder / 'stub.jsonl', _log_text('prompt', after))
    row = {
        'cell': cell,
        'harness': harness,
        'harness_version': '1.0.0',
        'passed': True,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': RUN_ID,
    }
    if cell == 'guard-loaded':
        _write(run_dir / 'canary' / 'canary.json', json.dumps({'passed': True}))
        _write(work / 'session.marker', 'x')
    elif cell == 'allow-shell':
        _write(work / 'allow-shell.marker', 'x')
        run_dir.mkdir(parents=True)
    elif cell == 'run-identity':
        _write(work / 'run-id.txt', f'  {RUN_ID}  \n')
        _write(run_dir / 'run.json', '{}')
    elif cell == 'heartbeat':
        _write(run_dir / 'heartbeat.json', json.dumps({'seq': 2}))
        _write(run_dir / 'run.json', json.dumps({'outcome': 'ended'}))
    elif cell == 'not-launched':
        row['run_id'] = None
        _write(work / 'not-launched.marker', 'x')
        _journal(state, harness, 'allow', None)
    elif cell == 'launcher-required':
        row['run_id'] = None
        _journal(state, harness, 'deny', 'launcher.required')
    else:
        run_dir.mkdir(parents=True)
    return row, state


def _break_log(row: dict, state: Path, *, reason_first: bool = False) -> None:
    needle = HUNG if row['cell'] == 'hung-guard' else REASON
    bodies = (needle, 'prompt') if reason_first else ('prompt', 'nothing')
    _write(Path(row['stub_log']), _log_text(*bodies))


def _plant(name: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['work_dir']) / name, 'x')


def _remove(name: str) -> Callable[[dict, Path], None]:
    return lambda row, state: (Path(row['work_dir']) / name).unlink()


def _set(path: Callable[[dict, Path], Path], text: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(path(row, state), text)


RUN_DIR: Callable[[dict, Path], Path] = lambda row, state: state / 'runs' / RUN_ID  # noqa: E731
JOURNAL: Callable[[dict, Path], Path] = lambda row, state: (  # noqa: E731
    state / 'not-launched' / 'abc' / 'journal.ndjson'
)
BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'guard-loaded': [
        _set(lambda r, s: RUN_DIR(r, s) / 'canary' / 'canary.json', '{"passed": false}'),
        _remove('session.marker'),
    ],
    'deny-shell': [
        _plant('deny-shell.marker'),
        _break_log,
        lambda row, state: _break_log(row, state, reason_first=True),
    ],
    'deny-write': [_plant('deny-write.txt'), _break_log],
    'allow-shell': [_remove('allow-shell.marker')],
    'run-identity': [
        _set(lambda r, s: Path(r['work_dir']) / 'run-id.txt', 'other'),
        lambda row, state: (RUN_DIR(row, state) / 'run.json').unlink(),
    ],
    'hung-guard': [_plant('hung.marker'), _break_log],
    'heartbeat': [
        _set(lambda r, s: RUN_DIR(r, s) / 'heartbeat.json', '{"seq": 1}'),
        _set(lambda r, s: RUN_DIR(r, s) / 'run.json', '{"outcome": "launched"}'),
    ],
    'not-launched': [
        _remove('not-launched.marker'),
        lambda row, state: _journal(state, row['harness'], 'deny', None),
        lambda row, state: _journal(state, row['harness'], 'allow', 'some-rule'),
        lambda row, state: _journal(state, 'opencode', 'allow', None),
    ],
    'launcher-required': [
        _plant('launcher-required.marker'),
        lambda row, state: _journal(state, row['harness'], 'allow', 'launcher.required'),
        lambda row, state: _journal(state, row['harness'], 'deny', 'other'),
    ],
}
FIXTURE_HARNESS = {'launcher-required': 'opencode', 'not-launched': 'claude-code'}


def check_derive() -> None:
    """Every cell derives true from a passing tree, and false after each way it can break."""
    for cell in (*LAUNCHED, 'hung-guard', 'not-launched', 'launcher-required'):
        harness = FIXTURE_HARNESS.get(cell, 'claude-code')
        said = lambda: NOT_LAUNCHED_TEXT  # noqa: E731
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, harness, Path(tmp))
            assert derive(row, state, doctor=said), f'{cell}: a passing tree derived false'
        for index, broken in enumerate(BREAKS.get(cell, [])):
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, harness, Path(tmp))
                broken(row, state)
                assert not derive(row, state, doctor=said), f'{cell}: break {index} derived true'
        if cell == 'not-launched':
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, harness, Path(tmp))
                assert not derive(row, state, doctor=lambda: 'nothing'), f'{cell}: doctor text'
        if cell in (*LAUNCHED, 'hung-guard'):
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, harness, Path(tmp))
                row['run_id'] = None
                assert not derive(row, state, doctor=said), f'{cell}: no run id derived true'


# ---- one cell on a real harness


def policy_text(base: Path) -> str:
    roots = json.dumps(str(base))
    return f"""\
version = 1

[launcher]
test_roots = [{roots}]
forbidden_roots = []

[[rule]]
id = "conformance-deny-shell"
effect = "deny"
governed = true
kinds = ["shell"]
command_regex = "deny-shell\\\\.marker"
reason = "{REASON}"

[[rule]]
id = "conformance-deny-write"
effect = "deny"
governed = true
kinds = ["file_write"]
path_glob = ["**/deny-write.txt"]
reason = "{REASON}"
"""


def kit_env(extra: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env = {k: v for k, v in env.items() if not SECRET_NAME.search(k)}
    # The app that runs this test sets its own variables; none of them belongs in a test session.
    env = {k: v for k, v in env.items() if not re.match(r'(CLAUDE|ANTHROPIC)', k, re.IGNORECASE)}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def kit(*args: str, env: dict) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, (args, proc.returncode, proc.stderr)
    return proc.stdout


def start_stub(folder: Path, steps: list, env: dict) -> tuple[subprocess.Popen, int]:
    script = folder / 'script.json'
    script.write_text(json.dumps(steps), encoding='utf-8')
    stub = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            '-m',
            'harness_kit',
            'stub',
            '--log',
            str(folder / 'stub.jsonl'),
            '--script',
            str(script),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding='utf-8',
        env=env,
    )
    return stub, json.loads(stub.stdout.readline())['port']


def cell_steps(cell: str, driver, work: Path) -> list[dict]:
    """The stub's script for one cell: one tool call, then a closing text."""
    if cell == 'deny-write':
        target, claude = str(work / 'deny-write.txt'), driver.name == 'claude-code'
        name, key = ('Write', 'file_path') if claude else ('write', 'path')
        step = {'tool': name, 'args': {key: target, 'content': 'probe'}}
    else:
        commands = {'run-identity': RUN_ID_COMMANDS, 'heartbeat': SLEEP_COMMANDS}
        command = commands[cell][driver.name] if cell in commands else SHELL_COMMANDS[cell]
        step = driver.canary_step(command)
    return [step, {'text': 'done'}]


def find_run(state: Path, work: Path) -> str | None:
    """The id of the run whose working folder is `work`."""
    want = os.path.normcase(os.path.realpath(work))
    for path in sorted((state / 'runs').glob('*/run.json')):
        record = read_json(path)
        found = record.get('workdir')
        if found and os.path.normcase(os.path.realpath(found)) == want:
            return record.get('run_id')
    return None


def run_cell(cell: str, harness: str, version: str | None, base: Path) -> dict:
    """Run one cell; `passed` is derived from the files the row names."""
    from harness_kit import harnesses

    driver = harnesses.get(harness)
    state = base / 'state'
    folder = base / 'cells' / f'{harness}-{cell}-{uuid.uuid4().hex[:8]}'
    work, tmp = folder / 'work', folder / 'tmp'
    for sub in (work, tmp):
        sub.mkdir(parents=True)
    row = {
        'cell': cell,
        'harness': harness,
        'harness_version': version,
        'passed': False,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': None,
    }
    policy = base / 'conformance-policy.toml'
    extra = {'KIT_STATE_ROOT': str(state)}
    extra.update({k: os.environ[k] for k in REQUIRED[1:]})
    env = kit_env(extra)
    stub, port = start_stub(folder, cell_steps(cell, driver, work), env)
    try:
        home_dir = folder / 'home'
        rendered = kit(
            'home',
            'render',
            '--harness',
            harness,
            '--dir',
            str(home_dir),
            '--endpoint',
            f'http://127.0.0.1:{port}',
            env=env,
        )
        home = json.loads(rendered)
        argv = driver.canary_argv('Run the scripted tool call.')
        if cell == 'deny-write' and harness == 'claude-code':
            argv = [*argv, 'Write']
        with open(folder / 'stdout.txt', 'wb') as out, open(folder / 'stderr.txt', 'wb') as err:
            if cell in LAUNCHED:
                head = ['run', '--harness', harness, '--home', str(home_dir)]
                head += ['--workdir', str(work), '--policy', str(policy), '--']
                command, run_env = [sys.executable, '-m', 'harness_kit', *head, *argv], env
            else:
                session = {k: v for k, v in env.items() if k != 'PYTHONPATH'}
                session.update(TEMP=str(tmp), TMP=str(tmp), PWD=str(work))
                if cell == 'hung-guard':
                    config = Path(home['shell_config'])
                    shell_config = json.loads(config.read_text(encoding='utf-8'))
                    late = str(folder / 'late.marker')
                    shell_config['cli_argv'] = [
                        sys.executable,
                        '-I',
                        str(Path(__file__).resolve()),
                        '--hang',
                        late,
                    ]
                    config.write_text(json.dumps(shell_config, indent=2) + '\n', encoding='utf-8')
                    minted = json.loads(kit('state', 'new-run', '--harness', harness, env=env))
                    row['run_id'] = session['KIT_RUN_ID'] = minted['run_id']
                else:
                    session['KIT_POLICY'] = str(policy)
                run_env = driver.session_env(home, session)
                binary = driver.binary_argv(run_env)
                assert binary, f'{harness}: binary missing'
                command = binary + argv
            subprocess.run(  # noqa: S603 - argv built above, no shell
                command,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=run_env,
                cwd=str(work),
                timeout=SESSION_TIMEOUT_S,
                check=False,
            )
    except Exception as exc:  # a failed cell is a row, not a crash of the suite
        row['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        stub.kill()
        stub.wait()
    if cell in LAUNCHED:
        row['run_id'] = find_run(state, work)
    try:
        row['passed'] = derive(row, state)
    except Exception as exc:
        row['error'] = f'{type(exc).__name__}: {exc}'
    return row


def main() -> int:
    if sys.argv[1:2] == ['--hang']:
        return hang(sys.argv[2])
    check_derive()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f'skip: the conformance suite needs {", ".join(missing)}')
        return 0
    if not WINDOWS:
        print('skip: the conformance suite runs on Windows only')
        return 0
    base = Path(os.environ['KIT_CONFORMANCE_BASE'])
    if not base.is_dir():
        print('FAIL: KIT_CONFORMANCE_BASE is not an existing folder')
        return 1
    base = base.resolve()
    sys.path.insert(0, str(SRC))
    from harness_kit import harnesses

    (base / 'conformance-policy.toml').write_text(policy_text(base), encoding='utf-8')
    rows: list[dict] = []
    try:
        for harness in HARNESSES:
            version = harnesses.get(harness).version(
                kit_env({k: os.environ[k] for k in REQUIRED[1:]})
            )
            for cell in (*LAUNCHED, *BARE[harness]):
                rows.append(run_cell(cell, harness, version, base))
    finally:
        (base / RESULTS).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(rows, indent=2))
    bad = [r for r in rows if not r['passed']]
    if bad:
        print('FAIL: ' + ', '.join(f'{r["harness"]}/{r["cell"]}' for r in bad))
        return 1
    print(f'ok: conformance cells passed on both harnesses ({len(rows)} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Rule cells: the uv rule pack on both real harnesses, in rendered homes, against a stub model.

Per harness, three cells run the real harness headless through `kit run`, with
a policy that `kit policy build` composes from the conformance base policy and
`packs/uv`, each cell in a work folder of its own:

- uv-deny: the folder holds an empty `uv.lock`; the stub asks for
  `echo probe > uv-deny.marker; pip install --help`. No marker appears, and the
  reason that `kit judge` composes for this cell's event is a substring of a
  request body after the tool call, as the stub logged it;
- uv-allow-outside: no `uv.lock` and no `pyproject.toml`; the same command with
  `uv-allow-outside.marker`. The marker appears;
- uv-allow-mention: the folder holds an empty `uv.lock`; the stub asks for
  `echo "pip install" > uv-allow-mention.marker`. The marker appears.

For the reason and for timing each cell has one neutral event built from its
command and work folder. It names the harness `claude-code` and is judged with
no `KIT_RUN_ID`, on both harnesses' rows: an event of a harness that was not
launched is denied by `launcher.required` before any policy rule. For uv-deny
the verdict's rule must be `uv-project-uses-uv` before its reason is used.
Before each session the event is judged once with the cell's policy, untimed,
so that the first load of the checker does not fall inside the session; then
20 timed `kit judge` calls with the cell's policy and 20 with the base policy
alone give `judge_ms_median` and `judge_ms_median_base`. Those calls run under
a `KIT_STATE_ROOT` of the cell's own, so they add no line to the journals the
conformance suite reads. The 20 timed verdicts of uv-deny must all be `deny`;
the medians are recorded and never asserted.

A run writes `rules-results.json` under KIT_CONFORMANCE_BASE and leaves
`conformance-results.json` alone. Each row has the keys of a conformance row
(`cell`, `harness`, `harness_version`, `passed`, `stub_log`, `work_dir`,
`run_id`) plus `judge_ms_median` and `judge_ms_median_base`; `passed` is
derived by `derive` from the files the row names, never from an exit code. The
derivation is checked on fixture trees before anything starts, on every
platform.

Prints `skip:` unless KIT_CONFORMANCE_BASE and at least one harness's
`KIT_HARNESS_ARGV_*` variable are set (and the platform is Windows); a harness
whose variable is unset is left out. The base must be an existing folder.

Stdlib-runnable: `python test_rules.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
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
    find_run,
    kit,
    kit_env,
    policy_text,
    read_log,
    start_stub,
)

WINDOWS = os.name == 'nt'
BASE_ENV = 'KIT_CONFORMANCE_BASE'
ARGV_ENV = {'claude-code': 'KIT_HARNESS_ARGV_CLAUDE_CODE', 'opencode': 'KIT_HARNESS_ARGV_OPENCODE'}
HARNESSES = ('claude-code', 'opencode')
RESULTS = 'rules-results.json'
PACK = HERE.parent / 'packs' / 'uv'
RULE_ID = 'uv-project-uses-uv'
CELLS = ('uv-deny', 'uv-allow-outside', 'uv-allow-mention')
COMMANDS = {
    'uv-deny': 'echo probe > uv-deny.marker; pip install --help',
    'uv-allow-outside': 'echo probe > uv-allow-outside.marker; pip install --help',
    'uv-allow-mention': 'echo "pip install" > uv-allow-mention.marker',
}
UV_LOCK = {'uv-deny': True, 'uv-allow-outside': False, 'uv-allow-mention': True}
MARKERS = {cell: f'{cell}.marker' for cell in CELLS}
TIMED_CALLS = 20
JUDGE_TIMEOUT_S = 60
EVENT_HARNESS = 'claude-code'
EVENT_HARNESS_VERSION = '2.1.316'
ROW_KEYS = (
    'cell',
    'harness',
    'harness_version',
    'passed',
    'stub_log',
    'work_dir',
    'run_id',
    'judge_ms_median',
    'judge_ms_median_base',
)
RUN_ID = '20261112T120000Z-0123456789ab'


# ---- deriving a row from its files


def _strings(node: object):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def carries(body: object, needle: str) -> bool:
    """True when one string of a logged request body, or the body as JSON, holds `needle`."""
    if any(needle in text for text in _strings(body)):
        return True
    return needle in json.dumps(body, ensure_ascii=False)


def after_the_tool_call(log: list[dict], needle: str) -> bool:
    """True when a request that follows the first scripted tool call carries `needle`."""
    later = [r for r in log if r.get('decision') == 'scripted' and (r.get('step_index') or 0) >= 1]
    return bool(needle) and any(carries(r.get('body'), needle) for r in later)


def derive(row: dict, state: Path, reason: str | None) -> bool:
    """Re-derive one row's `passed` from the files it names; `reason` is uv-deny's composed reason."""
    cell, run_id = row['cell'], row['run_id']
    work = Path(row['work_dir'])
    if not run_id or not (state / 'runs' / run_id / 'run.json').is_file():
        return False
    marker = work / MARKERS[cell]
    if cell == 'uv-deny':
        log = read_log(Path(row['stub_log']))
        return not marker.exists() and after_the_tool_call(log, reason or '')
    if cell in ('uv-allow-outside', 'uv-allow-mention'):
        return marker.is_file()
    return False


# ---- fixture trees for the derivation (run on every platform, before any skip)

FIXTURE_REASON = 'Blocked `pip install`. Use `uv add <pkg>` instead.'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _log_text(*bodies: object) -> str:
    rows = [
        {'kind': 'model', 'decision': 'scripted', 'step_index': i, 'body': body}
        for i, body in enumerate(bodies)
    ]
    return ''.join(json.dumps(r) + '\n' for r in rows)


def _tool_result(text: str) -> dict:
    content = [{'type': 'tool_result', 'tool_use_id': 't1', 'content': text}]
    return {'messages': [{'role': 'user', 'content': content}]}


def make_row(cell: str, folder: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the state root."""
    state, work = folder / 'state', folder / 'work'
    work.mkdir(parents=True)
    _write(state / 'runs' / RUN_ID / 'run.json', '{}')
    hook = f'PreToolUse:Bash hook error: [kit] "{FIXTURE_REASON}"'
    _write(folder / 'stub.jsonl', _log_text({'messages': []}, _tool_result(hook)))
    row = {
        'cell': cell,
        'harness': 'claude-code',
        'harness_version': '1.0.0',
        'passed': True,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': RUN_ID,
        'judge_ms_median': 1.0,
        'judge_ms_median_base': 1.0,
    }
    if cell != 'uv-deny':
        _write(work / MARKERS[cell], 'x')
    return row, state


def _plant(row: dict, state: Path) -> None:
    _write(Path(row['work_dir']) / MARKERS[row['cell']], 'x')


def _remove(row: dict, state: Path) -> None:
    (Path(row['work_dir']) / MARKERS[row['cell']]).unlink()


def _reason_first(row: dict, state: Path) -> None:
    _write(Path(row['stub_log']), _log_text(_tool_result(FIXTURE_REASON), {'messages': []}))


def _reason_cut(row: dict, state: Path) -> None:
    cut = FIXTURE_REASON.replace('<pkg>', 'pkg')
    _write(Path(row['stub_log']), _log_text({'messages': []}, _tool_result(cut)))


def _no_run(row: dict, state: Path) -> None:
    (state / 'runs' / RUN_ID / 'run.json').unlink()


BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'uv-deny': [_plant, _reason_first, _reason_cut, _no_run],
    'uv-allow-outside': [_remove, _no_run],
    'uv-allow-mention': [_remove, _no_run],
}


def check_derive() -> None:
    """Every cell derives true from a passing tree, and false after each way it can break."""
    for cell in CELLS:
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            assert derive(row, state, FIXTURE_REASON), f'{cell}: a passing tree derived false'
            assert set(row) == set(ROW_KEYS), row
        for index, broken in enumerate(BREAKS[cell]):
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, Path(tmp))
                broken(row, state)
                assert not derive(row, state, FIXTURE_REASON), f'{cell}: break {index} derived true'
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            row['run_id'] = None
            assert not derive(row, state, FIXTURE_REASON), f'{cell}: no run id derived true'
    with tempfile.TemporaryDirectory() as tmp:
        row, state = make_row('uv-deny', Path(tmp))
        assert not derive(row, state, None), 'uv-deny: no reason derived true'
        assert not derive(row, state, ''), 'uv-deny: an empty reason derived true'


# ---- the cell's event, judged and timed


def cell_event(command: str, work: Path) -> bytes:
    """The neutral event of one cell: a shell act in its work folder, of a harness needing no launch."""
    event = {
        'kit_event': 1,
        'run_id': None,
        'harness': {'name': EVENT_HARNESS, 'version': EVENT_HARNESS_VERSION},
        'session': {'id': 'rule-cell', 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': {
            'session': 'observed',
            'parent': 'unavailable',
            'root': 'unavailable',
            'origin': 'unavailable',
            'command': 'observed',
            'paths': 'not_applicable',
        },
        'act': {
            'kind': 'shell',
            'command': command,
            'argv': None,
            'paths': [],
            'cwd': str(work),
            'payload_sha256': hashlib.sha256(command.encode('utf-8')).hexdigest(),
        },
    }
    return json.dumps(event).encode('ascii')


def judge(event: bytes, policy: Path, env: dict) -> tuple[float, dict]:
    """One `kit judge` call: its wall time in ms and its verdict."""
    started = time.perf_counter()
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', 'judge', '--policy', str(policy)],
        input=event,
        capture_output=True,
        env=env,
        timeout=JUDGE_TIMEOUT_S,
        check=False,
    )
    elapsed = (time.perf_counter() - started) * 1000
    lines = proc.stdout.decode('utf-8', 'replace').splitlines()
    assert proc.returncode == 0 and len(lines) == 1, (proc.returncode, lines, proc.stderr)
    return elapsed, json.loads(lines[0])


def timed(event: bytes, policy: Path, env: dict) -> tuple[float, list[dict]]:
    """The median wall time of `TIMED_CALLS` judge calls, and their verdicts."""
    times, verdicts = [], []
    for _ in range(TIMED_CALLS):
        ms, verdict = judge(event, policy, env)
        times.append(ms)
        verdicts.append(verdict)
    return round(statistics.median(times), 1), verdicts


# ---- one cell on a real harness


def run_cell(
    cell: str,
    harness: str,
    version: str | None,
    base: Path,
    policies: dict[str, Path],
    state: Path,
    argv_env: dict,
) -> tuple[dict, list[str]]:
    """Run one cell: its row, with `passed` derived from the files it names, and its problems."""
    from harness_kit import harnesses

    driver = harnesses.get(harness)
    folder = base / 'rule-cells' / f'{harness}-{cell}-{uuid.uuid4().hex[:8]}'
    work = folder / 'work'
    work.mkdir(parents=True)
    work = work.resolve()
    if UV_LOCK[cell]:
        (work / 'uv.lock').write_bytes(b'')
    row = {
        'cell': cell,
        'harness': harness,
        'harness_version': version,
        'passed': False,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': None,
        'judge_ms_median': None,
        'judge_ms_median_base': None,
    }
    problems: list[str] = []
    reason = None
    judge_env = kit_env({'KIT_STATE_ROOT': str(folder / 'judge-state')})
    event = cell_event(COMMANDS[cell], work)
    try:
        _, first = judge(event, policies['cell'], judge_env)
        if cell == 'uv-deny':
            if first['verdict'] != 'deny' or first['rule'] != RULE_ID:
                problems.append(f'{harness}/{cell}: the untimed verdict is {first}')
            else:
                reason = first['reason']
        row['judge_ms_median'], verdicts = timed(event, policies['cell'], judge_env)
        row['judge_ms_median_base'], _ = timed(event, policies['base'], judge_env)
        seen = sorted({(v['verdict'], v['rule']) for v in verdicts}, key=str)
        print(f'{harness}/{cell}: timed verdicts {seen}', flush=True)
        if cell == 'uv-deny' and any(v['verdict'] != 'deny' for v in verdicts):
            problems.append(f'{harness}/{cell}: a timed verdict is not deny (cannot-tell): {seen}')
    except Exception as exc:  # a failed judge is a problem of the row, not a crash of the suite
        problems.append(f'{harness}/{cell}: judging failed: {type(exc).__name__}: {exc}')
    env = kit_env({'KIT_STATE_ROOT': str(state), **argv_env})
    stub, port = start_stub(folder, [driver.canary_step(COMMANDS[cell]), {'text': 'done'}], env)
    try:
        home_dir = folder / 'home'
        endpoint = f'http://127.0.0.1:{port}'
        kit(
            'home',
            'render',
            '--harness',
            harness,
            '--dir',
            str(home_dir),
            '--endpoint',
            endpoint,
            env=env,
        )
        head = ['run', '--harness', harness, '--home', str(home_dir), '--workdir', str(work)]
        head += ['--policy', str(policies['cell']), '--']
        argv = driver.canary_argv('Run the scripted tool call.')
        with open(folder / 'stdout.txt', 'wb') as out, open(folder / 'stderr.txt', 'wb') as err:
            subprocess.run(  # noqa: S603 - argv built above, no shell
                [sys.executable, '-m', 'harness_kit', *head, *argv],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=env,
                cwd=str(work),
                timeout=SESSION_TIMEOUT_S,
                check=False,
            )
    except Exception as exc:  # a failed cell is a row, not a crash of the suite
        problems.append(f'{harness}/{cell}: the session failed: {type(exc).__name__}: {exc}')
    finally:
        stub.kill()
        stub.wait()
    row['run_id'] = find_run(state, work)
    try:
        row['passed'] = derive(row, state, reason)
    except Exception as exc:
        problems.append(f'{harness}/{cell}: derivation failed: {type(exc).__name__}: {exc}')
    return row, problems


def build_policies(base: Path, env: dict) -> dict[str, Path]:
    """The conformance base policy and the policy built from it and `packs/uv`."""
    base_policy = base / 'rules-base-policy.toml'
    base_policy.write_text(policy_text(base), encoding='utf-8')
    cell_policy = base / 'rules-policy.toml'
    kit(
        'policy',
        'build',
        '--base',
        str(base_policy),
        '--pack',
        str(PACK),
        '--out',
        str(cell_policy),
        '--force',
        env=env,
    )
    return {'base': base_policy, 'cell': cell_policy}


def main() -> int:
    check_derive()
    base_raw = os.environ.get(BASE_ENV)
    chosen = [h for h in HARNESSES if os.environ.get(ARGV_ENV[h])]
    if not base_raw or not chosen:
        names = [BASE_ENV] if not base_raw else []
        names += [] if chosen else [ARGV_ENV[h] for h in HARNESSES]
        print(f'skip: the rule cells need {" and ".join(names)}')
        return 0
    if not WINDOWS:
        print('skip: the rule cells run on Windows only')
        return 0
    base = Path(base_raw)
    if not base.is_dir():
        print(f'FAIL: {BASE_ENV} is not an existing folder')
        return 1
    base = base.resolve()
    sys.path.insert(0, str(SRC))
    from harness_kit import harnesses

    argv_env = {ARGV_ENV[h]: os.environ[ARGV_ENV[h]] for h in chosen}
    state = base / 'rules-state'
    policies = build_policies(base, kit_env({'KIT_STATE_ROOT': str(state)}))
    rows: list[dict] = []
    problems: list[str] = []
    try:
        for harness in chosen:
            version = harnesses.get(harness).version(kit_env(argv_env))
            for cell in CELLS:
                row, found = run_cell(cell, harness, version, base, policies, state, argv_env)
                rows.append(row)
                problems += found
    finally:
        (base / RESULTS).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(rows, indent=2))
    bad = [f'{r["harness"]}/{r["cell"]}' for r in rows if not r['passed']]
    if bad or problems:
        print('FAIL: ' + '; '.join(bad + problems))
        return 1
    print(f'ok: rule cells passed on {", ".join(chosen)} ({len(rows)} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

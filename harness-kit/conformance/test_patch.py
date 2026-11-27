#!/usr/bin/env python3
"""Patch cells: opencode's `patch` tool judged by the paths its headers name, against a stub model.

opencode 2.2.5 offers `patch` only to a model whose id holds `gpt-` and neither `oss` nor `gpt-4`,
and then offers neither `edit` nor `write`. So each cell's test home adds such a model
(`PATCH_MODEL`) to its stub provider, and the session passes `--model` with it; the canary keeps
its own model. Each cell runs opencode headless through `kit run`, in a home rendered by
`kit home render --policy`, with a policy that `kit policy build` composes from the conformance
base policy, `packs/series` and `packs/owner-acts`. Each cell has a folder of its own under the
base, a `work` folder in it, and `SESSION_WORKFLOW_GOVERNED_HOME` set to `work/governed-home`.
Every `kit run` uses the state root `<base>/patch-state`.

- patch-plain: one `patch` call adding `work/notes.txt`. The file exists, and the call's journal
  line (the run's one file write besides the canary's lines) has verdict allow: under the
  owner-acts rule that means its paths were read, since unread paths give `unknown`.
- patch-governed: one `patch` call updating `work/governed-home/CLAUDE.md`, which the cell creates.
  The file is unchanged, and the owner-acts rule's reason is carried by a logged request after the
  tool call (whole, or the first 120 characters of the deny text `kit judge` composes).

The canary's lines (its session's, rules `canary.deny` and `canary.allow`) are left out of every
count. The account's governed files are hashed before the first cell and after the last; a change
fails the run.

A run writes `patch-results.json` under KIT_CONFORMANCE_BASE. A row has exactly `cell`, `harness`,
`harness_version`, `passed`, `stub_log`, `work_dir` and `run_id`; `passed` is
`derive(row, state, needle)`, a pure function of the files the row names, never an exit code. The
derivation is checked on fixture trees before anything starts, on every platform.

Every `kit run` of a cell passes `accept_args()`: `--accept-version` with the value of
`KIT_CONFORMANCE_ACCEPT_VERSION` when it is set, so the cells run on a version the contract
does not name yet. `harness_version` is the version the driver's probe reads for the binary
named by KIT_HARNESS_ARGV_OPENCODE, the one the cells run.

Prints `skip:` unless KIT_CONFORMANCE_BASE and KIT_HARNESS_ARGV_OPENCODE are set and the platform
is Windows. The base must be an existing folder.

Stdlib-runnable: `python test_patch.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
    read_log,
)
from test_guards import (  # noqa: E402
    DETAIL_CAP,
    DETAILS,
    GOVERNED_ENV,
    NEEDLE_CHARS,
    OWNER_RULE,
    build_policies,
    governed_hashes,
)
from test_rules import after_the_tool_call, carries  # noqa: E402

WINDOWS = os.name == 'nt'
BASE_ENV = 'KIT_CONFORMANCE_BASE'
ARGV_ENV = 'KIT_HARNESS_ARGV_OPENCODE'
HARNESS = 'opencode'
CELLS = ('patch-plain', 'patch-governed')
# Only opencode has a patch tool; the Claude Code shell runs no cell here.
CELLS_BY_HARNESS = {'claude-code': (), 'opencode': CELLS}
RESULTS = 'patch-results.json'
STATE_DIR = 'patch-state'
PATCH_MODEL_ID = 'gpt-5-probe'
PATCH_MODEL = 'stub/' + PATCH_MODEL_ID
PROMPT = 'Run the scripted tool call.'
GOVERNED = 'governed-home'
NOTES = 'notes.txt'
ADDED = 'kit-patch-cell'
ORIGINAL = 'kit-patch-original\n'
CANARY_RULES = ('canary.deny', 'canary.allow')
ROW_KEYS = ('cell', 'harness', 'harness_version', 'passed', 'stub_log', 'work_dir', 'run_id')
RUN_ID = '20261117T120000Z-0123456789ab'


def patch_text(cell: str) -> str:
    """The cell's patch: an Add of `notes.txt`, or an Update of the governed `CLAUDE.md`."""
    if cell == 'patch-plain':
        body = [f'*** Add File: {NOTES}', '+' + ADDED]
    else:
        body = [f'*** Update File: {GOVERNED}/CLAUDE.md', '@@', '-' + ORIGINAL.strip(), '+changed']
    return '\n'.join(['*** Begin Patch', *body, '*** End Patch'])


def stub_steps(cell: str) -> list[dict]:
    return [{'tool': 'patch', 'args': {'patchText': patch_text(cell)}}, {'text': 'done'}]


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


def derive(row: dict, state: Path, needle: str) -> bool:
    """Re-derive one row's `passed` from the files it names; `needle` is the owner-acts reason."""
    run_id = row.get('run_id')
    if not run_id:
        return False
    run_dir = Path(state) / 'runs' / run_id
    if not (run_dir / 'run.json').is_file():
        return False
    work = Path(row['work_dir'])
    if row.get('cell') == 'patch-plain':
        target = work / NOTES
        held = target.is_file() and target.read_text(encoding='utf-8').strip() == ADDED
        writes = [line for line in cell_journal(run_dir) if line.get('act_kind') == 'file_write']
        return held and len(writes) == 1 and writes[0].get('verdict') == 'allow'
    if row.get('cell') == 'patch-governed':
        target = work / GOVERNED / 'CLAUDE.md'
        kept = target.is_file() and target.read_text(encoding='utf-8') == ORIGINAL
        return kept and after_the_tool_call(read_log(Path(row['stub_log'])), needle)
    return False


# ---- fixture trees for the derivation (run on every platform, before any skip)

FIXTURE_NEEDLE = 'OWNER-NEEDLE'
CANARY_SESSION = 'canary-session'
CELL_SESSION = 'cell-session'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _lines(*items: dict) -> str:
    return ''.join(json.dumps(item) + '\n' for item in items)


def _log_text(*bodies: object) -> str:
    rows = [
        {'kind': 'model', 'decision': 'scripted', 'step_index': i, 'body': body}
        for i, body in enumerate(bodies)
    ]
    return ''.join(json.dumps(r) + '\n' for r in rows)


def _tool_result(text: str) -> dict:
    content = [{'type': 'tool_result', 'tool_use_id': 't1', 'content': text}]
    return {'messages': [{'role': 'user', 'content': content}]}


def _judged(session: str, kind: str, verdict: str, rule: str | None = None) -> dict:
    return {'session_id': session, 'act_kind': kind, 'verdict': verdict, 'rule': rule}


CANARY_LINES = (
    _judged(CANARY_SESSION, 'shell', 'deny', 'canary.deny'),
    _judged(CANARY_SESSION, 'shell', 'allow', 'canary.allow'),
    _judged(CANARY_SESSION, 'file_write', 'allow'),
)


def make_row(cell: str, folder: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the state root."""
    state, cell_dir = folder / 'state', folder / 'cell'
    work = cell_dir / 'work'
    (work / GOVERNED).mkdir(parents=True)
    run_dir = state / 'runs' / RUN_ID
    _write(run_dir / 'run.json', '{}')
    if cell == 'patch-plain':
        _write(work / NOTES, ADDED + '\n')
        cell_lines = (_judged(CELL_SESSION, 'file_write', 'allow'),)
        _write(cell_dir / 'stub.jsonl', _log_text({'messages': []}, _tool_result('ok')))
    else:
        _write(work / GOVERNED / 'CLAUDE.md', ORIGINAL)
        cell_lines = (_judged(CELL_SESSION, 'file_write', 'deny', OWNER_RULE),)
        hook = _tool_result('Error: ' + FIXTURE_NEEDLE)
        _write(cell_dir / 'stub.jsonl', _log_text({'messages': []}, hook))
    _write(run_dir / 'journal.ndjson', _lines(*CANARY_LINES, *cell_lines))
    row = {
        'cell': cell,
        'harness': HARNESS,
        'harness_version': '2.2.5',
        'passed': True,
        'stub_log': str(cell_dir / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': RUN_ID,
    }
    return row, state


def _journal(*items: dict) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        _write(state / 'runs' / RUN_ID / 'journal.ndjson', _lines(*CANARY_LINES, *items))

    return change


def _file(relative: str, text: str | None) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = Path(row['work_dir']) / relative
        if text is None:
            path.unlink()
        else:
            _write(path, text)

    return change


def _log(*bodies: object) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['stub_log']), _log_text(*bodies))


def _no_run(row: dict, state: Path) -> None:
    (state / 'runs' / RUN_ID / 'run.json').unlink()


BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'patch-plain': [
        _file(NOTES, None),
        _file(NOTES, 'other\n'),
        _journal(_judged(CELL_SESSION, 'file_write', 'unknown', OWNER_RULE)),
        _journal(_judged(CELL_SESSION, 'file_write', 'deny', OWNER_RULE)),
        _journal(),
        _journal(
            _judged(CELL_SESSION, 'file_write', 'allow'),
            _judged(CELL_SESSION, 'file_write', 'allow'),
        ),
        _no_run,
    ],
    'patch-governed': [
        _file(f'{GOVERNED}/CLAUDE.md', 'changed\n'),
        _file(f'{GOVERNED}/CLAUDE.md', None),
        _log({'messages': []}, _tool_result('allowed')),
        _log(_tool_result(FIXTURE_NEEDLE), {'messages': []}),
        _no_run,
    ],
}


def check_derive() -> None:
    """Every cell derives true from a passing tree, and false after each way it can break."""
    for cell in CELLS:
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            assert derive(row, state, FIXTURE_NEEDLE), f'{cell}: a passing tree derived false'
            assert set(row) == set(ROW_KEYS), row
        for index, broken in enumerate(BREAKS[cell]):
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, Path(tmp))
                broken(row, state)
                assert not derive(row, state, FIXTURE_NEEDLE), f'{cell}: break {index} derived true'
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            row['run_id'] = None
            assert not derive(row, state, FIXTURE_NEEDLE), f'{cell}: no run id derived true'
    with tempfile.TemporaryDirectory() as tmp:
        row, state = make_row('patch-governed', Path(tmp))
        assert not derive(row, state, ''), 'patch-governed: no needle derived true'
    assert set(CELLS_BY_HARNESS[HARNESS]) == set(CELLS)


# ---- one cell on the real harness


def owner_needle(log: list[dict], reason: str) -> str:
    """The whole reason when a logged request carries it, else the first 120 characters of the
    deny text `kit judge` composes for the cell's write."""
    if any(carries(r.get('body'), reason) for r in log):
        return reason
    return (DETAILS[OWNER_RULE][:DETAIL_CAP] + ' ' + reason)[:NEEDLE_CHARS]


def add_patch_model(home: dict) -> None:
    """Add `PATCH_MODEL_ID` to the home's stub provider, so opencode offers `patch`."""
    config = Path(home['config_file'])
    data = json.loads(config.read_text(encoding='utf-8'))
    data['providers']['stub']['models'][PATCH_MODEL_ID] = {'name': 'Stub patch model'}
    config.write_text(json.dumps(data, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def session_argv(driver) -> list[str]:
    """The canary's argument list with the patch model in place of its own."""
    argv = driver.canary_argv(PROMPT)
    at = argv.index('--model')
    return [*argv[: at + 1], PATCH_MODEL, *argv[at + 2 :]]


def run_cell(
    cell: str, version: str | None, base: Path, policy: Path, reason: str, argv_env: dict
) -> tuple[dict, list[str]]:
    """Run one cell: its row, with `passed` derived from the files it names, and its problems."""
    from harness_kit import harnesses
    from test_conformance import start_stub

    driver = harnesses.get(HARNESS)
    state = base / STATE_DIR
    folder = base / 'patch-cells' / f'{HARNESS}-{cell}-{uuid.uuid4().hex[:8]}'
    work = folder / 'work'
    (work / GOVERNED).mkdir(parents=True)
    work = work.resolve()
    governed = work / GOVERNED
    if cell == 'patch-governed':
        (governed / 'CLAUDE.md').write_text(ORIGINAL, encoding='utf-8')
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
    env = kit_env({'KIT_STATE_ROOT': str(state), GOVERNED_ENV: str(governed), **argv_env})
    stub, port = start_stub(folder, stub_steps(cell), env)
    try:
        home_dir = folder / 'home'
        render = ['home', 'render', '--harness', HARNESS, '--dir', str(home_dir)]
        render += ['--endpoint', f'http://127.0.0.1:{port}', '--policy', str(policy)]
        add_patch_model(json.loads(kit(*render, env=env)))
        head = ['run', '--harness', HARNESS, *accept_args(), '--home', str(home_dir)]
        head += ['--workdir', str(work), '--policy', str(policy), '--']
        with open(folder / 'stdout.txt', 'wb') as out, open(folder / 'stderr.txt', 'wb') as err:
            subprocess.run(  # noqa: S603 - argv built above, no shell
                [sys.executable, '-m', 'harness_kit', *head, *session_argv(driver)],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=env,
                cwd=str(work),
                timeout=SESSION_TIMEOUT_S,
                check=False,
            )
    except Exception as exc:  # a failed cell is a row, not a crash of the suite
        problems.append(f'{HARNESS}/{cell}: the session failed: {type(exc).__name__}: {exc}')
    finally:
        stub.kill()
        stub.wait()
    row['run_id'] = find_run(state, work)
    try:
        needle = owner_needle(read_log(Path(row['stub_log'])), reason)
        row['passed'] = derive(row, state, needle)
    except Exception as exc:
        problems.append(f'{HARNESS}/{cell}: derivation failed: {type(exc).__name__}: {exc}')
    return row, problems


def main() -> int:
    check_derive()
    base_raw = os.environ.get(BASE_ENV)
    argv_raw = os.environ.get(ARGV_ENV)
    if not base_raw or not argv_raw:
        names = [n for n, v in ((BASE_ENV, base_raw), (ARGV_ENV, argv_raw)) if not v]
        print(f'skip: the patch cells need {" and ".join(names)}')
        return 0
    if not WINDOWS:
        print('skip: the patch cells run on Windows only')
        return 0
    base = Path(base_raw)
    if not base.is_dir():
        print(f'FAIL: {BASE_ENV} is not an existing folder')
        return 1
    base = base.resolve()
    sys.path.insert(0, str(SRC))
    from harness_kit import harnesses
    from harness_kit.policy import load_policy

    before = governed_hashes()
    argv_env = {ARGV_ENV: argv_raw}
    policies = build_policies(base, kit_env({'KIT_STATE_ROOT': str(base / STATE_DIR)}))
    reason = next(r.reason for r in load_policy(policies['cell']).rules if r.id == OWNER_RULE)
    rows: list[dict] = []
    problems: list[str] = []
    try:
        version = harnesses.get(HARNESS).version(kit_env(argv_env))
        for cell in CELLS_BY_HARNESS[HARNESS]:
            row, found = run_cell(cell, version, base, policies['cell'], reason, argv_env)
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
    print(f'ok: patch cells passed on {HARNESS} ({len(rows)} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

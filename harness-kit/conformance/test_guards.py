#!/usr/bin/env python3
"""Guard cells: the series and owner-acts packs on both real harnesses, against a stub model.

Per harness, three cells run the real harness headless through `kit run`, in a
home rendered by `kit home render --policy`, with a policy that `kit policy
build` composes from the conformance base policy, `packs/series` and
`packs/owner-acts`. Each cell has a folder of its own under the base, a `work`
folder in it, and `SESSION_WORKFLOW_GOVERNED_HOME` set to `work/governed-home`,
created empty. Every `kit run` uses the state root `<base>/guards-state`.

- series-guard: the stub asks for three shell calls (`COMMANDS`): a create, the
  same create again, and the create with its series declared. A stand-in `gh`
  first on `PATH` appends `keel_series=<value>` to the cell's `gh-calls.txt`
  and prints a pull-request URL. `gh-calls.txt` ends with exactly two lines,
  `keel_series=` then `keel_series=none:kit-cell`; the series rule's reason is
  carried by the logged request with `step_index` 2 and not by the one with
  `step_index` 1; the cell session's note lines include an outcome line whose
  recorder result is `facts`.
- owner-acts-deny: one file write of `kit-guard-cell` to
  `work/governed-home/CLAUDE.md`. The file is absent, and the owner-acts rule's
  reason is carried by a logged request after the tool call.
- owner-acts-allow: the same write, under a prompt that names the act. The file
  holds `kit-guard-cell`, and the cell session's note lines include a prompt
  line whose recorder result is `facts`.

The canary's session also sends notes into the run, so a run's `notes.ndjson`
is read only for the lines whose `session_id` is not the canary's, the session
of the run's journal line whose rule is `canary.deny`. A rule's reason is
carried when a logged request holds it whole, or else the first 120 characters
of the text `kit judge` composes for the cell's deny (the rule's detail cut to
200 characters, one space, the reason), so that a harness that cuts the text
from its end keeps the needle; the run prints which of the two each cell used.

Timing, as in `test_rules.py`: each cell's first act is judged once untimed with
the cell's policy, then 20 times timed with the cell's policy and 20 times with
the base policy alone, as a `claude-code` event with no `KIT_RUN_ID` and a
`KIT_STATE_ROOT` of the cell's own. The medians are recorded and never
asserted; the 20 timed verdicts of `series-guard` must all equal its untimed
verdict. The account's governed files (`~/.claude/CLAUDE.md`, `settings.json`,
`settings.local.json`, where present) are hashed before the first cell and
after the last; a change fails the run. The test writes none of them.

A run writes `guards-results.json` under KIT_CONFORMANCE_BASE and leaves
`conformance-results.json` and `rules-results.json` alone. A row has exactly
`cell`, `harness`, `harness_version`, `passed`, `stub_log`, `work_dir`,
`run_id`, `note_lines`, `judge_ms_median` and `judge_ms_median_base`; `passed`
is `derive(row, state, needles)`, never an exit code. The derivation is checked
on fixture trees before anything starts, on every platform.

Prints `skip:` unless KIT_CONFORMANCE_BASE and at least one harness's
`KIT_HARNESS_ARGV_*` variable are set (and the platform is Windows); a harness
whose variable is unset is left out. The base must be an existing folder.

Stdlib-runnable: `python test_guards.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
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
    find_run,
    kit,
    kit_env,
    policy_text,
    read_log,
    start_stub,
)
from test_rules import after_the_tool_call, carries, judge, timed  # noqa: E402

WINDOWS = os.name == 'nt'
BASE_ENV = 'KIT_CONFORMANCE_BASE'
ARGV_ENV = {'claude-code': 'KIT_HARNESS_ARGV_CLAUDE_CODE', 'opencode': 'KIT_HARNESS_ARGV_OPENCODE'}
HARNESSES = ('claude-code', 'opencode')
RESULTS = 'guards-results.json'
STATE_DIR = 'guards-state'
PACKS = (HERE.parent / 'packs' / 'series', HERE.parent / 'packs' / 'owner-acts')
GOVERNED_ENV = 'SESSION_WORKFLOW_GOVERNED_HOME'
SERIES_RULE = 'series-second-pr-declared'
OWNER_RULE = 'owner-acts-named-by-owner'
CELLS = ('series-guard', 'owner-acts-deny', 'owner-acts-allow')
CELL_RULE = {'series-guard': SERIES_RULE, 'owner-acts-deny': OWNER_RULE}
PROMPTS = {
    'series-guard': 'Run the scripted tool call.',
    'owner-acts-deny': 'Run the scripted tool call.',
    'owner-acts-allow': 'Run the scripted tool call. Pode editar o CLAUDE.md.',
}
CREATE = 'gh pr create -R kit-probe/guard-cell --title kit-cell --body kit-cell'
COMMANDS = {
    'claude-code': (CREATE, CREATE, 'KEEL_SERIES=none:kit-cell ' + CREATE),
    'opencode': (CREATE, CREATE, "$env:KEEL_SERIES='none:kit-cell'; " + CREATE),
}
PR_URL = 'https://github.com/kit-probe/guard-cell/pull/1'
CALL_LINES = ['keel_series=', 'keel_series=none:kit-cell']
CALLS_FILE = 'gh-calls.txt'
WRITE_TEXT = 'kit-guard-cell'
TARGET = ('governed-home', 'CLAUDE.md')
# The detail each pack's rule gives for the cell's deny; the composed deny text starts with it.
DETAILS = {
    SERIES_RULE: (
        'The command carries no KEEL_SERIES. Series guard: this session already created a pull '
        'request in kit-probe/guard-cell (https://github.com/kit-probe/guard-cell/pull/1), and '
        'this command creates another there.'
    ),
    OWNER_RULE: 'Owner-acts gate: denied (write CLAUDE.md).',
}
DETAIL_CAP = 200
NEEDLE_CHARS = 120
CANARY_RULE = 'canary.deny'
GOVERNED_FILES = ('CLAUDE.md', 'settings.json', 'settings.local.json')
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
    'note_lines',
    'judge_ms_median',
    'judge_ms_median_base',
)
RUN_ID = '20261113T120000Z-0123456789ab'


# ---- the stand-in gh


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def stand_in_gh(calls: str) -> dict[str, str]:
    """The texts of the stand-in `gh` (POSIX sh) and `gh.cmd`, appending to `calls`.

    Each appends `keel_series=` and the value of KEEL_SERIES (empty when unset)
    to `calls` and prints the cell's pull-request URL. Every line of the sh text
    ends in a comment, so a carriage return a writer adds falls inside it.
    """
    posix = Path(calls).as_posix()
    sh = (
        '#!/bin/sh\n'
        f'printf \'keel_series=%s\\n\' "${{KEEL_SERIES-}}" >> {_sh_quote(posix)} #\n'
        f"printf '%s\\n' '{PR_URL}' #\n"
    )
    cmd = (
        f'@echo off\n>>"{calls.replace("%", "%%")}" echo keel_series=%KEEL_SERIES%\necho {PR_URL}\n'
    )
    return {'gh': sh, 'gh.cmd': cmd}


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


def cell_note_lines(run_dir: Path) -> list[dict]:
    """The run's note lines but those of the canary's session."""
    canary = {
        line.get('session_id')
        for line in _ndjson(run_dir / 'journal.ndjson')
        if line.get('rule') == CANARY_RULE
    }
    return [n for n in _ndjson(run_dir / 'notes.ndjson') if n.get('session_id') not in canary]


def note_counts(lines: list[dict]) -> dict[str, int]:
    return {
        kind: sum(1 for n in lines if n.get('note_kind') == kind) for kind in ('prompt', 'outcome')
    }


def _recorded(lines: list[dict], kind: str) -> bool:
    """True when a line of `kind` has a recorder whose result is `facts`."""
    for line in lines:
        recorders = line.get('recorders')
        if line.get('note_kind') != kind or not isinstance(recorders, list):
            continue
        if any(isinstance(r, dict) and r.get('result') == 'facts' for r in recorders):
            return True
    return False


def _step_carries(log: list[dict], index: int, needle: str) -> bool:
    found = [r for r in log if r.get('decision') == 'scripted' and r.get('step_index') == index]
    return any(carries(r.get('body'), needle) for r in found)


def derive(row: dict, state: Path, needles: dict) -> bool:
    """Re-derive one row's `passed` from the files it names; `needles` maps a rule id to its text."""
    run_id = row.get('run_id')
    if not run_id:
        return False
    run_dir = Path(state) / 'runs' / run_id
    if not (run_dir / 'run.json').is_file():
        return False
    work = Path(row['work_dir'])
    target = work.joinpath(*TARGET)
    cell = row['cell']
    if cell == 'series-guard':
        calls = work.parent / CALLS_FILE
        lines = calls.read_text(encoding='utf-8').splitlines() if calls.is_file() else None
        needle = needles.get(SERIES_RULE) or ''
        log = read_log(Path(row['stub_log']))
        carried = bool(needle) and _step_carries(log, 2, needle)
        carried = carried and not _step_carries(log, 1, needle)
        return lines == CALL_LINES and carried and _recorded(cell_note_lines(run_dir), 'outcome')
    if cell == 'owner-acts-deny':
        log = read_log(Path(row['stub_log']))
        needle = needles.get(OWNER_RULE) or ''
        return not target.exists() and after_the_tool_call(log, needle)
    if cell == 'owner-acts-allow':
        held = target.is_file() and target.read_text(encoding='utf-8').strip() == WRITE_TEXT
        return held and _recorded(cell_note_lines(run_dir), 'prompt')
    return False


# ---- fixture trees for the derivation (run on every platform, before any skip)

FIXTURE_NEEDLES = {SERIES_RULE: 'SERIES-NEEDLE', OWNER_RULE: 'OWNER-NEEDLE'}
CANARY_SESSION = 'canary-session'
CELL_SESSION = 'cell-session'


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


def _note(session: str, kind: str, result: str) -> dict:
    return {
        'session_id': session,
        'note_kind': kind,
        'outcome': 'recorded',
        'recorders': [{'id': 'some-check', 'result': result}],
    }


def _lines(*items: dict) -> str:
    return ''.join(json.dumps(item) + '\n' for item in items)


def _cell_notes(cell: str) -> list[dict]:
    if cell == 'series-guard':
        return [_note(CELL_SESSION, 'prompt', 'unchanged'), _note(CELL_SESSION, 'outcome', 'facts')]
    if cell == 'owner-acts-allow':
        return [_note(CELL_SESSION, 'prompt', 'facts')]
    return []


def make_row(cell: str, folder: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the state root."""
    state, cell_dir = folder / 'state', folder / 'cell'
    work = cell_dir / 'work'
    (work / TARGET[0]).mkdir(parents=True)
    run_dir = state / 'runs' / RUN_ID
    _write(run_dir / 'run.json', '{}')
    _write(run_dir / 'journal.ndjson', _lines({'session_id': CANARY_SESSION, 'rule': CANARY_RULE}))
    canary_note = _note(CANARY_SESSION, 'prompt', 'facts')
    _write(run_dir / 'notes.ndjson', _lines(canary_note, *_cell_notes(cell)))
    hook = 'PreToolUse:Bash hook error: [kit] "{}"'
    if cell == 'series-guard':
        needle = FIXTURE_NEEDLES[SERIES_RULE]
        bodies = [{'messages': []}, _tool_result(PR_URL), _tool_result(hook.format(needle))]
        _write(cell_dir / 'stub.jsonl', _log_text(*bodies, _tool_result(PR_URL)))
        _write(cell_dir / CALLS_FILE, '\n'.join(CALL_LINES) + '\n')
    elif cell == 'owner-acts-deny':
        needle = FIXTURE_NEEDLES[OWNER_RULE]
        _write(
            cell_dir / 'stub.jsonl', _log_text({'messages': []}, _tool_result(hook.format(needle)))
        )
    else:
        _write(cell_dir / 'stub.jsonl', _log_text({'messages': []}, _tool_result('ok')))
        _write(work.joinpath(*TARGET), WRITE_TEXT)
    row = {
        'cell': cell,
        'harness': 'claude-code',
        'harness_version': '1.0.0',
        'passed': True,
        'stub_log': str(cell_dir / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': RUN_ID,
        'note_lines': note_counts(_cell_notes(cell)),
        'judge_ms_median': 1.0,
        'judge_ms_median_base': 1.0,
    }
    return row, state


def _run_dir(state: Path) -> Path:
    return state / 'runs' / RUN_ID


def _calls(text: str) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['work_dir']).parent / CALLS_FILE, text)


def _log(*bodies: object) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(Path(row['stub_log']), _log_text(*bodies))


def _notes(*items: dict) -> Callable[[dict, Path], None]:
    return lambda row, state: _write(_run_dir(state) / 'notes.ndjson', _lines(*items))


def _target(text: str | None) -> Callable[[dict, Path], None]:
    def change(row: dict, state: Path) -> None:
        path = Path(row['work_dir']).joinpath(*TARGET)
        if text is None:
            path.unlink()
        else:
            _write(path, text)

    return change


def _no_run(row: dict, state: Path) -> None:
    (_run_dir(state) / 'run.json').unlink()


_SERIES_HOOK = _tool_result(FIXTURE_NEEDLES[SERIES_RULE])
_OWNER_HOOK = _tool_result(FIXTURE_NEEDLES[OWNER_RULE])
_CANARY_ONLY = (
    _note(CANARY_SESSION, 'outcome', 'facts'),
    _note(CANARY_SESSION, 'prompt', 'facts'),
    _note(CELL_SESSION, 'prompt', 'unchanged'),
    _note(CELL_SESSION, 'outcome', 'unchanged'),
)
BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'series-guard': [
        _calls('keel_series=\n'),
        _calls('keel_series=none:kit-cell\nkeel_series=\n'),
        _calls('keel_series=\nkeel_series=\nkeel_series=none:kit-cell\n'),
        lambda row, state: (Path(row['work_dir']).parent / CALLS_FILE).unlink(),
        _log({'messages': []}, _tool_result(PR_URL), _tool_result('allowed'), _tool_result(PR_URL)),
        _log({'messages': []}, _SERIES_HOOK, _SERIES_HOOK, _tool_result(PR_URL)),
        _log({'messages': []}, _tool_result(PR_URL)),
        _notes(*_CANARY_ONLY),
        _notes(_note(CELL_SESSION, 'prompt', 'facts')),
        _no_run,
    ],
    'owner-acts-deny': [
        _target(WRITE_TEXT),
        _log({'messages': []}, _tool_result('allowed')),
        _log(_OWNER_HOOK, {'messages': []}),
        _no_run,
    ],
    'owner-acts-allow': [
        _target(None),
        _target('other'),
        _notes(*_CANARY_ONLY),
        _notes(_note(CELL_SESSION, 'outcome', 'facts')),
        _no_run,
    ],
}


def check_derive() -> None:
    """Every cell derives true from a passing tree, and false after each way it can break."""
    for cell in CELLS:
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            assert derive(row, state, FIXTURE_NEEDLES), f'{cell}: a passing tree derived false'
            assert set(row) == set(ROW_KEYS), row
        for index, broken in enumerate(BREAKS[cell]):
            with tempfile.TemporaryDirectory() as tmp:
                row, state = make_row(cell, Path(tmp))
                broken(row, state)
                assert not derive(row, state, FIXTURE_NEEDLES), (
                    f'{cell}: break {index} derived true'
                )
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            row['run_id'] = None
            assert not derive(row, state, FIXTURE_NEEDLES), f'{cell}: no run id derived true'
    for cell in ('series-guard', 'owner-acts-deny'):
        with tempfile.TemporaryDirectory() as tmp:
            row, state = make_row(cell, Path(tmp))
            assert not derive(row, state, {}), f'{cell}: no needle derived true'
    with tempfile.TemporaryDirectory() as tmp:
        row, state = make_row('series-guard', Path(tmp))
        assert note_counts(cell_note_lines(_run_dir(state))) == {'prompt': 1, 'outcome': 1}


# ---- the needles and the cell's first act


def composed_needle(rule_id: str, reason: str) -> str:
    """The first 120 characters of the deny text `kit judge` composes for the cell's act."""
    return (DETAILS[rule_id][:DETAIL_CAP] + ' ' + reason)[:NEEDLE_CHARS]


def choose_needles(log: list[dict], cell: str, reasons: dict[str, str]) -> tuple[dict, str]:
    """The whole reasons when a logged request carries the cell's reason whole, else the fallback."""
    rule_id = CELL_RULE.get(cell)
    if rule_id is None or any(carries(r.get('body'), reasons[rule_id]) for r in log):
        return dict(reasons), 'whole reason'
    return {k: composed_needle(k, v) for k, v in reasons.items()}, 'first 120 characters'


def first_event(cell: str, harness: str, work: Path) -> bytes:
    """The neutral event of the cell's first act, of a harness needing no launch."""
    if cell == 'series-guard':
        command = COMMANDS[harness][0]
        act = {'kind': 'shell', 'command': command, 'argv': None, 'paths': []}
        observed = {'command': 'observed', 'paths': 'not_applicable'}
        payload = command
    else:
        target = str(work.joinpath(*TARGET))
        act = {'kind': 'file_write', 'command': None, 'argv': None, 'paths': [target]}
        observed = {'command': 'not_applicable', 'paths': 'observed'}
        payload = target
    act.update(cwd=str(work), payload_sha256=hashlib.sha256(payload.encode('utf-8')).hexdigest())
    event = {
        'kit_event': 1,
        'run_id': None,
        'harness': {'name': EVENT_HARNESS, 'version': EVENT_HARNESS_VERSION},
        'session': {'id': 'guard-cell', 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': {
            'session': 'observed',
            'parent': 'unavailable',
            'root': 'unavailable',
            'origin': 'unavailable',
            **observed,
        },
        'act': act,
    }
    return json.dumps(event).encode('ascii')


def stub_steps(cell: str, driver, work: Path) -> list[dict]:
    """The stub's script for one cell: its tool calls, then a closing text."""
    if cell == 'series-guard':
        steps = [driver.canary_step(command) for command in COMMANDS[driver.name]]
    else:
        target = str(work.joinpath(*TARGET))
        claude = driver.name == 'claude-code'
        name, key = ('Write', 'file_path') if claude else ('write', 'path')
        steps = [{'tool': name, 'args': {key: target, 'content': WRITE_TEXT}}]
    return [*steps, {'text': 'done'}]


# ---- the account's governed files


def governed_hashes() -> dict[str, str | None]:
    """SHA-256 of each governed file of the running account, None where absent; reads only."""
    folder = Path.home() / '.claude'
    hashes: dict[str, str | None] = {}
    for name in GOVERNED_FILES:
        path = folder / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return hashes


# ---- one cell on a real harness


def place_stand_in(folder: Path) -> Path:
    """The cell's `bin` with the stand-in `gh` and `gh.cmd`, written byte for byte."""
    bin_dir = folder / 'bin'
    bin_dir.mkdir()
    for name, text in stand_in_gh(str(folder / CALLS_FILE)).items():
        (bin_dir / name).write_bytes(text.encode('ascii'))
    (bin_dir / 'gh').chmod(0o755)
    return bin_dir


def run_cell(
    cell: str,
    harness: str,
    version: str | None,
    base: Path,
    policies: dict[str, Path],
    reasons: dict[str, str],
    argv_env: dict,
) -> tuple[dict, list[str]]:
    """Run one cell: its row, with `passed` derived from the files it names, and its problems."""
    from harness_kit import harnesses

    driver = harnesses.get(harness)
    state = base / STATE_DIR
    folder = base / 'guard-cells' / f'{harness}-{cell}-{uuid.uuid4().hex[:8]}'
    work = folder / 'work'
    (work / TARGET[0]).mkdir(parents=True)
    work = work.resolve()
    governed = work / TARGET[0]
    bin_dir = place_stand_in(folder)
    row = {
        'cell': cell,
        'harness': harness,
        'harness_version': version,
        'passed': False,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': None,
        'note_lines': {'prompt': 0, 'outcome': 0},
        'judge_ms_median': None,
        'judge_ms_median_base': None,
    }
    problems: list[str] = []
    judge_env = kit_env(
        {'KIT_STATE_ROOT': str(folder / 'judge-state'), GOVERNED_ENV: str(governed)}
    )
    event = first_event(cell, harness, work)
    try:
        _, first = judge(event, policies['cell'], judge_env)
        row['judge_ms_median'], verdicts = timed(event, policies['cell'], judge_env)
        row['judge_ms_median_base'], _ = timed(event, policies['base'], judge_env)
        seen = sorted({(v['verdict'], v['rule']) for v in verdicts}, key=str)
        print(
            f'{harness}/{cell}: untimed {first["verdict"]}/{first["rule"]}, timed {seen}',
            flush=True,
        )
        if cell == 'series-guard' and any(v != first for v in verdicts):
            problems.append(
                f'{harness}/{cell}: a timed verdict differs from the untimed one: {seen}'
            )
    except Exception as exc:  # a failed judge is a problem of the row, not a crash of the suite
        problems.append(f'{harness}/{cell}: judging failed: {type(exc).__name__}: {exc}')
    env = kit_env({'KIT_STATE_ROOT': str(state), GOVERNED_ENV: str(governed), **argv_env})
    path_key = next((k for k in env if k.upper() == 'PATH'), 'PATH')
    env[path_key] = str(bin_dir) + os.pathsep + env.get(path_key, '')
    found = shutil.which('gh', path=env[path_key])
    if found is None or Path(found).parent.resolve() != bin_dir.resolve():
        problems.append(f'{harness}/{cell}: gh resolves to {found}, not the stand-in')
        return row, problems
    stub, port = start_stub(folder, stub_steps(cell, driver, work), env)
    try:
        home_dir = folder / 'home'
        render = ['home', 'render', '--harness', harness, '--dir', str(home_dir)]
        render += ['--endpoint', f'http://127.0.0.1:{port}', '--policy', str(policies['cell'])]
        kit(*render, env=env)
        head = ['run', '--harness', harness, '--home', str(home_dir), '--workdir', str(work)]
        head += ['--policy', str(policies['cell']), '--']
        argv = driver.canary_argv(PROMPTS[cell])
        if cell != 'series-guard' and harness == 'claude-code':
            argv = [*argv, 'Write']
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
        if row['run_id']:
            row['note_lines'] = note_counts(cell_note_lines(state / 'runs' / row['run_id']))
        needles, used = choose_needles(read_log(Path(row['stub_log'])), cell, reasons)
        if cell in CELL_RULE:
            print(f'{harness}/{cell}: needle {used}', flush=True)
        row['passed'] = derive(row, state, needles)
    except Exception as exc:
        problems.append(f'{harness}/{cell}: derivation failed: {type(exc).__name__}: {exc}')
    return row, problems


def build_policies(base: Path, env: dict) -> dict[str, Path]:
    """The conformance base policy and the policy built from it and the two packs."""
    base_policy = base / 'guards-base-policy.toml'
    base_policy.write_text(policy_text(base), encoding='utf-8')
    cell_policy = base / 'guards-policy.toml'
    packs = [arg for pack in PACKS for arg in ('--pack', str(pack))]
    build = ['policy', 'build', '--base', str(base_policy), *packs]
    kit(*build, '--out', str(cell_policy), '--force', env=env)
    return {'base': base_policy, 'cell': cell_policy}


def main() -> int:
    check_derive()
    base_raw = os.environ.get(BASE_ENV)
    chosen = [h for h in HARNESSES if os.environ.get(ARGV_ENV[h])]
    if not base_raw or not chosen:
        names = [BASE_ENV] if not base_raw else []
        names += [] if chosen else [ARGV_ENV[h] for h in HARNESSES]
        print(f'skip: the guard cells need {" and ".join(names)}')
        return 0
    if not WINDOWS:
        print('skip: the guard cells run on Windows only')
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
    argv_env = {ARGV_ENV[h]: os.environ[ARGV_ENV[h]] for h in chosen}
    policies = build_policies(base, kit_env({'KIT_STATE_ROOT': str(base / STATE_DIR)}))
    rules = {rule.id: rule.reason for rule in load_policy(policies['cell']).rules}
    reasons = {SERIES_RULE: rules[SERIES_RULE], OWNER_RULE: rules[OWNER_RULE]}
    rows: list[dict] = []
    problems: list[str] = []
    try:
        for harness in chosen:
            version = harnesses.get(harness).version(kit_env(argv_env))
            for cell in CELLS:
                row, found = run_cell(cell, harness, version, base, policies, reasons, argv_env)
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
    print(f'ok: guard cells passed on {", ".join(chosen)} ({len(rows)} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

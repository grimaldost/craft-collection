#!/usr/bin/env python3
"""Wiring cells: bare opencode starts on a wired copy of a test global configuration.

Each cell writes a test global configuration into its folder (the stub provider, comments and
an existing, empty `plugins` array), wires a copy of it with `kit home wire` (the kit shell
materialized into the cell's `kit-shell` folder, the copy written to its `config` folder),
records the line of `kit home wire --check` on the copy in `wire-check.txt`, and starts
`opencode run --standalone --format json --auto` without `kit run` and without `KIT_RUN_ID`.
The session's environment is the one `kit run` builds for a test home's session, from its
allow list: the profile, the XDG folders and the temporary folder inside the cell's folder,
`KIT_STATE_ROOT` the cell's `state` folder and `KIT_POLICY` the conformance base policy, with
`OPENCODE_CONFIG_DIR` at the wired copy's folder. The stub, which the cell runs (`kit stub`,
its log `stub.jsonl` in the cell's folder), scripts one shell call,
`echo probe > wiring.marker`, then a closing text.

- bare-start-denied: the call is denied by `launcher.required`: the marker is absent, and a
  journal line outside any run, under the cell's state root, records that deny.
- bare-start-project-removal: the working folder's `opencode.jsonc` holds
  `{"plugins": ["-harness-kit"]}`, which removes the kit plugin in a bare start, as measured
  on opencode 2.2.5: the call runs unjudged, its marker present and no journal line anywhere
  in the cell's folder.
- bare-start-no-policy: as a real bare start, neither `KIT_POLICY` nor `KIT_STATE_ROOT` is
  set, so the default state root lies in the cell's profile (`home/Local/harness-kit`). The
  call is denied as `unknown`, for want of a policy: the marker is absent, a journal line
  under that root records an `unknown` with no rule, nothing is journaled under the cell's
  `state` folder, and a request after the call carries `no policy`.

Every cell needs `wire-check.txt` to say `wired:`. These cells start no `kit run`, so they
need no `--accept-version`: only `kit run` refuses a version.

A run writes `wiring-results.json` under KIT_CONFORMANCE_BASE. A row has exactly `cell`,
`harness`, `harness_version`, `passed`, `stub_log`, `work_dir` and `run_id` (null: a bare
start has no run); `passed` is `derive(row)`, a pure function of the files in the cell's
folder (the parent of `work_dir`), never an exit code. The derivation is checked on fixture
trees before anything starts, on every platform. `harness_version` is the version the
driver's probe reads for the binary named by KIT_HARNESS_ARGV_OPENCODE, the one the cells
run. The account's governed Claude Code files and its opencode configuration folder are
hashed before the first cell and after the last, and only read.

Prints `skip:` unless KIT_CONFORMANCE_BASE and KIT_HARNESS_ARGV_OPENCODE are set and the platform
is Windows. The base must be an existing folder.

Stdlib-runnable: `python test_wiring.py`.
"""

from __future__ import annotations

import hashlib
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
    kit,
    kit_env,
    policy_text,
    read_log,
    start_stub,
)
from test_guards import governed_hashes  # noqa: E402
from test_rules import after_the_tool_call  # noqa: E402

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from harness_kit.harnesses.opencode import MODEL, PROVIDER_PACKAGE  # noqa: E402

WINDOWS = os.name == 'nt'
BASE_ENV = 'KIT_CONFORMANCE_BASE'
ARGV_ENV = 'KIT_HARNESS_ARGV_OPENCODE'
HARNESS = 'opencode'
CELLS = ('bare-start-denied', 'bare-start-project-removal', 'bare-start-no-policy')
# Only opencode's configuration is wired; the Claude Code driver runs no cell here.
CELLS_BY_HARNESS = {'claude-code': (), 'opencode': CELLS}
RESULTS = 'wiring-results.json'
ROW_KEYS = ('cell', 'harness', 'harness_version', 'passed', 'stub_log', 'work_dir', 'run_id')
PROMPT = 'Run the scripted tool call.'
MARKER = 'wiring.marker'
COMMAND = f'echo probe > {MARKER}'
WIRE_CHECK = 'wire-check.txt'
CELL_STATE = ('state',)
# The default state root of a session whose profile is the cell's `home` folder (Windows).
DEFAULT_STATE = ('home', 'Local', 'harness-kit')
LAUNCHER_RULE = 'launcher.required'
NO_POLICY = 'no policy'
PROJECT_REMOVAL = '{"plugins": ["-harness-kit"]}\n'


def global_configuration(endpoint: str) -> str:
    """The cell's test global configuration: the stub provider, comments and an empty
    `plugins` array, as JSONC with trailing commas."""
    return f"""\
// A test global configuration of a wiring cell: the stub provider only.
{{
  "model": "{MODEL}", // the cell's stub
  /* kit home wire appends the kit shell to this array */
  "plugins": [],
  "providers": {{
    "stub": {{
      "name": "Stub",
      "env": ["STUB_API_KEY"],
      "package": "{PROVIDER_PACKAGE}",
      "settings": {{"baseURL": "{endpoint}/v1"}},
      "models": {{"stub-model": {{"name": "Stub Model"}}}},
    }},
  }},
}}
"""


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


def journal_lines(folder: Path) -> list[dict]:
    """Every journal line at any depth under `folder`."""
    if not folder.is_dir():
        return []
    return [line for path in sorted(folder.rglob('journal.ndjson')) for line in _ndjson(path)]


def _bare(lines: list[dict], verdict: str, rule: str | None) -> bool:
    """True when one line records a bare opencode call with this verdict and rule."""
    return any(
        line.get('launched') is False
        and line.get('harness') == HARNESS
        and line.get('verdict') == verdict
        and line.get('rule') == rule
        for line in lines
    )


def derive(row: dict, state: Path | None = None) -> bool:
    """Re-derive one row's `passed` from the files in the cell's folder.

    The cell's folder is the parent of `work_dir`; `state`, when given, names the cell's state
    root in place of its `state` folder.
    """
    work = Path(row['work_dir'])
    folder = work.parent
    cell_state = Path(state) if state is not None else folder.joinpath(*CELL_STATE)
    check = folder / WIRE_CHECK
    if not check.is_file() or not check.read_text(encoding='utf-8').startswith('wired: '):
        return False
    marker = (work / MARKER).exists()
    if row.get('cell') == 'bare-start-denied':
        lines = journal_lines(cell_state)
        launched = [x for x in lines if x.get('launched') is not False]
        return not marker and _bare(lines, 'deny', LAUNCHER_RULE) and not launched
    if row.get('cell') == 'bare-start-project-removal':
        return marker and not journal_lines(folder) and not journal_lines(cell_state)
    if row.get('cell') == 'bare-start-no-policy':
        default = journal_lines(folder.joinpath(*DEFAULT_STATE))
        carried = after_the_tool_call(read_log(Path(row['stub_log'])), NO_POLICY)
        quiet = not journal_lines(cell_state)
        return not marker and _bare(default, 'unknown', None) and quiet and carried
    return False


# ---- fixture trees for the derivation (run on every platform, before any skip)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _log_text(*bodies: object) -> str:
    rows = [
        {'kind': 'model', 'decision': 'scripted', 'step_index': i, 'body': body}
        for i, body in enumerate(bodies)
    ]
    return ''.join(json.dumps(r) + '\n' for r in rows)


def _line(verdict: str, rule: str | None, launched: bool = False) -> dict:
    return {
        'run_id': None,
        'launched': launched,
        'harness': HARNESS,
        'verdict': verdict,
        'rule': rule,
    }


def _journal(where: tuple[str, ...], *lines: dict) -> Callable[[dict, Path], None]:
    def change(row: dict, folder: Path) -> None:
        path = folder.joinpath(*where, 'not-launched', 'abc', 'journal.ndjson')
        _write(path, ''.join(json.dumps(line) + '\n' for line in lines))

    return change


NO_POLICY_REASON = 'unreadable policy: no policy: pass --policy or set KIT_POLICY'


def make_row(cell: str, base: Path) -> tuple[dict, Path]:
    """A tree in which one cell passed: its row, and the cell's folder."""
    folder = base / 'cell'
    work = folder / 'work'
    work.mkdir(parents=True)
    _write(folder / WIRE_CHECK, 'wired: config lists kit-shell\n')
    reason = NO_POLICY_REASON if cell == 'bare-start-no-policy' else 'done'
    _write(folder / 'stub.jsonl', _log_text({'messages': []}, {'tool_result': reason}))
    if cell == 'bare-start-denied':
        _journal(CELL_STATE, _line('deny', LAUNCHER_RULE))({}, folder)
    elif cell == 'bare-start-project-removal':
        _write(work / MARKER, 'probe\n')
    else:
        _journal(DEFAULT_STATE, _line('unknown', None))({}, folder)
    row = {
        'cell': cell,
        'harness': HARNESS,
        'harness_version': '2.2.5',
        'passed': True,
        'stub_log': str(folder / 'stub.jsonl'),
        'work_dir': str(work),
        'run_id': None,
    }
    return row, folder


def _file(name: str, text: str | None) -> Callable[[dict, Path], None]:
    def change(row: dict, folder: Path) -> None:
        path = folder / name
        if text is None:
            path.unlink()
        else:
            _write(path, text)

    return change


def _log(*bodies: object) -> Callable[[dict, Path], None]:
    return lambda row, folder: _write(Path(row['stub_log']), _log_text(*bodies))


COMMON: list[Callable[[dict, Path], None]] = [
    _file(WIRE_CHECK, None),
    _file(WIRE_CHECK, 'not wired: config does not list kit-shell\n'),
]
BREAKS: dict[str, list[Callable[[dict, Path], None]]] = {
    'bare-start-denied': [
        _file(f'work/{MARKER}', 'probe\n'),
        _journal(CELL_STATE),
        _journal(CELL_STATE, _line('allow', None)),
        _journal(CELL_STATE, _line('deny', 'other')),
        _journal(CELL_STATE, {**_line('deny', LAUNCHER_RULE), 'harness': 'claude-code'}),
        _journal(CELL_STATE, _line('deny', LAUNCHER_RULE, launched=True)),
        _journal(CELL_STATE, _line('deny', LAUNCHER_RULE), _line('allow', None, launched=True)),
        lambda row, folder: (
            _journal(CELL_STATE)(row, folder),
            _journal(DEFAULT_STATE, _line('deny', LAUNCHER_RULE))(row, folder),
        ),
    ],
    'bare-start-project-removal': [
        _file(f'work/{MARKER}', None),
        _journal(CELL_STATE, _line('allow', None)),
        _journal(DEFAULT_STATE, _line('deny', LAUNCHER_RULE)),
        _journal(('elsewhere',), _line('allow', None)),
    ],
    'bare-start-no-policy': [
        _file(f'work/{MARKER}', 'probe\n'),
        _journal(DEFAULT_STATE),
        _journal(DEFAULT_STATE, _line('deny', LAUNCHER_RULE)),
        _journal(DEFAULT_STATE, _line('unknown', 'some-rule')),
        _journal(CELL_STATE, _line('unknown', None)),
        _log({'messages': []}, {'tool_result': 'done'}),
        _log({'tool_result': NO_POLICY_REASON}, {'messages': []}),
    ],
}


def check_derive() -> None:
    """Every cell derives true from a passing tree, and false after each way it can break."""
    for cell in CELLS:
        with tempfile.TemporaryDirectory() as tmp:
            row, folder = make_row(cell, Path(tmp))
            assert derive(row), f'{cell}: a passing tree derived false'
            assert derive(row, folder / 'state'), f'{cell}: the named state root derived false'
            assert set(row) == set(ROW_KEYS), row
        for index, broken in enumerate([*COMMON, *BREAKS[cell]]):
            with tempfile.TemporaryDirectory() as tmp:
                row, folder = make_row(cell, Path(tmp))
                broken(row, folder)
                assert not derive(row), f'{cell}: break {index} derived true'
    with tempfile.TemporaryDirectory() as tmp:
        row, _ = make_row('bare-start-denied', Path(tmp))
        row['cell'] = 'another-cell'
        assert not derive(row), 'an unknown cell derived true'
    assert set(CELLS_BY_HARNESS[HARNESS]) == set(CELLS) and CELLS_BY_HARNESS['claude-code'] == ()


# ---- the account's own configuration, only read


def account_opencode_folder(env: dict | None = None) -> Path:
    """The account's opencode configuration folder: `OPENCODE_CONFIG_DIR`, else
    `XDG_CONFIG_HOME` plus `opencode`, else the profile's `.config/opencode`."""
    env = os.environ if env is None else env
    if env.get('OPENCODE_CONFIG_DIR'):
        return Path(env['OPENCODE_CONFIG_DIR'])
    if env.get('XDG_CONFIG_HOME'):
        return Path(env['XDG_CONFIG_HOME']) / 'opencode'
    return Path.home() / '.config' / 'opencode'


def folder_hashes(folder: Path) -> dict[str, str]:
    """SHA-256 of every file under `folder`, by relative path; reads only."""
    if not folder.is_dir():
        return {}
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob('*'))
        if path.is_file()
    }


def account_hashes() -> dict:
    return {
        'claude': governed_hashes(),
        'opencode': folder_hashes(account_opencode_folder()),
    }


# ---- one cell on the real harness


def bare_env(
    driver, folder: Path, config: Path, endpoint: str, environ: dict, policy: Path, policy_set: bool
) -> dict:
    """The environment `kit run` builds for a test home's session in `folder`, with
    `OPENCODE_CONFIG_DIR` at `config`'s folder, less `KIT_RUN_ID`; less `KIT_POLICY` and
    `KIT_STATE_ROOT` too unless `policy_set`."""
    from harness_kit import launcher, state

    home = {'dir': str(folder), 'endpoint': endpoint, 'config_file': str(config)}
    session = folder / 'session'
    for sub in (session / 'tmp', session / 'gh-config', folder / 'home' / 'Roaming'):
        sub.mkdir(parents=True, exist_ok=True)
    (folder / 'home' / 'Local').mkdir(parents=True, exist_ok=True)
    (session / 'gitconfig-empty').touch()
    env, _ = launcher.build_env(
        driver,
        home,
        environ,
        run_dir=session,
        run_id='',
        root=folder.joinpath(*CELL_STATE),
        policy_path=policy,
        workdir=folder / 'work',
    )
    drop = [state.RUN_ID_ENV]
    if not policy_set:
        drop += ['KIT_POLICY', state.STATE_ROOT_ENV]
    for name in drop:
        for key in [k for k in env if k.upper() == name]:
            del env[key]
    return env


def run_cell(
    cell: str, version: str | None, base: Path, policy: Path, argv_env: dict
) -> tuple[dict, list[str]]:
    """Run one cell: its row, with `passed` derived from the files of its folder, and its
    problems."""
    from harness_kit import harnesses

    driver = harnesses.get(HARNESS)
    folder = base / 'wiring-cells' / f'{HARNESS}-{cell}-{uuid.uuid4().hex[:8]}'
    (folder / 'work').mkdir(parents=True)
    folder = folder.resolve()
    work = folder / 'work'
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
    env = kit_env({'KIT_STATE_ROOT': str(folder.joinpath(*CELL_STATE)), **argv_env})
    stub, port = start_stub(folder, [driver.canary_step(COMMAND), {'text': 'done'}], env)
    try:
        endpoint = f'http://127.0.0.1:{port}'
        source = folder / 'global' / 'opencode.jsonc'
        source.parent.mkdir()
        source.write_text(global_configuration(endpoint), encoding='utf-8')
        shell_dir, config = folder / 'kit-shell', folder / 'config' / 'opencode.jsonc'
        wire = ['home', 'wire', '--harness', HARNESS, '--config', str(source)]
        kit(*wire, '--shell-dir', str(shell_dir), '--out', str(config), env=env)
        checked = [
            'home',
            'wire',
            '--check',
            '--config',
            str(config),
            '--shell-dir',
            str(shell_dir),
        ]
        check = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, '-m', 'harness_kit', *checked],
            capture_output=True,
            text=True,
            encoding='utf-8',
            env=env,
            timeout=60,
            check=False,
        )
        (folder / WIRE_CHECK).write_text(check.stdout, encoding='utf-8')
        if cell == 'bare-start-project-removal':
            (work / 'opencode.jsonc').write_text(PROJECT_REMOVAL, encoding='utf-8')
        policy_set = cell != 'bare-start-no-policy'
        session = bare_env(driver, folder, config, endpoint, env, policy, policy_set)
        binary = driver.binary_argv(env)
        if not binary:
            raise RuntimeError('the opencode binary was not found')
        with open(folder / 'stdout.txt', 'wb') as out, open(folder / 'stderr.txt', 'wb') as err:
            subprocess.run(  # noqa: S603 - argv built by the cell, no shell
                [*binary, *driver.canary_argv(PROMPT)],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=session,
                cwd=str(work),
                timeout=SESSION_TIMEOUT_S,
                check=False,
            )
    except Exception as exc:  # a failed cell is a row, not a crash of the suite
        problems.append(f'{HARNESS}/{cell}: the session failed: {type(exc).__name__}: {exc}')
    finally:
        stub.kill()
        stub.wait()
    try:
        row['passed'] = derive(row)
    except Exception as exc:
        problems.append(f'{HARNESS}/{cell}: derivation failed: {type(exc).__name__}: {exc}')
    return row, problems


def main() -> int:
    check_derive()
    base_raw = os.environ.get(BASE_ENV)
    argv_raw = os.environ.get(ARGV_ENV)
    if not base_raw or not argv_raw:
        names = [n for n, v in ((BASE_ENV, base_raw), (ARGV_ENV, argv_raw)) if not v]
        print(f'skip: the wiring cells need {" and ".join(names)}')
        return 0
    if not WINDOWS:
        print('skip: the wiring cells run on Windows only')
        return 0
    base = Path(base_raw)
    if not base.is_dir():
        print(f'FAIL: {BASE_ENV} is not an existing folder')
        return 1
    base = base.resolve()
    from harness_kit import harnesses

    before = account_hashes()
    policy = base / 'wiring-policy.toml'
    policy.write_text(policy_text(base), encoding='utf-8')
    argv_env = {ARGV_ENV: argv_raw}
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
    after = account_hashes()
    if after != before:
        problems.append("the account's governed files or opencode configuration folder changed")
    print(json.dumps(rows, indent=2))
    bad = [f'{r["harness"]}/{r["cell"]}' for r in rows if not r['passed']]
    if bad or problems:
        print('FAIL: ' + '; '.join(bad + problems))
        return 1
    print(f'ok: wiring cells passed on {HARNESS} ({len(rows)} cells)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

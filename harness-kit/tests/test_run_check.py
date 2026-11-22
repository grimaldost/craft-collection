#!/usr/bin/env python3
"""Checks of how `kit run` governs a session's configuration, with a fake harness.

Contract under test:
- `run.json` holds `protected` (the home's configuration and shell folders, `home.json`,
  `run-open.json`, the state root, the policy file, the judge's import surface: the folder
  that holds `harness_kit`, each folder a checker puts on `sys.path`, the checker files, the
  interpreter's `sys.prefix` and `sys.base_prefix`; the project-config names in the working
  folder and every folder of the project walk, `.agents` in the working folder, the system
  opencode folder, the account's Claude Code home and opencode configuration folder),
  `protected_except` (the run's `tmp` folder) and `policy_sha256`; neither the working folder
  nor any folder holding it is protected, even when `kit run` starts there with `-m`;
- the check during the run ends a session that changes a watched file, rewrites one and
  restores its bytes 300 ms later, edits the policy file or `run.json`, creates a
  project-config name in the working folder or writes a file under `xdg/config/`, with
  `config-changed`, the changed names in `config_changed` and exit 66; a change made just
  before the session exits is found by the read after its end; a session that changes nothing
  ends as before; the check watches a Claude Code home too;
- after a `config-changed` end the home holds `config-changed.json` with `run_id` and
  `carried` (the changed paths outside the home and the run's folder), the exit lines name
  each carried path, and the next `kit run` on that home is refused with exit 64 and no run,
  naming the run and each carried path;
- a project-config name in the working folder is refused in interactive mode, and recorded
  for a headless test home; a system opencode configuration folder is refused in every mode;
- in interactive mode, a home whose `shell_config.json` names a judge other than this kit's
  is refused with exit 64 and no run.

Stdlib-runnable: `python test_run_check.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import harnesses, launcher, watch
from harness_kit.harnesses.opencode import OpenCode
from kit_fixtures import SRC, run_module
from test_launcher import OPENCODE_ARGS, PINNED, SESSION_ARGS, Case, scratch

WINDOWS = os.name == 'nt'
FAKE = Path(__file__).resolve().parent / 'governance_fake_harness.py'
INTERACTIVE_ARGS = ['--standalone']
SLEEP = ['sleep', 30]


def make_case(harness: str = 'opencode', actions: list | tuple = ()) -> Case:
    case = Case(scratch(), harness)
    case.argv = [sys.executable, str(FAKE), str(case.out), PINNED[harness], json.dumps(actions)]
    return case


def accounts(case: Case) -> dict:
    return {
        'CLAUDE_CONFIG_DIR': str(case.base / 'account-claude'),
        'OPENCODE_CONFIG_DIR': str(case.base / 'account-opencode'),
    }


def norm(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def within(path: str | Path, base: str | Path) -> bool:
    p, b = norm(path), norm(base)
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


def done(case: Case) -> None:
    shutil.rmtree(case.base, ignore_errors=True)


def run(case: Case, args: list[str] | None = None, mode: str | None = None, cwd=None, **env):
    head = ['run', '--harness', case.harness]
    head += ['--mode', mode] if mode else []
    head += ['--home', str(case.home), '--workdir', str(case.work), '--policy', str(case.policy)]
    full = case.env(**accounts(case), **env)
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *head, '--', *(args or SESSION_ARGS[case.harness])],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=full,
        cwd=str(cwd or case.base),
        timeout=180,
    )
    return proc, time.time()


def refused(case: Case, proc, needle: str) -> None:
    assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
    lines = proc.stderr.splitlines()
    assert len(lines) == 1, lines
    assert needle in lines[0], (needle, lines)


# ---- run.json


def _checker_policy(case: Case) -> tuple[Path, Path]:
    lib = case.base / 'checker-lib'
    lib.mkdir()
    (lib / 'helper_mod.py').write_text('VALUE = 1\n', encoding='utf-8')
    checker = case.base / 'chk.py'
    body = (
        'import sys\n'
        'sys.dont_write_bytecode = True\n'
        f'sys.path.insert(0, {str(lib)!r})\n'
        'import helper_mod\n'
        'def check(act, observation):\n'
        "    return {'result': 'no-match'}\n"
    )
    checker.write_text(body, encoding='utf-8')
    sha = hashlib.sha256(checker.read_bytes()).hexdigest()
    roots = json.dumps(str(case.tests))
    case.policy.write_text(
        f'version = 2\n\n[launcher]\ntest_roots = [{roots}]\nforbidden_roots = []\n\n'
        f'[[checker]]\nid = "c"\nfile = {json.dumps(checker.as_posix())}\nsha256 = "{sha}"\n\n'
        '[[rule]]\nid = "r"\neffect = "deny"\ngoverned = false\nkinds = ["shell"]\n'
        'check = "c"\nreason = "x"\n',
        encoding='utf-8',
    )
    return lib, checker


def test_run_json_records_the_protected_paths():
    case = make_case()
    try:
        lib, checker = _checker_policy(case)
        proc, _ = run(case, cwd=case.work)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        record = case.run_json()
        protected = [norm(p) for p in record['protected']]
        run_dir = case.state.resolve() / 'runs' / record['run_id']
        assert record['protected_except'] == [str(run_dir / 'tmp')], record['protected_except']
        sha = hashlib.sha256(case.policy.read_bytes()).hexdigest()
        assert record['policy_sha256'] == sha, record['policy_sha256']
        home = case.home
        want = [
            home / 'conf',
            home / 'kit-shell',
            home / 'xdg' / 'config',
            home / 'home.json',
            home / 'run-open.json',
            case.state.resolve(),
            case.policy,
            SRC.resolve(),
            lib,
            checker,
            Path(sys.prefix),
            Path(sys.base_prefix),
            case.work / 'opencode.json',
            case.work / 'opencode.jsonc',
            case.work / '.opencode',
            case.work / '.agents',
            case.tests / 'opencode.jsonc',
            case.base / '.opencode',
            case.state.resolve() / 'runs' / 'opencode.json',
            harnesses.get('opencode').system_config_dir(),
            case.base / 'account-claude',
            case.base / 'account-opencode',
        ]
        missing = [str(p) for p in want if norm(p) not in protected]
        assert not missing, (missing, record['protected'])
        inside = [p for p in record['protected'] if within(case.work, p)]
        assert not inside, inside
        assert norm(lib / 'helper_mod.py') not in protected, record['protected']
    finally:
        done(case)


def test_a_claude_code_run_records_its_own_home_folders():
    case = make_case('claude-code')
    try:
        proc, _ = run(case)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        protected = [norm(p) for p in case.run_json()['protected']]
        for path in (case.home / 'claude-config', case.home / 'kit-shell', case.policy):
            assert norm(path) in protected, (path, protected)
        assert norm(case.work / '.claude' / 'settings.json') in protected, protected
    finally:
        done(case)


# ---- the check during the run


def _ended(
    case: Case, actions: list, needle: str | None, **kw
) -> tuple[dict, subprocess.CompletedProcess]:
    case.argv[-1] = json.dumps(actions)
    proc, ended = run(case, **kw)
    assert proc.returncode == 66, (proc.returncode, proc.stdout, proc.stderr)
    record = case.run_json()
    assert record['outcome'] == 'config-changed', record
    if needle is not None:
        assert needle in record['config_changed'], (needle, record['config_changed'])
    assert not Path(str(case.out) + '.after').exists(), 'the session ran to its end'
    changed = Path(str(case.out) + '.changed')
    if changed.exists():
        took = ended - float(changed.read_text(encoding='ascii'))
        assert took < 15, took
    return record, proc


def test_a_changed_watched_file_ends_the_session():
    case = make_case()
    try:
        record, proc = _ended(
            case, [['append', 'home:conf/opencode.jsonc'], SLEEP], 'conf/opencode.jsonc'
        )
        assert record['config_changed'] == ['conf/opencode.jsonc'], record
        assert 'conf/opencode.jsonc' in proc.stderr, proc.stderr
        marker = json.loads((case.home / 'config-changed.json').read_text(encoding='utf-8'))
        assert marker == {'run_id': record['run_id'], 'carried': []}, marker
        assert not (case.home / 'run-open.json').exists()
        again, _ = run(case)
        refused(case, again, record['run_id'])
        assert len(case.runs()) == 1, case.runs()
    finally:
        done(case)


def test_a_rewrite_restored_300_ms_later_ends_the_session():
    case = make_case()
    try:
        _ended(case, [['rewrite', 'home:conf/opencode.jsonc', 300], SLEEP], 'conf/opencode.jsonc')
    finally:
        done(case)


def test_a_policy_edit_carries_into_a_new_home():
    case = make_case()
    try:
        record, proc = _ended(case, [['append', 'policy'], SLEEP], str(case.policy))
        marker = json.loads((case.home / 'config-changed.json').read_text(encoding='utf-8'))
        assert marker['carried'] == [str(case.policy)], marker
        lines = [line for line in proc.stderr.splitlines() if str(case.policy) in line]
        assert any('carries into a new home' in line for line in lines), proc.stderr
        again, _ = run(case)
        refused(case, again, str(case.policy))
        assert record['run_id'] in again.stderr, again.stderr
        case.policy.write_text('not a policy [', encoding='utf-8')
        again, _ = run(case)
        refused(case, again, str(case.policy))
        assert 'carries into a new home' in again.stderr, again.stderr
    finally:
        done(case)


def test_a_project_config_name_created_in_the_working_folder_ends_the_session():
    case = make_case()
    try:
        name = str(case.work / 'opencode.json')
        _ended(case, [['create', 'work:opencode.json'], SLEEP], name)
        marker = json.loads((case.home / 'config-changed.json').read_text(encoding='utf-8'))
        assert marker['carried'] == [name], marker
    finally:
        done(case)


def test_a_file_under_xdg_config_ends_the_session():
    case = make_case()
    try:
        _ended(
            case,
            [['create', 'home:xdg/config/opencode/x.json'], SLEEP],
            'xdg/config/opencode/x.json',
        )
    finally:
        done(case)


def test_an_edit_of_run_json_ends_the_session_and_is_not_carried():
    case = make_case()
    try:
        record, _ = _ended(case, [['append', 'run'], SLEEP], None)
        names = record['config_changed']
        assert any(n.replace('\\', '/').endswith('/run.json') for n in names), names
        marker = json.loads((case.home / 'config-changed.json').read_text(encoding='utf-8'))
        assert marker['carried'] == [], marker
    finally:
        done(case)


def test_a_change_just_before_the_end_is_found_after_it():
    case = make_case()
    try:
        case.argv[-1] = json.dumps([['append', 'home:conf/opencode.jsonc']])
        proc, _ = run(case)
        assert proc.returncode == 66, (proc.returncode, proc.stderr)
        record = case.run_json()
        assert record['config_changed'] == ['conf/opencode.jsonc'], record
        assert (case.home / 'config-changed.json').is_file()
    finally:
        done(case)


def test_a_session_that_changes_nothing_ends_as_before():
    case = make_case(actions=[['create', 'work:notes.txt']])
    try:
        proc, _ = run(case)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        record = case.run_json()
        assert record['outcome'] == 'ended' and 'config_changed' not in record, record
        assert not (case.home / 'config-changed.json').exists()
    finally:
        done(case)


def test_the_check_watches_a_claude_code_home():
    case = make_case('claude-code')
    try:
        _ended(
            case,
            [['append', 'home:claude-config/settings.json'], SLEEP],
            'claude-config/settings.json',
        )
    finally:
        done(case)


# ---- refusals


def test_a_project_config_name_in_the_working_folder_is_refused_in_interactive_mode():
    if not WINDOWS:
        print('skip: interactive mode runs on Windows only')
        return
    case = make_case()
    try:
        (case.work / '.opencode' / 'plugins').mkdir(parents=True)
        proc, _ = run(case, INTERACTIVE_ARGS, mode='interactive')
        refused(case, proc, '.opencode')
        assert case.runs() == [] and not case.out.exists()
        proc, _ = run(case, OPENCODE_ARGS)
        assert proc.returncode == 0, proc.stderr
        assert case.run_json()['project_config'] == ['.opencode']
    finally:
        done(case)


def _preflight(case: Case, mode: str = 'headless') -> launcher.Plan:
    environ = case.env(**accounts(case))
    environ.pop('PYTHONPATH', None)
    return launcher.preflight(
        'opencode',
        str(case.home),
        str(case.work),
        str(case.policy),
        OPENCODE_ARGS if mode == 'headless' else INTERACTIVE_ARGS,
        environ,
        mode=mode,
    )


def test_a_system_opencode_folder_is_refused_in_every_mode():
    case = make_case()
    saved = OpenCode.system_config_dir
    try:
        system = case.base / 'system-opencode'
        OpenCode.system_config_dir = lambda self: system  # type: ignore[method-assign]
        plan = _preflight(case)
        assert norm(system) in [norm(p) for p in plan.protected], plan.protected
        system.mkdir()
        try:
            _preflight(case)
        except launcher.RefusalError as exc:
            assert str(system) in str(exc), str(exc)
        else:
            raise AssertionError('a system opencode folder was not refused')
    finally:
        OpenCode.system_config_dir = saved  # type: ignore[method-assign]
        done(case)


def test_a_judge_other_than_this_kits_is_refused():
    case = make_case()
    try:
        driver = harnesses.get('opencode')
        home = json.loads((case.home / 'home.json').read_text(encoding='utf-8'))
        launcher.check_cli_argv(home, driver)
        config = Path(home['shell_config'])
        data = json.loads(config.read_text(encoding='utf-8'))
        data['cli_argv'] = [sys.executable, '-I', '-c', 'print(1)']
        config.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
        try:
            launcher.check_cli_argv(home, driver)
        except launcher.RefusalError as exc:
            assert 'cli_argv' in str(exc), str(exc)
        else:
            raise AssertionError('another judge was not refused')
        if not WINDOWS:
            return
        rel = config.relative_to(case.home).as_posix()
        home[watch.RENDERED_KEY][rel] = watch.file_sha256(config)
        (case.home / 'home.json').write_text(json.dumps(home, indent=2) + '\n', encoding='utf-8')
        proc, _ = run(case, INTERACTIVE_ARGS, mode='interactive')
        refused(case, proc, 'cli_argv')
        assert case.runs() == []
    finally:
        done(case)


if __name__ == '__main__':
    run_module(globals(), 'the governance of a run')

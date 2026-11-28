#!/usr/bin/env python3
"""Checks of `kit run` on a daily home whose daily file names a ripgrep, with a fake harness.

The home's copy is `xdg/cache/opencode/bin/rg.exe` (`rg` off Windows). Contract under test, with
the fake harness of `ripgrep_fake_harness.py` named through `KIT_HARNESS_ARGV_OPENCODE`, a daily
file whose `test` is true, a key variable holding a made-up value, and, on Windows, the system's
`PATHEXT` faked to `.COM;.EXE;.BAT;.CMD` unless a case names another value:
- a run of a home that names a ripgrep records the copy in `home-hashes.json`, and lists in
  `run.json`'s `protected` the copy and the candidate paths (every path opencode's lookup tries
  before the copy), so a write tool's write of one is denied, but neither the `bin` folder nor
  `xdg/cache`; a home that names none and a test home list neither, and are not refused for an
  `rg.exe` on `PATH`;
- preflight refuses, with exit 64 and no run, a copy rewritten or removed, a copy whose record
  in `home.json` was rewritten with it, and an `rg.exe` that opencode would run before the copy:
  first on `PATH`, behind a relative, quoted or empty entry, in the working folder or the work
  tree top on Windows, as a `PATHEXT` variant the pinned value holds (and not one only kit's own
  environment holds), beside a copy the pinned value does not count, under an empty `PATHEXT`
  item, with a mode only `isexe` counts off Windows, and with the named bytes;
- it does not refuse what the lookup passes over (a folder named `rg.exe`, an `rg.exe` the pinned
  value does not count, an `rg` without an execute bit, the home's own `bin` first on `PATH`), and
  those runs end `ended`;
- an `rg.exe` created by the canary refuses the start with `refused-home-changed`, exit 65; one
  created in a candidate folder during the run, or after the second read and before the check's
  first read, a folder replaced by a file and a `chmod` end the run with `config-changed`, exit
  66, naming the path (relative to the home inside it);
- the copy rewritten before the session refuses the start with exit 65; rewritten or removed
  during the run it ends the run with exit 66, and one appearing in a home without it does too;
  a hand copy in a home that names none is refused as a difference from the render.

Stdlib-runnable: `python test_daily_ripgrep.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import launcher, verdict
from harness_kit.policy import load_policy_text
from kit_fixtures import SRC, run_module, write_event

WINDOWS = os.name == 'nt'
NAME = 'rg.exe' if WINDOWS else 'rg'
COPY = 'xdg/cache/opencode/bin/' + NAME
FAKE = Path(__file__).resolve().parent / 'ripgrep_fake_harness.py'
PINNED = '.COM;.EXE;.BAT;.CMD'
KEY_ENV = 'TEST_RIPGREP_RELAY_KEY'
KEY = 'made-up-relay-key-4c1d9e'
MODEL_ID = 'vendor/model-a'
ARGS = ['run', '--standalone', '--format', 'json', '--auto', '--model', 'relay/' + MODEL_ID, 'hi']
STAND_IN = b'stand-in for a ripgrep binary\x00' * 32
SLEEP = ['sleep', 30]
# `kit run` through this bootstrap: on Windows the system's PATHEXT is faked, and a list of paths
# can be created right before the session starts, after the second read.
BOOT = r"""
import json, sys
spec = json.loads(sys.argv.pop(1))
sys.path.insert(0, spec['src'])
from harness_kit import launcher
if launcher.WINDOWS and spec.get('pathext') is not None:
    real = launcher.windows_pins
    launcher.windows_pins = lambda: {**real(), 'PATHEXT': spec['pathext']}
plant = spec.get('plant') or []
if plant:
    start = launcher._Session.start.__func__
    def planted(cls, *args, **kwargs):
        for path in plant:
            open(path, 'wb').close()
        return start(cls, *args, **kwargs)
    launcher._Session.start = classmethod(planted)
from harness_kit.cli import main
sys.exit(main(sys.argv[1:]))
"""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _toml(value: str) -> str:
    return '"' + value.replace('\\', '\\\\') + '"'


def daily_text(port: int, tools: str) -> str:
    # The numbers below are an example.
    return f"""\
daily = 1

[relay]
listen_port = {port}
upstream_base = "http://127.0.0.1:1"
route = "/v1/chat/completions"
key_env = "{KEY_ENV}"
test = true
usage_include = true
default_model = "{MODEL_ID}"
upstream_timeout_s = 30

[relay.ceilings]
run_usd = 1.0
day_usd = 2.0
month_usd = 3.0

[[relay.model]]
id = "{MODEL_ID}"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 1.0
max_output_tokens = 100

[git]
name = "Ripgrep Test"
email = "ripgrep.test@example.invalid"
{tools}"""


def clean_path() -> list[str]:
    """git's folder when it holds no name starting with `rg`; nothing else of kit's `PATH`."""
    git = shutil.which('git')
    if not git:
        return []
    folder = os.path.dirname(git)
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return [] if any(n.lower().startswith('rg') for n in names) else [folder]


def norm(path: object) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def mentions(text: str, needle: object) -> bool:
    """Whether `text` names `needle`, compared as the system compares paths."""
    return str(needle) in text or os.path.normcase(str(needle)) in os.path.normcase(text)


class Case:
    """A state root, a test folder, a policy, a daily file (or none) and its home."""

    def __init__(self, named: bool = True, kind: str = 'daily') -> None:
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix='kit-rg-run-')))
        self.state = self.base / 'state'
        self.tests = self.base / 'tests'
        self.work = self.tests / 'work'
        self.work.mkdir(parents=True)
        self.out = self.base / 'fake-out.json'
        self.source = self.base / 'tools' / 'rg-source.bin'
        self.source.parent.mkdir()
        self.source.write_bytes(STAND_IN)
        self.sha = hashlib.sha256(STAND_IN).hexdigest()
        self.port = free_port()
        self.policy = self.base / 'policy.toml'
        roots = json.dumps(str(self.tests))
        self.policy.write_text(
            f'version = 1\n\n[launcher]\ntest_roots = [{roots}]\nforbidden_roots = []\n',
            encoding='utf-8',
        )
        self.home = self.base / 'home'
        self.bin = self.home / 'xdg' / 'cache' / 'opencode' / 'bin'
        if kind == 'test':
            args = ['--endpoint', 'http://127.0.0.1:1']
        else:
            tools = ''
            if named:
                tools = f'\n[tools]\nripgrep = {_toml(str(self.source))}\n'
                tools += f'ripgrep_sha256 = "{self.sha}"\n'
            self.daily = self.base / 'daily.toml'
            self.daily.write_text(daily_text(self.port, tools), encoding='utf-8')
            args = ['--daily', str(self.daily)]
        proc = self.kit('home', 'render', '--harness', 'opencode', '--dir', str(self.home), *args)
        assert proc.returncode == 0, proc.stderr

    def env(self, entries: list, steps: dict, **extra: str) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('KIT_', 'GIT_'))}
        env = {k: v for k, v in env.items() if not launcher.SECRET_NAME.search(k)}
        env = {k: v for k, v in env.items() if not k.upper().startswith(('CLAUDE', 'ANTHROPIC'))}
        for name in ('PYTHONIOENCODING', 'SESSION_WORKFLOW_GOVERNED_HOME', 'PATHEXT'):
            env = {k: v for k, v in env.items() if k.upper() != name}
        if WINDOWS:
            env['PATHEXT'] = PINNED
        env['PATH'] = os.pathsep.join([*(str(e) for e in entries), *clean_path()])
        env['PYTHONPATH'] = str(SRC)
        env['KIT_STATE_ROOT'] = str(self.state)
        argv = [sys.executable, str(FAKE), str(self.out), '2.2.5', json.dumps(steps)]
        env['KIT_HARNESS_ARGV_OPENCODE'] = json.dumps(argv)
        env[KEY_ENV] = KEY
        env.update(extra)
        return env

    def kit(self, *args: str, env: dict | None = None, boot: dict | None = None):
        spec = {'src': str(SRC), 'pathext': PINNED, **(boot or {})}
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, '-c', BOOT, json.dumps(spec), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env if env is not None else self.env([], {}),
            cwd=str(self.base),
            timeout=180,
        )

    def run(self, entries=(), steps=None, boot=None, workdir=None, args=ARGS, **extra):
        head = ['run', '--harness', 'opencode', '--home', str(self.home)]
        head += ['--workdir', str(workdir or self.work), '--policy', str(self.policy), '--']
        env = self.env(list(entries), steps or {}, **extra)
        return self.kit(*head, *args, env=env, boot=boot)

    def runs(self) -> list[Path]:
        folder = self.state / 'runs'
        return sorted(folder.glob('*/run.json')) if folder.is_dir() else []

    def run_dir(self) -> Path:
        found = self.runs()
        assert len(found) == 1, found
        return found[0].parent

    def run_json(self) -> dict:
        return json.loads((self.run_dir() / 'run.json').read_text(encoding='utf-8'))

    def folder(self, name: str) -> Path:
        path = self.base / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def plant(self, path: Path, data: bytes = b'planted\n', mode: int = 0o755) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if not WINDOWS:
            os.chmod(path, mode)
        return path

    def fresh(self) -> None:
        """Forget the runs and the session's output, so the next run is the only one."""
        shutil.rmtree(self.state / 'runs', ignore_errors=True)
        for suffix in ('', '.after'):
            Path(str(self.out) + suffix).unlink(missing_ok=True)

    def close(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)


def refused(case: Case, proc, *needles: object) -> str:
    assert proc.returncode == 64, (proc.returncode, proc.stderr)
    lines = proc.stderr.splitlines()
    assert len(lines) == 1, lines
    for needle in needles:
        assert mentions(lines[0], needle), (needle, lines)
    assert KEY not in proc.stderr
    assert not case.out.exists(), 'the harness was started'
    assert case.runs() == [], case.runs()
    return lines[0]


def ended(case: Case, proc) -> dict:
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    record = case.run_json()
    assert record['outcome'] == 'ended', record
    assert Path(str(case.out) + '.after').exists(), 'the session did not run to its end'
    return record


def changed(case: Case, proc, path: object) -> dict:
    assert proc.returncode == 66, (proc.returncode, proc.stderr)
    record = case.run_json()
    assert record['outcome'] == 'config-changed', record
    names = record['config_changed']
    assert any(mentions(n, path) and mentions(str(path), n) for n in names), (path, names)
    assert not Path(str(case.out) + '.after').exists(), 'the session ran to its end'
    return record


def refused_start(case: Case, proc, path: object) -> None:
    assert proc.returncode == 65, (proc.returncode, proc.stderr)
    assert case.run_json()['outcome'] == 'refused-home-changed', case.run_json()
    assert mentions(proc.stderr, path), proc.stderr
    assert not case.out.exists(), 'the session started'


# ---- a run of a named home


def test_a_named_home_records_its_copy_and_protects_the_candidates():
    case = Case()
    try:
        a = case.folder('a')
        record = ended(case, case.run([a]))
        hashes = json.loads((case.run_dir() / 'home-hashes.json').read_text(encoding='utf-8'))
        assert hashes[COPY] == case.sha, hashes
        protected = [norm(p) for p in record['protected']]
        assert norm(case.home / COPY) in protected, record['protected']
        assert norm(a / NAME) in protected, record['protected']
        if WINDOWS:
            assert norm(case.work / 'rg.exe') in protected, record['protected']
            assert norm(case.work / 'rg.exe.CMD') in protected, record['protected']
        for folder in (case.bin, case.home / 'xdg' / 'cache', case.home / 'xdg'):
            assert norm(folder) not in protected, (folder, record['protected'])
        policy = load_policy_text(
            'version = 1\n\n[[rule]]\nid = "allow-all"\neffect = "allow"\ngoverned = true\n'
            'kinds = ["file_write"]\nreason = "allowed"\n',
            windows=WINDOWS,
            sha256=record['policy_sha256'],
        )
        harness = {'name': 'opencode', 'version': '2.2.5'}
        for path, want in ((a / NAME, 'deny'), (case.bin / 'other.exe', 'allow')):
            event = write_event([str(path)], **{'harness': harness, 'act.cwd': str(case.work)})
            found = verdict.judge(event, policy, True, run=record, run_dir=str(case.run_dir()))
            assert found['verdict'] == want, (path, found)
    finally:
        case.close()


def test_a_home_that_names_none_and_a_test_home_take_an_rg_on_path():
    for kind in ('daily', 'test'):
        case = Case(named=False, kind=kind)
        try:
            a = case.folder('a')
            case.plant(a / NAME)
            record = ended(case, case.run([a]))
            protected = [norm(p) for p in record['protected']]
            assert norm(case.home / COPY) not in protected, (kind, record['protected'])
            assert norm(a / NAME) not in protected, (kind, record['protected'])
            hashes = json.loads((case.run_dir() / 'home-hashes.json').read_text(encoding='utf-8'))
            assert COPY not in hashes, (kind, hashes)
        finally:
            case.close()


# ---- the copy is the named one


def test_a_copy_rewritten_removed_or_rewritten_with_its_record_is_refused():
    case = Case()
    try:
        copy = case.home / COPY
        copy.write_bytes(STAND_IN + b'x')
        refused(case, case.run(), 'the home differs from its render at ' + COPY)
        copy.unlink()
        refused(case, case.run(), 'the home differs from its render at ' + COPY)
        other = STAND_IN + b'another binary'
        copy.write_bytes(other)
        home = json.loads((case.home / 'home.json').read_text(encoding='utf-8'))
        sha = hashlib.sha256(other).hexdigest()
        home['rendered_sha256'][COPY] = sha
        (case.home / 'home.json').write_text(json.dumps(home, indent=2) + '\n', encoding='utf-8')
        line = refused(case, case.run(), f"the home's {COPY} is not the ripgrep the daily file")
        assert sha in line and case.sha in line, line
    finally:
        case.close()


# ---- what opencode would run first


def test_an_rg_that_opencode_would_run_first_is_refused():
    case = Case()
    try:
        a = case.folder('a')
        planted = case.plant(a / NAME)
        needle = f'an {NAME} resolves at'
        line = refused(case, case.run([a]), needle, planted)
        assert "before the home's copy" in line, line
        planted.write_bytes(STAND_IN)
        refused(case, case.run([a]), needle, planted)
        planted.unlink()
        relative = case.plant(case.work / 'rel' / NAME)
        refused(case, case.run(['rel', a]), needle, relative)
        relative.unlink()
        quoted = case.plant(case.folder('quoted dir') / NAME)
        refused(case, case.run([f'"{quoted.parent}"']), needle, quoted)
        quoted.unlink()
        in_work = case.plant(case.work / NAME)
        refused(case, case.run(['', a]), needle, in_work)
        if WINDOWS:
            refused(case, case.run([a]), needle, in_work)
        in_work.unlink()
    finally:
        case.close()


def test_on_windows_the_work_tree_top_is_searched_too():
    if not WINDOWS:
        print('skip: which searches the current folder first on Windows only')
        return
    case = Case()
    try:
        repo = case.tests / 'repo'
        sub = repo / 'sub'
        sub.mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
        subprocess.run(['git', 'init', '-q', str(repo)], check=True, env=env)  # noqa: S603, S607
        planted = case.plant(repo / 'rg.exe')
        refused(case, case.run(workdir=sub), 'resolves at', planted)
    finally:
        case.close()


def test_on_windows_the_pinned_pathext_decides_what_counts():
    if not WINDOWS:
        print('skip: PATHEXT is read on Windows only')
        return
    case = Case()
    try:
        a = case.folder('a')
        cmd = case.plant(a / 'rg.exe.CMD')
        boot = {'pathext': '.CMD'}
        refused(case, case.run([a], boot=boot, PATHEXT='.XYZ'), 'resolves at', cmd)
        cmd.unlink()
        case.plant(a / 'rg.exe.XYZ')
        ended(case, case.run([a], boot=boot, PATHEXT='.XYZ'))
        case.fresh()
        beside = case.plant(case.bin / 'rg.exe.CMD')
        refused(case, case.run([case.folder('b')], boot=boot), 'resolves at', beside)
        beside.unlink()
        first = case.plant(a / 'rg.exe')
        refused(case, case.run([a], boot={'pathext': '.CMD;'}), 'resolves at', first)
        ended(case, case.run([a], boot=boot))
    finally:
        case.close()


def test_off_windows_isexes_mode_rule_decides_what_counts():
    if WINDOWS:
        print('skip: the mode rule is read off Windows only')
        return
    case = Case()
    try:
        a = case.folder('a')
        planted = case.plant(a / 'rg', mode=0o001)
        refused(case, case.run([a]), 'resolves at', planted)
        os.chmod(planted, 0o644)
        ended(case, case.run([a]))
    finally:
        case.close()


def test_what_the_lookup_passes_over_is_not_refused():
    case = Case()
    try:
        a = case.folder('a')
        (a / NAME).mkdir()
        ended(case, case.run([a]))
        case.fresh()
        ended(case, case.run([case.bin, a]))
    finally:
        case.close()


# ---- before and during the run


def test_an_rg_planted_by_the_canary_refuses_the_start():
    case = Case()
    try:
        a = case.folder('a')
        planted = (case.work if WINDOWS else a) / NAME
        steps = {'canary': [['create', str(planted)]]}
        refused_start(case, case.run([a], steps=steps), planted)
    finally:
        case.close()


def test_an_rg_created_in_a_candidate_folder_during_the_run_ends_it():
    case = Case()
    try:
        a = case.folder('a')
        steps = {'session': [['create', str(a / NAME)], SLEEP]}
        record = changed(case, case.run([a], steps=steps), a / NAME)
        marker = json.loads((case.home / 'config-changed.json').read_text(encoding='utf-8'))
        assert norm(a / NAME) in [norm(p) for p in marker['carried']], marker
        if WINDOWS:
            case.close()
            case = Case()
            beside = case.bin / 'rg.exe.CMD'
            steps = {'session': [['create', str(beside)], SLEEP]}
            proc = case.run([case.folder('b')], steps=steps, boot={'pathext': '.CMD'})
            record = changed(case, proc, COPY + '.CMD')
            assert COPY.lower() + '.cmd' in [n.lower() for n in record['config_changed']], record
    finally:
        case.close()


def test_an_rg_created_after_the_second_read_ends_the_run():
    case = Case()
    try:
        a = case.folder('a')
        steps = {'session': [SLEEP]}
        changed(case, case.run([a], steps=steps, boot={'plant': [str(a / NAME)]}), a / NAME)
    finally:
        case.close()


def test_a_passed_over_candidate_that_changes_ends_the_run():
    case = Case()
    try:
        a = case.folder('a')
        folder = a / NAME
        folder.mkdir()
        steps = {'session': [['rmdir', str(folder)], ['create', str(folder)], SLEEP]}
        changed(case, case.run([a], steps=steps), folder)
        if not WINDOWS:
            case.close()
            case = Case()
            b = case.folder('b')
            planted = case.plant(b / 'rg', mode=0o644)
            steps = {'session': [['chmod', str(planted), 0o755], SLEEP]}
            changed(case, case.run([b], steps=steps), planted)
    finally:
        case.close()


def test_the_copy_is_guarded_before_and_during_the_run():
    case = Case()
    try:
        copy = case.home / COPY
        steps = {'canary': [['append', str(copy)]]}
        refused_start(case, case.run(steps=steps), COPY)
    finally:
        case.close()
    for op in ('append', 'remove'):
        case = Case()
        try:
            steps = {'session': [[op, str(case.home / COPY)], SLEEP]}
            record = changed(case, case.run(steps=steps), COPY)
            assert COPY in record['config_changed'], record
        finally:
            case.close()
    case = Case(kind='test')
    try:
        steps = {'session': [['create', str(case.home / COPY)], SLEEP]}
        record = changed(case, case.run(steps=steps), COPY)
        assert COPY in record['config_changed'], record
    finally:
        case.close()


def test_a_hand_copy_in_a_home_that_names_none_is_refused():
    case = Case(named=False)
    try:
        case.plant(case.home / COPY)
        refused(case, case.run(), f'the home differs from its render at {COPY}; render the home')
    finally:
        case.close()


if __name__ == '__main__':
    run_module(globals(), 'kit run on a home that names a ripgrep')

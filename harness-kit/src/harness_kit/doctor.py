"""The heartbeat of a launched run, and `kit doctor`.

While `kit run` holds a session, a thread of the launcher writes
`runs/<id>/heartbeat.json` (`run_id`, `pid`, `seq`, `utc`) every 2 seconds by
atomic replace. A run that is still `minted` or `launched` and whose last sign
of life (its heartbeat, else its start) is older than 10 seconds is `stale`:
the launcher is gone without recording an end.

`kit doctor [--json]` reports, per harness, what the kit tested per objective
and the harness's known losses, from the contract files under `contracts/`.
A harness whose version differs from its contract reads `unknown` on every
objective but `prevention`; one whose binary is absent reads `unknown` on all
of them. Per harness, after the objectives, one line gives the interactive
mode's state from the contract's `[modes.interactive]` entry, read the same
way (`unknown` when the binary is absent or its version differs). It also lists
the runs under the state root with their status (`running`, `stale`, `ended`,
`refused`, `config-changed`, `interrupted`) and the sessions judged without a
launch, whose guarantees are unknown.

`kit doctor --live --live-root DIR` also runs the presence canary per harness
whose binary is found, in a scratch home under DIR (which must lie under a
`test_roots` entry of `KIT_POLICY`). A passed canary sets `guard_loaded`,
`refusal_in_turn` and `allow_passes` to `degraded` where the contract holds a
loss for that objective and to `tested` where it holds none; a failed one sets
them to `absent`.

When `KIT_POLICY` names a readable version 2, 3 or 4 policy with a
`<policy>.packs.json` beside it whose `policy_sha256` is the policy's, the report
gains a section `rules`: per rule with a checker, its pack, `governed`, a state
per harness from the contract's `[rules]` table (`unknown` when the binary is
absent or its version differs) and the pack's declared preventing layer. A policy
that does not load gives the one line `policy unreadable: <reason>` (a file that
is TOML with `version = 1` gives no section), a sidecar of another policy gives
`sidecar stale`. With a version 1 policy, with no `KIT_POLICY` and with a
version 2, 3 or 4 policy that has no sidecar the report has no such section. The
section reads files only: it runs no checker and starts no program.

When `KIT_POLICY` names a readable policy with at least one recording checker (a
`records` key, version 3 or 4), the report also gains a section `notes`: per
recording checker, its kinds and, per harness and kind, a state from the
contract's `[notes]` table (`unknown` when the binary is absent, its version
differs or the contract has no entry for the kind). It stands after `rules` and
reads files only, as `rules` does. Any other policy gives no such section.

`kit doctor --home DIR` adds one line after the harness entries, and in JSON the key
`home` (`dir`, and `ripgrep` with `state`, `path` and `shadowed_by`): whether the home in
DIR is a daily opencode home whose daily file names a ripgrep, the state of its copy
`xdg/cache/opencode/bin/rg.exe` (`rg` off Windows) against the render's record, and which
file opencode's lookup would run first. The lookup is the opencode driver's walk over kit's
own `PATH`, which the session inherits, with the home's `bin` folder appended and, on
Windows, the `PATHEXT` the system holds (`launcher.windows_pins`, the value the session
gets); with no working folder it reads absolute entries only. It reads files and the
registry and starts no program; it exits 0 in every case.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import tomllib

from harness_kit import canary, harnesses, packs, state, stubmodel, watch
from harness_kit.policy import Policy, PolicyError, load_policy

CONTRACTS_DIR = Path(__file__).resolve().parent / 'contracts'
CONTRACT_FILES = {'claude-code': 'claude_code.toml', 'opencode': 'opencode.toml'}
OBJECTIVES = (
    'guard_loaded',
    'refusal_in_turn',
    'allow_passes',
    'run_identity',
    'launcher_checks',
    'hung_guard',
    'heartbeat',
    'prevention',
)
STATES = ('tested', 'degraded', 'absent', 'unknown')
MODES = ('interactive',)
MODE_LABEL = 'mode'
# Run outcomes that end a run, and the status each reads as.
ENDED_STATUS = {
    'ended': 'ended',
    'refused-canary': 'refused',
    'refused-home-changed': 'refused',
    'refused-relay': 'refused',
    'config-changed': 'config-changed',
    'interrupted': 'interrupted',
}
LIVE_OBJECTIVES = ('guard_loaded', 'refusal_in_turn', 'allow_passes')
PREVENTION = 'prevention'

HEARTBEAT_JSON = 'heartbeat.json'
HEARTBEAT_S = 2
STALE_S = 10
READ_DEADLINE_S = 1.0
UTC_FORMS = ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S.%fZ')
NOT_LAUNCHED_TEXT = 'not launched, guarantees unknown'
RULES_KEY = 'rules'
NOTES_KEY = 'notes'
HOME_KEY = 'home'
RIPGREP_LINE = 'ripgrep: '
UNREADABLE_TEXT = 'policy unreadable: '
STALE_TEXT = 'sidecar stale'
DECLARED_TEXT = 'declared by the pack, not checked by the kit'
NO_PREVENTION_TEXT = 'none declared'

EXIT_REFUSED = 64


class DoctorRefusalError(Exception):
    """A doctor request that cannot run; the message is one ASCII line."""


def _ascii(text: object) -> str:
    return str(text).encode('ascii', 'backslashreplace').decode('ascii').replace('\n', ' ')


def _utc_text(now: datetime) -> str:
    return now.strftime(UTC_FORMS[0])


# ---- the heartbeat


class Heartbeat:
    """A daemon thread that rewrites `heartbeat.json` every `interval_s` until stopped."""

    def __init__(self, run_dir: Path, run_id: str, interval_s: float = HEARTBEAT_S) -> None:
        self.path = Path(run_dir) / HEARTBEAT_JSON
        self.run_id = run_id
        self.interval_s = interval_s
        self.seq = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name='kit-heartbeat', daemon=True)

    def _beat(self) -> None:
        self.seq += 1
        record = {
            'run_id': self.run_id,
            'pid': os.getpid(),
            'seq': self.seq,
            'utc': _utc_text(datetime.now(timezone.utc)),
        }
        try:
            state.write_json_atomic(self.path, record)
        except OSError:
            pass  # a missed beat only makes the run read stale sooner

    def _loop(self) -> None:
        while True:
            self._beat()
            if self._stop.wait(self.interval_s):
                return

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()


# ---- reading the state root


def _read_json(path: Path) -> dict | None:
    """A JSON object from a file another process may be replacing; None when unreadable."""
    end = time.monotonic() + READ_DEADLINE_S
    while True:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return None
        except PermissionError:
            if time.monotonic() >= end:
                return None
            time.sleep(0.02)
        except (OSError, ValueError):
            return None


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    for form in UTC_FORMS:
        try:
            return datetime.strptime(value, form).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def run_status(run_dir: Path, now: datetime | None = None) -> str:
    """The status an ended run's outcome reads as (`ended`, `refused`, `config-changed`,
    `interrupted`), or, for a run still held by a launcher, `running` or `stale`."""
    now = datetime.now(timezone.utc) if now is None else now
    record = _read_json(Path(run_dir) / 'run.json') or {}
    outcome = record.get('outcome')
    if isinstance(outcome, str) and outcome in ENDED_STATUS:
        return ENDED_STATUS[outcome]
    beat = _read_json(Path(run_dir) / HEARTBEAT_JSON) or {}
    last = _parse_utc(beat.get('utc')) or _parse_utc(record.get('started_utc'))
    if last is None:
        return 'stale'
    return 'stale' if (now - last).total_seconds() > STALE_S else 'running'


def list_runs(root: Path) -> list[dict]:
    out = []
    for run_json in sorted((Path(root) / 'runs').glob('*/run.json')):
        record = _read_json(run_json) or {}
        out.append(
            {
                'run_id': run_json.parent.name,
                'harness': record.get('harness'),
                'status': run_status(run_json.parent),
            }
        )
    return out


def list_not_launched(root: Path) -> list[dict]:
    """One entry per session judged without a launch; an invalid event names no session."""
    counts: dict[tuple, int] = {}
    for journal in sorted((Path(root) / 'not-launched').glob(f'*/{state.JOURNAL}')):
        if journal.parent.name == 'invalid':
            continue
        try:
            lines = journal.read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                key = (str(entry.get('session_id')), str(entry.get('harness')))
                counts[key] = counts.get(key, 0) + 1
    return [
        {'session': session, 'harness': harness, 'events': events, 'guarantees': 'unknown'}
        for (session, harness), events in sorted(counts.items())
    ]


# ---- contracts and the per-harness report


def load_contract(name: str) -> dict:
    """The contract of one harness, parsed from its TOML file."""
    path = CONTRACTS_DIR / CONTRACT_FILES[name]
    return tomllib.loads(path.read_text(encoding='utf-8'))


def binary_present(argv: list[str]) -> bool:
    """True when the driver's argv names a program that exists."""
    if not argv:
        return False
    return os.path.isfile(argv[0]) or shutil.which(argv[0]) is not None


def harness_report(driver: harnesses.Driver, env: Mapping[str, str], live: dict | None) -> dict:
    """One harness's entry: version found, contract version, objectives, losses."""
    contract = load_contract(driver.name)
    expected = contract['harness']['version']
    present = binary_present(driver.binary_argv(env))
    found = driver.version(env) if present else None
    losses = list(contract.get('loss', []))
    rows = {row['id']: row for row in contract.get('objective', [])}
    objectives = {}
    for name in OBJECTIVES:
        row = rows.get(name, {'state': 'unknown', 'evidence': ''})
        entry = {'state': row['state'], 'source': 'contract', 'evidence': row['evidence']}
        if not present:
            entry.update(state='unknown', evidence='the harness binary was not found')
        elif found != expected and name != PREVENTION:
            shown = found or 'none read'
            entry.update(
                state='unknown',
                evidence=f'version found {shown} is not the contract version {expected}',
            )
        objectives[name] = entry
    modes = {}
    for name in MODES:
        row = (contract.get('modes') or {}).get(name)
        if not isinstance(row, dict):
            row = {'state': 'unknown', 'evidence': ''}
        entry = {'state': row['state'], 'source': 'contract', 'evidence': row['evidence']}
        if not present:
            entry.update(state='unknown', evidence='the harness binary was not found')
        elif found != expected:
            shown = found or 'none read'
            entry.update(
                state='unknown',
                evidence=f'version found {shown} is not the contract version {expected}',
            )
        modes[name] = entry
    if present and live is not None:
        run = live.get('run_id') or 'none'
        for name in LIVE_OBJECTIVES:
            if live.get('passed') is True:
                lost = any(loss.get('objective') == name for loss in losses)
                value = 'degraded' if lost else 'tested'
                evidence = f'live canary passed in run {run}'
            else:
                value = 'absent'
                evidence = f'live canary failed in run {run}: {_ascii(live.get("reason"))}'
            objectives[name] = {'state': value, 'source': 'live', 'evidence': evidence}
    return {
        'version_found': found,
        'contract_version': expected,
        'objectives': objectives,
        'modes': modes,
        'losses': losses,
    }


# ---- rules from a built policy


def _toml_version(path: Path) -> object:
    """The top-level `version` of a file that parses as TOML, else None."""
    try:
        data = tomllib.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data.get('version')


def _is_version(value: object, number: int) -> bool:
    return type(value) is int and value == number


def _read_sidecar(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _sidecar_packs(data: dict) -> list[dict]:
    items = data.get('packs')
    return [p for p in items if isinstance(p, dict)] if isinstance(items, list) else []


def _rule_state(contract: dict, found: object, rule_id: str) -> tuple[str, str]:
    """A harness's state for a rule and its evidence text, as the objectives follow."""
    if found is None or found != contract['harness']['version']:
        return 'unknown', ''
    entry = (contract.get(RULES_KEY) or {}).get(rule_id)
    if not isinstance(entry, dict) or entry.get('state') != 'tested':
        return 'unknown', ''
    return 'tested', _ascii(entry.get('evidence', ''))


def _rule_rows(policy: Policy, sidecar: dict, harness_rows: Mapping[str, dict]) -> list[dict]:
    pack_list = _sidecar_packs(sidecar)
    contracts = {name: load_contract(name) for name in harness_rows}
    rows = []
    for rule in policy.rules:
        if rule.check is None:
            continue
        owner = next((p for p in pack_list if rule.id in (p.get('rules') or [])), None)
        prevention = NO_PREVENTION_TEXT
        for pack in pack_list:
            declared = pack.get('prevention')
            if isinstance(declared, dict) and declared.get('rule') == rule.id:
                prevention = f'{_ascii(declared.get("layer"))} ({DECLARED_TEXT})'
        states, evidence = {}, {}
        for name, entry in harness_rows.items():
            states[name], evidence[name] = _rule_state(
                contracts[name], entry['version_found'], rule.id
            )
        rows.append(
            {
                'id': rule.id,
                'governed': rule.governed,
                'pack': _ascii(owner.get('name')) if owner is not None else None,
                'states': states,
                'evidence': evidence,
                'prevention': prevention,
            }
        )
    return rows


def rules_section(environ: Mapping[str, str], harness_rows: Mapping[str, dict]):
    """The `rules` value for the report: a list, a one-line string, or None for no section.

    Reads the policy and its sidecar as files; nothing is executed.
    """
    policy_file = environ.get('KIT_POLICY')
    if not policy_file:
        return None
    path = Path(os.path.abspath(policy_file))
    try:
        policy = load_policy(path)
    except PolicyError as exc:
        if _is_version(_toml_version(path), 1):
            return None
        return UNREADABLE_TEXT + _ascii(exc)
    version = _toml_version(path)
    # A version 4 policy reads as a version 3 one: its `[permissions]` section names no rule.
    if not any(_is_version(version, n) for n in (2, 3, 4)):
        return None
    sidecar_file = packs.sidecar_path(path)
    if not sidecar_file.exists():
        return None
    sidecar = _read_sidecar(sidecar_file)
    if sidecar.get('policy_sha256') != policy.sha256:
        return STALE_TEXT
    return _rule_rows(policy, sidecar, harness_rows)


# ---- notes from a policy that records


def _note_state(contract: dict, found: object, kind: str) -> tuple[str, str]:
    """A harness's state for a recorded kind and its evidence text, as the rules follow."""
    if found is None or found != contract['harness']['version']:
        return 'unknown', ''
    entry = (contract.get(NOTES_KEY) or {}).get(kind)
    if not isinstance(entry, dict):
        return 'unknown', ''
    if entry.get('state') == 'tested':
        return 'tested', _ascii(entry.get('evidence', ''))
    if entry.get('state') == 'absent':
        return 'absent', ''
    return 'unknown', ''


def notes_section(environ: Mapping[str, str], harness_rows: Mapping[str, dict]) -> list | None:
    """The `notes` value for the report: a row per recording checker, or None for no section."""
    policy_file = environ.get('KIT_POLICY')
    if not policy_file:
        return None
    try:
        policy = load_policy(Path(os.path.abspath(policy_file)))
    except PolicyError:
        return None
    recording = [c for c in policy.checkers if c.records]
    if not recording:
        return None
    contracts = {name: load_contract(name) for name in harness_rows}
    rows = []
    for checker in recording:
        states: dict[str, dict] = {}
        evidence: dict[str, dict] = {}
        for name, entry in harness_rows.items():
            states[name], evidence[name] = {}, {}
            for kind in checker.records:
                value, proof = _note_state(contracts[name], entry['version_found'], kind)
                states[name][kind], evidence[name][kind] = value, proof
        rows.append(
            {
                'checker': _ascii(checker.id),
                'records': list(checker.records),
                'states': states,
                'evidence': evidence,
            }
        )
    return rows


# ---- the live canary


def _within(path: Path | str, base: Path | str) -> bool:
    p = os.path.normcase(os.path.realpath(str(path)))
    b = os.path.normcase(os.path.realpath(str(base)))
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


def check_live_root(live_root: str, environ: Mapping[str, str]) -> tuple[Path, Path]:
    """The resolved live root and the policy path; refused unless under a test root."""
    policy_file = environ.get('KIT_POLICY')
    if not policy_file:
        raise DoctorRefusalError('--live needs KIT_POLICY, whose test_roots hold the live root')
    policy_path = Path(os.path.abspath(policy_file))
    try:
        policy = load_policy(policy_path)
    except PolicyError as exc:
        raise DoctorRefusalError(f'policy unreadable: {_ascii(exc)}') from None
    resolved = Path(os.path.realpath(live_root))
    roots = [r for r in policy.launcher.get('test_roots', []) if r]
    if not any(_within(resolved, root) for root in roots):
        raise DoctorRefusalError(f'live root {_ascii(resolved)} is outside the test roots')
    reason = state.refusal(str(resolved), dict(environ), resolve=os.path.realpath)
    if reason is not None:
        raise DoctorRefusalError(f'live root {_ascii(resolved)} refused: {reason}')
    if resolved.exists() and not resolved.is_dir():
        raise DoctorRefusalError(f'live root {_ascii(resolved)} is not a folder')
    return resolved, policy_path


def live_canary(
    driver: harnesses.Driver,
    binary: list[str],
    live_root: Path,
    policy_path: Path,
    environ: Mapping[str, str],
) -> dict:
    """Render a scratch home under the live root and run the canary there; its record."""
    from harness_kit import launcher

    folder = Path(tempfile.mkdtemp(prefix=f'{driver.name}-', dir=str(live_root)))
    stub = stubmodel.Stub(folder / 'session-stub.ndjson', [])
    server = threading.Thread(target=stub.serve_forever, daemon=True)
    server.start()
    run_id = None
    try:
        home = driver.render_home(folder / 'home', f'http://127.0.0.1:{stub.port}')
        root = folder / 'state'
        run_id, run_dir = state.mint_run(root, driver.name)
        for name in ('tmp', 'gh-config'):
            (run_dir / name).mkdir()
        (run_dir / 'gitconfig-empty').write_bytes(b'')
        work = folder / 'work'
        work.mkdir()

        def make_env(copy: dict, place: Path) -> dict:
            env, _ = launcher.build_env(
                driver,
                copy,
                dict(environ),
                run_dir=run_dir,
                run_id=run_id,
                root=root,
                policy_path=policy_path,
                workdir=place,
            )
            return env

        record = canary.run_canary(
            driver,
            home,
            binary,
            run_dir=run_dir,
            workdir=work,
            project_config=[],
            make_env=make_env,
        )
        state.write_json_atomic(run_dir / state.CANARY_DIR / canary.CANARY_JSON, record)
        run_json = run_dir / 'run.json'
        run = _read_json(run_json) or {}
        run.update(outcome='ended' if record['passed'] else 'refused-canary')
        state.write_json_atomic(run_json, run)
    except Exception as exc:  # the live report reads a failure as absent, never as tested
        record = {'passed': False, 'reason': f'live canary not run: {_ascii(exc)}'}
    finally:
        stub.shutdown()
        stub.server_close()
    record['run_id'] = run_id
    return record


# ---- the ripgrep of a home


def _read_home(folder: Path) -> dict | str:
    """The home's `home.json` when it is a rendered home, else why it is unreadable."""
    path = folder / watch.HOME_JSON
    try:
        home = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return f'{_ascii(path)} is absent'
    except OSError as exc:
        return f'{_ascii(path)} is not readable: {type(exc).__name__}'
    except ValueError:
        return f'{_ascii(path)} is not JSON'
    rendered = isinstance(home, dict) and home.get('kit_home') == 1
    rendered = rendered and all(isinstance(home.get(k), str) for k in harnesses.HOME_KEYS[1:])
    return home if rendered else f'{_ascii(path)} is not a rendered home'


def _on_disk(path: Path) -> str | None:
    """The SHA-256 of a regular file, `unreadable` when it cannot be read, None when it is not
    a file."""
    if not path.is_file():
        return None
    try:
        return watch.file_sha256(path)
    except OSError:
        return 'unreadable'


def _walk(driver, folder: Path, environ: Mapping[str, str]):
    """The driver's ripgrep walk with kit's own `PATH`, the home's `bin` folder and, on Windows,
    the system's `PATHEXT`; no working folder. OSError when the system values are unreadable."""
    env = dict(environ)
    if os.name == 'nt':
        from harness_kit import launcher

        pathext = launcher.windows_pins()['PATHEXT']
        env = {k: v for k, v in env.items() if k.upper() != 'PATHEXT'}
        env['PATHEXT'] = pathext
    bin_dir = os.path.normpath(str(folder / Path(driver.ripgrep_copy).parent))
    return driver.ripgrep_walk(env, bin_dir, None)


def _ripgrep(folder: Path, environ: Mapping[str, str]) -> tuple[str, str | None, str | None, str]:
    """(state, path, shadowed_by, text) of the home in `folder`."""
    home = _read_home(folder)
    if isinstance(home, str):
        return 'home-unreadable', None, None, f'home unreadable: {home}'
    if home['harness'] != 'opencode' or harnesses.home_kind(home) != harnesses.DAILY_HOME:
        return 'not-daily', None, None, 'not a daily opencode home'
    driver = harnesses.get('opencode')
    rel = driver.ripgrep_copy
    copy = folder / rel
    name = Path(rel).name
    record = home.get(watch.RENDERED_KEY)
    recorded = record.get(rel) if isinstance(record, dict) else None
    settings = home.get('daily_settings')
    tools = settings.get('tools') if isinstance(settings, dict) else None
    named = tools.get('ripgrep_sha256') if isinstance(tools, dict) else None
    found = _on_disk(copy)
    if not isinstance(named, str):
        head = 'not named in the daily file; '
        if found is not None and recorded != found:
            return 'not-named-differs', str(copy), None, f'{head}{rel} differs from its render'
        try:
            walk = _walk(driver, folder, environ)
        except OSError as exc:
            return 'system-unreadable', None, None, _system_text(exc)
        if walk.found is None:
            return (
                'not-named-fails',
                None,
                None,
                f"{head}opencode's grep and glob fail in this home",
            )
        return 'not-named-runs', walk.found, None, f'{head}{_ascii(walk.found)} runs, unguarded'
    if found is None:
        status, copy_text = 'named-absent', 'is absent'
    elif found == recorded == named:
        status, copy_text = 'named-matches', 'matches its render'
    else:
        status, copy_text = 'named-differs', 'differs from its render'
    try:
        walk = _walk(driver, folder, environ)
    except OSError as exc:
        return 'system-unreadable', None, None, _system_text(exc)
    if walk.found is None or watch.norm(walk.found) == watch.norm(copy):
        return status, str(copy), None, f'named, {rel} {copy_text}, no {name} earlier on PATH'
    text = f'named, {rel} {copy_text}, shadowed by {_ascii(walk.found)}'
    return status, str(copy), walk.found, text


def _system_text(exc: OSError) -> str:
    return f'the system values could not be read: {_ascii(exc)}'


def home_section(home_dir: str, environ: Mapping[str, str]) -> tuple[dict, str]:
    """The report's `home` value and its text line for the home in `home_dir`."""
    folder = Path(os.path.abspath(home_dir))
    status, path, shadow, text = _ripgrep(folder, environ)
    value = {'state': status, 'path': path, 'shadowed_by': shadow}
    return {'dir': str(folder), 'ripgrep': value}, RIPGREP_LINE + text


def _with_home(report: dict, value: dict) -> dict:
    """The report with `home` after the runs and the sessions not launched, before `rules`."""
    out = {k: v for k, v in report.items() if k not in (RULES_KEY, NOTES_KEY)}
    out[HOME_KEY] = value
    out.update({k: v for k, v in report.items() if k in (RULES_KEY, NOTES_KEY)})
    return out


# ---- the report


def build_report(environ: Mapping[str, str], live_root: str | None = None) -> dict:
    """The doctor report; raise DoctorRefusalError for a refused root or live root."""
    try:
        root = state.state_root(dict(environ))
    except state.StateRootError as exc:
        raise DoctorRefusalError(_ascii(exc)) from None
    live: dict[str, dict] = {}
    if live_root is not None:
        resolved, policy_path = check_live_root(live_root, environ)
        resolved.mkdir(parents=True, exist_ok=True)
        for name in harnesses.names():
            driver = harnesses.get(name)
            binary = driver.binary_argv(environ)
            if binary_present(binary):
                live[name] = live_canary(driver, binary, resolved, policy_path, environ)
    report_harnesses = {
        name: harness_report(harnesses.get(name), environ, live.get(name))
        for name in harnesses.names()
    }
    report = {
        'kit_doctor': 1,
        'harnesses': report_harnesses,
        'runs': list_runs(root),
        'not_launched': list_not_launched(root),
    }
    rules = rules_section(environ, report_harnesses)
    if rules is not None:
        report[RULES_KEY] = rules
    notes = notes_section(environ, report_harnesses)
    if notes is not None:
        report[NOTES_KEY] = notes
    return report


def _rules_lines(rules: object) -> list[str]:
    if isinstance(rules, str):
        return [f'rules: {rules}']
    lines = ['rules:']
    for row in rules:  # type: ignore[attr-defined]
        pack = row['pack'] if row['pack'] is not None else '-'
        lines.append(f'  {row["id"]} governed {str(row["governed"]).lower()} pack {pack}')
        for name, value in row['states'].items():
            evidence = f' ({row["evidence"][name]})' if row['evidence'][name] else ''
            lines.append(f'    {name} {value}{evidence}')
        lines.append(f'    prevention: {row["prevention"]}')
    if not rules:
        lines.append('  (none)')
    return lines


def _notes_lines(rows: list[dict]) -> list[str]:
    lines = ['notes:']
    for row in rows:
        lines.append(f'  {row["checker"]} records {", ".join(row["records"])}')
        for name, kinds in row['states'].items():
            for kind in row['records']:
                proof = row['evidence'][name][kind]
                suffix = f' ({proof})' if kinds[kind] == 'tested' else ''
                lines.append(f'    {name} {kind} {kinds[kind]}{suffix}')
    return lines


def render_text(report: dict, home_line: str | None = None) -> str:
    """The text report; `home_line`, the line of `--home`, follows the harness entries."""
    lines = ['kit doctor']
    for name, entry in report['harnesses'].items():
        found = entry['version_found'] or 'not found'
        lines.append(f'{name}: version found {found}, contract {entry["contract_version"]}')
        for objective, row in entry['objectives'].items():
            lines.append(f'  {objective:<16} {row["state"]:<9} ({row["source"]}) {row["evidence"]}')
        for mode, row in entry.get('modes', {}).items():
            label = f'{MODE_LABEL} {mode}'
            lines.append(f'  {label:<16} {row["state"]:<9} ({row["source"]}) {row["evidence"]}')
        for loss in entry['losses']:
            lines.append(
                f'  loss {loss["id"]} [{loss["objective"]}, {loss["mark"]}]: {loss["text"]}'
            )
    if home_line is not None:
        lines.append(home_line)
    if RULES_KEY in report:
        lines.extend(_rules_lines(report[RULES_KEY]))
    if NOTES_KEY in report:
        lines.extend(_notes_lines(report[NOTES_KEY]))
    lines.append('runs:')
    for run in report['runs'] or [{'run_id': '(none)', 'harness': '', 'status': ''}]:
        lines.append(f'  {run["run_id"]} {run["harness"] or ""} {run["status"]}'.rstrip())
    lines.append('not launched:')
    for entry in report['not_launched']:
        lines.append(
            f'  session {entry["session"]} ({entry["harness"]}, events {entry["events"]}): '
            + NOT_LAUNCHED_TEXT
        )
    if not report['not_launched']:
        lines.append('  (none)')
    return '\n'.join(_ascii(line) for line in lines) + '\n'


def main(as_json: bool, live: bool, live_root: str | None, home: str | None = None) -> int:
    """`kit doctor`; a refused state root or live root exits 64. With `home`, the report gains
    the line and the key of `home_section`."""
    try:
        if live != (live_root is not None):
            raise DoctorRefusalError('--live and --live-root DIR go together')
        report = build_report(os.environ, live_root if live else None)
    except DoctorRefusalError as exc:
        sys.stderr.write(f'kit: doctor refused: {exc}\n')
        sys.stderr.flush()
        return EXIT_REFUSED
    line = None
    if home is not None:
        value, line = home_section(home, os.environ)
        report = _with_home(report, value)
    if as_json:
        sys.stdout.write(json.dumps(report, ensure_ascii=True) + '\n')
    else:
        sys.stdout.write(render_text(report, line))
    sys.stdout.flush()
    return 0

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
of them. It also lists the runs under the state root with their status
(`running`, `stale`, `ended`, `refused`) and the sessions judged without a
launch, whose guarantees are unknown.

`kit doctor --live --live-root DIR` also runs the presence canary per harness
whose binary is found, in a scratch home under DIR (which must lie under a
`test_roots` entry of `KIT_POLICY`). A passed canary sets `guard_loaded`,
`refusal_in_turn` and `allow_passes` to `degraded` where the contract holds a
loss for that objective and to `tested` where it holds none; a failed one sets
them to `absent`.
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

from harness_kit import canary, harnesses, state, stubmodel
from harness_kit.policy import PolicyError, load_policy

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
LIVE_OBJECTIVES = ('guard_loaded', 'refusal_in_turn', 'allow_passes')
PREVENTION = 'prevention'

HEARTBEAT_JSON = 'heartbeat.json'
HEARTBEAT_S = 2
STALE_S = 10
READ_DEADLINE_S = 1.0
UTC_FORMS = ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S.%fZ')
NOT_LAUNCHED_TEXT = 'not launched, guarantees unknown'

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
    """`ended`, `refused`, or, for a run still held by a launcher, `running` or `stale`."""
    now = datetime.now(timezone.utc) if now is None else now
    record = _read_json(Path(run_dir) / 'run.json') or {}
    outcome = record.get('outcome')
    if outcome == 'ended':
        return 'ended'
    if outcome == 'refused-canary':
        return 'refused'
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
        'losses': losses,
    }


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
    return {
        'kit_doctor': 1,
        'harnesses': report_harnesses,
        'runs': list_runs(root),
        'not_launched': list_not_launched(root),
    }


def render_text(report: dict) -> str:
    lines = ['kit doctor']
    for name, entry in report['harnesses'].items():
        found = entry['version_found'] or 'not found'
        lines.append(f'{name}: version found {found}, contract {entry["contract_version"]}')
        for objective, row in entry['objectives'].items():
            lines.append(f'  {objective:<16} {row["state"]:<9} ({row["source"]}) {row["evidence"]}')
        for loss in entry['losses']:
            lines.append(
                f'  loss {loss["id"]} [{loss["objective"]}, {loss["mark"]}]: {loss["text"]}'
            )
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


def main(as_json: bool, live: bool, live_root: str | None) -> int:
    """`kit doctor`; a refused state root or live root exits 64."""
    try:
        if live != (live_root is not None):
            raise DoctorRefusalError('--live and --live-root DIR go together')
        report = build_report(os.environ, live_root if live else None)
    except DoctorRefusalError as exc:
        sys.stderr.write(f'kit: doctor refused: {exc}\n')
        sys.stderr.flush()
        return EXIT_REFUSED
    if as_json:
        sys.stdout.write(json.dumps(report, ensure_ascii=True) + '\n')
    else:
        sys.stdout.write(render_text(report))
    sys.stdout.flush()
    return 0

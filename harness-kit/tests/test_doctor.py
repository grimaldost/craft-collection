#!/usr/bin/env python3
"""Checks of the heartbeat, `kit doctor` and the contract files.

Contract under test, with the fake harness of `canary_fake_harness.py`:
- each contract parses, holds the closed objective list once, states from the
  closed vocabulary, `prevention` `absent` and every other objective `unknown`,
  and every loss row this slice requires, each with a plain evidence sentence
  naming the harness version and a date;
- `kit run` writes `runs/<id>/heartbeat.json` (`run_id`, `pid`, `seq`, `utc`)
  every 2 seconds while the session runs; the run reads `running`, and
  `stale` once the launcher is killed and its heartbeat is older than 10 s;
- `kit doctor` takes states from the contract when the version found is the
  contract's, reports every objective `unknown` when it differs (`prevention`
  stays `absent`) and every objective `unknown`, `prevention` included, when
  the binary is absent;
- a not-launched session is listed with `guarantees` `unknown`, and the text
  form says "not launched, guarantees unknown";
- `kit doctor --live` runs the canary per harness found: a good guard gives
  `degraded` where a loss row names the objective and `tested` where none
  does, a broken one `absent`, a missing binary `unknown`; a live root outside
  the policy's test roots exits 64;
- no output holds a percent sign or the words percent or score.

Stdlib-runnable: `python test_doctor.py`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import doctor
from kit_fixtures import event, run_module
from test_canary import FAKE, PINNED, SESSION_ARGS, Case, base_env, kit, scratch

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
MARKS = ('measured', 'read', 'inferred')
REQUIRED_LOSSES = {
    'claude-code': {
        'settings-malformed-silent': 'guard_loaded',
        'python-c-settings-write': 'prevention',
        'sibling-updatedinput-rewrite': 'prevention',
        'shell-prefix-unjudged': 'prevention',
        'hook-failure-invisible-in-print-mode': 'refusal_in_turn',
        'no-origin-field': 'run_identity',
        'no-parent-in-payload': 'run_identity',
        'settings-unreadable-silent': 'guard_loaded',
    },
    'opencode': {
        'plugin-load-failure-silent': 'guard_loaded',
        'config-write-drops-plugin-in-process': 'prevention',
        'later-plugin-rewrites-input': 'prevention',
        'fetch-inside-execute': 'prevention',
        'no-origin-field': 'run_identity',
        'bare-start-without-plugin': 'launcher_checks',
    },
}
CONTRACT_FILES = {'claude-code': 'claude_code.toml', 'opencode': 'opencode.toml'}
FORBIDDEN = re.compile(r'%|percent|score', re.IGNORECASE)
PRIVATE_LABELS = re.compile(r'\b(CC[0-9]|O3load|O-guard-off|P[0-9]|R[0-9]|O[0-9])\b')
OUTPUTS: list[str] = []


def doctor_run(*args: str, env: dict) -> subprocess.CompletedProcess:
    proc = kit('doctor', *args, env=env)
    OUTPUTS.append(proc.stdout.decode('utf-8', 'replace') + proc.stderr.decode('utf-8', 'replace'))
    return proc


def doctor_json(env: dict, *args: str) -> dict:
    proc = doctor_run('--json', *args, env=env)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def fake_argv(base: Path, version: str, mode: str = 'guarded') -> str:
    return json.dumps([sys.executable, str(FAKE), str(base / 'fake-out.json'), version, '0', mode])


def doctor_env(base: Path, claude: str, opencode: str, **extra: str) -> dict:
    return base_env(
        KIT_STATE_ROOT=str(base / 'state'),
        KIT_HARNESS_ARGV_CLAUDE_CODE=claude,
        KIT_HARNESS_ARGV_OPENCODE=opencode,
        **extra,
    )


# ---- the contract files


def test_contracts_hold_the_closed_lists_and_the_required_losses():
    for harness, name in CONTRACT_FILES.items():
        path = doctor.CONTRACTS_DIR / name
        data = tomllib.loads(path.read_text(encoding='utf-8'))
        assert data['harness'] == {'name': harness, 'version': PINNED[harness]}, data['harness']
        ids = [o['id'] for o in data['objective']]
        assert sorted(ids) == sorted(OBJECTIVES) and len(ids) == len(OBJECTIVES), ids
        for objective in data['objective']:
            assert set(objective) == {'id', 'state', 'mark', 'evidence'}, objective
            assert objective['state'] in STATES and objective['mark'] in MARKS, objective
            expected = 'absent' if objective['id'] == 'prevention' else 'unknown'
            assert objective['state'] == expected, objective
            if objective['id'] == 'prevention':
                assert objective['evidence'].strip(), objective
            else:
                assert objective['evidence'] == '', objective
        losses = {loss['id']: loss for loss in data['loss']}
        assert len(losses) == len(data['loss']), 'a loss id repeats'
        for loss_id, objective in REQUIRED_LOSSES[harness].items():
            assert loss_id in losses, (harness, loss_id)
            assert losses[loss_id]['objective'] == objective, losses[loss_id]
        for loss in data['loss']:
            assert set(loss) == {'id', 'objective', 'mark', 'evidence', 'text'}, loss
            assert loss['objective'] in OBJECTIVES and loss['mark'] in MARKS, loss
            assert PINNED[harness] in loss['evidence'], loss
            assert re.search(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', loss['evidence']), loss
            assert loss['text'].strip(), loss
        for row in [*data['objective'], *data['loss']]:
            for value in row.values():
                assert not PRIVATE_LABELS.search(value), (harness, value)
                assert not FORBIDDEN.search(value), (harness, value)
                assert value.isascii(), (harness, value)


def test_contract_rows_carry_the_marks_the_spec_gives():
    claude = doctor.load_contract('claude-code')
    marks = {loss['id']: loss['mark'] for loss in claude['loss']}
    assert marks['no-origin-field'] == 'read', marks
    assert all(m == 'measured' for k, m in marks.items() if k != 'no-origin-field'), marks
    malformed = next(x for x in claude['loss'] if x['id'] == 'settings-malformed-silent')
    assert 'by construction' in malformed['text'], malformed
    unreadable = next(x for x in claude['loss'] if x['id'] == 'settings-unreadable-silent')
    assert unreadable['evidence'] == (
        'Claude Code 2.1.316, 2026-11-08: with a read deny on settings.json the run exited 0, '
        'the hook did not run and Bash executed, in 3 of 3 sets.'
    ), unreadable
    assert unreadable['text'] == (
        'An unreadable settings.json leaves exit 0, no hook run and the tool executed; '
        'caught at launch by the canary, not during a run.'
    ), unreadable
    opencode = {loss['id']: loss['mark'] for loss in doctor.load_contract('opencode')['loss']}
    assert opencode['fetch-inside-execute'] == 'read', opencode
    assert opencode['bare-start-without-plugin'] == 'inferred', opencode
    for loss_id in (
        'plugin-load-failure-silent',
        'config-write-drops-plugin-in-process',
        'later-plugin-rewrites-input',
        'no-origin-field',
    ):
        assert opencode[loss_id] == 'measured', (loss_id, opencode)


# ---- the heartbeat and run status


def test_heartbeat_writes_its_keys_and_counts_up():
    base = scratch()
    try:
        run_dir = base / 'runs' / 'r'
        run_dir.mkdir(parents=True)
        beat = doctor.Heartbeat(run_dir, 'r', interval_s=0.05)
        beat.start()
        time.sleep(0.4)
        beat.stop()
        first = json.loads((run_dir / 'heartbeat.json').read_text(encoding='utf-8'))
        assert set(first) == {'run_id', 'pid', 'seq', 'utc'}, first
        assert first['run_id'] == 'r' and first['pid'] == os.getpid(), first
        assert first['seq'] >= 3, first
        time.sleep(0.2)
        after = json.loads((run_dir / 'heartbeat.json').read_text(encoding='utf-8'))
        assert after['seq'] == first['seq'], 'the heartbeat went on after stop'
        assert doctor.HEARTBEAT_S == 2 and doctor.STALE_S == 10
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _run_dir(base: Path, outcome: str, beat_age: float | None, started_age: float = 60) -> Path:
    now = datetime.now(timezone.utc)
    run_dir = base / 'runs' / f'run-{outcome}-{beat_age}'
    run_dir.mkdir(parents=True)
    started = (now - timedelta(seconds=started_age)).strftime('%Y-%m-%dT%H:%M:%SZ')
    record = {'run_id': run_dir.name, 'harness': 'opencode', 'started_utc': started}
    record['outcome'] = outcome
    (run_dir / 'run.json').write_text(json.dumps(record), encoding='ascii')
    if beat_age is not None:
        utc = (now - timedelta(seconds=beat_age)).strftime('%Y-%m-%dT%H:%M:%SZ')
        beat = {'run_id': run_dir.name, 'pid': 1, 'seq': 3, 'utc': utc}
        (run_dir / 'heartbeat.json').write_text(json.dumps(beat), encoding='ascii')
    return run_dir


def test_run_status_follows_outcome_and_heartbeat():
    base = scratch()
    try:
        cases = [
            ('ended', None, 60, 'ended'),
            ('refused-canary', None, 60, 'refused'),
            ('launched', 1, 60, 'running'),
            ('launched', 30, 60, 'stale'),
            ('launched', None, 60, 'stale'),
            ('minted', None, 1, 'running'),
            ('minted', 30, 60, 'stale'),
        ]
        for outcome, beat_age, started_age, expected in cases:
            run_dir = _run_dir(base, outcome, beat_age, started_age)
            found = doctor.run_status(run_dir)
            assert found == expected, (outcome, beat_age, found)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _wait(predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.2)
    return False


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _kill_pid(pid: int) -> None:
    if os.name == 'nt':
        import ctypes

        k32 = ctypes.WinDLL('kernel32')
        k32.OpenProcess.restype = ctypes.c_void_p
        handle = k32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if handle:
            k32.TerminateProcess(ctypes.c_void_p(handle), 1)
            k32.CloseHandle(ctypes.c_void_p(handle))
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def test_heartbeat_goes_stale_when_the_launcher_is_killed():
    case = Case(scratch(), 'claude-code', mode='sleep-60')
    session_pid = kit_pid = None
    try:
        args = [
            sys.executable,
            '-m',
            'harness_kit',
            'run',
            '--harness',
            'claude-code',
            '--home',
            str(case.home),
            '--workdir',
            str(case.work),
            '--policy',
            str(case.policy),
            '--',
            *SESSION_ARGS['claude-code'],
        ]
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            args, env=case.env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        pid_file = Path(str(case.out) + '.pid')
        try:
            assert _wait(pid_file.exists, 60), 'the session did not start'
            session_pid = int(pid_file.read_text(encoding='ascii'))
            beat_file = case.run_dir() / 'heartbeat.json'

            def two_beats() -> bool:
                beat = _read(beat_file)
                return beat is not None and beat['seq'] >= 2

            assert _wait(two_beats, 10), _read(beat_file)
            beat = _read(beat_file)
            kit_pid = case.run_json()['kit_pid']
            assert beat['run_id'] == case.run_dir().name and beat['pid'] == kit_pid, beat
            assert case.run_json()['outcome'] == 'launched', case.run_json()
            report = doctor_json(case.env(KIT_POLICY=str(case.policy)))
            runs = {r['run_id']: r for r in report['runs']}
            assert runs[case.run_dir().name]['status'] == 'running', report['runs']
            assert runs[case.run_dir().name]['harness'] == 'claude-code', report['runs']
        finally:
            if kit_pid is not None:
                _kill_pid(kit_pid)
            proc.kill()
            proc.wait(timeout=30)
        last = _read(case.run_dir() / 'heartbeat.json')
        time.sleep(doctor.STALE_S + 2)
        assert _read(case.run_dir() / 'heartbeat.json') == last, 'a beat after the kill'
        report = doctor_json(case.env())
        runs = {r['run_id']: r for r in report['runs']}
        assert runs[case.run_dir().name]['status'] == 'stale', report['runs']
    finally:
        if session_pid is not None:
            _kill_pid(session_pid)
        case.close()


def test_a_session_that_ends_reads_ended_with_heartbeats_counted():
    case = Case(scratch(), 'opencode', mode='sleep-5')
    try:
        proc = case.run()
        assert proc.returncode == 0, proc.stderr
        beat = json.loads((case.run_dir() / 'heartbeat.json').read_text(encoding='utf-8'))
        assert beat['seq'] >= 2, beat
        assert case.run_json()['outcome'] == 'ended', case.run_json()
        report = doctor_json(case.env())
        runs = {r['run_id']: r for r in report['runs']}
        assert runs[case.run_dir().name]['status'] == 'ended', report['runs']
    finally:
        case.close()


def test_a_refused_canary_reads_refused():
    case = Case(scratch(), 'opencode', mode='unguarded')
    try:
        proc = case.run()
        assert proc.returncode == 65, proc.stderr
        report = doctor_json(case.env())
        runs = {r['run_id']: r for r in report['runs']}
        assert runs[case.run_dir().name]['status'] == 'refused', report['runs']
    finally:
        case.close()


# ---- doctor from the contract


def test_doctor_reads_the_contract_when_the_version_matches():
    base = scratch()
    try:
        env = doctor_env(
            base, fake_argv(base, PINNED['claude-code']), fake_argv(base, PINNED['opencode'])
        )
        report = doctor_json(env)
        assert set(report) == {'kit_doctor', 'harnesses', 'runs', 'not_launched'}, report
        assert report['kit_doctor'] == 1, report
        for harness in ('claude-code', 'opencode'):
            entry = report['harnesses'][harness]
            assert set(entry) == {
                'version_found',
                'contract_version',
                'objectives',
                'losses',
            }, entry
            assert entry['version_found'] == PINNED[harness], entry
            assert entry['contract_version'] == PINNED[harness], entry
            assert list(entry['objectives']) == list(OBJECTIVES), entry['objectives']
            for name, objective in entry['objectives'].items():
                assert set(objective) == {'state', 'source', 'evidence'}, objective
                assert objective['source'] == 'contract', objective
                expected = 'absent' if name == 'prevention' else 'unknown'
                assert objective['state'] == expected, (name, objective)
            losses = {loss['id'] for loss in entry['losses']}
            assert set(REQUIRED_LOSSES[harness]) <= losses, losses
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_doctor_reports_unknown_on_a_version_mismatch():
    base = scratch()
    try:
        env = doctor_env(base, fake_argv(base, '2.1.999'), fake_argv(base, '2.2.5'))
        entry = doctor_json(env)['harnesses']['claude-code']
        assert entry['version_found'] == '2.1.999', entry
        for name, objective in entry['objectives'].items():
            expected = 'absent' if name == 'prevention' else 'unknown'
            assert objective['state'] == expected, (name, objective)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_tested_contract_reads_unknown_once_the_version_differs():
    from harness_kit import harnesses

    base = scratch()
    saved = doctor.CONTRACTS_DIR
    try:
        contracts = base / 'contracts'
        shutil.copytree(saved, contracts)
        path = contracts / CONTRACT_FILES['claude-code']
        text = path.read_text(encoding='utf-8').replace('state = "unknown"', 'state = "tested"')
        path.write_text(text, encoding='utf-8')
        doctor.CONTRACTS_DIR = contracts
        driver = harnesses.get('claude-code')
        for version, expected in (('2.1.316', 'tested'), ('2.1.999', 'unknown')):
            env = doctor_env(base, fake_argv(base, version), fake_argv(base, '2.2.5'))
            objectives = doctor.harness_report(driver, env, None)['objectives']
            for name, row in objectives.items():
                want = 'absent' if name == 'prevention' else expected
                assert row['state'] == want, (version, name, row)
    finally:
        doctor.CONTRACTS_DIR = saved
        shutil.rmtree(base, ignore_errors=True)


def test_doctor_reports_every_objective_unknown_without_a_binary():
    base = scratch()
    try:
        missing = json.dumps([str(base / 'no-such-harness.exe')])
        env = doctor_env(base, missing, fake_argv(base, '2.2.5'))
        report = doctor_json(env)
        entry = report['harnesses']['claude-code']
        assert entry['version_found'] is None, entry
        assert {o['state'] for o in entry['objectives'].values()} == {'unknown'}, entry
        other = report['harnesses']['opencode']['objectives']['prevention']
        assert other['state'] == 'absent', other
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_not_launched_session_reads_guarantees_unknown():
    base = scratch()
    try:
        policy = base / 'policy.toml'
        policy.write_text('version = 1\n', encoding='utf-8')
        env = doctor_env(
            base,
            fake_argv(base, PINNED['claude-code']),
            fake_argv(base, PINNED['opencode']),
            KIT_POLICY=str(policy),
        )
        ev = event(**{'session.id': 'bare-session-1'})
        judged = kit('judge', env=env, stdin=json.dumps(ev).encode('ascii'))
        assert json.loads(judged.stdout)['verdict'] == 'allow', judged.stdout
        report = doctor_json(env)
        found = [e for e in report['not_launched'] if e['session'] == 'bare-session-1']
        assert len(found) == 1, report['not_launched']
        entry = found[0]
        assert set(entry) == {'session', 'harness', 'events', 'guarantees'}, entry
        assert entry['harness'] == 'claude-code' and entry['guarantees'] == 'unknown', entry
        assert entry['events'] == 1, entry
        text = doctor_run(env=env)
        assert text.returncode == 0, text.stderr
        lines = [
            line for line in text.stdout.decode('ascii').splitlines() if 'bare-session-1' in line
        ]
        assert len(lines) == 1 and 'not launched, guarantees unknown' in lines[0], lines
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---- doctor --live


def _live_policy(base: Path) -> Path:
    policy = base / 'policy.toml'
    roots = json.dumps(str(base / 'tests'))
    policy.write_text(f'version = 1\n\n[launcher]\ntest_roots = [{roots}]\n', encoding='utf-8')
    return policy


def test_live_doctor_follows_the_canary():
    base = scratch()
    try:
        policy = _live_policy(base)
        env = doctor_env(
            base,
            fake_argv(base, PINNED['claude-code']),
            fake_argv(base, PINNED['opencode']),
            KIT_POLICY=str(policy),
        )
        live = str(base / 'tests' / 'live')
        report = doctor_json(env, '--live', '--live-root', live)
        claude = report['harnesses']['claude-code']['objectives']
        opencode = report['harnesses']['opencode']['objectives']
        for objectives in (claude, opencode):
            for name in ('guard_loaded', 'refusal_in_turn', 'allow_passes'):
                assert objectives[name]['source'] == 'live', (name, objectives[name])
            assert objectives['guard_loaded']['state'] == 'degraded', objectives
            assert objectives['allow_passes']['state'] == 'tested', objectives
            assert objectives['prevention']['state'] == 'absent', objectives
            assert objectives['heartbeat']['source'] == 'contract', objectives
        assert claude['refusal_in_turn']['state'] == 'degraded', claude
        assert opencode['refusal_in_turn']['state'] == 'tested', opencode

        broken = doctor_env(
            base,
            fake_argv(base, PINNED['claude-code'], 'unguarded'),
            json.dumps([str(base / 'no-such-harness.exe')]),
            KIT_POLICY=str(policy),
        )
        report = doctor_json(broken, '--live', '--live-root', live)
        claude = report['harnesses']['claude-code']['objectives']
        for name in ('guard_loaded', 'refusal_in_turn', 'allow_passes'):
            assert claude[name] == {**claude[name], 'state': 'absent', 'source': 'live'}, claude
        assert claude['prevention']['state'] == 'absent', claude
        opencode = report['harnesses']['opencode']['objectives']
        assert {o['state'] for o in opencode.values()} == {'unknown'}, opencode
        text = doctor_run('--live', '--live-root', live, env=broken)
        assert text.returncode == 0, text.stderr
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_live_root_outside_the_test_roots_is_refused():
    base = scratch()
    try:
        policy = _live_policy(base)
        env = doctor_env(
            base,
            fake_argv(base, PINNED['claude-code']),
            fake_argv(base, PINNED['opencode']),
            KIT_POLICY=str(policy),
        )
        outside = base / 'elsewhere'
        proc = doctor_run('--live', '--live-root', str(outside), env=env)
        assert proc.returncode == 64, proc.returncode
        assert not outside.exists(), 'the refused live root was created'
        no_policy = dict(env)
        del no_policy['KIT_POLICY']
        proc = doctor_run('--live', '--live-root', str(base / 'tests' / 'x'), env=no_policy)
        assert proc.returncode == 64, proc.returncode
        proc = doctor_run('--live', env=env)
        assert proc.returncode == 64, proc.returncode
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_zz_no_output_holds_a_percent_sign_or_the_words():
    help_text = kit('doctor', '--help', env=base_env())
    OUTPUTS.append(help_text.stdout.decode('utf-8', 'replace'))
    assert len(OUTPUTS) >= 10, len(OUTPUTS)
    for output in OUTPUTS:
        assert not FORBIDDEN.search(output), output


if __name__ == '__main__':
    run_module(globals(), 'heartbeat, doctor and contracts')

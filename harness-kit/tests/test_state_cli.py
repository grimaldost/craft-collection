#!/usr/bin/env python3
"""Checks of `kit state path`, `kit state new-run` and the run identity of `kit judge`.

Contract under test:
- `kit state path` prints the state root and creates nothing; a root inside a
  harness's configuration exits 64 with one stderr line and creates nothing;
- `kit state new-run --harness NAME` mints a run and prints its id and folder;
- `kit judge` fills `launched` and `run_id` from KIT_RUN_ID and the state root
  (a forged id is not launched), and appends one journal line per judgement,
  under runs/<id>/ when launched, else under not-launched/<16 hex of
  sha256(session.id)>/, or not-launched/invalid/ for an invalid event; the
  line never holds the command text or a path;
- a journal that cannot be written (a refused root, a lock held past its
  second) turns the verdict into `unknown`, governed, effect deny;
- an event of a harness other than claude-code that is not launched is denied
  by `launcher.required`, ahead of the policy's rules and after it loads;
- concurrent judges leave whole, parsable lines.

Stdlib-runnable: `python test_state_cli.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from kit_fixtures import SAMPLE_POLICY, SRC, event, run_module
from test_state import hold_lock

CONFIG_VARS = (
    'CLAUDE_CONFIG_DIR',
    'OPENCODE_CONFIG_DIR',
    'XDG_CONFIG_HOME',
    'CODEX_HOME',
    'PI_CODING_AGENT_DIR',
    'GOOSE_PATH_ROOT',
)
JOURNAL_KEYS = [
    'ts_utc',
    'run_id',
    'launched',
    'session_id',
    'harness',
    'act_kind',
    'payload_sha256',
    'verdict',
    'effect',
    'rule',
]
FORGED = '20261109T120000Z-0123456789ab'
PRIVATE_COMMAND = 'cat /w/private-dir/notes.txt'


def _env(**extra: str) -> dict:
    drop = ('PYTHONIOENCODING', *CONFIG_VARS)
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_') and k not in drop}
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def _kit(*args: str, stdin: bytes = b'', **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=stdin,
        capture_output=True,
        env=_env(**env),
        timeout=60,
    )


def _real(path: Path | str) -> Path:
    return Path(os.path.realpath(str(path)))


def _policy(td: str) -> Path:
    path = Path(td) / 'policy.toml'
    path.write_bytes(SAMPLE_POLICY.encode('utf-8'))
    return path


def _judge(ev: dict | bytes, policy: Path, **env: str) -> dict:
    data = ev if isinstance(ev, bytes) else json.dumps(ev).encode('utf-8')
    proc = _kit('judge', '--policy', str(policy), stdin=data, **env)
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    lines = proc.stdout.decode('ascii').splitlines()
    assert len(lines) == 1, proc.stdout
    return json.loads(lines[0])


def _lines(journal: Path) -> list[dict]:
    raw = journal.read_bytes()
    assert raw.endswith(b'\n'), raw
    return [json.loads(x) for x in raw.decode('ascii').splitlines()]


def _session_dir(root: Path, session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode('utf-8')).hexdigest()[:16]
    return root / 'not-launched' / digest


def _new_run(root: Path, harness: str = 'opencode') -> str:
    proc = _kit('state', 'new-run', '--harness', harness, KIT_STATE_ROOT=str(root))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.decode('ascii'))
    assert list(out) == ['run_id', 'run_dir'], out
    assert _real(out['run_dir']) == _real(root) / 'runs' / out['run_id'], out
    return out['run_id']


def test_state_path_prints_the_override_and_creates_nothing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        proc = _kit('state', 'path', KIT_STATE_ROOT=str(root))
        assert proc.returncode == 0, proc.stderr
        assert _real(proc.stdout.decode('ascii').strip()) == _real(root)
        assert not root.exists()


def test_state_path_prints_the_platform_default():
    with tempfile.TemporaryDirectory() as td:
        env = {'LOCALAPPDATA': td} if os.name == 'nt' else {'XDG_STATE_HOME': td}
        proc = _kit('state', 'path', **env)
        assert proc.returncode == 0, proc.stderr
        assert _real(proc.stdout.decode('ascii').strip()) == _real(td) / 'harness-kit'
        assert not (Path(td) / 'harness-kit').exists()
        if os.name != 'nt':
            env = _env(HOME=td)
            env.pop('XDG_STATE_HOME', None)
            proc = subprocess.run(
                [sys.executable, '-m', 'harness_kit', 'state', 'path'],
                capture_output=True,
                env=env,
                timeout=60,
            )
            expected = _real(td) / '.local' / 'state' / 'harness-kit'
            assert _real(proc.stdout.decode('ascii').strip()) == expected, proc


def test_each_refusal_exits_64_and_creates_nothing():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cases = [(base / name / 'kit', {}) for name in ('.claude', '.opencode', '.pi')]
        cases.append((base / '.config' / 'opencode' / 'kit', {}))
        for var in CONFIG_VARS:
            cases.append((base / 'conf' / 'kit', {var: str(base / 'conf')}))
        for root, extra in cases:
            for args in (('state', 'path'), ('state', 'new-run', '--harness', 'opencode')):
                proc = _kit(*args, KIT_STATE_ROOT=str(root), **extra)
                assert proc.returncode == 64, (root, extra, args, proc.returncode, proc.stderr)
                assert proc.stdout == b'', proc.stdout
                err = proc.stderr.decode('ascii').splitlines()
                assert len(err) == 1 and 'refused' in err[0], err
                assert not root.exists(), root
        assert sorted(p.name for p in base.iterdir()) == []


def test_new_run_mints_a_run_json():
    with tempfile.TemporaryDirectory() as td:
        run_id = _new_run(Path(td), 'claude-code')
        run_json = Path(td) / 'runs' / run_id / 'run.json'
        data = json.loads(run_json.read_bytes())
        assert (data['run_id'], data['harness'], data['outcome']) == (
            run_id,
            'claude-code',
            'minted',
        )


def test_a_launched_judgement_carries_the_run_and_journals_under_it():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        run_id = _new_run(root)
        ev = event(run_id='something-else', **{'act.command': PRIVATE_COMMAND})
        ev['harness']['name'] = 'opencode'
        v = _judge(ev, _policy(td), KIT_STATE_ROOT=str(root), KIT_RUN_ID=run_id)
        assert (v['verdict'], v['run_id'], v['launched']) == ('allow', run_id, True), v
        journal = root / 'runs' / run_id / 'journal.ndjson'
        (line,) = _lines(journal)
        assert list(line) == JOURNAL_KEYS, line
        assert (line['run_id'], line['launched'], line['session_id']) == (run_id, True, 's1')
        assert (line['harness'], line['act_kind'], line['payload_sha256']) == (
            'opencode',
            'shell',
            'a' * 64,
        )
        assert (line['verdict'], line['effect'], line['rule']) == ('allow', 'allow', None)
        raw = journal.read_bytes()
        for secret in (PRIVATE_COMMAND, 'private-dir', 'notes.txt', '/w'):
            assert secret.encode() not in raw, secret
        assert not (root / 'not-launched').exists()


def test_a_forged_id_is_not_launched():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        root.mkdir()
        policy = _policy(td)
        for forged in (FORGED, '../runs', 'x'):
            ev = event(run_id=FORGED)
            v = _judge(ev, policy, KIT_STATE_ROOT=str(root), KIT_RUN_ID=forged)
            assert (v['verdict'], v['run_id'], v['launched']) == ('allow', None, False), v
        lines = _lines(_session_dir(root, 's1') / 'journal.ndjson')
        assert len(lines) == 3, lines
        assert all(x['run_id'] is None and x['launched'] is False for x in lines), lines
        assert not (root / 'runs').exists()


def test_an_unlaunched_claude_code_event_is_judged_by_the_policy_and_journaled():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        policy = _policy(td)
        v = _judge(event(), policy, KIT_STATE_ROOT=str(root))
        assert (v['verdict'], v['rule'], v['launched']) == ('allow', None, False), v
        ev = event(origin='child', **{'observation.origin': 'observed'})
        ev['act']['command'] = 'cp x /w/settings.json'
        ev['session']['id'] = 'café-session'
        v = _judge(ev, policy, KIT_STATE_ROOT=str(root))
        assert (v['verdict'], v['rule']) == ('deny', 'no-config-write'), v
        (line,) = _lines(_session_dir(root, 'café-session') / 'journal.ndjson')
        assert (line['verdict'], line['rule'], line['session_id']) == (
            'deny',
            'no-config-write',
            'café-session',
        )


def test_launcher_required_denies_an_unlaunched_non_claude_event():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        policy = _policy(td)
        ev = event()
        ev['harness'] = {'name': 'opencode', 'version': '2.2.5'}
        v = _judge(ev, policy, KIT_STATE_ROOT=str(root))
        assert (v['verdict'], v['effect'], v['governed'], v['rule']) == (
            'deny',
            'deny',
            True,
            'launcher.required',
        ), v
        assert v['policy_sha256'] == hashlib.sha256(policy.read_bytes()).hexdigest(), v
        (line,) = _lines(_session_dir(root, 's1') / 'journal.ndjson')
        assert (line['harness'], line['rule']) == ('opencode', 'launcher.required'), line
        v = _judge(ev, policy, KIT_STATE_ROOT=str(root), KIT_RUN_ID=FORGED)
        assert v['rule'] == 'launcher.required', v


def test_an_unreadable_policy_comes_before_launcher_required():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        ev = event()
        ev['harness']['name'] = 'opencode'
        v = _judge(ev, Path(td) / 'absent.toml', KIT_STATE_ROOT=str(root))
        assert (v['verdict'], v['effect'], v['governed'], v['rule']) == (
            'unknown',
            'deny',
            True,
            None,
        ), v


def test_an_invalid_event_is_journaled_under_invalid_or_its_run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        policy = _policy(td)
        v = _judge(b'{"kit_event": 1}', policy, KIT_STATE_ROOT=str(root))
        assert (v['verdict'], v['launched']) == ('unknown', False), v
        (line,) = _lines(root / 'not-launched' / 'invalid' / 'journal.ndjson')
        assert list(line) == JOURNAL_KEYS, line
        assert (line['verdict'], line['effect'], line['session_id']) == ('unknown', 'deny', None)
        run_id = _new_run(root)
        v = _judge(b'not json', policy, KIT_STATE_ROOT=str(root), KIT_RUN_ID=run_id)
        assert (v['verdict'], v['run_id'], v['launched']) == ('unknown', run_id, True), v
        assert len(_lines(root / 'runs' / run_id / 'journal.ndjson')) == 1


def test_a_refused_root_is_a_journal_that_cannot_be_written():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / '.claude' / 'kit'
        v = _judge(event(), _policy(td), KIT_STATE_ROOT=str(root))
        assert (v['verdict'], v['effect'], v['governed']) == ('unknown', 'deny', True), v
        assert not root.exists()


def test_a_root_that_is_a_file_is_a_journal_that_cannot_be_written():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        root.write_bytes(b'')
        v = _judge(event(), _policy(td), KIT_STATE_ROOT=str(root))
        assert (v['verdict'], v['effect'], v['governed']) == ('unknown', 'deny', True), v


def test_a_lock_held_past_its_second_turns_the_verdict_unknown():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        policy = _policy(td)
        run_id = _new_run(root)
        lock = root / 'runs' / run_id / 'journal.ndjson.lock'
        holder = hold_lock(lock, 5)
        try:
            v = _judge(event(), policy, KIT_STATE_ROOT=str(root), KIT_RUN_ID=run_id)
        finally:
            holder.kill()
            holder.wait()
        assert (v['verdict'], v['effect'], v['governed'], v['rule']) == (
            'unknown',
            'deny',
            True,
            None,
        ), v
        assert (v['run_id'], v['launched']) == (run_id, True), v
        journal = root / 'runs' / run_id / 'journal.ndjson'
        assert not journal.exists() or journal.read_bytes() == b''
        session_dir = _session_dir(root, 's1')
        session_dir.mkdir(parents=True)
        holder = hold_lock(session_dir / 'journal.ndjson.lock', 5)
        try:
            v = _judge(event(), policy, KIT_STATE_ROOT=str(root))
        finally:
            holder.kill()
            holder.wait()
        assert (v['verdict'], v['effect'], v['governed']) == ('unknown', 'deny', True), v


def test_twenty_concurrent_judges_leave_twenty_whole_lines():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        policy = _policy(td)
        run_id = _new_run(root)
        env = _env(KIT_STATE_ROOT=str(root), KIT_RUN_ID=run_id)
        procs = []
        for n in range(20):
            ev = event(**{'session.id': f'session-{n:02d}', 'act.command': 'x' * 5000})
            proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [sys.executable, '-m', 'harness_kit', 'judge', '--policy', str(policy)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            procs.append((proc, json.dumps(ev).encode('utf-8')))
        for proc, data in procs:
            out, err = proc.communicate(data, timeout=120)
            assert proc.returncode == 0, err
            assert json.loads(out)['verdict'] == 'allow', out
        lines = _lines(root / 'runs' / run_id / 'journal.ndjson')
        assert len(lines) == 20, len(lines)
        assert sorted(x['session_id'] for x in lines) == [f'session-{n:02d}' for n in range(20)]


if __name__ == '__main__':
    run_module(globals(), 'kit state and judge run identity')

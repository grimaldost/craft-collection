"""Tests for anchor_inject.py — the SessionStart(compact|resume) re-injection hook.

Contract under test (panel-hardened design, memory-suite v2):
- inert unless SESSION_WORKFLOW_ANCHOR_HOOKS=1 (house precedent: hooks ship OFF);
- silent no-op when no anchor exists (an anchor-less session pays nothing);
- fresh anchor -> stdout JSON with hookSpecificOutput.additionalContext carrying
  the anchor content;
- stale anchor -> still injected, prefixed with an explicit staleness warning
  (never silently suppressed, never silently trusted);
- closed anchors (*.closed.md) are never injected;
- oversized anchors are truncated to a bound (the anchor must not become the
  token hog it exists to prevent);
- every injection appends one telemetry line to log.ndjson;
- the hook always exits 0 (a broken hook must never break session start).

Stdlib-runnable (no pytest required): `python test_anchor_inject.py` runs every
test and prints `ok:`; the same no-arg functions are also collected under pytest.
The tests own their temp dirs via tempfile so `run_tests.py` (bare-python runner)
actually executes them, rather than silently collecting zero pytest-fixture tests.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'anchor_inject.py'


def run_hook(
    cwd: Path, env_on: bool = True, source: str = 'compact', extra_env: dict | None = None
):
    env = dict(os.environ)
    env.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
    if env_on:
        env['SESSION_WORKFLOW_ANCHOR_HOOKS'] = '1'
    if extra_env:
        env.update(extra_env)
    payload = json.dumps(
        {
            'hook_event_name': 'SessionStart',
            'source': source,
            'session_id': 'test-session',
            'cwd': str(cwd),
        }
    )
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT)],
        input=payload,
        capture_output=True,
        encoding='utf-8',  # the hook emits UTF-8 regardless of platform default
        env=env,
        timeout=30,
    )
    return proc


def make_anchor(
    base: Path,
    name: str = 'run.md',
    body: str = '# Mission\ntest mission\n# Cursor\nnext: step 7\n',
    age_s: int = 0,
):
    anchors = base / '.claude' / 'anchors'
    anchors.mkdir(parents=True, exist_ok=True)
    f = anchors / name
    f.write_text('---\nformat: anchor/v0\nstep: 7\n---\n' + body, encoding='utf-8')
    if age_s:
        old = time.time() - age_s
        os.utime(f, (old, old))
    return f


def test_inert_without_env():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp)
        proc = run_hook(tmp, env_on=False)
        assert proc.returncode == 0
        assert proc.stdout.strip() == ''


def test_silent_when_no_anchor():
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d))
        assert proc.returncode == 0
        assert proc.stdout.strip() == ''


def test_fresh_anchor_injected():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp)
        proc = run_hook(tmp)
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        ctx = out['hookSpecificOutput']['additionalContext']
        assert out['hookSpecificOutput']['hookEventName'] == 'SessionStart'
        assert 'test mission' in ctx
        assert 'next: step 7' in ctx


def test_closed_anchor_ignored():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='done.closed.md')
        proc = run_hook(tmp)
        assert proc.returncode == 0
        assert proc.stdout.strip() == ''


def test_stale_anchor_injected_with_warning():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, age_s=3 * 24 * 3600)
        proc = run_hook(tmp)
        out = json.loads(proc.stdout)
        ctx = out['hookSpecificOutput']['additionalContext']
        assert 'STALE' in ctx
        assert 'test mission' in ctx


def test_oversized_anchor_truncated():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, body='# Cursor\n' + ('x' * 50_000))
        proc = run_hook(tmp)
        out = json.loads(proc.stdout)
        ctx = out['hookSpecificOutput']['additionalContext']
        assert len(ctx) < 20_000
        assert 'truncated' in ctx.lower()


def test_telemetry_line_appended():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp)
        run_hook(tmp)
        log = tmp / '.claude' / 'anchors' / 'log.ndjson'
        assert log.exists()
        rec = json.loads(log.read_text(encoding='utf-8').strip().splitlines()[-1])
        assert rec['event'] == 'anchor-inject'
        assert rec['source'] == 'compact'
        assert rec['stale'] is False


def test_newest_non_closed_wins():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='old.md', body='OLD ANCHOR\n', age_s=3600)
        make_anchor(tmp, name='new.md', body='NEW ANCHOR\n')
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'NEW ANCHOR' in ctx
        assert 'OLD ANCHOR' not in ctx


def test_non_ascii_anchor_survives_cp1252_stdout():
    # Campaign anchors essentially always carry non-ASCII (arrows, accented
    # prose). Under Windows hook runners stdout defaults to cp1252; the print
    # used to raise UnicodeEncodeError, the fail-safe swallowed it, and the
    # harness received 0 bytes — a silent no-op. PYTHONIOENCODING reproduces
    # that stdout on any platform.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, body='# Cursor\nnext: → merge · ⚠ não esquecer\n')
        proc = run_hook(tmp, extra_env={'PYTHONIOENCODING': 'cp1252'})
        assert proc.returncode == 0
        assert proc.stdout.strip(), 'hook emitted 0 bytes under cp1252 stdout'
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert '→ merge' in ctx
        assert '⚠ não esquecer' in ctx
        log = tmp / '.claude' / 'anchors' / 'log.ndjson'
        rec = json.loads(log.read_text(encoding='utf-8').strip().splitlines()[-1])
        assert rec['event'] == 'anchor-inject'


def test_emit_failure_logs_failure_event_not_success():
    # Telemetry must never say "injected" unless the payload actually reached
    # stdout: the success record is written only after the print, and an emit
    # failure logs a distinct event (still exit 0 — never break a session).
    import io

    import anchor_inject

    class BoomStdout:  # no reconfigure attribute, write always raises
        def write(self, s):
            raise UnicodeEncodeError('charmap', 'x', 0, 1, 'boom')

        def flush(self):
            pass

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp)
        payload = json.dumps(
            {'hook_event_name': 'SessionStart', 'source': 'compact', 'cwd': str(tmp)}
        )
        old_in, old_out = sys.stdin, sys.stdout
        old_env = os.environ.get('SESSION_WORKFLOW_ANCHOR_HOOKS')
        os.environ['SESSION_WORKFLOW_ANCHOR_HOOKS'] = '1'
        sys.stdin, sys.stdout = io.StringIO(payload), BoomStdout()
        try:
            rc = anchor_inject.main()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
            if old_env is None:
                os.environ.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
            else:
                os.environ['SESSION_WORKFLOW_ANCHOR_HOOKS'] = old_env
        assert rc == 0
        log = tmp / '.claude' / 'anchors' / 'log.ndjson'
        events = [
            json.loads(line)['event']
            for line in log.read_text(encoding='utf-8').strip().splitlines()
        ]
        assert 'anchor-inject-failed' in events
        assert 'anchor-inject' not in events, 'success logged for an injection that never emitted'


if __name__ == '__main__':
    test_inert_without_env()
    test_silent_when_no_anchor()
    test_fresh_anchor_injected()
    test_closed_anchor_ignored()
    test_stale_anchor_injected_with_warning()
    test_oversized_anchor_truncated()
    test_telemetry_line_appended()
    test_newest_non_closed_wins()
    test_non_ascii_anchor_survives_cp1252_stdout()
    test_emit_failure_logs_failure_event_not_success()
    print('ok: all anchor_inject tests passed')

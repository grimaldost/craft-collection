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
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'anchor_inject.py'


def run_hook(cwd: Path, env_on: bool = True, source: str = 'compact'):
    env = dict(os.environ)
    env.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
    if env_on:
        env['SESSION_WORKFLOW_ANCHOR_HOOKS'] = '1'
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
        text=True,
        env=env,
        timeout=30,
    )
    return proc


def make_anchor(
    tmp_path: Path,
    name: str = 'run.md',
    body: str = '# Mission\ntest mission\n# Cursor\nnext: step 7\n',
    age_s: int = 0,
):
    anchors = tmp_path / '.claude' / 'anchors'
    anchors.mkdir(parents=True, exist_ok=True)
    f = anchors / name
    f.write_text('---\nformat: anchor/v0\nstep: 7\n---\n' + body, encoding='utf-8')
    if age_s:
        old = time.time() - age_s
        os.utime(f, (old, old))
    return f


def test_inert_without_env(tmp_path):
    make_anchor(tmp_path)
    proc = run_hook(tmp_path, env_on=False)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ''


def test_silent_when_no_anchor(tmp_path):
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ''


def test_fresh_anchor_injected(tmp_path):
    make_anchor(tmp_path)
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    ctx = out['hookSpecificOutput']['additionalContext']
    assert out['hookSpecificOutput']['hookEventName'] == 'SessionStart'
    assert 'test mission' in ctx
    assert 'next: step 7' in ctx


def test_closed_anchor_ignored(tmp_path):
    make_anchor(tmp_path, name='done.closed.md')
    proc = run_hook(tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ''


def test_stale_anchor_injected_with_warning(tmp_path):
    make_anchor(tmp_path, age_s=3 * 24 * 3600)
    proc = run_hook(tmp_path)
    out = json.loads(proc.stdout)
    ctx = out['hookSpecificOutput']['additionalContext']
    assert 'STALE' in ctx
    assert 'test mission' in ctx


def test_oversized_anchor_truncated(tmp_path):
    make_anchor(tmp_path, body='# Cursor\n' + ('x' * 50_000))
    proc = run_hook(tmp_path)
    out = json.loads(proc.stdout)
    ctx = out['hookSpecificOutput']['additionalContext']
    assert len(ctx) < 20_000
    assert 'truncated' in ctx.lower()


def test_telemetry_line_appended(tmp_path):
    make_anchor(tmp_path)
    run_hook(tmp_path)
    log = tmp_path / '.claude' / 'anchors' / 'log.ndjson'
    assert log.exists()
    rec = json.loads(log.read_text(encoding='utf-8').strip().splitlines()[-1])
    assert rec['event'] == 'anchor-inject'
    assert rec['source'] == 'compact'
    assert rec['stale'] is False


def test_newest_non_closed_wins(tmp_path):
    make_anchor(tmp_path, name='old.md', body='OLD ANCHOR\n', age_s=3600)
    make_anchor(tmp_path, name='new.md', body='NEW ANCHOR\n')
    proc = run_hook(tmp_path)
    ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
    assert 'NEW ANCHOR' in ctx
    assert 'OLD ANCHOR' not in ctx

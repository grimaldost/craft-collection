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
- an `<!-- anchor:tail -->` marker splits HEAD (injected) from TAIL (on disk
  only), so the live state is never the part the bound cuts; marker-less
  anchors keep the whole-file behavior;
- with >1 open anchor in the dir, the injection warns and names the others
  (concurrent tracks must not silently follow the wrong cursor);
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


def test_tail_marker_injects_head_only():
    # anchor/v1 two-tier structure: everything above the `<!-- anchor:tail -->`
    # marker is the live HEAD (mission, cursor, invariants, last-known-good,
    # resume steps) and is injected; the TAIL below (append-only decisions log,
    # resolved history) stays on disk. This is what keeps a long run's live
    # state from being the part an 8K bound cuts.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        body = (
            '# Mission\nlive mission\n# Cursor\nnext: step 9\n'
            '<!-- anchor:tail -->\n'
            '# Decisions log\nOLD DECISION DETAIL\n'
        )
        make_anchor(tmp, body=body)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'live mission' in ctx
        assert 'next: step 9' in ctx
        assert 'OLD DECISION DETAIL' not in ctx
        assert 'tail' in ctx.lower()  # the injection names that a tail exists on disk


def test_oversized_head_still_bounded():
    # The marker does not repeal the bound: a HEAD that alone exceeds the budget
    # still gets the truncation fallback, note included.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        body = '# Cursor\n' + ('x' * 50_000) + '\n<!-- anchor:tail -->\ntail\n'
        make_anchor(tmp, body=body)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert len(ctx) < 20_000
        assert 'truncated' in ctx.lower()


def test_multi_open_anchor_warning():
    # Concurrent tracks in one cwd: the hook still injects the newest open
    # anchor, but it must SAY that other open anchors exist (naming them) so a
    # resumed session on the other track doesn't silently follow the wrong
    # cursor. A single open anchor gets no such warning.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='track-a.md', body='TRACK A\n', age_s=3600)
        make_anchor(tmp, name='track-b.md', body='TRACK B\n')
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'TRACK B' in ctx
        assert 'track-a.md' in ctx  # named, so the reader can go get it
        assert 'other open anchor' in ctx.lower()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='only.md', body='ONLY TRACK\n')
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'other open anchor' not in ctx.lower()


def test_marker_at_top_falls_back_to_whole_file():
    # A marker with an EMPTY head (first line of the file) is a malformed v1
    # anchor; injecting an empty HEAD would be the protocol's cardinal failure
    # (0 useful bytes on the recovery path). Fall back to whole-file instead.
    # (A frontmatter-only head is NOT empty — it still injects the path line
    # and the tail note, which is recoverable.)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        anchors = tmp / '.claude' / 'anchors'
        anchors.mkdir(parents=True)
        (anchors / 'run.md').write_text(
            '<!-- anchor:tail -->\n# Cursor\nTAIL ONLY CONTENT\n', encoding='utf-8'
        )
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'TAIL ONLY CONTENT' in ctx


def test_multi_anchor_warning_caps_names():
    # Pathological dirs (many open anchors) must not blow the injected header:
    # name at most a handful, count the rest.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for i in range(8):
            make_anchor(tmp, name=f'track-{i}.md', body=f'TRACK {i}\n', age_s=(8 - i) * 60)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert '7 other open anchor(s)' in ctx
        assert 'and 2 more' in ctx  # 5 named, 2 counted
        assert ctx.count('track-') <= 6  # the injected one may appear in its path line


def test_is_content_terminal_predicate():
    # The one predicate behind both terminal de-ranking (selection) and the rename
    # offer: an anchor whose CONTENT declares the track done but was never renamed.
    import anchor_inject as ai

    assert ai.is_content_terminal('# Run\n**Status:** CLOSED\nwrap-up\n')
    assert ai.is_content_terminal('foo\nstatus: closed\nbar\n')
    assert ai.is_content_terminal('# Done\nStatus: Landed on main\n')
    assert not ai.is_content_terminal('# Cursor\nnext: step 7\n')
    assert not ai.is_content_terminal('status: in progress\n')
    assert not ai.is_content_terminal('next: close the PR\n')  # 'close' without 'status:' is live


def test_status_line_with_trailing_prose_is_live():
    # A status line whose value is an imperative or a progress note is NOT terminal —
    # only a status whose value IS a terminal marker (optionally "on/to <where>")
    # counts. Otherwise a live anchor gets de-ranked to the wrong cursor and offered
    # a rename that would permanently stop its injection (state loss).
    import anchor_inject as ai

    assert not ai.is_content_terminal(
        '# Cursor\nStatus: complete the migration and verify parity\n'
    )
    assert not ai.is_content_terminal(
        '# Cursor\nStatus: landed the auth refactor to main, now docs\n'
    )
    assert not ai.is_content_terminal('# Cursor\nStatus: done with phase 1, starting phase 2\n')


def test_landed_on_main_marker_is_terminal():
    # The close markers still count (guard against over-narrowing the predicate).
    import anchor_inject as ai

    assert ai.is_content_terminal('# Done\n**Status:** landed on main\n')
    assert ai.is_content_terminal('**Status:** CLOSED\n')
    assert ai.is_content_terminal('status: done\n')


def test_tail_status_does_not_mark_live_head_terminal():
    # is_content_terminal scans only the HEAD (above the tail marker); a folded
    # "Status: landed phase 2 to main" in the append-only TAIL must not mark an
    # anchor whose HEAD cursor is still active as terminal.
    import anchor_inject as ai

    text = (
        '# Cursor\nnext: run parity check on phase 3\n'
        '<!-- anchor:tail -->\n'
        '# Folded history\n**Status:** landed phase 2 to main\n'
    )
    assert not ai.is_content_terminal(text)


def test_active_anchor_selected_over_newer_terminal():
    # A NEWER anchor that reads as closed-in-content must not shadow an OLDER
    # genuinely-active track. Selection de-ranks content-terminal anchors below live
    # ones — the rename stays the only signal that STOPS injection; this only reorders.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='active.md', body='# Cursor\nACTIVE WORK\n', age_s=3600)
        make_anchor(tmp, name='done.md', body='**Status:** CLOSED\nFINISHED TRACK\n')
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'ACTIVE WORK' in ctx
        assert 'FINISHED TRACK' not in ctx


def test_all_terminal_falls_back_to_newest():
    # When every open anchor reads as terminal, one is still injected (the newest) —
    # de-ranking reorders, it never suppresses the recovery path to zero bytes.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='old-done.md', body='**Status:** CLOSED\nOLD DONE\n', age_s=3600)
        make_anchor(tmp, name='new-done.md', body='**Status:** CLOSED\nNEW DONE\n')
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'NEW DONE' in ctx


def test_terminal_other_anchor_gets_rename_command():
    # A content-terminal-but-unrenamed OTHER anchor is surfaced with the exact
    # remediation command, so the operator clears the accumulation in one paste
    # instead of opening each file (7 stranded across ~8 tracks motivated this).
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='live.md', body='# Cursor\nLIVE\n')
        make_anchor(tmp, name='stale-done.md', body='**Status:** CLOSED\nDEAD\n', age_s=3600)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'LIVE' in ctx
        assert 'mv stale-done.md stale-done.closed.md' in ctx


def test_active_other_anchor_has_no_rename_command():
    # Specificity: only content-terminal others get an mv line — a still-active
    # concurrent track is named (go read it) but never offered for rename.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='primary.md', body='# Cursor\nPRIMARY\n')
        make_anchor(tmp, name='other-active.md', body='# Cursor\nSTILL GOING\n', age_s=3600)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'other-active.md' in ctx
        assert 'mv other-active.md' not in ctx


def test_list_stale_emits_rename_commands():
    # The /anchor close --stale sweep is mechanical — list_stale returns the exact
    # rename commands for content-terminal-but-unrenamed anchors, nothing else.
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='done.md', body='**Status:** CLOSED\ndone\n')
        make_anchor(tmp, name='live.md', body='# Cursor\ngoing\n')
        cmds = ai.list_stale(tmp / '.claude' / 'anchors')
        assert cmds == ['mv done.md done.closed.md']


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
    test_tail_marker_injects_head_only()
    test_oversized_head_still_bounded()
    test_multi_open_anchor_warning()
    test_marker_at_top_falls_back_to_whole_file()
    test_multi_anchor_warning_caps_names()
    test_is_content_terminal_predicate()
    test_status_line_with_trailing_prose_is_live()
    test_landed_on_main_marker_is_terminal()
    test_tail_status_does_not_mark_live_head_terminal()
    test_active_anchor_selected_over_newer_terminal()
    test_all_terminal_falls_back_to_newest()
    test_terminal_other_anchor_gets_rename_command()
    test_active_other_anchor_has_no_rename_command()
    test_list_stale_emits_rename_commands()
    test_emit_failure_logs_failure_event_not_success()
    print('ok: all anchor_inject tests passed')

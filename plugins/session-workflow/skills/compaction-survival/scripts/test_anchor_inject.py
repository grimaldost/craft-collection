"""Tests for anchor_inject.py — the SessionStart(compact|resume|clear|startup)
re-injection hook.

Contract under test (panel-hardened design, memory-suite v2):
- ON by default; SESSION_WORKFLOW_ANCHOR_HOOKS=0 is the documented opt-out;
- silent no-op when no anchor exists (an anchor-less session pays nothing);
- fresh anchor -> stdout JSON with hookSpecificOutput.additionalContext carrying
  the anchor content;
- stale anchor (>24h) -> a POINTER, not the body: path + title + age +
  confirm-to-expand + the close command (never silently suppressed, never
  silently trusted, never 8K chars of dead cursor);
- source=startup injects only when the anchor is recent (crash-restart window);
  compact/resume/clear always evaluate;
- closed anchors (*.closed.md) are never injected;
- oversized anchors are bounded by spending the budget top-down on whole
  sections and NAMING the dropped ones -- document order is the drop order --
  with a byte cut as the fallback when there are no headings to cut on;
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
    # Default ON: env_on leaves the variable unset, which is how a real install
    # runs. env_on=False sets the documented opt-out value.
    env.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
    if not env_on:
        env['SESSION_WORKFLOW_ANCHOR_HOOKS'] = '0'
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


def test_injects_with_no_env_set():
    """The hook ships ON. An install that sets nothing must still re-inject the
    anchor -- the whole point of the rule: a mechanism whose gate nobody sets has
    never run, and the plugin's evidence rests on it."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp)
        proc = run_hook(tmp)
        assert proc.returncode == 0
        assert '<control-anchor>' in proc.stdout


def test_opt_out_silences_it():
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


def test_stale_anchor_gets_pointer_not_body():
    # T22a age gate: a stale anchor (>24h) is never silently dropped, but its
    # FULL BODY no longer rides every session start - the injection degrades to
    # a pointer (path + title + age + confirm-to-expand + close command) so a
    # dead track costs a paragraph, not 8K chars, until someone confirms it.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='old-run.md', age_s=3 * 24 * 3600)
        proc = run_hook(tmp)
        out = json.loads(proc.stdout)
        ctx = out['hookSpecificOutput']['additionalContext']
        assert 'STALE' in ctx.upper()
        assert 'test mission' not in ctx, 'stale anchor body must be withheld'
        assert 'old-run.md' in ctx
        assert 'read the file' in ctx.lower()  # confirm-to-expand instruction
        assert 'mv old-run.md old-run.closed.md' in ctx  # the close command
        assert len(ctx) < 1200, 'pointer tier must stay small'


def test_stale_pointer_carries_title():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, body='# Anchor - big migration wave\ndetails body\n', age_s=48 * 3600)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'big migration wave' in ctx
        assert 'details body' not in ctx


def test_just_under_stale_boundary_injects_full_body():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, age_s=23 * 3600)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'test mission' in ctx
        assert 'next: step 7' in ctx


def test_startup_with_recent_anchor_injects():
    # Crash-restart branch: a fresh process (source=startup) whose newest anchor
    # was updated recently is a restart continuation - inject the full body.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, age_s=600)
        proc = run_hook(tmp, source='startup')
        assert proc.returncode == 0
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'test mission' in ctx


def test_startup_with_old_anchor_is_silent():
    # An ordinary new session days (or even half a day) after the last anchor
    # write is NOT a crash recovery - startup stays silent past the recency
    # window instead of taxing every fresh session in the cwd.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, age_s=12 * 3600)
        proc = run_hook(tmp, source='startup')
        assert proc.returncode == 0
        assert proc.stdout.strip() == ''


def test_startup_window_boundary_is_6h():
    # Pin the exact STARTUP_RECENT_S value, not just the wide bracket: ~10 min
    # inside the window injects, ~10 min outside stays silent.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, age_s=6 * 3600 - 600)
        proc = run_hook(tmp, source='startup')
        assert proc.stdout.strip(), 'just inside the 6h window must inject'
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, age_s=6 * 3600 + 600)
        proc = run_hook(tmp, source='startup')
        assert proc.stdout.strip() == '', 'just outside the 6h window must stay silent'


def test_pointer_tier_survives_cp1252_stdout():
    # The pointer's Title: line is a new UTF-8 surface; it must survive a
    # cp1252 hook-runner stdout exactly as the full tier does.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, body='# Café → não esquecer\ndetails body\n', age_s=48 * 3600)
        proc = run_hook(tmp, extra_env={'PYTHONIOENCODING': 'cp1252'})
        assert proc.returncode == 0
        assert proc.stdout.strip(), 'pointer emitted 0 bytes under cp1252 stdout'
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'Café → não esquecer' in ctx
        assert 'details body' not in ctx


def test_full_tier_read_race_degrades_not_raises():
    # An anchor renamed/deleted between selection and read (a concurrent session
    # closing it) must not skip both the injection and the telemetry: the
    # race-safe read degrades to a path-only context.
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ghost = tmp / '.claude' / 'anchors' / 'gone.md'
        ctx = ai.build_context(ghost, None)
        assert str(ghost) in ctx, 'path-only context must still name the anchor'


def test_clear_source_injects():
    # /clear wipes context in a continuing session - an explicit reset signal,
    # same treatment as compact/resume.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp)
        proc = run_hook(tmp, source='clear')
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'test mission' in ctx


def test_pointer_tier_still_warns_other_open_anchors():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='track-a.md', body='TRACK A\n', age_s=49 * 3600)
        make_anchor(tmp, name='track-b.md', body='TRACK B\n', age_s=48 * 3600)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'other open anchor' in ctx.lower()
        assert 'track-a.md' in ctx


def test_telemetry_carries_tier():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp)
        run_hook(tmp)
        make_anchor(tmp, name='stale.md', age_s=48 * 3600)
        (tmp / '.claude' / 'anchors' / 'run.md').unlink()
        run_hook(tmp)
        log = tmp / '.claude' / 'anchors' / 'log.ndjson'
        tiers = [
            json.loads(line)['tier']
            for line in log.read_text(encoding='utf-8').strip().splitlines()
        ]
        assert tiers == ['full', 'pointer'], tiers


def test_oversized_anchor_drops_whole_sections_and_names_them():
    # An over-budget HEAD is spent top-down on whole sections; what did not fit is
    # named rather than cut mid-sentence. The bound still holds.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, body='# Cursor\nnext: step 7\n# History\n' + ('x' * 50_000))
        proc = run_hook(tmp)
        out = json.loads(proc.stdout)
        ctx = out['hookSpecificOutput']['additionalContext']
        assert len(ctx) < 20_000
        assert 'dropped from injection' in ctx.lower()
        assert 'History' in ctx, 'the dropped section must be named'
        assert 'next: step 7' in ctx, 'the section that fit must survive'


def test_headingless_oversized_anchor_falls_back_to_a_byte_cut():
    # No headings means nothing to cut on. The byte-cut fallback stays: 0 useful
    # bytes on the recovery path is worse than a cut, so it must never be silence.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        anchors = tmp / '.claude' / 'anchors'
        anchors.mkdir(parents=True)
        (anchors / 'run.md').write_text('x' * 50_000, encoding='utf-8')
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
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
    # is still bounded, and still says what it could not carry.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        body = (
            '# Cursor\nnext: step 7\n# Bulk\n' + ('x' * 50_000) + '\n<!-- anchor:tail -->\ntail\n'
        )
        make_anchor(tmp, body=body)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert len(ctx) < 20_000
        assert 'dropped from injection' in ctx.lower()


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


def test_a_design_doc_in_the_anchors_dir_does_not_outrank_a_real_anchor():
    # A 79 KB design document dropped into .claude/anchors/ was selected as the
    # anchor because it was newest, and the injection spent its whole budget on a
    # file with no cursor in it. Shape, not mtime, decides what is an anchor: the
    # `format: anchor/...` frontmatter /anchor already writes, or a cursor section.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='real-run.md', age_s=600)
        anchors = tmp / '.claude' / 'anchors'
        (anchors / 'design.md').write_text(
            '# Service layer design\n\n' + ('prose. ' * 200), encoding='utf-8'
        )
        ctx = json.loads(run_hook(tmp).stdout)['hookSpecificOutput']['additionalContext']
        assert 'next: step 7' in ctx, 'the real anchor must be the one injected'
        assert 'design.md' in ctx
        assert 'not an anchor' in ctx.lower(), 'the stray file must be named as one'


def test_a_cursor_section_alone_makes_a_file_an_anchor():
    # The v0 anchors in the wild carry no `format:` line. A cursor section is the
    # second, sufficient signal - otherwise this predicate would silence exactly
    # the long-running tracks the protocol exists for.
    import anchor_inject as ai

    assert ai.is_anchor_shaped('# Run\n## Cursor\nnext: step 4\n')
    assert ai.is_anchor_shaped('---\nformat: anchor/v1\n---\n# Run\nno cursor yet\n')
    assert not ai.is_anchor_shaped('# Service layer design\n\nprose about the design.\n')


def test_a_lone_stray_file_is_still_injected_rather_than_nothing():
    # Zero useful bytes on the recovery path is the protocol's cardinal failure, so
    # the predicate de-ranks and it never refuses.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        anchors = tmp / '.claude' / 'anchors'
        anchors.mkdir(parents=True)
        (anchors / 'design.md').write_text('# Service layer design\nprose\n', encoding='utf-8')
        proc = run_hook(tmp)
        assert proc.returncode == 0
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'Service layer design' in ctx


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
        os.environ.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
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


def test_head_order_is_the_drop_order():
    # The load-bearing claim of section-aware injection: what an author writes
    # FIRST is what survives a cut. The same two sections in the opposite order
    # must produce the opposite survivor - otherwise "order is the drop order"
    # is a sentence in a skill body and not a property of the mechanism.
    import anchor_inject as ai

    bulk = 'x' * 20_000
    resume_first = '# Resume steps\nrun the thing\n# History\n' + bulk + '\n'
    history_first = '# History\n' + bulk + '\n# Resume steps\nrun the thing\n'

    fit = ai.fit_head(resume_first)
    assert 'run the thing' in fit.text
    assert fit.dropped == ['History']
    assert fit.byte_cut is False, 'a clean section boundary means no byte cut'

    # Same two sections, opposite order, opposite survivor. The first section
    # alone overruns here, so the byte-cut floor applies -- but the section
    # beyond it is still named rather than lost silently.
    fit = ai.fit_head(history_first)
    assert 'run the thing' not in fit.text, 'a late section must not survive an early overrun'
    assert fit.dropped == ['Resume steps']
    assert fit.byte_cut is True


def test_the_cursor_is_reserved_before_the_budget_is_spent():
    # The failure this reserve exists for, measured on four separate nights AFTER
    # the survival-order doctrine shipped: an author who obeys the order still puts
    # a standing-directives block above the cursor, the budget is spent on it, and
    # the injection ends "[dropped ...: Cursor]" - the one section a resuming
    # session cannot do without. Order remains the drop order for everything else.
    import anchor_inject as ai

    head = (
        '# Standing directives\n'
        + ('x' * 20_000)
        + '\n# Cursor\nnext: verify the probe, then run wave 12\n# History\nold\n'
    )
    fit = ai.fit_head(head)
    assert 'run wave 12' in fit.text, 'the cursor must survive a cut it did not cause'
    assert fit.cursor_reserved == 'Cursor'
    assert 'Cursor' not in fit.dropped
    assert 'Standing directives' in fit.dropped
    assert len(fit.text) <= ai.MAX_CONTEXT_CHARS


def test_a_reserved_cursor_keeps_its_document_position():
    # The reserve changes what survives, not where it appears: a reader whose HEAD
    # is re-assembled out of order cannot tell the anchor from a summary of it.
    import anchor_inject as ai

    head = '# Mission\nship it\n# Bulk\n' + ('x' * 20_000) + '\n# Cursor\nnext: step 7\n'
    fit = ai.fit_head(head)
    assert fit.text.index('ship it') < fit.text.index('next: step 7')
    assert fit.dropped == ['Bulk']


def test_the_drop_line_says_the_cursor_was_reserved():
    # A drop manifest that does not say the cursor was held back reads exactly like
    # the old one, and the operator learned to distrust it.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(
            tmp,
            body='# Standing directives\n' + ('x' * 20_000) + '\n# Cursor\nnext: step 7\n',
        )
        ctx = json.loads(run_hook(tmp).stdout)['hookSpecificOutput']['additionalContext']
        assert 'next: step 7' in ctx
        assert 'cursor reserved' in ctx.lower()


def test_a_cursor_that_alone_overruns_is_kept_and_cut_not_dropped():
    # Degradation floor: a bloated cursor still beats no cursor. Everything else is
    # named as dropped rather than lost silently.
    import anchor_inject as ai

    head = '# Mission\nship it\n# Cursor\nnext: ' + ('y' * 20_000) + '\n# History\nold\n'
    fit = ai.fit_head(head)
    assert 'next: yyy' in fit.text
    assert fit.byte_cut is True
    assert fit.cursor_reserved == 'Cursor'
    assert set(fit.dropped) == {'Mission', 'History'}
    assert len(fit.text) <= ai.MAX_CONTEXT_CHARS


def test_a_head_with_no_cursor_section_still_spends_top_down():
    # No cursor to reserve is the old behaviour exactly, and the drop line must not
    # claim a reserve that did not happen.
    import anchor_inject as ai

    fit = ai.fit_head('# A\nkeep me\n# Big\n' + ('x' * 20_000) + '\n')
    assert 'keep me' in fit.text
    assert fit.dropped == ['Big']
    assert fit.cursor_reserved == ''


def _head_fit(*args):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), '--head-fit', *args],
        capture_output=True,
        encoding='utf-8',
        env=env,
        timeout=30,
    )


def test_head_fit_reports_the_number_the_author_was_counting_by_hand():
    # The authoring half of the same failure: the hook computes this fit on every
    # injection and the author could not ask for it, so a byte counter was
    # hand-written three times in one session and a head still shipped 118 bytes
    # over budget. Bytes, budget and overrun all come from the mechanism.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        anchor = make_anchor(
            tmp,
            body='# Standing directives\n'
            + ('x' * 20_000)
            + '\n# Cursor\nnext: step 7\n# History\nold\n',
        )
        proc = _head_fit(str(anchor))
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout
        assert '8000' in out, 'the budget must be printed, not assumed'
        assert 'OVER' in out.upper()
        assert 'Standing directives' in out, 'a section that would drop must be named'
        assert 'History' in out
        assert 'Cursor' in out, 'the reserved cursor must be named'


def test_head_fit_on_an_anchor_that_fits_says_so_and_drops_nothing():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        anchor = make_anchor(tmp)
        proc = _head_fit(str(anchor))
        assert proc.returncode == 0
        assert 'headroom' in proc.stdout.lower()
        assert 'OVER' not in proc.stdout.upper()


def test_head_fit_measures_the_head_not_the_whole_file():
    # The TAIL stays on disk, so counting the file would tell the author to shrink
    # something the injection never carried.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        anchor = make_anchor(
            tmp, body='# Cursor\nnext: step 7\n<!-- anchor:tail -->\n' + ('z' * 30_000)
        )
        proc = _head_fit(str(anchor))
        assert proc.returncode == 0
        assert 'headroom' in proc.stdout.lower(), 'the 30K tail must not count against the head'


def test_head_fit_names_the_cursor_of_a_head_that_fits():
    # `fit_head` returns early on a head within budget, with nothing reserved,
    # and the report used to read that empty reservation as "this HEAD names no
    # cursor" - a false statement about the anchor on the common, in-budget case
    # (2026-09-17 report: an author went reading the source to check a heading
    # that was fine).
    with tempfile.TemporaryDirectory() as d:
        proc = _head_fit(str(make_anchor(Path(d))))
        assert proc.returncode == 0, proc.stderr
        assert 'names no cursor' not in proc.stdout, proc.stdout
        cursor_line = next(ln for ln in proc.stdout.splitlines() if ln.startswith('cursor'))
        assert 'Cursor' in cursor_line, cursor_line
        assert 'fits' in cursor_line, 'say why nothing was reserved: ' + cursor_line


def test_head_fit_does_not_claim_a_fit_for_a_lone_cursor_over_budget():
    # A HEAD that is one cursor section and nothing else has no other section to
    # drop, so `fit_head` cuts it without reserving anything. The report must name
    # the cursor without saying the head fits.
    with tempfile.TemporaryDirectory() as d:
        anchor = Path(d) / 'run.md'
        anchor.write_text('# Cursor\nnext: step 7\n' + 'x' * 9_000 + '\n', encoding='utf-8')
        proc = _head_fit(str(anchor))
        assert proc.returncode == 0, proc.stderr
        cursor_line = next(ln for ln in proc.stdout.splitlines() if ln.startswith('cursor'))
        assert 'Cursor' in cursor_line, cursor_line
        assert 'fits' not in cursor_line, cursor_line
        assert 'OVER' in proc.stdout


def test_head_fit_says_no_cursor_only_when_the_head_has_none():
    with tempfile.TemporaryDirectory() as d:
        anchor = make_anchor(Path(d), body='# Mission\ntest mission\n# Plan\nsteps\n')
        proc = _head_fit(str(anchor))
        assert proc.returncode == 0, proc.stderr
        assert 'names no cursor' in proc.stdout, proc.stdout


def test_head_fit_reports_the_unit_the_budget_is_enforced_in():
    # The budget is enforced as len() over a str - characters - and the report
    # labelled the same figure "bytes". On a non-ASCII anchor the two differ, and
    # near the budget the difference decides whether the author trims.
    with tempfile.TemporaryDirectory() as d:
        anchor = make_anchor(
            Path(d),
            body='# Missao\n' + 'revisao da configuracao ' * 3 + 'ção' * 40 + '\n'
            '# Cursor\nnext: step 7\n',
        )
        head = anchor.read_text(encoding='utf-8')  # marker-less: the head is the file
        assert len(head) != len(head.encode('utf-8')), 'fixture must tell the units apart'
        proc = _head_fit(str(anchor))
        assert proc.returncode == 0, proc.stderr
        assert f'head: {len(head)} chars / budget 8000 chars' in proc.stdout, proc.stdout
        assert 'bytes' not in proc.stdout


def test_head_fit_refuses_a_path_that_is_not_there_rather_than_printing_a_clean_bill():
    with tempfile.TemporaryDirectory() as d:
        proc = _head_fit(str(Path(d) / 'nope.md'))
        assert proc.returncode == 2
        assert proc.stdout.strip() == '', 'a missing anchor must not render as a measurement'
    assert _head_fit().returncode == 2


def test_everything_after_the_first_overrun_is_dropped():
    # Order is a priority, not a packing problem: a small section that happens to
    # sit after a big one must not sneak in ahead of it.
    import anchor_inject as ai

    head = '# A\nkeep me\n# Big\n' + ('x' * 20_000) + '\n# Tiny\nlate\n'
    fit = ai.fit_head(head)
    assert 'keep me' in fit.text
    assert 'late' not in fit.text
    assert fit.dropped == ['Big', 'Tiny']


def test_headings_inside_fenced_code_are_not_section_boundaries():
    # An anchor that pastes a shell transcript would otherwise be shredded at
    # every '#' comment, and the dropped-section names would be nonsense.
    import anchor_inject as ai

    head = '# Cursor\nnext\n```sh\n# not a heading\necho hi\n```\n# Real\nyes\n'
    names = [name for name, _ in ai.split_sections(head)]
    assert names == ['Cursor', 'Real']


def test_split_sections_is_lossless():
    import anchor_inject as ai

    head = 'preamble\n# One\na\n# Two\nb'
    assert '\n'.join(block for _, block in ai.split_sections(head)) == head


def test_stale_pointer_carries_the_cursor_it_asserts():
    # A pointer showing only path/title/age cannot be checked against reality.
    # The cursor can: a four-day-old file claiming "Phase 1 IN PROGRESS" is
    # exactly the case that shipped a wrong cursor nobody surfaced.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(
            tmp,
            name='dormant.md',
            body='# Remodel\n# Cursor\nPhase 1 IN PROGRESS - workflow wf_aed2f9b2\n',
            age_s=96 * 3600,
        )
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'Phase 1 IN PROGRESS' in ctx
        assert 'wf_aed2f9b2' in ctx
        assert len(ctx) < 1200, 'pointer tier must stay small even with the cursor'


def test_pointer_without_a_cursor_section_still_emits():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='old.md', body='# Just a title\nbody\n', age_s=48 * 3600)
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'STALE' in ctx.upper()
        assert 'Cursor it still asserts' not in ctx


def test_list_dormant_names_untouched_active_anchors():
    # list_stale keys on content that reads as done; an anchor abandoned
    # mid-cursor never says so, which is why it needs its own reading.
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(
            tmp,
            name='abandoned.md',
            body='# Remodel wave\n# Cursor\nPhase 1 IN PROGRESS\n',
            age_s=96 * 3600,
        )
        lines = ai.list_dormant(tmp / '.claude' / 'anchors')
        assert len(lines) == 1
        assert 'abandoned.md' in lines[0]
        assert '96h' in lines[0]
        assert 'Remodel wave' in lines[0]
        assert 'Phase 1 IN PROGRESS' in lines[0]
        assert ai.list_stale(tmp / '.claude' / 'anchors') == [], (
            'the sweep that already ships must provably NOT reach this case'
        )


def test_list_dormant_skips_fresh_and_content_terminal_anchors():
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='fresh.md', body='# Cursor\ngoing\n')
        make_anchor(tmp, name='done.md', body='**Status:** CLOSED\nfinished\n', age_s=96 * 3600)
        assert ai.list_dormant(tmp / '.claude' / 'anchors') == []


def test_sweeps_survive_a_cp1252_stdout():
    # Both sweep arms print anchor CONTENT -- titles and cursors -- and campaign
    # anchors essentially always carry arrows and accented prose. main() forces
    # UTF-8 at that seam, but the CLI arms exit before main() ever runs, so an
    # arrow in a cursor killed --list-dormant with a traceback on a cp1252
    # console. Both arms are asserted, so neither regresses alone.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(
            tmp,
            name='acentuado.md',
            body='# Remodelação — fase 2\n# Cursor\npróximo → passo\n',
            age_s=400 * 3600,
        )
        make_anchor(tmp, name='done.md', body='**Status:** CLOSED\npronto\n')
        for arm in ('--list-dormant', '--list-stale'):
            env = dict(os.environ)
            env['PYTHONIOENCODING'] = 'cp1252'
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [sys.executable, str(SCRIPT), arm, str(tmp / '.claude' / 'anchors')],
                capture_output=True,
                env=env,
                timeout=30,
            )
            assert proc.returncode == 0, f'{arm} died on a cp1252 stdout: {proc.stderr[-300:]}'
        env = dict(os.environ)
        env['PYTHONIOENCODING'] = 'cp1252'
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(SCRIPT), '--list-dormant', str(tmp / '.claude' / 'anchors')],
            capture_output=True,
            env=env,
            timeout=30,
        )
        assert 'passo' in proc.stdout.decode('utf-8'), 'the cursor must survive the seam intact'


if __name__ == '__main__':
    test_injects_with_no_env_set()
    test_opt_out_silences_it()
    test_silent_when_no_anchor()
    test_fresh_anchor_injected()
    test_closed_anchor_ignored()
    test_stale_anchor_gets_pointer_not_body()
    test_stale_pointer_carries_title()
    test_just_under_stale_boundary_injects_full_body()
    test_startup_with_recent_anchor_injects()
    test_startup_with_old_anchor_is_silent()
    test_startup_window_boundary_is_6h()
    test_pointer_tier_survives_cp1252_stdout()
    test_full_tier_read_race_degrades_not_raises()
    test_clear_source_injects()
    test_pointer_tier_still_warns_other_open_anchors()
    test_telemetry_carries_tier()
    test_oversized_anchor_drops_whole_sections_and_names_them()
    test_headingless_oversized_anchor_falls_back_to_a_byte_cut()
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
    test_a_design_doc_in_the_anchors_dir_does_not_outrank_a_real_anchor()
    test_a_cursor_section_alone_makes_a_file_an_anchor()
    test_a_lone_stray_file_is_still_injected_rather_than_nothing()
    test_list_stale_emits_rename_commands()
    test_emit_failure_logs_failure_event_not_success()
    test_head_order_is_the_drop_order()
    test_the_cursor_is_reserved_before_the_budget_is_spent()
    test_a_reserved_cursor_keeps_its_document_position()
    test_the_drop_line_says_the_cursor_was_reserved()
    test_a_cursor_that_alone_overruns_is_kept_and_cut_not_dropped()
    test_a_head_with_no_cursor_section_still_spends_top_down()
    test_head_fit_reports_the_number_the_author_was_counting_by_hand()
    test_head_fit_on_an_anchor_that_fits_says_so_and_drops_nothing()
    test_head_fit_measures_the_head_not_the_whole_file()
    test_head_fit_names_the_cursor_of_a_head_that_fits()
    test_head_fit_does_not_claim_a_fit_for_a_lone_cursor_over_budget()
    test_head_fit_says_no_cursor_only_when_the_head_has_none()
    test_head_fit_reports_the_unit_the_budget_is_enforced_in()
    test_head_fit_refuses_a_path_that_is_not_there_rather_than_printing_a_clean_bill()
    test_everything_after_the_first_overrun_is_dropped()
    test_headings_inside_fenced_code_are_not_section_boundaries()
    test_split_sections_is_lossless()
    test_stale_pointer_carries_the_cursor_it_asserts()
    test_pointer_without_a_cursor_section_still_emits()
    test_list_dormant_names_untouched_active_anchors()
    test_list_dormant_skips_fresh_and_content_terminal_anchors()
    test_sweeps_survive_a_cp1252_stdout()
    print('ok: all anchor_inject tests passed')

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
    cwd: Path,
    env_on: bool = True,
    source: str = 'compact',
    extra_env: dict | None = None,
    transcript=None,
):
    env = dict(os.environ)
    # Default ON: env_on leaves the variable unset, which is how a real install
    # runs. env_on=False sets the documented opt-out value.
    env.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
    if not env_on:
        env['SESSION_WORKFLOW_ANCHOR_HOOKS'] = '0'
    if extra_env:
        env.update(extra_env)
    fields = {
        'hook_event_name': 'SessionStart',
        'source': source,
        'session_id': 'test-session',
        'cwd': str(cwd),
    }
    if transcript is not None:
        # Any type on purpose: a non-string transcript_path is one of the cases.
        fields['transcript_path'] = str(transcript) if isinstance(transcript, Path) else transcript
    payload = json.dumps(fields)
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
    extra_frontmatter: str = '',
):
    anchors = base / '.claude' / 'anchors'
    anchors.mkdir(parents=True, exist_ok=True)
    f = anchors / name
    f.write_text(
        '---\nformat: anchor/v0\nstep: 7\n' + extra_frontmatter + '---\n' + body, encoding='utf-8'
    )
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


# -- parked anchors: `parked: <what it waits on>` in the frontmatter -------------

PARKED_AGE_H = 466
WAITS_ON = 'vendor sign-off on the schema change'
PARKED_BODY = '# Schema rollout\n# Cursor\nPhase 2 blocked until the vendor answers\n'


def make_parked(base: Path, name: str = 'schema-rollout.md', age_h: int = 0, waits=WAITS_ON):
    return make_anchor(
        base,
        name=name,
        body=PARKED_BODY,
        age_s=age_h * 3600,
        extra_frontmatter=f'parked: {waits}\n',
    )


def test_parked_reason_reads_the_frontmatter_field():
    import anchor_inject as ai

    text = f'---\nformat: anchor/v1\nparked: {WAITS_ON}\nstep: 3\n---\n{PARKED_BODY}'
    assert ai.parked_reason(text) == WAITS_ON


def test_parked_reason_is_empty_when_the_field_is_absent_or_blank():
    import anchor_inject as ai

    assert ai.parked_reason('---\nformat: anchor/v1\nstep: 3\n---\n' + PARKED_BODY) == ''
    assert ai.parked_reason('---\nformat: anchor/v1\nparked:\n---\n' + PARKED_BODY) == ''
    assert ai.parked_reason(PARKED_BODY) == ''


def test_parked_reason_ignores_a_parked_line_in_the_tail_or_the_body():
    import anchor_inject as ai

    fm = '---\nformat: anchor/v1\nstep: 3\n---\n'
    in_body = fm + '# Cursor\nparked: a note about another track\n'
    in_tail = fm + PARKED_BODY + '<!-- anchor:tail -->\nparked: folded decision text\n'
    no_frontmatter = 'parked: not frontmatter at all\n' + PARKED_BODY
    assert ai.parked_reason(in_body) == ''
    assert ai.parked_reason(in_tail) == ''
    assert ai.parked_reason(no_frontmatter) == ''


def test_a_parked_anchor_lists_under_the_parked_heading_and_not_as_dormant():
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_parked(tmp, age_h=PARKED_AGE_H)
        make_anchor(
            tmp,
            name='abandoned.md',
            body='# Remodel wave\n# Cursor\nPhase 1 IN PROGRESS\n',
            age_s=96 * 3600,
        )
        anchors = tmp / '.claude' / 'anchors'
        lines = ai.list_dormant(anchors)
        dormant = [ln for ln in lines if ln.startswith('abandoned.md')]
        assert len(dormant) == 1, lines
        assert not any(ln.startswith('schema-rollout.md') for ln in lines), (
            'a parked anchor must not read as dormant: the sweep would offer to close it'
        )
        assert 'parked:' in lines, lines
        parked = lines[lines.index('parked:') + 1 :]
        assert len(parked) == 1, lines
        for part in ('schema-rollout.md', f'{PARKED_AGE_H}h', WAITS_ON, 'Phase 2 blocked'):
            assert part in parked[0], (part, parked[0])
        assert lines.index('parked:') > lines.index(dormant[0]), 'dormant lines come first'

        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(SCRIPT), '--list-dormant', str(anchors)],
            capture_output=True,
            encoding='utf-8',
            timeout=30,
        )
        assert proc.returncode == 0
        assert 'parked:' in proc.stdout.splitlines()


def test_a_fresh_parked_anchor_is_still_listed_as_parked():
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_parked(tmp)
        lines = ai.list_dormant(tmp / '.claude' / 'anchors')
        assert lines[0] == 'parked:' and WAITS_ON in lines[1], lines


def test_a_parked_anchor_that_is_the_only_open_one_injects_the_short_block():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        f = make_parked(tmp)
        proc = run_hook(tmp)
        assert proc.returncode == 0
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert str(f) in ctx
        assert f'parked: {WAITS_ON}' in ctx
        assert 'remove the `parked:` line' in ctx, 'the block must say how to un-park'
        assert f'mv {f.name} {f.stem}.closed.md' in ctx, 'and how to close instead'
        assert 'Phase 2 blocked' not in ctx, 'the HEAD is withheld for a parked anchor'
        assert 'format: anchor/' not in ctx
        assert len(ctx) < 700, f'one short block, got {len(ctx)} chars'
        log = (tmp / '.claude' / 'anchors' / 'log.ndjson').read_text(encoding='utf-8')
        assert json.loads(log.splitlines()[-1])['tier'] == 'parked'


def test_a_parked_anchor_beside_a_live_one_injects_the_live_one_and_names_the_parked():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, name='live.md', body='# Cursor\nlive cursor text\n', age_s=3600)
        make_parked(tmp)  # newer than the live one, so recency alone would pick it
        proc = run_hook(tmp)
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert 'live cursor text' in ctx
        assert 'Phase 2 blocked' not in ctx
        assert 'schema-rollout.md' in ctx
        assert f'parked: {WAITS_ON}' in ctx


def test_select_anchor_ranks_parked_below_live_and_above_content_terminal():
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        done = make_anchor(tmp, name='done.md', body='**Status:** CLOSED\nfinished\n')
        parked = make_parked(tmp)
        live = make_anchor(tmp, name='live.md', body='# Cursor\nlive\n', age_s=48 * 3600)
        newest_first = sorted([done, parked, live], key=lambda p: -p.stat().st_mtime)
        primary, _ = ai.select_anchor(newest_first)
        assert primary == live
        primary, _ = ai.select_anchor([a for a in newest_first if a != live])
        assert primary == parked, 'parked outranks a content-terminal anchor'
        primary, _ = ai.select_anchor([parked])
        assert primary == parked, 'the only anchor is still selected'


GOLDEN_CONTEXT_WITH_OTHERS = (
    '<control-anchor>\n'
    'A control anchor for this project exists at {DIR}/run.md (compaction-survival protocol). '
    'Re-read it before acting: verify the real state (git log, files on disk), then continue '
    'from its cursor. Treat it as the source of truth for run state over any summary above.\n'
    'WARNING - 3 other open anchor(s) in this dir: old-track.md, done.md, design.md. '
    "Concurrent tracks share this cwd; if this anchor is not your track's, read the right one "
    'before acting. 1 of them read as "not an anchor" (no format: anchor/... line and no cursor '
    'section): design.md. 1 read as closed in-content but were never renamed; close each: '
    'mv done.md done.closed.md\n'
    '---\n---\nformat: anchor/v0\nstep: 7\n---\n# Mission\nship the thing\n# Cursor\n'
    'next: step 7\n# Notes\nsome notes\n'
    '[anchor tail (decisions log / resolved history) on disk - read the file if needed]\n'
    '</control-anchor>'
)
GOLDEN_CONTEXT_ALONE = (
    '<control-anchor>\n'
    'A control anchor for this project exists at {DIR}/run.md (compaction-survival protocol). '
    'Re-read it before acting: verify the real state (git log, files on disk), then continue '
    'from its cursor. Treat it as the source of truth for run state over any summary above.\n'
    '---\n---\nformat: anchor/v0\nstep: 7\n---\n# Mission\nship the thing\n# Cursor\n'
    'next: step 7\n# Notes\nsome notes\n'
    '[anchor tail (decisions log / resolved history) on disk - read the file if needed]\n'
    '</control-anchor>'
)
GOLDEN_POINTER_WITH_OTHERS = (
    '<control-anchor>\n'
    'A control anchor exists at {DIR}/old-track.md but is STALE: last updated ~100h ago, '
    'so its body is withheld to spare context.\n'
    'Title: Remodel wave\n'
    'If you are continuing that track, read the file now - it is the source of truth for its '
    'run state. If the track is finished, close it: mv old-track.md old-track.closed.md\n'
    'Cursor it still asserts: Phase 1 IN PROGRESS\n'
    'WARNING - 2 other open anchor(s) in this dir: run.md, done.md. Concurrent tracks share '
    "this cwd; if this anchor is not your track's, read the right one before acting. "
    '1 read as closed in-content but were never renamed; close each: '
    'mv done.md done.closed.md\n'
    '</control-anchor>'
)
GOLDEN_POINTER_ALONE = (
    '<control-anchor>\n'
    'A control anchor exists at {DIR}/old-track.md but is STALE: last updated ~100h ago, '
    'so its body is withheld to spare context.\n'
    'Title: Remodel wave\n'
    'If you are continuing that track, read the file now - it is the source of truth for its '
    'run state. If the track is finished, close it: mv old-track.md old-track.closed.md\n'
    'Cursor it still asserts: Phase 1 IN PROGRESS\n'
    '</control-anchor>'
)
GOLDEN_DORMANT = ['old-track.md  96h  Remodel wave  | cursor: Phase 1 IN PROGRESS']


def test_without_a_parked_field_every_output_is_byte_identical_to_the_golden():
    """Goldens captured from the code as it was before the parked field existed."""
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        run = make_anchor(
            tmp,
            name='run.md',
            body=(
                '# Mission\nship the thing\n# Cursor\nnext: step 7\n# Notes\nsome notes\n'
                '<!-- anchor:tail -->\nlog line\n'
            ),
        )
        old = make_anchor(
            tmp,
            name='old-track.md',
            body='# Remodel wave\n# Cursor\nPhase 1 IN PROGRESS\n',
            age_s=96 * 3600,
        )
        done = make_anchor(
            tmp, name='done.md', body='**Status:** CLOSED\nfinished\n', age_s=96 * 3600
        )
        anchors = run.parent
        design = anchors / 'design.md'
        design.write_text('just a design doc\n', encoding='utf-8')

        def scrub(s: str) -> str:
            return s.replace(str(anchors) + os.sep, '{DIR}/')

        assert scrub(ai.build_context(run, [old, done, design])) == GOLDEN_CONTEXT_WITH_OTHERS
        assert scrub(ai.build_context(run)) == GOLDEN_CONTEXT_ALONE
        assert scrub(ai.build_pointer(old, 100 * 3600, [run, done])) == GOLDEN_POINTER_WITH_OTHERS
        assert scrub(ai.build_pointer(old, 100 * 3600)) == GOLDEN_POINTER_ALONE
        assert ai.list_dormant(anchors) == GOLDEN_DORMANT


STARTUP_SENTENCES = (
    'If this session is that run restarting, re-read it and continue from its cursor. '
    'If you were started for a different task (for example as a subprocess of another '
    'tool), ignore it and do not act on its cursor.'
)


def _fixture_context(source: str) -> str:
    """build_context(run, source=...) for the golden fixture anchor, directory scrubbed."""
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        run = make_anchor(
            Path(d),
            name='run.md',
            body=(
                '# Mission\nship the thing\n# Cursor\nnext: step 7\n# Notes\nsome notes\n'
                '<!-- anchor:tail -->\nlog line\n'
            ),
        )
        return ai.build_context(run, source=source).replace(str(run.parent) + os.sep, '{DIR}/')


def test_compact_resume_clear_and_unknown_sources_keep_the_golden_header():
    """Only source=startup changes the header. The other sources, and a missing
    source, give the string captured before the startup branch existed."""
    for source in ('compact', 'resume', 'clear', ''):
        assert _fixture_context(source) == GOLDEN_CONTEXT_ALONE, source


def test_startup_header_is_conditional_and_drops_the_source_of_truth_claim():
    out = _fixture_context('startup')
    assert STARTUP_SENTENCES in out
    assert STARTUP_SENTENCES.isascii()
    assert 'Treat it as the source of truth' not in out
    assert 'Re-read it before acting' not in out
    assert out.startswith(
        '<control-anchor>\nA control anchor for this project exists at {DIR}/run.md '
        '(compaction-survival protocol). '
    )
    # Only the header sentence changed: everything after the rule is the golden's.
    assert out.split('\n---\n', 1)[1] == GOLDEN_CONTEXT_ALONE.split('\n---\n', 1)[1]


def test_startup_hook_run_with_a_recent_anchor_gets_the_conditional_header():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_anchor(tmp, age_s=600)
        proc = run_hook(tmp, source='startup')
        ctx = json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']
        assert STARTUP_SENTENCES in ctx
        assert 'Treat it as the source of truth' not in ctx
        assert 'test mission' in ctx and 'next: step 7' in ctx
    for source in ('compact', 'resume', 'clear'):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            make_anchor(tmp, age_s=600)
            ctx = json.loads(run_hook(tmp, source=source).stdout)['hookSpecificOutput'][
                'additionalContext'
            ]
            assert 'Treat it as the source of truth' in ctx, source
            assert 'ignore it and do not act on its cursor' not in ctx, source


# -- --step: bump `step:` and prepend the cursor entry in one edit ---------------

STEP_ANCHOR = (
    '---\n'
    'format: anchor/v1\n'
    'task: demo\n'
    'step: 4\n'
    '---\n'
    '# Mission\n'
    'ship it\n'
    '\n'
    '## Cursor\n'
    '\n'
    '- Step 4: older entry\n'
    '- Step 3: oldest entry\n'
    '\n'
    '## Invariants\n'
    'keep step: 4 out of this prose\n'
    '<!-- anchor:tail -->\n'
    '## Decisions log\n'
    '- Step 2: tail text\n'
)


def _write_anchor(base: Path, text: str, name: str = 'run.md') -> Path:
    f = base / name
    with open(f, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    return f


def _step_cli(*args, encoding: str = 'utf-8'):
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = encoding
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), '--step', *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=env,
        timeout=30,
    )


def test_step_bumps_the_frontmatter_and_puts_the_new_entry_first_in_the_cursor():
    with tempfile.TemporaryDirectory() as d:
        f = _write_anchor(Path(d), STEP_ANCHOR)
        proc = _step_cli(str(f), 'pushed the branch')
        out = proc.stdout.decode('utf-8')
        assert proc.returncode == 0, proc.stderr
        want = STEP_ANCHOR.replace('step: 4\n---', 'step: 5\n---').replace(
            '## Cursor\n\n', '## Cursor\n\n- Step 5: pushed the branch\n'
        )
        assert f.read_bytes() == want.encode('utf-8')
        assert 'step: 4 -> 5' in out
        assert 'head:' in out and 'budget' in out
        assert out.isascii()


def test_step_text_with_a_windows_path_and_an_arrow_round_trips_byte_exactly():
    # Backslashes and a non-ASCII arrow are the two ways a text-handling shortcut
    # (a regex replacement template, a locale-default write) corrupts an entry.
    text = 'moved C:\\Users\\x\\repo \u2192 D:\\work\\repo\\new'
    with tempfile.TemporaryDirectory() as d:
        f = _write_anchor(Path(d), STEP_ANCHOR)
        proc = _step_cli(str(f), text)
        assert proc.returncode == 0, proc.stderr
        raw = f.read_bytes()
        assert ('- Step 5: ' + text + '\n').encode('utf-8') in raw
        assert raw.decode('utf-8').count('\u2192') == 1


def test_step_survives_a_cp1252_stdout():
    # The confirmation names the anchor; an arrow in the file name would raise
    # under a cp1252 console unless the arm forces UTF-8 before it prints.
    with tempfile.TemporaryDirectory() as d:
        f = _write_anchor(Path(d), STEP_ANCHOR, name='fase \u2192 dois.md')
        proc = _step_cli(str(f), 'proximo \u2192 passo', encoding='cp1252')
        assert proc.returncode == 0, f'--step died on a cp1252 stdout: {proc.stderr[-300:]}'
        assert 'proximo \u2192 passo' in f.read_text(encoding='utf-8')


def test_step_adds_a_missing_field_as_step_1_after_the_format_line():
    with tempfile.TemporaryDirectory() as d:
        text = STEP_ANCHOR.replace('step: 4\n', '').replace(
            '- Step 4: older entry\n- Step 3: oldest entry\n', 'nothing yet\n'
        )
        f = _write_anchor(Path(d), text)
        proc = _step_cli(str(f), 'first entry')
        assert proc.returncode == 0, proc.stderr
        got = f.read_text(encoding='utf-8')
        assert got.startswith('---\nformat: anchor/v1\nstep: 1\ntask: demo\n---\n')
        assert '## Cursor\n\n- Step 1: first entry\nnothing yet\n' in got


def test_step_keeps_the_line_endings_of_the_file():
    with tempfile.TemporaryDirectory() as d:
        crlf = STEP_ANCHOR.replace('\n', '\r\n')
        f = _write_anchor(Path(d), crlf)
        proc = _step_cli(str(f), 'on a windows editor')
        assert proc.returncode == 0, proc.stderr
        raw = f.read_bytes()
        assert b'\r\n- Step 5: on a windows editor\r\n' in raw
        assert raw.count(b'\n') == raw.count(b'\r\n'), 'a bare LF crept into a CRLF file'
        assert b'step: 5\r\n' in raw


def test_step_edits_only_the_head_frontmatter_and_cursor():
    # `step: 4` in the prose and a Cursor-like heading in the TAIL are not targets.
    with tempfile.TemporaryDirectory() as d:
        text = STEP_ANCHOR.replace(
            '## Decisions log\n', '## Decisions log\nstep: 9\n## Cursor\n- Step 2: tail cursor\n'
        )
        f = _write_anchor(Path(d), text)
        assert _step_cli(str(f), 'only the head').returncode == 0
        got = f.read_text(encoding='utf-8')
        assert 'keep step: 4 out of this prose' in got
        assert got.count('step: 9\n') == 1
        assert got.count('- Step 5: only the head') == 1
        assert got.index('- Step 5: only the head') < got.index('<!-- anchor:tail -->')


def test_step_after_a_lagging_field_numbers_past_the_cursor():
    # The field says 3 but the cursor already shows Step 5: the next entry is 6,
    # and the field is repaired in the same edit.
    with tempfile.TemporaryDirectory() as d:
        text = STEP_ANCHOR.replace('step: 4\n', 'step: 3\n').replace(
            '- Step 4: older entry', '- Step 5: older entry'
        )
        f = _write_anchor(Path(d), text)
        assert _step_cli(str(f), 'catch up').returncode == 0
        got = f.read_text(encoding='utf-8')
        assert '\nstep: 6\n' in got
        assert '- Step 6: catch up\n- Step 5: older entry' in got


def test_step_on_an_anchor_without_a_cursor_exits_2_and_leaves_the_file_untouched():
    with tempfile.TemporaryDirectory() as d:
        text = '---\nformat: anchor/v1\nstep: 4\n---\n# Mission\nship it\n'
        f = _write_anchor(Path(d), text)
        before = f.read_bytes()
        proc = _step_cli(str(f), 'nowhere to put it')
        assert proc.returncode == 2
        assert str(f) in proc.stderr.decode('utf-8')
        assert f.read_bytes() == before
        assert [p.name for p in f.parent.iterdir()] == ['run.md'], 'a temp file was left behind'


def test_step_usage_errors_exit_2_and_say_which_path():
    with tempfile.TemporaryDirectory() as d:
        f = _write_anchor(Path(d), STEP_ANCHOR)
        before = f.read_bytes()
        missing = Path(d) / 'nope.md'
        cases = [
            (str(missing), 'text'),  # no such file
            (str(f), '   '),  # empty text
            (str(f), 'two\nlines'),  # an entry is one bullet
            (str(f),),  # no text at all
            (),  # nothing at all
        ]
        for args in cases:
            proc = _step_cli(*args)
            assert proc.returncode == 2, f'{args!r}: exit {proc.returncode}'
            err = proc.stderr.decode('utf-8')
            assert err.startswith('error: --step'), err
        assert str(missing) in _step_cli(str(missing), 'text').stderr.decode('utf-8')
        assert f.read_bytes() == before


def test_step_into_a_cursor_with_no_bullets_still_lands_under_the_heading():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        spaced = '---\nformat: anchor/v1\nstep: 2\n---\n## Cursor\n\nprose, no bullets\n'
        f = _write_anchor(base, spaced)
        assert _step_cli(str(f), 'first bullet').returncode == 0
        assert f.read_text(encoding='utf-8').endswith(
            '## Cursor\n\n- Step 3: first bullet\nprose, no bullets\n'
        )
        bare = '---\nformat: anchor/v1\nstep: 2\n---\n## Cursor'
        g = _write_anchor(base, bare, name='eof.md')
        assert _step_cli(str(g), 'at eof').returncode == 0
        assert g.read_text(encoding='utf-8').endswith('## Cursor\n- Step 3: at eof\n')


def test_step_keeps_a_byte_order_mark():
    with tempfile.TemporaryDirectory() as d:
        f = _write_anchor(Path(d), '﻿' + STEP_ANCHOR)
        assert _step_cli(str(f), 'edited under a bom').returncode == 0
        raw = f.read_bytes()
        assert raw.startswith(b'\xef\xbb\xbf---\n')
        assert b'- Step 5: edited under a bom\n' in raw


def test_newest_step_reads_the_cursor_bullets_only():
    import anchor_inject as ai

    head = '## Cursor\n- Step 5: a\n- Step 4: b\nStep 99 in prose\n## Other\n- Step 70: not here\n'
    assert ai.newest_step(head) == 5
    assert ai.newest_step('## Cursor\n- done: all\n') is None
    assert ai.newest_step('# Mission\n- Step 3: x\n') is None
    assert ai.newest_step('## Cursor\n- **Step 12**: bold label\n') == 12


LAG_LINE = "step: frontmatter says 3, cursor's newest is Step 5 - run --step or correct the field"


def test_head_fit_flags_a_step_field_behind_the_cursor():
    with tempfile.TemporaryDirectory() as d:
        text = STEP_ANCHOR.replace('step: 4\n', 'step: 3\n').replace('Step 4:', 'Step 5:')
        f = _write_anchor(Path(d), text)
        proc = _head_fit(str(f))
        assert proc.returncode == 0
        assert LAG_LINE in proc.stdout.splitlines()


def test_head_fit_is_quiet_when_step_agrees_or_either_side_is_absent():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cases = {
            'agree': STEP_ANCHOR,
            'ahead': STEP_ANCHOR.replace('step: 4\n', 'step: 9\n'),
            'nofield': STEP_ANCHOR.replace('step: 4\n', ''),
            'nobullets': STEP_ANCHOR.replace(
                '- Step 4: older entry\n- Step 3: oldest entry\n', 'idle\n'
            ),
        }
        for name, text in cases.items():
            proc = _head_fit(str(_write_anchor(base, text, name + '.md')))
            assert proc.returncode == 0
            assert 'step: frontmatter' not in proc.stdout, name


# -- the directory the session started in, read from its transcript --------------

START_BODY = '# Mission\nstart-dir mission\n# Cursor\nnext: from the start dir\n'
NOW_BODY = '# Mission\nmoved-to mission\n# Cursor\nnext: from the moved-to dir\n'


def _two_dirs(d: str) -> tuple[Path, Path, Path]:
    """Directory A where the session started, directory B where it runs now, and
    a transcript shaped like a real one: a metadata record with no cwd first, then
    the first message record carrying A, then a later record carrying B."""
    base = Path(d)
    start, now = base / 'start-dir', base / 'moved-to'
    start.mkdir()
    now.mkdir()
    transcript = base / 'session.jsonl'
    records = [
        {'type': 'queue-operation', 'operation': 'enqueue'},
        {'type': 'user', 'cwd': str(start), 'message': {'role': 'user', 'content': 'go'}},
        {'type': 'assistant', 'cwd': str(now), 'message': {'role': 'assistant'}},
    ]
    transcript.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
    return start, now, transcript


def _context(proc) -> str:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']


def _header(ctx: str) -> list[str]:
    """The lines above the anchor body (the whole block for the pointer tier)."""
    return ctx.split('\n---\n', 1)[0].splitlines()


def test_a_moved_session_injects_the_start_directory_anchor_and_names_both_directories():
    # The anchor was armed in A; by the compaction the session runs in B, which
    # holds none. Looking only under B resumed the run with no state at all.
    for source in ('compact', 'resume', 'clear'):
        with tempfile.TemporaryDirectory() as d:
            start, now, transcript = _two_dirs(d)
            make_anchor(start, body=START_BODY)
            ctx = _context(run_hook(now, source=source, transcript=transcript))
            assert 'start-dir mission' in ctx, source
            assert any(str(start) in line and str(now) in line for line in _header(ctx)), ctx
            log = start / '.claude' / 'anchors' / 'log.ndjson'
            assert log.is_file(), 'telemetry goes to the anchors dir that was used'
            assert not (now / '.claude').exists()
            assert json.loads(log.read_text(encoding='utf-8'))['anchor_dir'] == 'start'


def test_a_moved_session_with_no_start_anchor_injects_the_current_one_and_names_both():
    with tempfile.TemporaryDirectory() as d:
        start, now, transcript = _two_dirs(d)
        make_anchor(now, body=NOW_BODY)
        ctx = _context(run_hook(now, transcript=transcript))
        assert 'moved-to mission' in ctx
        assert any(str(start) in line and str(now) in line for line in _header(ctx)), ctx
        log = now / '.claude' / 'anchors' / 'log.ndjson'
        assert json.loads(log.read_text(encoding='utf-8'))['anchor_dir'] == 'cwd'


def test_anchors_in_both_directories_inject_the_start_one_and_warn_about_the_other():
    # The current directory's anchor is the newer file, and still loses: the
    # session's own track is the one armed where it started.
    with tempfile.TemporaryDirectory() as d:
        start, now, transcript = _two_dirs(d)
        make_anchor(start, body=START_BODY, age_s=600)
        make_anchor(now, name='other-track.md', body=NOW_BODY)
        ctx = _context(run_hook(now, transcript=transcript))
        assert 'start-dir mission' in ctx
        assert 'moved-to mission' not in ctx
        warn = [line for line in _header(ctx) if line.startswith('WARNING')]
        assert len(warn) == 1, ctx
        assert 'other-track.md' in warn[0] and str(now) in warn[0], warn[0]


def test_both_directories_reach_the_pointer_and_parked_tiers_too():
    with tempfile.TemporaryDirectory() as d:
        start, now, transcript = _two_dirs(d)
        make_anchor(start, body=START_BODY, age_s=48 * 3600)
        make_anchor(now, name='other-track.md', body=NOW_BODY)
        ctx = _context(run_hook(now, transcript=transcript))
        assert 'STALE' in ctx and str(start) in ctx
        lines = ctx.splitlines()
        assert any(str(start) in line and str(now) in line for line in lines), ctx
        assert any(line.startswith('WARNING') and 'other-track.md' in line for line in lines)
    with tempfile.TemporaryDirectory() as d:
        start, now, transcript = _two_dirs(d)
        make_parked(start)
        ctx = _context(run_hook(now, transcript=transcript))
        assert 'PARKED' in ctx
        assert any(str(start) in line and str(now) in line for line in ctx.splitlines()), ctx


def test_an_unreadable_transcript_keeps_the_payload_cwd_lookup():
    with tempfile.TemporaryDirectory() as d:
        start, now, _ = _two_dirs(d)
        base = Path(d)
        no_cwd = base / 'no-cwd.jsonl'
        no_cwd.write_text('{"type": "queue-operation"}\n{broken\n', encoding='utf-8')
        unreadable = [None, base / 'missing.jsonl', base, no_cwd, '', 42, ['a', 'list']]
        make_anchor(start, body=START_BODY)
        for t in unreadable:
            proc = run_hook(now, transcript=t)
            assert proc.returncode == 0 and proc.stdout.strip() == '', (t, proc.stdout)
        make_anchor(now, body=NOW_BODY)
        today = _context(run_hook(now))
        assert 'moved-to mission' in today
        for t in unreadable:
            assert _context(run_hook(now, transcript=t)) == today, t


def test_startup_reads_only_the_payload_cwd():
    # A fresh process is not a continuation: the transcript is not read at all.
    with tempfile.TemporaryDirectory() as d:
        start, now, transcript = _two_dirs(d)
        make_anchor(start, body=START_BODY)
        proc = run_hook(now, source='startup', transcript=transcript)
        assert proc.returncode == 0 and proc.stdout.strip() == ''
        make_anchor(now, body=NOW_BODY)
        ctx = _context(run_hook(now, source='startup', transcript=transcript))
        assert ctx == _context(run_hook(now, source='startup'))
        assert 'moved-to mission' in ctx and str(start) not in ctx


def test_start_cwd_returns_the_first_cwd_and_skips_garbage():
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        first, later = str(base / 'first'), str(base / 'later')
        lines = [
            '{not json at all',
            '[1, 2]',
            '"a bare string"',
            json.dumps({'type': 'queue-operation'}),
            json.dumps({'cwd': ''}),
            json.dumps({'cwd': 7}),
            json.dumps({'type': 'user', 'cwd': first}),
            json.dumps({'type': 'user', 'cwd': later}),
        ]
        t = base / 't.jsonl'
        t.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        assert ai.start_cwd(str(t)) == Path(first)
        # Invalid UTF-8 on an earlier line is replaced, not raised.
        b = base / 'bytes.jsonl'
        b.write_bytes(b'\xff\xfe{"x": 1}\n' + json.dumps({'cwd': first}).encode() + b'\n')
        assert ai.start_cwd(str(b)) == Path(first)
        for bad in (None, '', 42, str(base / 'missing.jsonl'), str(base), Path(t)):
            assert ai.start_cwd(bad) is None, bad


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
    test_parked_reason_reads_the_frontmatter_field()
    test_parked_reason_is_empty_when_the_field_is_absent_or_blank()
    test_parked_reason_ignores_a_parked_line_in_the_tail_or_the_body()
    test_a_parked_anchor_lists_under_the_parked_heading_and_not_as_dormant()
    test_a_fresh_parked_anchor_is_still_listed_as_parked()
    test_a_parked_anchor_that_is_the_only_open_one_injects_the_short_block()
    test_a_parked_anchor_beside_a_live_one_injects_the_live_one_and_names_the_parked()
    test_select_anchor_ranks_parked_below_live_and_above_content_terminal()
    test_without_a_parked_field_every_output_is_byte_identical_to_the_golden()
    test_compact_resume_clear_and_unknown_sources_keep_the_golden_header()
    test_startup_header_is_conditional_and_drops_the_source_of_truth_claim()
    test_startup_hook_run_with_a_recent_anchor_gets_the_conditional_header()
    test_step_bumps_the_frontmatter_and_puts_the_new_entry_first_in_the_cursor()
    test_step_text_with_a_windows_path_and_an_arrow_round_trips_byte_exactly()
    test_step_survives_a_cp1252_stdout()
    test_step_adds_a_missing_field_as_step_1_after_the_format_line()
    test_step_keeps_the_line_endings_of_the_file()
    test_step_edits_only_the_head_frontmatter_and_cursor()
    test_step_after_a_lagging_field_numbers_past_the_cursor()
    test_step_on_an_anchor_without_a_cursor_exits_2_and_leaves_the_file_untouched()
    test_step_usage_errors_exit_2_and_say_which_path()
    test_step_into_a_cursor_with_no_bullets_still_lands_under_the_heading()
    test_step_keeps_a_byte_order_mark()
    test_newest_step_reads_the_cursor_bullets_only()
    test_head_fit_flags_a_step_field_behind_the_cursor()
    test_head_fit_is_quiet_when_step_agrees_or_either_side_is_absent()
    test_a_moved_session_injects_the_start_directory_anchor_and_names_both_directories()
    test_a_moved_session_with_no_start_anchor_injects_the_current_one_and_names_both()
    test_anchors_in_both_directories_inject_the_start_one_and_warn_about_the_other()
    test_both_directories_reach_the_pointer_and_parked_tiers_too()
    test_an_unreadable_transcript_keeps_the_payload_cwd_lookup()
    test_startup_reads_only_the_payload_cwd()
    test_start_cwd_returns_the_first_cwd_and_skips_garbage()
    print('ok: all anchor_inject tests passed')

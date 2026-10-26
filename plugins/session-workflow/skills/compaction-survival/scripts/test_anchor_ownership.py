"""Tests for anchor ownership in anchor_inject.py (spec 2026-10-25, section 2).

Contract under test:
- the PostToolUse(Write|Edit|MultiEdit) arm records, in
  `.claude/anchors/.owners.json` (filename to session id), the session that last
  wrote each open anchor, replacing the file atomically (temp file and os.replace);
- `--step` runs without a payload and leaves the recorded owner unchanged;
- a `.closed.md` rename drops the entry;
- ownership is a key of `anchor_rank`, after shape, content-terminal and parked and
  before staleness, threaded through `select_anchor` and `resolve_anchors`: at
  SessionStart the payload session's own anchor ranks first even when another is
  newer, and among its own anchors today's order decides;
- when the session owns none of the open anchors, today's ranking and tiers stay
  and one line names the injected anchor's owner and says to ignore it if this
  session is not resuming that track;
- an anchor with no owner record behaves exactly as today, and a directory with no
  `.owners.json` produces byte-identical output to the script before ownership.

Every hook case runs the script in a subprocess fed a real payload.
Stdlib-runnable: `python test_anchor_ownership.py` runs every test and prints `ok:`.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'anchor_inject.py'
sys.path.insert(0, str(HERE))

# The git blob of anchor_inject.py as it was before ownership existed (origin/main
# 3d2c431, 2026-10-25). The byte-identical test runs that exact script beside the
# current one; it lives in history, so it stays reachable after this change merges.
PRE_OWNERSHIP_BLOB = 'da1bf582674869438d8d7e54a726cce792f71b5b'

LIVE_BODY = '# Mission\n{m}\n# Cursor\nnext: {m} next step\n'


def _anchor(base: Path, name: str, mission: str, age_s: int = 0, body: str | None = None) -> Path:
    anchors = base / '.claude' / 'anchors'
    anchors.mkdir(parents=True, exist_ok=True)
    f = anchors / name
    text = body if body is not None else LIVE_BODY.format(m=mission)
    f.write_text('---\nformat: anchor/v1\nstep: 3\n---\n' + text, encoding='utf-8')
    _age(f, age_s)
    return f


def _age(f: Path, age_s: int) -> None:
    if age_s:
        old = time.time() - age_s
        os.utime(f, (old, old))


def _env(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
    env.pop('PYTHONUTF8', None)
    env['PYTHONIOENCODING'] = 'cp1252'  # the Windows hook stdout this must survive
    if extra:
        env.update(extra)
    return env


def _run(args: list[str], stdin: str, script: Path = SCRIPT):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(script), *args],
        input=stdin,
        capture_output=True,
        encoding='utf-8',
        env=_env(),
        timeout=30,
    )


def _session_start(cwd: Path, session: str | None, source: str = 'compact', transcript=None):
    fields = {'hook_event_name': 'SessionStart', 'source': source, 'cwd': str(cwd)}
    if session is not None:
        fields['session_id'] = session
    if transcript is not None:
        fields['transcript_path'] = str(transcript)
    return _run([], json.dumps(fields))


def _post_write(path: Path, session: str | None, tool: str = 'Write'):
    fields = {
        'hook_event_name': 'PostToolUse',
        'tool_name': tool,
        'tool_input': {'file_path': str(path)},
        'cwd': str(path.parent),
    }
    if session is not None:
        fields['session_id'] = session
    return _run(['--post-write'], json.dumps(fields))


def _ctx(proc) -> str:
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip(), 'expected an injection, got no output'
    return json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']


def _owners(anchors: Path) -> dict:
    return json.loads((anchors / '.owners.json').read_text(encoding='utf-8'))


def _owner_lines(ctx: str) -> list[str]:
    return [line for line in ctx.splitlines() if 'last written by session' in line]


def _write_by(path: Path, session: str, age_s: int = 0) -> None:
    """Record `session` as the last writer of `path` the way production does: the
    PostToolUse arm after a Write. Then age the file, since the write is the past."""
    proc = _post_write(path, session)
    assert proc.returncode == 0 and proc.stdout == '', (proc.stdout, proc.stderr)
    _age(path, age_s)


# --- recording -------------------------------------------------------------------


def test_post_write_records_the_last_writer_of_an_open_anchor():
    with tempfile.TemporaryDirectory() as d:
        run = _anchor(Path(d), 'run.md', 'track one')
        proc = _post_write(run, 'sess-A')
        assert proc.returncode == 0 and proc.stdout == '', 'recording is silent'
        assert _owners(run.parent) == {'run.md': 'sess-A'}
        for tool in ('Edit', 'MultiEdit'):
            _post_write(run, f'sess-{tool}', tool=tool)
            assert _owners(run.parent) == {'run.md': f'sess-{tool}'}, tool


def test_post_write_keeps_the_other_entries_and_writes_no_temp_file_behind():
    with tempfile.TemporaryDirectory() as d:
        one = _anchor(Path(d), 'one.md', 'one')
        two = _anchor(Path(d), 'two.md', 'two')
        _post_write(one, 'sess-A')
        _post_write(two, 'sess-B')
        assert _owners(one.parent) == {'one.md': 'sess-A', 'two.md': 'sess-B'}
        leftovers = [p.name for p in one.parent.iterdir() if p.name.endswith('.tmp')]
        assert leftovers == [], leftovers


def test_post_write_without_a_session_id_or_on_a_non_anchor_records_nothing():
    with tempfile.TemporaryDirectory() as d:
        run = _anchor(Path(d), 'run.md', 'track')
        _post_write(run, None)
        assert not (run.parent / '.owners.json').exists()
        closed = run.parent / 'old.closed.md'
        closed.write_text('# old\n', encoding='utf-8')
        _post_write(closed, 'sess-A')
        other = Path(d) / 'notes.md'
        other.write_text('# notes\n', encoding='utf-8')
        _post_write(other, 'sess-A')
        assert not (run.parent / '.owners.json').exists()
        assert not (Path(d) / '.owners.json').exists()


def test_owners_file_is_replaced_atomically_through_os_replace():
    import anchor_inject as ai

    calls = []
    real = ai.os.replace

    def spy(src, dst):
        calls.append((Path(src), Path(dst)))
        return real(src, dst)

    with tempfile.TemporaryDirectory() as d:
        run = _anchor(Path(d), 'run.md', 'track')
        ai.os.replace = spy
        try:
            ai.record_owner(run, 'sess-A')
        finally:
            ai.os.replace = real
        target = run.parent / '.owners.json'
        assert len(calls) == 1, calls
        src, dst = calls[0]
        assert dst == target and src.parent == run.parent and src != target, calls
        assert not src.exists()
        assert _owners(run.parent) == {'run.md': 'sess-A'}


def test_step_leaves_the_recorded_owner_unchanged():
    with tempfile.TemporaryDirectory() as d:
        run = _anchor(Path(d), 'run.md', 'track')
        _write_by(run, 'sess-A')
        before = (run.parent / '.owners.json').read_bytes()
        proc = _run(['--step', str(run), 'did the next thing'], '')
        assert proc.returncode == 0, proc.stderr
        assert 'Step 4: did the next thing' in run.read_text(encoding='utf-8')
        assert (run.parent / '.owners.json').read_bytes() == before


def test_a_closed_rename_drops_the_entry():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        run = _anchor(base, 'run.md', 'finished track')
        live = _anchor(base, 'live.md', 'live track')
        _write_by(run, 'sess-A')
        _write_by(live, 'sess-B')
        run.rename(run.parent / 'run.closed.md')
        _session_start(base, 'sess-C')
        assert _owners(run.parent) == {'live.md': 'sess-B'}


def test_a_closed_rename_is_dropped_at_the_next_anchor_write_too():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        run = _anchor(base, 'run.md', 'finished track')
        live = _anchor(base, 'live.md', 'live track')
        _write_by(run, 'sess-A')
        run.rename(run.parent / 'run.closed.md')
        _write_by(live, 'sess-B')
        assert _owners(run.parent) == {'live.md': 'sess-B'}


# --- ranking ---------------------------------------------------------------------


def test_compact_from_a_session_injects_its_own_anchor_when_the_other_is_newer():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mine = _anchor(base, 'mine.md', 'track of X')
        theirs = _anchor(base, 'theirs.md', 'track of Y')
        _write_by(mine, 'sess-X', age_s=3600)
        _write_by(theirs, 'sess-Y', age_s=60)
        ctx = _ctx(_session_start(base, 'sess-X'))
        assert 'track of X next step' in ctx and 'track of Y next step' not in ctx, ctx
        assert _owner_lines(ctx) == [], 'the session owns what it got: no owner line'
        ctx = _ctx(_session_start(base, 'sess-Y'))
        assert 'track of Y next step' in ctx and 'track of X next step' not in ctx, ctx


def test_ownership_ranks_before_staleness():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mine = _anchor(base, 'mine.md', 'track of X')
        theirs = _anchor(base, 'theirs.md', 'track of Y')
        _write_by(mine, 'sess-X', age_s=48 * 3600)
        _write_by(theirs, 'sess-Y', age_s=60)
        ctx = _ctx(_session_start(base, 'sess-X'))
        assert 'STALE' in ctx and 'mine.md' in ctx.splitlines()[1], ctx


def test_startup_from_a_new_session_gets_todays_injection_plus_the_owner_line():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        older = _anchor(base, 'older.md', 'track of X')
        newer = _anchor(base, 'newer.md', 'track of Y')
        _age(older, 3600)
        _age(newer, 60)
        today = _ctx(_session_start(base, 'sess-NEW', source='startup'))
        _write_by(older, 'sess-X', age_s=3600)
        _write_by(newer, 'sess-Y', age_s=60)
        ctx = _ctx(_session_start(base, 'sess-NEW', source='startup'))
        lines = _owner_lines(ctx)
        assert len(lines) == 1, ctx
        assert 'sess-Y' in lines[0] and 'ignore' in lines[0].lower(), lines[0]
        assert lines[0].isascii()
        rest = [line for line in ctx.splitlines() if line not in lines]
        assert rest == today.splitlines(), (rest, today)


def test_the_owner_line_reaches_the_pointer_and_parked_tiers():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        stale = _anchor(base, 'stale.md', 'old track')
        _write_by(stale, 'sess-Y', age_s=48 * 3600)
        ctx = _ctx(_session_start(base, 'sess-NEW'))
        assert 'STALE' in ctx and len(_owner_lines(ctx)) == 1, ctx
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        parked = _anchor(base, 'parked.md', 'waiting track')
        parked.write_text(
            '---\nformat: anchor/v1\nparked: the review\n---\n# Mission\nm\n# Cursor\nnext\n',
            encoding='utf-8',
        )
        _write_by(parked, 'sess-Y')
        ctx = _ctx(_session_start(base, 'sess-NEW'))
        assert 'PARKED' in ctx and len(_owner_lines(ctx)) == 1, ctx


def test_an_owned_file_that_is_not_anchor_shaped_does_not_beat_an_unowned_live_anchor():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        live = _anchor(base, 'live.md', 'unowned live track', age_s=3600)
        anchors = live.parent
        notes = anchors / 'design.md'
        notes.write_text('# Design notes\nno cursor here\n', encoding='utf-8')
        _write_by(notes, 'sess-X', age_s=60)
        ctx = _ctx(_session_start(base, 'sess-X'))
        assert 'unowned live track next step' in ctx, ctx
        assert 'no cursor here' not in ctx
        assert _owner_lines(ctx) == [], 'the injected anchor has no owner record'


def test_an_owned_finished_or_parked_anchor_does_not_beat_an_unowned_live_one():
    finished = '# Mission\nmine\nStatus: landed\n# Cursor\nnext: nothing\n'
    parked = '# Mission\nmine\n# Cursor\nnext: wait\n'
    for label, body, extra in (('finished', finished, ''), ('parked', parked, 'parked: CI\n')):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            live = _anchor(base, 'live.md', 'unowned live track', age_s=3600)
            own = live.parent / 'own.md'
            own.write_text('---\nformat: anchor/v1\n' + extra + '---\n' + body, encoding='utf-8')
            _write_by(own, 'sess-X', age_s=60)
            ctx = _ctx(_session_start(base, 'sess-X'))
            assert 'unowned live track next step' in ctx, (label, ctx)


def test_among_a_sessions_own_anchors_todays_order_decides():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        older = _anchor(base, 'older.md', 'older own track')
        newer = _anchor(base, 'newer.md', 'newer own track')
        other = _anchor(base, 'other.md', 'track of Y')
        _write_by(older, 'sess-X', age_s=7200)
        _write_by(newer, 'sess-X', age_s=3600)
        _write_by(other, 'sess-Y', age_s=60)
        ctx = _ctx(_session_start(base, 'sess-X'))
        assert 'newer own track next step' in ctx, ctx


def test_anchor_rank_and_select_anchor_take_the_session_id():
    import anchor_inject as ai

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mine = _anchor(base, 'mine.md', 'X')
        theirs = _anchor(base, 'theirs.md', 'Y')
        ai.record_owner(mine, 'sess-X')
        ai.record_owner(theirs, 'sess-Y')
        _age(mine, 3600)
        newest_first = ai.find_open_anchors(mine.parent)
        assert ai.select_anchor(newest_first)[0] == theirs, 'no session: today order'
        assert ai.select_anchor(newest_first, 'sess-X')[0] == mine
        assert ai.anchor_rank(mine, 'sess-X') < ai.anchor_rank(theirs, 'sess-X')
        assert ai.anchor_rank(mine) == ai.anchor_rank(theirs)


# --- a payload cwd that differs from the anchor's directory ----------------------


def _two_dirs(d: str) -> tuple[Path, Path, Path]:
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


def test_an_owned_anchor_in_the_current_directory_beats_an_unowned_start_one():
    # Without ownership the start directory wins a tie between two live anchors.
    # Ownership is a rank key, so the current directory's anchor this session wrote
    # is strictly better and is chosen.
    with tempfile.TemporaryDirectory() as d:
        start, now, transcript = _two_dirs(d)
        _anchor(start, 'start.md', 'unowned start track', age_s=60)
        own = _anchor(now, 'own.md', 'own current track')
        _write_by(own, 'sess-X', age_s=3600)
        ctx = _ctx(_session_start(now, 'sess-X', transcript=transcript))
        assert 'own current track next step' in ctx, ctx
        assert 'unowned start track next step' not in ctx
        ctx = _ctx(_session_start(now, 'sess-OTHER', transcript=transcript))
        assert 'unowned start track next step' in ctx, 'another session: today order'


def test_an_owned_anchor_in_the_start_directory_beats_a_newer_current_one():
    with tempfile.TemporaryDirectory() as d:
        start, now, transcript = _two_dirs(d)
        own = _anchor(start, 'own.md', 'own start track')
        _write_by(own, 'sess-X', age_s=3600)
        theirs = _anchor(now, 'theirs.md', 'current track of Y')
        _write_by(theirs, 'sess-Y', age_s=60)
        ctx = _ctx(_session_start(now, 'sess-X', transcript=transcript))
        assert 'own start track next step' in ctx, ctx
        assert _owner_lines(ctx) == []


def test_startup_from_another_directory_never_reaches_an_owned_anchor():
    # startup reads only the payload cwd: an owned anchor elsewhere is not found.
    with tempfile.TemporaryDirectory() as d:
        start, now, _ = _two_dirs(d)
        own = _anchor(start, 'own.md', 'own start track')
        _write_by(own, 'sess-X', age_s=60)
        proc = _session_start(now, 'sess-X', source='startup')
        assert proc.returncode == 0 and proc.stdout == '', proc.stdout


# --- no owner record behaves as today --------------------------------------------


def _pre_ownership_script(dest: Path) -> Path | None:
    """The script as it was before ownership, from git history; None when git or
    the history is unavailable (a snapshot without .git)."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ['git', '-C', str(HERE), 'cat-file', '-p', PRE_OWNERSHIP_BLOB],  # noqa: S607
            capture_output=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if not k.startswith('GIT_')},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    script = dest / 'anchor_inject_before.py'
    script.write_bytes(proc.stdout)
    return script


def _scenarios(base: Path) -> list[tuple[str, Path, dict]]:
    """Fixture directories covering every tier, the multi-track warning and a moved
    session, with the payload fields to send each."""
    out = []
    one = base / 'full'
    _anchor(one, 'run.md', 'track → accent ê', age_s=60)
    _anchor(one, 'other.md', 'other track', age_s=3600)
    (one / '.claude' / 'anchors' / 'notes.md').write_text('# notes\n', encoding='utf-8')
    out.append(('full', one, {'source': 'compact'}))
    out.append(('startup', one, {'source': 'startup'}))
    two = base / 'pointer'
    _anchor(two, 'old.md', 'old track', age_s=48 * 3600)
    out.append(('pointer', two, {'source': 'resume'}))
    three = base / 'parked'
    p = _anchor(three, 'p.md', 'parked track')
    p.write_text('---\nformat: anchor/v1\nparked: CI\n---\n# Cursor\nwait\n', encoding='utf-8')
    out.append(('parked', three, {'source': 'clear'}))
    moved = base / 'moved'
    moved.mkdir()
    start, now, transcript = _two_dirs(str(moved))
    _anchor(start, 's.md', 'start track', age_s=600)
    _anchor(now, 'n.md', 'now track')
    out.append(('moved', now, {'source': 'compact', 'transcript_path': str(transcript)}))
    return out


def test_no_owners_file_gives_byte_identical_output_to_the_script_before_ownership():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        before = _pre_ownership_script(base)
        if before is None:
            print('skip: the pre-ownership script is not reachable through git here')
            return
        for label, cwd, fields in _scenarios(base):
            for session in ('sess-X', None):
                payload = {'hook_event_name': 'SessionStart', 'cwd': str(cwd), **fields}
                if session:
                    payload['session_id'] = session
                old = _run([], json.dumps(payload), script=before)
                new = _run([], json.dumps(payload))
                assert old.returncode == new.returncode == 0, (label, new.stderr)
                assert old.stdout, (label, 'the fixture must inject something')
                assert new.stdout == old.stdout, (label, old.stdout, new.stdout)
                for anchors in cwd.parent.rglob('anchors'):
                    assert not (anchors / '.owners.json').exists(), label


def test_an_unusable_owners_file_behaves_as_no_owner_record():
    for raw in ('not json', '[1, 2]', '{"run.md": 7}', ''):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _anchor(base, 'run.md', 'newest track', age_s=60)
            _anchor(base, 'other.md', 'older track', age_s=3600)
            today = _ctx(_session_start(base, 'sess-X'))
            (base / '.claude' / 'anchors' / '.owners.json').write_text(raw, encoding='utf-8')
            proc = _session_start(base, 'sess-X')
            assert _ctx(proc) == today, raw


def test_an_anchor_with_no_owner_record_keeps_todays_order_beside_owned_ones():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        unowned = _anchor(base, 'unowned.md', 'unowned newest track')
        owned = _anchor(base, 'owned.md', 'track of Y')
        _write_by(owned, 'sess-Y', age_s=3600)
        _age(unowned, 60)
        ctx = _ctx(_session_start(base, 'sess-NEW'))
        assert 'unowned newest track next step' in ctx, ctx
        assert _owner_lines(ctx) == [], 'no owner record on the injected anchor: no line'


def test_owner_housekeeping_never_raises_into_the_hook():
    # The record is bookkeeping: a failure inside it must not cost the injection
    # (main) or the size warning (post-write) that runs after it.
    import anchor_inject as ai

    def boom(*_args):
        raise RuntimeError('record broke')

    with tempfile.TemporaryDirectory() as d:
        run = _anchor(Path(d), 'run.md', 'track')
        ai.record_owner(run, 'sess-A')
        real = ai._live_entries
        ai._live_entries = boom
        try:
            ai.prune_owners(run.parent)
            ai.record_owner(run, 'sess-B')
        finally:
            ai._live_entries = real
        assert _owners(run.parent) == {'run.md': 'sess-A'}


def test_a_malformed_payload_exits_zero_with_no_output():
    for raw in ('{not json', '[]', '"text"'):
        for args in ([], ['--post-write']):
            proc = _run(args, raw)
            assert proc.returncode == 0 and proc.stdout == '', (args, raw, proc.stdout)


if __name__ == '__main__':
    test_post_write_records_the_last_writer_of_an_open_anchor()
    test_post_write_keeps_the_other_entries_and_writes_no_temp_file_behind()
    test_post_write_without_a_session_id_or_on_a_non_anchor_records_nothing()
    test_owners_file_is_replaced_atomically_through_os_replace()
    test_step_leaves_the_recorded_owner_unchanged()
    test_a_closed_rename_drops_the_entry()
    test_a_closed_rename_is_dropped_at_the_next_anchor_write_too()
    test_compact_from_a_session_injects_its_own_anchor_when_the_other_is_newer()
    test_ownership_ranks_before_staleness()
    test_startup_from_a_new_session_gets_todays_injection_plus_the_owner_line()
    test_the_owner_line_reaches_the_pointer_and_parked_tiers()
    test_an_owned_file_that_is_not_anchor_shaped_does_not_beat_an_unowned_live_anchor()
    test_an_owned_finished_or_parked_anchor_does_not_beat_an_unowned_live_one()
    test_among_a_sessions_own_anchors_todays_order_decides()
    test_anchor_rank_and_select_anchor_take_the_session_id()
    test_an_owned_anchor_in_the_current_directory_beats_an_unowned_start_one()
    test_an_owned_anchor_in_the_start_directory_beats_a_newer_current_one()
    test_startup_from_another_directory_never_reaches_an_owned_anchor()
    test_no_owners_file_gives_byte_identical_output_to_the_script_before_ownership()
    test_an_unusable_owners_file_behaves_as_no_owner_record()
    test_an_anchor_with_no_owner_record_keeps_todays_order_beside_owned_ones()
    test_owner_housekeeping_never_raises_into_the_hook()
    test_a_malformed_payload_exits_zero_with_no_output()
    print('ok: anchor ownership tests passed')

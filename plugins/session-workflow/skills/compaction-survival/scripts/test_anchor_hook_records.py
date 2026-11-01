"""Tests for the records anchor_inject.py leaves (v: 2): every exit of the
SessionStart arm writes exactly one record naming its outcome, session and source,
and the PostToolUse arm writes one `anchor-write` record per write to an open anchor.

Contract under test:
- one record per SessionStart outcome (full, pointer-stale, pointer-owner, parked,
  no-anchors, startup-too-old, bad-payload, error, emit-failed) in the central log
  `anchor-hooks/log.ndjson` under CLAUDE_PLUGIN_DATA, with today's `event`, `tier` and
  `stale`: `anchor-inject` for the four that inject, `anchor-inject-failed` for
  emit-failed, `anchor-inject-skipped` with `tier` and `stale` null for the rest;
- the per-directory log gets the same record only when the anchors directory already
  exists, and the hook never creates one;
- stdout is byte-identical to the script before the records existed, on every path;
- a failed central or per-directory write, and an unreadable plugin.json, change
  neither stdout nor the exit code;
- with SESSION_WORKFLOW_ANCHOR_HOOKS=0 nothing is written.

Every test pins CLAUDE_PLUGIN_DATA to its own temporary folder, in every subprocess
environment and in-process, so no test writes to the inherited or the fallback
location. Session ids stay in `sess-*`, so a reader of real logs can tell test runs apart.
Stdlib-runnable: `python test_anchor_hook_records.py` runs every test and prints `ok:`.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'anchor_inject.py'
sys.path.insert(0, str(HERE))

# The git blob of anchor_inject.py as it was before these records (origin/main
# d134aad, release 0.30.0). The stdout of every case is compared with that script's.
BEFORE_RECORDS_BLOB = '9bbecdd155ab10e1b23dd3637e03130f2e727861'

LIVE = '# Mission\nship it → now\n# Cursor\n- Step 2: next\n'
INJECTED = ('full', 'pointer-stale', 'pointer-owner', 'parked')


def _anchor(cwd: Path, name: str = 'run.md', age_s: int = 0, frontmatter: str = '') -> Path:
    anchors = cwd / '.claude' / 'anchors'
    anchors.mkdir(parents=True, exist_ok=True)
    f = anchors / name
    f.write_text(f'---\nformat: anchor/v1\n{frontmatter}---\n{LIVE}', encoding='utf-8')
    if age_s:
        old = time.time() - age_s
        os.utime(f, (old, old))
    return f


def _env(data: Path, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env['CLAUDE_PLUGIN_DATA'] = str(data)
    env.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
    env['PYTHONIOENCODING'] = 'utf-8'
    if extra:
        env.update(extra)
    return env


def _run(script: Path, stdin: str, data: Path, args=(), extra: dict | None = None):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(script), *args],
        input=stdin,
        capture_output=True,
        encoding='utf-8',
        env=_env(data, extra),
        timeout=30,
    )


def _payload(cwd: Path, session: str = 'sess-rec', source: str = 'compact') -> str:
    return json.dumps(
        {
            'hook_event_name': 'SessionStart',
            'source': source,
            'session_id': session,
            'cwd': str(cwd),
        }
    )


def _central(data: Path) -> list[dict]:
    log = data / 'anchor-hooks' / 'log.ndjson'
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]


def _per_dir(cwd: Path) -> list[dict]:
    log = cwd / '.claude' / 'anchors' / 'log.ndjson'
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]


def _before_script(dest: Path) -> Path | None:
    """The script as it was before the records, from git history; None when git or
    the history is unavailable (a snapshot without .git)."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ['git', '-C', str(HERE), 'cat-file', '-p', BEFORE_RECORDS_BLOB],  # noqa: S607
            capture_output=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if not k.startswith('GIT_')},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    script = dest / 'before' / 'anchor_inject_before.py'
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(proc.stdout)
    return script


def _case(base: Path, stdin: str, cwd: Path, args=(), extra: dict | None = None):
    """Run the old script, then the new one, on one fixture: (old proc or None, the
    per-directory records the old one left, new proc, central records). The two
    runs use separate data folders; only the new script writes the central log."""
    before = _before_script(base)
    old = old_records = None
    if before is not None:
        old = _run(before, stdin, base / 'data-before', args, extra)
        old_records = _per_dir(cwd)
    data = base / 'data'
    new = _run(SCRIPT, stdin, data, args, extra)
    if old is not None:
        assert new.returncode == old.returncode == 0, (old.stderr, new.stderr)
        assert new.stdout == old.stdout, (old.stdout, new.stdout)
    assert new.returncode == 0, new.stderr
    return old, old_records, new, _central(data)


def _one(records: list[dict], outcome: str, session: object, source: object) -> dict:
    assert len(records) == 1, records
    rec = records[0]
    assert rec['v'] == 2, rec
    assert rec['outcome'] == outcome, rec
    assert rec['session'] == session and rec['source'] == source, rec
    if outcome in INJECTED:
        assert rec['event'] == 'anchor-inject', rec
        assert rec['tier'] in ('full', 'pointer', 'parked'), rec
        assert isinstance(rec['stale'], bool), rec
    elif outcome == 'emit-failed':
        assert rec['event'] == 'anchor-inject-failed', rec
    else:
        assert rec['event'] == 'anchor-inject-skipped', rec
        assert rec['tier'] is None and rec['stale'] is None, rec
    for field in (
        'owner',
        'owns_open_anchor',
        'anchor_age_s',
        'head_chars',
        'dropped',
        'cwd',
        'anchors_dir',
        'plugin_version',
        'ts',
    ):
        assert field in rec, (field, rec)
    assert rec['ts'].endswith('+00:00'), rec['ts']
    return rec


def _injected(proc) -> str:
    return json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']


# --- one record per outcome --------------------------------------------------------


def test_full_outcome():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd)
        _, _, new, records = _case(base, _payload(cwd), cwd)
        assert 'ship it → now' in _injected(new)
        rec = _one(records, 'full', 'sess-rec', 'compact')
        assert rec['tier'] == 'full' and rec['stale'] is False
        assert rec['owner'] == '' and rec['owns_open_anchor'] is False
        assert rec['head_chars'] > 0 and rec['dropped'] == 0
        assert rec['anchors_dir'] == str(cwd / '.claude' / 'anchors')
        assert rec['plugin_version'] == _manifest_version()
        assert _per_dir(cwd)[-1] == rec, 'the per-directory log gets the same record'


def test_pointer_stale_outcome():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd, age_s=48 * 3600)
        _, _, new, records = _case(base, _payload(cwd, source='resume'), cwd)
        assert 'STALE' in _injected(new)
        rec = _one(records, 'pointer-stale', 'sess-rec', 'resume')
        assert rec['tier'] == 'pointer' and rec['stale'] is True
        assert rec['anchor_age_s'] >= 48 * 3600 - 60


def test_pointer_owner_outcome_records_the_ownership_fact():
    # A session that owns no anchor in a directory with open anchors records
    # who does, and that it owns none, the fact the record before this dropped.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        a = _anchor(cwd)
        (a.parent / '.owners.json').write_text(json.dumps({'run.md': 'sess-owner'}), 'utf-8')
        _, old_records, new, records = _case(base, _payload(cwd, session='sess-new'), cwd)
        assert 'last written by session sess-owner' in _injected(new)
        rec = _one(records, 'pointer-owner', 'sess-new', 'compact')
        assert rec['tier'] == 'pointer' and rec['stale'] is False
        assert rec['owner'] == 'sess-owner' and rec['owns_open_anchor'] is False
        if old_records is not None:
            assert 'owner' not in old_records[-1] and 'owns_open_anchor' not in old_records[-1]


def test_parked_outcome():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd, frontmatter='parked: the CI fix\n')
        _, _, new, records = _case(base, _payload(cwd, source='clear'), cwd)
        assert 'PARKED' in _injected(new)
        rec = _one(records, 'parked', 'sess-rec', 'clear')
        assert rec['tier'] == 'parked' and rec['dropped'] == 0


def test_no_anchors_outcome_in_a_directory_with_no_open_anchor():
    # Before this change such a run left no record anywhere.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd, name='done.closed.md')
        old, old_records, new, records = _case(base, _payload(cwd), cwd)
        assert new.stdout == ''
        if old is not None:
            assert old_records == [], 'the script before this change left a record'
        rec = _one(records, 'no-anchors', 'sess-rec', 'compact')
        assert rec['owns_open_anchor'] is False and rec['owner'] == ''
        assert rec['anchor_age_s'] is None and rec['head_chars'] is None
        assert rec['dropped'] is None and rec['file'] is None
        assert _per_dir(cwd) == [rec], 'the existing anchors directory gets it too'
        assert (cwd / '.claude' / 'anchors' / '.gitignore').read_text(encoding='utf-8') == '*'


def test_no_anchors_outcome_with_no_anchors_directory():
    # The central log is the only place a run in a directory with no
    # .claude/anchors can leave its record, and the hook does not create one.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        cwd.mkdir()
        _, _, new, records = _case(base, _payload(cwd, source='startup'), cwd)
        assert new.stdout == ''
        rec = _one(records, 'no-anchors', 'sess-rec', 'startup')
        assert rec['cwd'] == str(cwd)
        assert not (cwd / '.claude').exists(), 'the hook created an anchors directory'


def test_startup_too_old_outcome():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd, age_s=12 * 3600)
        _, _, new, records = _case(base, _payload(cwd, source='startup'), cwd)
        assert new.stdout == ''
        rec = _one(records, 'startup-too-old', 'sess-rec', 'startup')
        assert rec['file'] == 'run.md' and rec['anchor_age_s'] >= 12 * 3600 - 60
        assert rec['dropped'] is None


def test_bad_payload_outcome():
    for raw in ('{not json', '[]'):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            cwd = base / 'work'
            _anchor(cwd)
            _, _, new, records = _case(base, raw, cwd)
            assert new.stdout == '', raw
            rec = _one(records, 'bad-payload', '', 'unknown')
            assert rec['cwd'] is None and rec['owns_open_anchor'] is None, raw


def test_error_outcome():
    # A cwd that is not a path raises inside the hook; the outer guard has always
    # turned that into exit 0 with no output, and now it leaves a record.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        stdin = json.dumps(
            {
                'hook_event_name': 'SessionStart',
                'source': 'resume',
                'session_id': 'sess-err',
                'cwd': 7,
            }
        )
        _, _, new, records = _case(base, stdin, base)
        assert new.stdout == ''
        rec = _one(records, 'error', 'sess-err', 'resume')
        assert rec['error'] == 'TypeError', rec


class _BoomStdout:
    """A stdout whose write raises, keeping what the hook tried to write."""

    def __init__(self):
        self.tried = []

    def write(self, s):
        self.tried.append(s)
        raise UnicodeEncodeError('charmap', 'x', 0, 1, 'boom')

    def flush(self):
        pass


@contextlib.contextmanager
def _in_process(data: Path, stdin: str, stdout):
    saved = (sys.stdin, sys.stdout, os.environ.get('CLAUDE_PLUGIN_DATA'))
    os.environ['CLAUDE_PLUGIN_DATA'] = str(data)
    os.environ.pop('SESSION_WORKFLOW_ANCHOR_HOOKS', None)
    sys.stdin, sys.stdout = io.StringIO(stdin), stdout
    try:
        yield
    finally:
        sys.stdin, sys.stdout = saved[0], saved[1]
        if saved[2] is None:
            os.environ.pop('CLAUDE_PLUGIN_DATA', None)
        else:
            os.environ['CLAUDE_PLUGIN_DATA'] = saved[2]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_emit_failed_outcome():
    import anchor_inject

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd)
        stdin = _payload(cwd, source='compact')
        before = _before_script(base)
        if before is not None:
            old_out = _BoomStdout()
            with _in_process(base / 'data-before', stdin, old_out):
                assert _load(before, 'anchor_inject_before').main() == 0
        new_out = _BoomStdout()
        data = base / 'data'
        with _in_process(data, stdin, new_out):
            assert anchor_inject.main() == 0
        if before is not None:
            assert new_out.tried == old_out.tried, 'the attempted stdout changed'
        rec = _one(_central(data), 'emit-failed', 'sess-rec', 'compact')
        assert rec['tier'] == 'full' and rec['stale'] is False
        assert rec['error'] == 'UnicodeEncodeError'


def test_a_raise_in_the_per_directory_step_leaves_one_record():
    # The per-directory step runs after the print. A raise there must stay inside
    # log_outcome: reaching main's error path would write a second record.
    import anchor_inject

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd)
        stdin = _payload(cwd)
        golden = _run(SCRIPT, stdin, base / 'data-golden')
        data = base / 'data'
        out = io.StringIO()

        def boom(_anchors_dir, _record):
            raise RuntimeError('per-directory step')

        # append_telemetry runs only inside log_outcome, after the print.
        saved = anchor_inject.append_telemetry
        anchor_inject.append_telemetry = boom
        try:
            with _in_process(data, stdin, out):
                assert anchor_inject.main() == 0
        finally:
            anchor_inject.append_telemetry = saved
        assert out.getvalue() == golden.stdout and golden.stdout, (golden.stdout, out.getvalue())
        _one(_central(data), 'full', 'sess-rec', 'compact')


def test_the_anchor_dir_field_is_null_with_no_anchors_directory():
    # A raise before the anchors directory is resolved: the record cannot say
    # which directory was used, so it says nothing rather than "start".
    import anchor_inject

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd)
        data = base / 'data'

        def boom(*_args):
            raise RuntimeError('resolve')

        saved = anchor_inject.resolve_anchors
        anchor_inject.resolve_anchors = boom
        try:
            with _in_process(data, _payload(cwd), io.StringIO()):
                assert anchor_inject.main() == 0
        finally:
            anchor_inject.resolve_anchors = saved
        rec = _one(_central(data), 'error', 'sess-rec', 'compact')
        assert rec['anchors_dir'] is None and rec['anchor_dir'] is None, rec


class _UndecodableStdin:
    """A stdin whose bytes are not text in its encoding."""

    def read(self, *_args):
        raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte')


def test_an_undecodable_or_unparseable_stdin_is_a_bad_payload():
    import anchor_inject

    # A digit string past the interpreter's int conversion limit is a ValueError
    # from json.loads that is not a JSONDecodeError.
    huge_int = '{"n": ' + '1' * 5000 + '}'
    for label, stdin in (('undecodable', None), ('unparseable', huge_int)):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            cwd = base / 'work'
            _anchor(cwd)
            data = base / 'data'
            out = io.StringIO()
            with _in_process(data, stdin or '', out):
                if stdin is None:
                    sys.stdin = _UndecodableStdin()
                assert anchor_inject.main() == 0, label
            assert out.getvalue() == '', (label, out.getvalue())
            rec = _one(_central(data), 'bad-payload', '', 'unknown')
            assert 'error' not in rec, (label, rec)
    # The same as a subprocess: bytes that are not UTF-8 on a UTF-8 stdin.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        data = base / 'data'
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(SCRIPT)],
            input=b'{"source": "compact", "x": "\xff"}',
            capture_output=True,
            env=_env(data),
            timeout=30,
        )
        assert proc.returncode == 0 and proc.stdout == b'', (proc.stdout, proc.stderr)
        _one(_central(data), 'bad-payload', '', 'unknown')


# --- the write arm -----------------------------------------------------------------


def _write_payload(path: Path, session: str) -> str:
    return json.dumps(
        {
            'hook_event_name': 'PostToolUse',
            'tool_name': 'Write',
            'tool_input': {'file_path': str(path)},
            'session_id': session,
            'cwd': str(path.parent),
        }
    )


def test_anchor_write_record():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        small = _anchor(cwd)
        big = cwd / '.claude' / 'anchors' / 'big.md'
        big.write_text('---\nformat: anchor/v1\n---\n# Cursor\n' + 'x' * 7_500 + '\n', 'utf-8')
        notes = cwd / 'notes.md'
        notes.write_text('# not an anchor\n', encoding='utf-8')
        for path in (small, big, notes):
            _case(base, _write_payload(path, 'sess-writer'), cwd, args=('--post-write',))
        records = _central(base / 'data')
        assert [r['event'] for r in records] == ['anchor-write', 'anchor-write'], records
        assert [r['file'] for r in records] == ['run.md', 'big.md']
        assert [r['warned'] for r in records] == [False, True]
        for r in records:
            assert r['session'] == 'sess-writer' and r['v'] == 2, r
            assert r['ts'].endswith('+00:00'), r
        assert records[0]['head_chars'] == len(small.read_text(encoding='utf-8'))
        assert records[1]['head_chars'] >= 7_500


def test_an_unreadable_anchor_write_still_leaves_a_record():
    # A write to an open anchor that cannot be read back (a folder at the path
    # here) is still a write: its record says so, with no HEAD size.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        _anchor(cwd)
        blocked = cwd / '.claude' / 'anchors' / 'gone.md'
        blocked.mkdir()
        _, _, new, records = _case(
            base, _write_payload(blocked, 'sess-writer'), cwd, args=('--post-write',)
        )
        assert new.stdout == ''
        assert len(records) == 1, records
        rec = records[0]
        assert rec['event'] == 'anchor-write' and rec['file'] == 'gone.md', rec
        assert rec['session'] == 'sess-writer' and rec['head_chars'] is None, rec
        assert rec['warned'] is False and rec['v'] == 2, rec


# --- the opt-out -------------------------------------------------------------------


def test_opt_out_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        a = _anchor(cwd)
        off = {'SESSION_WORKFLOW_ANCHOR_HOOKS': '0'}
        data = base / 'data'
        for stdin, args in (
            (_payload(cwd), ()),
            (_write_payload(a, 'sess-off'), ('--post-write',)),
        ):
            proc = _run(SCRIPT, stdin, data, args, off)
            assert proc.returncode == 0 and proc.stdout == '', proc.stdout
        assert not data.exists(), 'the opt-out wrote to the plugin data folder'
        assert sorted(p.name for p in a.parent.iterdir()) == ['run.md']


# --- a failed write never changes stdout or the exit code --------------------------


def _manifest_version() -> str:
    manifest = HERE.parents[2] / '.claude-plugin' / 'plugin.json'
    return json.loads(manifest.read_text(encoding='utf-8'))['version']


def test_unreadable_plugin_json_keeps_the_golden_stdout_and_a_null_version():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        # A copy of the script inside a plugin tree whose plugin.json is a folder.
        copy = base / 'plugin' / 'skills' / 'compaction-survival' / 'scripts' / 'anchor_inject.py'
        copy.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, copy)
        (base / 'plugin' / '.claude-plugin' / 'plugin.json').mkdir(parents=True)
        cwd = base / 'work'
        _anchor(cwd)
        golden = _run(SCRIPT, _payload(cwd), base / 'data-golden')
        data = base / 'data'
        proc = _run(copy, _payload(cwd), data)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == golden.stdout and golden.stdout, (golden.stdout, proc.stdout)
        rec = _one(_central(data), 'full', 'sess-rec', 'compact')
        assert rec['plugin_version'] is None, rec


def test_unwritable_plugin_data_keeps_the_golden_stdout_and_the_per_directory_record():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        cwd = base / 'work'
        a = _anchor(cwd)
        golden = _run(SCRIPT, _payload(cwd), base / 'data-golden')
        blocked = base / 'not-a-folder'
        blocked.write_text('a file where the data folder should be\n', encoding='utf-8')
        before = len(_per_dir(cwd))
        proc = _run(SCRIPT, _payload(cwd), blocked)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == golden.stdout and golden.stdout
        after = _per_dir(cwd)
        assert len(after) == before + 1 and after[-1]['outcome'] == 'full', after
        # The write arm, on the same unwritable folder.
        big = a.parent / 'big.md'
        big.write_text('---\nformat: anchor/v1\n---\n# Cursor\n' + 'x' * 7_500 + '\n', 'utf-8')
        golden_w = _run(
            SCRIPT, _write_payload(big, 'sess-w'), base / 'data-golden', ('--post-write',)
        )
        proc = _run(SCRIPT, _write_payload(big, 'sess-w'), blocked, ('--post-write',))
        assert proc.returncode == 0 and proc.stdout == golden_w.stdout and golden_w.stdout
        assert blocked.read_text(encoding='utf-8').startswith('a file where')


def test_unwritable_anchors_directory_log_keeps_the_golden_stdout_and_one_central_record():
    for label, make in (
        ('full', lambda cwd: _anchor(cwd)),
        ('no-anchors', lambda cwd: _anchor(cwd, name='done.closed.md')),
    ):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            cwd = base / 'work'
            make(cwd)
            golden = _run(SCRIPT, _payload(cwd), base / 'data-golden')
            # The per-directory log's path is taken by a folder: no append can land.
            log = cwd / '.claude' / 'anchors' / 'log.ndjson'
            log.unlink()
            log.mkdir()
            data = base / 'data'
            proc = _run(SCRIPT, _payload(cwd), data)
            assert proc.returncode == 0, (label, proc.stderr)
            assert proc.stdout == golden.stdout, (label, golden.stdout, proc.stdout)
            _one(_central(data), label, 'sess-rec', 'compact')
            assert log.is_dir()


if __name__ == '__main__':
    test_full_outcome()
    test_pointer_stale_outcome()
    test_pointer_owner_outcome_records_the_ownership_fact()
    test_parked_outcome()
    test_no_anchors_outcome_in_a_directory_with_no_open_anchor()
    test_no_anchors_outcome_with_no_anchors_directory()
    test_startup_too_old_outcome()
    test_bad_payload_outcome()
    test_error_outcome()
    test_emit_failed_outcome()
    test_a_raise_in_the_per_directory_step_leaves_one_record()
    test_the_anchor_dir_field_is_null_with_no_anchors_directory()
    test_an_undecodable_or_unparseable_stdin_is_a_bad_payload()
    test_anchor_write_record()
    test_an_unreadable_anchor_write_still_leaves_a_record()
    test_opt_out_writes_nothing()
    test_unreadable_plugin_json_keeps_the_golden_stdout_and_a_null_version()
    test_unwritable_plugin_data_keeps_the_golden_stdout_and_the_per_directory_record()
    test_unwritable_anchors_directory_log_keeps_the_golden_stdout_and_one_central_record()
    print('ok: anchor hook record tests passed')

"""Tests for render_signature.py — the machine-generated LLM provenance signature.

Contract under test (panel-hardened, 2026-07-16 review round):
- the model comes from the transcript's last MAIN-LOOP assistant message —
  sidechain (subagent) and `<synthetic>` entries never sign;
- transcript auto-discovery nominates by munged-cwd dir match but signs only a
  FRESH transcript whose recorded cwd verifies against this one (exact paths,
  so lossy-munging collisions cannot pass); stale or wrong-project transcripts
  are refused;
- `plugins_from_json` parses `id`=plugin@marketplace, drops disabled plugins,
  tolerates shape drift;
- the rendered block is the two trailers; an empty stack omits Agent-Stack;
- `apply_to_message` handles what git actually emits: scissors sections
  (`commit --verbose`) are frozen and the block lands before them; the
  configured `core.commentChar` is honored; non-UTF-8 bytes round-trip; CRLF is
  preserved; scrubs are vendor-identity-anchored and flush-left only (a human
  co-author named Claude, indented examples, and body prose all survive); the
  block joins an existing final paragraph only when every line of it is
  trailer-shaped, so `git interpret-trailers` can always parse the result;
- CLI: unresolvable model exits 1 with no output; `--apply` always exits 0.

Stdlib-runnable (no pytest required): `python test_render_signature.py` runs
every test and prints `ok:`; the same no-arg functions also collect under pytest.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import render_signature as rs

SCRIPT = Path(__file__).resolve().parent / 'render_signature.py'


def _write_transcript(path: Path, entries: list[dict]) -> Path:
    path.write_text('\n'.join(json.dumps(e) for e in entries) + '\n', encoding='utf-8')
    return path


def _assistant(model: str, sidechain: bool = False, cwd: str | None = None) -> dict:
    entry = {'type': 'assistant', 'isSidechain': sidechain, 'message': {'model': model}}
    if cwd is not None:
        entry['cwd'] = cwd
    return entry


def test_model_from_transcript_last_main_loop_wins():
    with tempfile.TemporaryDirectory() as td:
        t = _write_transcript(
            Path(td) / 's.jsonl',
            [
                {'type': 'user', 'message': {'content': 'hi'}},
                _assistant('claude-opus-4-8'),
                _assistant('claude-haiku-4-5', sidechain=True),  # subagent: never signs
                _assistant('<synthetic>'),  # API-error stub: never signs
                _assistant('claude-sonnet-5'),
                _assistant('claude-haiku-4-5', sidechain=True),
            ],
        )
        assert rs.model_from_transcript(t) == 'claude-sonnet-5'


def test_model_from_transcript_tolerates_junk_lines():
    with tempfile.TemporaryDirectory() as td:
        t = Path(td) / 's.jsonl'
        t.write_text(
            'not json\n\n' + json.dumps(_assistant('claude-sonnet-5')) + '\n', encoding='utf-8'
        )
        assert rs.model_from_transcript(t) == 'claude-sonnet-5'
        assert rs.model_from_transcript(Path(td) / 'missing.jsonl') is None


def test_find_transcript_matches_munged_cwd_and_newest_file():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td) / 'home' / 'me' / 'repo'
        (cwd / 'sub').mkdir(parents=True)
        projects = Path(td) / 'projects'
        pdir = projects / rs._norm(str(cwd))
        pdir.mkdir(parents=True)
        _write_transcript(pdir / 'old.jsonl', [_assistant('claude-opus-4-8')])
        _write_transcript(pdir / 'new.jsonl', [_assistant('claude-sonnet-5')])
        now = time.time()
        os.utime(pdir / 'old.jsonl', (now - 600, now - 600))
        found = rs.find_transcript(cwd, projects)
        assert found is not None and found.name == 'new.jsonl'
        # a subdirectory of the session root climbs to the match
        found_sub = rs.find_transcript(cwd / 'sub', projects)
        assert found_sub is not None and found_sub.name == 'new.jsonl'
        assert rs.find_transcript(Path(td) / 'elsewhere', projects) is None


def test_find_transcript_refuses_stale_transcript():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td) / 'repo'
        cwd.mkdir()
        pdir = Path(td) / 'projects' / rs._norm(str(cwd))
        pdir.mkdir(parents=True)
        t = _write_transcript(pdir / 'ancient.jsonl', [_assistant('claude-opus-4-8')])
        old = time.time() - 2 * rs.FRESHNESS_WINDOW_S
        os.utime(t, (old, old))
        # a previous session's transcript is outside the freshness window: never signs
        assert rs.find_transcript(cwd, Path(td) / 'projects') is None


def test_find_transcript_verifies_recorded_cwd():
    with tempfile.TemporaryDirectory() as td:
        # two distinct projects whose munged dir names collide (`my.repo` vs `my/repo`)
        cwd = Path(td) / 'my.repo'
        other = Path(td) / 'my' / 'repo'
        cwd.mkdir()
        other.mkdir(parents=True)
        pdir = Path(td) / 'projects' / rs._norm(str(cwd))
        pdir.mkdir(parents=True)
        _write_transcript(pdir / 'other.jsonl', [_assistant('claude-opus-4-8', cwd=str(other))])
        # the only candidate records the OTHER project's cwd: refuse, don't guess
        assert rs.find_transcript(cwd, Path(td) / 'projects') is None
        _write_transcript(pdir / 'mine.jsonl', [_assistant('claude-sonnet-5', cwd=str(cwd))])
        found = rs.find_transcript(cwd, Path(td) / 'projects')
        assert found is not None and found.name == 'mine.jsonl'


def test_plugins_from_json_parses_and_filters():
    data = [
        {'id': 'session-workflow@craft-collection', 'version': '0.15.0', 'enabled': True},
        {'id': 'noisy@mkt', 'version': '1.0.0', 'enabled': False},  # disabled: dropped
        {'id': 'bare-plugin'},
        'shape-drift-string',
        {'no': 'id'},
    ]
    got = rs.plugins_from_json(data)
    assert got == [
        {'name': 'session-workflow', 'version': '0.15.0', 'marketplace': 'craft-collection'},
        {'name': 'bare-plugin', 'version': None, 'marketplace': None},
    ]
    assert rs.plugins_from_json({'plugins': data}) == got
    assert rs.plugins_from_json('garbage') == []


def test_render_block_shapes():
    assert rs.render_block('claude-sonnet-5', []) == 'Assisted-By: claude-sonnet-5'
    two = rs.render_block('claude-sonnet-5', ['claude-code@2.1.0', 'x@1.0 (mkt)'])
    assert two == 'Assisted-By: claude-sonnet-5\nAgent-Stack: claude-code@2.1.0; x@1.0 (mkt)'


def test_apply_scrubs_vendor_identity_keeps_humans():
    msg = (
        'feat: add thing\n\nbody line\n\n'
        'Co-Authored-By: Ada Lovelace <ada@example.com>\n'
        'Co-Authored-By: Claude Dubois <claude.dubois@example.fr>\n'
        'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>\n'
        'Co-Authored-By: Claude <claude-bot@users.noreply.github.com>\n'
        '\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)\n'
    )
    out = rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')
    assert 'noreply@anthropic.com' not in out
    assert 'users.noreply.github.com' not in out
    assert 'Generated with' not in out
    assert 'Ada Lovelace' in out
    assert 'Claude Dubois <claude.dubois@example.fr>' in out  # a human named Claude survives
    assert out.count('Assisted-By:') == 1


def test_apply_spares_prose_and_indented_examples():
    msg = (
        'docs: explain the signature\n\n'
        'Remove the stale fixtures that were generated with the Claude tokenizer.\n\n'
        'Example of the trailer block:\n'
        '    Assisted-By: claude-opus-4-8\n'
        '    Agent-Stack: x@1.0\n'
    )
    out = rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')
    assert 'generated with the Claude tokenizer' in out  # body prose survives
    assert '    Assisted-By: claude-opus-4-8' in out  # indented example survives
    assert out.count('\nAssisted-By: claude-sonnet-5') == 1  # fresh block still lands


def test_apply_refreshes_instead_of_duplicating():
    msg = 'feat: x\n\nAssisted-By: claude-opus-4-8\nAgent-Stack: old@0.1\n'
    block = 'Assisted-By: claude-sonnet-5\nAgent-Stack: new@0.2'
    out = rs.apply_to_message(msg, block)
    assert out.count('Assisted-By:') == 1
    assert 'claude-sonnet-5' in out and 'claude-opus-4-8' not in out
    assert rs.apply_to_message(out, block) == out  # idempotent


def test_apply_joins_trailer_paragraph_but_not_prose():
    # a real trailer paragraph is joined (git parses one final trailer block) ...
    signed = rs.apply_to_message(
        'feat: x\n\nbody\n\nSigned-off-by: Ada <ada@example.com>\n',
        'Assisted-By: claude-sonnet-5',
    )
    assert 'Signed-off-by: Ada <ada@example.com>\nAssisted-By: claude-sonnet-5\n' in signed
    # ... but a prose paragraph whose LAST line merely looks trailer-shaped is not
    prose = rs.apply_to_message(
        'feat: x\n\nSome prose here.\nNote: docs need a follow-up\n',
        'Assisted-By: claude-sonnet-5',
    )
    assert 'Note: docs need a follow-up\n\nAssisted-By: claude-sonnet-5\n' in prose


def test_apply_output_parses_with_git_interpret_trailers():
    git = shutil.which('git')
    if not git:
        print('skip-subtest: git unavailable, interpret-trailers check not run')
        return
    out = rs.apply_to_message(
        'feat: x\n\nSome prose here.\nNote: docs need a follow-up\n',
        'Assisted-By: claude-sonnet-5\nAgent-Stack: claude-code@2.1.0',
    )
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [git, 'interpret-trailers', '--parse'], input=out, capture_output=True, text=True
    )
    assert 'Assisted-By: claude-sonnet-5' in proc.stdout
    assert 'Agent-Stack: claude-code@2.1.0' in proc.stdout


def test_apply_inserts_before_scissors_and_freezes_the_diff():
    msg = (
        'feat: x\n\n'
        '# ------------------------ >8 ------------------------\n'
        '# Do not modify or remove the line above.\n'
        'diff --git a/f b/f\n'
        '+Co-Authored-By: Claude <noreply@anthropic.com>\n'
    )
    out = rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')
    assert out.index('Assisted-By: claude-sonnet-5') < out.index('>8')
    # the diff preview after the scissors line is byte-frozen, scrubs included
    assert '+Co-Authored-By: Claude <noreply@anthropic.com>' in out


def test_apply_honors_comment_char():
    # comment-only message under core.commentChar=';' is an abort: leave unsigned
    aborted = rs.apply_to_message(
        '; aborting\n; nothing here\n', 'Assisted-By: x', comment_char=';'
    )
    assert 'Assisted-By' not in aborted
    # and real content still signs, before the ';' comments
    signed = rs.apply_to_message('feat: x\n\n; a comment\n', 'Assisted-By: x', comment_char=';')
    assert signed.index('Assisted-By: x') < signed.index('; a comment')


def test_apply_leaves_comment_only_message_unsigned():
    msg = '# aborting\n'
    assert 'Assisted-By' not in rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')


def test_apply_preserves_crlf():
    msg = 'feat: x\r\n\r\nbody\r\n'
    out = rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')
    assert '\r\n' in out and 'Assisted-By: claude-sonnet-5\r\n' in out
    assert '\n' not in out.replace('\r\n', '')  # no mixed endings introduced


def test_apply_scrub_only_when_block_is_none():
    msg = 'fix: y\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n'
    out = rs.apply_to_message(msg, None)
    assert 'Claude' not in out and out.startswith('fix: y')


def _run_cli(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != 'CLAUDECODE'}
    # PATH without the claude CLI keeps the stack resolution deterministic here.
    env['PATH'] = str(Path(sys.executable).parent)
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        encoding='utf-8',
        cwd=cwd,
        env=env,
        timeout=30,
    )


def test_cli_explicit_model_prints_trailers():
    with tempfile.TemporaryDirectory() as td:
        proc = _run_cli(['--model', 'claude-sonnet-5', '--no-harness'], Path(td))
        assert proc.returncode == 0
        assert proc.stdout.strip() == 'Assisted-By: claude-sonnet-5'


def test_cli_unresolvable_model_fails_loud():
    with tempfile.TemporaryDirectory() as td:
        proc = _run_cli(['--no-harness'], Path(td))
        assert proc.returncode == 1
        assert not proc.stdout.strip()
        assert 'could not resolve' in proc.stderr


def test_cli_json_output():
    with tempfile.TemporaryDirectory() as td:
        t = _write_transcript(Path(td) / 's.jsonl', [_assistant('claude-sonnet-5')])
        proc = _run_cli(['--transcript', str(t), '--no-harness', '--json'], Path(td))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data['model'] == 'claude-sonnet-5'
        assert data['trailers'] == 'Assisted-By: claude-sonnet-5'


def test_cli_auto_discovery_via_projects_root():
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td) / 'repo'
        cwd.mkdir()
        pdir = Path(td) / 'projects' / rs._norm(str(cwd))
        pdir.mkdir(parents=True)
        _write_transcript(pdir / 's.jsonl', [_assistant('claude-sonnet-5', cwd=str(cwd))])
        proc = _run_cli(['--projects-root', str(Path(td) / 'projects'), '--no-harness'], cwd)
        assert proc.returncode == 0
        assert proc.stdout.strip() == 'Assisted-By: claude-sonnet-5'


def test_cli_apply_never_fails_and_signs_when_resolvable():
    with tempfile.TemporaryDirectory() as td:
        t = _write_transcript(Path(td) / 's.jsonl', [_assistant('claude-sonnet-5')])
        msg = Path(td) / 'COMMIT_EDITMSG'
        msg.write_text(
            'feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n', encoding='utf-8'
        )
        proc = _run_cli(['--apply', str(msg), '--transcript', str(t), '--no-harness'], Path(td))
        assert proc.returncode == 0 and not proc.stdout.strip()
        out = msg.read_text(encoding='utf-8')
        assert 'Assisted-By: claude-sonnet-5' in out and 'Co-Authored-By' not in out
        # unresolvable model: still exit 0, scrub only, no signature invented
        msg2 = Path(td) / 'MSG2'
        msg2.write_text(
            'fix: y\n\n\U0001f916 Generated with [Claude Code](https://x)\n', encoding='utf-8'
        )
        proc2 = _run_cli(['--apply', str(msg2), '--no-harness'], Path(td))
        assert proc2.returncode == 0
        out2 = msg2.read_text(encoding='utf-8')
        assert 'Generated with' not in out2 and 'Assisted-By' not in out2
        # missing file: still exit 0
        proc3 = _run_cli(['--apply', str(Path(td) / 'nope'), '--no-harness'], Path(td))
        assert proc3.returncode == 0


def test_cli_apply_survives_non_utf8_bytes():
    with tempfile.TemporaryDirectory() as td:
        t = _write_transcript(Path(td) / 's.jsonl', [_assistant('claude-sonnet-5')])
        msg = Path(td) / 'COMMIT_EDITMSG'
        raw = b'fix: caf\xe9 handling\n\ncorpo da mensagem\n'  # latin-1, not valid UTF-8
        msg.write_bytes(raw)
        proc = _run_cli(['--apply', str(msg), '--transcript', str(t), '--no-harness'], Path(td))
        assert proc.returncode == 0  # a hook must never abort the commit
        out = msg.read_bytes()
        assert b'\xe9' in out  # the raw byte round-tripped (surrogateescape)
        assert b'Assisted-By: claude-sonnet-5' in out


if __name__ == '__main__':
    test_model_from_transcript_last_main_loop_wins()
    test_model_from_transcript_tolerates_junk_lines()
    test_find_transcript_matches_munged_cwd_and_newest_file()
    test_find_transcript_refuses_stale_transcript()
    test_find_transcript_verifies_recorded_cwd()
    test_plugins_from_json_parses_and_filters()
    test_render_block_shapes()
    test_apply_scrubs_vendor_identity_keeps_humans()
    test_apply_spares_prose_and_indented_examples()
    test_apply_refreshes_instead_of_duplicating()
    test_apply_joins_trailer_paragraph_but_not_prose()
    test_apply_output_parses_with_git_interpret_trailers()
    test_apply_inserts_before_scissors_and_freezes_the_diff()
    test_apply_honors_comment_char()
    test_apply_leaves_comment_only_message_unsigned()
    test_apply_preserves_crlf()
    test_apply_scrub_only_when_block_is_none()
    test_cli_explicit_model_prints_trailers()
    test_cli_unresolvable_model_fails_loud()
    test_cli_json_output()
    test_cli_auto_discovery_via_projects_root()
    test_cli_apply_never_fails_and_signs_when_resolvable()
    test_cli_apply_survives_non_utf8_bytes()
    print('ok: all render_signature tests passed')

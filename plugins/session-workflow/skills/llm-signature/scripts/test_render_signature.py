"""Tests for render_signature.py — the machine-generated LLM provenance signature.

Contract under test:
- the model comes from the transcript's last MAIN-LOOP assistant message —
  sidechain (subagent) and `<synthetic>` entries never sign;
- transcript auto-discovery matches the munged cwd dir under the projects
  root (normalization-tolerant, climbs to parents, newest .jsonl wins);
- `plugins_from_json` parses `id`=plugin@marketplace, drops disabled plugins,
  tolerates shape drift;
- the rendered block is the two trailers; an empty stack omits Agent-Stack;
- `apply_to_message` scrubs Claude/Anthropic co-author boilerplate and
  "Generated with Claude Code" badges (human co-authors survive), refreshes
  stale trailers instead of duplicating, inserts before `#` comments, joins an
  existing trailer paragraph, and leaves a comment-only message unsigned;
- CLI: unresolvable model exits 1 with no output; `--apply` always exits 0.

Stdlib-runnable (no pytest required): `python test_render_signature.py` runs
every test and prints `ok:`; the same no-arg functions also collect under pytest.
"""

import json
import os
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


def _assistant(model: str, sidechain: bool = False) -> dict:
    return {'type': 'assistant', 'isSidechain': sidechain, 'message': {'model': model}}


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
        cwd = Path(td) / 'home' / 'me' / 'my.repo'
        (cwd / 'sub').mkdir(parents=True)
        projects = Path(td) / 'projects'
        pdir = projects / rs._norm(str(cwd))
        pdir.mkdir(parents=True)
        old = _write_transcript(pdir / 'old.jsonl', [_assistant('claude-opus-4-8')])
        past = time.time() - 3600
        os.utime(old, (past, past))
        _write_transcript(pdir / 'new.jsonl', [_assistant('claude-sonnet-5')])
        found = rs.find_transcript(cwd, projects)
        assert found is not None and found.name == 'new.jsonl'
        # a subdirectory of the session root climbs to the match
        found_sub = rs.find_transcript(cwd / 'sub', projects)
        assert found_sub is not None and found_sub.name == 'new.jsonl'
        assert rs.find_transcript(Path(td) / 'elsewhere', projects) is None


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


def test_apply_scrubs_ai_boilerplate_keeps_humans():
    msg = (
        'feat: add thing\n\nbody line\n\n'
        'Co-Authored-By: Ada Lovelace <ada@example.com>\n'
        'Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n'
        '🤖 Generated with [Claude Code](https://claude.com/claude-code)\n'
    )
    out = rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')
    assert 'noreply@anthropic.com' not in out
    assert 'Generated with' not in out
    assert 'Ada Lovelace' in out
    # joins the surviving trailer paragraph — one block, no blank line inserted
    assert 'Co-Authored-By: Ada Lovelace <ada@example.com>\nAssisted-By: claude-sonnet-5\n' in out


def test_apply_refreshes_instead_of_duplicating():
    msg = 'feat: x\n\nAssisted-By: claude-opus-4-8\nAgent-Stack: old@0.1\n'
    block = 'Assisted-By: claude-sonnet-5\nAgent-Stack: new@0.2'
    out = rs.apply_to_message(msg, block)
    assert out.count('Assisted-By:') == 1
    assert 'claude-sonnet-5' in out and 'claude-opus-4-8' not in out
    assert rs.apply_to_message(out, block) == out  # idempotent


def test_apply_inserts_before_comments_and_after_subject():
    msg = 'feat: x\n\n# Please enter the commit message\n# Lines starting with # are ignored\n'
    out = rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')
    # blank line after the subject (a `feat:` subject is not a trailer), block before comments
    assert out.startswith('feat: x\n\nAssisted-By: claude-sonnet-5\n')
    assert out.index('Assisted-By') < out.index('# Please enter')


def test_apply_leaves_comment_only_message_unsigned():
    msg = '# aborting\n'
    assert 'Assisted-By' not in rs.apply_to_message(msg, 'Assisted-By: claude-sonnet-5')


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
        _write_transcript(pdir / 's.jsonl', [_assistant('claude-sonnet-5')])
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
        msg2.write_text('fix: y\n\n🤖 Generated with [Claude Code](https://x)\n', encoding='utf-8')
        proc2 = _run_cli(['--apply', str(msg2), '--no-harness'], Path(td))
        assert proc2.returncode == 0
        out2 = msg2.read_text(encoding='utf-8')
        assert 'Generated with' not in out2 and 'Assisted-By' not in out2
        # missing file: still exit 0
        proc3 = _run_cli(['--apply', str(Path(td) / 'nope'), '--no-harness'], Path(td))
        assert proc3.returncode == 0


if __name__ == '__main__':
    test_model_from_transcript_last_main_loop_wins()
    test_model_from_transcript_tolerates_junk_lines()
    test_find_transcript_matches_munged_cwd_and_newest_file()
    test_plugins_from_json_parses_and_filters()
    test_render_block_shapes()
    test_apply_scrubs_ai_boilerplate_keeps_humans()
    test_apply_refreshes_instead_of_duplicating()
    test_apply_inserts_before_comments_and_after_subject()
    test_apply_leaves_comment_only_message_unsigned()
    test_apply_scrub_only_when_block_is_none()
    test_cli_explicit_model_prints_trailers()
    test_cli_unresolvable_model_fails_loud()
    test_cli_json_output()
    test_cli_auto_discovery_via_projects_root()
    test_cli_apply_never_fails_and_signs_when_resolvable()
    print('ok: all render_signature tests passed')

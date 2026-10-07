#!/usr/bin/env python3
"""Self-contained checks for feedback_nudge.py (no pytest required)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import feedback_nudge as fn


class _FakeStdin:
    def __init__(self, data: bytes) -> None:
        self.buffer = io.BytesIO(data)


@contextlib.contextmanager
def _env(**kv):
    saved = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run(argv: list[str], payload: object) -> tuple[int, str]:
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    old_stdin = sys.stdin
    out = io.StringIO()
    try:
        sys.stdin = _FakeStdin(raw)
        with contextlib.redirect_stdout(out):
            rc = fn.main(argv)
    finally:
        sys.stdin = old_stdin
    return rc, out.getvalue()


def _skill_call(name: str) -> dict:
    """One assistant record carrying a Skill tool_use -- the real transcript shape
    (verified against six live transcripts, 2026-08-11)."""
    return {
        'type': 'assistant',
        'message': {
            'content': [
                {'type': 'tool_use', 'id': 'tu1', 'name': 'Skill', 'input': {'skill': name}}
            ]
        },
    }


def _mcp_call(name: str) -> dict:
    return {
        'type': 'assistant',
        'message': {'content': [{'type': 'tool_use', 'id': 'tu2', 'name': name, 'input': {}}]},
    }


def _write_transcript(path: Path, prompts: list[str], records: list[dict] | None = None) -> None:
    lines = [json.dumps({'type': 'user', 'message': {'content': p}}) for p in prompts]
    lines += [json.dumps(r) for r in records or []]
    lines.append(json.dumps({'type': 'assistant', 'message': {'content': 'plain text turn'}}))
    lines.append('{ not json')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _targets(td: Path) -> Path:
    p = td / 'feedback-targets.toml'
    p.write_text('[keel]\nrepo = "/tmp/keel"\n', encoding='utf-8')
    return p


def _nudge_env(td: str, targets: str, min_turns: str = '2'):
    return _env(
        SESSION_WORKFLOW_FEEDBACK_NUDGE=None,  # default ON: nothing set
        SESSION_WORKFLOW_NUDGE_STATE_DIR=td,
        FEEDBACK_TARGETS_FILE=targets,
        SESSION_WORKFLOW_NUDGE_MIN_TURNS=min_turns,
    )


def test_fires_once_with_no_env_set():
    """The hook ships ON: an unset gate is not a default, and this one had never
    fired anywhere. The binding check below is what makes that safe."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['first prompt', 'second prompt'],
            [
                _skill_call('humblepowers:choosing-tools'),
                _mcp_call('mcp__plugin_fathom_fathom__plan'),
            ],
        )
        payload = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _nudge_env(td, str(_targets(tdp))):
            rc, out = _run(['--stop-nudge'], payload)
            assert rc == 0, out
            block = json.loads(out)
            assert block['decision'] == 'block'
            assert 'humblepowers:choosing-tools' in block['reason']
            assert 'mcp__plugin_fathom_fathom__plan' in block['reason']
            assert out == out.encode('ascii', errors='replace').decode('ascii'), 'non-ASCII output'
            assert (tdp / 'sid.nudged').is_file()
            rc2, out2 = _run(['--stop-nudge'], payload)
            assert rc2 == 0 and out2 == '', 'second stop must be silent (marker)'


def test_silent_without_a_registered_targets_file():
    """The binding check. With no feedback-targets file there is nowhere to report
    to, so a default-on nudge must cost an install with no registered tools
    nothing at all."""
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['a', 'b'], [_skill_call('humblepowers:choosing-tools')])
        with _env(
            SESSION_WORKFLOW_FEEDBACK_NUDGE=None,
            SESSION_WORKFLOW_NUDGE_STATE_DIR=td,
            FEEDBACK_TARGETS_FILE=str(tdp / 'does-not-exist.toml'),
            SESSION_WORKFLOW_NUDGE_MIN_TURNS='2',
        ):
            assert _run(
                ['--stop-nudge'], {'session_id': 's', 'transcript_path': str(transcript)}
            ) == (
                0,
                '',
            )
        assert not (tdp / 's.nudged').exists()


def test_silent_paths():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        targets = str(_targets(tdp))
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'], [_skill_call('humblepowers:choosing-tools')])
        base = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _env(
            SESSION_WORKFLOW_FEEDBACK_NUDGE='0',
            SESSION_WORKFLOW_NUDGE_STATE_DIR=td,
            FEEDBACK_TARGETS_FILE=targets,
        ):
            assert _run(['--stop-nudge'], base) == (0, ''), 'opt-out'
        with _nudge_env(td, targets):
            assert _run(['--stop-nudge'], {**base, 'stop_hook_active': True}) == (0, ''), (
                'stop_hook_active'
            )
        with _nudge_env(td, targets, min_turns='3'):
            assert _run(['--stop-nudge'], base) == (0, ''), 'below turn threshold'
        with _nudge_env(td, targets):
            assert _run(['--stop-nudge'], {'session_id': 'sid'}) == (0, ''), 'no transcript path'
        with _nudge_env(td, targets):
            bare = tdp / 'bare.jsonl'
            _write_transcript(bare, ['one', 'two'])
            assert _run(['--stop-nudge'], {**base, 'transcript_path': str(bare)}) == (0, ''), (
                'no plugin tool exercised'
            )
        assert not (tdp / 'sid.nudged').exists(), 'no silent path may burn the marker'


def test_debt_cleared_by_tool_feedback():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['one', 'two', 'three'],
            [
                _skill_call('humblepowers:choosing-tools'),
                _skill_call('session-workflow:tool-feedback'),
            ],
        )
        with _nudge_env(td, str(_targets(tdp))):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert (rc, out) == (0, ''), 'tool-feedback invocation must clear the debt'


def test_synthetic_user_records_do_not_count_as_turns():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['real prompt', '[SYSTEM NOTIFICATION - NOT USER INPUT] done', '<task-notification>x'],
            [_skill_call('humblepowers:choosing-tools')],
        )
        with _nudge_env(td, str(_targets(tdp))):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert (rc, out) == (0, ''), 'synthetic records counted toward the turn gate'


def test_read_transcript_shapes():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        blocks = json.dumps(
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'block prompt'}]}}
        )
        no_msg = json.dumps({'type': 'user'})
        p.write_text('\n'.join([blocks, no_msg]) + '\n', encoding='utf-8')
        assert fn.read_transcript(str(p)) == (1, []), 'textless user record must NOT count'
        assert fn.read_transcript(str(Path(td) / 'missing.jsonl')) == (0, [])
        assert fn.read_transcript(None) == (0, [])


def test_tool_result_user_records_do_not_count_as_turns():
    # In a real transcript most type=="user" records are tool results (content
    # blocks with no human text) - ~64 of 71 in the reviewed sample. Counting
    # them makes the min-turns gate inert.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        human = {'type': 'user', 'message': {'content': 'real prompt'}}
        tool_result = {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tu1',
                        'content': [{'type': 'text', 'text': 'file contents here'}],
                    }
                ]
            },
        }
        lines = [json.dumps(human)] + [json.dumps(tool_result)] * 5
        p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        assert fn.read_transcript(str(p))[0] == 1, 'tool_result records counted as human turns'


def test_non_plugin_tool_calls_are_not_debt():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        rec = {
            'type': 'assistant',
            'message': {
                'content': [
                    {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'ls'}},
                    {'type': 'tool_use', 'name': 'mcp__other__thing', 'input': {}},
                ]
            },
        }
        p.write_text(json.dumps(rec) + '\n', encoding='utf-8')
        assert fn.read_transcript(str(p))[1] == [], 'ordinary tools counted as plugin exercise'


def test_transcript_bom_and_crlf_tolerated():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 't.jsonl'
        recs = [
            json.dumps({'type': 'user', 'message': {'content': f'prompt {i}'}}) for i in range(3)
        ]
        p.write_bytes(b'\xef\xbb\xbf' + '\r\n'.join(recs).encode('utf-8') + b'\r\n')
        assert fn.read_transcript(str(p))[0] == 3, 'BOM/CRLF transcript undercounted'


def test_output_ascii_with_non_ascii_skill_name():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'], [_skill_call('plugin:habilitação-中文')])
        with _nudge_env(td, str(_targets(tdp))):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'sid', 'transcript_path': str(transcript)}
            )
    assert rc == 0 and out, 'nudge must fire'
    out.encode('ascii')  # raises -> non-ASCII leaked to stdout (cp1252 hazard)


def test_failed_print_does_not_burn_the_marker():
    class _Boom:
        def write(self, *a):
            raise OSError('console gone')

        def flush(self):
            pass

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'], [_skill_call('humblepowers:choosing-tools')])
        payload = {'session_id': 'sid', 'transcript_path': str(transcript)}
        with _nudge_env(td, str(_targets(tdp))):
            old_stdin = sys.stdin
            try:
                sys.stdin = _FakeStdin(json.dumps(payload).encode('utf-8'))
                with contextlib.redirect_stdout(_Boom()):
                    rc = fn.main(['--stop-nudge'])
            finally:
                sys.stdin = old_stdin
            assert rc == 0, 'a delivery failure must still exit 0'
            assert not (tdp / 'sid.nudged').exists(), 'failed delivery burned the slot'
            rc2, out2 = _run(['--stop-nudge'], payload)
            assert rc2 == 0 and out2, 'retry after failed delivery must re-fire'


def test_min_turns_garbage_falls_back():
    for raw, want in (('abc', 8), ('0', 8), ('-3', 8), ('5', 5), (None, 8)):
        with _env(SESSION_WORKFLOW_NUDGE_MIN_TURNS=raw):
            assert fn._min_turns() == want, (raw, want)


def test_main_unknown_mode_and_garbage_stdin_exit_0():
    assert _run([], {}) == (0, '')
    assert _run(['--stop-nudge'], b'\xff\xfe garbage')[0] == 0


def _real_registry(td: Path) -> Path:
    """A feedback-targets file in the shipped v1 shape, with one target whose
    repo actually ships a plugin and one that does not."""
    craft = td / 'craft-collection'
    (craft / 'plugins' / 'session-workflow').mkdir(parents=True)
    convoy = td / 'convoy'
    convoy.mkdir()
    p = td / 'real-targets.toml'
    p.write_text(
        '[targets.craft-collection]\n'
        f'repo = "{craft.as_posix()}"\n'
        'feedback_dir = "/tmp/fb"\n'
        '\n'
        '[targets.convoy]\n'
        f'repo = "{convoy.as_posix()}"\n',
        encoding='utf-8',
    )
    return p


def test_registered_repos_parses_the_targets_file():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert sorted(repos) == ['convoy', 'craft-collection']


def test_a_plugin_skill_resolves_through_the_repo_that_ships_it():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert fn.is_registered('session-workflow:compaction-survival', repos)


def test_a_bare_personal_skill_is_not_registered():
    # The observed defect: the nudge named `mantis-wisdom` -- a personal skill
    # under ~/.claude/skills, in no registry -- as a "plugin tool", sending the
    # reader to the registry to confirm a non-target.
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert not fn.is_registered('mantis-wisdom', repos)


def test_a_target_named_directly_is_registered():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert fn.is_registered('convoy', repos)


def test_an_mcp_plugin_tool_resolves_to_its_plugin():
    with tempfile.TemporaryDirectory() as td:
        repos = fn.registered_repos(_real_registry(Path(td)))
        assert fn.is_registered('mcp__plugin_convoy_convoy__convoy_run', repos)


def test_filtering_drops_only_the_unregistered():
    with tempfile.TemporaryDirectory() as td:
        targets = _real_registry(Path(td))
        tools = ['mantis-wisdom', 'session-workflow:compaction-survival', 'other-skill']
        assert fn.registered_only(tools, targets) == ['session-workflow:compaction-survival']


def test_the_filter_fails_open_when_no_repo_resolves():
    # A registry whose checkouts moved must not silence a real debt: saying too
    # much is a smaller failure than going quiet on a report that is owed.
    with tempfile.TemporaryDirectory() as td:
        targets = Path(td) / 'moved.toml'
        targets.write_text('[targets.gone]\nrepo = "/nowhere/at/all"\n', encoding='utf-8')
        tools = ['mantis-wisdom', 'session-workflow:compaction-survival']
        assert fn.registered_only(tools, targets) == tools


def test_a_session_of_only_unregistered_skills_owes_nothing():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        targets = _real_registry(tdp)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript, ['first prompt', 'second prompt'], [_skill_call('mantis-wisdom')]
        )
        with _nudge_env(td, str(targets)):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'unreg', 'transcript_path': str(transcript)}
            )
        assert rc == 0
        assert out.strip() == '', 'no registered tool ran, so there is no debt to nudge about'


def test_a_registered_skill_beside_an_unregistered_one_still_nudges():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        targets = _real_registry(tdp)
        transcript = tdp / 't.jsonl'
        _write_transcript(
            transcript,
            ['first prompt', 'second prompt'],
            [_skill_call('mantis-wisdom'), _skill_call('session-workflow:compaction-survival')],
        )
        with _nudge_env(td, str(targets)):
            rc, out = _run(
                ['--stop-nudge'], {'session_id': 'mixed', 'transcript_path': str(transcript)}
            )
        assert rc == 0
        assert 'compaction-survival' in out
        assert 'mantis-wisdom' not in out, 'a non-target must not be named as a registered tool'


# --- --stale-bodies: a skill body in context older than the installed plugin ---

SKILL_MARK = 'Base directory for this skill:'


def _cache_base(
    root: Path, plugin: str, version: str, skill: str, marketplace: str = 'craft-collection'
) -> str:
    """Where the harness serves a cached plugin's skill from."""
    return str(root / 'plugins' / 'cache' / marketplace / plugin / version / 'skills' / skill)


def _skill_load(base: str) -> dict:
    """A skill load as the harness records it: a meta user record whose one text
    block starts with the base-directory line. Written with json.dumps, so a
    Windows path lands in the file with escaped backslashes, as in a real
    transcript (214 of 214 such records in the local transcripts read on
    2026-10-07 had this shape)."""
    return {
        'type': 'user',
        'isMeta': True,
        'message': {
            'role': 'user',
            'content': [{'type': 'text', 'text': f'{SKILL_MARK} {base}\n\n# Skill\n\nBody.'}],
        },
    }


def _reattached(*bases: str) -> dict:
    """The record that serves invoked skills' bodies again (an `invoked_skills`
    attachment; 98 records in the same local transcripts)."""
    skills = [
        {'name': f'skill-{i}', 'path': f'plugin:skill-{i}', 'content': f'{SKILL_MARK} {b}\n\n# S'}
        for i, b in enumerate(bases)
    ]
    return {'type': 'attachment', 'attachment': {'type': 'invoked_skills', 'skills': skills}}


def _write_records(path: Path, records: list[dict]) -> Path:
    lines = [json.dumps({'type': 'user', 'message': {'content': 'a prompt'}})]
    lines += [json.dumps(r) for r in records]
    lines.append('{ not json')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def _install_registry(
    root: Path, versions: dict[str, str], marketplace: str = 'craft-collection'
) -> Path:
    """installed_plugins.json beside the cache, in the registry's version-2 shape."""
    plugins = {
        f'{name}@{marketplace}': [
            {
                'scope': 'user',
                'installPath': str(root / 'plugins' / 'cache' / marketplace / name / v),
                'version': v,
            }
        ]
        for name, v in versions.items()
    }
    p = root / 'plugins' / 'installed_plugins.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({'version': 2, 'plugins': plugins}), encoding='utf-8')
    return p


def _stale_run(transcript: object, **env: str | None) -> tuple[int, str]:
    payload = {
        'session_id': 'sid',
        'hook_event_name': 'SessionStart',
        'source': 'resume',
        'transcript_path': str(transcript) if transcript is not None else None,
    }
    with _env(**{'SESSION_WORKFLOW_STALE_BODY_CHECK': None, **env}):  # default ON
        return _run(['--stale-bodies'], payload)


def _context(out: str) -> str:
    block = json.loads(out)
    assert block['hookSpecificOutput']['hookEventName'] == 'SessionStart', block
    return block['hookSpecificOutput']['additionalContext']


def test_stale_body_names_both_versions_and_the_fix():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        transcript = _write_records(
            root / 't.jsonl',
            [
                _skill_load(_cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival')),
                _skill_load(_cache_base(root, 'session-workflow', '0.21.0', 'tool-feedback')),
            ],
        )
        rc, out = _stale_run(transcript)
    assert rc == 0, out
    out.encode('ascii')  # raises -> non-ASCII on stdout (cp1252 hazard)
    context = _context(out)
    lines = context.splitlines()
    assert len(lines) == 1, f'one line per plugin, got {lines}'
    line = lines[0]
    for want in ('session-workflow', '0.21.0', '0.24.4', 'compaction-survival', 'tool-feedback'):
        assert want in line, (want, line)
    assert 'again' in line and 'anchor' in line, f'the fix is not named: {line}'


def test_stale_body_same_version_is_silent():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        transcript = _write_records(
            root / 't.jsonl',
            [_skill_load(_cache_base(root, 'session-workflow', '0.24.4', 'compaction-survival'))],
        )
        assert _stale_run(transcript) == (0, '')


def test_stale_body_a_later_reload_clears_the_warning():
    """Last load wins: invoking the skill again at the installed version is the
    fix the warning names, so it must clear the warning."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        old = _cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival')
        new = _cache_base(root, 'session-workflow', '0.24.4', 'compaction-survival')
        cleared = _write_records(root / 'a.jsonl', [_skill_load(old), _skill_load(new)])
        assert _stale_run(cleared) == (0, ''), 'a reload at the installed version must clear'
        back = _write_records(root / 'b.jsonl', [_skill_load(new), _skill_load(old)])
        rc, out = _stale_run(back)
        assert rc == 0 and '0.21.0' in _context(out), 'the LAST load decides'


def test_stale_body_reattached_bodies_count_as_loads():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        old = _cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival')
        new = _cache_base(root, 'session-workflow', '0.24.4', 'compaction-survival')
        stale = _write_records(root / 'a.jsonl', [_reattached(old)])
        rc, out = _stale_run(stale)
        assert rc == 0 and '0.21.0' in _context(out), 'a re-served body is in context too'
        fresh = _write_records(root / 'b.jsonl', [_skill_load(old), _reattached(new)])
        assert _stale_run(fresh) == (0, '')


def test_stale_body_bom_and_crlf_tolerated():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        load = _skill_load(_cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival'))
        transcript = root / 't.jsonl'
        transcript.write_bytes(b'\xef\xbb\xbf' + json.dumps(load).encode('utf-8') + b'\r\n')
        rc, out = _stale_run(transcript)
    assert rc == 0 and '0.21.0' in _context(out), 'a BOM on the first line hid the load'


def test_parse_skill_base_accepts_both_separators():
    win = 'C:\\Users\\someone\\.claude\\plugins\\cache\\mkt\\session-workflow\\0.21.0\\skills\\tf'
    posix = '/home/someone/.claude/plugins/cache/mkt/session-workflow/0.21.0/skills/tf'
    for base, root in ((win, 'C:\\Users\\someone\\.claude'), (posix, '/home/someone/.claude')):
        load = fn.parse_skill_base(base)
        assert load is not None, base
        assert (load.marketplace, load.plugin, load.version, load.skill) == (
            'mkt',
            'session-workflow',
            '0.21.0',
            'tf',
        ), load
        assert load.root == root, load
    checkout = fn.parse_skill_base('/work/craft-collection/plugins/session-workflow/skills/tf')
    assert checkout is not None and checkout.version is None, 'a checkout has no cache version'
    assert (checkout.plugin, checkout.skill) == ('session-workflow', 'tf')
    personal = fn.parse_skill_base('/home/someone/.claude/skills/personal')
    assert personal is not None and personal.version is None, 'no cache, no version'
    assert fn.parse_skill_base('/opt/bundled-skill') is None


def test_stale_body_silent_paths():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = _skill_load(_cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival'))
        stale = _write_records(root / 'stale.jsonl', [old])
        # No registry yet: nothing to compare against.
        assert _stale_run(stale) == (0, ''), 'missing registry'
        _install_registry(root, {'session-workflow': '0.24.4', 'sha-pinned': 'abc1234'})
        assert _stale_run(stale)[1], 'precondition: this transcript warns'
        assert _stale_run(stale, SESSION_WORKFLOW_STALE_BODY_CHECK='0') == (0, ''), 'opt-out'
        assert _stale_run(root / 'missing.jsonl') == (0, ''), 'missing transcript'
        assert _stale_run(None) == (0, ''), 'no transcript path'
        assert _stale_run(root) == (0, ''), 'transcript path is a directory'
        with _env(SESSION_WORKFLOW_STALE_BODY_CHECK=None):
            assert _run(['--stale-bodies'], b'\xff\xfe not json') == (0, ''), 'malformed stdin'
            assert _run(['--stale-bodies'], [1, 2]) == (0, ''), 'stdin not an object'
        cases = {
            'plugin not in the registry': _cache_base(root, 'keel', '0.1.0', 'apply-method'),
            'same name, other marketplace': _cache_base(
                root, 'session-workflow', '0.21.0', 'tool-feedback', marketplace='a-fork'
            ),
            'newer than installed': _cache_base(root, 'session-workflow', '0.30.0', 'anchor'),
            'unparseable version': _cache_base(root, 'session-workflow', 'abc1234', 'anchor'),
            'unparseable installed version': _cache_base(root, 'sha-pinned', '0.1.0', 'anchor'),
            '--plugin-dir checkout': str(
                root / 'checkout' / 'plugins' / 'session-workflow' / 'skills' / 'anchor'
            ),
        }
        for name, base in cases.items():
            transcript = _write_records(root / 'case.jsonl', [_skill_load(base)])
            assert _stale_run(transcript) == (0, ''), name
        checkout = cases['--plugin-dir checkout'].replace('anchor', 'compaction-survival')
        later = _write_records(root / 'later.jsonl', [old, _skill_load(checkout)])
        assert _stale_run(later) == (0, ''), 'a later checkout load replaces the cached body'


def test_stale_body_a_quoted_marker_is_not_a_load():
    """A tool result that quotes the marker (a grep over old transcripts) serves
    no body; neither does a human prompt that mentions it mid-text."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        base = _cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival')
        quoted = {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tu1',
                        'content': [{'type': 'text', 'text': f'{SKILL_MARK} {base}\n'}],
                    }
                ]
            },
        }
        mentioned = {'type': 'user', 'message': {'content': f'why did {SKILL_MARK} {base} load?'}}
        transcript = _write_records(root / 't.jsonl', [quoted, mentioned])
        assert _stale_run(transcript) == (0, '')


def test_stale_body_exception_in_the_arm_exits_0():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        transcript = _write_records(
            root / 't.jsonl',
            [_skill_load(_cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival'))],
        )
        saved = sys.modules.get('plugin_version')
        sys.modules['plugin_version'] = None  # the next import raises ImportError
        try:
            assert _stale_run(transcript) == (0, ''), 'an import failure must exit 0, silent'
        finally:
            if saved is None:
                sys.modules.pop('plugin_version', None)
            else:
                sys.modules['plugin_version'] = saved


def _child_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_', 'PYTHONPATH'))}
    env.pop('SESSION_WORKFLOW_STALE_BODY_CHECK', None)
    env.pop('SESSION_WORKFLOW_FEEDBACK_NUDGE', None)
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    env.update(extra)
    return env


def test_stale_body_import_failure_cannot_touch_the_stop_nudge():
    """The arm's helper module is imported inside the arm. Run a copy of this
    script with no plugin_version.py beside it: the Stop nudge still fires and
    the stale-body arm stays silent, exit 0 both times."""
    import shutil
    import subprocess

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        alone = tdp / 'alone'
        alone.mkdir()
        script = alone / 'feedback_nudge.py'
        shutil.copyfile(Path(fn.__file__), script)
        transcript = tdp / 't.jsonl'
        _write_transcript(transcript, ['one', 'two'], [_skill_call('humblepowers:choosing-tools')])
        env = _child_env(
            SESSION_WORKFLOW_NUDGE_STATE_DIR=td,
            FEEDBACK_TARGETS_FILE=str(_targets(tdp)),
            SESSION_WORKFLOW_NUDGE_MIN_TURNS='2',
        )
        payload = json.dumps({'session_id': 'sid', 'transcript_path': str(transcript)})
        for arm, fires in (('--stop-nudge', True), ('--stale-bodies', False)):
            done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [sys.executable, str(script), arm],
                input=payload,
                capture_output=True,
                text=True,
                env=env,
                cwd=alone,
                timeout=60,
            )
            assert done.returncode == 0, (arm, done.stderr)
            assert bool(done.stdout.strip()) is fires, (arm, done.stdout, done.stderr)


def test_stale_body_large_transcript_stays_fast():
    """A long session's transcript runs to tens of MB and the hook has a 10 s
    timeout. 50 MB of tool-result lines with four sparse skill loads must be
    read well inside it; only the marker lines are parsed."""
    import time

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _install_registry(root, {'session-workflow': '0.24.4'})
        noise = json.dumps(
            {
                'type': 'user',
                'message': {
                    'content': [{'type': 'tool_result', 'tool_use_id': 'tu', 'content': 'x' * 5000}]
                },
            }
        )
        load = json.dumps(
            _skill_load(_cache_base(root, 'session-workflow', '0.21.0', 'compaction-survival'))
        )
        transcript = root / 'big.jsonl'
        with open(transcript, 'w', encoding='utf-8', newline='\n') as fh:
            for i in range(10_000):
                fh.write((load if i % 2500 == 1250 else noise) + '\n')
        size = transcript.stat().st_size
        assert size >= 50_000_000, size
        start = time.perf_counter()
        rc, out = _stale_run(transcript)
        elapsed = time.perf_counter() - start
    assert rc == 0 and '0.21.0' in _context(out), out
    assert elapsed < 5.0, f'{size} bytes took {elapsed:.2f}s'


def test_hooks_json_wires_the_stale_body_check():
    hooks = Path(__file__).resolve().parents[3] / 'hooks' / 'hooks.json'
    data = json.loads(hooks.read_text(encoding='utf-8'))
    wired = [
        (group.get('matcher'), hook)
        for group in data['hooks']['SessionStart']
        for hook in group['hooks']
        if hook.get('args', [])[-1:] == ['--stale-bodies']
    ]
    assert len(wired) == 1, wired
    matcher, hook = wired[0]
    assert matcher == 'resume|compact', matcher
    assert hook['args'][-2].endswith('/skills/tool-feedback/scripts/feedback_nudge.py'), hook
    assert hook.get('timeout') == 10, hook
    assert 'SESSION_WORKFLOW_STALE_BODY_CHECK=0' in data['description']


def main() -> int:
    test_fires_once_with_no_env_set()
    test_silent_without_a_registered_targets_file()
    test_silent_paths()
    test_debt_cleared_by_tool_feedback()
    test_synthetic_user_records_do_not_count_as_turns()
    test_read_transcript_shapes()
    test_tool_result_user_records_do_not_count_as_turns()
    test_non_plugin_tool_calls_are_not_debt()
    test_transcript_bom_and_crlf_tolerated()
    test_output_ascii_with_non_ascii_skill_name()
    test_failed_print_does_not_burn_the_marker()
    test_min_turns_garbage_falls_back()
    test_main_unknown_mode_and_garbage_stdin_exit_0()
    test_registered_repos_parses_the_targets_file()
    test_a_plugin_skill_resolves_through_the_repo_that_ships_it()
    test_a_bare_personal_skill_is_not_registered()
    test_a_target_named_directly_is_registered()
    test_an_mcp_plugin_tool_resolves_to_its_plugin()
    test_filtering_drops_only_the_unregistered()
    test_the_filter_fails_open_when_no_repo_resolves()
    test_a_session_of_only_unregistered_skills_owes_nothing()
    test_a_registered_skill_beside_an_unregistered_one_still_nudges()
    test_stale_body_names_both_versions_and_the_fix()
    test_stale_body_same_version_is_silent()
    test_stale_body_a_later_reload_clears_the_warning()
    test_stale_body_reattached_bodies_count_as_loads()
    test_stale_body_bom_and_crlf_tolerated()
    test_parse_skill_base_accepts_both_separators()
    test_stale_body_silent_paths()
    test_stale_body_a_quoted_marker_is_not_a_load()
    test_stale_body_exception_in_the_arm_exits_0()
    test_stale_body_import_failure_cannot_touch_the_stop_nudge()
    test_stale_body_large_transcript_stays_fast()
    test_hooks_json_wires_the_stale_body_check()
    print('ok: feedback_nudge')
    return 0


if __name__ == '__main__':
    sys.exit(main())

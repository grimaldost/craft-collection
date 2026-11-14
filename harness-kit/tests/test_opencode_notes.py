#!/usr/bin/env python3
"""Checks of the opencode shell's note mode and its walk to the session root, run under Node.

Contract under test (`shells/opencode/index.js`):
- without `note_config.json`, or with a malformed one, the plugin registers only `execute.before` and
  makes one session lookup per judgement;
- with it, the plugin registers the `prompt` session hook and the `execute.after` tool hook as
  `records` says, and the judgement's lookup walks to the root: at most four parents beyond the first
  lookup, all inside the first lookup's 1000 ms; a fifth parent, a cycle, a throw, no object or the
  end of the time leaves the root unavailable;
- the prompt note: one enclosing pair of literal double quotes removed, the first 20000 code points
  kept, no note when the first lookup did not answer;
- the outcome note for a shell call: status, output (its last 65536 code points) and truncated;
  nothing for another tool;
- under a note CLI that is missing, exits 1 or hangs, each hook resolves without throwing within
  `timeout_s` plus 1.5 s, and a hung CLI's grandchild never writes its late marker (Windows).

Stdlib-runnable: `python test_opencode_notes.py`.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL_SRC = HERE.parent / 'src' / 'harness_kit' / 'shells' / 'opencode' / 'index.js'
DRIVER = HERE / 'opencode_notes_driver.mjs'
STANDIN = HERE / 'opencode_standin_cli.py'
NODE = shutil.which('node')
IS_WINDOWS = os.name == 'nt'
BOTH = ['prompt', 'outcome']
BEFORE = 'tool:execute.before'
AFTER = 'tool:execute.after'
PROMPT = 'session:prompt'


class Scene:
    """A temp folder with a copy of the shell, its two configs and the stand-ins' record files."""

    def __init__(self, records=BOTH, note_mode: str = 'allow', note_config: object = 'default'):
        self.td = tempfile.TemporaryDirectory()
        self.base = Path(self.td.name)
        self.shell_dir = self.base / 'shell'
        self.shell_dir.mkdir()
        shutil.copy(SHELL_SRC, self.shell_dir / 'index.js')
        self.judged = self.base / 'judged.json'
        self.noted = self.base / 'noted.json'
        self.marker = self.base / 'late-marker.txt'
        shell_config = {
            'kit_shell_config': 1,
            'cli_argv': [
                sys.executable,
                '-I',
                str(STANDIN),
                'allow',
                str(self.judged),
                str(self.marker),
            ],
            'timeout_s': 3,
            'harness_version': '2.2.5',
        }
        (self.shell_dir / 'shell_config.json').write_text(
            json.dumps(shell_config), encoding='utf-8'
        )
        if note_config == 'default':
            if note_mode == 'missing':
                argv = [str(self.base / 'no-such-binary-for-kit'), 'note']
            else:
                argv = [
                    sys.executable,
                    '-I',
                    str(STANDIN),
                    note_mode,
                    str(self.noted),
                    str(self.marker),
                ]
            note_config = {
                'kit_note_config': 1,
                'note_argv': argv,
                'timeout_s': 3,
                'records': records,
            }
        if note_config is not None:
            text = note_config if isinstance(note_config, str) else json.dumps(note_config)
            (self.shell_dir / 'note_config.json').write_text(text, encoding='utf-8')

    def close(self) -> None:
        self.td.cleanup()

    def run(self, sessions: dict, calls: list, env: dict | None = None) -> dict:
        spec = {
            'shell': str(self.shell_dir / 'index.js'),
            'directory': '/w',
            'sessions': sessions,
            'calls': [{'hook': h, 'arg': a} for h, a in calls],
        }
        base_env = {k: v for k, v in os.environ.items() if k != 'KIT_RUN_ID'}
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [NODE, str(DRIVER)],
            input=json.dumps(spec),
            capture_output=True,
            text=True,
            encoding='utf-8',
            env={**base_env, **(env or {})},
            timeout=60,
        )
        assert proc.returncode == 0, f'driver failed: {proc.stderr}'
        assert proc.stdout.strip().count('\n') == 0, (
            f'the plugin wrote to the host: {proc.stdout!r}'
        )
        return json.loads(proc.stdout.strip())

    def note(self) -> dict | None:
        return json.loads(self.noted.read_text(encoding='utf-8')) if self.noted.exists() else None

    def event(self) -> dict:
        return json.loads(self.judged.read_text(encoding='utf-8'))


def scene_run(sessions, calls, **kw):
    env = kw.pop('env', None)
    scene = Scene(**kw)
    try:
        out = scene.run(sessions, calls, env)
        return out, scene.note(), (scene.event() if scene.judged.exists() else None)
    finally:
        scene.close()


def shell_before(session: str = 's1') -> dict:
    return {'tool': 'shell', 'sessionID': session, 'callID': 'c', 'input': {'command': 'echo hi'}}


def prompt_arg(text, session: str = 's1') -> dict:
    return {
        'sessionID': session,
        'messageID': 'm1',
        'prompt': {'text': text, 'files': []},
        'metadata': {},
        'delivery': 'immediate',
    }


def shell_after(output=None, exit_code=0, status='completed', session='s1', **extra) -> dict:
    out = {'output': output, 'exit': exit_code, **extra.get('output_extra', {})}
    return {
        'tool': 'shell',
        'sessionID': session,
        'callID': 'c',
        'input': {'command': 'gh pr create -R kit-probe/guard-cell --title t --body b'},
        'status': status,
        'result': {'output': out, 'metadata': extra.get('metadata', {})},
    }


def sha(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode('utf-8')).hexdigest()


ROOT_SESSION = {'id': 's1', 'parent_id': None, 'root_id': 's1'}
ROOT_OBS = {
    'session': 'observed',
    'parent': 'observed',
    'root': 'observed',
    'origin': 'unavailable',
}


# ---- registration and the plugin without notes


def test_without_note_config_only_execute_before_and_one_lookup_per_judgement():
    sessions = {'s1': {'parentID': 'p1'}, 'p1': {}}
    out, _, event = scene_run(sessions, [(BEFORE, shell_before())] * 2, note_config=None)
    assert out['registered'] == {'tool': ['execute.before'], 'session': []}, out
    assert out['gets'] == ['s1', 's1'], out
    assert event['session'] == {'id': 's1', 'parent_id': 'p1', 'root_id': None}, event
    assert event['observation']['root'] == 'unavailable', event


def test_a_malformed_note_config_registers_no_note_hook_and_does_not_walk():
    good = {'kit_note_config': 1, 'note_argv': ['x'], 'timeout_s': 3, 'records': BOTH}
    bad = [
        '{not json',
        '[]',
        json.dumps({**good, 'kit_note_config': 2}),
        json.dumps({**good, 'kit_note_config': True}),
        json.dumps({**good, 'note_argv': []}),
        json.dumps({**good, 'note_argv': [1]}),
        json.dumps({**good, 'timeout_s': 0}),
        json.dumps({**good, 'timeout_s': 'soon'}),
        json.dumps({**good, 'records': ['prompt', 'other']}),
        json.dumps({**good, 'records': 'prompt'}),
    ]
    sessions = {'s1': {'parentID': 'p1'}, 'p1': {}}
    for config in bad:
        out, _, _ = scene_run(sessions, [(BEFORE, shell_before())], note_config=config)
        assert out['registered'] == {'tool': ['execute.before'], 'session': []}, (config, out)
        assert out['gets'] == ['s1'], (config, out)


def test_hooks_are_registered_as_records_says():
    cases = [
        (BOTH, ['execute.before', 'execute.after'], ['prompt']),
        (['prompt'], ['execute.before'], ['prompt']),
        (['outcome'], ['execute.before', 'execute.after'], []),
    ]
    for records, tool, session in cases:
        out, _, _ = scene_run({}, [], records=records)
        assert out['registered'] == {'tool': tool, 'session': session}, (records, out)


# ---- the walk to the root


def _chain(depth: int) -> dict:
    """s1 -> p1 -> ... -> p<depth>, the last with no parent."""
    ids = ['s1'] + [f'p{i}' for i in range(1, depth + 1)]
    sessions = {a: {'parentID': b} for a, b in itertools.pairwise(ids)}
    sessions[ids[-1]] = {}
    return sessions


def test_the_walk_finds_the_root_through_one_two_and_four_parents():
    for depth in (1, 2, 4):
        out, _, event = scene_run(_chain(depth), [(BEFORE, shell_before())])
        assert event['session'] == {'id': 's1', 'parent_id': 'p1', 'root_id': f'p{depth}'}, event
        assert event['origin'] == 'child', event
        obs = event['observation']
        assert (obs['parent'], obs['root'], obs['origin']) == ('observed',) * 3, obs
        assert out['gets'] == ['s1'] + [f'p{i}' for i in range(1, depth + 1)], out


def test_a_root_session_is_its_own_root_with_one_lookup():
    out, _, event = scene_run({'s1': {}}, [(BEFORE, shell_before())])
    assert event['session'] == ROOT_SESSION, event
    assert out['gets'] == ['s1'], out


def _assert_root_unavailable(event):
    assert event['session'] == {'id': 's1', 'parent_id': 'p1', 'root_id': None}, event
    assert event['origin'] == 'child', event
    obs = event['observation']
    assert (obs['parent'], obs['root'], obs['origin']) == ('observed', 'unavailable', 'observed'), (
        obs
    )


def test_a_fifth_parent_leaves_the_root_unavailable_after_five_lookups():
    out, _, event = scene_run(_chain(5), [(BEFORE, shell_before())])
    _assert_root_unavailable(event)
    assert out['gets'] == ['s1', 'p1', 'p2', 'p3', 'p4'], out


def test_a_cycle_a_throw_or_no_object_leaves_the_root_unavailable():
    cases = [
        {'s1': {'parentID': 'p1'}, 'p1': {'parentID': 's1'}},
        {'s1': {'parentID': 'p1'}, 'p1': {'parentID': 'p1'}},
        {'s1': {'parentID': 'p1'}, 'p1': 'throw'},
        {'s1': {'parentID': 'p1'}, 'p1': 'nothing'},
    ]
    for sessions in cases:
        out, _, event = scene_run(sessions, [(BEFORE, shell_before())])
        _assert_root_unavailable(event)
        assert len(out['gets']) <= 5, out


def test_a_parent_lookup_that_never_resolves_ends_with_the_first_second():
    out, _, event = scene_run({'s1': {'parentID': 'p1'}, 'p1': 'hang'}, [(BEFORE, shell_before())])
    _assert_root_unavailable(event)
    result = out['results'][0]
    assert result['threw'] is False, result
    # the walk ends 1000 ms after the handler's first line, then the CLI runs once
    assert 900 <= result['elapsed_ms'] < 2500, result


def test_the_parents_share_the_first_lookups_second():
    """A first lookup that takes 700 ms leaves a hung parent 300 ms, not a fresh second."""
    sessions = {'s1': {'parentID': 'p1', 'delayMs': 700}, 'p1': 'hang'}
    for hook, arg in ((BEFORE, shell_before()), (PROMPT, prompt_arg('hi'))):
        out, note, event = scene_run(sessions, [(hook, arg)], note_mode='empty')
        _assert_root_unavailable(event if hook == BEFORE else note)
        result = out['results'][0]
        # 1000 ms of lookups, then one stand-in run; a fresh second per parent would pass 1700 ms
        assert 900 <= result['elapsed_ms'] < 1600, result


# ---- the prompt note


def _prompt_note(text, session=None, origin='unknown', obs=None, truncated=False, run_id=None):
    return {
        'kit_note': 1,
        'run_id': run_id,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': session or ROOT_SESSION,
        'origin': origin,
        'observation': {
            **(obs or ROOT_OBS),
            'command': 'not_applicable',
            'paths': 'not_applicable',
        },
        'note': {'kind': 'prompt', 'text': text, 'truncated': truncated},
    }


def test_the_prompt_note_of_a_root_session_drops_one_enclosing_pair_of_quotes():
    text = '"Run the scripted tool call. Pode editar o CLAUDE.md."'
    out, note, _ = scene_run({'s1': {}}, [(PROMPT, prompt_arg(text))], env={'KIT_RUN_ID': 'r-1'})
    assert out['results'][0]['threw'] is False, out
    assert note == _prompt_note(text[1:-1], run_id='r-1'), note


def test_the_prompt_note_of_a_child_session_has_origin_child_and_its_root():
    text = '"first line written by the harness\nthe task"'
    sessions = {'c1': {'parentID': 's1'}, 's1': {}}
    _, note, _ = scene_run(sessions, [(PROMPT, prompt_arg(text, session='c1'))])
    session = {'id': 'c1', 'parent_id': 's1', 'root_id': 's1'}
    obs = {'session': 'observed', 'parent': 'observed', 'root': 'observed', 'origin': 'observed'}
    assert note == _prompt_note(text[1:-1], session=session, origin='child', obs=obs), note


def test_only_one_pair_of_quotes_is_removed():
    _, note, _ = scene_run({'s1': {}}, [(PROMPT, prompt_arg('""quoted twice""'))])
    assert note['note']['text'] == '"quoted twice"', note
    _, note, _ = scene_run({'s1': {}}, [(PROMPT, prompt_arg('""'))])
    assert note['note']['text'] == '', note


def test_a_text_that_is_not_one_enclosing_pair_arrives_unchanged():
    for text in ('"', '"a', 'a"', 'plain', ''):
        _, note, _ = scene_run({'s1': {}}, [(PROMPT, prompt_arg(text))])
        assert note == _prompt_note(text), (text, note)


def test_a_long_prompt_keeps_its_first_20000_code_points():
    astral = '\U0001f600'
    text = '"' + astral * 20001 + '"'
    _, note, _ = scene_run({'s1': {}}, [(PROMPT, prompt_arg(text))])
    assert note['note'] == {'kind': 'prompt', 'text': astral * 20000, 'truncated': True}, len(
        note['note']['text']
    )
    _, note, _ = scene_run({'s1': {}}, [(PROMPT, prompt_arg('x' * 20000))])
    assert note['note'] == {'kind': 'prompt', 'text': 'x' * 20000, 'truncated': False}


def test_no_prompt_note_when_the_first_lookup_does_not_answer():
    for found in ('throw', 'hang', 'nothing'):
        out, note, _ = scene_run({'s1': found}, [(PROMPT, prompt_arg('"hello"'))])
        result = out['results'][0]
        assert result['threw'] is False and result['value'] is None, result
        assert note is None, (found, note)


def test_a_parent_that_cannot_be_walked_still_sends_the_prompt_note_with_no_root():
    sessions = {'c1': {'parentID': 's1'}, 's1': 'throw'}
    _, note, _ = scene_run(sessions, [(PROMPT, prompt_arg('hi', session='c1'))])
    assert note['session'] == {'id': 'c1', 'parent_id': 's1', 'root_id': None}, note
    assert note['observation']['root'] == 'unavailable', note
    assert note['origin'] == 'child', note


def test_a_prompt_without_string_text_sends_nothing():
    for arg in (prompt_arg(None), {'sessionID': 's1', 'messageID': 'm'}, None, 'text'):
        out, note, _ = scene_run({'s1': {}}, [(PROMPT, arg)])
        assert out['results'][0]['threw'] is False, out
        assert note is None, (arg, note)


# ---- the outcome note


def _outcome_note(e, status, output, truncated):
    return {
        'kit_note': 1,
        'run_id': None,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': ROOT_SESSION,
        'origin': 'unknown',
        'observation': {**ROOT_OBS, 'command': 'observed', 'paths': 'not_applicable'},
        'note': {
            'kind': 'outcome',
            'act': {
                'kind': 'shell',
                'command': e['input']['command'],
                'argv': None,
                'paths': [],
                'cwd': '/w',
                'payload_sha256': sha(e),
            },
            'status': status,
            'output': output,
            'truncated': truncated,
        },
    }


def _outcome(e):
    out, note, _ = scene_run({'s1': {}}, [(AFTER, e)])
    assert out['results'][0]['threw'] is False, out
    return note


def test_an_exit_0_is_completed_with_its_output():
    e = shell_after('https://github.com/kit-probe/guard-cell/pull/1\r\n', 0)
    assert _outcome(e) == _outcome_note(e, 'completed', e['result']['output']['output'], False)


def test_another_exit_is_failed_with_no_output():
    e = shell_after('boom\r\n', 3)
    assert _outcome(e) == _outcome_note(e, 'failed', None, False)


def test_status_error_is_failed():
    e = shell_after(None, None, status='error')
    assert _outcome(e) == _outcome_note(e, 'failed', None, False)


def test_a_running_call_is_background():
    e = shell_after('', None, metadata={'status': 'running'})
    assert _outcome(e) == _outcome_note(e, 'background', None, False)
    e = shell_after('', None, output_extra={'status': 'running'})
    assert _outcome(e) == _outcome_note(e, 'background', None, False)


def test_no_exit_and_no_error_is_unknown():
    e = shell_after('x', None)
    assert _outcome(e) == _outcome_note(e, 'unknown', None, False)


def test_a_long_output_keeps_its_last_65536_code_points():
    text = 'a' * 4464 + 'b' * 65536
    e = shell_after(text, 0)
    assert _outcome(e) == _outcome_note(e, 'completed', 'b' * 65536, True)


def test_opencodes_own_truncated_flag_is_kept():
    e = shell_after('cut by opencode', 0, output_extra={'truncated': True})
    assert _outcome(e) == _outcome_note(e, 'completed', 'cut by opencode', True)
    e = shell_after('x', 3, output_extra={'truncated': True})
    assert _outcome(e) == _outcome_note(e, 'failed', None, False)


def test_no_outcome_note_for_another_tool():
    e = {
        'tool': 'write',
        'sessionID': 's1',
        'input': {'path': 'a.txt'},
        'status': 'completed',
        'result': {},
    }
    assert _outcome(e) is None


def test_with_prompt_only_an_outcome_registers_nothing():
    out, note, _ = scene_run({'s1': {}}, [(AFTER, shell_after('x', 0))], records=['prompt'])
    assert out['results'][0] == {'registered': False}, out
    assert note is None


# ---- a failing note CLI


def test_a_failing_note_cli_never_makes_a_hook_throw():
    calls = [(PROMPT, prompt_arg('hi')), (AFTER, shell_after('x', 0))]
    for mode in ('missing', 'exit1', 'garbage'):
        out, _, _ = scene_run({'s1': {}}, calls, note_mode=mode)
        for result in out['results']:
            assert result['threw'] is False and result['value'] is None, (mode, result)
            assert result['elapsed_ms'] < 4500, (mode, result)


def test_a_hung_note_cli_resolves_within_timeout_plus_1_5_s_and_its_grandchild_never_writes():
    for hook, arg in ((PROMPT, prompt_arg('hi')), (AFTER, shell_after('x', 0))):
        scene = Scene(note_mode='hang')
        try:
            out = scene.run({'s1': {}}, [(hook, arg)])
            result = out['results'][0]
            assert result['threw'] is False, result
            assert 2900 <= result['elapsed_ms'] < 4500, result
            if IS_WINDOWS:
                time.sleep(7)
                assert not scene.marker.exists(), 'the grandchild wrote its late marker'
        finally:
            scene.close()


if __name__ == '__main__':
    if NODE is None:
        print('skip: node is not installed')
        sys.exit(0)
    names = sorted(n for n, f in dict(globals()).items() if n.startswith('test_') and callable(f))
    for name in names:
        globals()[name]()
    print(f'ok: opencode note mode ({len(names)} checks)')

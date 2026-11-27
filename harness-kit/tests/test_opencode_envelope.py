#!/usr/bin/env python3
"""Checks of the opencode driver's translation of the shell's envelope.

Contract under test (`harnesses/opencode.py`):
- the envelope has exactly `kit_raw` (1), `hook`, `run_id`, `harness`, `session`, `origin`,
  `observation` (exactly `session`, `parent`, `root`, `origin`), `location` and `payload` (a
  string holding one JSON object); a missing or extra key, a wrong type, a payload that is not a
  JSON object or another harness name is refused;
- `translate_event` gives the neutral event the shell built before the envelope: `shell`, `write`,
  `edit` and any other tool, `payload_sha256` the SHA-256 of the payload's UTF-8 bytes, `cwd` the
  location, or the shell call's own `workdir` resolved against it, and paths
  `normpath(join(location, path))`;
- `patch` reads every line whose trimmed text starts with an Add, Update, Delete or Move header,
  trimming with ECMAScript's white space set; its paths are `observed` when every header was read
  and one path found, else `unavailable`;
- `translate_note` gives the prompt note (one enclosing pair of quotes removed, the first 20000
  code points kept) and the outcome note (status rules, the last 65536 code points);
- `refused_tool` names `opencode_worktree_remove` and its reason for an `execute.before` envelope,
  matched by exact name, and nothing for any other tool, spelling or hook.

Stdlib-runnable: `python test_opencode_envelope.py`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.event import InvalidEventError, check_event
from harness_kit.harnesses import get
from harness_kit.harnesses.opencode import ECMA_WHITESPACE, ecma_trim, patch_paths
from harness_kit.notes import InvalidNoteError, check_note
from kit_fixtures import run_module

DRIVER = get('opencode')
LOC = os.path.abspath('/w')
PLACE = {'session': 'observed', 'parent': 'observed', 'root': 'observed', 'origin': 'unavailable'}
SESSION = {'id': 's1', 'parent_id': None, 'root_id': 's1'}
REASON = (
    'kit refuses this tool under kit run; remove a worktree with git in the shell, which kit judges'
)


def payload_text(e: object) -> str:
    return json.dumps(e, separators=(',', ':'))


def envelope(e: object, hook: str = 'execute.before', location: str = LOC, **over) -> dict:
    env = {
        'kit_raw': 1,
        'hook': hook,
        'run_id': None,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': dict(SESSION),
        'origin': 'unknown',
        'observation': dict(PLACE),
        'location': location,
        'payload': e if isinstance(e, str) else payload_text(e),
    }
    env.update(over)
    return env


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def at(*parts: str) -> str:
    return os.path.normpath(os.path.join(LOC, *parts))


def shell(command: str = 'echo hi', **input_extra) -> dict:
    return {
        'tool': 'shell',
        'sessionID': 's1',
        'callID': 'c',
        'input': {'command': command, **input_extra},
    }


def translated(e: dict, **over) -> dict:
    ev = DRIVER.translate_event(envelope(e, **over))
    return check_event(ev)


# ---- the envelope


def test_a_shell_call_is_exactly_the_neutral_event_the_shell_built():
    e = shell('echo hi')
    ev = translated(e, run_id='r-1')
    assert ev == {
        'kit_event': 1,
        'run_id': 'r-1',
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': SESSION,
        'origin': 'unknown',
        'observation': {**PLACE, 'command': 'observed', 'paths': 'not_applicable'},
        'act': {
            'kind': 'shell',
            'command': 'echo hi',
            'argv': None,
            'paths': [],
            'cwd': LOC,
            'payload_sha256': sha(payload_text(e)),
        },
    }, ev


def test_payload_sha256_hashes_the_payload_string_as_sent():
    text = '{"tool": "shell", "sessionID": "s1", "input": {"command": "caf\\u00e9 \u4e2d"}}'
    ev = translated(text)
    assert ev['act']['payload_sha256'] == sha(text), ev
    assert ev['act']['command'] == 'caf\xe9 \u4e2d', ev


def test_the_cwd_is_the_location_as_sent():
    ev = translated(shell(), location='/w/')
    assert ev['act']['cwd'] == '/w/', ev


def test_a_shell_call_with_its_own_workdir_gets_that_folder_resolved():
    assert translated(shell(workdir='sub/dir'))['act']['cwd'] == at('sub', 'dir')
    other = os.path.abspath('/elsewhere')
    assert translated(shell(workdir=other))['act']['cwd'] == other
    for value in (None, 7, ''):
        assert translated(shell(workdir=value))['act']['cwd'] == LOC, value


def test_a_shell_call_without_a_string_command_is_an_empty_observed_command():
    for inp in ({}, {'command': 5}, None, 'text', []):
        ev = DRIVER.translate_event(envelope({'tool': 'shell', 'sessionID': 's1', 'input': inp}))
        assert ev['act']['command'] == '' and ev['observation']['command'] == 'observed', ev


def test_write_and_edit_are_file_writes_resolved_against_the_location():
    for tool in ('write', 'edit'):
        ev = translated({'tool': tool, 'sessionID': 's1', 'input': {'path': 'sub/../a.txt'}})
        act = ev['act']
        assert (act['kind'], act['command'], act['paths']) == ('file_write', None, [at('a.txt')])
        obs = ev['observation']
        assert (obs['command'], obs['paths']) == ('not_applicable', 'observed'), obs


def test_a_write_without_a_string_path_has_unavailable_paths():
    ev = DRIVER.translate_event(envelope({'tool': 'write', 'sessionID': 's1', 'input': {}}))
    assert ev['act']['paths'] == [] and ev['observation']['paths'] == 'unavailable', ev


def test_any_other_tool_is_other_with_both_observations_not_applicable():
    ev = translated({'tool': 'grep', 'sessionID': 's1', 'input': {'pattern': 'x'}})
    assert (ev['act']['kind'], ev['act']['command'], ev['act']['paths']) == ('other', None, [])
    assert ev['act']['cwd'] == LOC
    obs = ev['observation']
    assert (obs['command'], obs['paths']) == ('not_applicable', 'not_applicable'), obs


def _refused(env: object) -> str:
    try:
        DRIVER.translate_event(env)
    except InvalidEventError as exc:
        return str(exc)
    raise AssertionError(f'not refused: {env!r}')


def test_a_broken_envelope_is_refused():
    good = envelope(shell())
    broken = [None, [], 'text']
    for key in good:
        broken.append({k: v for k, v in good.items() if k != key})
    broken += [
        {**good, 'extra': 1},
        {**good, 'kit_raw': 2},
        {**good, 'kit_raw': True},
        {**good, 'kit_raw': '1'},
        {**good, 'hook': 'execute.after'},
        {**good, 'hook': 'other'},
        {**good, 'run_id': 5},
        {**good, 'harness': {'name': 'claude-code', 'version': '2.2.5'}},
        {**good, 'harness': {'name': 'opencode'}},
        {**good, 'harness': {'name': 'opencode', 'version': '2.2.5', 'x': 1}},
        {**good, 'harness': 'opencode'},
        {**good, 'observation': {**PLACE, 'command': 'observed'}},
        {**good, 'observation': {k: v for k, v in PLACE.items() if k != 'root'}},
        {**good, 'observation': 'observed'},
        {**good, 'location': None},
        {**good, 'payload': {'tool': 'shell'}},
        {**good, 'payload': '[1, 2]'},
        {**good, 'payload': 'not json'},
        {**good, 'payload': '"text"'},
        {**good, 'payload': '{"tool": "shell", "tool": "x"}'},
        {**good, 'payload': '{"sessionID": "s1"}'},
        {**good, 'payload': '{"tool": 5}'},
    ]
    for env in broken:
        assert _refused(env).isascii()


def test_a_place_the_event_contract_refuses_is_refused():
    for over in ({'origin': 'owner'}, {'session': {'id': 's1'}}, {'session': 'x'}):
        ev = DRIVER.translate_event(envelope(shell(), **over))
        try:
            check_event(ev)
        except InvalidEventError:
            continue
        raise AssertionError(over)


# ---- patch


def _patch(text: str) -> dict:
    return DRIVER.translate_event(
        envelope({'tool': 'patch', 'sessionID': 's1', 'input': {'patchText': text}})
    )


def test_each_patch_form_yields_its_paths():
    text = '\n'.join(
        [
            '*** Begin Patch',
            '*** Environment ID: env-1',
            '*** Add File: new.txt',
            '+hello',
            '    *** Update File: old.txt',
            '*** End of File',
            '*** Move to: moved/old.txt',
            '@@',
            '-a',
            '+b',
            '*** Delete File: gone.txt',
            '*** End Patch',
        ]
    )
    ev = check_event(_patch(text))
    assert ev['act']['kind'] == 'file_write' and ev['act']['command'] is None, ev
    assert ev['observation']['paths'] == 'observed', ev
    expected = [at('new.txt'), at('old.txt'), at('moved', 'old.txt'), at('gone.txt')]
    assert ev['act']['paths'] == expected, ev['act']['paths']


def test_an_indented_header_after_an_add_hunk_is_read():
    text = '*** Begin Patch\n*** Add File: a.txt\n+x\n  *** Add File: b.txt\n+y\n*** End Patch'
    assert patch_paths(text, LOC) == [at('a.txt'), at('b.txt')]


def test_carriage_returns_and_a_heredoc_wrapper_are_normalized():
    text = "cat <<'EOF'\r\n*** Begin Patch\r\n*** Add File: a.txt\r\n+x\r\n*** End Patch\r\nEOF\n"
    assert patch_paths(text, LOC) == [at('a.txt')]
    text = '<<PATCH\n*** Begin Patch\n*** Delete File: d.txt\n*** End Patch\nPATCH'
    assert patch_paths(text, LOC) == [at('d.txt')]


def test_trimming_uses_the_ecmascript_white_space_set():
    expected = {*range(0x09, 0x0E), 0x20, 0xA0, 0x1680, *range(0x2000, 0x200B)} | {
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
        0xFEFF,
    }
    assert {ord(c) for c in ECMA_WHITESPACE} == expected
    assert ecma_trim('\ufeff a \xa0') == 'a'
    assert ecma_trim('\x1c\x85a\x1f') == '\x1c\x85a\x1f'


def test_a_header_led_by_a_byte_order_mark_beside_an_ordinary_one_yields_both():
    text = '*** Begin Patch\n\ufeff*** Add File: a.txt\n+x\n*** Add File: b.txt\n+y\n*** End Patch'
    assert patch_paths(text, LOC) == [at('a.txt'), at('b.txt')]


def test_a_path_ending_in_feff_loses_it_and_one_ending_in_0085_keeps_it():
    text = (
        '*** Begin Patch\n*** Delete File: a.txt\ufeff\n*** Delete File: b.txt\x85\n*** End Patch'
    )
    assert patch_paths(text, LOC) == [at('a.txt'), at('b.txt\x85')]


def test_an_unread_form_or_no_path_is_unavailable():
    unread = [
        '*** Begin Patch\n*** Copy File: a.txt\n*** End Patch',
        '*** Begin Patch\n*** Add File: a.txt\n+x\n*** Rename to: b.txt\n*** End Patch',
        '*** Begin Patch\n*** End Patch',
        '--- a/x.txt\n+++ b/x.txt\n@@\n-a\n+b\n',
        '',
    ]
    for text in unread:
        assert patch_paths(text, LOC) is None, text
        ev = check_event(_patch(text))
        assert ev['act']['paths'] == [] and ev['observation']['paths'] == 'unavailable', text
    for inp in ({}, {'patchText': 5}, None):
        ev = check_event(
            DRIVER.translate_event(envelope({'tool': 'patch', 'sessionID': 's1', 'input': inp}))
        )
        assert ev['observation']['paths'] == 'unavailable', inp


# ---- notes


def _prompt(text: object) -> dict:
    return {'sessionID': 's1', 'messageID': 'm1', 'prompt': {'text': text, 'files': []}}


def _note(e: object, hook: str, **over) -> dict:
    return check_note(DRIVER.translate_note(envelope(e, hook=hook, **over)))


def test_a_prompt_note_drops_one_enclosing_pair_of_quotes():
    note = _note(_prompt('"hi there"'), 'prompt', run_id='r-1')
    assert note == {
        'kit_note': 1,
        'run_id': 'r-1',
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': SESSION,
        'origin': 'unknown',
        'observation': {**PLACE, 'command': 'not_applicable', 'paths': 'not_applicable'},
        'note': {'kind': 'prompt', 'text': 'hi there', 'truncated': False},
    }, note
    for text, kept in (('""x""', '"x"'), ('""', ''), ('"', '"'), ('"a', '"a'), ('plain', 'plain')):
        assert _note(_prompt(text), 'prompt')['note']['text'] == kept, text


def test_a_long_prompt_keeps_its_first_20000_code_points():
    astral = '\U0001f600'
    body = _note(_prompt('"' + astral * 20001 + '"'), 'prompt')['note']
    assert body == {'kind': 'prompt', 'text': astral * 20000, 'truncated': True}
    body = _note(_prompt('x' * 20000), 'prompt')['note']
    assert body == {'kind': 'prompt', 'text': 'x' * 20000, 'truncated': False}


def _after(output=None, exit_code=0, status='completed', **extra) -> dict:
    out = {'output': output, 'exit': exit_code, **extra.get('output_extra', {})}
    return {
        'tool': 'shell',
        'sessionID': 's1',
        'callID': 'c',
        'input': {'command': 'echo hi'},
        'status': status,
        'result': {'output': out, 'metadata': extra.get('metadata', {})},
    }


def _outcome(e: dict) -> dict:
    return _note(e, 'execute.after')['note']


def test_an_outcome_note_carries_the_shell_act_and_its_status():
    e = _after('done\n', 0)
    note = _note(e, 'execute.after')
    assert note['observation'] == {**PLACE, 'command': 'observed', 'paths': 'not_applicable'}
    assert note['note'] == {
        'kind': 'outcome',
        'act': {
            'kind': 'shell',
            'command': 'echo hi',
            'argv': None,
            'paths': [],
            'cwd': LOC,
            'payload_sha256': sha(payload_text(e)),
        },
        'status': 'completed',
        'output': 'done\n',
        'truncated': False,
    }, note


def test_the_outcome_status_rules():
    assert _outcome(_after('boom', 3))['status'] == 'failed'
    assert _outcome(_after('boom', 3))['output'] is None
    assert _outcome(_after(None, None, status='error'))['status'] == 'failed'
    assert _outcome(_after('', None, metadata={'status': 'running'}))['status'] == 'background'
    assert _outcome(_after('', None, output_extra={'status': 'running'}))['status'] == 'background'
    assert _outcome(_after('x', None))['status'] == 'unknown'
    assert _outcome(_after('x', False))['status'] == 'unknown'
    assert _outcome(_after('x', 0.0))['status'] == 'completed'
    assert _outcome(_after('x', 2.5))['status'] == 'failed'


def test_a_long_output_keeps_its_last_65536_code_points_and_opencodes_flag():
    body = _outcome(_after('a' * 4464 + 'b' * 65536, 0))
    assert (body['output'], body['truncated']) == ('b' * 65536, True)
    body = _outcome(_after('cut', 0, output_extra={'truncated': True}))
    assert (body['output'], body['truncated']) == ('cut', True)
    body = _outcome(_after('x', 3, output_extra={'truncated': True}))
    assert (body['output'], body['truncated']) == (None, False)


def test_a_broken_note_envelope_is_refused():
    broken = [
        envelope(_prompt('hi'), hook='execute.before'),
        envelope(_prompt(None), hook='prompt'),
        envelope({'sessionID': 's1'}, hook='prompt'),
        {**envelope(_prompt('hi'), hook='prompt'), 'kit_raw': 2},
        {**envelope(_prompt('hi'), hook='prompt'), 'payload': '[]'},
        envelope({'sessionID': 's1', 'status': 'completed'}, hook='execute.after'),
    ]
    for env in broken:
        try:
            DRIVER.translate_note(env)
        except InvalidNoteError as exc:
            assert str(exc).isascii()
            continue
        raise AssertionError(env)


# ---- refused tools


def test_the_refused_list_holds_one_tool_and_its_reason():
    assert dict(DRIVER.refused_tools) == {'opencode_worktree_remove': REASON}
    e = {'tool': 'opencode_worktree_remove', 'sessionID': 's1', 'input': {'force': True}}
    assert DRIVER.refused_tool(envelope(e)) == ('opencode_worktree_remove', REASON)
    ev = translated(e)
    assert ev['act']['kind'] == 'other', ev


def test_other_tools_spellings_and_hooks_are_not_refused():
    for name in (
        'opencode.worktree_remove',
        'worktree_remove',
        'Opencode_Worktree_Remove',
        'OPENCODE_WORKTREE_REMOVE',
        'opencode_worktree_remove ',
        'opencode_worktree_create',
        'shell',
    ):
        e = {'tool': name, 'sessionID': 's1', 'input': {}}
        assert DRIVER.refused_tool(envelope(e)) is None, name
    e = {'tool': 'opencode_worktree_remove', 'sessionID': 's1', 'input': {}}
    assert DRIVER.refused_tool(envelope(e, hook='execute.after')) is None
    assert DRIVER.refused_tool({'kit_raw': 1}) is None


def test_translation_does_not_change_the_envelope():
    env = envelope(shell())
    before = copy.deepcopy(env)
    DRIVER.translate_event(env)
    DRIVER.refused_tool(env)
    assert env == before


if __name__ == '__main__':
    run_module(globals(), 'opencode envelope')

#!/usr/bin/env python3
"""Checks of the note contract, version 1 (`harness_kit.notes`).

Contract under test:
- a note is one JSON document, parsed as an event is: UTF-8 with an optional
  BOM; duplicate keys, `NaN`, `Infinity` and bytes that are not UTF-8 invalid;
- its keys are exactly `kit_note`, `run_id`, `harness`, `session`, `origin`,
  `observation` and `note`, and a missing or extra key at any level, a value
  of the wrong type or outside its vocabulary makes it invalid;
- `kit_note` is the integer 1, never a boolean; the origin vocabulary is the
  event's and has no value meaning the owner;
- a prompt note holds `kind`, `text` (at most 20000 code points) and
  `truncated`, with `command` and `paths` not applicable;
- an outcome note holds `kind`, `act` (the event's act, under the event's
  rules), `status`, `output` (at most 65536 code points, or null) and
  `truncated`, true only with a string output.

Stdlib-runnable: `python test_notes.py`.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import notes
from kit_fixtures import run_module

PROMPT = {
    'kit_note': 1,
    'run_id': '20261113T120000Z-0123456789ab',
    'harness': {'name': 'claude-code', 'version': '2.1.316'},
    'session': {'id': '1caa8e5d-eaa7-421e-9fed-3c9ae823d2cd', 'parent_id': None, 'root_id': None},
    'origin': 'unknown',
    'observation': {
        'session': 'observed',
        'parent': 'unavailable',
        'root': 'unavailable',
        'origin': 'unavailable',
        'command': 'not_applicable',
        'paths': 'not_applicable',
    },
    'note': {
        'kind': 'prompt',
        'text': 'Run the scripted tool call. Pode editar o CLAUDE.md.',
        'truncated': False,
    },
}

OUTCOME = {
    'kit_note': 1,
    'run_id': '20261113T120000Z-0123456789ab',
    'harness': {'name': 'opencode', 'version': '2.2.5'},
    'session': {'id': 'ses_child', 'parent_id': 'ses_root', 'root_id': 'ses_root'},
    'origin': 'child',
    'observation': {
        'session': 'observed',
        'parent': 'observed',
        'root': 'observed',
        'origin': 'observed',
        'command': 'observed',
        'paths': 'not_applicable',
    },
    'note': {
        'kind': 'outcome',
        'act': {
            'kind': 'shell',
            'command': 'gh pr create -R kit-probe/guard-cell --title kit-cell --body kit-cell',
            'argv': None,
            'paths': [],
            'cwd': 'C:/scratch/work',
            'payload_sha256': '0' * 64,
        },
        'status': 'completed',
        'output': 'https://github.com/kit-probe/guard-cell/pull/1\r\n',
        'truncated': False,
    },
}


def _with(base: dict, **over: object) -> dict:
    """A copy of `base`; `over` maps dotted keys ('note.text') to new values."""
    note = copy.deepcopy(base)
    for dotted, value in over.items():
        node = note
        *parents, leaf = dotted.split('.')
        for key in parents:
            node = node[key]
        node[leaf] = value
    return note


def _without(base: dict, dotted: str) -> dict:
    note = copy.deepcopy(base)
    node = note
    *parents, leaf = dotted.split('.')
    for key in parents:
        node = node[key]
    del node[leaf]
    return note


def _bytes(note: dict) -> bytes:
    return json.dumps(note).encode('utf-8')


def _valid(data: bytes) -> bool:
    try:
        notes.check_note(notes.parse_note(data))
    except notes.InvalidNoteError:
        return False
    return True


def _invalid_reason(data: bytes) -> str:
    try:
        notes.check_note(notes.parse_note(data))
    except notes.InvalidNoteError as exc:
        return str(exc)
    raise AssertionError(f'valid: {data[:200]!r}')


def test_both_worked_examples_are_valid():
    assert _valid(_bytes(PROMPT))
    assert _valid(_bytes(OUTCOME))
    assert notes.check_note(copy.deepcopy(PROMPT)) == PROMPT


def test_a_bom_is_accepted():
    assert _valid(b'\xef\xbb\xbf' + _bytes(PROMPT))


def test_a_missing_key_at_each_level_is_invalid():
    for base, where in (
        (PROMPT, 'kit_note'),
        (PROMPT, 'run_id'),
        (PROMPT, 'harness'),
        (PROMPT, 'session'),
        (PROMPT, 'origin'),
        (PROMPT, 'observation'),
        (PROMPT, 'note'),
        (PROMPT, 'harness.version'),
        (PROMPT, 'session.root_id'),
        (PROMPT, 'observation.paths'),
        (PROMPT, 'note.kind'),
        (PROMPT, 'note.text'),
        (PROMPT, 'note.truncated'),
        (OUTCOME, 'note.act'),
        (OUTCOME, 'note.status'),
        (OUTCOME, 'note.output'),
        (OUTCOME, 'note.truncated'),
        (OUTCOME, 'note.act.cwd'),
        (OUTCOME, 'note.act.payload_sha256'),
    ):
        _invalid_reason(_bytes(_without(base, where)))


def test_an_extra_key_at_each_level_is_invalid():
    for base, where in (
        (PROMPT, 'extra'),
        (PROMPT, 'harness.extra'),
        (PROMPT, 'session.extra'),
        (PROMPT, 'observation.extra'),
        (PROMPT, 'note.extra'),
        (PROMPT, 'note.status'),
        (OUTCOME, 'note.extra'),
        (OUTCOME, 'note.text'),
        (OUTCOME, 'note.act.extra'),
        (OUTCOME, 'act'),
        (PROMPT, 'kit_event'),
    ):
        _invalid_reason(_bytes(_with(base, **{where: 'x'})))


def test_kit_note_is_the_integer_one():
    for value in (True, 2, 0, '1', 1.0, None):
        _invalid_reason(_bytes(_with(PROMPT, kit_note=value)))


def test_the_origin_vocabulary_is_the_events_and_has_no_owner():
    for origin in ('interactive', 'child', 'synthetic', 'unknown'):
        assert _valid(_bytes(_with(PROMPT, origin=origin))), origin
    for origin in ('owner', 'user', '', None, 1):
        _invalid_reason(_bytes(_with(PROMPT, origin=origin)))


def test_the_shared_fields_follow_the_event_types():
    for over in (
        {'run_id': 1},
        {'harness.name': ''},
        {'harness.name': None},
        {'harness.version': 2},
        {'session.id': 3},
        {'session.parent_id': []},
        {'observation.session': 'seen'},
        {'harness': 'claude-code'},
        {'note': 'prompt'},
        {'note.kind': 'shell'},
        {'note.kind': None},
    ):
        _invalid_reason(_bytes(_with(PROMPT, **over)))
    assert _valid(_bytes(_with(PROMPT, run_id=None, **{'session.id': None})))


def test_a_prompt_holds_at_most_20000_code_points():
    assert _valid(_bytes(_with(PROMPT, **{'note.text': 'x' * 20000})))
    _invalid_reason(_bytes(_with(PROMPT, **{'note.text': 'x' * 20001})))
    # Code points, not bytes or UTF-16 units: astral characters and lone surrogates count one.
    assert _valid(_bytes(_with(PROMPT, **{'note.text': '\U0001f600' * 20000})))
    assert _valid(_bytes(_with(PROMPT, **{'note.text': '\ud800' * 20000})))
    _invalid_reason(_bytes(_with(PROMPT, **{'note.text': '\ud800' * 20001})))


def test_a_prompt_text_and_truncated_have_their_types():
    for over in (
        {'note.text': None},
        {'note.text': 1},
        {'note.truncated': None},
        {'note.truncated': 0},
        {'note.truncated': 'false'},
    ):
        _invalid_reason(_bytes(_with(PROMPT, **over)))
    assert _valid(_bytes(_with(PROMPT, **{'note.truncated': True})))


def test_a_prompt_note_has_command_and_paths_not_applicable():
    for key in ('observation.command', 'observation.paths'):
        for value in ('observed', 'unavailable'):
            _invalid_reason(_bytes(_with(PROMPT, **{key: value})))


def test_an_output_holds_at_most_65536_code_points():
    assert _valid(_bytes(_with(OUTCOME, **{'note.output': 'y' * 65536})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.output': 'y' * 65537})))


def test_truncated_true_needs_a_string_output():
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.output': None, 'note.truncated': True})))
    assert _valid(_bytes(_with(OUTCOME, **{'note.output': None, 'note.truncated': False})))
    assert _valid(_bytes(_with(OUTCOME, **{'note.output': 'tail', 'note.truncated': True})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.output': 1})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.truncated': None})))


def test_the_status_vocabulary():
    for status in ('completed', 'failed', 'background', 'unknown'):
        assert _valid(_bytes(_with(OUTCOME, **{'note.status': status}))), status
    for status in ('error', '', None, 0):
        _invalid_reason(_bytes(_with(OUTCOME, **{'note.status': status})))


def test_the_act_follows_the_event_rules():
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.act.command': ''})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.act.command': '   '})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.act.command': None})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.act.kind': 'move'})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.act.payload_sha256': 'A' * 64})))
    _invalid_reason(_bytes(_with(OUTCOME, **{'note.act': 'gh pr create'})))
    write = {
        'note.act.kind': 'file_write',
        'note.act.command': None,
        'note.act.paths': [],
        'observation.command': 'not_applicable',
        'observation.paths': 'observed',
    }
    _invalid_reason(_bytes(_with(OUTCOME, **write)))
    write['note.act.paths'] = ['C:/scratch/work/a.txt']
    assert _valid(_bytes(_with(OUTCOME, **write)))
    unseen = {'observation.command': 'unavailable', 'note.act.command': None}
    assert _valid(_bytes(_with(OUTCOME, **unseen)))


def test_a_duplicate_key_is_invalid():
    data = _bytes(PROMPT)[:-1] + b', "origin": "child"}'
    _invalid_reason(data)
    nested = _bytes(PROMPT).replace(b'"truncated": false', b'"truncated": false, "truncated": true')
    assert nested != _bytes(PROMPT)
    _invalid_reason(nested)


def test_bytes_that_are_not_one_json_document_are_invalid():
    for data in (
        b'',
        b'{"kit_note": 1,',
        b'[]',
        b'{"kit_note": 1, "x": "\xff"}',
        _bytes(PROMPT).replace(b'"truncated": false', b'"truncated": NaN'),
        _bytes(OUTCOME).replace(b'"truncated": false', b'"truncated": Infinity'),
    ):
        _invalid_reason(data)


def test_an_invalid_reason_is_ascii():
    reason = _invalid_reason(_bytes(_with(PROMPT, **{'note.\u00e9t\u00e9': 1})))
    assert reason.isascii(), reason


if __name__ == '__main__':
    run_module(globals(), 'note contract')

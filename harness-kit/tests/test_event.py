#!/usr/bin/env python3
"""Checks of the neutral event contract, version 1.

Contract under test: strict keys at every level, the closed vocabularies for
origin, observation and act kind, the value types, and the rule that a shell
act whose command was observed must carry a command. `validate_event` returns
None for a valid event and a short ASCII reason otherwise.

Stdlib-runnable: `python test_event.py`.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.event import ACT_KINDS, OBSERVATIONS, ORIGINS, validate_event
from kit_fixtures import event, run_module, write_event


def _invalid(ev: object) -> str:
    reason = validate_event(ev)
    assert reason is not None, f'expected invalid: {ev!r}'
    assert reason.isascii(), reason
    return reason


def test_the_sample_event_is_valid():
    assert validate_event(event()) is None


def test_a_write_event_is_valid():
    assert validate_event(write_event(['/w/a.txt'])) is None


def test_vocabularies_are_closed_and_have_no_owner():
    assert set(ORIGINS) == {'interactive', 'child', 'synthetic', 'unknown'}
    assert set(OBSERVATIONS) == {'observed', 'unavailable', 'not_applicable'}
    assert set(ACT_KINDS) == {'shell', 'file_write', 'other', 'unknown'}
    assert 'owner' not in ORIGINS


def test_origin_owner_is_invalid():
    assert 'origin' in _invalid(event(origin='owner'))


def test_each_origin_value_is_valid():
    for origin in ('interactive', 'child', 'synthetic', 'unknown'):
        assert validate_event(event(origin=origin)) is None, origin


def test_a_non_object_is_invalid():
    for value in ([], 'x', 1, None, True):
        _invalid(value)


def test_a_missing_key_at_any_level_is_invalid():
    for path in (
        ('kit_event',),
        ('run_id',),
        ('harness',),
        ('harness', 'name'),
        ('harness', 'version'),
        ('session', 'id'),
        ('session', 'parent_id'),
        ('session', 'root_id'),
        ('origin',),
        ('observation', 'paths'),
        ('observation', 'session'),
        ('act', 'kind'),
        ('act', 'argv'),
        ('act', 'payload_sha256'),
    ):
        ev = event()
        node = ev
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
        _invalid(ev)


def test_an_extra_key_at_any_level_is_invalid():
    for parent in (None, 'harness', 'session', 'observation', 'act'):
        ev = event()
        node = ev if parent is None else ev[parent]
        node['extra'] = 'x'
        _invalid(ev)


def test_kit_event_must_be_the_integer_one():
    for value in (2, 0, '1', True, 1.0, None):
        _invalid(event(kit_event=value))


def test_observation_values_are_closed():
    for field in ('session', 'parent', 'root', 'origin', 'command', 'paths'):
        _invalid(event(**{f'observation.{field}': 'seen'}))
        _invalid(event(**{f'observation.{field}': None}))


def test_act_kind_is_closed():
    _invalid(event(**{'act.kind': 'exec'}))
    for kind in ('other', 'unknown'):
        assert validate_event(event(**{'act.kind': kind})) is None, kind


def test_an_observed_empty_shell_command_is_invalid():
    for command in ('', '   ', None):
        reason = _invalid(event(**{'act.command': command}))
        assert 'command' in reason, reason


def test_an_unobserved_empty_shell_command_is_valid():
    for obs in ('unavailable', 'not_applicable'):
        ev = event(**{'act.command': None, 'observation.command': obs})
        assert validate_event(ev) is None, obs


def test_an_observed_write_with_no_path_is_invalid():
    _invalid(write_event([]))


def test_value_types_are_checked():
    bad = {
        'run_id': 5,
        'harness.name': '',
        'harness.version': 2,
        'session.id': 7,
        'session.parent_id': 1,
        'session.root_id': [],
        'act.command': 5,
        'act.argv': 'echo hi',
        'act.paths': '/w/a',
        'act.cwd': 3,
        'act.payload_sha256': 'A' * 64,
    }
    for key, value in bad.items():
        _invalid(event(**{key: value}))
    _invalid(event(**{'act.argv': ['echo', 1]}))
    _invalid(event(**{'act.paths': ['/w/a', None]}))
    _invalid(event(**{'act.payload_sha256': 'a' * 63}))
    _invalid(event(harness=['claude-code']))
    _invalid(event(observation='observed'))


def test_optional_values_may_be_null_or_set():
    ev = event(
        run_id='20261108T120000Z-0123456789ab',
        **{
            'harness.version': None,
            'session.parent_id': 'p1',
            'act.argv': ['echo', 'hi'],
            'act.cwd': None,
        },
    )
    assert validate_event(ev) is None


def test_validation_does_not_change_the_event():
    ev = event()
    before = copy.deepcopy(ev)
    validate_event(ev)
    assert ev == before


def test_a_non_ascii_key_gives_an_ascii_reason():
    ev = event()
    ev['act']['café'] = 1
    _invalid(ev)


if __name__ == '__main__':
    run_module(globals(), 'neutral event contract')

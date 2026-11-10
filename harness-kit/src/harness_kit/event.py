"""The neutral event, version 1: what a shell tells the kit about one act.

No field is copied from a harness payload; a shell translates its harness's
payload into this shape. The contract is strict: a missing or extra key at any
level, a value outside a closed vocabulary or of the wrong type makes the event
invalid, and an invalid event is judged `unknown` (effect deny).

The origin vocabulary has no value meaning the owner: no payload says who wrote
a prompt, so a claim of one is an invalid event.
"""

from __future__ import annotations

import json
import re

EVENT_VERSION = 1

ORIGINS = ('interactive', 'child', 'synthetic', 'unknown')
OBSERVATIONS = ('observed', 'unavailable', 'not_applicable')
ACT_KINDS = ('shell', 'file_write', 'other', 'unknown')

TOP_KEYS = ('kit_event', 'run_id', 'harness', 'session', 'origin', 'observation', 'act')
HARNESS_KEYS = ('name', 'version')
SESSION_KEYS = ('id', 'parent_id', 'root_id')
OBSERVATION_KEYS = ('session', 'parent', 'root', 'origin', 'command', 'paths')
ACT_KEYS = ('kind', 'command', 'argv', 'paths', 'cwd', 'payload_sha256')

_SHA256 = re.compile(r'[0-9a-f]{64}')


class InvalidEventError(ValueError):
    """The input is not a valid neutral event; the message is ASCII."""


def _keys(value: object, expected: tuple[str, ...], where: str) -> dict:
    if not isinstance(value, dict):
        raise InvalidEventError(f'{where} is not an object')
    missing = [k for k in expected if k not in value]
    extra = sorted(ascii(k) for k in value if k not in expected)
    if missing:
        raise InvalidEventError(f'{where} lacks key(s): {", ".join(missing)}')
    if extra:
        raise InvalidEventError(f'{where} has unknown key(s): {", ".join(extra)}')
    return value


def _str_or_null(value: object, where: str) -> None:
    if value is not None and not isinstance(value, str):
        raise InvalidEventError(f'{where} is neither a string nor null')


def _str_list(value: object, where: str) -> None:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise InvalidEventError(f'{where} is not a list of strings')


def _one_of(value: object, allowed: tuple[str, ...], where: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise InvalidEventError(f'{where} is not one of: {", ".join(allowed)}')


def check_event(ev: object) -> dict:
    """Return the event unchanged when valid; raise InvalidEventError otherwise."""
    ev = _keys(ev, TOP_KEYS, 'event')
    version = ev['kit_event']
    if type(version) is not int or version != EVENT_VERSION:
        raise InvalidEventError(f'kit_event is not {EVENT_VERSION}')
    _str_or_null(ev['run_id'], 'run_id')

    harness = _keys(ev['harness'], HARNESS_KEYS, 'harness')
    if not isinstance(harness['name'], str) or not harness['name']:
        raise InvalidEventError('harness.name is not a non-empty string')
    _str_or_null(harness['version'], 'harness.version')

    session = _keys(ev['session'], SESSION_KEYS, 'session')
    for key in SESSION_KEYS:
        _str_or_null(session[key], f'session.{key}')

    _one_of(ev['origin'], ORIGINS, 'origin')

    observation = _keys(ev['observation'], OBSERVATION_KEYS, 'observation')
    for key in OBSERVATION_KEYS:
        _one_of(observation[key], OBSERVATIONS, f'observation.{key}')

    act = _keys(ev['act'], ACT_KEYS, 'act')
    _one_of(act['kind'], ACT_KINDS, 'act.kind')
    _str_or_null(act['command'], 'act.command')
    if act['argv'] is not None:
        _str_list(act['argv'], 'act.argv')
    _str_list(act['paths'], 'act.paths')
    _str_or_null(act['cwd'], 'act.cwd')
    sha = act['payload_sha256']
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        raise InvalidEventError('act.payload_sha256 is not 64 lowercase hex')

    # A guard that saw nothing must not read as a guard that allowed.
    if observation['command'] == 'observed':
        command = act['command']
        if command is None or (act['kind'] == 'shell' and not command.strip()):
            raise InvalidEventError('act.command is observed but empty')
    if act['kind'] == 'file_write' and observation['paths'] == 'observed' and not act['paths']:
        raise InvalidEventError('act.paths is observed but empty on a file write')
    return ev


def validate_event(ev: object) -> str | None:
    """None for a valid event, else the ASCII reason it is invalid."""
    try:
        check_event(ev)
    except InvalidEventError as exc:
        return str(exc)
    return None


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise InvalidEventError(f'duplicate key {key!a}')
        out[key] = value
    return out


def _no_constant(name: str) -> object:
    raise InvalidEventError(f'{name} is not JSON')


def parse_event(data: bytes) -> object:
    """Decode one JSON document (UTF-8, optional BOM); duplicate keys are invalid."""
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise InvalidEventError('input is not UTF-8') from None
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except ValueError as exc:
        if isinstance(exc, InvalidEventError):
            raise
        raise InvalidEventError(
            f'input is not one JSON document: {getattr(exc, "msg", type(exc).__name__)}'
        ) from None
    except RecursionError:
        raise InvalidEventError('input nests too deeply') from None

"""The session note, version 1: what a shell tells the kit after the fact.

A note carries something that already happened in a session: a submitted
prompt, or the outcome of a finished shell call. It asks for no verdict and
never blocks a session (note-never-decides). The contract is as strict as the
event's: a missing or extra key at any level, a value of the wrong type or
outside its vocabulary makes the note invalid. `run_id`, `harness`, `session`,
`origin` and `observation` follow the event's types and vocabularies, so the
origin has no value meaning the owner, and an outcome's act follows the
event's act rules.

A shell cuts before it sends: a prompt keeps its first 20000 code points, an
output its last 65536. A text or output longer than its cap is invalid; the
kit never cuts.

Under policy version 3 a checker that declares `records` is a recorder of the
kinds it names: `kit note` calls its `record(note, facts)` and keeps what it
returns as the session's facts (`harness_kit.facts`).
"""

from __future__ import annotations

import copy

from harness_kit import checkers, facts
from harness_kit.event import (
    EVENT_VERSION,
    OBSERVATION_KEYS,
    InvalidEventError,
    check_event,
    parse_event,
)

NOTE_VERSION = 1

TOP_KEYS = ('kit_note', 'run_id', 'harness', 'session', 'origin', 'observation', 'note')
NOTE_KINDS = ('prompt', 'outcome')
PROMPT_KEYS = ('kind', 'text', 'truncated')
OUTCOME_KEYS = ('kind', 'act', 'status', 'output', 'truncated')
STATUSES = ('completed', 'failed', 'background', 'unknown')

TEXT_CAP = 20000
OUTPUT_CAP = 65536

# A prompt note has no act; the shared fields are checked through an event
# that carries this inert one.
_NO_ACT = {
    'kind': 'other',
    'command': None,
    'argv': None,
    'paths': [],
    'cwd': None,
    'payload_sha256': '0' * 64,
}


class InvalidNoteError(ValueError):
    """The input is not a valid note; the message is ASCII."""


def _keys(value: object, expected: tuple[str, ...], where: str) -> dict:
    if not isinstance(value, dict):
        raise InvalidNoteError(f'{where} is not an object')
    missing = [k for k in expected if k not in value]
    extra = sorted(ascii(k) for k in value if k not in expected)
    if missing:
        raise InvalidNoteError(f'{where} lacks key(s): {", ".join(missing)}')
    if extra:
        raise InvalidNoteError(f'{where} has unknown key(s): {", ".join(extra)}')
    return value


def _as_event(note: dict, act: dict) -> None:
    ev = {k: note[k] for k in TOP_KEYS if k not in ('kit_note', 'note')}
    ev['kit_event'] = EVENT_VERSION
    ev['act'] = act
    try:
        check_event(ev)
    except InvalidEventError as exc:
        raise InvalidNoteError(str(exc).replace('act.', 'note.act.')) from None


def _prompt(note: dict, body: dict) -> None:
    _keys(body, PROMPT_KEYS, 'note')
    text = body['text']
    if not isinstance(text, str):
        raise InvalidNoteError('note.text is not a string')
    if len(text) > TEXT_CAP:
        raise InvalidNoteError(f'note.text has more than {TEXT_CAP} code points')
    if type(body['truncated']) is not bool:
        raise InvalidNoteError('note.truncated is not a boolean')
    observation = _keys(note['observation'], OBSERVATION_KEYS, 'observation')
    for key in ('command', 'paths'):
        if observation[key] != 'not_applicable':
            raise InvalidNoteError(f'observation.{key} is not not_applicable on a prompt note')
    _as_event(note, dict(_NO_ACT))


def _outcome(note: dict, body: dict) -> None:
    _keys(body, OUTCOME_KEYS, 'note')
    status = body['status']
    if not isinstance(status, str) or status not in STATUSES:
        raise InvalidNoteError(f'note.status is not one of: {", ".join(STATUSES)}')
    output = body['output']
    if output is not None and not isinstance(output, str):
        raise InvalidNoteError('note.output is neither a string nor null')
    if output is not None and len(output) > OUTPUT_CAP:
        raise InvalidNoteError(f'note.output has more than {OUTPUT_CAP} code points')
    truncated = body['truncated']
    if type(truncated) is not bool:
        raise InvalidNoteError('note.truncated is not a boolean')
    if truncated and output is None:
        raise InvalidNoteError('note.truncated is true with a null output')
    if not isinstance(body['act'], dict):
        raise InvalidNoteError('note.act is not an object')
    _as_event(note, body['act'])


def check_note(note: object) -> dict:
    """Return the note unchanged when valid; raise InvalidNoteError otherwise."""
    note = _keys(note, TOP_KEYS, 'note document')
    version = note['kit_note']
    if type(version) is not int or version != NOTE_VERSION:
        raise InvalidNoteError(f'kit_note is not {NOTE_VERSION}')
    body = note['note']
    if not isinstance(body, dict):
        raise InvalidNoteError('note is not an object')
    kind = body.get('kind')
    if not isinstance(kind, str) or kind not in NOTE_KINDS:
        raise InvalidNoteError(f'note.kind is not one of: {", ".join(NOTE_KINDS)}')
    if kind == 'prompt':
        _prompt(note, body)
    else:
        _outcome(note, body)
    return note


def parse_note(data: bytes) -> object:
    """Decode one JSON document as an event is (UTF-8, optional BOM, no duplicate keys)."""
    try:
        return parse_event(data)
    except InvalidEventError as exc:
        raise InvalidNoteError(str(exc)) from None


def note_content(note: dict) -> str | None:
    """The text of a prompt note or the string output of an outcome note, else None."""
    body = note['note']
    return body['text'] if body['kind'] == 'prompt' else body['output']


# ---- recorders (policy version 3)

FACTS = 'facts'
UNCHANGED = 'unchanged'
FAILED = 'failed'
SKIPPED = 'skipped'
TOO_LARGE = 'too-large'
CONFLICT = 'conflict'
RECORD_RESULTS = (FACTS, UNCHANGED, FAILED, SKIPPED, TOO_LARGE, CONFLICT)


def recorders_for(note: dict, checkers) -> tuple:
    """The checkers whose `records` holds the note's kind, in the policy's order."""
    kind = note['note']['kind']
    return tuple(c for c in checkers if kind in c.records)


def record_argument(note: dict) -> dict:
    """What `record` receives as its note: a copy without `run_id` and `session`."""
    return {k: copy.deepcopy(v) for k, v in note.items() if k not in ('run_id', 'session')}


def _record_one(recording, checker, note_arg: dict, root, run_id: str, key: str) -> str:
    path = facts.facts_path(root, run_id, key, checker.id)
    try:
        expected = facts.read_raw(path)
    except OSError:
        return FAILED
    current = facts.decode(expected)
    if current is None:
        return FAILED
    if not recording.can_call():
        return SKIPPED
    result, value = recording.call(checker, note_arg, current)
    for attempt in range(2):
        if result != FACTS:
            return result
        if not facts.fits(value):
            return TOO_LARGE
        try:
            done, now = facts.compare_and_replace(root, run_id, path, expected, value)
        except OSError:  # facts.lock not obtained, or a read or the write failed
            return FAILED
        if done:
            return FACTS
        if attempt == 1:
            return CONFLICT
        current = facts.decode(now)
        if current is None:  # changed under the recorder into what no recorder can read
            return CONFLICT
        expected = now
        result, value = recording.call(checker, note_arg, current)
    return CONFLICT


def record_note(note: dict, recorders, root, run_id: str, key: str) -> list[dict]:
    """Call each recorder on the note in turn; return `{"id", "result"}` per recorder.

    Each recorder reads its facts file (no lock, no retry; unreadable is
    `failed`), is skipped once less than 50 ms of the note's 500 ms is left,
    and is called on copies of the note without `run_id` and `session` and of
    its facts. A new value too large for its file is `too-large`; else it is
    written by compare-and-replace under `facts.lock`, with one more call and
    one more compare when the file changed meanwhile, and a second change is a
    `conflict`. Only the waits on `record` calls draw on the budget.
    """
    recording = checkers.Recording()
    note_arg = record_argument(note)
    out = []
    for checker in recorders:
        try:
            result = _record_one(recording, checker, note_arg, root, run_id, key)
        except Exception:  # a recorder's failure is its own result; a note never decides
            result = FAILED
        out.append({'id': checker.id, 'result': result})
    return out

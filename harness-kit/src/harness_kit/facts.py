"""Session facts: the small per-session values a recording checker keeps inside a run.

Facts exist only inside a minted run. A facts file is
`runs/<run_id>/facts/<16 hex>/<checker id>.json` under the state root, the
folder named by `state.session_folder` of the session's root key. It holds
exactly `{"kit_facts": 1, "facts": OBJECT}`, written by
`state.write_json_atomic`, at most `MAX_BYTES` as that function writes it.

The root key is `session.root_id` when `observation.root` is observed and the
id is a non-empty string; else `session.id` when `observation.session` is
observed and the id is a non-empty string; else there is none and the session
cannot be observed. Events and notes share the rule.

A read gives `{}` for no file, a copy of the object for a sound file, and None
for anything else. Only `kit note` writes facts, by compare-and-replace under
`facts.lock` in the run's `facts/` folder; a judgement reads without any lock,
retrying a sharing error for at most `JUDGE_RETRY_S`, and writes nothing.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from harness_kit import state

FACTS_VERSION = 1
FACTS_DIR = 'facts'
FACTS_LOCK = 'facts.lock'
DOCUMENT_KEYS = ('kit_facts', 'facts')
MAX_BYTES = 65536
JUDGE_RETRY_S = 0.1
LOCK_TIMEOUT = state.LOCK_TIMEOUT
_RETRY_SLEEP = 0.01


class FactsLockError(OSError):
    """`facts.lock` was not obtained in time; the message is ASCII."""


def _id(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def root_key(doc: dict) -> str | None:
    """The root key of a valid event or note, or None when its session cannot be observed."""
    session, observation = doc['session'], doc['observation']
    if observation['root'] == 'observed' and _id(session['root_id']):
        return session['root_id']
    if observation['session'] == 'observed' and _id(session['id']):
        return session['id']
    return None


def facts_dir(root: Path, run_id: str) -> Path:
    """The run's `facts/` folder."""
    return Path(root) / 'runs' / run_id / FACTS_DIR


def lock_path(root: Path, run_id: str) -> Path:
    """The run's `facts.lock`."""
    return facts_dir(root, run_id) / FACTS_LOCK


def facts_path(root: Path, run_id: str, key: str, checker_id: str) -> Path:
    """The facts file of one checker for one session root."""
    return facts_dir(root, run_id) / state.session_folder(key) / f'{checker_id}.json'


def document(value: dict) -> dict:
    """The whole content of a facts file holding `value`."""
    return {'kit_facts': FACTS_VERSION, 'facts': value}


def encode(value: dict) -> bytes:
    """The bytes of a facts file holding `value`, as `state.write_json_atomic` writes them."""
    return state.json_bytes(document(value))


def fits(value: dict) -> bool:
    """True when the file holding `value` is at most `MAX_BYTES`."""
    return len(encode(value)) <= MAX_BYTES


def decode(data: bytes | None) -> dict | None:
    """`{}` for no file (None), the object of a sound file, None for anything else."""
    if data is None:
        return {}
    if len(data) > MAX_BYTES:
        return None
    try:
        doc = json.loads(data.decode('utf-8'))
    except (ValueError, RecursionError):
        return None
    if not isinstance(doc, dict) or sorted(doc) != sorted(DOCUMENT_KEYS):
        return None
    if type(doc['kit_facts']) is not int or doc['kit_facts'] != FACTS_VERSION:
        return None
    value = doc['facts']
    return value if isinstance(value, dict) else None


def _read_bytes(path: Path) -> bytes:
    return Path(path).read_bytes()


def read_raw(path: Path, retry_s: float = 0.0) -> bytes | None:
    """The file's bytes, or None when there is no file.

    A sharing error (`PermissionError`) is retried for at most `retry_s`
    seconds; it and any other error is then raised.
    """
    end = time.monotonic() + retry_s
    while True:
        try:
            return _read_bytes(path)
        except FileNotFoundError:
            return None
        except PermissionError:
            if time.monotonic() >= end:
                raise
            time.sleep(_RETRY_SLEEP)


def read(path: Path, retry_s: float = 0.0) -> dict | None:
    """The facts of one file: `{}`, a fresh object, or None when unreadable."""
    try:
        data = read_raw(path, retry_s)
    except OSError:
        return None
    return decode(data)


def judge_reader(root: Path, run_id: str, key: str) -> Callable[[str], dict | None]:
    """A judgement's reader: a checker id to its facts, read without a lock, writing nothing."""

    def read_for(checker_id: str) -> dict | None:
        return read(facts_path(root, run_id, key, checker_id), JUDGE_RETRY_S)

    return read_for


@contextmanager
def locked(root: Path, run_id: str, timeout: float = LOCK_TIMEOUT) -> Iterator[None]:
    """Hold the run's `facts.lock`, making the `facts/` folder first.

    Raise FactsLockError when it is not obtained within `timeout` seconds, and
    OSError when the folder or the lock file cannot be opened.
    """
    path = lock_path(root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = state.open_lock(path)
    try:
        if not state.acquire(fd, timeout):
            raise FactsLockError(f'facts lock not obtained within {timeout:g} s')
        try:
            yield
        finally:
            state.release(fd)
    finally:
        os.close(fd)


def compare_and_replace(
    root: Path,
    run_id: str,
    path: Path,
    expected: bytes | None,
    value: dict,
    timeout: float = LOCK_TIMEOUT,
) -> tuple[bool, bytes | None]:
    """Replace the facts file with `value` when its bytes still equal `expected`.

    Under `facts.lock`, the file is read again: when its bytes equal
    `expected` (no file and None count as equal) the folders are made and the
    file is written by `state.write_json_atomic`; return (True, None). Else
    nothing is written; return (False, the bytes now on disk). Raise
    FactsLockError when the lock is not obtained in time and OSError when a
    read or the write fails.
    """
    with locked(root, run_id, timeout):
        now = read_raw(path)
        if now != expected:
            return False, now
        path.parent.mkdir(parents=True, exist_ok=True)
        state.write_json_atomic(path, document(value))
        return True, None

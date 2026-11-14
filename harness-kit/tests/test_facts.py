#!/usr/bin/env python3
"""Checks of the session facts store (`harness_kit.facts`).

Contract under test:
- the root key is `session.root_id` when `observation.root` is observed and
  the id a non-empty string; else `session.id` when `observation.session` is
  observed and the id a non-empty string; else there is none;
- a facts file is `runs/<run_id>/facts/<16 hex>/<checker id>.json`, the folder
  named by `state.session_folder(root key)`; the lock is
  `runs/<run_id>/facts/facts.lock`;
- a file holds exactly `{"kit_facts": 1, "facts": OBJECT}` as
  `state.write_json_atomic` writes it, at most 65536 bytes;
- a read gives `{}` for no file, a copy of the object for a sound file, and
  None for anything else; the judgement's read retries a sharing error for at
  most 100 ms, the plain read not at all;
- compare-and-replace writes only when the bytes on disk equal the expected
  ones (both absent count as equal), and makes the folders it needs.

Stdlib-runnable: `python test_facts.py`.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import facts, state
from kit_fixtures import event, run_module

RUN = '20261113T120000Z-0123456789ab'


def test_the_root_key_follows_the_shared_rule():
    ev = event()
    assert facts.root_key(ev) == 's1'
    ev = event(**{'session.root_id': 'r1', 'observation.root': 'observed'})
    assert facts.root_key(ev) == 'r1'
    ev = event(**{'session.root_id': 'r1', 'observation.root': 'unavailable'})
    assert facts.root_key(ev) == 's1'
    ev = event(**{'session.root_id': '', 'observation.root': 'observed'})
    assert facts.root_key(ev) == 's1'
    ev = event(**{'session.root_id': None, 'observation.root': 'observed'})
    assert facts.root_key(ev) == 's1'
    assert facts.root_key(event(**{'session.id': ''})) is None
    assert facts.root_key(event(**{'session.id': None})) is None
    assert facts.root_key(event(**{'observation.session': 'unavailable'})) is None


def test_the_paths_of_a_facts_file_and_of_the_lock():
    root = Path('/state')
    key = 'ses_root'
    path = facts.facts_path(root, RUN, key, 'series-check')
    assert path == root / 'runs' / RUN / 'facts' / state.session_folder(key) / 'series-check.json'
    assert facts.lock_path(root, RUN) == root / 'runs' / RUN / 'facts' / 'facts.lock'


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_a_read_gives_three_answers():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'f' / 'c.json'
        assert facts.read(path) == {}
        path.parent.mkdir()
        state.write_json_atomic(path, facts.document({'a': [1]}))
        assert facts.read(path) == {'a': [1]}
        for bad in (
            b'not json',
            b'[]',
            b'{"kit_facts": 1}',
            b'{"kit_facts": 2, "facts": {}}',
            b'{"kit_facts": true, "facts": {}}',
            b'{"kit_facts": 1, "facts": []}',
            b'{"kit_facts": 1, "facts": {}, "x": 1}',
            b'\xff\xfe',
        ):
            _write(path, bad)
            assert facts.read(path) is None, bad
        big = json.dumps({'kit_facts': 1, 'facts': {'x': 'a' * 65536}}).encode()
        _write(path, big)
        assert facts.read(path) is None
        path.unlink()
        path.mkdir()
        assert facts.read(path) is None


def test_the_size_is_counted_as_write_json_atomic_writes_it():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'c.json'
        value = {'url': ['https://example.invalid/pull/1'], 'n': 2, 'text': 'é'}
        state.write_json_atomic(path, facts.document(value))
        assert facts.encode(value) == path.read_bytes()
        assert facts.fits(value)
        assert not facts.fits({'x': 'a' * 65536})
        exact = {'x': ''}
        room = facts.MAX_BYTES - len(facts.encode(exact))
        exact['x'] = 'a' * room
        assert len(facts.encode(exact)) == facts.MAX_BYTES and facts.fits(exact)
        exact['x'] += 'a'
        assert not facts.fits(exact)


def test_a_read_gives_a_copy():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'c.json'
        state.write_json_atomic(path, facts.document({'a': {'b': 1}}))
        first = facts.read(path)
        first['a']['b'] = 2
        assert facts.read(path) == {'a': {'b': 1}}


class _Flaky:
    """A stand-in for the raw read that raises a sharing error `n` times."""

    def __init__(self, n: int, data: bytes) -> None:
        self.n, self.data, self.calls = n, data, 0

    def __call__(self, path):
        self.calls += 1
        if self.calls <= self.n:
            raise PermissionError(13, 'sharing violation')
        return self.data


def test_the_judgement_read_retries_a_sharing_error_for_at_most_100_ms():
    data = facts.encode({'a': 1})
    saved = facts._read_bytes
    try:
        facts._read_bytes = _Flaky(3, data)
        assert facts.read(Path('x'), retry_s=facts.JUDGE_RETRY_S) == {'a': 1}
        facts._read_bytes = _Flaky(3, data)
        assert facts.read(Path('x')) is None
        facts._read_bytes = _Flaky(10**9, data)
        start = time.monotonic()
        assert facts.read(Path('x'), retry_s=facts.JUDGE_RETRY_S) is None
        assert time.monotonic() - start < 0.5
    finally:
        facts._read_bytes = saved
    assert facts.JUDGE_RETRY_S == 0.1


def test_the_judgement_reader_reads_by_checker_id_and_creates_nothing():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        read = facts.judge_reader(root, RUN, 'k')
        assert read('a') == {}
        assert list(root.iterdir()) == []
        path = facts.facts_path(root, RUN, 'k', 'a')
        path.parent.mkdir(parents=True)
        state.write_json_atomic(path, facts.document({'v': 1}))
        assert read('a') == {'v': 1} and read('b') == {}


def test_compare_and_replace_writes_only_over_the_expected_bytes():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = facts.facts_path(root, RUN, 'k', 'a')
        done, now = facts.compare_and_replace(root, RUN, path, None, {'n': 1})
        assert done and now is None, (done, now)
        first = path.read_bytes()
        assert facts.read(path) == {'n': 1}
        done, now = facts.compare_and_replace(root, RUN, path, None, {'n': 9})
        assert not done and now == first
        assert facts.read(path) == {'n': 1}
        done, _ = facts.compare_and_replace(root, RUN, path, first, {'n': 2})
        assert done and facts.read(path) == {'n': 2}
        assert facts.lock_path(root, RUN).is_file()


def test_compare_and_replace_gives_up_on_a_held_lock():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = facts.facts_path(root, RUN, 'k', 'a')
        with facts.locked(root, RUN):
            start = time.monotonic()
            try:
                facts.compare_and_replace(root, RUN, path, None, {'n': 1}, timeout=0.2)
            except facts.FactsLockError:
                pass
            else:
                raise AssertionError('the lock was taken twice')
            assert time.monotonic() - start < 1.0
        assert not path.exists()


def test_the_document_shape():
    value = {'a': 1}
    doc = facts.document(value)
    assert list(doc) == ['kit_facts', 'facts'] and doc['kit_facts'] == 1
    assert doc['facts'] == value
    assert facts.decode(None) == {}
    assert facts.decode(facts.encode(copy.deepcopy(value))) == value


if __name__ == '__main__':
    run_module(globals(), 'session facts')

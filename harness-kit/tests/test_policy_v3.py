#!/usr/bin/env python3
"""Checks of policy version 3: `records` on a checker table, and a recording checker's load.

Contract under test:
- `version` is 1, 2 or 3; any other version reads `policy version is not 1, 2
  or 3`;
- version 3 is version 2 with one more optional checker key, `records`: a
  non-empty array of distinct strings, each `prompt` or `outcome`;
  `Checker.records` holds them in the order given, and is empty without the
  key;
- a checker with `records` has an id that matches `[a-z0-9][a-z0-9-]{0,62}` and
  is no reserved device name; any other `records`, or such an id, makes the
  whole policy unreadable;
- under versions 1 and 2 `records` is an unknown key, as before;
- `checkers.try_load` requires a callable `record` of a recording checker, with
  the reason `checker '<id>' defines no callable record`; a checker without
  `records` needs none.

Stdlib-runnable: `python test_policy_v3.py`.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import checkers
from harness_kit.policy import PolicyError, load_policy_text
from kit_fixtures import run_module

CHECK = 'def check(act, observation):\n    return {"result": "no-match"}\n'
RECORDING = CHECK + 'def record(note, facts):\n    return {"result": "unchanged"}\n'

RULE = """\
[[rule]]
id = "r"
effect = "deny"
governed = false
kinds = ["shell"]
check = "{id}"
reason = "probe"
"""


def _file(folder: Path, body: str = RECORDING, name: str = 'rule.py') -> tuple[str, str]:
    path = folder / name
    data = body.encode('utf-8')
    path.write_bytes(data)
    return path.as_posix(), hashlib.sha256(data).hexdigest()


def _policy(
    folder: Path,
    version: int = 3,
    records: str | None = '["outcome"]',
    checker_id: str = 'series-check',
    body: str = RECORDING,
) -> str:
    file, sha = _file(folder, body)
    table = (
        f'[[checker]]\nid = "{checker_id}"\nfile = "{file}"\nsha256 = "{sha}"\nbudget_ms = 250\n'
    )
    if records is not None:
        table += f'records = {records}\n'
    return f'version = {version}\n\n' + table + '\n' + RULE.format(id=checker_id)


def _unreadable(text: str) -> str:
    try:
        load_policy_text(text)
    except PolicyError as exc:
        reason = str(exc)
        assert reason.isascii(), reason
        return reason
    raise AssertionError(f'expected unreadable:\n{text}')


def test_version_3_with_records_loads_with_the_kinds_in_order():
    with tempfile.TemporaryDirectory() as td:
        for records, expected in (
            ('["outcome"]', ('outcome',)),
            ('["prompt"]', ('prompt',)),
            ('["outcome", "prompt"]', ('outcome', 'prompt')),
            ('["prompt", "outcome"]', ('prompt', 'outcome')),
        ):
            policy = load_policy_text(_policy(Path(td), records=records))
            assert policy.checkers[0].records == expected, (records, policy.checkers[0])
            assert policy.rules[0].check == 'series-check'


def test_version_3_without_records_loads_with_no_records():
    with tempfile.TemporaryDirectory() as td:
        policy = load_policy_text(_policy(Path(td), records=None, body=CHECK))
        assert policy.checkers[0].records == ()
        assert policy.checkers[0].budget_ms == 250


def test_version_3_with_no_checker_loads():
    policy = load_policy_text('version = 3\n')
    assert policy.rules == () and policy.checkers == ()


def test_versions_1_and_2_have_no_records():
    with tempfile.TemporaryDirectory() as td:
        policy = load_policy_text(_policy(Path(td), version=2, records=None, body=CHECK))
        assert policy.checkers[0].records == ()
    assert load_policy_text('version = 1\n').checkers == ()


def test_records_under_version_2_is_an_unknown_key():
    with tempfile.TemporaryDirectory() as td:
        reason = _unreadable(_policy(Path(td), version=2))
        assert 'unknown key' in reason and 'records' in reason, reason


def test_each_bad_records_makes_the_policy_unreadable():
    with tempfile.TemporaryDirectory() as td:
        for records in (
            '[]',
            '["outcome", "outcome"]',
            '["prompt", "prompt"]',
            '["file"]',
            '["Prompt"]',
            '"outcome"',
            '1',
            '[1]',
            '[["outcome"]]',
            '{kind = "outcome"}',
            'true',
        ):
            _unreadable(_policy(Path(td), records=records))


def test_a_recording_id_that_cannot_name_a_file_is_refused():
    with tempfile.TemporaryDirectory() as td:
        for bad in (
            'Series',
            'a/b',
            'a\\\\b',
            'nul',
            'con',
            'prn',
            'aux',
            'com1',
            'com9',
            'lpt1',
            'lpt9',
            '-lead',
            'a.b',
            'a_b',
            'a' * 64,
        ):
            _unreadable(_policy(Path(td), checker_id=bad))
        for good in ('a', '0', 'series-check', 'a' * 63, 'com0', 'com10', 'nuls', 'lpt'):
            policy = load_policy_text(_policy(Path(td), checker_id=good))
            assert policy.checkers[0].id == good


def test_an_id_without_records_keeps_the_version_2_rule():
    with tempfile.TemporaryDirectory() as td:
        for free in ('Series', 'nul', 'a_b'):
            policy = load_policy_text(_policy(Path(td), records=None, checker_id=free, body=CHECK))
            assert policy.checkers[0].id == free


def test_an_unknown_version_names_1_2_and_3():
    for text in ('version = 4\n', 'version = 0\n', 'version = "3"\n', 'version = true\n'):
        assert _unreadable(text) == 'policy version is not 1, 2 or 3', text


def _checker(folder: Path, body: str, records: str | None):
    return load_policy_text(_policy(folder, records=records, body=body)).checkers[0]


def test_try_load_requires_a_callable_record_of_a_recording_checker():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        assert checkers.try_load(_checker(folder, RECORDING, '["outcome"]')) is None
        for body in (CHECK, CHECK + 'record = 3\n'):
            reason = checkers.try_load(_checker(folder, body, '["prompt"]'))
            assert reason == "checker 'series-check' defines no callable record", reason


def test_try_load_needs_no_record_without_records():
    with tempfile.TemporaryDirectory() as td:
        assert checkers.try_load(_checker(Path(td), CHECK, None)) is None


def test_try_load_names_a_missing_check_before_a_missing_record():
    with tempfile.TemporaryDirectory() as td:
        reason = checkers.try_load(_checker(Path(td), 'X = 1\n', '["outcome"]'))
        assert reason == "checker 'series-check' defines no callable check", reason


if __name__ == '__main__':
    run_module(globals(), 'policy version 3')

#!/usr/bin/env python3
"""Checks of the policy file, versions 1 and 2: load, validation and glob translation.

Contract under test: a policy is read whole before any judgement; `version` is
1 or 2, each rule's `effect` is allow or deny, `kinds` a non-empty list of act
kinds, `governed` a boolean, every `command_regex` compiles and every
`path_glob` entry compiles once translated; any failure makes the whole policy
unreadable. Paths compare in forward-slash form, case-folded on Windows; `**`
spans folders, `*` and `?` do not. Version 2 adds `[[checker]]` tables (`id`,
`file`, `sha256`, optional `budget_ms` from 50 to 500) and a rule key `check`;
the checker file's bytes are read and hashed at load, never executed there.

Stdlib-runnable: `python test_policy.py`.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.policy import (
    PolicyError,
    glob_to_regex,
    load_policy,
    load_policy_text,
    normalize_path,
)
from kit_fixtures import SAMPLE_POLICY, run_module

RULE = """\
[[rule]]
id = "r"
effect = "deny"
governed = true
kinds = ["shell"]
"""


def _unreadable(text: str) -> str:
    try:
        load_policy_text(text)
    except PolicyError as exc:
        reason = str(exc)
        assert reason.isascii(), reason
        return reason
    raise AssertionError(f'expected unreadable:\n{text}')


def test_the_sample_policy_loads():
    policy = load_policy_text(SAMPLE_POLICY)
    assert len(policy.rules) == 1
    rule = policy.rules[0]
    assert rule.id == 'no-config-write'
    assert rule.effect == 'deny'
    assert rule.governed is True
    assert rule.kinds == ('shell', 'file_write')
    assert rule.command_regex is not None
    assert rule.command_regex.search('cat settings.json')
    assert not rule.command_regex.search('cat settingsXjson')
    assert len(rule.path_globs) == 1
    assert rule.origin_in == ('child',)
    assert rule.reason == 'configuration writes are governed'
    assert policy.launcher == {'test_roots': ['/abs/path'], 'forbidden_roots': []}


def test_a_policy_with_no_rule_loads():
    assert load_policy_text('version = 1\n').rules == ()


def test_a_rule_with_kinds_alone_loads():
    rule = load_policy_text('version = 1\n' + RULE).rules[0]
    assert rule.command_regex is None
    assert rule.path_globs is None
    assert rule.origin_in is None
    assert rule.reason == ''


def test_each_unreadable_form_is_refused():
    forms = {
        'toml syntax': 'version = = 1\n',
        'no version': RULE,
        'version 3': 'version = 3\n',
        'version string': 'version = "1"\n',
        'version boolean': 'version = true\n',
        'unknown top key': 'version = 1\nrules = []\n',
        'rule not a table array': 'version = 1\nrule = 3\n',
        'launcher not a table': 'version = 1\nlauncher = 3\n',
        'test_roots not a list': 'version = 1\n[launcher]\ntest_roots = "/a"\n',
        'forbidden_roots with a number': 'version = 1\n[launcher]\nforbidden_roots = [1]\n',
    }
    for label, text in forms.items():
        assert _unreadable(text), label


def _rule(**fields: str) -> str:
    lines = {
        'id': '"r"',
        'effect': '"deny"',
        'governed': 'true',
        'kinds': '["shell"]',
    }
    lines.update(fields)
    body = ''.join(f'{k} = {v}\n' for k, v in lines.items() if v is not None)
    return 'version = 1\n[[rule]]\n' + body


def test_each_unreadable_rule_is_refused():
    forms = {
        'effect block': {'effect': '"block"'},
        'effect missing': {'effect': None},
        'kinds empty': {'kinds': '[]'},
        'kinds unknown': {'kinds': '["exec"]'},
        'kinds string': {'kinds': '"shell"'},
        'kinds missing': {'kinds': None},
        'governed string': {'governed': '"yes"'},
        'governed missing': {'governed': None},
        'id missing': {'id': None},
        'id empty': {'id': '""'},
        'reason number': {'reason': '3'},
        'regex does not compile': {'command_regex': '"("'},
        'regex not a string': {'command_regex': '5'},
        'glob not a list': {'path_glob': '"**/x"'},
        'glob entry a number': {'path_glob': '[5]'},
        'glob bad range': {'path_glob': '["[z-a]"]'},
        'glob open class': {'path_glob': '["[abc"]'},
        'origin owner': {'origin_in': '["owner"]'},
        'origin not a list': {'origin_in': '"child"'},
        'unknown rule key': {'command_regexp': '"x"'},
    }
    for label, fields in forms.items():
        reason = _unreadable(_rule(**fields))
        assert reason, label


def test_one_bad_rule_makes_the_whole_policy_unreadable():
    good = _rule()
    bad = '[[rule]]\nid = "b"\neffect = "deny"\ngoverned = true\nkinds = ["shell"]\n'
    bad += 'command_regex = "["\n'
    _unreadable(good + bad)


def test_load_policy_reads_the_file_and_hashes_its_bytes():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'policy.toml'
        data = SAMPLE_POLICY.encode('utf-8')
        path.write_bytes(data)
        policy = load_policy(path)
    assert policy.sha256 == hashlib.sha256(data).hexdigest()


def test_load_policy_refuses_a_missing_file_and_bad_bytes():
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / 'absent.toml'
        try:
            load_policy(missing)
        except PolicyError as exc:
            assert exc.sha256 is None
        else:
            raise AssertionError('a missing file loaded')
        bad = Path(td) / 'bad.toml'
        bad.write_bytes(b'version = 1\n# \xff\xfe\n')
        try:
            load_policy(bad)
        except PolicyError as exc:
            assert exc.sha256 == hashlib.sha256(bad.read_bytes()).hexdigest()
        else:
            raise AssertionError('non-UTF-8 bytes loaded')


def _matches(glob: str, path: str, windows: bool = False) -> bool:
    regex = glob_to_regex(glob, windows=windows)
    return regex.fullmatch(normalize_path(path, windows=windows)) is not None


def test_double_star_spans_folders():
    assert _matches('**/settings.json', '/w/.claude/settings.json')
    assert _matches('**/settings.json', 'settings.json')
    assert _matches('**/settings.json', '/settings.json')
    assert not _matches('**/settings.json', '/w/settings.json.bak')
    assert not _matches('**/settings.json', '/w/my-settings.json')
    assert _matches('/w/**/b.txt', '/w/b.txt')
    assert _matches('/w/**/b.txt', '/w/x/y/b.txt')
    assert _matches('/w/**', '/w/x/y')


def test_single_star_and_question_mark_stay_in_one_folder():
    assert _matches('/w/*.json', '/w/a.json')
    assert not _matches('/w/*.json', '/w/x/a.json')
    assert _matches('/w/?.txt', '/w/a.txt')
    assert not _matches('/w/?.txt', '/w/ab.txt')
    assert not _matches('/w?x', '/w/x')


def test_character_classes_and_literal_dots():
    assert _matches('/w/[ab].txt', '/w/a.txt')
    assert not _matches('/w/[ab].txt', '/w/c.txt')
    assert _matches('/w/[!ab].txt', '/w/c.txt')
    assert not _matches('/w/[!ab].txt', '/w/a.txt')
    assert not _matches('/w/a.txt', '/w/aXtxt')


def test_paths_compare_in_forward_slash_form():
    assert _matches('**/settings.json', 'C:\\w\\.claude\\settings.json')
    assert _matches('C:/w/**/settings.json', 'C:\\w\\.claude\\settings.json')


def test_case_folds_on_windows_only():
    assert _matches('**/settings.json', 'C:\\W\\SETTINGS.JSON', windows=True)
    assert _matches('C:/W/**', 'c:/w/x', windows=True)
    assert not _matches('**/settings.json', '/w/SETTINGS.JSON', windows=False)


def test_a_version_that_is_neither_1_nor_2_names_both():
    reason = _unreadable('version = 3\n')
    assert '1' in reason and '2' in reason, reason


CHECK_RULE = """\
[[rule]]
id = "r"
effect = "deny"
governed = false
kinds = ["shell"]
check = "c"
reason = "use uv"
"""

MATCH_BODY = 'def check(act, observation):\n    return {"result": "match"}\n'


def _checker_file(folder: Path, body: str = MATCH_BODY) -> tuple[Path, str]:
    path = folder / 'rule_check.py'
    data = body.encode('utf-8')
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def _v2(file: str, sha: str, extra: str = '', rule: str = CHECK_RULE) -> str:
    table = f'[[checker]]\nid = "c"\nfile = "{file}"\nsha256 = "{sha}"\n{extra}'
    return 'version = 2\n\n' + table + '\n' + rule


def test_a_version_2_policy_with_a_checker_loads():
    with tempfile.TemporaryDirectory() as td:
        path, sha = _checker_file(Path(td))
        policy = load_policy_text(_v2(path.as_posix(), sha))
        data = path.read_bytes()
    assert len(policy.checkers) == 1
    checker = policy.checkers[0]
    assert (checker.id, checker.sha256, checker.budget_ms) == ('c', sha, 250)
    assert Path(checker.path) == path
    assert checker.source == data
    assert policy.rules[0].check == 'c'
    assert policy.rules[0].has_matchers


def test_a_version_2_policy_without_checkers_loads():
    policy = load_policy_text('version = 2\n' + RULE)
    assert policy.checkers == ()
    assert policy.rules[0].check is None


def test_a_version_1_policy_has_no_checkers():
    policy = load_policy_text('version = 1\n' + RULE)
    assert policy.checkers == ()
    assert policy.rules[0].check is None


def test_budget_ms_is_read_within_its_range():
    with tempfile.TemporaryDirectory() as td:
        path, sha = _checker_file(Path(td))
        for budget in (50, 500, 123):
            policy = load_policy_text(_v2(path.as_posix(), sha, f'budget_ms = {budget}\n'))
            assert policy.checkers[0].budget_ms == budget


def test_a_relative_file_is_read_beside_the_policy_file():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'packs'
        folder.mkdir()
        path, sha = _checker_file(folder)
        policy_path = Path(td) / 'policy.toml'
        policy_path.write_text(_v2('packs/rule_check.py', sha), encoding='utf-8')
        policy = load_policy(policy_path)
        assert Path(policy.checkers[0].path) == path
        assert Path(policy.checkers[0].path).is_absolute()


def test_load_policy_text_refuses_a_relative_file():
    with tempfile.TemporaryDirectory() as td:
        _path, sha = _checker_file(Path(td))
        _unreadable(_v2('rule_check.py', sha))


def test_each_unreadable_checker_is_refused():
    with tempfile.TemporaryDirectory() as td:
        path, sha = _checker_file(Path(td))
        f = path.as_posix()
        changed = hashlib.sha256(path.read_bytes() + b' ').hexdigest()
        second = f'[[checker]]\nid = "c"\nfile = "{f}"\nsha256 = "{sha}"\n\n[[rule]]'
        forms = {
            'missing file': _v2(Path(td, 'absent.py').as_posix(), sha),
            'unreadable file (a folder)': _v2(Path(td).as_posix(), sha),
            'hash differs': _v2(f, changed),
            'hash in upper case': _v2(f, sha.upper()),
            'hash too short': _v2(f, sha[:63]),
            'repeated id': _v2(f, sha).replace('[[rule]]', second),
            'unknown checker key': _v2(f, sha, 'timeout = 3\n'),
            'budget 49': _v2(f, sha, 'budget_ms = 49\n'),
            'budget 501': _v2(f, sha, 'budget_ms = 501\n'),
            'budget a string': _v2(f, sha, 'budget_ms = "250"\n'),
            'budget a boolean': _v2(f, sha, 'budget_ms = true\n'),
            'budget a float': _v2(f, sha, 'budget_ms = 250.0\n'),
            'check names no checker': _v2(f, sha, rule=CHECK_RULE.replace('"c"', '"other"')),
            'check not a string': _v2(f, sha, rule=CHECK_RULE.replace('"c"', '3')),
            'checker id missing': _v2(f, sha).replace('id = "c"\nfile', 'file'),
            'checker id empty': _v2(f, sha).replace('id = "c"\nfile', 'id = ""\nfile'),
            'checker sha256 missing': _v2(f, sha).replace(f'sha256 = "{sha}"\n', ''),
            'checker file key missing': _v2(f, sha).replace(f'file = "{f}"\n', ''),
            'checker not an array of tables': 'version = 2\nchecker = 3\n',
            'file not a string': _v2(f, sha).replace(f'"{f}"', '3'),
        }
        for label, text in forms.items():
            assert _unreadable(text), label


def test_version_1_knows_neither_checker_nor_check():
    with tempfile.TemporaryDirectory() as td:
        path, sha = _checker_file(Path(td))
        reason = _unreadable(_v2(path.as_posix(), sha).replace('version = 2', 'version = 1'))
        assert 'unknown key' in reason and 'checker' in reason, reason
        reason = _unreadable('version = 1\n' + CHECK_RULE)
        assert 'unknown key' in reason and 'check' in reason, reason


def test_loading_does_not_execute_the_checker():
    with tempfile.TemporaryDirectory() as td:
        marker = Path(td) / 'executed.marker'
        body = f'open({str(marker)!r}, "w").close()\n' + MATCH_BODY
        path, sha = _checker_file(Path(td), body)
        load_policy_text(_v2(path.as_posix(), sha))
        assert not marker.exists()


def test_an_unreadable_checker_carries_the_hash_of_the_policy_bytes():
    with tempfile.TemporaryDirectory() as td:
        path, _sha = _checker_file(Path(td))
        policy_path = Path(td) / 'policy.toml'
        policy_path.write_text(_v2(path.as_posix(), '0' * 64), encoding='utf-8')
        try:
            load_policy(policy_path)
        except PolicyError as exc:
            assert exc.sha256 == hashlib.sha256(policy_path.read_bytes()).hexdigest()
            assert str(exc).isascii()
        else:
            raise AssertionError('a checker with another hash loaded')


if __name__ == '__main__':
    run_module(globals(), 'policy file')

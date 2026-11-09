#!/usr/bin/env python3
"""Checks of the three-state verdict: matcher and rule truth tables, the algorithm.

Contract under test:
- a matcher reads its field's observation: `unavailable` cannot tell,
  `not_applicable` is skipped, `observed` matches or not;
- a rule's result is the first row that holds: any no-match, any cannot-tell,
  at least one match, all matchers skipped (no-match), no matcher (match); an
  act whose kind the rule does not list is a no-match before anything else;
- the algorithm: invalid event or unreadable policy is `unknown`; rules scan in
  file order, the first governed cannot-tell is remembered, a deny match denies,
  an allow match allows unless a cannot-tell was remembered; at the end
  `unknown` if remembered, else `allow` ungoverned;
- the verdict carries exactly the version-1 keys.

Stdlib-runnable: `python test_verdict.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.policy import PolicyError, load_policy_text
from harness_kit.verdict import VERDICT_KEYS, judge, rule_result
from kit_fixtures import SAMPLE_POLICY, event, run_module, write_event

SHA = 'b' * 64


def _policy(*rules: str, sha: str | None = SHA, windows: bool = False):
    return load_policy_text('version = 1\n' + ''.join(rules), windows=windows, sha256=sha)


def _rule(rid: str, effect: str = 'deny', governed: bool = True, **extra: str) -> str:
    lines = [
        '[[rule]]',
        f'id = "{rid}"',
        f'effect = "{effect}"',
        f'governed = {"true" if governed else "false"}',
        extra.pop('kinds', 'kinds = ["shell", "file_write", "other", "unknown"]'),
        f'reason = "reason of {rid}"',
    ]
    lines.extend(extra.values())
    return '\n'.join(lines) + '\n'


def _only_rule(text: str):
    return _policy(text).rules[0]


CMD = 'command_regex = "secret"'
GLOB = 'path_glob = ["**/secret.txt"]'
ORIGIN = 'origin_in = ["child"]'


def _shell(command: str = 'cat secret', obs: str = 'observed', **over: object) -> dict:
    return event(**{'act.command': command, 'observation.command': obs, **over})


def test_command_matcher_truth_table():
    rule = _only_rule(_rule('r', m=CMD))
    assert rule_result(rule, _shell('cat secret')) == 'match'
    assert rule_result(rule, _shell('cat public')) == 'no-match'
    assert rule_result(rule, _shell(None, 'unavailable')) == 'cannot-tell'
    assert rule_result(rule, _shell(None, 'not_applicable')) == 'no-match'


def test_path_matcher_truth_table():
    rule = _only_rule(_rule('r', m=GLOB))
    assert rule_result(rule, write_event(['/w/a.txt', '/w/x/secret.txt'])) == 'match'
    assert rule_result(rule, write_event(['/w/a.txt'])) == 'no-match'
    unavailable = write_event([], **{'observation.paths': 'unavailable'})
    assert rule_result(rule, unavailable) == 'cannot-tell'
    assert rule_result(rule, _shell()) == 'no-match'


def test_origin_matcher_truth_table():
    rule = _only_rule(_rule('r', m=ORIGIN))
    child = {'origin': 'child', 'observation.origin': 'observed'}
    other = {'origin': 'interactive', 'observation.origin': 'observed'}
    assert rule_result(rule, _shell(**child)) == 'match'
    assert rule_result(rule, _shell(**other)) == 'no-match'
    assert rule_result(rule, _shell()) == 'cannot-tell'
    skipped = {'observation.origin': 'not_applicable'}
    assert rule_result(rule, _shell(**skipped)) == 'no-match'


def test_rule_table_a_no_match_beats_a_cannot_tell():
    rule = _only_rule(_rule('r', a=CMD, b=ORIGIN))
    assert rule_result(rule, _shell('cat public')) == 'no-match'


def test_rule_table_a_cannot_tell_beats_a_match():
    rule = _only_rule(_rule('r', a=CMD, b=ORIGIN))
    assert rule_result(rule, _shell('cat secret')) == 'cannot-tell'


def test_rule_table_a_match_with_the_rest_skipped_matches():
    rule = _only_rule(_rule('r', a=CMD, b=GLOB))
    assert rule_result(rule, _shell('cat secret')) == 'match'


def test_rule_table_all_matchers_skipped_is_no_match():
    rule = _only_rule(_rule('r', a=GLOB, b=ORIGIN))
    ev = _shell(**{'observation.origin': 'not_applicable'})
    assert rule_result(rule, ev) == 'no-match'


def test_rule_table_kinds_alone_matches():
    rule = _only_rule(_rule('r'))
    assert rule_result(rule, _shell()) == 'match'
    assert rule_result(rule, write_event(['/w/a'])) == 'match'


def test_an_unlisted_kind_is_no_match_before_any_matcher_is_read():
    rule = _only_rule(_rule('r', kinds='kinds = ["file_write"]', b=ORIGIN))
    assert rule_result(rule, _shell()) == 'no-match'
    rule = _only_rule(_rule('r', kinds='kinds = ["file_write"]'))
    assert rule_result(rule, event(**{'act.kind': 'other'})) == 'no-match'


def test_sample_rule_on_a_shell_act():
    rule = load_policy_text(SAMPLE_POLICY).rules[0]
    write_cmd = 'echo {} > ~/.claude/settings.json'
    assert rule_result(rule, _shell(write_cmd)) == 'cannot-tell'
    assert rule_result(rule, _shell('ls -la')) == 'no-match'
    child = {'origin': 'child', 'observation.origin': 'observed'}
    assert rule_result(rule, _shell(write_cmd, **child)) == 'match'


def test_sample_rule_on_a_write():
    rule = load_policy_text(SAMPLE_POLICY, windows=False).rules[0]
    assert rule_result(rule, write_event(['/w/.claude/settings.json'])) == 'cannot-tell'
    assert rule_result(rule, write_event(['/w/notes.txt'])) == 'no-match'
    child = {'origin': 'child', 'observation.origin': 'observed'}
    assert rule_result(rule, write_event(['/w/.claude/settings.json'], **child)) == 'match'


def _assert_shape(v: dict) -> None:
    assert list(v) == list(VERDICT_KEYS), list(v)
    assert v['kit_verdict'] == 1
    assert v['layer'] == 'cli'
    assert v['run_id'] is None
    assert v['launched'] is False
    assert isinstance(v['reason'], str) and v['reason'].isascii()
    expected_effect = 'allow' if v['verdict'] == 'allow' else 'deny'
    assert v['effect'] == expected_effect, v


def _expect(v: dict, verdict: str, governed: bool, rule: str | None, sha: str | None = SHA):
    _assert_shape(v)
    got = (v['verdict'], v['governed'], v['rule'], v['policy_sha256'])
    assert got == (verdict, governed, rule, sha), v


def test_verdict_keys_are_exactly_version_one():
    assert VERDICT_KEYS == (
        'kit_verdict',
        'verdict',
        'effect',
        'governed',
        'rule',
        'reason',
        'layer',
        'policy_sha256',
        'run_id',
        'launched',
    )


def test_branch_invalid_event_is_unknown():
    v = judge(event(origin='owner'), _policy(_rule('r', effect='allow')))
    _expect(v, 'unknown', True, None)


def test_branch_unreadable_policy_is_unknown():
    v = judge(event(), PolicyError('bad', 'c' * 64))
    _expect(v, 'unknown', True, None, 'c' * 64)
    v = judge(event(), PolicyError('absent'))
    _expect(v, 'unknown', True, None, None)


def test_branch_deny_match_denies():
    v = judge(_shell(), _policy(_rule('d', m=CMD)))
    _expect(v, 'deny', True, 'd')
    assert v['reason'] == 'reason of d'


def test_branch_allow_match_allows():
    v = judge(_shell(), _policy(_rule('a', 'allow', m=CMD), _rule('d')))
    _expect(v, 'allow', True, 'a')


def test_branch_allow_match_after_a_cannot_tell_is_unknown():
    v = judge(_shell(), _policy(_rule('c', m=ORIGIN), _rule('a', 'allow', m=CMD)))
    _expect(v, 'unknown', True, 'c')


def test_branch_deny_match_after_a_cannot_tell_denies():
    v = judge(_shell(), _policy(_rule('c', 'allow', m=ORIGIN), _rule('d', m=CMD)))
    _expect(v, 'deny', True, 'd')


def test_branch_end_with_a_cannot_tell_is_unknown_and_names_the_first():
    v = judge(_shell(), _policy(_rule('c1', m=ORIGIN), _rule('c2', 'allow', m=ORIGIN)))
    _expect(v, 'unknown', True, 'c1')


def test_branch_end_with_nothing_is_ungoverned_allow():
    v = judge(_shell('ls'), _policy(_rule('d', m=CMD)))
    _expect(v, 'allow', False, None)
    _expect(judge(_shell(), _policy()), 'allow', False, None)


def test_branch_an_ungoverned_cannot_tell_is_skipped():
    v = judge(_shell(), _policy(_rule('c', governed=False, m=ORIGIN)))
    _expect(v, 'allow', False, None)
    v = judge(_shell(), _policy(_rule('c', governed=False, m=ORIGIN), _rule('a', 'allow')))
    _expect(v, 'allow', True, 'a')


def test_an_ungoverned_match_carries_its_governed_value():
    v = judge(_shell(), _policy(_rule('d', governed=False)))
    _expect(v, 'deny', False, 'd')


def test_the_first_match_in_file_order_wins():
    v = judge(_shell(), _policy(_rule('d1'), _rule('a', 'allow')))
    _expect(v, 'deny', True, 'd1')


def test_sample_policy_definite_mismatch_with_origin_unavailable_allows():
    policy = load_policy_text(SAMPLE_POLICY, windows=False, sha256=SHA)
    _expect(judge(_shell('ls -la'), policy), 'allow', False, None)
    _expect(judge(write_event(['/w/a.txt']), policy), 'allow', False, None)
    on_config = judge(write_event(['/w/.claude/settings.json']), policy)
    _expect(on_config, 'unknown', True, 'no-config-write')


def test_paths_fold_case_when_the_policy_was_loaded_for_windows():
    policy = _policy(_rule('d', m='path_glob = ["**/Secret.txt"]'), windows=True)
    _expect(judge(write_event(['C:\\W\\SECRET.TXT']), policy), 'deny', True, 'd')
    policy = _policy(_rule('d', m='path_glob = ["**/Secret.txt"]'), windows=False)
    _expect(judge(write_event(['/w/SECRET.TXT']), policy), 'allow', False, None)


if __name__ == '__main__':
    run_module(globals(), 'three-state verdict')

#!/usr/bin/env python3
"""Checks of policy version 4: the optional `[permissions]` table.

Contract under test:
- `version` is 1, 2, 3 or 4; any other version reads `policy version is not 1,
  2, 3 or 4`;
- version 4 is version 3 with one more optional top-level table,
  `[permissions]`: `default` (required: `allow`, `ask` or `deny`) and any number
  of `[[permissions.rule]]` tables with exactly `action` (one of `read`, `edit`,
  `glob`, `grep`, `shell`, `subagent`, `skill`, `question`, `webfetch`,
  `websearch`, `external_directory`), `resource` (a non-empty string) and
  `effect` (`allow`, `ask` or `deny`); any other key or value makes the whole
  policy unreadable; `Policy.permissions` holds the section, None without it;
- under versions 1 to 3 `permissions` is an unknown key, as before;
- a version 4 policy keeps every version 3 form (checkers with `records`);
- the judge ignores the section: an event judges the same under a version 3
  policy and under the same policy as version 4 with a section.

Stdlib-runnable: `python test_policy_v4.py`.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import verdict
from harness_kit.policy import (
    PERMISSION_ACTIONS,
    PermissionRule,
    Permissions,
    PolicyError,
    load_policy_text,
)
from kit_fixtures import SAMPLE_POLICY, event, run_module, write_event

ACTIONS = (
    'read',
    'edit',
    'glob',
    'grep',
    'shell',
    'subagent',
    'skill',
    'question',
    'webfetch',
    'websearch',
    'external_directory',
)
HEAD = 'version = 4\n'


def _section(default: str = '"ask"', rules: str = '') -> str:
    return f'\n[permissions]\ndefault = {default}\n{rules}'


def _rule(action: str = '"shell"', resource: str = '"echo *"', effect: str = '"allow"') -> str:
    return f'\n[[permissions.rule]]\naction = {action}\nresource = {resource}\neffect = {effect}\n'


def _unreadable(text: str) -> str:
    try:
        load_policy_text(text)
    except PolicyError as exc:
        reason = str(exc)
        assert reason.isascii(), reason
        return reason
    raise AssertionError(f'expected unreadable:\n{text}')


def test_the_action_list_is_the_stated_one():
    assert PERMISSION_ACTIONS == ACTIONS, PERMISSION_ACTIONS


def test_a_version_4_policy_without_the_section_loads():
    policy = load_policy_text(HEAD)
    assert policy.permissions is None and policy.rules == ()
    policy = load_policy_text(SAMPLE_POLICY.replace('version = 1', 'version = 4'))
    assert policy.permissions is None and len(policy.rules) == 1


def test_every_default_loads():
    for default in ('allow', 'ask', 'deny'):
        policy = load_policy_text(HEAD + _section(f'"{default}"'))
        assert policy.permissions == Permissions(default=default, rules=()), policy.permissions


def test_every_action_and_effect_loads_in_order():
    rules = ''.join(
        _rule(f'"{action}"', f'"r{n}-*?"', f'"{("allow", "ask", "deny")[n % 3]}"')
        for n, action in enumerate(ACTIONS)
    )
    policy = load_policy_text(HEAD + _section('"deny"', rules))
    assert policy.permissions is not None and policy.permissions.default == 'deny'
    want = tuple(
        PermissionRule(action=action, resource=f'r{n}-*?', effect=('allow', 'ask', 'deny')[n % 3])
        for n, action in enumerate(ACTIONS)
    )
    assert policy.permissions.rules == want, policy.permissions.rules


def test_a_resource_keeps_its_text():
    for resource in ('*', '?', 'echo probe > perm-deny*', 'https://host/*', '*/locked/*', ' x '):
        text = HEAD + _section(rules=_rule(resource=_toml(resource)))
        rule = load_policy_text(text).permissions.rules[0]
        assert rule.resource == resource, rule


def _toml(text: str) -> str:
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def test_a_version_4_policy_keeps_the_version_3_forms():
    with tempfile.TemporaryDirectory() as td:
        body = b'def check(act, observation):\n    return {"result": "no-match"}\n'
        body += b'def record(note, facts):\n    return {"result": "unchanged"}\n'
        path = Path(td) / 'rule.py'
        path.write_bytes(body)
        sha = hashlib.sha256(body).hexdigest()
        text = (
            HEAD
            + f'\n[[checker]]\nid = "rec"\nfile = "{path.as_posix()}"\nsha256 = "{sha}"\n'
            + 'records = ["prompt"]\n'
            + '\n[[rule]]\nid = "r"\neffect = "deny"\ngoverned = false\nkinds = ["shell"]\n'
            + 'check = "rec"\n'
            + _section(rules=_rule())
        )
        policy = load_policy_text(text)
        assert policy.checkers[0].records == ('prompt',)
        assert policy.rules[0].check == 'rec'
        assert policy.permissions is not None and len(policy.permissions.rules) == 1


def test_each_invalid_form_is_unreadable():
    cases = {
        'not a table': HEAD + 'permissions = "ask"\n',
        'an array': HEAD + 'permissions = ["ask"]\n',
        'no default': HEAD + '\n[permissions]\n' + _rule(),
        'only rules': HEAD + _rule(),
        'default other': HEAD + _section('"prompt"'),
        'default upper': HEAD + _section('"Deny"'),
        'default number': HEAD + _section('1'),
        'default array': HEAD + _section('["deny"]'),
        'unknown key': HEAD + _section() + 'mode = "x"\n',
        'rule not array': HEAD + _section() + 'rule = 3\n',
        'rule a table': HEAD + _section() + '\n[permissions.rule]\naction = "shell"\n',
        'rule of strings': HEAD + _section() + 'rule = ["shell"]\n',
        'rule unknown key': HEAD + _section(rules=_rule() + 'id = "x"\n'),
        'no action': HEAD + _section(rules=_rule().replace('action = "shell"\n', '')),
        'no resource': HEAD + _section(rules=_rule().replace('resource = "echo *"\n', '')),
        'no effect': HEAD + _section(rules=_rule().replace('effect = "allow"\n', '')),
        'action execute': HEAD + _section(rules=_rule('"execute"')),
        'action bash': HEAD + _section(rules=_rule('"bash"')),
        'action upper': HEAD + _section(rules=_rule('"Shell"')),
        'action wildcard': HEAD + _section(rules=_rule('"*"')),
        'action write': HEAD + _section(rules=_rule('"write"')),
        'action number': HEAD + _section(rules=_rule('1')),
        'resource empty': HEAD + _section(rules=_rule(resource='""')),
        'resource number': HEAD + _section(rules=_rule(resource='3')),
        'resource array': HEAD + _section(rules=_rule(resource='["*"]')),
        'effect other': HEAD + _section(rules=_rule(effect='"block"')),
        'effect bool': HEAD + _section(rules=_rule(effect='true')),
    }
    for name, text in cases.items():
        reason = _unreadable(text)
        assert reason, name


def test_the_section_is_an_unknown_key_before_version_4():
    for version in (1, 2, 3):
        text = f'version = {version}\n' + _section(rules=_rule())
        reason = _unreadable(text)
        assert reason == "policy has unknown key(s): 'permissions'", (version, reason)


def test_an_unknown_version_names_1_2_3_and_4():
    one_rule = SAMPLE_POLICY.replace('version = 1', 'version = 5')
    assert _unreadable(one_rule) == 'policy version is not 1, 2, 3 or 4'
    for text in ('version = 5\n', 'version = 0\n', 'version = "4"\n', 'version = true\n'):
        assert _unreadable(text) == 'policy version is not 1, 2, 3 or 4', text


def test_the_judge_ignores_the_section():
    v3 = SAMPLE_POLICY.replace('version = 1', 'version = 3')
    v4 = SAMPLE_POLICY.replace('version = 1', 'version = 4') + _section(
        '"deny"', _rule('"shell"', '"*"', '"deny"')
    )
    events = (
        event(**{'act.command': 'cat settings.json', 'origin': 'child'}),
        event(**{'act.command': 'echo hi'}),
        write_event(['/w/settings.json'], origin='child'),
        write_event(['/w/other.txt']),
    )
    for ev in events:
        a = verdict.judge(ev, load_policy_text(v3))
        b = verdict.judge(ev, load_policy_text(v4))
        assert a == b, (ev['act'], a, b)


if __name__ == '__main__':
    run_module(globals(), 'policy version 4')

#!/usr/bin/env python3
"""Checks of opencode's permissions rendered from a policy's `[permissions]` section.

Contract under test (`harness_kit.harnesses.opencode_permissions`):
- `wildcard_match` reads a pattern as opencode 2.2.5 does: `*` any text, `?` one
  character, every other character literal, the whole text matched, letter case
  ignored, back slashes read as forward ones in both, and a pattern ending in a
  space and `*` also matching the text before that space;
- `render(section, base, switches)`: `permissions` is `* * DEFAULT`, then the
  section's allow rules, then its ask rules, then its deny rules, each in the
  section's order, then the switches; without a section the switches alone;
  `policies` is `base`, then one `tool.use` deny `ACTION:RESOURCE` per deny rule
  in the section's order;
- `permissions_sha256` is the SHA-256 of the canonical JSON (sorted keys, no
  spaces) of `{"permissions": ..., "policies": ...}`;
- `canary_refusal` reads both canary commands for `shell` by the last matching
  `permissions` rule and by any matching `tool.use` deny; a deny names the rule
  that gives it, and allow or ask passes (None).

Stdlib-runnable: `python test_opencode_permissions.py`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.harnesses import opencode_permissions as op
from harness_kit.policy import PermissionRule, Permissions
from kit_fixtures import run_module

DENY_CMD = 'echo probe > deny-0123456789abcdef.marker'
ALLOW_CMD = 'echo probe > allow-0123456789abcdef.marker'
SWITCHES = [{'action': 'execute', 'resource': '*', 'effect': 'deny'}]
BASE = [{'action': 'plugin.use', 'resource': '*', 'effect': 'deny'}]


def _s(default: str, *rules: tuple[str, str, str]) -> Permissions:
    return Permissions(default=default, rules=tuple(PermissionRule(*r) for r in rules))


def _st(action: str, resource: str, effect: str) -> dict:
    return {'action': action, 'resource': resource, 'effect': effect}


def test_the_canary_commands_are_the_stated_ones():
    assert op.CANARY_COMMANDS == (DENY_CMD, ALLOW_CMD), op.CANARY_COMMANDS


def test_wildcard_match_reads_patterns_as_opencode_does():
    yes = [
        ('echo probe > m.marker', 'echo probe > m*'),
        ('echo probe > m.marker', '*'),
        ('a/b/c.txt', '*/b/*'),
        ('C:\\w\\locked\\x.txt', '*/locked/*'),
        ('c:/w/locked/x.txt', 'C:\\W\\LOCKED\\*'),
        ('ECHO PROBE', 'echo probe'),
        ('ab', 'a?'),
        ('ls', 'ls *'),
        ('ls -la', 'ls *'),
        ('a.b+c(d)[e]{f}$g^h|i', 'a.b+c(d)[e]{f}$g^h|i'),
        ('line one\nline two', 'line*two'),
        ('https://host/path', 'https://host/*'),
    ]
    no = [
        ('locked/x.txt', '*/locked/*'),
        ('abc', 'a?'),
        ('axb', 'a.b'),
        ('lsx', 'ls *'),
        ('echo probe > m.marker', 'echo probe'),
        ('xecho', 'echo*'),
        ('a(b', 'a\\(b'),
    ]
    for text, pattern in yes:
        assert op.wildcard_match(text, pattern), (text, pattern)
    for text, pattern in no:
        assert not op.wildcard_match(text, pattern), (text, pattern)


def test_render_orders_allow_ask_deny_after_the_default_and_before_the_switches():
    section = _s(
        'deny',
        ('shell', 'd1', 'deny'),
        ('read', 'a1', 'allow'),
        ('edit', 'k1', 'ask'),
        ('shell', 'a2', 'allow'),
        ('webfetch', 'd2', 'deny'),
        ('glob', 'k2', 'ask'),
    )
    permissions, policies = op.render(section, BASE, SWITCHES)
    assert permissions == [
        _st('*', '*', 'deny'),
        _st('read', 'a1', 'allow'),
        _st('shell', 'a2', 'allow'),
        _st('edit', 'k1', 'ask'),
        _st('glob', 'k2', 'ask'),
        _st('shell', 'd1', 'deny'),
        _st('webfetch', 'd2', 'deny'),
        *SWITCHES,
    ], permissions
    assert policies == [
        *BASE,
        _st('tool.use', 'shell:d1', 'deny'),
        _st('tool.use', 'webfetch:d2', 'deny'),
    ], policies


def test_render_without_a_section_gives_the_switches_alone():
    permissions, policies = op.render(None, BASE, SWITCHES)
    assert permissions == SWITCHES and policies == BASE
    permissions, policies = op.render(_s('ask'), BASE, SWITCHES)
    assert permissions == [_st('*', '*', 'ask'), *SWITCHES] and policies == BASE


def test_render_copies_its_inputs():
    base, switches = [dict(BASE[0])], [dict(SWITCHES[0])]
    permissions, policies = op.render(None, base, switches)
    permissions[0]['effect'] = 'allow'
    policies.append({})
    assert switches == SWITCHES and base == BASE


def test_the_hash_is_of_the_canonical_json_of_both_lists():
    permissions, policies = op.render(_s('ask', ('shell', 'x', 'deny')), BASE, SWITCHES)
    text = json.dumps(
        {'permissions': permissions, 'policies': policies}, sort_keys=True, separators=(',', ':')
    )
    want = hashlib.sha256(text.encode('utf-8')).hexdigest()
    assert op.permissions_sha256(permissions, policies) == want
    reordered = [{k: d[k] for k in reversed(list(d))} for d in permissions]
    assert op.permissions_sha256(reordered, policies) == want
    assert op.permissions_sha256(permissions[::-1], policies) != want


def _refusal(section: Permissions | None) -> str | None:
    return op.canary_refusal(*op.render(section, BASE, SWITCHES))


def test_a_section_that_lets_both_canary_calls_through_passes():
    for section in (
        None,
        _s('allow'),
        _s('ask'),
        _s('ask', ('shell', 'echo *', 'ask')),
        _s(
            'deny',
            ('shell', 'echo probe > deny-*', 'allow'),
            ('shell', 'echo probe > allow-*', 'ask'),
        ),
        _s('deny', ('shell', '*', 'allow')),
        _s('allow', ('read', '*', 'deny'), ('edit', '*', 'deny'), ('webfetch', '*', 'deny')),
        _s('allow', ('shell', 'rm *', 'deny'), ('shell', 'echo probe > perm-deny*', 'deny')),
    ):
        assert _refusal(section) is None, section


def test_a_deny_of_either_canary_command_is_refused_naming_the_rule():
    for command, resource in (
        (DENY_CMD, 'echo probe > deny*'),
        (ALLOW_CMD, 'echo probe > allow-*'),
        (ALLOW_CMD, 'ECHO *'),
        (DENY_CMD, 'echo *'),
    ):
        section = _s('allow', ('shell', '*', 'allow'), ('shell', resource, 'deny'))
        reason = _refusal(section)
        assert reason is not None and reason.isascii(), (resource, reason)
        assert f"'{resource}'" in reason and 'deny' in reason and 'shell' in reason, reason
        assert command in reason or 'echo probe' in reason, reason


def test_a_default_deny_without_allows_for_the_canary_is_refused_naming_the_default():
    for section in (
        _s('deny'),
        _s('deny', ('shell', 'echo probe > allow-*', 'allow')),
        _s('deny', ('read', '*', 'allow')),
    ):
        reason = _refusal(section)
        assert reason is not None and 'default' in reason and "'*'" in reason, reason


def test_a_tool_use_deny_alone_refuses_the_canary():
    permissions = [_st('*', '*', 'allow')]
    policies = [*BASE, _st('tool.use', 'shell:echo probe > deny-*', 'deny')]
    reason = op.canary_refusal(permissions, policies)
    assert reason is not None and 'tool.use' in reason and 'shell:echo probe > deny-*' in reason
    policies = [*BASE, _st('tool.use', 'execute:*', 'deny')]
    assert op.canary_refusal(permissions, policies) is None


if __name__ == '__main__':
    run_module(globals(), 'opencode permissions')

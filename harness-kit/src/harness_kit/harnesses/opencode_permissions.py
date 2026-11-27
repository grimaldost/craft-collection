"""opencode's native permissions, rendered from a policy's `[permissions]` section.

The section reads as Claude Code's rules do: a deny beats an ask and an ask beats an
allow, whatever their order. opencode 2.2.5 reads its `permissions` rules in order and
the last matching rule wins, after each shipped agent's own rules, so the render orders
them: `* * DEFAULT`, the section's allow rules, its ask rules, its deny rules (each in the
section's order), then the switches that turn tools off, which stay last so no rule of
the section lifts one. Every deny rule is also rendered as a `tool.use` deny statement
`ACTION:RESOURCE` after the home's other `policies`, since such a statement holds after
an approval saved in the interface. A home rendered from a policy without the section
gets the switches alone, and opencode's own base applies to every other action.

The canary's two shell calls must reach the kit's hook, which refuses the first: under
the rendered rules each resolves to allow or ask (the canary passes `--auto`, which
answers an ask once), else the render and `kit run` refuse, naming the rule.
`wildcard_match` reads a pattern as opencode 2.2.5 does.

`permissions_sha256` hashes the rendered `permissions` and `policies` as canonical JSON;
`home.json` records it, and `kit run` compares a fresh render with it and with the
home's configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from harness_kit.policy import Permissions

CANARY_ACTION = 'shell'
# The canary's two commands, with a nonce of its form (16 hex digits).
CANARY_COMMANDS = (
    'echo probe > deny-0123456789abcdef.marker',
    'echo probe > allow-0123456789abcdef.marker',
)
TOOL_USE = 'tool.use'
EFFECT_ORDER = ('allow', 'ask', 'deny')
# The characters opencode escapes before it turns `*` and `?` into a regular expression.
_SPECIAL = frozenset('.+^${}()|[]\\')


def statement(action: str, resource: str, effect: str) -> dict:
    return {'action': action, 'resource': resource, 'effect': effect}


def _regex(pattern: str) -> re.Pattern[str]:
    """opencode's matcher: back slashes read as forward ones, `*` any text, `?` one
    character, a trailing ` *` optional, the whole text, letter case ignored."""
    text = pattern.replace('\\', '/')
    optional_tail = text.endswith(' *')
    if optional_tail:
        text = text[:-2]
    out = []
    for ch in text:
        if ch == '*':
            out.append('.*')
        elif ch == '?':
            out.append('.')
        else:
            out.append(re.escape(ch) if ch in _SPECIAL or not ch.isalnum() else ch)
    if optional_tail:
        out.append('(?: .*)?')
    return re.compile(''.join(out), re.DOTALL | re.IGNORECASE)


def wildcard_match(text: str, pattern: str) -> bool:
    """Whether opencode 2.2.5 reads `text` as matching `pattern`."""
    return _regex(pattern).fullmatch(text.replace('\\', '/')) is not None


def render(
    section: Permissions | None, base: Iterable[dict], switches: Iterable[dict]
) -> tuple[list[dict], list[dict]]:
    """(`permissions`, `policies`) of a home: `base` is its other statements, `switches` the
    rules that end `permissions`."""
    permissions: list[dict] = []
    policies = [dict(item) for item in base]
    if section is not None:
        permissions.append(statement('*', '*', section.default))
        for effect in EFFECT_ORDER:
            permissions += [
                statement(r.action, r.resource, r.effect)
                for r in section.rules
                if r.effect == effect
            ]
        policies += [
            statement(TOOL_USE, f'{r.action}:{r.resource}', 'deny')
            for r in section.rules
            if r.effect == 'deny'
        ]
    permissions += [dict(item) for item in switches]
    return permissions, policies


def canonical(permissions: object, policies: object) -> bytes:
    """The canonical JSON (sorted keys, no spaces) of both lists."""
    value = {'permissions': permissions, 'policies': policies}
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def permissions_sha256(permissions: object, policies: object) -> str:
    return hashlib.sha256(canonical(permissions, policies)).hexdigest()


def _last(items: Iterable[object], matches) -> dict | None:
    found = None
    for item in items:
        if isinstance(item, dict) and matches(item):
            found = item
    return found


def _strings(item: dict, *keys: str) -> bool:
    return all(isinstance(item.get(k), str) for k in keys)


def _resolve(command: str, permissions: list, policies: list) -> str | None:
    """The rule that refuses `command` for `shell`, named, or None when it reaches the hook."""
    rule = _last(
        permissions,
        lambda r: (
            _strings(r, 'action', 'resource', 'effect')
            and wildcard_match(CANARY_ACTION, r['action'])
            and wildcard_match(command, r['resource'])
        ),
    )
    if rule is not None and rule['effect'] == 'deny':
        if rule['action'] == '*' and rule['resource'] == '*':
            return "the section's default, rule * '*' deny"
        return f'the rule {rule["action"]} {rule["resource"]!a} deny'
    found = _last(
        policies,
        lambda s: (
            _strings(s, 'action', 'resource', 'effect')
            and s['action'] == TOOL_USE
            and wildcard_match(f'{CANARY_ACTION}:{command}', s['resource'])
        ),
    )
    if found is not None and found['effect'] == 'deny':
        return f'the {TOOL_USE} statement {found["resource"]!a} deny'
    return None


def canary_refusal(permissions: list, policies: list) -> str | None:
    """Why the rendered rules would refuse a canary call before the kit's hook sees it,
    naming the rule; None when both calls resolve to allow or ask."""
    for command in CANARY_COMMANDS:
        named = _resolve(command, permissions, policies)
        if named is not None:
            return (
                f"the [permissions] section refuses the canary's shell call {command!a} before "
                f'kit judges it, by {named}; the canary needs allow or ask for both of its calls'
            )
    return None

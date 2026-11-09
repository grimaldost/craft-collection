"""The three-state verdict, version 1, and the judging of one event against a policy.

A rule is read in two steps. First its kinds: an act whose kind is not listed
gives no-match and nothing else is read. Then each optional matcher, by the
observation of the field it reads: `unavailable` cannot tell, `not_applicable`
is skipped, `observed` matches or not. The rule's result is the first row that
holds: any no-match; any cannot-tell; at least one match; all matchers skipped
(no-match); no matcher at all (match).

Rules scan in file order. The first governed rule that cannot tell is
remembered. A deny match denies; an allow match allows unless a cannot-tell was
remembered, which gives `unknown`. At the end: `unknown` when one was
remembered, else an ungoverned `allow`. An invalid event or an unreadable
policy is `unknown`. `unknown` has effect deny.
"""

from __future__ import annotations

from harness_kit.event import InvalidEventError, check_event, parse_event
from harness_kit.policy import Policy, PolicyError, Rule, normalize_path

VERDICT_VERSION = 1
LAYER = 'cli'

VERDICT_KEYS = (
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

MATCH = 'match'
NO_MATCH = 'no-match'
CANNOT_TELL = 'cannot-tell'
SKIPPED = 'skipped'


def make_verdict(
    verdict: str,
    *,
    governed: bool,
    rule: str | None,
    reason: str,
    policy_sha256: str | None,
) -> dict:
    """One verdict with exactly the version-1 keys, in order."""
    return {
        'kit_verdict': VERDICT_VERSION,
        'verdict': verdict,
        'effect': 'allow' if verdict == 'allow' else 'deny',
        'governed': governed,
        'rule': rule,
        'reason': reason,
        'layer': LAYER,
        'policy_sha256': policy_sha256,
        'run_id': None,
        'launched': False,
    }


def unknown_verdict(reason: str, policy_sha256: str | None = None) -> dict:
    """The verdict for an input that could not be judged: unknown, governed, no rule."""
    return make_verdict(
        'unknown', governed=True, rule=None, reason=reason, policy_sha256=policy_sha256
    )


def _matcher(observation: str, test) -> str:
    if observation == 'unavailable':
        return CANNOT_TELL
    if observation == 'not_applicable':
        return SKIPPED
    return MATCH if test() else NO_MATCH


def rule_result(rule: Rule, event: dict, windows: bool = False) -> str:
    """`match`, `no-match` or `cannot-tell` for one rule against one valid event."""
    act = event['act']
    observation = event['observation']
    if act['kind'] not in rule.kinds:
        return NO_MATCH
    results: list[str] = []
    if rule.command_regex is not None:
        regex = rule.command_regex
        results.append(_matcher(observation['command'], lambda: regex.search(act['command'] or '')))
    if rule.path_globs is not None:
        globs = rule.path_globs
        paths = [normalize_path(p, windows) for p in act['paths']]
        results.append(
            _matcher(
                observation['paths'],
                lambda: any(g.fullmatch(p) for p in paths for g in globs),
            )
        )
    if rule.origin_in is not None:
        origins = rule.origin_in
        results.append(_matcher(observation['origin'], lambda: event['origin'] in origins))
    if NO_MATCH in results:
        return NO_MATCH
    if CANNOT_TELL in results:
        return CANNOT_TELL
    if MATCH in results:
        return MATCH
    return NO_MATCH if results else MATCH


def judge(event: object, policy: Policy | PolicyError) -> dict:
    """Judge one event (parsed JSON) against a loaded policy or the error that loading raised."""
    if isinstance(policy, PolicyError):
        return unknown_verdict(f'unreadable policy: {policy}', policy.sha256)
    sha = policy.sha256
    try:
        ev = check_event(event)
    except InvalidEventError as exc:
        return unknown_verdict(f'invalid event: {exc}', sha)

    remembered: Rule | None = None
    for rule in policy.rules:
        result = rule_result(rule, ev, policy.windows)
        if result == CANNOT_TELL:
            if rule.governed and remembered is None:
                remembered = rule
            continue
        if result != MATCH:
            continue
        if rule.effect == 'deny':
            return make_verdict(
                'deny', governed=rule.governed, rule=rule.id, reason=rule.reason, policy_sha256=sha
            )
        if remembered is None:
            return make_verdict(
                'allow', governed=rule.governed, rule=rule.id, reason=rule.reason, policy_sha256=sha
            )
        break
    if remembered is not None:
        return make_verdict(
            'unknown',
            governed=True,
            rule=remembered.id,
            reason=_cannot_tell_reason(remembered),
            policy_sha256=sha,
        )
    return make_verdict(
        'allow', governed=False, rule=None, reason='no rule matched', policy_sha256=sha
    )


def _cannot_tell_reason(rule: Rule) -> str:
    text = f'cannot tell whether rule {rule.id} applies'
    return f'{text}: {rule.reason}' if rule.reason else text


def judge_bytes(data: bytes, policy: Policy | PolicyError) -> dict:
    """Judge the raw bytes of one event; bytes that are not one JSON object are invalid."""
    if isinstance(policy, PolicyError):
        return judge(None, policy)
    try:
        event = parse_event(data)
    except InvalidEventError as exc:
        return unknown_verdict(f'invalid event: {exc}', policy.sha256)
    return judge(event, policy)

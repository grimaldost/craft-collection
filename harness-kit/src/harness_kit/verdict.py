"""The three-state verdict, version 1, and the judging of one event against a policy.

A rule is read in two steps. First its kinds: an act whose kind is not listed
gives no-match and nothing else is read. Then each optional matcher, by the
observation of the field it reads: `unavailable` cannot tell, `not_applicable`
is skipped, `observed` matches or not. The rule's result is the first row that
holds: any no-match; any cannot-tell; at least one match; all matchers skipped
(no-match); no matcher at all (match). The `check` matcher of policy version
2 is read last, and only when no other matcher gave no-match; its result
enters the same table. A deny from a rule whose checker returned a `detail`
carries the detail, one space and the rule's reason.

Rules scan in file order. The first governed rule that cannot tell is
remembered. A deny match denies; an allow match allows unless a cannot-tell was
remembered, which gives `unknown`. At the end: `unknown` when one was
remembered, else an ungoverned `allow`. An invalid event or an unreadable
policy is `unknown`. `unknown` has effect deny.

Ahead of the policy's rules and after the policy loads, an event of a harness
other than Claude Code that was not launched is denied by `launcher.required`.
Then, when the caller passes the canary's nonce, a shell act whose command
names `deny-<nonce>.marker` is denied by `canary.deny`, and one that names
`allow-<nonce>.marker` is allowed by `canary.allow`.
"""

from __future__ import annotations

from harness_kit import checkers
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

LAUNCHER_FREE_HARNESS = 'claude-code'
LAUNCHER_RULE = 'launcher.required'
LAUNCHER_REASON = 'this harness runs only under kit run; start the session with kit run'

CANARY_DENY_RULE = 'canary.deny'
CANARY_ALLOW_RULE = 'canary.allow'
CANARY_DENY_REASON = 'kit canary: this call is refused on purpose'
CANARY_ALLOW_REASON = 'kit canary: this call is allowed on purpose'


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


def rule_result(
    rule: Rule,
    event: dict,
    windows: bool = False,
    checks: checkers.Judgement | None = None,
) -> str:
    """`match`, `no-match` or `cannot-tell` for one rule against one valid event.

    `checks` calls the rule's checker; without it a rule with `check` cannot tell
    once its other matchers leave the checker to decide.
    """
    return _rule_outcome(rule, event, windows, checks)[0]


def _rule_outcome(
    rule: Rule, event: dict, windows: bool, checks: checkers.Judgement | None
) -> tuple[str, str | None]:
    """The rule's result and the checker's detail, if one was returned."""
    act = event['act']
    observation = event['observation']
    if act['kind'] not in rule.kinds:
        return NO_MATCH, None
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
    detail = None
    if rule.check is not None and NO_MATCH not in results:
        if checks is None:
            results.append(CANNOT_TELL)
        else:
            result, detail = checks.call(rule.check, act, observation)
            results.append(result)
    if NO_MATCH in results:
        return NO_MATCH, detail
    if CANNOT_TELL in results:
        return CANNOT_TELL, detail
    if MATCH in results:
        return MATCH, detail
    return (NO_MATCH if results else MATCH), detail


def canary_rule(event: dict, nonce: str | None) -> str | None:
    """`canary.deny`, `canary.allow` or None for one valid event under the canary's nonce."""
    act = event['act']
    if not nonce or act['kind'] != 'shell' or event['observation']['command'] != 'observed':
        return None
    command = act['command'] or ''
    if f'deny-{nonce}.marker' in command:
        return CANARY_DENY_RULE
    if f'allow-{nonce}.marker' in command:
        return CANARY_ALLOW_RULE
    return None


def judge(
    event: object,
    policy: Policy | PolicyError,
    launched: bool | None = None,
    nonce: str | None = None,
) -> dict:
    """Judge one event (parsed JSON) against a loaded policy or the error that loading raised.

    `launched` is whether the event belongs to a run the launcher minted; None
    leaves the launcher rule out (a caller that judges outside the CLI).
    `nonce` is the canary's, when the CLI judges inside a canary run.
    """
    if isinstance(policy, PolicyError):
        return unknown_verdict(f'unreadable policy: {policy}', policy.sha256)
    sha = policy.sha256
    try:
        ev = check_event(event)
    except InvalidEventError as exc:
        return unknown_verdict(f'invalid event: {exc}', sha)
    if launched is False and ev['harness']['name'] != LAUNCHER_FREE_HARNESS:
        return make_verdict(
            'deny', governed=True, rule=LAUNCHER_RULE, reason=LAUNCHER_REASON, policy_sha256=sha
        )
    canary = canary_rule(ev, nonce)
    if canary is not None:
        deny = canary == CANARY_DENY_RULE
        return make_verdict(
            'deny' if deny else 'allow',
            governed=True,
            rule=canary,
            reason=CANARY_DENY_REASON if deny else CANARY_ALLOW_REASON,
            policy_sha256=sha,
        )

    checks = checkers.Judgement(policy.checkers) if policy.checkers else None
    remembered: Rule | None = None
    for rule in policy.rules:
        result, detail = _rule_outcome(rule, ev, policy.windows, checks)
        if result == CANNOT_TELL:
            if rule.governed and remembered is None:
                remembered = rule
            continue
        if result != MATCH:
            continue
        if rule.effect == 'deny':
            return make_verdict(
                'deny',
                governed=rule.governed,
                rule=rule.id,
                reason=_deny_reason(rule, detail),
                policy_sha256=sha,
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


def _deny_reason(rule: Rule, detail: str | None) -> str:
    if detail is None:
        return rule.reason
    return f'{detail} {rule.reason}' if rule.reason else detail


def _cannot_tell_reason(rule: Rule) -> str:
    text = f'cannot tell whether rule {rule.id} applies'
    return f'{text}: {rule.reason}' if rule.reason else text


def judge_bytes(
    data: bytes,
    policy: Policy | PolicyError,
    launched: bool | None = None,
    nonce: str | None = None,
) -> dict:
    """Judge the raw bytes of one event; bytes that are not one JSON object are invalid."""
    if isinstance(policy, PolicyError):
        return judge(None, policy, launched)
    try:
        event = parse_event(data)
    except InvalidEventError as exc:
        return unknown_verdict(f'invalid event: {exc}', policy.sha256)
    return judge(event, policy, launched, nonce)

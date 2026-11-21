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
Then, for a launched event whose run record holds `policy_sha256`, a loaded
policy whose bytes hash otherwise is a governed `unknown` by `config.protected`.
Then, when the caller passes the canary's nonce, a shell act whose command
names `deny-<nonce>.marker` is denied by `canary.deny`, and one that names
`allow-<nonce>.marker` is allowed by `canary.allow`. Then an event whose tool
its harness's driver refuses by name (the caller passes the driver's answer) is
denied by `<harness>.refused-tool` with the reason the driver gives, whatever
the policy's rules say. Then, for a launched event of a harness other than
Claude Code whose run record (the caller passes it) holds `workdir`, an act
whose `cwd` is empty, relative, or outside each of the run's `workdir`, its
`work_tree_top` and its canary's `work` folder is denied by
`launcher.workdir`; a run record that could not be read gives `unknown` there.
Then, for a launched `file_write` act whose run record holds `protected`, a
path at or under one of its paths and under none of `protected_except` is
denied by `config.protected`; paths the act did not observe, or a run record
that could not be read, give `unknown` there. Every harness's run record is
read for this rule and the policy hash. Paths are compared as the policy
compares them, with a folder boundary.

A checker that records notes (policy version 3) is called with its session
facts as a third argument: what the caller's `facts` function gives for its
id, or None without one. A judgement reads facts and never writes them.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable

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

REFUSED_TOOL_SUFFIX = '.refused-tool'

WORKDIR_RULE = 'launcher.workdir'
WORKDIR_REASON = (
    "this session's tool calls start only in the folder kit run launched; "
    'start another kit run for another folder'
)
WORKDIR_UNREADABLE = 'cannot tell where the call may start: the run record could not be read'
PROTECTED_RULE = 'config.protected'
PROTECTED_REASON = "this file governs the session; kit protects it from the session's tools"
PROTECTED_UNAVAILABLE = (
    'cannot tell whether the write reaches a file that governs the session: '
    'its paths were not observed'
)
PROTECTED_UNREADABLE = (
    'cannot tell whether the write reaches a file that governs the session: '
    'the run record could not be read'
)
POLICY_CHANGED_REASON = 'the policy changed after kit run read it'
# What a caller passes as the run record when `run.json` could not be read.
UNREADABLE_RUN = 'unreadable'
_DRIVE_ROOT = re.compile(r'[a-z]:/')


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


def _absolute(path: str, windows: bool) -> bool:
    if windows:
        return bool(_DRIVE_ROOT.match(path)) or path.startswith('//')
    return path.startswith('/')


def _folder_form(path: str, windows: bool) -> str:
    """A path in the policy's form with its `.` and `..` parts resolved; '' for an empty one."""
    path = normalize_path(path, windows)
    return posixpath.normpath(path) if path else ''


def _inside(path: str, folder: str) -> bool:
    base = folder.rstrip('/')
    return path == folder or path.startswith(base + '/')


def workdir_result(
    event: dict, run: dict | str | None, run_dir: str | None, windows: bool
) -> str | None:
    """`deny` or `unknown` from `launcher.workdir` for one launched event, or None when the
    rule does not apply or the act starts in one of the run's folders."""
    if run is None or event['harness']['name'] == LAUNCHER_FREE_HARNESS:
        return None
    if run == UNREADABLE_RUN:
        return 'unknown'
    if not isinstance(run, dict) or 'workdir' not in run:
        return None
    cwd = _folder_form(event['act']['cwd'] or '', windows)
    if not cwd or not _absolute(cwd, windows):
        return 'deny'
    folders = [run.get('workdir'), run.get('work_tree_top')]
    if run_dir:
        folders.append(str(run_dir) + '/canary/work')
    for folder in folders:
        form = _folder_form(folder, windows) if isinstance(folder, str) else ''
        if form and _absolute(form, windows) and _inside(cwd, form):
            return None
    return 'deny'


def _forms(paths: object, windows: bool) -> list[str]:
    """The absolute paths of a list in the policy's form; others are left out."""
    out = []
    for path in paths if isinstance(paths, list) else []:
        form = _folder_form(path, windows) if isinstance(path, str) else ''
        if form and _absolute(form, windows):
            out.append(form)
    return out


def policy_changed(run: dict | str | None, policy: Policy) -> bool:
    """True when the run record holds `policy_sha256` and the loaded policy hashes otherwise."""
    if not isinstance(run, dict) or 'policy_sha256' not in run:
        return False
    return run['policy_sha256'] != policy.sha256


def protected_result(event: dict, run: dict | str | None, windows: bool) -> str | None:
    """`deny` or `unknown` from `config.protected` for one launched event, or None when the
    rule does not apply or no path of the write is protected."""
    act = event['act']
    if run is None or act['kind'] != 'file_write':
        return None
    if run == UNREADABLE_RUN:
        return 'unknown'
    if not isinstance(run, dict) or 'protected' not in run:
        return None
    if event['observation']['paths'] != 'observed':
        return 'unknown'
    protected = _forms(run.get('protected'), windows)
    excepted = _forms(run.get('protected_except'), windows)
    cwd = _folder_form(act['cwd'] or '', windows)
    for path in act['paths']:
        form = _folder_form(path, windows)
        if form and not _absolute(form, windows):
            if not cwd or not _absolute(cwd, windows):
                return 'unknown'
            form = posixpath.normpath(posixpath.join(cwd, form))
        if any(_inside(form, f) for f in excepted):
            continue
        if any(_inside(form, f) for f in protected):
            return 'deny'
    return None


def judge(
    event: object,
    policy: Policy | PolicyError,
    launched: bool | None = None,
    nonce: str | None = None,
    *,
    facts: Callable[[str], dict | None] | None = None,
    refused: tuple[str, str] | None = None,
    run: dict | str | None = None,
    run_dir: str | None = None,
) -> dict:
    """Judge one event (parsed JSON) against a loaded policy or the error that loading raised.

    `launched` is whether the event belongs to a run the launcher minted; None
    leaves the launcher rule out (a caller that judges outside the CLI).
    `nonce` is the canary's, when the CLI judges inside a canary run.
    `facts` maps a recording checker's id to its session facts or None; without
    it every recording checker receives None.
    `refused` is the driver's (tool, reason) for a tool it refuses by name.
    `run` is the run record of a launched event (`UNREADABLE_RUN` when it could not be read)
    and `run_dir` its folder; without a record `launcher.workdir` is left out.
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
    if launched is True and policy_changed(run, policy):
        return make_verdict(
            'unknown',
            governed=True,
            rule=PROTECTED_RULE,
            reason=POLICY_CHANGED_REASON,
            policy_sha256=sha,
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
    if refused is not None:
        return make_verdict(
            'deny',
            governed=True,
            rule=ev['harness']['name'] + REFUSED_TOOL_SUFFIX,
            reason=refused[1],
            policy_sha256=sha,
        )
    bound = workdir_result(ev, run, run_dir, policy.windows) if launched is True else None
    if bound is not None:
        return make_verdict(
            bound,
            governed=True,
            rule=WORKDIR_RULE,
            reason=WORKDIR_REASON if bound == 'deny' else WORKDIR_UNREADABLE,
            policy_sha256=sha,
        )
    guarded = protected_result(ev, run, policy.windows) if launched is True else None
    if guarded is not None:
        if guarded == 'deny':
            reason = PROTECTED_REASON
        elif run == UNREADABLE_RUN:
            reason = PROTECTED_UNREADABLE
        else:
            reason = PROTECTED_UNAVAILABLE
        return make_verdict(
            guarded, governed=True, rule=PROTECTED_RULE, reason=reason, policy_sha256=sha
        )

    checks = checkers.Judgement(policy.checkers, facts=facts) if policy.checkers else None
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
    *,
    facts: Callable[[str], dict | None] | None = None,
    run: dict | str | None = None,
    run_dir: str | None = None,
) -> dict:
    """Judge the raw bytes of one event; bytes that are not one JSON object are invalid."""
    if isinstance(policy, PolicyError):
        return judge(None, policy, launched)
    try:
        event = parse_event(data)
    except InvalidEventError as exc:
        return unknown_verdict(f'invalid event: {exc}', policy.sha256)
    return judge(event, policy, launched, nonce, facts=facts, run=run, run_dir=run_dir)

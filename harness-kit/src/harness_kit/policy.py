"""The policy file, versions 1 and 2 (TOML): load, validate and compile it whole.

A policy is read whole before any judgement. Any failure (TOML syntax, a wrong
version, an unknown key, a bad effect, kinds or governed value, a regular
expression or glob that does not compile) makes the whole policy unreadable,
which the judge turns into a verdict of `unknown`.

Version 2 adds `[[checker]]` tables and the rule key `check`, which names one
of them. A checker table holds exactly `id`, `file`, `sha256` and, optionally,
`budget_ms`. Its file is absolute or relative to the folder of the policy file
(a policy loaded from text accepts only an absolute one). At load the file's
bytes are read and hashed, and kept for the judge to execute; loading never
executes them. A missing or unreadable file or a hash that differs makes the
whole policy unreadable.

Paths are compared in forward-slash form, case-folded on Windows. In a glob,
`**` spans folders, while `*` and `?` stay inside one folder; `[...]` is a
character class (`[!...]` negated) that never matches a slash.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

from harness_kit.event import ACT_KINDS, ORIGINS

POLICY_VERSION = 1
POLICY_VERSIONS = (1, 2)

EFFECTS = ('allow', 'deny')
TOP_KEYS = ('version', 'launcher', 'rule')
LAUNCHER_LISTS = ('test_roots', 'forbidden_roots')
RULE_REQUIRED = ('id', 'effect', 'governed', 'kinds')
RULE_OPTIONAL = ('command_regex', 'path_glob', 'origin_in', 'reason')
CHECKER_REQUIRED = ('id', 'file', 'sha256')
CHECKER_OPTIONAL = ('budget_ms',)
BUDGET_MIN_MS = 50
BUDGET_MAX_MS = 500
BUDGET_DEFAULT_MS = 250
_SHA256 = re.compile('[0-9a-f]{64}')


class PolicyError(ValueError):
    """The policy is unreadable; the message is ASCII, `sha256` names the bytes read."""

    def __init__(self, message: str, sha256: str | None = None) -> None:
        super().__init__(message)
        self.sha256 = sha256


@dataclass(frozen=True)
class Rule:
    id: str
    effect: str
    governed: bool
    kinds: tuple[str, ...]
    command_regex: re.Pattern[str] | None = None
    path_globs: tuple[re.Pattern[str], ...] | None = None
    origin_in: tuple[str, ...] | None = None
    reason: str = ''
    check: str | None = None

    @property
    def has_matchers(self) -> bool:
        return (
            self.command_regex is not None
            or self.path_globs is not None
            or self.origin_in is not None
            or self.check is not None
        )


@dataclass(frozen=True)
class Checker:
    """One checker table: `path` is absolute, `source` the bytes that hash to `sha256`."""

    id: str
    path: str
    sha256: str
    budget_ms: int = BUDGET_DEFAULT_MS
    source: bytes = field(default=b'', repr=False)


@dataclass(frozen=True)
class Policy:
    rules: tuple[Rule, ...]
    launcher: dict = field(default_factory=dict)
    sha256: str | None = None
    windows: bool = False
    checkers: tuple[Checker, ...] = ()


def _is_windows(windows: bool | None) -> bool:
    return os.name == 'nt' if windows is None else windows


def normalize_path(path: str, windows: bool | None = None) -> str:
    """Forward-slash form, case-folded on Windows."""
    path = path.replace('\\', '/')
    return path.casefold() if _is_windows(windows) else path


def _class_to_regex(glob: str, start: int) -> tuple[str, int]:
    """Translate the character class opening at `start`; return it and the index after."""
    k = start + 1
    negate = k < len(glob) and glob[k] == '!'
    if negate:
        k += 1
    first = k
    if k < len(glob) and glob[k] == ']':
        k += 1
    end = glob.find(']', k)
    if end < 0:
        raise PolicyError(f'glob {glob!a} has an unclosed [')
    body = glob[first:end]
    body = body.replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
    if not negate and body.startswith('^'):
        body = '\\' + body
    return (f'[^{body}/]' if negate else f'(?!/)[{body}]'), end + 1


def glob_to_regex(glob: str, windows: bool | None = None) -> re.Pattern[str]:
    """Compile a path glob to a regular expression for `fullmatch` on a normalized path."""
    g = normalize_path(glob, windows)
    out: list[str] = []
    i = 0
    while i < len(g):
        c = g[i]
        if g.startswith('**/', i):
            out.append('(?:.*/)?')
            i += 3
        elif g.startswith('**', i):
            out.append('.*')
            i += 2
        elif c == '*':
            out.append('[^/]*')
            i += 1
        elif c == '?':
            out.append('[^/]')
            i += 1
        elif c == '[':
            part, i = _class_to_regex(g, i)
            out.append(part)
        else:
            out.append(re.escape(c))
            i += 1
    try:
        return re.compile('(?s:' + ''.join(out) + ')')
    except re.error as exc:
        raise PolicyError(f'glob {glob!a} does not compile: {exc}') from None


def _str_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise PolicyError(f'{where} is not a list of strings')
    return value


def _rule(raw: object, n: int, windows: bool, checker_ids: tuple[str, ...] | None) -> Rule:
    """One rule; `checker_ids` is None under version 1, where `check` is an unknown key."""
    where = f'rule {n}'
    if not isinstance(raw, dict):
        raise PolicyError(f'{where} is not a table')
    known = RULE_REQUIRED + RULE_OPTIONAL + (('check',) if checker_ids is not None else ())
    unknown = sorted(ascii(k) for k in raw if k not in known)
    if unknown:
        raise PolicyError(f'{where} has unknown key(s): {", ".join(unknown)}')
    missing = [k for k in RULE_REQUIRED if k not in raw]
    if missing:
        raise PolicyError(f'{where} lacks key(s): {", ".join(missing)}')
    rule_id = raw['id']
    if not isinstance(rule_id, str) or not rule_id:
        raise PolicyError(f'{where}: id is not a non-empty string')
    where = f'rule {rule_id!a}'
    if raw['effect'] not in EFFECTS:
        raise PolicyError(f'{where}: effect is not one of: {", ".join(EFFECTS)}')
    if not isinstance(raw['governed'], bool):
        raise PolicyError(f'{where}: governed is not a boolean')
    kinds = _str_list(raw['kinds'], f'{where}: kinds')
    if not kinds or any(k not in ACT_KINDS for k in kinds):
        raise PolicyError(f'{where}: kinds is not a non-empty list of: {", ".join(ACT_KINDS)}')
    reason = raw.get('reason', '')
    if not isinstance(reason, str):
        raise PolicyError(f'{where}: reason is not a string')

    command_regex = None
    if 'command_regex' in raw:
        if not isinstance(raw['command_regex'], str):
            raise PolicyError(f'{where}: command_regex is not a string')
        try:
            command_regex = re.compile(raw['command_regex'])
        except re.error as exc:
            raise PolicyError(f'{where}: command_regex does not compile: {exc}') from None
    path_globs = None
    if 'path_glob' in raw:
        globs = _str_list(raw['path_glob'], f'{where}: path_glob')
        path_globs = tuple(glob_to_regex(g, windows) for g in globs)
    origin_in = None
    if 'origin_in' in raw:
        origins = _str_list(raw['origin_in'], f'{where}: origin_in')
        if any(o not in ORIGINS for o in origins):
            raise PolicyError(f'{where}: origin_in is not a list of: {", ".join(ORIGINS)}')
        origin_in = tuple(origins)
    check = None
    if 'check' in raw:
        check = raw['check']
        if not isinstance(check, str) or check not in (checker_ids or ()):
            raise PolicyError(f'{where}: check names no declared checker')
    return Rule(
        id=rule_id,
        effect=raw['effect'],
        governed=raw['governed'],
        kinds=tuple(kinds),
        command_regex=command_regex,
        path_globs=path_globs,
        origin_in=origin_in,
        reason=reason,
        check=check,
    )


def _checker(raw: object, n: int, folder: Path | None) -> Checker:
    where = f'checker {n}'
    if not isinstance(raw, dict):
        raise PolicyError(f'{where} is not a table')
    unknown = sorted(ascii(k) for k in raw if k not in CHECKER_REQUIRED + CHECKER_OPTIONAL)
    if unknown:
        raise PolicyError(f'{where} has unknown key(s): {", ".join(unknown)}')
    missing = [k for k in CHECKER_REQUIRED if k not in raw]
    if missing:
        raise PolicyError(f'{where} lacks key(s): {", ".join(missing)}')
    checker_id = raw['id']
    if not isinstance(checker_id, str) or not checker_id:
        raise PolicyError(f'{where}: id is not a non-empty string')
    where = f'checker {checker_id!a}'
    file = raw['file']
    if not isinstance(file, str) or not file:
        raise PolicyError(f'{where}: file is not a non-empty string')
    sha = raw['sha256']
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        raise PolicyError(f'{where}: sha256 is not 64 lowercase hex digits')
    budget = raw.get('budget_ms', BUDGET_DEFAULT_MS)
    if type(budget) is not int or not BUDGET_MIN_MS <= budget <= BUDGET_MAX_MS:
        raise PolicyError(
            f'{where}: budget_ms is not an integer from {BUDGET_MIN_MS} to {BUDGET_MAX_MS}'
        )
    path = Path(file)
    if not path.is_absolute():
        if folder is None:
            raise PolicyError(f'{where}: file is not absolute and the policy has no folder')
        path = folder / path
    path = Path(os.path.abspath(path))
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise PolicyError(f'{where}: file cannot be read: {type(exc).__name__}') from None
    if hashlib.sha256(source).hexdigest() != sha:
        raise PolicyError(f'{where}: file bytes do not match its sha256')
    return Checker(id=checker_id, path=str(path), sha256=sha, budget_ms=budget, source=source)


def _checkers(data: dict, folder: Path | None) -> tuple[Checker, ...]:
    raw_checkers = data.get('checker', [])
    if not isinstance(raw_checkers, list):
        raise PolicyError('checker is not an array of tables')
    checkers = tuple(_checker(raw, n, folder) for n, raw in enumerate(raw_checkers, 1))
    seen: set[str] = set()
    for checker in checkers:
        if checker.id in seen:
            raise PolicyError(f'checker id {checker.id!a} is repeated')
        seen.add(checker.id)
    return checkers


def load_policy_text(
    text: str,
    windows: bool | None = None,
    sha256: str | None = None,
    folder: str | os.PathLike[str] | None = None,
) -> Policy:
    """Parse and validate a whole policy; raise PolicyError when any part fails.

    `folder` is where a relative checker `file` is read from; without it only
    an absolute one is accepted.
    """
    win = _is_windows(windows)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f'policy is not valid TOML: {exc}', sha256) from None
    try:
        version = data.get('version')
        v2 = type(version) is int and version == 2
        top_keys = TOP_KEYS + (('checker',) if v2 else ())
        unknown = sorted(ascii(k) for k in data if k not in top_keys)
        if unknown:
            raise PolicyError(f'policy has unknown key(s): {", ".join(unknown)}')
        if type(version) is not int or version not in POLICY_VERSIONS:
            raise PolicyError('policy version is not 1 or 2')
        launcher = data.get('launcher', {})
        if not isinstance(launcher, dict):
            raise PolicyError('launcher is not a table')
        for key in LAUNCHER_LISTS:
            if key in launcher:
                _str_list(launcher[key], f'launcher.{key}')
        raw_rules = data.get('rule', [])
        if not isinstance(raw_rules, list):
            raise PolicyError('rule is not an array of tables')
        checkers: tuple[Checker, ...] = ()
        checker_ids = None
        if v2:
            checkers = _checkers(data, None if folder is None else Path(folder))
            checker_ids = tuple(c.id for c in checkers)
        rules = tuple(_rule(raw, n, win, checker_ids) for n, raw in enumerate(raw_rules, 1))
    except PolicyError as exc:
        exc.sha256 = sha256
        raise
    return Policy(rules=rules, launcher=launcher, sha256=sha256, windows=win, checkers=checkers)


def load_policy(path: str | os.PathLike[str], windows: bool | None = None) -> Policy:
    """Read a policy file whole; `sha256` of the returned policy hashes its bytes."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise PolicyError(f'policy file cannot be read: {type(exc).__name__}') from None
    digest = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise PolicyError('policy file is not UTF-8', digest) from None
    folder = Path(os.path.abspath(path)).parent
    return load_policy_text(text, windows=windows, sha256=digest, folder=folder)

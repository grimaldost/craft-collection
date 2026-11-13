"""The policy file, version 1 (TOML): load, validate and compile it whole.

A policy is read whole before any judgement. Any failure (TOML syntax, a wrong
version, an unknown key, a bad effect, kinds or governed value, a regular
expression or glob that does not compile) makes the whole policy unreadable,
which the judge turns into a verdict of `unknown`.

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

EFFECTS = ('allow', 'deny')
TOP_KEYS = ('version', 'launcher', 'rule')
LAUNCHER_LISTS = ('test_roots', 'forbidden_roots')
RULE_REQUIRED = ('id', 'effect', 'governed', 'kinds')
RULE_OPTIONAL = ('command_regex', 'path_glob', 'origin_in', 'reason')


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

    @property
    def has_matchers(self) -> bool:
        return (
            self.command_regex is not None
            or self.path_globs is not None
            or self.origin_in is not None
        )


@dataclass(frozen=True)
class Policy:
    rules: tuple[Rule, ...]
    launcher: dict = field(default_factory=dict)
    sha256: str | None = None
    windows: bool = False


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


def _rule(raw: object, n: int, windows: bool) -> Rule:
    where = f'rule {n}'
    if not isinstance(raw, dict):
        raise PolicyError(f'{where} is not a table')
    unknown = sorted(ascii(k) for k in raw if k not in RULE_REQUIRED + RULE_OPTIONAL)
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
    return Rule(
        id=rule_id,
        effect=raw['effect'],
        governed=raw['governed'],
        kinds=tuple(kinds),
        command_regex=command_regex,
        path_globs=path_globs,
        origin_in=origin_in,
        reason=reason,
    )


def load_policy_text(text: str, windows: bool | None = None, sha256: str | None = None) -> Policy:
    """Parse and validate a whole policy; raise PolicyError when any part fails."""
    win = _is_windows(windows)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f'policy is not valid TOML: {exc}', sha256) from None
    try:
        unknown = sorted(ascii(k) for k in data if k not in TOP_KEYS)
        if unknown:
            raise PolicyError(f'policy has unknown key(s): {", ".join(unknown)}')
        version = data.get('version')
        if type(version) is not int or version != POLICY_VERSION:
            raise PolicyError(f'policy version is not {POLICY_VERSION}')
        launcher = data.get('launcher', {})
        if not isinstance(launcher, dict):
            raise PolicyError('launcher is not a table')
        for key in LAUNCHER_LISTS:
            if key in launcher:
                _str_list(launcher[key], f'launcher.{key}')
        raw_rules = data.get('rule', [])
        if not isinstance(raw_rules, list):
            raise PolicyError('rule is not an array of tables')
        rules = tuple(_rule(raw, n, win) for n, raw in enumerate(raw_rules, 1))
    except PolicyError as exc:
        exc.sha256 = sha256
        raise
    return Policy(rules=rules, launcher=launcher, sha256=sha256, windows=win)


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
    return load_policy_text(text, windows=windows, sha256=digest)

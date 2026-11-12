"""Rule packs and `kit policy build`: compose one version 2 policy from a base and packs.

A pack is a folder holding `pack.toml` and the checker files it names:
`pack = 1`, a `name`, `[[checker]]` tables (`id`, `file` relative to the pack
with no `..` segment, optional `budget_ms`), `[[rule]]` tables with the keys of
a policy rule, and an optional `[prevention]` table (`rule`, `layer`) that the
doctor reads.

The build writes the base's `launcher` table, the base's rules then each
pack's rules in argument order, and every checker with its `file` absolute in
forward-slash form and its `sha256` computed from its bytes now. The standard
library has no TOML writer, so this module emits its own: basic strings with
every character outside U+0020..U+007E escaped, keys in a fixed order, LF line
ends; the same inputs give the same bytes. Beside the policy it writes
`<out>.packs.json`, which records the packs and the hash of the policy.

Every checker is loaded once to test it, as `kit run` does before a launch
(`verify_checkers`); nothing is written unless every input is sound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

import tomllib

from harness_kit import checkers
from harness_kit.policy import (
    BUDGET_DEFAULT_MS,
    LAUNCHER_LISTS,
    RULE_OPTIONAL,
    RULE_REQUIRED,
    Checker,
    PolicyError,
    load_policy,
    load_policy_text,
)

EXIT_REFUSED = 64
EXIT_INTERNAL = 70

PACK_FILE = 'pack.toml'
PACK_VERSION = 1
PACK_KEYS = ('pack', 'name', 'checker', 'rule', 'prevention')
PACK_CHECKER_REQUIRED = ('id', 'file')
PACK_CHECKER_OPTIONAL = ('budget_ms',)
PREVENTION_KEYS = ('rule', 'layer')
RULE_KEYS = RULE_REQUIRED + RULE_OPTIONAL + ('check',)
# The order a rule's keys are written in; every key a version 2 rule may hold.
RULE_ORDER = (
    'id',
    'effect',
    'governed',
    'kinds',
    'command_regex',
    'path_glob',
    'origin_in',
    'check',
    'reason',
)
SIDECAR_SUFFIX = '.packs.json'
SIDECAR_VERSION = 1


class BuildError(ValueError):
    """An input of the build is refused; the message is ASCII."""


@dataclass(frozen=True)
class CheckerEntry:
    """A checker as the build writes it: `file` absolute, forward slashes."""

    id: str
    file: str
    sha256: str
    budget_ms: object


@dataclass(frozen=True)
class Pack:
    name: str
    folder: str
    checkers: tuple[CheckerEntry, ...]
    rules: tuple[dict, ...]
    prevention: dict | None


def forward(path: str | os.PathLike[str]) -> str:
    """An absolute path in forward-slash form."""
    return os.path.abspath(path).replace('\\', '/')


def toml_string(text: str) -> str:
    """A TOML basic string; every character outside U+0020..U+007E is escaped."""
    out = ['"']
    for ch in text:
        code = ord(ch)
        if ch == '\\':
            out.append('\\\\')
        elif ch == '"':
            out.append('\\"')
        elif 0x20 <= code <= 0x7E:
            out.append(ch)
        elif 0xD800 <= code <= 0xDFFF:
            raise BuildError(f'string {text!a} holds a surrogate, which TOML cannot carry')
        elif code <= 0xFFFF:
            out.append(f'\\u{code:04X}')
        else:
            out.append(f'\\U{code:08X}')
    out.append('"')
    return ''.join(out)


def toml_value(value: object) -> str:
    """A string, boolean, integer or array of them, in TOML."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return toml_string(value)
    if isinstance(value, list):
        return '[' + ', '.join(toml_value(v) for v in value) + ']'
    raise BuildError(f'a value of type {type(value).__name__!a} cannot be written')


def _read_toml(path: Path, what: str) -> dict:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BuildError(f'{what} cannot be read: {type(exc).__name__}') from None
    try:
        return tomllib.loads(data.decode('utf-8'))
    except UnicodeDecodeError:
        raise BuildError(f'{what} is not UTF-8') from None
    except tomllib.TOMLDecodeError as exc:
        raise BuildError(f'{what} is not valid TOML: {exc}') from None


def _tables(data: dict, key: str, where: str) -> list[dict]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(t, dict) for t in value):
        raise BuildError(f'{where}: {key} is not an array of tables')
    return value


def read_base(path: str | os.PathLike[str]) -> tuple[dict, tuple[CheckerEntry, ...], list[dict]]:
    """The base's launcher table, checkers and raw rules; the base must load as a policy."""
    where = f'base {forward(path)!a}'
    try:
        policy = load_policy(path)
    except PolicyError as exc:
        raise BuildError(f'{where} is unreadable: {exc}') from None
    data = _read_toml(Path(path), where)
    launcher = data.get('launcher', {})
    unknown = sorted(ascii(k) for k in launcher if k not in LAUNCHER_LISTS)
    if unknown:
        raise BuildError(f'{where}: launcher has unknown key(s): {", ".join(unknown)}')
    entries = tuple(
        CheckerEntry(
            id=c.id,
            file=forward(c.path),
            sha256=hashlib.sha256(c.source).hexdigest(),
            budget_ms=c.budget_ms,
        )
        for c in policy.checkers
    )
    return launcher, entries, _tables(data, 'rule', where)


def _relative_file(file: object, where: str) -> str:
    if not isinstance(file, str) or not file:
        raise BuildError(f'{where}: file is not a non-empty string')
    if PureWindowsPath(file).anchor or PurePosixPath(file).is_absolute():
        raise BuildError(f'{where}: file {file!a} is absolute')
    if '..' in re.split(r'[\\/]', file):
        raise BuildError(f'{where}: file {file!a} has a .. segment')
    return file


def _pack_checker(raw: dict, n: int, folder: Path, where: str) -> CheckerEntry:
    outer = where
    where = f'{outer}: checker {n}'
    unknown = sorted(
        ascii(k) for k in raw if k not in PACK_CHECKER_REQUIRED + PACK_CHECKER_OPTIONAL
    )
    if unknown:
        raise BuildError(f'{where} has unknown key(s): {", ".join(unknown)}')
    missing = [k for k in PACK_CHECKER_REQUIRED if k not in raw]
    if missing:
        raise BuildError(f'{where} lacks key(s): {", ".join(missing)}')
    checker_id = raw['id']
    if not isinstance(checker_id, str) or not checker_id:
        raise BuildError(f'{where}: id is not a non-empty string')
    where = f'{outer}: checker {checker_id!a}'
    path = folder / _relative_file(raw['file'], where)
    if not path.is_file():
        raise BuildError(f'{where}: file {raw["file"]!a} does not exist in the pack')
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise BuildError(f'{where}: file cannot be read: {type(exc).__name__}') from None
    return CheckerEntry(
        id=checker_id,
        file=forward(path),
        sha256=hashlib.sha256(source).hexdigest(),
        budget_ms=raw.get('budget_ms', BUDGET_DEFAULT_MS),
    )


def _pack_rule(raw: dict, n: int, where: str) -> dict:
    unknown = sorted(ascii(k) for k in raw if k not in RULE_KEYS)
    if unknown:
        raise BuildError(f'{where}: rule {n} has unknown key(s): {", ".join(unknown)}')
    rule_id = raw.get('id')
    if not isinstance(rule_id, str) or not rule_id:
        raise BuildError(f'{where}: rule {n}: id is not a non-empty string')
    return raw


def read_pack(folder: str | os.PathLike[str]) -> Pack:
    """Read and check one pack folder; raise BuildError when any part is refused."""
    root = Path(os.path.abspath(folder))
    where = f'pack {forward(root)!a}'
    if not root.is_dir():
        raise BuildError(f'{where} is not a folder')
    data = _read_toml(root / PACK_FILE, f'{where}: {PACK_FILE}')
    unknown = sorted(ascii(k) for k in data if k not in PACK_KEYS)
    if unknown:
        raise BuildError(f'{where} has unknown key(s): {", ".join(unknown)}')
    if type(data.get('pack')) is not int or data['pack'] != PACK_VERSION:
        raise BuildError(f'{where}: pack is not {PACK_VERSION}')
    name = data.get('name')
    if not isinstance(name, str) or not name:
        raise BuildError(f'{where}: name is not a non-empty string')
    entries = tuple(
        _pack_checker(raw, n, root, where)
        for n, raw in enumerate(_tables(data, 'checker', where), 1)
    )
    rules = tuple(
        _pack_rule(raw, n, where) for n, raw in enumerate(_tables(data, 'rule', where), 1)
    )
    prevention = data.get('prevention')
    if prevention is not None:
        if not isinstance(prevention, dict):
            raise BuildError(f'{where}: prevention is not a table')
        if sorted(prevention) != sorted(PREVENTION_KEYS) or not all(
            isinstance(prevention[k], str) for k in PREVENTION_KEYS
        ):
            raise BuildError(
                f'{where}: prevention does not hold exactly the strings rule and layer'
            )
        if prevention['rule'] not in [r['id'] for r in rules]:
            raise BuildError(f'{where}: prevention names no rule of the pack')
        prevention = {k: prevention[k] for k in PREVENTION_KEYS}
    return Pack(
        name=name, folder=forward(root), checkers=entries, rules=rules, prevention=prevention
    )


def _unique(ids: Iterable[str], what: str) -> None:
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise BuildError(f'{what} id {item!a} repeats across the base and the packs')
        seen.add(item)


def compose(launcher: dict, entries: Iterable[CheckerEntry], rules: Iterable[dict]) -> str:
    """The text of a version 2 policy; keys in a fixed order, LF line ends."""
    lines = ['version = 2', '', '[launcher]']
    lines += [f'{k} = {toml_value(launcher[k])}' for k in LAUNCHER_LISTS if k in launcher]
    lines.append('')
    for entry in entries:
        lines += [
            '[[checker]]',
            f'id = {toml_value(entry.id)}',
            f'file = {toml_value(entry.file)}',
            f'sha256 = {toml_value(entry.sha256)}',
            f'budget_ms = {toml_value(entry.budget_ms)}',
            '',
        ]
    for rule in rules:
        lines.append('[[rule]]')
        lines += [f'{k} = {toml_value(rule[k])}' for k in RULE_ORDER if k in rule]
        lines.append('')
    return '\n'.join(lines)


def sidecar_text(policy_bytes: bytes, packs: Iterable[Pack]) -> str:
    """The text of `<out>.packs.json` for a written policy."""
    data = {
        'kit_packs': SIDECAR_VERSION,
        'policy_sha256': hashlib.sha256(policy_bytes).hexdigest(),
        'packs': [
            {
                'name': p.name,
                'folder': p.folder,
                'rules': [r['id'] for r in p.rules],
                'prevention': p.prevention,
            }
            for p in packs
        ],
    }
    return json.dumps(data, ensure_ascii=True) + '\n'


def sidecar_path(out: str | os.PathLike[str]) -> Path:
    out = Path(out)
    return out.with_name(out.name + SIDECAR_SUFFIX)


def verify_checkers(items: Iterable[Checker]) -> str | None:
    """Load each checker once, as the judge would, without calling it.

    Each load waits at most the checker's `budget_ms` on a daemon thread, with
    descriptors 1 and 2 at the null device for the load only and restored
    after it. Return None when every checker executes and defines a callable
    `check`, else the ASCII reason of the first one that does not.
    """
    for checker in items:
        reason = checkers.try_load(checker)
        if reason is not None:
            return reason
    return None


def build(
    base: str | os.PathLike[str],
    pack_folders: Iterable[str | os.PathLike[str]],
    out: str | os.PathLike[str],
    force: bool = False,
) -> tuple[Path, Path]:
    """Build and write the policy and its sidecar; raise BuildError, writing nothing, on refusal."""
    out = Path(out)
    side = sidecar_path(out)
    if not force:
        for path in (out, side):
            if os.path.lexists(path):
                raise BuildError(f'{forward(path)!a} exists; pass --force to replace it')
    if not out.parent.is_dir():
        raise BuildError(f'the folder of --out, {forward(out.parent)!a}, does not exist')
    launcher, entries, rules = read_base(base)
    packs = [read_pack(folder) for folder in pack_folders]
    entries = entries + tuple(e for p in packs for e in p.checkers)
    rules = list(rules) + [r for p in packs for r in p.rules]
    _unique((r['id'] for r in rules), 'rule')
    _unique((e.id for e in entries), 'checker')
    text = compose(launcher, entries, rules)
    try:
        policy = load_policy_text(text)
    except PolicyError as exc:
        raise BuildError(f'the composed policy does not load: {exc}') from None
    reason = verify_checkers(policy.checkers)
    if reason is not None:
        raise BuildError(reason)
    data = text.encode('ascii')
    out.write_bytes(data)
    side.write_bytes(sidecar_text(data, packs).encode('ascii'))
    return out, side


def add_parser(sub) -> None:
    """The `policy build` subcommand, under the `kit` parser's subparsers."""
    policy = sub.add_parser('policy', help='compose policies from rule packs')
    policy_sub = policy.add_subparsers(
        dest='policy_command', metavar='POLICY_COMMAND', required=True
    )
    b = policy_sub.add_parser(
        'build',
        help='write a version 2 policy from a base policy and rule packs; refusals exit 64',
    )
    b.add_argument('--base', metavar='FILE', required=True, help='version 1 or 2 base policy')
    b.add_argument(
        '--pack', metavar='DIR', required=True, action='append', help='pack folder (repeatable)'
    )
    b.add_argument('--out', metavar='FILE', required=True, help='policy file to write')
    b.add_argument('--force', action='store_true', help='replace --out and its sidecar')


def _say(message: str) -> None:
    sys.stderr.write(f'kit: {message}\n')
    sys.stderr.flush()


def run_build(args: argparse.Namespace) -> int:
    """`kit policy build`; a refused input exits 64 and writes nothing."""
    try:
        out, side = build(args.base, args.pack, args.out, args.force)
    except BuildError as exc:
        _say(f'policy build refused: {exc}')
        return EXIT_REFUSED
    except OSError as exc:
        _say(f'policy build failed: {exc!a}')
        return EXIT_INTERNAL
    _say(f'policy written: {forward(out)!a} and {forward(side)!a}')
    return 0

"""The kit plugin wired into a copy of an opencode global configuration, and the check of it.

`wire` reads an opencode global configuration (JSON or JSONC), materializes the opencode
shell into a folder of its own (`index.js` and a `shell_config.json` whose `cli_argv` ends
in `judge --from opencode`; no note mode, so no `note_config.json`), and writes a copy of
the configuration's text with two edits: the shell folder added to `plugins`, and
`"update": "disable"` when `update` is absent. It never writes the configuration itself:
applying the copy is the owner's act. `check` says whether a configuration lists a shell
folder whose files are the ones this kit renders.

The text is edited, not a parsed tree, so every other byte stays, comments included. An
absent `plugins` or `update` is inserted as the first key after the opening brace; an
existing `plugins` array gets the entry appended when it lies on one line. A `plugins`
array spread over lines, a nested form (an element that is not a string, a value that is not
an array, `plugins` twice, or `plugins` inside another object) and a text that does not
parse are refused, naming the entry to add by hand; the shell is then materialized all the
same, so the entry can be added.

JSONC is read by `strip_jsonc`, which blanks comments and trailing commas outside strings
with spaces and keeps every line break, so an offset in the stripped text is the offset of
the same character in the original.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from json.decoder import scanstring
from pathlib import Path

from harness_kit.harnesses import SHELLS_DIR, HomeError, contract_version, materialize_shell

HARNESS = 'opencode'
PLUGINS, UPDATE = 'plugins', 'update'
UPDATE_SETTING = '"update": "disable"'
# The kit shell's plugin id is `harness-kit`; a later `-harness-kit` entry removes it.
REMOVAL = '-harness-kit'
JSON_WS = ' \t\r\n'
BOM = chr(0xFEFF)  # a byte order mark, which opencode trims as white space
INDENT = '  '


class JsoncError(ValueError):
    """A text that does not parse as JSON or JSONC; the message is ASCII."""


class FormError(ValueError):
    """A configuration whose `plugins` this module does not edit; the message is ASCII."""


def _ascii(text: object) -> str:
    return str(text).encode('ascii', 'backslashreplace').decode('ascii').replace('\n', ' ')


# ---- the JSONC scanner


def _blank(chars: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if chars[i] not in '\r\n':
            chars[i] = ' '


def strip_jsonc(text: str, trailing_commas: bool = True) -> str:
    """`text` with each comment, and each trailing comma, outside strings turned into spaces.

    Line breaks are kept, so the result has the same length and every offset names the same
    character. A leading byte order mark is blanked too. JsoncError for an unterminated
    string or block comment.
    """
    chars = list(text)
    n = len(text)
    i = 0
    pending = None  # a comma whose next significant character is not known yet
    if text.startswith(BOM):
        chars[0] = ' '
        i = 1
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            if j >= n:
                raise JsoncError(f'unterminated string at offset {i}')
            pending, i = None, j + 1
            continue
        if ch == '/' and text[i + 1 : i + 2] == '/':
            j = i + 2
            while j < n and text[j] not in '\r\n':
                j += 1
            _blank(chars, i, j)
            i = j
            continue
        if ch == '/' and text[i + 1 : i + 2] == '*':
            j = text.find('*/', i + 2)
            if j < 0:
                raise JsoncError(f'unterminated comment at offset {i}')
            _blank(chars, i, j + 2)
            i = j + 2
            continue
        if ch in JSON_WS:
            i += 1
            continue
        if ch in ']}' and pending is not None and trailing_commas:
            chars[pending] = ' '
        pending = i if ch == ',' else None
        i += 1
    return ''.join(chars)


def _constant(name: str) -> object:
    raise JsoncError(f'{name} is not a JSON value')


def load_jsonc(text: str) -> object:
    """The value a JSON or JSONC text holds; JsoncError when it does not parse."""
    try:
        return json.loads(strip_jsonc(text), parse_constant=_constant)
    except ValueError as exc:  # json.JSONDecodeError and JsoncError
        raise JsoncError(_ascii(exc)) from None


# ---- the top-level object


@dataclass(frozen=True)
class Member:
    key: str
    start: int  # the value's first character
    end: int  # one past the value's last character
    value: object


def _skip(text: str, i: int) -> int:
    while i < len(text) and text[i] in JSON_WS:
        i += 1
    return i


def _members(stripped: str) -> tuple[int, int, list[Member]]:
    """(offset of the opening brace, offset of the closing brace, the members in text order)
    of the top-level object of a stripped text that parses."""
    decoder = json.JSONDecoder(parse_constant=_constant)
    at = _skip(stripped, 0)
    if stripped[at : at + 1] != '{':
        raise JsoncError('the configuration is not a JSON object')
    members: list[Member] = []
    i = _skip(stripped, at + 1)
    while stripped[i : i + 1] != '}':
        key, i = scanstring(stripped, i + 1)
        start = _skip(stripped, _skip(stripped, i) + 1)  # past the colon
        value, end = decoder.raw_decode(stripped, start)
        members.append(Member(key, start, end, value))
        i = _skip(stripped, end)
        if stripped[i : i + 1] == ',':
            i = _skip(stripped, i + 1)
    return at, i, members


def _holds_plugins_key(value: object) -> bool:
    if isinstance(value, dict):
        return PLUGINS in value or any(_holds_plugins_key(v) for v in value.values())
    if isinstance(value, list):
        return any(_holds_plugins_key(v) for v in value)
    return False


def _append(text: str, member: Member, entry: str) -> tuple[int, str]:
    """(offset, text) that appends `entry` to the one-line `plugins` array of `member`."""
    if not isinstance(member.value, list) or not all(isinstance(v, str) for v in member.value):
        raise FormError(
            'its plugins value is in a nested form (not an array of strings), which '
            'kit home wire does not edit'
        )
    if any(ch in '\r\n' for ch in text[member.start : member.end]):
        raise FormError(
            'its plugins array spans more than one line, which kit home wire does not edit'
        )
    close = member.end - 1
    at = close
    while text[at - 1] in ' \t':
        at -= 1
    kept = strip_jsonc(text, trailing_commas=False)
    last = close - 1
    while kept[last] in ' \t':
        last -= 1
    item = json.dumps(entry, ensure_ascii=True)
    if not member.value:
        return at, (item if text[at - 1] == '[' else ' ' + item)
    return at, (' ' + item if kept[last] == ',' else ', ' + item)


def _indent(text: str, brace: int, close: int) -> str:
    """The indent of the first line after the opening brace's line that holds anything."""
    i = text.find('\n', brace)
    while 0 <= i < close:
        start = i + 1
        j = start
        while j < len(text) and text[j] in ' \t':
            j += 1
        if j >= close:
            return text[start:j] + INDENT
        if text[j] not in '\r\n':
            return text[start:j]
        i = text.find('\n', start)
    return INDENT


def _first_keys(text: str, brace: int, close: int, items: list[str], more: bool) -> str:
    """The text inserted right after the opening brace: `items` as the first members."""
    if '\n' not in text[brace:close]:
        return ', '.join(items) + (', ' if more else '')
    first_break = text.find('\n', brace)
    newline = '\r\n' if text[first_break - 1] == '\r' else '\n'
    indent = _indent(text, brace, close)
    return ','.join(newline + indent + item for item in items) + (',' if more else '')


def wired_text(text: str, entry: str) -> str:
    """`text` with `entry` added to `plugins` and `update` set to `disable` when absent.

    JsoncError for a text that does not parse or is no object; FormError for a `plugins`
    this module does not edit, or for an edited text that would not read back as the
    configuration with the two edits.
    """
    old = load_jsonc(text)
    brace, close, members = _members(strip_jsonc(text))
    if any(_holds_plugins_key(m.value) for m in members):
        raise FormError(
            'it names plugins inside another value, a nested form kit home wire does not edit'
        )
    found = [m for m in members if m.key == PLUGINS]
    if len(found) > 1:
        raise FormError('it names plugins more than once, which kit home wire does not edit')
    inserts: list[tuple[int, str]] = []
    first: list[str] = []
    if found:
        inserts.append(_append(text, found[0], entry))
    else:
        first.append(f'"{PLUGINS}": [{json.dumps(entry, ensure_ascii=True)}]')
    if not any(m.key == UPDATE for m in members):
        first.append(UPDATE_SETTING)
    if first:
        inserts.append((brace + 1, _first_keys(text, brace, close, first, bool(members))))
    wired = text
    for at, chunk in sorted(inserts, reverse=True):
        wired = wired[:at] + chunk + wired[at:]
    want = dict(old) if isinstance(old, dict) else {}
    want[PLUGINS] = [*want.get(PLUGINS, []), entry]
    want.setdefault(UPDATE, 'disable')
    try:
        held = load_jsonc(wired)
    except JsoncError:
        held = None
    if held != want:
        raise FormError('the edited text would not read back as it with the entry added')
    return wired


# ---- the shell folder


def entry_for(shell_dir: Path | str) -> str:
    """The `plugins` entry of a shell folder: its absolute path with forward slashes."""
    return Path(os.path.abspath(str(shell_dir))).as_posix()


def materialize(folder: Path) -> None:
    """The opencode shell, as `kit home render` writes it, without a note mode."""
    source = SHELLS_DIR / HARNESS / 'index.js'
    materialize_shell(source, folder, contract_version(HARNESS), HARNESS)


def _files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob('*'))
        if p.is_file()
    }


def shell_differences(folder: Path) -> list[str]:
    """The names whose files in `folder` differ from a fresh materialization (missing, extra
    or changed); empty when they are equal."""
    with tempfile.TemporaryDirectory(prefix='kit-wire-') as td:
        fresh = Path(td) / 'shell'
        materialize(fresh)
        want = _files(fresh)
    have = _files(folder)
    return sorted(n for n in set(want) | set(have) if want.get(n) != have.get(n))


def _same_folder(item: object, folder: Path) -> bool:
    if not isinstance(item, str) or not item or not os.path.isabs(item):
        return False
    return os.path.normcase(os.path.normpath(item)) == os.path.normcase(os.path.abspath(folder))


def _same_file(a: Path, b: Path) -> bool:
    if os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b)):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _within(path: Path, folder: Path) -> bool:
    inner = os.path.normcase(os.path.abspath(path))
    outer = os.path.normcase(os.path.abspath(folder))
    return inner.startswith(outer.rstrip('\\/') + os.sep)


def _read(config: Path) -> str:
    """The configuration's text; HomeError when it cannot be read."""
    try:
        return config.read_bytes().decode('utf-8')
    except OSError as exc:
        raise HomeError(f'{_ascii(config)} cannot be read: {_ascii(exc)}') from None
    except UnicodeDecodeError:
        raise JsoncError('it is not UTF-8 text') from None


# ---- the two commands


def wire(config: str, shell_dir: str, out: str) -> str:
    """Materialize the shell into `shell_dir` and write the wired copy of `config` to `out`.

    Returns the line to print. HomeError for a refusal (nothing written, but for a refusal
    over the configuration's form, after which the shell is materialized for the entry to add
    by hand); OSError when a write fails.
    """
    source, folder, dest = Path(config), Path(shell_dir), Path(out)
    if _same_file(source, dest):
        raise HomeError('--out names the configuration itself, which kit home wire never writes')
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise HomeError(f'the shell folder is not empty: {_ascii(shell_dir)}')
    if _within(dest, folder):
        raise HomeError('--out lies inside the shell folder, which holds the shell alone')
    if dest.is_dir():
        raise HomeError(f'--out is a folder: {_ascii(out)}')
    entry = entry_for(folder)
    try:
        text = _read(source)
        wired = wired_text(text, entry)
    except (JsoncError, FormError) as exc:
        why = f'it does not parse as JSON or JSONC ({exc})' if isinstance(exc, JsoncError) else exc
        materialize(folder)
        raise HomeError(
            f'{_ascii(config)}: {why}; the shell is in {_ascii(shell_dir)}, so add this '
            f'entry to the plugins array by hand: {json.dumps(entry, ensure_ascii=True)}'
        ) from None
    materialize(folder)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(wired.encode('utf-8'))
    return f'wired: {_ascii(out)} lists {_ascii(shell_dir)}'


def check(config: str, shell_dir: str) -> tuple[int, str]:
    """(exit code, line): 0 and `wired: CONFIG lists SHELL_DIR` when the configuration lists
    the folder and its files are the ones this kit renders, else 1 and `not wired: REASON`.
    HomeError for a configuration that cannot be read or does not parse as an object."""
    try:
        data = load_jsonc(_read(Path(config)))
    except JsoncError as exc:
        raise HomeError(f'{_ascii(config)} does not parse as JSON or JSONC: {exc}') from None
    if not isinstance(data, dict):
        raise HomeError(f'{_ascii(config)} is not a JSON object')
    folder = Path(shell_dir)
    plugins = data.get(PLUGINS)
    if not isinstance(plugins, list):
        return 1, f'not wired: {_ascii(config)} has no plugins array'
    listed = [i for i, item in enumerate(plugins) if _same_folder(item, folder)]
    if not listed:
        return (
            1,
            f'not wired: the plugins array of {_ascii(config)} does not list {_ascii(shell_dir)}',
        )
    if REMOVAL in plugins[listed[-1] + 1 :]:
        return 1, (
            f'not wired: the plugins array of {_ascii(config)} removes {REMOVAL[1:]} after '
            f'listing {_ascii(shell_dir)}'
        )
    if not folder.is_dir():
        return 1, f'not wired: {_ascii(shell_dir)} holds no shell'
    differ = shell_differences(folder)
    if differ:
        return 1, (
            f'not wired: the files of {_ascii(shell_dir)} differ from the shell this kit renders: '
            + ', '.join(_ascii(n) for n in differ)
        )
    return 0, f'wired: {_ascii(config)} lists {_ascii(shell_dir)}'

"""opencode driver: a home whose configuration loads the kit shell as a plugin folder.

The shell sends the kit CLI one envelope per hook: the hook's event object as
opencode gives it (`payload`, its `JSON.stringify` text), the session's place
as the shell's lookups found it and the folder the session runs in. This
driver translates an envelope into the neutral event (`translate_event`) or
the note (`translate_note`), and names the tools the kit refuses by name
(`refused_tool`).

A daily home (`render_daily_home`) names one provider, `relay`: the relay `kit run`
starts for the session on the daily file's port, which the session reaches with its
capability; each of its models whose id starts with `anthropic/` carries opencode's Anthropic
cache format (`model_entry`). Its `gitconfig` holds the daily file's identity and joins the
watched files.
The canary's copy of any home holds only the watched files, with empty `xdg/` and `home/`
folders, so a home's history is never copied.

A daily file may name a ripgrep binary (`[tools]`): the render reads its bytes once, checks
their SHA-256 and writes them to `RIPGREP_COPY` in opencode's `bin` folder, where opencode
looks. That copy is a watched file of every home (listed only when present) and is left out of
the canary's copy. `ripgrep_walk` says which file opencode 2.2.5 would run as `rg`, as its
`which` 6.0.1 and `isexe` 4.0.0 resolve it.

Every home's configuration carries `policies` that load no plugin but the kit's, no MCP
server and no provider or integration but the home's own, then a `tool.use` deny for each
tool that runs code or moves the session outside the tools the driver translates; its
`permissions` end with a switch that turns each of those tools off, and the image tool's
configuration key is off. The session's file watcher is off, so a configuration write does
not reload the running process. `system_config_dir()` names opencode's system configuration
folder, which `kit run` refuses and protects.

A home rendered with a policy that has a `[permissions]` section carries it as opencode's
own `permissions` and `tool.use` denies (`opencode_permissions`), and `home.json` records
`permissions_sha256`; `permissions_refusal` is `kit run`'s comparison with a fresh render.
"""

from __future__ import annotations

import functools
import hashlib
import json
import ntpath
import os
import posixpath
import re
import shutil
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath
from types import MappingProxyType

from harness_kit import watch
from harness_kit.event import InvalidEventError, parse_event
from harness_kit.harnesses import (
    DAILY_HOME,
    FAKE_KEY,
    HEADLESS,
    INTERACTIVE,
    RELAY_CAPABILITY_ENV,
    SHELLS_DIR,
    TEST_HOME,
    ContractVersion,
    Grammar,
    HomeError,
    check_endpoint,
    configured_argv,
    finish_home,
    home_env,
    is_batch,
    materialize_shell,
    opencode_permissions,
    prepare_dir,
    read_version,
    set_var,
    write_json,
    write_note_config,
)

MODEL = 'stub/stub-model'
PROVIDER_PACKAGE = '@opencode/ai/providers/openai-compatible'
RELAY_PROVIDER = 'relay'
# opencode's cache format for a daily home's Anthropic models: with it, opencode marks the prompt
# for the provider's cache (its default 5-minute lifetime); without it, it sends no mark. A value
# opencode does not accept drops the whole provider, so it is written from this one constant.
CACHE_FORMAT = 'anthropic'
ANTHROPIC_PREFIX = 'anthropic/'
GITCONFIG = 'gitconfig'
WINDOWS = os.name == 'nt'
# The ripgrep binary as opencode names it on this platform, and the home's copy of the one a
# daily file names: opencode's `bin` folder is `$XDG_CACHE_HOME/opencode/bin`, and the session's
# `XDG_CACHE_HOME` is the home's `xdg/cache`.
RIPGREP = 'rg.exe' if WINDOWS else 'rg'
RIPGREP_BIN = 'xdg/cache/opencode/bin'
RIPGREP_COPY = f'{RIPGREP_BIN}/{RIPGREP}'
RIPGREP_MODE = 0o755
NATIVE = ('node_modules', '@opencode', 'cli', 'bin', 'opencode.exe')
CONFIG_NAMES = (
    'OPENCODE_CONFIG_DIR',
    'OPENCODE_TEST_HOME',
    'XDG_CONFIG_HOME',
    'XDG_DATA_HOME',
    'XDG_STATE_HOME',
    'XDG_CACHE_HOME',
)

# ---- the envelope

ENVELOPE_KEYS = (
    'kit_raw',
    'hook',
    'run_id',
    'harness',
    'session',
    'origin',
    'observation',
    'location',
    'payload',
)
BEFORE, AFTER, PROMPT = 'execute.before', 'execute.after', 'prompt'
HOOKS = (BEFORE, AFTER, PROMPT)
PLACE_KEYS = ('session', 'parent', 'root', 'origin')
TEXT_CAP = 20000
OUTPUT_CAP = 65536

# What ECMAScript's String.prototype.trim removes, which opencode trims a patch with. It differs
# from str.strip(): it removes U+FEFF and keeps U+001C to U+001F and U+0085.
ECMA_WHITESPACE = ''.join(
    map(
        chr,
        (
            *range(0x09, 0x0E),
            0x20,
            0xA0,
            0x1680,
            *range(0x2000, 0x200B),
            0x2028,
            0x2029,
            0x202F,
            0x205F,
            0x3000,
            0xFEFF,
        ),
    )
)
_WS = re.escape(ECMA_WHITESPACE)
# opencode's heredoc wrapper: an optional `cat`, `<<`, an optionally quoted word, the body, the word.
_HEREDOC = re.compile(
    rf'(?:cat[{_WS}]+)?<<([\'"]?)([A-Za-z0-9_]+)\1[{_WS}]*\n(.*?)\n\2[{_WS}]*', re.DOTALL
)
PATCH_PATH_PREFIXES = ('*** Add File: ', '*** Update File: ', '*** Delete File: ', '*** Move to: ')
PATCH_MARKS = ('*** Begin Patch', '*** End Patch', '*** End of File')
PATCH_QUIET_PREFIX = '*** Environment ID:'
PATCH_HEADER = '*** '

REFUSED_TOOLS = {
    'opencode_worktree_remove': (
        'kit refuses this tool under kit run; remove a worktree with git in the shell, '
        'which kit judges'
    ),
}

# Tools that run code or move the session outside the tools the driver translates, which every
# home switches off, in this order.
SWITCHED_OFF = (
    'execute',
    'opencode_worktree_create',
    'opencode_session_move',
    'experimental_image_generate',
)
WATCHER_OFF = ('OPENCODE_DISABLE_FILEWATCHER', 'OPENCODE_FILEWATCHER_DISABLE')
SYSTEM_FOLDER_POSIX = '/etc/opencode'
PERMISSIONS_KEY = 'permissions_sha256'


def _statement(action: str, resource: str, effect: str) -> dict:
    return {'action': action, 'resource': resource, 'effect': effect}


def rendered_policies(kit: str, provider: str) -> list[dict]:
    """The `policies` of a home whose kit plugin is `kit` and whose provider is `provider`."""
    return [
        _statement('plugin.use', '*', 'deny'),
        _statement('plugin.use', kit, 'allow'),
        _statement('mcp.use', '*', 'deny'),
        _statement('provider.use', '*', 'deny'),
        _statement('provider.use', provider, 'allow'),
        _statement('integration.connect', '*', 'deny'),
        _statement('integration.use', '*', 'deny'),
        _statement('integration.use', provider, 'allow'),
        *(_statement('tool.use', f'{tool}:*', 'deny') for tool in SWITCHED_OFF),
    ]


def switches() -> list[dict]:
    """The `permissions` rules that turn each switched-off tool off; they end `permissions`."""
    return [_statement(tool, '*', 'deny') for tool in SWITCHED_OFF]


def system_config_dir() -> Path:
    """opencode's system configuration folder: ProgramData, as the operating system gives it,
    plus `opencode` on Windows; `/etc/opencode` elsewhere."""
    if os.name != 'nt':
        return Path(SYSTEM_FOLDER_POSIX)
    from harness_kit.launcher import windows_pins

    return Path(windows_pins()['PROGRAMDATA']) / 'opencode'


def model_entry(model_id: str) -> dict:
    """A daily home's entry for one model: its name, and the cache format for an Anthropic id."""
    if model_id.startswith(ANTHROPIC_PREFIX):
        return {'name': model_id, 'compatibility': {'cacheFormat': CACHE_FORMAT}}
    return {'name': model_id}


def _ascii(text: object) -> str:
    return str(text).encode('ascii', 'backslashreplace').decode('ascii')


def read_ripgrep(path: str, sha256: str) -> bytes:
    """The bytes of the ripgrep a daily file names, read once.

    HomeError, naming the path, when it is absent, not a regular file or unreadable (with the
    error's class), or when its SHA-256 is not the one the daily file names.
    """
    shown = _ascii(path)
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            raise HomeError(f'tools.ripgrep {shown} is not a regular file')
        data = Path(path).read_bytes()
    except OSError as exc:
        raise HomeError(f'tools.ripgrep {shown} not read: {type(exc).__name__}') from None
    found = hashlib.sha256(data).hexdigest()
    if found != sha256:
        raise HomeError(
            f"tools.ripgrep {shown} has SHA-256 {found}, not the daily file's "
            f'tools.ripgrep_sha256 {_ascii(sha256)}'
        )
    return data


# ---- which file opencode runs as `rg`

# opencode 2.2.5 resolves ripgrep with `which(RIPGREP, undefined, global.bin)`: the `which`
# package 6.0.1 over the process's `PATH` with `bin` appended, each candidate tested by `isexe`
# 4.0.0; with none, `bin/RIPGREP` when it is a regular file; else it downloads one. The walk below
# mirrors those two packages as their sources read at those versions.
DEFAULT_PATHEXT = '.EXE;.CMD;.BAT;.COM'
# `which` strips one pair of quotes around an entry it matches with `/^".*"$/`; in JavaScript
# `.` matches anything but a line terminator, and `$` only the end of the text.
_QUOTED = re.compile(r'"[^\n\r\u2028\u2029]*"')
_BARE_DRIVE = re.compile(r'[A-Za-z]:')


@dataclass(frozen=True)
class RipgrepWalk:
    """One walk of opencode's ripgrep lookup.

    `found` is the file opencode would run (None: it would download one), `tried` every path
    the walk tried, absolute, in order and each once, and `copy` the `bin` folder's own file.
    """

    found: str | None
    tried: tuple[str, ...]
    copy: str


def _env_value(env: Mapping[str, str], name: str) -> str | None:
    """A variable as the session's process reads it: on Windows without regard to case."""
    if WINDOWS:
        return next((v for k, v in env.items() if k.upper() == name), None)
    return env.get(name)


def _search_path(env: Mapping[str, str]) -> str:
    """The `PATH` opencode passes to `which`: `PATH`, else `Path` (POSIX), else empty."""
    if WINDOWS:
        return _env_value(env, 'PATH') or ''
    value = env.get('PATH')
    return (value if value is not None else env.get('Path')) or ''


def _suffixes(pathext: str, name: str) -> list[str]:
    """`which`'s suffixes: each item as written and lowercased, the bare name first for a name
    that holds a dot."""
    items = [x for item in pathext.split(';') for x in (item, item.lower())]
    if '.' in name and items[0] != '':
        items.insert(0, '')
    return items


def _join(entry: str, name: str) -> str:
    """`which`'s path for one entry: its quotes removed, joined and normalized as Node's
    `path.join` does (a bare drive `C:` joins at that drive's root)."""
    part = entry[1:-1] if _QUOTED.fullmatch(entry) else entry
    if not part:
        return name
    if WINDOWS:
        if _BARE_DRIVE.fullmatch(part):
            return part + '\\' + name
        return ntpath.normpath(ntpath.join(part, name))
    joined = posixpath.normpath(posixpath.join(part, name))
    return '/' + joined.lstrip('/') if joined.startswith('//') else joined


def _against(path: str, cwd: str | None) -> str | None:
    """`path` as `isexe` stats it from the current folder `cwd`; None for a relative path when
    there is no current folder."""
    if PurePath(path).is_absolute():
        return path
    if cwd is None:
        return None
    if not WINDOWS:
        return posixpath.normpath(posixpath.join(cwd, path))
    joined = ntpath.join(cwd, path)
    drive, rest = ntpath.splitdrive(joined)
    if drive and not rest.startswith(('\\', '/')):
        # A drive-relative path on another drive: the session carries no folder of that drive.
        joined = drive + '\\' + rest
    return ntpath.normpath(joined)


def _counts(path: str, written: str, pathext: str) -> bool:
    """Whether `isexe` accepts the file: a regular file once links are followed, and on Windows
    a path ending with a `PATHEXT` item, off Windows a mode that lets this process execute it."""
    try:
        found = os.stat(path)
    except (OSError, ValueError):
        return False
    if not stat.S_ISREG(found.st_mode):
        return False
    if WINDOWS:
        items = pathext.split(';')
        if '' in items:
            return True
        tail = written.lower()
        return any(item and tail.endswith(item.lower()) for item in items)
    uid = os.getuid()
    groups = {os.getgid(), *os.getgroups()}
    mode = found.st_mode
    return bool(
        mode & 0o001
        or (mode & 0o010 and found.st_gid in groups)
        or (mode & 0o100 and found.st_uid == uid)
        or (mode & 0o110 and uid == 0)
    )


def ripgrep_walk(env: Mapping[str, str], bin_dir: str, cwd: str | None) -> RipgrepWalk:
    """The file opencode 2.2.5 would run as `rg` in a process with environment `env` and current
    folder `cwd`, its `bin` folder `bin_dir`.

    With `cwd` None (no current folder) the walk leaves out the current-folder entry and every
    entry still relative after the join.
    """
    delimiter = ';' if WINDOWS else ':'
    base = _search_path(env)
    full = base + delimiter + bin_dir if base and bin_dir else (base or bin_dir)
    entries = ([cwd] if WINDOWS and cwd is not None else []) + full.split(delimiter)
    pathext = (_env_value(env, 'PATHEXT') or DEFAULT_PATHEXT) if WINDOWS else ''
    suffixes = _suffixes(pathext, RIPGREP) if WINDOWS else ['']
    tried: list[str] = []
    seen: set[str] = set()
    found = None
    for entry in entries:
        joined = _join(entry, RIPGREP)
        for suffix in suffixes:
            written = joined + suffix
            path = _against(written, cwd)
            if path is None:
                continue
            if watch.norm(path) not in seen:
                seen.add(watch.norm(path))
                tried.append(path)
            if _counts(path, written, pathext):
                found = path
                break
        if found is not None:
            break
    copy = _join(bin_dir, RIPGREP)
    if found is None and os.path.isfile(copy):
        found = copy
    return RipgrepWalk(found=found, tried=tuple(tried), copy=copy)


def ecma_trim(text: str) -> str:
    """`text` without the ECMAScript white space at either end."""
    return text.strip(ECMA_WHITESPACE)


def resolve(location: str, path: str) -> str:
    """`path` against `location`, as Node's `path.resolve(location, path)` gives it.

    For an absolute location this is `os.path.normpath(os.path.join(location, path))`; a
    location without a drive or a root takes them from the working folder, as Node does.
    """
    try:
        here = os.getcwd()
    except OSError:
        here = ''
    return os.path.normpath(os.path.join(here, location, path))


def patch_paths(text: str, location: str) -> list[str] | None:
    """The paths a patch's headers name, resolved; None when a header is unread or none is found.

    The text is normalized as opencode 2.2.5 does (trimmed, its heredoc wrapper stripped, one
    trailing carriage return dropped from each line); then every line whose trimmed text starts
    with one of the four path prefixes gives a path, wherever it stands, so no path opencode
    applies is missed. A trimmed line that starts with `*** ` and is neither a path header nor one
    of the forms that name none is an unread header.
    """
    text = ecma_trim(text)
    wrapped = _HEREDOC.fullmatch(text)
    if wrapped is not None:
        text = wrapped.group(3)
    paths: list[str] = []
    for raw in text.split('\n'):
        line = ecma_trim(raw[:-1] if raw.endswith('\r') else raw)
        prefix = next((p for p in PATCH_PATH_PREFIXES if line.startswith(p)), None)
        if prefix is not None:
            paths.append(resolve(location, ecma_trim(line[len(prefix) :])))
        elif line.startswith(PATCH_HEADER) and not (
            line in PATCH_MARKS or line.startswith(PATCH_QUIET_PREFIX)
        ):
            return None
    return paths or None


def _get(value: object, key: str) -> object:
    """`value[key]` for an object, else None: JavaScript's `value?.[key]` over JSON values."""
    return value.get(key) if isinstance(value, dict) else None


def _number(value: object) -> bool:
    return type(value) in (int, float)


@functools.lru_cache(maxsize=4)
def _payload(text: str) -> tuple[dict, str]:
    """The payload's object and the SHA-256 of its UTF-8 bytes; InvalidEventError otherwise."""
    try:
        data = text.encode('utf-8')
    except UnicodeEncodeError:
        raise InvalidEventError('envelope payload is not UTF-8 text') from None
    event = parse_event(data)
    if not isinstance(event, dict):
        raise InvalidEventError('envelope payload is not a JSON object')
    return event, hashlib.sha256(data).hexdigest()


def _exact(value: object, keys: tuple[str, ...], where: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise InvalidEventError(f'{where} is not an object with exactly: {", ".join(keys)}')
    return value


def read_envelope(envelope: object, harness: str) -> tuple[dict, dict, str]:
    """(envelope, payload object, payload SHA-256); InvalidEventError for a refused envelope."""
    env = _exact(envelope, ENVELOPE_KEYS, 'envelope')
    if type(env['kit_raw']) is not int or env['kit_raw'] != 1:
        raise InvalidEventError('envelope kit_raw is not 1')
    if env['hook'] not in HOOKS:
        raise InvalidEventError(f'envelope hook is not one of: {", ".join(HOOKS)}')
    if env['run_id'] is not None and not isinstance(env['run_id'], str):
        raise InvalidEventError('envelope run_id is neither a string nor null')
    named = _exact(env['harness'], ('name', 'version'), 'envelope harness')
    if named['name'] != harness:
        raise InvalidEventError(f'envelope harness is not {harness}')
    _exact(env['observation'], PLACE_KEYS, 'envelope observation')
    if not isinstance(env['location'], str):
        raise InvalidEventError('envelope location is not a string')
    if not isinstance(env['payload'], str):
        raise InvalidEventError('envelope payload is not a string')
    event, sha = _payload(env['payload'])
    return env, event, sha


def _act(env: dict, e: dict, sha: str) -> tuple[dict, str, str]:
    """(neutral act, command observation, paths observation) of one tool event."""
    tool, location = e.get('tool'), env['location']
    inp = _get(e, 'input')
    command, paths, cwd = None, [], location
    command_obs = paths_obs = 'not_applicable'
    kind = 'other'
    if tool == 'shell':
        kind, command_obs = 'shell', 'observed'
        command = inp['command'] if isinstance(_get(inp, 'command'), str) else ''
        workdir = _get(inp, 'workdir')
        if isinstance(workdir, str) and workdir:
            cwd = resolve(location, workdir)
    elif tool in ('write', 'edit'):
        kind = 'file_write'
        path = _get(inp, 'path')
        paths = [resolve(location, path)] if isinstance(path, str) else []
        paths_obs = 'observed' if paths else 'unavailable'
    elif tool == 'patch':
        kind = 'file_write'
        text = _get(inp, 'patchText')
        paths = (patch_paths(text, location) if isinstance(text, str) else None) or []
        paths_obs = 'observed' if paths else 'unavailable'
    act = {
        'kind': kind,
        'command': command,
        'argv': None,
        'paths': paths,
        'cwd': cwd,
        'payload_sha256': sha,
    }
    return act, command_obs, paths_obs


def _frame(env: dict, command_obs: str, paths_obs: str) -> dict:
    place = env['observation']
    observation = {k: place[k] for k in PLACE_KEYS}
    observation.update(command=command_obs, paths=paths_obs)
    return {
        'run_id': env['run_id'],
        'harness': env['harness'],
        'session': env['session'],
        'origin': env['origin'],
        'observation': observation,
    }


def _tool_event(envelope: object, harness: str, hook: str) -> tuple[dict, dict, str]:
    env, e, sha = read_envelope(envelope, harness)
    if env['hook'] != hook:
        raise InvalidEventError(f'envelope hook is not {hook}')
    if not isinstance(e.get('tool'), str):
        raise InvalidEventError('envelope payload names no tool')
    return env, e, sha


def _prompt_body(e: dict) -> dict:
    text = _get(_get(e, 'prompt'), 'text')
    if not isinstance(text, str):
        raise InvalidEventError('envelope payload has no prompt text')
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return {'kind': 'prompt', 'text': text[:TEXT_CAP], 'truncated': len(text) > TEXT_CAP}


def _status(e: dict) -> str:
    result = _get(e, 'result')
    out = _get(result, 'output')
    if e.get('status') == 'error':
        return 'failed'
    if _get(_get(result, 'metadata'), 'status') == 'running' or _get(out, 'status') == 'running':
        return 'background'
    exit_code = _get(out, 'exit')
    if _number(exit_code) and exit_code == 0:
        return 'completed'
    return 'failed' if _number(exit_code) else 'unknown'


def _outcome_body(e: dict, act: dict) -> dict:
    status = _status(e)
    out = _get(_get(e, 'result'), 'output')
    text = _get(out, 'output')
    if status != 'completed' or not isinstance(text, str):
        return {'kind': 'outcome', 'act': act, 'status': status, 'output': None, 'truncated': False}
    cut = len(text) > OUTPUT_CAP or _get(out, 'truncated') is True
    return {
        'kind': 'outcome',
        'act': act,
        'status': status,
        'output': text[-OUTPUT_CAP:],
        'truncated': cut,
    }


def resolve_shim(path: str) -> str | None:
    """opencode's npm shim runs the native binary beside it; any other batch file is missing."""
    shim = Path(path)
    if shim.stem.lower() != 'opencode':
        return None
    native = shim.parent.joinpath(*NATIVE)
    return str(native) if native.is_file() else None


class OpenCode:
    name = 'opencode'
    # The contract's `[harness] version`: the one source of the pin.
    pinned_version = ContractVersion()
    # `run` is the subcommand of every probe that ran a session; the flags are those of `canary_argv`.
    required_leading_tokens = ('run',)
    required_session_args = ('--standalone',)
    allowed_session_flags = ('--standalone', '--format', '--auto', '--model')
    project_config_paths = ('opencode.json', 'opencode.jsonc', '.opencode')
    # The interface (no subcommand) runs through its private server: `--standalone` exactly
    # once, and only the flags of this table; a positional, a subcommand, `--server`, `--auto`
    # and every `--flag=value` form are refused.
    modes = MappingProxyType(
        {
            HEADLESS: Grammar(
                leading=required_leading_tokens,
                required=required_session_args,
                allowed=allowed_session_flags,
            ),
            INTERACTIVE: Grammar(
                required=('--standalone',),
                flags=(
                    ('--standalone', 0),
                    ('--continue', 0),
                    ('-c', 0),
                    ('--session', 1),
                    ('-s', 1),
                    ('--prompt', 1),
                ),
            ),
        }
    )
    # opencode's project walk has no stop before the filesystem root.
    project_walk = 'root'
    # The files the guard is read from. opencode 2.2.5 wrote nothing under `conf/` or
    # `kit-shell/` in an interactive or a headless session, so no name is excluded; it writes
    # `conf/cli.json` when a setting changes in the interface, which stays watched.
    # A daily home's `gitconfig` is watched too; a test home has none. The home's ripgrep copy
    # is watched in every home, and listed only when present: of `xdg/cache` that file alone.
    watched_folders = ('conf', 'kit-shell')
    watched_files = ('home.json', GITCONFIG, RIPGREP_COPY)
    excluded_names: tuple[str, ...] = ()
    # The home's configuration and shell folders, which kit protects from the session's tools,
    # and the folder whose files the check during the run also reads. A `.agents` root feeds
    # only its `skills` folder, so it is no project-config name: in the working folder it is
    # protected, not refused. The ripgrep copy is protected in a daily home whose daily file
    # names a ripgrep, and only there.
    protected_folders = ('conf', 'kit-shell', 'xdg/config')
    ripgrep_copy = RIPGREP_COPY
    run_watched_folders = ('xdg/config',)
    protected_workdir_names = ('.agents',)
    # A render takes the policy's `[permissions]` section, and `kit run` compares it.
    renders_permissions = True

    def binary_argv(self, env: Mapping[str, str]) -> list[str]:
        """The `opencode` argv; [] when missing. Its `.cmd` shim becomes the native binary."""
        argv = configured_argv(self.name, 'opencode', env)
        if argv and is_batch(argv[0]):
            native = resolve_shim(argv[0])
            return [native, *argv[1:]] if native else []
        return argv

    def version(self, env: Mapping[str, str]) -> str | None:
        return read_version(self.binary_argv(env), env, CONFIG_NAMES)

    def render_home(
        self, home: Path, endpoint: str, records: tuple[str, ...] = (), permissions=None
    ) -> dict:
        """A test home; `permissions` is the policy's `[permissions]` section, or None."""
        check_endpoint(endpoint)
        stub = {
            'name': 'Stub',
            'env': ['STUB_API_KEY'],
            'package': PROVIDER_PACKAGE,
            'settings': {'baseURL': endpoint + '/v1'},
            'models': {'stub-model': {'name': 'Stub Model'}},
        }
        settings = {'update': 'disable', 'model': MODEL, 'providers': {'stub': stub}}
        extra = {'kind': TEST_HOME, 'canary_model': MODEL}
        return self._render(home, endpoint, records, settings, extra, 'stub', permissions)

    def render_daily_home(
        self, home: Path, found, records: tuple[str, ...] = (), permissions=None
    ) -> dict:
        """A daily home for the daily file `found` (`daily.Daily`): its provider is the relay.

        When the daily file names a ripgrep, its bytes are read once, before anything is
        written, and those bytes become the home's `RIPGREP_COPY`.
        """
        from harness_kit.daily import gitconfig_text

        endpoint = found.endpoint
        check_endpoint(endpoint)
        named = getattr(found, 'ripgrep', None)
        ripgrep = read_ripgrep(named, found.ripgrep_sha256) if named is not None else None
        model = f'{RELAY_PROVIDER}/{found.relay.default_model}'
        relay = {
            'name': 'Relay',
            'env': [RELAY_CAPABILITY_ENV],
            'package': PROVIDER_PACKAGE,
            'settings': {'baseURL': endpoint + '/v1'},
            'models': {m.id: model_entry(m.id) for m in found.relay.models},
        }
        settings = {
            'update': 'disable',
            'model': model,
            'small_model': model,
            'providers': {RELAY_PROVIDER: relay},
        }
        extra = {
            'kind': DAILY_HOME,
            'daily_file': str(found.path),
            'daily_sha256': found.sha256,
            'daily_settings': found.settings,
            'canary_model': model,
        }
        gitconfig = gitconfig_text(found.git_name, found.git_email)
        return self._render(
            home,
            endpoint,
            records,
            settings,
            extra,
            RELAY_PROVIDER,
            permissions,
            gitconfig,
            ripgrep=ripgrep,
        )

    def permission_lists(self, folder: Path, provider: str, section) -> tuple[list, list]:
        """(`permissions`, `policies`) of a home in `folder` whose provider is `provider`."""
        kit = (folder / 'kit-shell' / 'opencode-plugin').as_posix()
        return opencode_permissions.render(section, rendered_policies(kit, provider), switches())

    def _render(
        self,
        home,
        endpoint,
        records,
        settings,
        extra,
        provider,
        section,
        gitconfig=None,
        *,
        ripgrep: bytes | None = None,
    ) -> dict:
        target = Path(os.path.abspath(str(home)))
        permissions, policies = self.permission_lists(target, provider, section)
        refusal = opencode_permissions.canary_refusal(permissions, policies)
        if refusal is not None:
            raise HomeError(refusal)
        folder = prepare_dir(home)
        plugin = folder / 'kit-shell' / 'opencode-plugin'
        source = SHELLS_DIR / 'opencode' / 'index.js'
        entry, shell_config = materialize_shell(source, plugin, self.pinned_version, self.name)
        write_note_config(shell_config.parent, records, self.name)
        (folder / 'xdg').mkdir()
        config = folder / 'conf' / 'opencode.jsonc'
        kit = plugin.as_posix()
        governed = {
            'plugins': [kit],
            'policies': policies,
            'permissions': permissions,
            'experimental': {'image_generate': False},
        }
        write_json(config, {**settings, **governed})
        if gitconfig is not None:
            (folder / GITCONFIG).write_bytes(gitconfig.encode('utf-8'))
        if ripgrep is not None:
            copy = folder / RIPGREP_COPY
            copy.parent.mkdir(parents=True)
            copy.write_bytes(ripgrep)
            if not WINDOWS:
                os.chmod(copy, RIPGREP_MODE)
        rendered = watch.hash_files(folder, self, rendered=True)
        sha = opencode_permissions.permissions_sha256(permissions, policies)
        extra = {**extra, PERMISSIONS_KEY: sha}
        return finish_home(
            self.name, folder, endpoint, config, entry, shell_config, rendered, extra
        )

    def permissions_refusal(self, home: dict, section) -> str | None:
        """Why `kit run` refuses this home under a policy's `[permissions]` section (None for a
        policy without one), else None.

        The lists are rendered again from the policy: a section that would refuse a canary
        call, a home whose recorded hash differs (its policy changed after the render) and a
        configuration that does not parse or holds other lists are refused.
        """
        provider = RELAY_PROVIDER if home.get('kind') == DAILY_HOME else 'stub'
        fresh = self.permission_lists(Path(home['dir']), provider, section)
        refusal = opencode_permissions.canary_refusal(*fresh)
        if refusal is not None:
            return refusal
        sha = opencode_permissions.permissions_sha256(*fresh)
        if home.get(PERMISSIONS_KEY) != sha:
            return (
                "the home's permissions were rendered from another [permissions] section than "
                "this policy's (home.json's permissions_sha256 differs); render the home again "
                'with this policy into an empty folder'
            )
        try:
            config = json.loads(Path(home['config_file']).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return (
                "the home's opencode.jsonc does not parse; render the home again into an empty "
                'folder'
            )
        if not isinstance(config, dict):
            config = {}
        found = (config.get('permissions'), config.get('policies'))
        if opencode_permissions.permissions_sha256(*found) != sha:
            return (
                "the home's opencode.jsonc holds permissions or policies other than its policy "
                'renders; render the home again into an empty folder'
            )
        return None

    def session_env(self, home: dict, base: Mapping[str, str]) -> dict[str, str]:
        env = home_env(home, base)
        folder = Path(home['dir'])
        xdg = folder / 'xdg'
        values = {
            'STUB_API_KEY': FAKE_KEY,
            'OPENCODE_DISABLE_AUTOUPDATE': '1',
            'OPENCODE_DISABLE_CLAUDE_CODE': '1',
            'OPENCODE_DISABLE_CLAUDE_CODE_SKILLS': '1',
            'OPENCODE_DISABLE_MODELS_FETCH': '1',
            'OPENCODE_DISABLE_FREE_MODELS': '1',
            'OPENCODE_TEST_HOME': str(folder / 'home'),
            'OPENCODE_CONFIG_DIR': str(Path(home['config_file']).parent),
            'OPENCODE_DB': str(xdg / 'o.db'),
            'XDG_CONFIG_HOME': str(xdg / 'config'),
            'XDG_DATA_HOME': str(xdg / 'data'),
            'XDG_STATE_HOME': str(xdg / 'state'),
            'XDG_CACHE_HOME': str(xdg / 'cache'),
            **dict.fromkeys(WATCHER_OFF, '1'),
        }
        for key, value in values.items():
            set_var(env, key, value)
        return env

    def system_config_dir(self) -> Path:
        """opencode's system configuration folder; kit run refuses it, protects it and reads
        its presence during a run."""
        return system_config_dir()

    def ripgrep_bin(self, env: Mapping[str, str], home_dir: Path | str) -> str:
        """opencode's `bin` folder in a session with environment `env`: its `XDG_CACHE_HOME`
        (the home's `xdg/cache` when it has none) plus `opencode/bin`."""
        cache = _env_value(env, 'XDG_CACHE_HOME') or str(Path(home_dir) / 'xdg' / 'cache')
        return os.path.normpath(os.path.join(cache, 'opencode', 'bin'))

    def ripgrep_walk(self, env: Mapping[str, str], bin_dir: str, cwd: str | None) -> RipgrepWalk:
        """The file opencode would run as `rg` (`ripgrep_walk`)."""
        return ripgrep_walk(env, bin_dir, cwd)

    def copy_home_for_canary(self, home: dict, dest: Path, canary_endpoint: str) -> dict:
        """Copy the home's watched files but its ripgrep copy, with empty `xdg/` and `home/`
        folders, then swap the endpoint text in the configuration without parsing it."""
        source = Path(home['dir'])
        target = Path(os.path.abspath(str(dest)))
        try:
            relative = Path(home['config_file']).relative_to(source)
        except ValueError:
            raise HomeError('config_file is outside the home folder') from None
        target.mkdir(parents=True, exist_ok=True)
        for rel in watch.watched_paths(source, self):
            if rel == RIPGREP_COPY:
                continue
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, target / rel)
        for name in ('xdg', 'home'):
            (target / name).mkdir(exist_ok=True)
        copy = dict(home)
        copy.update(dir=str(target), config_file=str(target / relative), endpoint=canary_endpoint)
        config = Path(copy['config_file'])
        if not config.is_file():
            raise HomeError('the opencode configuration is absent from the copied home')
        data = config.read_bytes()
        old = home['endpoint'].encode('ascii')
        if not old or old not in data:
            raise HomeError('the endpoint text is absent from the copied opencode configuration')
        config.write_bytes(data.replace(old, canary_endpoint.encode('ascii')))
        return copy

    def canary_argv(self, prompt: str, home: dict | None = None) -> list[str]:
        """The canary's arguments; the model is the home's `canary_model`, else a test home's."""
        model = (home or {}).get('canary_model') or MODEL
        return ['run', '--standalone', '--format', 'json', '--auto', '--model', model, prompt]

    def canary_step(self, command: str) -> dict:
        return {'tool': 'shell', 'args': {'command': command}}

    # ---- the envelope

    refused_tools = REFUSED_TOOLS

    def translate_event(self, envelope: object) -> dict:
        """The neutral event of an `execute.before` envelope; InvalidEventError when refused."""
        env, e, sha = _tool_event(envelope, self.name, BEFORE)
        act, command_obs, paths_obs = _act(env, e, sha)
        return {'kit_event': 1, **_frame(env, command_obs, paths_obs), 'act': act}

    def translate_note(self, envelope: object) -> dict:
        """The note of a `prompt` or `execute.after` envelope; InvalidNoteError when refused."""
        from harness_kit.notes import InvalidNoteError

        try:
            env, e, sha = read_envelope(envelope, self.name)
            if env['hook'] == PROMPT:
                frame = _frame(env, 'not_applicable', 'not_applicable')
                return {'kit_note': 1, **frame, 'note': _prompt_body(e)}
            env, e, sha = _tool_event(envelope, self.name, AFTER)
        except InvalidEventError as exc:
            raise InvalidNoteError(str(exc)) from None
        act, command_obs, paths_obs = _act(env, e, sha)
        return {'kit_note': 1, **_frame(env, command_obs, paths_obs), 'note': _outcome_body(e, act)}

    def refused_tool(self, envelope: object) -> tuple[str, str] | None:
        """(tool, reason) for an `execute.before` envelope naming a refused tool, else None."""
        try:
            _env, e, _sha = _tool_event(envelope, self.name, BEFORE)
        except InvalidEventError:
            return None
        tool = e['tool']
        return (tool, self.refused_tools[tool]) if tool in self.refused_tools else None

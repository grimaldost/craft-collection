"""opencode driver: a home whose configuration loads the kit shell as a plugin folder.

The shell sends the kit CLI one envelope per hook: the hook's event object as
opencode gives it (`payload`, its `JSON.stringify` text), the session's place
as the shell's lookups found it and the folder the session runs in. This
driver translates an envelope into the neutral event (`translate_event`) or
the note (`translate_note`), and names the tools the kit refuses by name
(`refused_tool`).
"""

from __future__ import annotations

import functools
import hashlib
import os
import re
from collections.abc import Mapping
from pathlib import Path

from harness_kit.event import InvalidEventError, parse_event
from harness_kit.harnesses import (
    FAKE_KEY,
    SHELLS_DIR,
    HomeError,
    check_endpoint,
    configured_argv,
    copy_home,
    finish_home,
    home_env,
    is_batch,
    materialize_shell,
    prepare_dir,
    read_version,
    set_var,
    write_json,
    write_note_config,
)

MODEL = 'stub/stub-model'
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
    pinned_version = '2.2.5'
    # `run` is the subcommand of every probe that ran a session; the flags are those of `canary_argv`.
    required_leading_tokens = ('run',)
    required_session_args = ('--standalone',)
    allowed_session_flags = ('--standalone', '--format', '--auto', '--model')
    project_config_paths = ('opencode.json', 'opencode.jsonc', '.opencode')
    # opencode's project walk has no stop before the filesystem root.
    project_walk = 'root'

    def binary_argv(self, env: Mapping[str, str]) -> list[str]:
        """The `opencode` argv; [] when missing. Its `.cmd` shim becomes the native binary."""
        argv = configured_argv(self.name, 'opencode', env)
        if argv and is_batch(argv[0]):
            native = resolve_shim(argv[0])
            return [native, *argv[1:]] if native else []
        return argv

    def version(self, env: Mapping[str, str]) -> str | None:
        return read_version(self.binary_argv(env), env, CONFIG_NAMES)

    def render_home(self, home: Path, endpoint: str, records: tuple[str, ...] = ()) -> dict:
        check_endpoint(endpoint)
        folder = prepare_dir(home)
        plugin = folder / 'kit-shell' / 'opencode-plugin'
        source = SHELLS_DIR / 'opencode' / 'index.js'
        entry, shell_config = materialize_shell(source, plugin, self.pinned_version, self.name)
        write_note_config(shell_config.parent, records, self.name)
        (folder / 'xdg').mkdir()
        config = folder / 'conf' / 'opencode.jsonc'
        stub = {
            'name': 'Stub',
            'env': ['STUB_API_KEY'],
            'package': '@opencode/ai/providers/openai-compatible',
            'settings': {'baseURL': endpoint + '/v1'},
            'models': {'stub-model': {'name': 'Stub Model'}},
        }
        write_json(
            config,
            {
                'update': 'disable',
                'model': MODEL,
                'providers': {'stub': stub},
                'plugins': [plugin.as_posix()],
            },
        )
        return finish_home(self.name, folder, endpoint, config, entry, shell_config)

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
        }
        for key, value in values.items():
            set_var(env, key, value)
        return env

    def copy_home_for_canary(self, home: dict, dest: Path, canary_endpoint: str) -> dict:
        """Copy the home, then swap the endpoint text in the configuration without parsing it."""
        copy = copy_home(home, dest, canary_endpoint)
        config = Path(copy['config_file'])
        data = config.read_bytes()
        old = home['endpoint'].encode('ascii')
        if not old or old not in data:
            raise HomeError('the endpoint text is absent from the copied opencode configuration')
        config.write_bytes(data.replace(old, canary_endpoint.encode('ascii')))
        return copy

    def canary_argv(self, prompt: str) -> list[str]:
        return ['run', '--standalone', '--format', 'json', '--auto', '--model', MODEL, prompt]

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

"""opencode driver: a home whose configuration loads the kit shell as a plugin folder."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

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

    def render_home(self, home: Path, endpoint: str) -> dict:
        check_endpoint(endpoint)
        folder = prepare_dir(home)
        plugin = folder / 'kit-shell' / 'opencode-plugin'
        source = SHELLS_DIR / 'opencode' / 'index.js'
        entry, shell_config = materialize_shell(source, plugin, self.pinned_version)
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

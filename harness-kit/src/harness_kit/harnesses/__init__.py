"""Per-harness drivers: the only place that knows a harness's files, flags and environment.

`get(name)` gives the driver of `claude-code` or `opencode`. A driver renders a
test home (the shell, its `shell_config.json`, the harness configuration and
`home.json`), builds the session environment over that home, copies the home
for the canary, and names the arguments the launcher checks.

`binary_argv` returns an empty list when the binary is missing; a caller never
runs an empty argv. On Windows a `.cmd` or `.bat` file is never run, from the
`KIT_HARNESS_ARGV_*` variable or from `PATH`, because its `%*` passes a prompt
through `cmd.exe`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import harness_kit

WINDOWS = os.name == 'nt'
FAKE_KEY = 'stub-not-a-key'
SHELL_TIMEOUT_S = 3
VERSION_TIMEOUT_S = 30
VERSION_RE = re.compile(r'\d+\.\d+\.\d+')
ENDPOINT_RE = re.compile(r'http://(127\.0\.0\.1|localhost):[0-9]{1,5}')
BATCH_SUFFIXES = ('.cmd', '.bat')
HOME_KEYS = ('kit_home', 'harness', 'endpoint', 'dir', 'config_file', 'shell_entry', 'shell_config')
SHELLS_DIR = Path(__file__).resolve().parent.parent / 'shells'
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


class HomeError(Exception):
    """A home that cannot be rendered or copied; the message is ASCII."""


class Driver(Protocol):
    name: str
    pinned_version: str
    required_leading_tokens: tuple[str, ...]
    required_session_args: tuple[str, ...]
    allowed_session_flags: tuple[str, ...]
    project_config_paths: tuple[str, ...]
    project_walk: str

    def binary_argv(self, env: Mapping[str, str]) -> list[str]: ...
    def version(self, env: Mapping[str, str]) -> str | None: ...
    def render_home(self, home: Path, endpoint: str) -> dict: ...
    def session_env(self, home: dict, base: Mapping[str, str]) -> dict[str, str]: ...
    def copy_home_for_canary(self, home: dict, dest: Path, canary_endpoint: str) -> dict: ...
    def canary_argv(self, prompt: str) -> list[str]: ...
    def canary_step(self, command: str) -> dict: ...


def names() -> tuple[str, ...]:
    return tuple(sorted(_drivers()))


def get(name: str) -> Driver:
    """The driver of one harness; KeyError for a name no driver has."""
    drivers = _drivers()
    if name not in drivers:
        raise KeyError(f'no driver for harness {name!a}; known: {", ".join(sorted(drivers))}')
    return drivers[name]


def _drivers() -> dict[str, Driver]:
    from harness_kit.harnesses.claude_code import ClaudeCode
    from harness_kit.harnesses.opencode import OpenCode

    return {d.name: d for d in (ClaudeCode(), OpenCode())}


# ---- shared helpers for the drivers


def argv_variable(name: str) -> str:
    """`claude-code` -> `KIT_HARNESS_ARGV_CLAUDE_CODE`."""
    return 'KIT_HARNESS_ARGV_' + re.sub(r'[^A-Za-z0-9]', '_', name).upper()


def configured_argv(name: str, command: str, env: Mapping[str, str]) -> list[str]:
    """The argv from the driver's variable, else `shutil.which(command)`; [] when neither gives one."""
    raw = env.get(argv_variable(name))
    if raw:
        try:
            argv = json.loads(raw)
        except ValueError:
            return []
        ok = isinstance(argv, list) and bool(argv)
        return list(argv) if ok and all(isinstance(a, str) and a for a in argv) else []
    found = shutil.which(command, path=env.get('PATH', ''))
    return [found] if found else []


def is_batch(path: str) -> bool:
    return WINDOWS and path.lower().endswith(BATCH_SUFFIXES)


def scratch_env(env: Mapping[str, str], scratch: Path, extra_names: tuple[str, ...]) -> dict:
    """`env` with every home variable, and the driver's configuration names, inside `scratch`."""
    out = dict(env)
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', *extra_names):
        set_var(out, key, str(scratch))
    drive, rest = os.path.splitdrive(str(scratch))
    set_var(out, 'HOMEDRIVE', drive)
    set_var(out, 'HOMEPATH', rest)
    return out


def read_version(
    argv: list[str], env: Mapping[str, str], extra_names: tuple[str, ...]
) -> str | None:
    """The first dotted triple `argv --version` prints, run from an empty scratch home."""
    if not argv:
        return None
    with tempfile.TemporaryDirectory(prefix='kit-version-') as td:
        scratch = Path(td)
        extra = {'creationflags': NO_WINDOW} if WINDOWS else {}
        try:
            proc = subprocess.run(  # noqa: S603 - argv from the driver, no shell
                [*argv, '--version'],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                env=scratch_env(env, scratch, extra_names),
                cwd=str(scratch),
                timeout=VERSION_TIMEOUT_S,
                check=False,
                **extra,
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    found = VERSION_RE.search(proc.stdout or '')
    return found.group(0) if found else None


def set_var(env: dict, key: str, value: str) -> None:
    """Set `key`, dropping any other spelling of it, so no two letter cases disagree."""
    for other in [k for k in env if k.upper() == key.upper() and k != key]:
        del env[other]
    env[key] = value


def home_env(home: dict, base: Mapping[str, str]) -> dict[str, str]:
    """`base` with the home variables inside the home and every proxy at the endpoint."""
    env = dict(base)
    profile = Path(home['dir']) / 'home'
    set_var(env, 'HOME', str(profile))
    set_var(env, 'USERPROFILE', str(profile))
    drive, rest = os.path.splitdrive(str(profile))
    set_var(env, 'HOMEDRIVE', drive)
    set_var(env, 'HOMEPATH', rest)
    set_var(env, 'APPDATA', str(profile / 'Roaming'))
    set_var(env, 'LOCALAPPDATA', str(profile / 'Local'))
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        set_var(env, key, home['endpoint'])
    set_var(env, 'NO_PROXY', '127.0.0.1,localhost')
    return env


def cli_argv() -> list[str]:
    """The kit CLI as the shells start it: this interpreter, isolated, this package first on its path."""
    parent = str(Path(harness_kit.__file__).resolve().parent.parent)
    bootstrap = (
        f'import sys; sys.path.insert(0, {parent!a}); '
        'from harness_kit.cli import main; sys.exit(main())'
    )
    return [sys.executable, '-I', '-c', bootstrap, 'judge']


def check_endpoint(endpoint: str) -> None:
    if not ENDPOINT_RE.fullmatch(endpoint or ''):
        raise HomeError(f'endpoint {endpoint!a} is not http://127.0.0.1:PORT')


def prepare_dir(home: Path) -> Path:
    """The absolute home folder, created; refused unless it was absent or empty."""
    folder = Path(os.path.abspath(str(home)))
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise HomeError(f'home folder is not empty: {str(folder)!a}')
    folder.mkdir(parents=True, exist_ok=True)
    profile = folder / 'home'
    for sub in (profile / 'Roaming', profile / 'Local'):
        sub.mkdir(parents=True, exist_ok=True)
    return folder


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def materialize_shell(source: Path, dest_dir: Path, pinned_version: str) -> tuple[Path, Path]:
    """Copy one shell file into `dest_dir` beside its `shell_config.json`."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    entry = dest_dir / source.name
    shutil.copyfile(source, entry)
    config = dest_dir / 'shell_config.json'
    write_json(
        config,
        {
            'kit_shell_config': 1,
            'cli_argv': cli_argv(),
            'timeout_s': SHELL_TIMEOUT_S,
            'harness_version': pinned_version,
        },
    )
    return entry, config


def finish_home(
    name: str, folder: Path, endpoint: str, config: Path, entry: Path, shell_config: Path
) -> dict:
    """Write `home.json` and return it."""
    home = dict(
        zip(
            HOME_KEYS,
            (1, name, endpoint, str(folder), str(config), str(entry), str(shell_config)),
            strict=True,
        )
    )
    write_json(folder / 'home.json', home)
    return home


def copy_home(home: dict, dest: Path, canary_endpoint: str) -> dict:
    """Copy the home byte for byte into `dest`; the descriptor of the copy.

    `shell_entry` and `shell_config` keep the paths the copied configuration names.
    """
    source = Path(home['dir'])
    target = Path(os.path.abspath(str(dest)))
    try:
        relative = Path(home['config_file']).relative_to(source)
    except ValueError:
        raise HomeError('config_file is outside the home folder') from None
    shutil.copytree(source, target, dirs_exist_ok=True)
    copy = dict(home)
    copy.update(dir=str(target), config_file=str(target / relative), endpoint=canary_endpoint)
    return copy

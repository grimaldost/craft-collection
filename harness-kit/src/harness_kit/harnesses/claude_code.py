"""Claude Code driver: a home whose user settings register the kit shell as a PreToolUse hook.

When the policy records notes, the same shell file is also registered, with `--note`, for
UserPromptSubmit and for PostToolUse and PostToolUseFailure.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from harness_kit import watch
from harness_kit.harnesses import (
    FAKE_KEY,
    HEADLESS,
    SHELLS_DIR,
    Grammar,
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

MATCHER = 'Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit'
# The note entries: a submitted prompt, and a shell call that succeeded or exited non-zero
# (PostToolUseFailure fires for the latter, never PostToolUse). They carry no `onFailure`.
RESULT_MATCHER = 'Bash|PowerShell'
MODEL = 'claude-sonnet-5-5'
CONFIG_NAMES = ('CLAUDE_CONFIG_DIR',)


class ClaudeCode:
    name = 'claude-code'
    pinned_version = '2.1.316'
    # `-p` is the only mode a probe ran; the flags are those of `canary_argv`.
    required_leading_tokens = ('-p',)
    required_session_args = ('--setting-sources', 'user')
    allowed_session_flags = (
        '-p',
        '--output-format',
        '--verbose',
        '--model',
        '--setting-sources',
        '--allowedTools',
    )
    project_config_paths = ('.claude/settings.json', '.claude/settings.local.json')
    # Headless only: the driver offers no interactive mode.
    modes = MappingProxyType(
        {
            HEADLESS: Grammar(
                leading=required_leading_tokens,
                required=required_session_args,
                allowed=allowed_session_flags,
            )
        }
    )
    # A walk to the drive root would meet the user layer itself under the profile.
    project_walk = 'work_tree'
    # The files the guard is read from. Claude Code writes its history and state into
    # `claude-config/` during a session, so only `settings.json` there is watched.
    watched_folders = ('kit-shell',)
    watched_files = ('claude-config/settings.json', 'home.json')
    excluded_names: tuple[str, ...] = ()

    def binary_argv(self, env: Mapping[str, str]) -> list[str]:
        """The `claude` argv; [] when missing. A `.cmd` or `.bat` is missing, never run."""
        argv = configured_argv(self.name, 'claude', env)
        return [] if not argv or is_batch(argv[0]) else argv

    def version(self, env: Mapping[str, str]) -> str | None:
        return read_version(self.binary_argv(env), env, CONFIG_NAMES)

    def render_home(self, home: Path, endpoint: str, records: tuple[str, ...] = ()) -> dict:
        check_endpoint(endpoint)
        folder = prepare_dir(home)
        source = SHELLS_DIR / 'claude_code' / 'kit_hook.py'
        entry, shell_config = materialize_shell(source, folder / 'kit-shell', self.pinned_version)
        write_note_config(shell_config.parent, records)
        config = folder / 'claude-config' / 'settings.json'
        hook = {
            'type': 'command',
            'command': sys.executable,
            'args': ['-I', str(entry)],
            'timeout': 30,
            'onFailure': 'block',
        }
        hooks = {'PreToolUse': [{'matcher': MATCHER, 'hooks': [hook]}]}
        note = {k: v for k, v in hook.items() if k != 'onFailure'}
        note['args'] = [*hook['args'], '--note']
        if 'prompt' in records:
            hooks['UserPromptSubmit'] = [{'hooks': [dict(note)]}]
        if 'outcome' in records:
            for name in ('PostToolUse', 'PostToolUseFailure'):
                hooks[name] = [{'matcher': RESULT_MATCHER, 'hooks': [dict(note)]}]
        write_json(config, {'hooks': hooks})
        rendered = watch.hash_files(folder, self, rendered=True)
        return finish_home(self.name, folder, endpoint, config, entry, shell_config, rendered)

    def session_env(self, home: dict, base: Mapping[str, str]) -> dict[str, str]:
        env = home_env(home, base)
        set_var(env, 'CLAUDE_CONFIG_DIR', str(Path(home['config_file']).parent))
        set_var(env, 'ANTHROPIC_BASE_URL', home['endpoint'])
        set_var(env, 'ANTHROPIC_AUTH_TOKEN', FAKE_KEY)
        set_var(env, 'DISABLE_AUTOUPDATER', '1')
        set_var(env, 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', '1')
        return env

    def copy_home_for_canary(self, home: dict, dest: Path, canary_endpoint: str) -> dict:
        # The endpoint reaches Claude Code through the environment, so the copy needs no edit.
        return copy_home(home, dest, canary_endpoint)

    def canary_argv(self, prompt: str) -> list[str]:
        # `--allowedTools` is variadic and would swallow a prompt placed after it, so it goes last.
        return [
            '-p',
            prompt,
            '--output-format',
            'stream-json',
            '--verbose',
            '--model',
            MODEL,
            '--setting-sources',
            'user',
            '--allowedTools',
            'Bash',
        ]

    def canary_step(self, command: str) -> dict:
        return {'tool': 'Bash', 'args': {'command': command, 'description': 'kit canary'}}

#!/usr/bin/env python3
"""Checks of what the opencode driver renders and sets to govern opencode's configuration.

Contract under test:
- every opencode home's `opencode.jsonc` holds `policies` beginning with the eight statements
  (deny every plugin but the kit's, by its absolute path with forward slashes; deny every MCP
  server; deny every provider and integration but the home's own, `stub` or `relay`), then a
  `tool.use` deny `TOOL:*` for `execute`, `opencode_worktree_create`, `opencode_session_move`
  and `experimental_image_generate`, in that order; `permissions` ending with the switch
  `TOOL * deny` of each, in the same order, and holding them alone (no policy section); and
  `experimental.image_generate` false; for a test home and a daily home;
- the session environment sets `OPENCODE_DISABLE_FILEWATCHER` and
  `OPENCODE_FILEWATCHER_DISABLE` to `1`;
- `system_config_dir()` is the folder the operating system gives as ProgramData plus
  `opencode` on Windows, and `/etc/opencode` elsewhere;
- each driver names the home folders kit protects: opencode `conf`, `kit-shell` and
  `xdg/config`; Claude Code `claude-config` and `kit-shell`; opencode also watches the files
  under `xdg/config` during a run;
- each driver names the home's ripgrep copy, which kit protects in a daily home that names a
  ripgrep: opencode `xdg/cache/opencode/bin/rg.exe` (`rg` off Windows), never the `bin` folder or
  `xdg/cache`; Claude Code none.

Stdlib-runnable: `python test_config_render.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import daily, harnesses
from kit_fixtures import run_module

WINDOWS = os.name == 'nt'
ENDPOINT = 'http://127.0.0.1:43210'
TOOLS = (
    'execute',
    'opencode_worktree_create',
    'opencode_session_move',
    'experimental_image_generate',
)
DAILY = """\
daily = 1

[relay]
listen_port = 47811
upstream_base = "http://127.0.0.1:47812"
route = "/v1/chat/completions"
key_env = "KIT_RENDER_TEST_KEY"
test = true
usage_include = true
default_model = "cell/stub-model"
upstream_timeout_s = 60

[relay.ceilings]
run_usd = 1.0
day_usd = 2.0
month_usd = 3.0

[[relay.model]]
id = "cell/stub-model"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0
max_output_tokens = 1000

[git]
name = "Render Test"
email = "render.test@example.invalid"
"""


def statements(kit: str, provider: str) -> list[dict]:
    def s(action: str, resource: str, effect: str) -> dict:
        return {'action': action, 'resource': resource, 'effect': effect}

    return [
        s('plugin.use', '*', 'deny'),
        s('plugin.use', kit, 'allow'),
        s('mcp.use', '*', 'deny'),
        s('provider.use', '*', 'deny'),
        s('provider.use', provider, 'allow'),
        s('integration.connect', '*', 'deny'),
        s('integration.use', '*', 'deny'),
        s('integration.use', provider, 'allow'),
        *(s('tool.use', f'{tool}:*', 'deny') for tool in TOOLS),
    ]


def switches() -> list[dict]:
    return [{'action': tool, 'resource': '*', 'effect': 'deny'} for tool in TOOLS]


def _config(home: dict) -> dict:
    return json.loads(Path(home['config_file']).read_text(encoding='utf-8'))


def _check(home: dict, provider: str) -> None:
    config = _config(home)
    kit = (Path(home['dir']) / 'kit-shell' / 'opencode-plugin').as_posix()
    assert config['plugins'] == [kit], config['plugins']
    assert config['policies'][: len(statements(kit, provider))] == statements(kit, provider)
    assert config['permissions'] == switches(), config['permissions']
    assert config['experimental'] == {'image_generate': False}, config.get('experimental')


def test_a_test_home_carries_the_statements_and_switches():
    folder = Path(tempfile.mkdtemp(prefix='kit-render-'))
    try:
        home = harnesses.get('opencode').render_home(folder / 'home', ENDPOINT)
        _check(home, 'stub')
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_a_daily_home_carries_them_with_the_relay():
    folder = Path(tempfile.mkdtemp(prefix='kit-render-'))
    try:
        path = folder / 'daily.toml'
        path.write_text(DAILY, encoding='utf-8')
        found = daily.load_daily(path, folder / 'state')
        home = harnesses.get('opencode').render_daily_home(folder / 'home', found)
        _check(home, 'relay')
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_the_session_turns_the_file_watcher_off():
    folder = Path(tempfile.mkdtemp(prefix='kit-render-'))
    try:
        driver = harnesses.get('opencode')
        home = driver.render_home(folder / 'home', ENDPOINT)
        env = driver.session_env(home, {})
        assert env['OPENCODE_DISABLE_FILEWATCHER'] == '1', env
        assert env['OPENCODE_FILEWATCHER_DISABLE'] == '1', env
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_the_system_folder_is_the_operating_systems():
    found = Path(harnesses.get('opencode').system_config_dir())
    if WINDOWS:
        from harness_kit.launcher import windows_pins

        assert found == Path(windows_pins()['PROGRAMDATA']) / 'opencode', found
    else:
        assert found == Path('/etc/opencode'), found


def test_each_driver_names_the_home_folders_it_protects():
    oc, cc = harnesses.get('opencode'), harnesses.get('claude-code')
    assert tuple(oc.protected_folders) == ('conf', 'kit-shell', 'xdg/config')
    assert tuple(cc.protected_folders) == ('claude-config', 'kit-shell')
    assert tuple(oc.run_watched_folders) == ('xdg/config',)
    assert tuple(cc.run_watched_folders) == ()


def test_each_driver_names_the_ripgrep_copy_it_protects_in_a_named_home():
    oc, cc = harnesses.get('opencode'), harnesses.get('claude-code')
    assert oc.ripgrep_copy == 'xdg/cache/opencode/bin/' + ('rg.exe' if WINDOWS else 'rg')
    assert cc.ripgrep_copy == ''
    assert oc.ripgrep_copy in oc.watched_files
    for folder in ('xdg/cache', 'xdg/cache/opencode/bin'):
        assert folder not in oc.protected_folders and folder not in oc.watched_files, folder


if __name__ == '__main__':
    run_module(globals(), 'the rendered opencode statements and switches')

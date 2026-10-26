"""Tests for governed_home.py: where the owner's governance files live.

The order is fixed by the 2026-10-25 discipline-mechanisms spec (Context):
`$SESSION_WORKFLOW_GOVERNED_HOME` when set (tests and the end-to-end run only),
else `$CLAUDE_CONFIG_DIR` when set, else `~/.claude`. Each step has its own test,
and every test passes an explicit environment mapping, so nothing here reads or
changes the real environment.

Stdlib-runnable: `python plugins/session-workflow/hooks/test_governed_home.py` prints `ok:`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import governed_home as gh

OVERRIDE = str(Path('/srv/governed-override'))
CONFIG = str(Path('/srv/claude-config'))


def test_the_override_wins_over_everything():
    env = {gh.OVERRIDE_ENV: OVERRIDE, gh.CONFIG_DIR_ENV: CONFIG}
    assert gh.governed_home(env) == Path(OVERRIDE)


def test_the_config_dir_is_next():
    assert gh.governed_home({gh.CONFIG_DIR_ENV: CONFIG}) == Path(CONFIG)


def test_the_home_claude_directory_is_last():
    assert gh.governed_home({}) == Path.home() / '.claude'


def test_an_empty_value_counts_as_unset():
    env = {gh.OVERRIDE_ENV: '', gh.CONFIG_DIR_ENV: '  '}
    assert gh.governed_home(env) == Path.home() / '.claude'
    assert gh.governed_home({gh.OVERRIDE_ENV: '', gh.CONFIG_DIR_ENV: CONFIG}) == Path(CONFIG)


def test_a_tilde_value_is_expanded():
    assert gh.governed_home({gh.OVERRIDE_ENV: '~/gov'}) == Path.home() / 'gov'


def test_governed_files_resolve_under_the_home():
    env = {gh.OVERRIDE_ENV: OVERRIDE}
    assert gh.GOVERNED_FILES == ('CLAUDE.md', 'settings.json', 'settings.local.json')
    assert gh.governed_path('CLAUDE.md', env) == Path(OVERRIDE) / 'CLAUDE.md'
    assert gh.governed_paths(env) == tuple(Path(OVERRIDE) / n for n in gh.GOVERNED_FILES)


def test_the_process_environment_is_the_default_mapping():
    import os

    saved = {k: os.environ.get(k) for k in (gh.OVERRIDE_ENV, gh.CONFIG_DIR_ENV)}
    try:
        os.environ[gh.OVERRIDE_ENV] = OVERRIDE
        assert gh.governed_home() == Path(OVERRIDE)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == '__main__':
    test_the_override_wins_over_everything()
    test_the_config_dir_is_next()
    test_the_home_claude_directory_is_last()
    test_an_empty_value_counts_as_unset()
    test_a_tilde_value_is_expanded()
    test_governed_files_resolve_under_the_home()
    test_the_process_environment_is_the_default_mapping()
    print('ok: governed_home resolves override, then CLAUDE_CONFIG_DIR, then ~/.claude')

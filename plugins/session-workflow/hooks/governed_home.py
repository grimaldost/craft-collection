"""Where the owner's governance files live: the one resolver every hook uses.

    from governed_home import governed_home, governed_path, governed_paths, GOVERNED_FILES

    governed_home()                 # Path of the governed home for this process
    governed_path('CLAUDE.md')      # that home / 'CLAUDE.md'
    governed_paths()                # one Path per name in GOVERNED_FILES
    governed_home({'CLAUDE_CONFIG_DIR': 'D:/cfg'})   # an explicit mapping instead of os.environ

Order: `$SESSION_WORKFLOW_GOVERNED_HOME` when set (tests and the end-to-end run
only; it moves nothing but this answer), else `$CLAUDE_CONFIG_DIR` when set, else
`~/.claude`. An empty or blank value counts as unset; `~` is expanded. The
governed files are the global `CLAUDE.md`, `settings.json` and
`settings.local.json` in that home.

The owner-acts gate and the governance-change notice resolve the path here and
nowhere else, so a test that points the override at a scratch directory moves
both. These variables are paths, not switches. Pure apart from reading the
mapping; stdlib only.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

OVERRIDE_ENV = 'SESSION_WORKFLOW_GOVERNED_HOME'
CONFIG_DIR_ENV = 'CLAUDE_CONFIG_DIR'
GOVERNED_FILES = ('CLAUDE.md', 'settings.json', 'settings.local.json')


def governed_home(environ: Mapping[str, str] | None = None) -> Path:
    """The governed home: the override, else CLAUDE_CONFIG_DIR, else ~/.claude."""
    env = os.environ if environ is None else environ
    for name in (OVERRIDE_ENV, CONFIG_DIR_ENV):
        value = (env.get(name) or '').strip()
        if value:
            return Path(value).expanduser()
    return Path.home() / '.claude'


def governed_path(name: str, environ: Mapping[str, str] | None = None) -> Path:
    """`name` (one of GOVERNED_FILES, by convention) under the governed home."""
    return governed_home(environ) / name


def governed_paths(environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    """Every governed file under the governed home, in GOVERNED_FILES order."""
    home = governed_home(environ)
    return tuple(home / name for name in GOVERNED_FILES)

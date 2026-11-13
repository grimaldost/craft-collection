"""Checker of the uv rule pack: the engineering-discipline plugin's uv core, called by the judge.

The checker holds no rule of its own. When the file is loaded it finds
`plugins/engineering-discipline/hooks/` from its own location in the
repository, puts that folder on `sys.path` (which also serves the core's own
sibling import) and imports the core under its own name, `uv_enforce`.
Bytecode writing is turned off first, so no cache folder appears under
`plugins/`. A core that is missing or does not load makes this file fail to
execute.

`check(act, observation)` answers:
- `cannot-tell` when the command was not observed or `act["cwd"]` is not a
  non-empty string;
- `match` exactly when the core's `verdict` blocks the command in that folder,
  with the plugin's override `CLAUDE_ALLOW_PIP=1` read from this process's
  environment; the detail names the words the core's `blocked_match` found;
- `no-match` otherwise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

CORE_FOLDER = Path(__file__).resolve().parents[3] / 'plugins' / 'engineering-discipline' / 'hooks'
if str(CORE_FOLDER) not in sys.path:
    sys.path.insert(0, str(CORE_FOLDER))

import uv_enforce  # noqa: E402 - the core's folder is on sys.path only from here

ALLOW_ENV = 'CLAUDE_ALLOW_PIP'


def check(act: dict, observation: dict) -> dict:
    """`match`, `no-match` or `cannot-tell` for one act, as the core decides it."""
    cwd = act.get('cwd')
    if observation.get('command') != 'observed' or not isinstance(cwd, str) or not cwd:
        return {'result': 'cannot-tell'}
    command = act.get('command')
    allow = os.environ.get(ALLOW_ENV) == '1'
    if uv_enforce.verdict(command, uv_enforce.cwd_is_uv_project(cwd), allow) != 'block':
        return {'result': 'no-match'}
    return {'result': 'match', 'detail': f'Blocked `{uv_enforce.blocked_match(command)}`.'}

"""Shared builders for the harness-kit tests: neutral events, policies, test runner.

Not a test module itself (no `test_` prefix); each test file imports it as a sibling.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SHA = 'a' * 64

_BASE_EVENT = {
    'kit_event': 1,
    'run_id': None,
    'harness': {'name': 'claude-code', 'version': '2.1.316'},
    'session': {'id': 's1', 'parent_id': None, 'root_id': None},
    'origin': 'unknown',
    'observation': {
        'session': 'observed',
        'parent': 'unavailable',
        'root': 'unavailable',
        'origin': 'unavailable',
        'command': 'observed',
        'paths': 'not_applicable',
    },
    'act': {
        'kind': 'shell',
        'command': 'echo hi',
        'argv': None,
        'paths': [],
        'cwd': '/w',
        'payload_sha256': SHA,
    },
}


def event(**over: object) -> dict:
    """A valid shell event; `over` maps dotted keys ('act.command') to new values."""
    ev = copy.deepcopy(_BASE_EVENT)
    for dotted, value in over.items():
        node = ev
        *parents, leaf = dotted.split('.')
        for key in parents:
            node = node[key]
        node[leaf] = value
    return ev


def write_event(paths: list[str], **over: object) -> dict:
    """A valid file-write event over `paths`, its command not applicable."""
    base = {
        'act.kind': 'file_write',
        'act.command': None,
        'act.paths': paths,
        'observation.command': 'not_applicable',
        'observation.paths': 'observed',
    }
    base.update(over)
    return event(**base)


SAMPLE_POLICY = """\
version = 1

[launcher]
test_roots = ["/abs/path"]
forbidden_roots = []

[[rule]]
id = "no-config-write"
effect = "deny"
governed = true
kinds = ["shell", "file_write"]
command_regex = "settings\\\\.json"
path_glob = ["**/settings.json"]
origin_in = ["child"]
reason = "configuration writes are governed"
"""


def run_module(namespace: dict, label: str) -> None:
    """Run every `test_*` function of a module namespace, then print the sentinel."""
    names = sorted(n for n, f in namespace.items() if n.startswith('test_') and callable(f))
    for name in names:
        namespace[name]()
    print(f'ok: {label} ({len(names)} checks)')

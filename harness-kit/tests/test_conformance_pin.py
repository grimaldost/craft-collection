#!/usr/bin/env python3
"""Checks of the conformance files' part in a re-pin.

Contract under test:
- every conformance file (`conformance/test_*.py`) declares `CELLS_BY_HARNESS`,
  a dict from each harness name to the tuple of the cell names it runs for that
  harness, with the cells each file runs;
- every cell a conformance file starts with `kit run` passes `--accept-version`
  with the value of `KIT_CONFORMANCE_ACCEPT_VERSION` when it is set, and nothing
  when it is not: each `kit run` argument list in the files carries the shared
  `accept_args()`;
- the hung-guard matrix's rows carry `cell` (`hung-` and the row's `shell`
  label) and `harness_version`, beside their other keys, and its cells run the
  binary that `KIT_HARNESS_ARGV_*` names, whose version the row records.

Stdlib-runnable: `python test_conformance_pin.py`.
"""

from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path

from kit_fixtures import run_module

CONFORMANCE = Path(__file__).resolve().parents[1] / 'conformance'
if str(CONFORMANCE) not in sys.path:
    sys.path.insert(0, str(CONFORMANCE))

HARNESSES = ('claude-code', 'opencode')
ACCEPT_ENV = 'KIT_CONFORMANCE_ACCEPT_VERSION'
LAUNCHED = ('guard-loaded', 'deny-shell', 'deny-write', 'allow-shell', 'run-identity', 'heartbeat')
HUNG = ('hung-git-bash', 'hung-pwsh-7', 'hung-powershell-5.1')
EXPECTED = {
    'test_conformance': {
        'claude-code': (*LAUNCHED, 'hung-guard', 'not-launched'),
        'opencode': (*LAUNCHED, 'hung-guard', 'launcher-required'),
    },
    'test_rules': dict.fromkeys(HARNESSES, ('uv-deny', 'uv-allow-outside', 'uv-allow-mention')),
    'test_guards': dict.fromkeys(
        HARNESSES, ('series-guard', 'owner-acts-deny', 'owner-acts-allow')
    ),
    'test_kill_matrix': {
        'claude-code': HUNG,
        'opencode': (*HUNG, 'hung-system32-off-path'),
    },
}


def _files() -> list[Path]:
    return sorted(CONFORMANCE.glob('test_*.py'))


def test_every_conformance_file_declares_its_cells_by_harness():
    assert len(_files()) >= 9, _files()
    for path in _files():
        module = importlib.import_module(path.stem)
        cells = getattr(module, 'CELLS_BY_HARNESS', None)
        assert isinstance(cells, dict), (path.name, cells)
        assert set(cells) == set(HARNESSES), (path.name, sorted(cells))
        for harness, names in cells.items():
            assert isinstance(names, tuple), (path.name, harness, names)
            assert all(isinstance(n, str) and n for n in names), (path.name, harness, names)
            assert len(set(names)) == len(names), (path.name, harness, names)
        assert any(cells.values()), (path.name, cells)
        if path.stem in EXPECTED:
            assert cells == EXPECTED[path.stem], (path.name, cells)


def _accept_args():
    from test_conformance import accept_args

    return accept_args


def test_accept_args_follow_the_variable():
    accept_args = _accept_args()
    saved = os.environ.pop(ACCEPT_ENV, None)
    try:
        assert accept_args() == [], accept_args()
        os.environ[ACCEPT_ENV] = ''
        assert accept_args() == [], accept_args()
        os.environ[ACCEPT_ENV] = '2.2.6'
        assert accept_args() == ['--accept-version', '2.2.6'], accept_args()
    finally:
        os.environ.pop(ACCEPT_ENV, None)
        if saved is not None:
            os.environ[ACCEPT_ENV] = saved


def _run_lists(tree: ast.AST) -> list[ast.List]:
    """Every list literal that starts `kit run`'s arguments: `'run', '--harness', ...`."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.List) or len(node.elts) < 2:
            continue
        head = [e.value if isinstance(e, ast.Constant) else None for e in node.elts[:2]]
        if head == ['run', '--harness']:
            found.append(node)
    return found


def _carries_accept_args(node: ast.List) -> bool:
    for element in node.elts:
        call = element.value if isinstance(element, ast.Starred) else None
        if isinstance(call, ast.Call) and getattr(call.func, 'id', None) == 'accept_args':
            return True
    return False


def test_every_kit_run_of_a_conformance_file_carries_accept_args():
    counted = 0
    for path in _files():
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in _run_lists(tree):
            counted += 1
            assert _carries_accept_args(node), (path.name, node.lineno)
        text = path.read_text(encoding='utf-8')
        # A file that starts `kit run` names its arguments only through such lists.
        if "'run', '--harness'" not in text:
            assert path.stem == 'test_kill_matrix', path.name
    assert counted >= 10, counted


def test_the_kill_matrix_rows_carry_cell_and_harness_version():
    import test_kill_matrix as matrix

    row = matrix.new_row('opencode', 'pwsh-7', '2.2.5')
    assert row['cell'] == 'hung-pwsh-7', row
    assert row['harness_version'] == '2.2.5', row
    assert row['harness'] == 'opencode' and row['shell'] == 'pwsh-7', row
    assert row['passed'] is False, row
    off = matrix.new_row('opencode', matrix.NO_SYSTEM32, None)
    assert off['cell'] == 'hung-system32-off-path' and off['harness_version'] is None, off
    planned = [(h, c) for h, c, _shell, _off in matrix.plan_cells()]
    assert planned == [(h, c) for h in HARNESSES for c in EXPECTED['test_kill_matrix'][h]]
    for _h, cell, shell, off in matrix.plan_cells():
        assert cell == 'hung-' + (matrix.NO_SYSTEM32 if off else shell), (cell, shell, off)


def test_the_kill_matrix_runs_the_binary_its_variable_names():
    import test_kill_matrix as matrix

    named = {
        'KIT_HARNESS_ARGV_CLAUDE_CODE': '["C:/fake/claude-fake.exe"]',
        'KIT_HARNESS_ARGV_OPENCODE': '["C:/fake/opencode-fake.exe", "--x"]',
    }
    env = {'PATH': '', 'KIT_STATE_ROOT': 'C:/state'}
    assert matrix.harness_binary('claude-code', env, named) == ['C:/fake/claude-fake.exe']
    assert matrix.harness_binary('opencode', env, named) == ['C:/fake/opencode-fake.exe', '--x']


if __name__ == '__main__':
    run_module(globals(), 'conformance files in a re-pin')

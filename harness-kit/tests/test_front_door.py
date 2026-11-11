#!/usr/bin/env python3
"""Checks of the front door: the README, the portability pointer and the wheel.

Contract under test:
- the README states in its first 40 lines that a shell's refusal is feedback and
  that the objective `prevention` is `absent`;
- the README names every subcommand `kit` has (read from the argument parser, so
  a new subcommand reddens this test until the README names it) and the exit
  codes the launcher and the canary use;
- `docs/portability.md` points at the README under its enforcement ladder;
- the built wheel ships the shells and the two contract files.

Stdlib-runnable: `python test_front_door.py`. The wheel check prints a `skip:`
line of its own when `uv` is not on `PATH`.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
REPO = KIT_ROOT.parent
README = KIT_ROOT / 'README.md'
PORTABILITY = REPO / 'docs' / 'portability.md'
sys.path.insert(0, str(KIT_ROOT / 'src'))

from harness_kit import cli  # noqa: E402

WHEEL_MEMBERS = (
    'harness_kit/shells/claude_code/kit_hook.py',
    'harness_kit/shells/opencode/index.js',
    'harness_kit/contracts/claude_code.toml',
    'harness_kit/contracts/opencode.toml',
)


def _subcommand_paths(parser: argparse.ArgumentParser, prefix: str = 'kit') -> list[str]:
    """Every subcommand of the parser, nested ones joined: `kit state path`."""
    paths: list[str] = []
    for action in parser._actions:  # argparse has no public listing
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                path = f'{prefix} {name}'
                nested = _subcommand_paths(child, path)
                paths.extend(nested or [path])
    return paths


def _readme() -> str:
    assert README.is_file(), f'missing {README}'
    return README.read_text(encoding='utf-8')


def test_readme_states_the_prevention_limit_in_its_first_40_lines():
    head = '\n'.join(_readme().splitlines()[:40])
    assert re.search(r'feedback', head, re.IGNORECASE), head
    assert re.search(r'`prevention`[^\n]*`absent`|`absent`[^\n]*`prevention`', head), head


def test_readme_names_every_subcommand():
    text = _readme()
    paths = _subcommand_paths(cli.build_parser())
    assert 'kit state path' in paths and 'kit home render' in paths, paths
    missing = [p for p in paths if p not in text]
    assert not missing, missing


def test_readme_names_the_run_subcommand():
    # `run` is dispatched ahead of the parser, so the parser lists it with no children.
    assert 'kit run' in _readme()


def test_readme_names_the_exit_codes():
    text = _readme()
    for code in ('64', '65', '70'):
        assert re.search(rf'\b{code}\b', text), code


def test_readme_names_the_state_root_and_the_doctor_states():
    text = _readme()
    for word in ('KIT_STATE_ROOT', 'KIT_POLICY', 'tested', 'degraded', 'absent', 'unknown'):
        assert word in text, word


def test_portability_page_points_at_the_readme_under_the_enforcement_ladder():
    text = PORTABILITY.read_text(encoding='utf-8')
    match = re.search(r'^## Enforcement ladder.*?(?=^## )', text, re.MULTILINE | re.DOTALL)
    assert match, 'no enforcement ladder section'
    assert 'harness-kit/README.md' in match.group(0), match.group(0)


def test_wheel_ships_the_shells_and_the_contracts():
    uv = shutil.which('uv')
    if uv is None:
        print('skip: uv is not on PATH; the wheel was not built')
        return
    with tempfile.TemporaryDirectory() as td:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                uv,
                'build',
                '--wheel',
                '--project',
                str(KIT_ROOT),
                '--python',
                sys.executable,
                '--out-dir',
                td,
            ],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr
        wheels = sorted(Path(td).glob('harness_kit-*.whl'))
        assert len(wheels) == 1, wheels
        with zipfile.ZipFile(wheels[0]) as zf:
            names = set(zf.namelist())
    missing = [m for m in WHEEL_MEMBERS if m not in names]
    assert not missing, (missing, sorted(names))


if __name__ == '__main__':
    test_readme_states_the_prevention_limit_in_its_first_40_lines()
    test_readme_names_every_subcommand()
    test_readme_names_the_run_subcommand()
    test_readme_names_the_exit_codes()
    test_readme_names_the_state_root_and_the_doctor_states()
    test_portability_page_points_at_the_readme_under_the_enforcement_ladder()
    test_wheel_ships_the_shells_and_the_contracts()
    print('ok: front door')

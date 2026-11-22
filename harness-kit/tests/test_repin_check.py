#!/usr/bin/env python3
"""Checks of `conformance/repin_check.py`.

Contract under test, on fixture results nested one folder deep under the folder
given, as one base per conformance file leaves them:
- for a harness, it exits 0 when every cell each conformance file declares for
  it in `CELLS_BY_HARNESS` has a row, every row passed or failed with
  `accepted_failure` `loopback-fetch-refused`, and every row holds the same
  `harness_version`, the contract's `[harness] version` (the package's
  contract, or `--contract FILE`); rows of another harness are not read;
- otherwise it exits 1 and prints one line per cause, naming it: a missing
  cell, a failed cell, a failed row carrying another reason, mixed versions, a
  contract version that differs, an unreadable results file.

Stdlib-runnable: `python test_repin_check.py`.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tomllib
from kit_fixtures import SRC, run_module

CONFORMANCE = Path(__file__).resolve().parents[1] / 'conformance'
CHECK = CONFORMANCE / 'repin_check.py'
if str(CONFORMANCE) not in sys.path:
    sys.path.insert(0, str(CONFORMANCE))
HARNESSES = ('claude-code', 'opencode')
ACCEPTED = 'loopback-fetch-refused'


def contract_version(harness: str) -> str:
    path = SRC / 'harness_kit' / 'contracts' / (harness.replace('-', '_') + '.toml')
    return tomllib.loads(path.read_text(encoding='utf-8'))['harness']['version']


def declared() -> dict[str, dict[str, tuple[str, ...]]]:
    """Each conformance file's `CELLS_BY_HARNESS`, by the file's stem."""
    out = {}
    for path in sorted(CONFORMANCE.glob('test_*.py')):
        out[path.stem] = importlib.import_module(path.stem).CELLS_BY_HARNESS
    return out


def write_results(folder: Path, versions: dict[str, str], edit=None) -> None:
    """One subfolder per conformance file, holding its results file with a passing row per
    declared cell of each harness; `edit(stem, rows)` may change the rows first."""
    for stem, cells in declared().items():
        rows = []
        for harness in HARNESSES:
            for cell in cells.get(harness, ()):
                rows.append(
                    {
                        'cell': cell,
                        'harness': harness,
                        'harness_version': versions[harness],
                        'passed': True,
                        'stub_log': '/home/user/stub.jsonl',
                        'work_dir': '/home/user/work',
                        'run_id': None,
                    }
                )
        if edit is not None:
            rows = edit(stem, rows)
        sub = folder / stem
        sub.mkdir(parents=True)
        name = stem.removeprefix('test_').replace('_', '-') + '-results.json'
        (sub / name).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')


def pinned() -> dict[str, str]:
    return {h: contract_version(h) for h in HARNESSES}


def check(harness: str, results: Path, *more: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(CHECK), '--harness', harness, '--results', str(results), *more],
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=120,
    )


def passes(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert proc.stdout.startswith('ok: '), proc.stdout


def fails(proc: subprocess.CompletedProcess, *needles: str) -> list[str]:
    assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
    lines = proc.stdout.splitlines()
    for needle in needles:
        assert any(needle in line for line in lines), (needle, lines)
    return lines


def _set(cell: str, harness: str, **values):
    def edit(stem, rows):
        for row in rows:
            if row['cell'] == cell and row['harness'] == harness:
                row.update(values)
        return rows

    return edit


def test_a_complete_passing_run_at_the_contracts_version_passes():
    with tempfile.TemporaryDirectory() as td:
        write_results(Path(td), pinned())
        for harness in HARNESSES:
            passes(check(harness, Path(td)))


def test_a_failed_row_with_the_accepted_reason_passes():
    with tempfile.TemporaryDirectory() as td:
        edit = _set('perm-webfetch-allow', 'opencode', passed=False, accepted_failure=ACCEPTED)
        write_results(Path(td), pinned(), edit)
        passes(check('opencode', Path(td)))


def test_a_missing_cell_fails_naming_it():
    def edit(stem, rows):
        return [r for r in rows if not (r['cell'] == 'hung-pwsh-7' and r['harness'] == 'opencode')]

    with tempfile.TemporaryDirectory() as td:
        write_results(Path(td), pinned(), edit)
        lines = fails(check('opencode', Path(td)), 'hung-pwsh-7')
        assert len(lines) == 1, lines
        passes(check('claude-code', Path(td)))


def test_a_failed_cell_fails_naming_it():
    with tempfile.TemporaryDirectory() as td:
        write_results(Path(td), pinned(), _set('deny-shell', 'claude-code', passed=False))
        lines = fails(check('claude-code', Path(td)), 'deny-shell')
        assert len(lines) == 1, lines


def test_a_failed_row_with_another_reason_fails_naming_it():
    with tempfile.TemporaryDirectory() as td:
        edit = _set('perm-webfetch-allow', 'opencode', passed=False, accepted_failure='other')
        write_results(Path(td), pinned(), edit)
        fails(check('opencode', Path(td)), 'perm-webfetch-allow')
        assert "'other'" in check('opencode', Path(td)).stdout


def test_mixed_versions_fail_naming_them():
    with tempfile.TemporaryDirectory() as td:
        version = pinned()['opencode']
        write_results(Path(td), pinned(), _set('patch-plain', 'opencode', harness_version='2.2.6'))
        lines = fails(check('opencode', Path(td)), '2.2.6')
        assert any(version in line and '2.2.6' in line for line in lines), lines


def test_a_contract_version_that_differs_fails_naming_both():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        moved = {'claude-code': '2.1.400', 'opencode': '2.3.0'}
        write_results(base / 'results', moved)
        for harness in HARNESSES:
            proc = check(harness, base / 'results')
            fails(proc, moved[harness], contract_version(harness))
            # The re-pin: the same results against a contract edited to the new version pass.
            source = SRC / 'harness_kit' / 'contracts' / (harness.replace('-', '_') + '.toml')
            edited = base / f'{harness}.toml'
            shutil.copyfile(source, edited)
            text = edited.read_text(encoding='utf-8')
            text = re.sub(
                r'(?m)^version = "[^"]*"$', f'version = "{moved[harness]}"', text, count=1
            )
            edited.write_text(text, encoding='utf-8')
            passes(check(harness, base / 'results', '--contract', str(edited)))
            # And the pinned results fail against the edited contract.
            write_results(base / f'pinned-{harness}', pinned())
            fails(check(harness, base / f'pinned-{harness}', '--contract', str(edited)), 'contract')


def test_rows_of_another_harness_are_not_read():
    with tempfile.TemporaryDirectory() as td:
        write_results(Path(td), {'claude-code': '0.0.1', 'opencode': pinned()['opencode']})
        passes(check('opencode', Path(td)))
        fails(check('claude-code', Path(td)), '0.0.1')


def test_an_unreadable_results_file_fails():
    with tempfile.TemporaryDirectory() as td:
        write_results(Path(td), pinned())
        (Path(td) / 'test_patch' / 'patch-results.json').write_text('[', encoding='utf-8')
        fails(check('opencode', Path(td)), 'patch-results.json')


def test_an_empty_folder_fails_on_every_declared_cell():
    with tempfile.TemporaryDirectory() as td:
        lines = fails(check('claude-code', Path(td)), 'guard-loaded', 'uv-deny')
        wanted = sum(len(cells.get('claude-code', ())) for cells in declared().values())
        assert len(lines) == wanted, (len(lines), wanted)


if __name__ == '__main__':
    run_module(globals(), 'repin check')

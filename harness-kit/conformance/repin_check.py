#!/usr/bin/env python3
"""Re-pin check: do the conformance results under a folder cover one harness version?

`python repin_check.py --harness NAME --results DIR [--contract FILE]` reads every
`*-results.json` at any depth under DIR (one base per conformance file leaves
them one folder down), keeps the rows of the harness NAME, and exits 0 only when:

- every cell that a conformance file beside this one declares for NAME in its
  `CELLS_BY_HARNESS` has a row;
- every row passed, or failed with `accepted_failure` holding the one reason a
  failure is accepted for, `loopback-fetch-refused` (a loopback fetch that
  opencode refuses by itself, in the webfetch control cell);
- every row holds the same `harness_version`, and that version is the
  `[harness] version` of the contract: the package's contract of NAME, or FILE.

Otherwise it exits 1 and prints one line per missing cell, failed cell, version
or unreadable file. A re-pin runs every conformance file against the new version
with `KIT_CONFORMANCE_ACCEPT_VERSION`, then this check against the contract
edited to that version (the README, "Re-pinning a harness version").

Stdlib-runnable: `python repin_check.py --harness opencode --results DIR`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import tomllib

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / 'src'
RESULTS_GLOB = '*-results.json'
ACCEPTED_FAILURE = 'loopback-fetch-refused'
HARNESSES = ('claude-code', 'opencode')


def _ascii(text: object) -> str:
    return str(text).encode('ascii', 'backslashreplace').decode('ascii').replace('\n', ' ')


def _shown(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def declared_cells(harness: str) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    """Each conformance file beside this one, by name, with the cells it declares for
    `harness`; and a line for each file that declares none or does not import."""
    for folder in (HERE, SRC):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    cells: dict[str, tuple[str, ...]] = {}
    problems: list[str] = []
    for path in sorted(HERE.glob('test_*.py')):
        try:
            by_harness = getattr(importlib.import_module(path.stem), 'CELLS_BY_HARNESS', None)
        except Exception as exc:  # a file that cannot be read declares nothing
            problems.append(f'declared: {path.name} does not import: {type(exc).__name__}')
            continue
        if not isinstance(by_harness, dict):
            problems.append(f'declared: {path.name} declares no CELLS_BY_HARNESS')
            continue
        cells[path.name] = tuple(by_harness.get(harness, ()))
    return cells, problems


def read_rows(folder: Path) -> tuple[list[tuple[Path, dict]], list[str]]:
    """The rows of every results file at any depth under `folder`, each with its file."""
    rows: list[tuple[Path, dict]] = []
    problems: list[str] = []
    for path in sorted(folder.rglob(RESULTS_GLOB)):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            problems.append(f'unreadable: {path}: {type(exc).__name__}')
            continue
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            problems.append(f'unreadable: {path}: not a list of rows')
            continue
        rows += [(path, row) for row in data]
    return rows, problems


def contract_version(path: Path) -> str | None:
    """The contract's `[harness] version`, or None when the file holds none."""
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    version = (data.get('harness') or {}).get('version')
    return version if isinstance(version, str) and version else None


def check(
    harness: str,
    cells: dict[str, tuple[str, ...]],
    rows: list[tuple[Path, dict]],
    contract: str | None,
) -> list[str]:
    """One line per missing cell, failed cell and version; none when the results cover the
    contract's version of `harness`."""
    mine = [(path, row) for path, row in rows if row.get('harness') == harness]
    seen = {row.get('cell') for _path, row in mine}
    lines = [
        f'missing: {harness} cell {cell} of {name} has no row'
        for name, declared in cells.items()
        for cell in declared
        if cell not in seen
    ]
    for path, row in mine:
        if row.get('passed') is True:
            continue
        cell, reason = _shown(row.get('cell')), row.get('accepted_failure')
        if reason == ACCEPTED_FAILURE:
            continue
        if reason is None:
            lines.append(f'failed: {harness} cell {cell} did not pass ({path.name})')
        else:
            lines.append(
                f'failed: {harness} cell {cell} carries accepted_failure {reason!r}, not '
                f'{ACCEPTED_FAILURE} ({path.name})'
            )
    versions = sorted({_shown(row.get('harness_version')) for _path, row in mine})
    named = _shown(contract)
    if len(versions) > 1:
        lines.append(
            f'version: the rows of {harness} hold more than one harness_version, '
            f'{", ".join(versions)}; the contract names {named}'
        )
    elif versions and versions[0] != contract:
        lines.append(
            f'version: the rows of {harness} hold harness_version {versions[0]}; the contract '
            f'names {named}'
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='repin_check.py',
        description='Check that conformance results cover a harness version every cell needs.',
    )
    parser.add_argument('--harness', required=True, choices=HARNESSES)
    parser.add_argument('--results', required=True, metavar='DIR', help='the results folder')
    parser.add_argument(
        '--contract', metavar='FILE', help="the contract (default: the package's, for the harness)"
    )
    args = parser.parse_args(argv)
    results = Path(args.results)
    default = SRC / 'harness_kit' / 'contracts' / (args.harness.replace('-', '_') + '.toml')
    contract_file = Path(args.contract) if args.contract else default
    problems: list[str] = []
    if not results.is_dir():
        problems.append(f'unreadable: {results} is not a folder')
    try:
        contract = contract_version(contract_file)
    except (OSError, ValueError) as exc:
        contract = None
        problems.append(f'unreadable: {contract_file}: {type(exc).__name__}')
    else:
        if contract is None:
            problems.append(f'version: {contract_file} holds no [harness] version')
    cells, found = declared_cells(args.harness)
    problems += found
    rows, found = read_rows(results) if results.is_dir() else ([], [])
    problems += found
    problems += check(args.harness, cells, rows, contract)
    for line in problems:
        print(_ascii(line))
    if problems:
        return 1
    mine = sum(1 for _path, row in rows if row.get('harness') == args.harness)
    wanted = sum(len(declared) for declared in cells.values())
    print(
        _ascii(
            f'ok: {args.harness} {contract}: {mine} rows under {results} cover the {wanted} '
            f'cells of {len(cells)} conformance files, each passed or failed with the accepted '
            "reason, at the contract's version"
        )
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

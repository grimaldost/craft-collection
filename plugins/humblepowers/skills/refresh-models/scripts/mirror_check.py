#!/usr/bin/env python3
"""Walk the registered downstream copies of tier / model / price data.

    mirror_check.py                       # $MODEL_MIRRORS_FILE, else ~/.claude/model-mirrors.toml
    mirror_check.py --bindings <file>     # an explicit registry

Step 6 of /refresh-models used to be an instruction a reader performed. It was
measured on 2026-09-05: nine sites registered in prose, zero walked after the
2026-08-11 lineup change, and two sibling estimators carried a superseded price
for three weeks. This is the same step as a command.

Two independent arms, because they catch different failures:

* Per registered site -- hygiene. The path still exists; the site has a
  ``backlog`` row or a ``status`` saying why not; its ``stamp`` matches the
  canonical ``[meta].last_reviewed`` EXACTLY. Equality, never age: two clocks
  let a copy certify itself fresh, and the age tripwire then measures the stamp
  rather than the lineup.
* Across the registered roots -- the catch-all grep for ``[[retired]]``
  patterns. This is the arm that finds a mirror nobody wrote down, which is how
  a second price table went unregistered until an audit tripped over it.

Exit 0 clean (an absent registry included -- that is the correct state for a
fresh environment, and it is REPORTED, never silent), 1 on findings, 2 when the
registry cannot be read at all. A gate that cannot answer must say so rather
than pass.

Stdlib only, ASCII output. Unlike the sibling ``lineup_check.py``, which reads
the canonical file with a regex so it runs anywhere, this one uses ``tomllib``:
the registry is an array of tables with nested values, where a regex would be
guesswork. Python 3.11+, which this repository already requires.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import tomllib

BINDINGS_ENV = 'MODEL_MIRRORS_FILE'
DEFAULT_BINDINGS = Path.home() / '.claude' / 'model-mirrors.toml'
ROLES = ('resolution-path', 'fallback', 'example', 'prose')
_SKIP_DIRS = {'.git', '__pycache__', '.venv', 'node_modules', '.ruff_cache', '.mypy_cache'}
_TEXT_SUFFIXES = {
    '.py',
    '.md',
    '.toml',
    '.json',
    '.yaml',
    '.yml',
    '.txt',
    '.cfg',
    '.ini',
    '.sh',
    '.js',
    '.ts',
}


def resolve_bindings(explicit: str | None = None) -> Path:
    """The registry to walk: ``--bindings``, else ``$MODEL_MIRRORS_FILE``, else the default."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(BINDINGS_ENV, '').strip()
    return Path(env) if env else DEFAULT_BINDINGS


def canonical_last_reviewed(path: Path) -> str | None:
    """``[meta].last_reviewed`` from the canonical tier data, or None if unreadable."""
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = data.get('meta', {}).get('last_reviewed')
    return value if isinstance(value, str) else None


def is_excluded(path: Path, excludes: list[dict[str, Any]]) -> str | None:
    """The ``reason`` of the first exclusion matching ``path``, else None."""
    posix = path.as_posix()
    for rule in excludes:
        glob = str(rule.get('glob', ''))
        if glob and (path.match(glob) or _glob_hits(posix, glob)):
            return str(rule.get('reason', 'no reason given'))
    return None


def _glob_hits(posix: str, glob: str) -> bool:
    """``**/tasks/**`` should hit any path with a ``tasks`` segment, wherever the
    walk started. ``Path.match`` anchors at the right, so it does not."""
    core = glob.strip('*').strip('/')
    return bool(core) and f'/{core}/' in f'/{posix}/'


def check_site(site: dict[str, Any], reviewed: str | None) -> list[str]:
    """Findings for one registered site. Empty means clean."""
    where = str(site.get('path', '<no path>'))
    found: list[str] = []

    role = site.get('role')
    if role is not None and role not in ROLES:
        found.append(f'{where}: unknown role {role!r}; known roles: {", ".join(ROLES)}')
    elif role == 'resolution-path':
        found.append(
            f'{where}: role = "resolution-path" -- this copy still DECIDES a run. '
            'The goal is zero such sites: the artefact carries the resolved value '
            'and the copy is a dated floor.'
        )

    if not site.get('backlog') and not site.get('status'):
        found.append(
            f'{where}: no backlog row and no status. A registered mirror that nobody '
            "tracks drifts silently -- name its repository's backlog row, or say why "
            'there is none.'
        )

    path = Path(where)
    if not path.exists():
        found.append(f'{where}: path does not exist; the registry points at a file that moved.')
        return found

    stamp = site.get('stamp')
    if stamp:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError as exc:
            found.append(f'{where}: cannot read the file to check its stamp ({exc.strerror}).')
            return found
        if reviewed is None:
            found.append(f'{where}: has a stamp, but the canonical last_reviewed is unreadable.')
        elif f'{stamp} {reviewed}' not in text:
            found.append(
                f'{where}: stale stamp. Expected the file to carry "{stamp} {reviewed}" '
                '(the canonical last_reviewed), and it does not.'
            )
    return found


def walk_retired(
    retired: list[dict[str, Any]], excludes: list[dict[str, Any]]
) -> tuple[list[str], int]:
    """Findings for every retired pattern still present, and how many files were excluded."""
    found: list[str] = []
    excluded = 0
    for rule in retired:
        raw = str(rule.get('pattern', ''))
        if not raw:
            found.append('a [[retired]] entry has no pattern; nothing to search for.')
            continue
        try:
            pattern = re.compile(raw)
        except re.error as exc:
            found.append(f'[[retired]] pattern {raw!r} does not compile: {exc}')
            continue
        reason = str(rule.get('reason', 'no reason given'))
        for root in rule.get('roots', []):
            base = Path(str(root))
            if not base.exists():
                found.append(f'{base.as_posix()}: [[retired]] root does not exist.')
                continue
            for file in sorted(base.rglob('*')):
                if not file.is_file() or file.suffix.lower() not in _TEXT_SUFFIXES:
                    continue
                if any(part in _SKIP_DIRS for part in file.parts):
                    continue
                if is_excluded(file, excludes) is not None:
                    excluded += 1
                    continue
                try:
                    text = file.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    continue
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if pattern.search(line):
                        found.append(
                            f'{file.as_posix()}:{lineno}: retired {raw!r} is still here -- {reason}'
                        )
    return found, excluded


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Walk the registered model-data mirror sites')
    ap.add_argument(
        '--bindings', default=None, help='registry file (default: the resolution chain)'
    )
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    bindings = resolve_bindings(args.bindings)
    if not bindings.exists():
        print(
            f'mirror walk SKIPPED: no bindings file at {bindings}. '
            'An absent registry is the correct state for a fresh environment -- but no '
            'site was checked, so this run proves nothing about the mirrors. '
            f'Set ${BINDINGS_ENV} or create the file to enable the walk.'
        )
        return 0
    try:
        registry = tomllib.loads(bindings.read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f'mirror walk CANNOT ANSWER: {bindings} could not be read ({exc}).')
        return 2

    canonical = registry.get('canonical')
    reviewed = canonical_last_reviewed(Path(str(canonical))) if canonical else None
    sites = registry.get('site', [])
    retired = registry.get('retired', [])
    excludes = registry.get('exclude', [])

    findings: list[str] = []
    for site in sites:
        findings.extend(check_site(site, reviewed))
    retired_findings, excluded = walk_retired(retired, excludes)
    findings.extend(retired_findings)

    for line in findings:
        print(f'mirror-check: {line}')
    print(
        f'mirror walk: {len(sites)} site(s) walked, {len(retired)} retired pattern(s) searched, '
        f'{excluded} file(s) excluded by glob, {len(findings)} finding(s). '
        f'Canonical last_reviewed: {reviewed or "unreadable"}.'
    )
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())

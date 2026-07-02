#!/usr/bin/env python3
"""Audit an existing Python project against the python-engineering standard.

Read-only: reports pass/fail per check, never modifies the project.

Usage:
    python doctor.py [path]     # default: current directory

Exit code 1 if any check fails. Requires: Python 3.11+ (stdlib only: tomllib).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomllib


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def _parse_toml(text: str) -> dict:
    """Parse pyproject text into a dict; malformed/empty -> {}.

    Parsing (vs. a raw substring scan) is the point: tomllib ignores comments, so
    a project that only *mentions* pip-audit / quote-style / [dependency-groups]
    in a comment cannot score points for tools it does not actually configure."""
    try:
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return {}


def _flatten_strings(obj: object) -> list[str]:
    """All string leaves in a nested dict/list — for scanning dependency tables."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _flatten_strings(v)]
    if isinstance(obj, (list, tuple)):
        return [s for v in obj for s in _flatten_strings(v)]
    return []


def _ci_files(d: Path) -> list[Path]:
    """CI config files present in the project: GitHub Actions, GitLab, CircleCI."""
    files = list(d.glob('.github/workflows/*.yml')) + list(d.glob('.github/workflows/*.yaml'))
    files += [p for p in (d / '.gitlab-ci.yml', d / '.circleci' / 'config.yml') if p.is_file()]
    return files


def audit(project_dir: Path) -> list[tuple[str, bool, str]]:
    """Return [(check_id, ok, detail)] for project_dir. Pure read-only."""
    d = Path(project_dir)
    pyproject_text = _read(d / 'pyproject.toml')
    pyproject = _parse_toml(pyproject_text)
    tool = pyproject.get('tool', {}) if isinstance(pyproject.get('tool'), dict) else {}
    checks: list[tuple[str, bool, str]] = []

    # src layout: a src/ dir containing at least one package directory.
    src = d / 'src'
    has_src = src.is_dir() and any(c.is_dir() for c in src.iterdir())
    checks.append(
        (
            'src-layout',
            has_src,
            'src/<package>/ present' if has_src else 'no src/ layout (flat layout?)',
        )
    )

    # Tests live in a top-level tests/ tree, never inside src/ (colocated tests
    # ship inside the built wheel and pollute the installed package).
    src_tests = sorted(p.name for p in src.rglob('test_*.py')) if src.is_dir() else []
    checks.append(
        (
            'tests-not-in-src',
            not src_tests,
            'no tests under src/'
            if not src_tests
            else f'{len(src_tests)} test module(s) under src/ - move to tests/ (e.g. {src_tests[0]})',
        )
    )

    # uv: uv.lock, the uv_build build backend, or a [tool.uv] table.
    build_system = pyproject.get('build-system', {})
    build_system = build_system if isinstance(build_system, dict) else {}
    build_strings = _flatten_strings(build_system)
    uses_uv = (
        (d / 'uv.lock').is_file() or any('uv_build' in s for s in build_strings) or 'uv' in tool
    )
    checks.append(
        ('uv', uses_uv, 'uv detected' if uses_uv else 'no uv.lock / uv_build / [tool.uv]')
    )

    # ruff single-quote formatting configured (parsed, so a commented example
    # quote-style does not count).
    ruff_fmt = tool.get('ruff', {}).get('format', {}) if isinstance(tool.get('ruff'), dict) else {}
    ruff_sq = isinstance(ruff_fmt, dict) and ruff_fmt.get('quote-style') == 'single'
    checks.append(
        (
            'ruff-single-quote',
            ruff_sq,
            'ruff single-quote configured'
            if ruff_sq
            else 'missing [tool.ruff.format] quote-style = "single"',
        )
    )

    # dev deps via PEP 735 dependency-groups (a real table, not a comment).
    has_groups = isinstance(pyproject.get('dependency-groups'), dict)
    checks.append(
        (
            'dependency-groups',
            has_groups,
            '[dependency-groups] used'
            if has_groups
            else 'dev deps should use [dependency-groups] (PEP 735)',
        )
    )

    # pip-audit wired in deps or a CI workflow (GitHub Actions, GitLab, or CircleCI).
    # pyproject side is scanned over parsed dependency string leaves (project deps,
    # optional-deps, dependency-groups, tool tables) so a commented mention does not
    # count; CI files are still scanned as raw text.
    pyproject_deps = (
        _flatten_strings(pyproject.get('project', {}))
        + _flatten_strings(pyproject.get('dependency-groups', {}))
        + _flatten_strings(tool)
    )
    ci = ' '.join(_read(p) for p in _ci_files(d))
    has_audit = any('pip-audit' in s for s in pyproject_deps) or 'pip-audit' in ci
    checks.append(
        ('pip-audit', has_audit, 'pip-audit present' if has_audit else 'no pip-audit in deps or CI')
    )

    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Audit a project against the python-engineering standard.'
    )
    parser.add_argument('path', nargs='?', default='.', help='project directory (default: .)')
    args = parser.parse_args(argv)

    results = audit(Path(args.path))
    print(f'\n  python-engineering doctor - {Path(args.path).resolve().name}')
    print(f'  {"-" * 56}')
    failed = 0
    for check_id, ok, detail in results:
        if not ok:
            failed += 1
        print(f'  [{"PASS" if ok else "FAIL"}] {check_id:<20} {detail}')
    print(f'  {"-" * 56}')
    print(f'  {len(results) - failed}/{len(results)} checks passed\n')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

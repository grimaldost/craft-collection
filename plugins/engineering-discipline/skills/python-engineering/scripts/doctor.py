#!/usr/bin/env python3
"""Audit an existing Python project against the python-engineering standard.

Read-only: reports pass/fail per check, never modifies the project.

Usage:
    python doctor.py [path]     # default: current directory

Exit code 1 if any check fails. Requires: Python 3.10+ (stdlib only).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def audit(project_dir: Path) -> list[tuple[str, bool, str]]:
    """Return [(check_id, ok, detail)] for project_dir. Pure read-only."""
    d = Path(project_dir)
    pyproject = _read(d / 'pyproject.toml')
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

    # uv: uv.lock, the uv_build backend, or a [tool.uv] table.
    uses_uv = (d / 'uv.lock').is_file() or 'uv_build' in pyproject or '[tool.uv]' in pyproject
    checks.append(
        ('uv', uses_uv, 'uv detected' if uses_uv else 'no uv.lock / uv_build / [tool.uv]')
    )

    # ruff single-quote formatting configured.
    ruff_sq = 'quote-style = "single"' in pyproject or "quote-style = 'single'" in pyproject
    checks.append(
        (
            'ruff-single-quote',
            ruff_sq,
            'ruff single-quote configured'
            if ruff_sq
            else 'missing [tool.ruff.format] quote-style = "single"',
        )
    )

    # dev deps via PEP 735 dependency-groups.
    has_groups = '[dependency-groups]' in pyproject
    checks.append(
        (
            'dependency-groups',
            has_groups,
            '[dependency-groups] used'
            if has_groups
            else 'dev deps should use [dependency-groups] (PEP 735)',
        )
    )

    # pip-audit wired in deps or a CI workflow.
    ci_files = list(d.glob('.github/workflows/*.yml')) + list(d.glob('.github/workflows/*.yaml'))
    ci = ' '.join(_read(p) for p in ci_files)
    has_audit = 'pip-audit' in pyproject or 'pip-audit' in ci
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

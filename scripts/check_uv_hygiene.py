#!/usr/bin/env python3
"""Commit-time uv hygiene: the pre-commit floor of uv_enforce (ADR-0003).

Inside a uv-managed project (uv.lock, or [tool.uv]/uv_build in pyproject.toml —
the same detection as the act-time hook's `cwd_is_uv_project` core), fail when
pip/poetry/virtualenv residue is present: a root `requirements*.txt` alongside
`uv.lock`, a `Pipfile`, or a tracked `venv//.venv` directory. Outside a uv
project it never fires. This is the commit-time tier of the enforcement
ladder — it catches after the fact what the Claude Code PreToolUse hook blocks
at act time. Exposed to consumer repos via this repo's `.pre-commit-hooks.yaml`
(hook id `check-uv-hygiene`). Stdlib-only; exit 1 on findings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_uv_project(root: Path) -> bool:
    if (root / 'uv.lock').is_file():
        return True
    pyproject = root / 'pyproject.toml'
    if pyproject.is_file():
        text = pyproject.read_text(encoding='utf-8', errors='ignore')
        return '[tool.uv]' in text or 'uv_build' in text
    return False


def _git_env() -> dict[str, str]:
    """The environment minus every GIT_* variable, so `-C` is authoritative.

    Git exports the repository-location variables (GIT_DIR, GIT_WORK_TREE,
    GIT_INDEX_FILE, ...) into every hook it runs, and an ambient GIT_DIR takes
    PRECEDENCE over `git -C <dir>`. This check IS a pre-commit hook, and it takes
    the tree to check as an argument, so the two can differ: unscrubbed it asks the
    HOOK's repository whether some OTHER tree has a venv committed -- an answer of
    "no" that means nothing, and the residue ships. It hides when the two coincide,
    which is how it survived. Found the hard way: the suite was green run directly
    and red inside `git push`."""
    return {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}


def _tracked_venvs(root: Path) -> list[str]:
    """Names of venv dirs committed to git; falls back to directory presence
    (a `pyvenv.cfg` marker) when git is unavailable — absence of git is not
    absence of residue."""
    names = ('venv', '.venv')
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv
            ['git', '-C', str(root), 'ls-files', '--', *names],  # noqa: S607 - PATH git
            capture_output=True,
            text=True,
            timeout=10,
            env=_git_env(),
        )
        if proc.returncode == 0:
            return sorted({ln.split('/', 1)[0] for ln in proc.stdout.splitlines() if ln.strip()})
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    return [n for n in names if (root / n / 'pyvenv.cfg').is_file()]


def check_tree(root: Path) -> list[str]:
    """Residue findings for `root` ([] when clean or not a uv project)."""
    if not is_uv_project(root):
        return []
    errors: list[str] = []
    if (root / 'uv.lock').is_file():
        for req in sorted(root.glob('requirements*.txt')):
            errors.append(
                f'{req.name}: pip requirements alongside uv.lock — '
                'declare dependencies with `uv add` (pyproject + uv.lock)'
            )
    if (root / 'Pipfile').is_file():
        errors.append('Pipfile: pipenv residue in a uv project — remove it; uv owns the env')
    for name in _tracked_venvs(root):
        errors.append(f'{name}/: virtualenv checked in — remove and use `uv venv` locally')
    return errors


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]).resolve() if argv else Path.cwd()
    errors = check_tree(root)
    for e in errors:
        print(f'uv-hygiene: {e}', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())

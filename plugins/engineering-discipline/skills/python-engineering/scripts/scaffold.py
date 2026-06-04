#!/usr/bin/env python3
"""Scaffold a new Python project to the python-engineering standard.

The pure core (`resolve_names`, `render_pyproject`) is unit-tested; the
side-effecting `main()` runs `uv init`, overwrites pyproject with the canonical
template, and drops a pre-commit config.

Usage:
    python scaffold.py my-cool-tool [--path .]

Requires: Python 3.10+; uv on PATH for the scaffolding step.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def resolve_names(project: str) -> dict[str, str]:
    """Resolve PyPI (kebab), package (snake), and class (Pascal) names."""
    base = re.sub(r'[^0-9a-zA-Z]+', '-', project).strip('-').lower()
    return {
        'pypi': base,
        'package': base.replace('-', '_'),
        'class': ''.join(part.capitalize() for part in base.split('-')),
    }


def name_error(names: dict[str, str]) -> str | None:
    """Return an error message if the resolved names are unusable, else None.

    A digit-leading project ('3d-tool' -> package '3d_tool') or an empty name does
    not yield a valid Python identifier, so the scaffolded package would be
    unimportable — catch it before `uv init` rather than emit a broken project."""
    if not names['package'].isidentifier():
        return (f"resolves to package {names['package']!r}, which is not a valid "
                'Python identifier (it likely starts with a digit or is empty) — '
                'choose a name whose first character is a letter')
    return None


PYPROJECT_TEMPLATE = '''\
[project]
name = "{pypi}"
version = "0.1.0"
description = "TODO: one-line description"
requires-python = ">=3.12"
dependencies = []

[build-system]
requires = ["uv_build"]
build-backend = "uv_build"

[dependency-groups]
dev = [
    {{ include-group = "lint" }},
    {{ include-group = "test" }},
    {{ include-group = "security" }},
    "pre-commit",
]
lint = ["ruff>=0.15", "ty"]
test = ["pytest>=8.0", "pytest-cov", "pytest-asyncio>=0.24", "hypothesis"]
security = ["pip-audit"]

[tool.ruff]
line-length = 100

[tool.ruff.format]
quote-style = "single"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "S", "TC"]

[tool.ruff.lint.flake8-quotes]
inline-quotes = "single"
docstring-quotes = "double"
multiline-quotes = "double"

[tool.ruff.lint.isort]
known-first-party = ["{package}"]

[tool.pytest.ini_options]
testpaths = ["tests"]
'''

PRECOMMIT = '''\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.7
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
'''


def render_pyproject(project: str) -> str:
    """Render a canonical pyproject.toml for `project`. Pure; no I/O."""
    return PYPROJECT_TEMPLATE.format(**resolve_names(project))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Scaffold a Python project to the python-engineering standard.')
    parser.add_argument('project', help='project name (kebab-case)')
    parser.add_argument('--path', default='.', help='parent directory (default: .)')
    args = parser.parse_args(argv)

    names = resolve_names(args.project)
    err = name_error(names)
    if err:
        print(f'error: {args.project!r} {err}', file=sys.stderr)
        return 1
    parent = Path(args.path)
    target = parent / names['pypi']
    if target.exists():
        print(f'error: {target} already exists', file=sys.stderr)
        return 1

    # 1. uv init --lib gives the src layout + uv_build backend from the start.
    try:
        subprocess.run(['uv', 'init', '--lib', names['pypi']], cwd=parent, check=True)  # noqa: S603,S607
    except FileNotFoundError:
        print('error: uv not found on PATH. Install uv (https://docs.astral.sh/uv/).',
              file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f'error: uv init failed ({e.returncode})', file=sys.stderr)
        return 1

    # 2. Overwrite pyproject with the canonical template; 3. add pre-commit config.
    (target / 'pyproject.toml').write_text(render_pyproject(args.project), encoding='utf-8')
    (target / '.pre-commit-config.yaml').write_text(PRECOMMIT, encoding='utf-8')

    print(f'\nScaffolded {names["pypi"]} at {target}')
    print(f'Next: cd {names["pypi"]} && uv sync && uv run pre-commit install')
    return 0


if __name__ == '__main__':
    sys.exit(main())

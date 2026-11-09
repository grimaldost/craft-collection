#!/usr/bin/env python3
"""Checks of the package's manifest, runtime imports and decision record.

Contract under test:
- `pyproject.toml` declares the name, Python floor, empty dependency list,
  `kit` script and `uv_build` backend;
- every module under `harness_kit/` imports only the standard library and the
  package itself;
- ADR-0009 holds the sections Context, Decision, Alternatives and Consequences
  and names ADR-0003.

Stdlib-runnable: `python test_package_contract.py`.
"""

from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

import tomllib

KIT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = KIT_ROOT / 'src' / 'harness_kit'
ADR = KIT_ROOT.parent / 'docs' / 'adr' / '0009-harness-kit-outside-the-harness.md'


def _foreign_imports(package: Path) -> tuple[list[str], list[str]]:
    """Return the modules walked and each import outside stdlib and package."""
    allowed = set(sys.stdlib_module_names) | {'harness_kit'}
    walked: list[str] = []
    foreign: list[str] = []
    for path in sorted(package.rglob('*.py')):
        name = path.relative_to(package).as_posix()
        walked.append(name)
        roots: list[str] = []
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                roots.extend(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots.append((node.module or '').split('.')[0])
        foreign.extend(f'{name}: {root}' for root in roots if root not in allowed)
    return walked, foreign


def _write(base: Path, rel: str, text: str) -> None:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_pyproject_declares_the_contract_fields():
    manifest = tomllib.loads((KIT_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    project = manifest['project']
    assert project['name'] == 'harness-kit', project['name']
    assert project['requires-python'] == '>=3.11', project['requires-python']
    assert project['dependencies'] == [], project['dependencies']
    assert project['scripts'] == {'kit': 'harness_kit.cli:main'}, project['scripts']
    assert manifest['build-system']['build-backend'] == 'uv_build', manifest['build-system']


def test_import_walk_flags_a_third_party_import_at_any_depth():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write(base, 'top.py', 'import yaml\n')
        _write(base, 'sub/dotted.py', 'from requests.adapters import HTTPAdapter\n')
        _write(base, 'nested.py', 'def f():\n    import numpy.linalg\n')
        _, foreign = _foreign_imports(base)
    assert foreign == ['nested.py: numpy', 'sub/dotted.py: requests', 'top.py: yaml'], foreign


def test_import_walk_accepts_stdlib_and_package_imports():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _write(
            base,
            'ok.py',
            'from __future__ import annotations\n'
            'import json, os.path\n'
            'from harness_kit.cli import main\n'
            'from . import sibling\n'
            'from .sibling import thing\n',
        )
        walked, foreign = _foreign_imports(base)
    assert walked == ['ok.py'], walked
    assert foreign == [], foreign


def test_package_imports_only_stdlib_and_itself():
    walked, foreign = _foreign_imports(PACKAGE)
    assert {'__init__.py', '__main__.py', 'cli.py'} <= set(walked), walked
    assert foreign == [], foreign


def test_adr_holds_the_four_sections():
    headings = re.findall(r'^## +(.+?) *$', ADR.read_text(encoding='utf-8'), re.MULTILINE)
    for section in ('Context', 'Decision', 'Alternatives', 'Consequences'):
        assert any(h.startswith(section) for h in headings), (section, headings)


def test_adr_names_adr_0003():
    assert 'ADR-0003' in ADR.read_text(encoding='utf-8')


def _adr_section(name):
    text = ADR.read_text(encoding='utf-8')
    match = re.search(r'^## +' + name + r'.*?$(.*?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
    assert match, name
    return ' '.join(match.group(1).split())


def test_adr_states_the_launcher_rule_as_the_judges_and_names_the_bare_start_loss():
    consequences = _adr_section('Consequences')
    assert '`launcher.required`' in consequences
    assert 'no plugin' in consequences
    assert 'starts only through' not in consequences


if __name__ == '__main__':
    test_pyproject_declares_the_contract_fields()
    test_import_walk_flags_a_third_party_import_at_any_depth()
    test_import_walk_accepts_stdlib_and_package_imports()
    test_package_imports_only_stdlib_and_itself()
    test_adr_holds_the_four_sections()
    test_adr_names_adr_0003()
    test_adr_states_the_launcher_rule_as_the_judges_and_names_the_bare_start_loss()
    print('ok: package contract')

"""Tests for doctor.audit.

Runnable with pytest OR directly: `python test_doctor.py`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from doctor import _ci_files, audit


def _make_project(root: Path, pyproject: str) -> None:
    (root / 'src' / 'mypkg').mkdir(parents=True)
    (root / 'src' / 'mypkg' / '__init__.py').write_text('', encoding='utf-8')
    (root / 'pyproject.toml').write_text(pyproject, encoding='utf-8')


def test_flags_missing_ruff_single_quote_but_passes_src_layout():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # uv + groups present, but NO ruff single-quote config.
        _make_project(
            root, '[build-system]\nrequires = ["uv_build"]\n\n[dependency-groups]\ndev = []\n'
        )
        results = {cid: ok for cid, ok, _ in audit(root)}
        assert results['src-layout'] is True
        assert results['uv'] is True
        assert results['dependency-groups'] is True
        assert results['ruff-single-quote'] is False


def test_passes_full_standard_project():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_project(
            root,
            '[build-system]\nrequires = ["uv_build"]\n\n'
            '[dependency-groups]\ndev = ["pip-audit"]\n\n'
            '[tool.ruff.format]\nquote-style = "single"\n',
        )
        results = {cid: ok for cid, ok, _ in audit(root)}
        assert all(results.values()), results


def test_flags_tests_under_src():
    # A test module colocated under src/ must fail tests-not-in-src.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_project(root, '[build-system]\nrequires = ["uv_build"]\n')
        (root / 'src' / 'mypkg' / 'test_thing.py').write_text('', encoding='utf-8')
        results = {cid: ok for cid, ok, _ in audit(root)}
        assert results['tests-not-in-src'] is False


def test_detects_github_actions_ci():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '.github' / 'workflows').mkdir(parents=True)
        (root / '.github' / 'workflows' / 'ci.yml').write_text('jobs: {}\n', encoding='utf-8')
        assert _ci_files(root), 'GitHub Actions workflow should be recognized as CI'


def test_detects_gitlab_ci_only():
    # A project whose ONLY CI config is .gitlab-ci.yml must be reported as having CI.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '.gitlab-ci.yml').write_text('stages: [test]\n', encoding='utf-8')
        assert _ci_files(root), 'GitLab CI (.gitlab-ci.yml) should be recognized as CI'


def test_detects_circleci_only():
    # A project whose ONLY CI config is .circleci/config.yml must be reported as having CI.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '.circleci').mkdir()
        (root / '.circleci' / 'config.yml').write_text('version: 2.1\n', encoding='utf-8')
        assert _ci_files(root), 'CircleCI (.circleci/config.yml) should be recognized as CI'


def test_no_ci_when_no_config():
    with tempfile.TemporaryDirectory() as d:
        assert not _ci_files(Path(d)), 'a project with no CI config should report no CI'


def test_pip_audit_found_in_gitlab_ci():
    # pip-audit declared only in a GitLab CI file should satisfy the pip-audit check.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_project(root, '[build-system]\nrequires = ["uv_build"]\n')
        (root / '.gitlab-ci.yml').write_text(
            'test:\n  script:\n    - pip-audit\n', encoding='utf-8'
        )
        results = {cid: ok for cid, ok, _ in audit(root)}
        assert results['pip-audit'] is True


if __name__ == '__main__':
    test_flags_missing_ruff_single_quote_but_passes_src_layout()
    test_passes_full_standard_project()
    test_flags_tests_under_src()
    test_detects_github_actions_ci()
    test_detects_gitlab_ci_only()
    test_detects_circleci_only()
    test_no_ci_when_no_config()
    test_pip_audit_found_in_gitlab_ci()
    print('ok: all doctor tests passed')

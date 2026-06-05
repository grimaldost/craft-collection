"""Tests for doctor.audit.

Runnable with pytest OR directly: `python test_doctor.py`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from doctor import audit


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


if __name__ == '__main__':
    test_flags_missing_ruff_single_quote_but_passes_src_layout()
    test_passes_full_standard_project()
    print('ok: all doctor tests passed')

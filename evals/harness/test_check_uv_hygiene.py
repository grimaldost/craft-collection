#!/usr/bin/env python3
"""Self-contained checks for scripts/check_uv_hygiene.py (no pytest required)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import check_uv_hygiene  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # Not a uv project: never fires, even with residue present.
        (root / 'requirements.txt').write_text('requests\n', encoding='utf-8')
        (root / 'Pipfile').write_text('', encoding='utf-8')
        assert check_uv_hygiene.check_tree(root) == [], 'must not fire outside a uv project'

        # uv project (uv.lock): requirements + Pipfile are residue.
        (root / 'uv.lock').write_text('', encoding='utf-8')
        errors = check_uv_hygiene.check_tree(root)
        assert any('requirements.txt' in e for e in errors), 'requirements.txt not flagged'
        assert any('Pipfile' in e for e in errors), 'Pipfile not flagged'

        # Clean uv project: no findings.
        (root / 'requirements.txt').unlink()
        (root / 'Pipfile').unlink()
        assert check_uv_hygiene.check_tree(root) == [], 'clean uv tree flagged'

        # A venv with pyvenv.cfg is flagged (no git in the fixture -> presence check).
        (root / '.venv').mkdir()
        (root / '.venv' / 'pyvenv.cfg').write_text('home = /usr\n', encoding='utf-8')
        errors = check_uv_hygiene.check_tree(root)
        assert any('.venv/' in e for e in errors), 'checked-in venv not flagged'

        # pyproject-based uv detection ([tool.uv]) works without uv.lock.
        other = root / 'sub'
        other.mkdir()
        (other / 'pyproject.toml').write_text('[tool.uv]\n', encoding='utf-8')
        (other / 'Pipfile').write_text('', encoding='utf-8')
        assert any('Pipfile' in e for e in check_uv_hygiene.check_tree(other)), (
            'pyproject-marked uv project not detected'
        )

        # main() exit codes: 1 on dirty, 0 on clean.
        assert check_uv_hygiene.main([str(other)]) == 1
        (other / 'Pipfile').unlink()
        assert check_uv_hygiene.main([str(other)]) == 0

    print('ok: check_uv_hygiene fixture trees (clean, dirty, non-uv, venv, pyproject)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

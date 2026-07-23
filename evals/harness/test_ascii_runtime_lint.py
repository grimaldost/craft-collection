#!/usr/bin/env python3
"""Self-contained checks for scripts/ascii_runtime_lint.py (no pytest required)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import ascii_runtime_lint as lint  # noqa: E402 - sys.path set up first


def _tree(base: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
    return base


def _run_main(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = lint.main(argv)
    return rc, out.getvalue()


def test_runtime_literal_flagged_docstring_exempt():
    with tempfile.TemporaryDirectory() as td:
        base = _tree(
            Path(td),
            {
                'scripts/tool.py': (
                    '"""Docstring with an em dash — exempt."""\nprint(\'runtime — dash\')\n'
                )
            },
        )
        current = lint.scan(base)
    assert list(current) == ['scripts/tool.py'], current
    assert len(current['scripts/tool.py']) == 1
    assert 'U+2014' in current['scripts/tool.py'][0]


def test_fstring_chunk_flagged():
    with tempfile.TemporaryDirectory() as td:
        base = _tree(Path(td), {'plugins/p/hooks/h.py': "x = 1\nprint(f'total §{x}')\n"})
        current = lint.scan(base)
    assert len(current.get('plugins/p/hooks/h.py', [])) == 1, current


def test_suppression_and_exclusions():
    with tempfile.TemporaryDirectory() as td:
        base = _tree(
            Path(td),
            {
                'scripts/writer.py': "CONTENT = 'file — content'  # ascii-ok\n",
                'scripts/test_thing.py': "print('test data → fine')\n",
                'scripts/binary.py': "B = b'\\xff\\xfe'\n",
                'docs/ignored.py': "print('outside scan dirs —')\n",
            },
        )
        current = lint.scan(base)
    assert current == {}, current


def test_ratchet_semantics():
    files = {'scripts/old.py': "print('a — b')\nprint('c — d')\n"}
    with tempfile.TemporaryDirectory() as td:
        base = _tree(Path(td), files)
        current = lint.scan(base)
        assert lint.check(current, {'scripts/old.py': 2}) == [], 'at baseline must pass'
        errs = lint.check(current, {'scripts/old.py': 1})
        assert errs and 'baseline 1' in errs[0], errs
        assert lint.check(current, {}) != [], 'new file starts at zero'


def test_write_baseline_then_pass():
    with tempfile.TemporaryDirectory() as td:
        base = _tree(Path(td), {'scripts/old.py': "print('a — b')\n"})
        rc, out = _run_main(['--root', str(base), '--write-baseline'])
        assert rc == 0, out
        data = json.loads((base / 'scripts' / lint.BASELINE_NAME).read_text(encoding='utf-8'))
        assert data == {'scripts/old.py': 1}, data
        rc2, out2 = _run_main(['--root', str(base)])
        assert rc2 == 0, out2
        (base / 'scripts' / 'new.py').write_text("print('x — y')\n", encoding='utf-8')
        rc3, out3 = _run_main(['--root', str(base)])
        assert rc3 == 1 and 'new.py' in out3, out3


def test_real_repo_is_at_or_under_baseline():
    # The actual gate the pre-commit hook runs: the tracked tree must not have
    # grown past scripts/ascii_lint_baseline.json.
    rc, out = _run_main(['--root', str(ROOT)])
    assert rc == 0, out


def main() -> int:
    test_runtime_literal_flagged_docstring_exempt()
    test_fstring_chunk_flagged()
    test_suppression_and_exclusions()
    test_ratchet_semantics()
    test_write_baseline_then_pass()
    test_real_repo_is_at_or_under_baseline()
    print('ok: ascii_runtime_lint')
    return 0


if __name__ == '__main__':
    sys.exit(main())

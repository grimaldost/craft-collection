"""Tests for scan_toolkit.

Runnable with pytest OR directly: `python test_scan_toolkit.py` (no pytest
dependency required, so the script ships self-verifiable).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scan_toolkit import scan


def _make_tree(root: Path) -> None:
    (root / '.claude/skills/foo').mkdir(parents=True)
    (root / '.claude/skills/foo/SKILL.md').write_text(
        '---\nname: foo\ndescription: Does the foo thing for tests.\n---\nbody\n',
        encoding='utf-8')
    (root / '.claude/commands').mkdir(parents=True)
    (root / '.claude/commands/bar.md').write_text('# bar\n', encoding='utf-8')
    (root / '.claude/agents').mkdir(parents=True)
    (root / '.claude/agents/baz.md').write_text('---\nname: baz\n---\n', encoding='utf-8')
    (root / '.claude/hooks').mkdir(parents=True)
    (root / '.claude/hooks/hook.py').write_text('# hook\n', encoding='utf-8')


def test_scan_enumerates_components():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_tree(root)
        out = scan([root])
        assert 'foo' in {s['name'] for s in out['skills']}
        assert any('foo thing' in s['description'] for s in out['skills'])
        assert 'bar' in {c['name'] for c in out['commands']}
        assert 'baz' in {a['name'] for a in out['agents']}
        assert 'hook.py' in {h['name'] for h in out['hooks']}


def test_missing_dirs_do_not_raise():
    with tempfile.TemporaryDirectory() as d:
        out = scan([Path(d)])  # no .claude at all
        assert out == {'skills': [], 'commands': [], 'agents': [], 'hooks': []}


if __name__ == '__main__':
    test_scan_enumerates_components()
    test_missing_dirs_do_not_raise()
    print('ok: all scan_toolkit tests passed')

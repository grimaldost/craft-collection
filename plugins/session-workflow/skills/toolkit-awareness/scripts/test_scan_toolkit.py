"""Tests for scan_toolkit.

Runnable with pytest OR directly: `python test_scan_toolkit.py` (no pytest
dependency required, so the script ships self-verifiable).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scan_toolkit import (
    _enumerate_plugin_components,
    _plugins_from_json,
    _read_frontmatter,
    scan,
)


def _make_tree(root: Path) -> None:
    (root / '.claude/skills/foo').mkdir(parents=True)
    (root / '.claude/skills/foo/SKILL.md').write_text(
        '---\nname: foo\ndescription: Does the foo thing for tests.\n---\nbody\n',
        encoding='utf-8',
    )
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


def test_frontmatter_quotes_stripped():
    # A YAML-quoted name/description must not render with literal quotes in the
    # inventory. A matched surrounding pair is stripped and \" unescaped; the
    # single-quoted style unescapes '' to '.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        sk = root / '.claude/skills/q'
        sk.mkdir(parents=True)
        (sk / 'SKILL.md').write_text(
            '---\nname: "q"\ndescription: "Says \\"hi\\" politely."\n---\nbody\n',
            encoding='utf-8',
        )
        sk2 = root / '.claude/skills/r'
        sk2.mkdir(parents=True)
        (sk2 / 'SKILL.md').write_text(
            "---\nname: 'r'\ndescription: 'It''s quoted.'\n---\nbody\n",
            encoding='utf-8',
        )
        out = scan([root])
    skills = {s['name']: s for s in out['skills'] if 'plugin' not in s}
    assert 'q' in skills and 'r' in skills, sorted(skills)
    assert skills['q']['description'] == 'Says "hi" politely.'
    assert skills['r']['description'] == "It's quoted."


def test_missing_dirs_do_not_raise():
    with tempfile.TemporaryDirectory() as d:
        out = scan([Path(d)])  # no .claude at all
        # The .claude-dir scan contributes nothing (those items are untagged); any items
        # present come from installed plugins (tagged with a `plugin` key), which are
        # CLI-sourced and environment-dependent, so we don't assert on their count.
        for kind in ('skills', 'commands', 'agents', 'hooks'):
            assert [it for it in out[kind] if 'plugin' not in it] == []
        assert 'plugins' in out  # CLI-sourced, environment-dependent — just present


def test_plugins_from_json_uses_id_and_hides_enabled():
    # `claude plugin list --json` returns id-keyed objects with no name; derive the
    # name from id and never leak the raw `enabled` bool into the label.
    rows = _plugins_from_json(
        [
            {
                'id': 'engineering-discipline@craft-collection',
                'version': '0.1.0',
                'enabled': True,
            },
            {
                'id': 'example-tool@example-marketplace',
                'version': '0.3.0',
                'enabled': False,
            },
        ]
    )
    assert rows[0]['name'] == 'engineering-discipline (0.1.0)'  # not '? (0.1.0, True)'
    assert rows[1]['name'] == 'example-tool (0.3.0, disabled)'
    assert all('?' not in r['name'] and 'True' not in r['name'] for r in rows)


def _make_plugin(install_path: Path) -> None:
    """A fake installed plugin's on-disk layout under its installPath: a skill, a
    command, an agent, and a hooks.json — the components `claude plugin list` points
    at via installPath but never enumerates itself."""
    (install_path / 'skills/foo').mkdir(parents=True)
    (install_path / 'skills/foo/SKILL.md').write_text(
        '---\nname: foo\ndescription: The plugin foo skill.\n---\nbody\n',
        encoding='utf-8',
    )
    (install_path / 'commands').mkdir(parents=True)
    (install_path / 'commands/pcmd.md').write_text('# pcmd\n', encoding='utf-8')
    (install_path / 'agents').mkdir(parents=True)
    (install_path / 'agents/pagent.md').write_text('---\nname: pagent\n---\n', encoding='utf-8')
    (install_path / 'hooks').mkdir(parents=True)
    (install_path / 'hooks/hooks.json').write_text(
        '{"hooks": {"SessionStart": [{"hooks": [{"type": "command"}]}]}}',
        encoding='utf-8',
    )


def test_enumerate_plugin_components_walks_install_path():
    # The core regression: a plugin's installPath must be walked so its skills,
    # commands, agents, and hooks are surfaced (not the blind SKILLS(2)/HOOKS(0)).
    with tempfile.TemporaryDirectory() as d:
        ip = Path(d) / 'plug'
        _make_plugin(ip)
        comps = _enumerate_plugin_components('myplugin', str(ip))
        assert 'foo' in {s['name'] for s in comps['skills']}
        assert all(s['plugin'] == 'myplugin' for s in comps['skills'])
        assert 'pcmd' in {c['name'] for c in comps['commands']}
        assert 'pagent' in {a['name'] for a in comps['agents']}
        # hooks.json events are enumerated (SessionStart), not left at 0
        assert any('SessionStart' in h['name'] for h in comps['hooks'])
        assert all(h['plugin'] == 'myplugin' for h in comps['hooks'])


def test_enumerate_plugin_components_missing_path_is_empty():
    # An installPath that does not resolve yields empty lists, never raises.
    comps = _enumerate_plugin_components('gone', str(Path('does') / 'not' / 'exist'))
    assert comps == {'skills': [], 'commands': [], 'agents': [], 'hooks': []}
    assert _enumerate_plugin_components('none', None) == {
        'skills': [],
        'commands': [],
        'agents': [],
        'hooks': [],
    }


def test_read_frontmatter_handles_folded_scalar():
    # A `description: >` folded block must be captured in full, not truncated to ">".
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'SKILL.md'
        p.write_text(
            '---\nname: folded\ndescription: >\n  First line of the\n'
            '  folded description.\nuser-invocable: true\n---\nbody\n',
            encoding='utf-8',
        )
        fm = _read_frontmatter(p)
        assert fm['name'] == 'folded'
        assert fm['description'] == 'First line of the folded description.'
        assert fm['user-invocable'] == 'true'


if __name__ == '__main__':
    test_scan_enumerates_components()
    test_frontmatter_quotes_stripped()
    test_missing_dirs_do_not_raise()
    test_plugins_from_json_uses_id_and_hides_enabled()
    test_enumerate_plugin_components_walks_install_path()
    test_enumerate_plugin_components_missing_path_is_empty()
    test_read_frontmatter_handles_folded_scalar()
    print('ok: all scan_toolkit tests passed')

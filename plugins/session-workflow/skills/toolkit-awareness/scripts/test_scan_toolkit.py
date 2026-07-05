"""Tests for scan_toolkit.

Runnable with pytest OR directly: `python test_scan_toolkit.py` (no pytest
dependency required, so the script ships self-verifiable).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scan_toolkit import (
    _enumerate_plugin_components,
    _merge_skew,
    _plugins_from_json,
    _read_frontmatter,
    _source_manifest_version,
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


def _make_marketplace(root: Path, plugin: str, version: str) -> Path:
    """A fake marketplace source tree: `.claude-plugin/marketplace.json` declaring
    one plugin whose manifest carries `version` — the shape `claude plugin
    marketplace list` points at via installLocation."""
    import json

    mp = root / 'market'
    (mp / '.claude-plugin').mkdir(parents=True)
    (mp / '.claude-plugin' / 'marketplace.json').write_text(
        json.dumps(
            {'name': 'market', 'plugins': [{'name': plugin, 'source': f'./plugins/{plugin}'}]}
        ),
        encoding='utf-8',
    )
    man = mp / 'plugins' / plugin / '.claude-plugin'
    man.mkdir(parents=True)
    (man / 'plugin.json').write_text(
        json.dumps({'name': plugin, 'version': version}), encoding='utf-8'
    )
    return mp


def test_plugins_from_json_exposes_version_and_marketplace():
    # The skew check needs the raw version and the marketplace half of the id as
    # structured fields, not just baked into the display name.
    rows = _plugins_from_json([{'id': 'plug@market', 'version': '0.1.0', 'enabled': True}])
    assert rows[0]['version'] == '0.1.0'
    assert rows[0]['marketplace'] == 'market'


def test_source_manifest_version_via_marketplace_json():
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'plug', '0.2.0')
        assert _source_manifest_version(mp, 'plug') == '0.2.0'


def test_source_manifest_version_fallback_layout():
    # Without a marketplace.json, the conventional plugins/<name>/ layout still resolves.
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'plug', '0.3.0')
        (mp / '.claude-plugin' / 'marketplace.json').unlink()
        assert _source_manifest_version(mp, 'plug') == '0.3.0'


def test_source_manifest_version_missing_is_none():
    with tempfile.TemporaryDirectory() as d:
        assert _source_manifest_version(Path(d) / 'nope', 'plug') is None


def test_merge_skew_annotates_stale_install():
    # Installed 0.1.0 vs marketplace source 0.2.0: the row gains a structured
    # source_version, a visible name suffix, and the scan a caveat line — the
    # invisible-skew footgun (a stale install once hid an entire skill).
    rows = _plugins_from_json([{'id': 'plug@market', 'version': '0.1.0', 'enabled': True}])
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'plug', '0.2.0')
        caveats = _merge_skew(rows, {'market': str(mp)})
    assert rows[0]['source_version'] == '0.2.0'
    assert 'source 0.2.0' in rows[0]['name']
    assert caveats and 'plug' in caveats[0] and '0.2.0' in caveats[0]


def test_merge_skew_equal_or_unknown_is_silent():
    # A matching version or an unresolvable marketplace produces no annotation and
    # no caveat — absence of evidence is not skew.
    rows = _plugins_from_json(
        [
            {'id': 'same@market', 'version': '0.2.0', 'enabled': True},
            {'id': 'ghost@nowhere', 'version': '0.1.0', 'enabled': True},
        ]
    )
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'same', '0.2.0')
        caveats = _merge_skew(rows, {'market': str(mp)})
    assert caveats == []
    assert all('source_version' not in r for r in rows)
    assert 'source' not in rows[0]['name']


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
    test_plugins_from_json_exposes_version_and_marketplace()
    test_source_manifest_version_via_marketplace_json()
    test_source_manifest_version_fallback_layout()
    test_source_manifest_version_missing_is_none()
    test_merge_skew_annotates_stale_install()
    test_merge_skew_equal_or_unknown_is_silent()
    test_enumerate_plugin_components_walks_install_path()
    test_enumerate_plugin_components_missing_path_is_empty()
    test_read_frontmatter_handles_folded_scalar()
    print('ok: all scan_toolkit tests passed')

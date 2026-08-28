"""Tests for plugin_version. Runnable with pytest or `python test_plugin_version.py`."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from plugin_version import field_line, main, read_registry, resolve_entry, tree_version

REGISTRY = {
    'plugins': {
        'engineering-discipline@craft-collection': [
            {
                'scope': 'user',
                'installPath': '/c/u/.claude/plugins/cache/craft-collection/'
                'engineering-discipline/0.5.0',
                'version': '0.5.0',
            }
        ],
        'session-workflow@craft-collection': [
            {
                'scope': 'user',
                'installPath': '/c/u/.claude/plugins/cache/craft-collection/'
                'session-workflow/0.21.0',
                'version': '0.21.0',
            }
        ],
    }
}


def test_a_plugin_resolves_to_its_installed_version_and_path():
    got = resolve_entry(REGISTRY, 'engineering-discipline')
    assert got['version'] == '0.5.0'
    assert got['install_path'].endswith('engineering-discipline/0.5.0')


def test_an_unknown_plugin_resolves_to_nothing_rather_than_a_plausible_guess():
    # The recorded failure: a report claimed "0.1.3 (installed cache, plugin.json)"
    # for a plugin whose cache had only ever held 0.5.0. A real historical version
    # is exactly the shape that survives a self-check, so not-found must be a hard
    # nothing here, never a nearest match.
    assert resolve_entry(REGISTRY, 'engineering-disciplin') is None
    assert resolve_entry(REGISTRY, 'nope') is None
    assert resolve_entry({'plugins': {}}, 'engineering-discipline') is None


def test_a_marketplace_qualified_name_resolves_the_same_as_a_bare_one():
    bare = resolve_entry(REGISTRY, 'session-workflow')
    qualified = resolve_entry(REGISTRY, 'session-workflow@craft-collection')
    assert bare == qualified


def test_the_field_line_carries_the_path_so_the_number_cannot_be_produced_without_it():
    line = field_line(
        'engineering-discipline', '0.5.0', '/cache/engineering-discipline/0.5.0', None
    )
    assert '0.5.0' in line
    assert '/cache/engineering-discipline/0.5.0' in line
    # the version's own evidence travels with it into the report
    assert line.count('0.5.0') >= 2


def test_a_working_tree_that_disagrees_forces_the_disclosure_into_the_pasted_line():
    line = field_line('humblepowers', '0.12.0', '/cache/humblepowers/0.12.0', '0.9.1')
    assert 'SKEW' in line
    assert '0.9.1' in line
    assert '0.12.0' in line


def test_a_working_tree_that_agrees_says_so_rather_than_going_silent():
    line = field_line('humblepowers', '0.12.0', '/cache/humblepowers/0.12.0', '0.12.0')
    assert 'SKEW' not in line
    assert 'working tree' in line


def test_the_rendered_line_is_ascii_because_reports_are_pasted_into_cp1252_consoles():
    line = field_line('humblepowers', '0.12.0', '/cache/hp/0.12.0', '0.9.1')
    line.encode('ascii')


def test_a_registry_that_cannot_be_read_is_an_error_not_an_empty_registry():
    # An unreadable registry silently returning {} would let the CLI report
    # "not installed" for a plugin that is - a wrong fact, quietly.
    assert read_registry(Path('/no/such/registry.json')) is None


def test_read_registry_parses_a_real_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'installed_plugins.json'
        p.write_text(json.dumps(REGISTRY), encoding='utf-8')
        assert read_registry(p) == REGISTRY


def test_tree_version_reads_the_manifest_and_is_none_when_there_is_no_checkout():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        manifest = root / 'plugins' / 'demo' / '.claude-plugin'
        manifest.mkdir(parents=True)
        (manifest / 'plugin.json').write_text('{"version": "9.9.9"}', encoding='utf-8')
        assert tree_version(root, 'demo') == '9.9.9'
        assert tree_version(root, 'absent') is None


def test_cli_refuses_an_unresolvable_plugin_and_names_nothing_plausible():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'installed_plugins.json'
        p.write_text(json.dumps(REGISTRY), encoding='utf-8')
        assert main(['engineering-discipline', '--registry', str(p)]) == 0
        # the reject path: no entry means exit 1, so a number cannot be had
        # by running the tool and ignoring it.
        assert main(['not-a-plugin', '--registry', str(p)]) == 1
        assert main(['x', '--registry', str(Path(d) / 'missing.json')]) == 1
    # naming no plugin is a usage error, never a clean bill of health
    assert main([]) == 2


if __name__ == '__main__':
    test_a_plugin_resolves_to_its_installed_version_and_path()
    test_an_unknown_plugin_resolves_to_nothing_rather_than_a_plausible_guess()
    test_a_marketplace_qualified_name_resolves_the_same_as_a_bare_one()
    test_the_field_line_carries_the_path_so_the_number_cannot_be_produced_without_it()
    test_a_working_tree_that_disagrees_forces_the_disclosure_into_the_pasted_line()
    test_a_working_tree_that_agrees_says_so_rather_than_going_silent()
    test_the_rendered_line_is_ascii_because_reports_are_pasted_into_cp1252_consoles()
    test_a_registry_that_cannot_be_read_is_an_error_not_an_empty_registry()
    test_read_registry_parses_a_real_file()
    test_tree_version_reads_the_manifest_and_is_none_when_there_is_no_checkout()
    test_cli_refuses_an_unresolvable_plugin_and_names_nothing_plausible()
    print('ok: all plugin_version tests passed')

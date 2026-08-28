#!/usr/bin/env python3
"""Emit a feedback report's `Tool/version` line from the install registry.

A report attributes its evidence to a version. Asking the author to read that
version and warning them not to guess is advice, and advice failed: one report
claimed `0.1.3 (installed cache, plugin.json)` for a plugin whose cache had only
ever held `0.5.0`, on a day when two sibling reports read the same cache
correctly. A real historical version is exactly the shape that survives a
self-check, so the field needs evidence rather than a warning.

This prints the field with its own provenance in it: the version, and the
resolved install path whose last segment IS that version. The number cannot be
produced without the read, and a cache-versus-checkout skew is rendered INTO the
line rather than left for the author to notice and narrate.

    python plugin_version.py session-workflow [--tree /path/to/repo]

Exit 0 when the plugin resolves, 1 when it does not (an unresolvable plugin is a
failure to attribute, never a clean bill of health), 2 on a usage error. Stdlib
only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path.home() / '.claude' / 'plugins' / 'installed_plugins.json'


def read_registry(path: Path) -> dict | None:
    """The install registry, or None when it cannot be read or parsed.

    None rather than `{}` on purpose: an empty dict makes every lookup report
    'not installed', which is a wrong fact stated quietly. The caller has to
    tell 'no registry' apart from 'registry without this plugin'.
    """
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def resolve_entry(registry: dict, plugin: str) -> dict | None:
    """The installed record for `plugin`, or None.

    Registry keys are `<name>@<marketplace>`; `plugin` may be given either way.
    The name is matched WHOLE — a prefix match would resolve a typo to a real
    neighbour's version, which is the failure this script exists to stop. A
    plugin installed at more than one scope resolves to the first record; both
    are reported by the CLI so the ambiguity is visible rather than silently
    collapsed.
    """
    wanted = plugin.split('@', 1)[0]
    for key, records in (registry.get('plugins') or {}).items():
        if key.split('@', 1)[0] != wanted:
            continue
        for record in records if isinstance(records, list) else [records]:
            if not isinstance(record, dict):
                continue
            version = record.get('version')
            if not version:
                continue
            return {
                'name': wanted,
                'marketplace': key.split('@', 1)[1] if '@' in key else None,
                'version': str(version),
                'install_path': str(record.get('installPath') or ''),
                'scope': record.get('scope'),
            }
    return None


def tree_version(repo_root: Path, plugin: str) -> str | None:
    """`plugins/<plugin>/.claude-plugin/plugin.json`'s version, or None."""
    manifest = repo_root / 'plugins' / plugin / '.claude-plugin' / 'plugin.json'
    try:
        data = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    version = data.get('version')
    return str(version) if version else None


def field_line(name: str, version: str, install_path: str, tree: str | None) -> str:
    """The report's `Tool/version` value, carrying its own provenance.

    The install path ends in the version, so the number and the evidence for it
    are one token: a line that was pasted was read. When a checkout disagrees,
    the disagreement is rendered here rather than left to the author, because
    the author is exactly who did not notice it.
    """
    line = f'{name} {version} (installed cache: {install_path})'
    if tree is None:
        return line
    if tree == version:
        return f'{line}; working tree agrees at {tree}'
    return f'{line}; working tree at {tree} - SKEW: name the copy you exercised'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a feedback report's Tool/version line from the install registry."
    )
    parser.add_argument('plugin', nargs='?', help='plugin name, with or without @marketplace')
    parser.add_argument(
        '--registry', default=None, help=f'install registry (default: {DEFAULT_REGISTRY})'
    )
    parser.add_argument(
        '--tree', default=None, help='repo root to compare the working tree against'
    )
    args = parser.parse_args(argv)

    if not args.plugin:
        print('error: name a plugin - resolving nothing is not an attribution', file=sys.stderr)
        return 2

    registry_path = Path(args.registry) if args.registry else DEFAULT_REGISTRY
    registry = read_registry(registry_path)
    if registry is None:
        print(f'error: cannot read the install registry at {registry_path}', file=sys.stderr)
        return 1

    entry = resolve_entry(registry, args.plugin)
    if entry is None:
        print(
            f'error: {args.plugin} is not in {registry_path} - do not attribute a version '
            'this could not confirm',
            file=sys.stderr,
        )
        return 1

    tree = tree_version(Path(args.tree), entry['name']) if args.tree else None
    print(
        f'- **Tool/version:** {field_line(entry["name"], entry["version"], entry["install_path"], tree)}'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

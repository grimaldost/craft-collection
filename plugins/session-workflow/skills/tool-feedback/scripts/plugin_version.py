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


def checkout_currency(repo_root: Path) -> str:
    """Whether the checkout is level with its upstream, as one readable line.

    A triage reconciles "shipped or absent?" against a working tree and never
    asks whether that tree is current. Three passes in one month ran against
    trees 4, 29 and 2 commits behind, and the 29-commit one was a full release
    behind with a remote-tracking ref 16 days stale, so even `git log
    origin/main` lied until a fetch. Every shipped/absent verdict taken against
    such a tree is wrong in the same direction, and the triage doc that results
    becomes the status of record.

    Fetches nothing: a read must not mutate the caller's repository. It reports
    the tracking ref's own staleness so a stale ref cannot pass as agreement."""
    import subprocess

    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv, no shell
                # `git` by PATH is deliberate: the caller's own git is the one
                # whose config and credentials define the upstream.
                ['git', '-C', str(repo_root), *args],  # noqa: S607
                capture_output=True,
                encoding='utf-8',
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    upstream = git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}')
    if not upstream:
        return '  checkout currency: no upstream tracking ref - cannot tell if it is current'
    counts = git('rev-list', '--left-right', '--count', 'HEAD...@{u}')
    if not counts or len(counts.split()) != 2:
        return f'  checkout currency: cannot compare against {upstream}'
    ahead, behind = counts.split()
    fetched = git('log', '-1', '--format=%cr', upstream) or 'unknown age'
    if behind == '0':
        return (
            f'  checkout currency: level with {upstream} (its tip is {fetched}; fetch to be sure)'
        )
    return (
        f'  checkout currency: {behind} commit(s) BEHIND {upstream}, {ahead} ahead - '
        f'reconcile against the remote, not this tree (its tip is {fetched})'
    )


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

    tree = None
    if args.tree:
        tree_root = Path(args.tree)
        tree = tree_version(tree_root, entry['name'])
        if tree is None:
            # A --tree that resolves no manifest used to return None, which
            # renders exactly like "the tree agrees" - a failure to attribute
            # reading as a clean bill of health, which is the one thing this
            # script exists not to do. Observed: --tree pointed at the plugin
            # directory instead of the repo root, and the line came back clean
            # over a real cache-versus-tree release skew.
            print(
                f'error: no plugins/{entry["name"]}/.claude-plugin/plugin.json under '
                f'{tree_root} - point --tree at the repo root, or omit it',
                file=sys.stderr,
            )
            return 1
    print(
        f'- **Tool/version:** {field_line(entry["name"], entry["version"], entry["install_path"], tree)}'
    )
    if args.tree:
        print(checkout_currency(Path(args.tree)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

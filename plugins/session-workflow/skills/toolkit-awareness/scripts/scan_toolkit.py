#!/usr/bin/env python3
"""Live inventory of installed Claude Code skills, commands, agents, hooks, and
plugins.

Scans user-level (~/.claude) and project-level (<cwd>/.claude) configuration, AND
asks the CLI for plugin-provided components (which live in the plugin cache, not
under .claude/) — a fresh, never-stale replacement for a hand-typed inventory.

Usage:
    python scan_toolkit.py                  # grouped table
    python scan_toolkit.py --json           # machine-readable
    python scan_toolkit.py --session-start  # inert unless TOOLKIT_AWARENESS_INJECT=1

Stdlib only (Python 3.10+). Plugin discovery shells out to `claude plugin list`
and degrades gracefully if the CLI is absent or changes its output format.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Component kinds discovered under a `.claude/` directory, plus plugins (which are
# discovered via the CLI). DISPLAY_ORDER is also the inventory's key set.
DIR_KINDS = ('skills', 'commands', 'agents', 'hooks')
DISPLAY_ORDER = ('skills', 'commands', 'agents', 'hooks', 'plugins')

_DESC_LIMIT = 100


def _read_frontmatter(md: Path) -> dict[str, str]:
    """Pull simple `key: value` pairs from a leading `---` frontmatter block,
    including `>` / `|` folded or literal block scalars (a `description: >` whose
    text continues on the following indented lines — a common pattern that a naive
    first-line parser truncates to just ">"). No YAML dependency; top-level keys
    only. {} on any error."""
    try:
        lines = md.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    if not lines or lines[0].strip() != '---':
        return {}
    out: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i].strip() != '---':
        line = lines[i]
        if ':' in line and not line[:1].isspace():  # a top-level key, not a nested line
            key, _, val = line.partition(':')
            key, val = key.strip(), val.strip()
            if val in ('>', '|', '>-', '|-', '>+', '|+'):  # block scalar — gather body
                body, i = [], i + 1
                while i < len(lines) and (not lines[i].strip() or lines[i][:1].isspace()):
                    body.append(lines[i].strip())
                    i += 1
                val = ' '.join(s for s in body if s)
                if key and key not in out:
                    out[key] = val
                continue
            if key and key not in out:  # first occurrence wins
                out[key] = val
        i += 1
    return out


def _preview(text: str, limit: int = _DESC_LIMIT) -> str:
    text = ' '.join(text.split())
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + '...'
    return text


def _scan_skills(skills_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not skills_dir.is_dir():
        return out
    for sub in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = sub / 'SKILL.md'
        if not skill_md.is_file():
            continue
        fm = _read_frontmatter(skill_md)
        out.append(
            {
                'name': fm.get('name', sub.name),
                'description': _preview(fm.get('description', '')),
                'path': str(sub),
            }
        )
    return out


def _scan_markdown_dir(d: Path) -> list[dict]:
    out: list[dict] = []
    if not d.is_dir():
        return out
    for md in sorted(d.glob('*.md')):
        fm = _read_frontmatter(md)
        out.append(
            {
                'name': fm.get('name', md.stem),
                'description': _preview(fm.get('description', '')),
                'path': str(md),
            }
        )
    return out


def _settings_hooks(claude_dir: Path) -> list[dict]:
    """List hook EVENTS actually configured in settings(.local).json — the most
    common real hook location, which a directory scan alone misses."""
    out: list[dict] = []
    for fname in ('settings.json', 'settings.local.json'):
        sp = claude_dir / fname
        if not sp.is_file():
            continue
        try:
            data = json.loads(sp.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        hooks = data.get('hooks') if isinstance(data, dict) else None
        if isinstance(hooks, dict):
            for event, entries in hooks.items():
                n = len(entries) if isinstance(entries, list) else 1
                out.append({'name': f'{event} x{n} [{fname}]', 'path': str(sp)})
    return out


def _scan_hooks(hooks_dir: Path, claude_dir: Path) -> list[dict]:
    out: list[dict] = []
    if hooks_dir.is_dir():
        for f in sorted(hooks_dir.iterdir()):
            if f.is_file():
                out.append({'name': f.name, 'path': str(f)})
    out.extend(_settings_hooks(claude_dir))
    return out


def _hooks_file_events(hooks_json: Path) -> list[dict]:
    """Enumerate the hook EVENTS declared in a plugin's `hooks/hooks.json` — the
    file `claude plugin list` points at via installPath but never expands. Shape
    mirrors settings: a top-level `hooks` dict keyed by event → list of matcher
    groups. On any read/parse error, [] (never raised)."""
    out: list[dict] = []
    try:
        data = json.loads(hooks_json.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, ValueError):
        return out
    hooks = data.get('hooks') if isinstance(data, dict) else None
    if isinstance(hooks, dict):
        for event, entries in hooks.items():
            n = len(entries) if isinstance(entries, list) else 1
            out.append({'name': f'{event} x{n}', 'path': str(hooks_json)})
    return out


def _enumerate_plugin_components(name: str, install_path) -> dict[str, list[dict]]:
    """Walk one installed plugin's on-disk layout and enumerate the components it
    provides — `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md`, and the events in
    `hooks/hooks.json`. `claude plugin list` yields each plugin's installPath but not
    the components under it, so this closes that gap. Each returned item is tagged with
    its owning `plugin` so the caller can merge it into the per-kind sections. A missing
    or unresolvable install_path yields empty lists, never raises — pure and unit-
    testable against a fixture tree, no `claude` CLI required."""
    empty: dict[str, list[dict]] = {'skills': [], 'commands': [], 'agents': [], 'hooks': []}
    if not install_path:
        return empty
    base = Path(install_path)
    if not base.is_dir():
        return empty
    comps = {
        'skills': _scan_skills(base / 'skills'),
        'commands': _scan_markdown_dir(base / 'commands'),
        'agents': _scan_markdown_dir(base / 'agents'),
        'hooks': _hooks_file_events(base / 'hooks' / 'hooks.json'),
    }
    for items in comps.values():
        for it in items:
            it['plugin'] = name
    return comps


def _plugin_description(install_path) -> str:
    """Best-effort plugin description from its manifest — `claude plugin list`
    omits it, so read .claude-plugin/plugin.json under the install path."""
    if not install_path:
        return ''
    try:
        manifest = Path(install_path) / '.claude-plugin' / 'plugin.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, ValueError):
        return ''
    return _preview(str(data.get('description', ''))) if isinstance(data, dict) else ''


def _plugins_from_json(data: object) -> list[dict]:
    """Pure parser for `claude plugin list --json`. The CLI returns a list of
    objects keyed by `id` (plugin@marketplace), with version/scope/enabled/
    installPath and NO name or description — so derive a readable name from `id`
    and pull the description from the manifest. Tolerates shape drift."""
    plugins = data.get('plugins') if isinstance(data, dict) else data
    if not isinstance(plugins, list):
        return []
    out: list[dict] = []
    for p in plugins:
        if isinstance(p, str):
            out.append({'name': p, 'description': '', 'plugin': p, 'installPath': None})
        elif isinstance(p, dict):
            ident = str(p.get('name') or p.get('id') or '?')
            label = ident.split('@', 1)[0]  # plugin@marketplace -> plugin
            ver = str(p.get('version', '')).strip()
            tags = [t for t in (ver, 'disabled' if p.get('enabled') is False else '') if t]
            suffix = f' ({", ".join(tags)})' if tags else ''
            desc = (
                _preview(str(p['description']))
                if p.get('description')
                else _plugin_description(p.get('installPath'))
            )
            # `name` carries the version/disabled suffix for the plugins section; the
            # bare `plugin` label + `installPath` let scan() walk the components under it.
            out.append(
                {
                    'name': label + suffix,
                    'description': desc,
                    'plugin': label,
                    'installPath': p.get('installPath'),
                }
            )
    return out


def _scan_plugins() -> list[dict]:
    """Plugin-provided components live in the plugin cache, not under .claude/ —
    ask the CLI. Tolerates the CLI being absent or failing; on any failure returns
    [] (the caller still reports the .claude inventory)."""
    try:
        proc = subprocess.run(
            ['claude', 'plugin', 'list', '--json'],  # noqa: S607 - 'claude' resolved from PATH
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0 or not (proc.stdout or '').strip():
        return []
    try:
        return _plugins_from_json(json.loads(proc.stdout))
    except (json.JSONDecodeError, ValueError):
        return []


def scan(roots: list[Path]) -> dict[str, list[dict]]:
    """Enumerate skills/commands/agents/hooks across each root's `.claude` dir, plus
    plugin-provided components (walked under each plugin's installPath). Missing dirs
    are skipped, never raised. `_caveats` carries a note when plugin-provided components
    could not be enumerated, so the human output degrades to an explicit caveat instead
    of a misleading bare `HOOKS (0)`."""
    result: dict[str, list[dict]] = {k: [] for k in DISPLAY_ORDER}
    result['_caveats'] = []
    for root in roots:
        claude = Path(root) / '.claude'
        if not claude.is_dir():
            continue
        result['skills'].extend(_scan_skills(claude / 'skills'))
        result['commands'].extend(_scan_markdown_dir(claude / 'commands'))
        result['agents'].extend(_scan_markdown_dir(claude / 'agents'))
        result['hooks'].extend(_scan_hooks(claude / 'hooks', claude))

    plugins = _scan_plugins()
    result['plugins'] = plugins
    # Walk each installed plugin's installPath and merge its components (tagged by owning
    # plugin) into the per-kind sections — the .claude scan alone is blind to them.
    walked = False
    for p in plugins:
        comps = _enumerate_plugin_components(
            p.get('plugin') or p.get('name', ''), p.get('installPath')
        )
        for kind in DIR_KINDS:
            if comps[kind]:
                walked = True
            result[kind].extend(comps[kind])
    if plugins and not walked:
        # Plugins are installed but none resolved to on-disk components (installPath
        # absent or unreadable) — say so rather than imply the per-kind counts are whole.
        result['_caveats'].append(
            'plugin-provided components not enumerated (installPath unavailable)'
        )
    elif not plugins:
        # The CLI is absent/failed, so plugin components are invisible to this scan.
        result['_caveats'].append(
            'plugin-provided components not enumerated (claude CLI unavailable)'
        )
    return result


def _print_table(inv: dict[str, list[dict]]) -> None:
    for kind in DISPLAY_ORDER:
        items = inv.get(kind, [])
        print(f'\n  {kind.upper()} ({len(items)})')
        if not items:
            print('    (none)')
            continue
        for it in items:
            desc = it.get('description', '')
            owner = f'[{it["plugin"]}] ' if it.get('plugin') else ''  # tag plugin-owned items
            print(f'    {it["name"]:<28} {owner}{desc}'.rstrip())
    for caveat in inv.get('_caveats', []):
        print(f'\n  note: {caveat}')
    print()


def _print_compact(inv: dict[str, list[dict]]) -> None:
    parts = []
    for kind in DISPLAY_ORDER:
        names = [it['name'] for it in inv.get(kind, [])]
        if names:
            parts.append(f'{kind}: ' + ', '.join(names))
    if parts:
        print('Installed toolkit: ' + ' | '.join(parts))
    for caveat in inv.get('_caveats', []):
        print(f'note: {caveat}')


def _default_roots() -> list[Path]:
    return [Path.home(), Path.cwd()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Live Claude Code toolkit inventory.')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    parser.add_argument(
        '--session-start',
        action='store_true',
        help='inject inventory only if TOOLKIT_AWARENESS_INJECT=1',
    )
    parser.add_argument(
        '--root',
        action='append',
        default=None,
        help='override scan root (repeatable); defaults to ~ and cwd',
    )
    args = parser.parse_args(argv)

    # SessionStart hook entry point: silent unless explicitly opted in, so the hook
    # can ship enabled-but-inert and cost nothing until the user wants it.
    if args.session_start and os.environ.get('TOOLKIT_AWARENESS_INJECT') != '1':
        return 0

    roots = [Path(r) for r in args.root] if args.root else _default_roots()
    inv = scan(roots)

    if args.json:
        print(json.dumps(inv, indent=2))
    elif args.session_start:
        _print_compact(inv)
    else:
        _print_table(inv)
    return 0


if __name__ == '__main__':
    sys.exit(main())

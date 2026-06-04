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
    """Pull simple `key: value` pairs from a leading `---` frontmatter block.
    No YAML dependency; only top-level scalar keys. {} on any error."""
    try:
        text = md.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return {}
    if not text.startswith('---'):
        return {}
    out: dict[str, str] = {}
    in_fm = False
    for i, line in enumerate(text.splitlines()):
        if i == 0 and line.strip() == '---':
            in_fm = True
            continue
        if in_fm and line.strip() == '---':
            break
        if in_fm and ':' in line:
            key, _, val = line.partition(':')
            key = key.strip()
            if key and key not in out:  # first occurrence wins
                out[key] = val.strip()
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
        out.append({'name': fm.get('name', sub.name),
                    'description': _preview(fm.get('description', '')),
                    'path': str(sub)})
    return out


def _scan_markdown_dir(d: Path) -> list[dict]:
    out: list[dict] = []
    if not d.is_dir():
        return out
    for md in sorted(d.glob('*.md')):
        fm = _read_frontmatter(md)
        out.append({'name': fm.get('name', md.stem),
                    'description': _preview(fm.get('description', '')),
                    'path': str(md)})
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
            out.append({'name': p, 'description': ''})
        elif isinstance(p, dict):
            ident = str(p.get('name') or p.get('id') or '?')
            label = ident.split('@', 1)[0]  # plugin@marketplace -> plugin
            ver = str(p.get('version', '')).strip()
            tags = [t for t in (ver, 'disabled' if p.get('enabled') is False else '') if t]
            suffix = f' ({", ".join(tags)})' if tags else ''
            desc = (_preview(str(p['description'])) if p.get('description')
                    else _plugin_description(p.get('installPath')))
            out.append({'name': label + suffix, 'description': desc})
    return out


def _scan_plugins() -> list[dict]:
    """Plugin-provided components live in the plugin cache, not under .claude/ —
    ask the CLI. Tolerates the CLI being absent or failing; on any failure returns
    [] (the caller still reports the .claude inventory)."""
    try:
        proc = subprocess.run(['claude', 'plugin', 'list', '--json'],
                              capture_output=True, text=True, timeout=20)
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
    plugin-provided components via the CLI. Missing dirs are skipped, never raised."""
    result: dict[str, list[dict]] = {k: [] for k in DISPLAY_ORDER}
    for root in roots:
        claude = Path(root) / '.claude'
        if not claude.is_dir():
            continue
        result['skills'].extend(_scan_skills(claude / 'skills'))
        result['commands'].extend(_scan_markdown_dir(claude / 'commands'))
        result['agents'].extend(_scan_markdown_dir(claude / 'agents'))
        result['hooks'].extend(_scan_hooks(claude / 'hooks', claude))
    result['plugins'] = _scan_plugins()
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
            print(f'    {it["name"]:<28} {desc}'.rstrip())
    print()


def _print_compact(inv: dict[str, list[dict]]) -> None:
    parts = []
    for kind in DISPLAY_ORDER:
        names = [it['name'] for it in inv.get(kind, [])]
        if names:
            parts.append(f'{kind}: ' + ', '.join(names))
    if parts:
        print('Installed toolkit: ' + ' | '.join(parts))


def _default_roots() -> list[Path]:
    return [Path.home(), Path.cwd()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Live Claude Code toolkit inventory.')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    parser.add_argument('--session-start', action='store_true',
                        help='inject inventory only if TOOLKIT_AWARENESS_INJECT=1')
    parser.add_argument('--root', action='append', default=None,
                        help='override scan root (repeatable); defaults to ~ and cwd')
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

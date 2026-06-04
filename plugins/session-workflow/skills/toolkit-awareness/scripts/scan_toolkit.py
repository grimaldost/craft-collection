#!/usr/bin/env python3
"""Live inventory of installed Claude Code skills, commands, agents, and hooks.

Scans user-level (~/.claude) and project-level (<cwd>/.claude) configuration and
reports what is installed — a fresh, never-stale replacement for a hand-typed
inventory.

Usage:
    python scan_toolkit.py                  # grouped table
    python scan_toolkit.py --json           # machine-readable
    python scan_toolkit.py --session-start  # inert unless TOOLKIT_AWARENESS_INJECT=1

Notes:
    Plugin-provided components live in the plugin cache and are best listed with
    `claude plugin list` / `claude plugin details`; this script covers the
    standard user/project .claude directories. Stdlib only (Python 3.10+).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# The four component kinds Claude Code discovers under a `.claude/` directory.
COMPONENT_DIRS = ('skills', 'commands', 'agents', 'hooks')

# First-sentence/description preview cap — long enough to be useful in a table,
# short enough to keep a session-start injection cheap.
_DESC_LIMIT = 100


def _read_frontmatter(md: Path) -> dict[str, str]:
    """Pull simple `key: value` pairs from a leading `---` frontmatter block.

    Minimal by design: no YAML dependency, only the top-level scalar keys we
    need (name, description). Returns {} on any read error or missing block.
    """
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
        out.append({
            'name': fm.get('name', sub.name),
            'description': _preview(fm.get('description', '')),
            'path': str(sub),
        })
    return out


def _scan_markdown_dir(d: Path) -> list[dict]:
    out: list[dict] = []
    if not d.is_dir():
        return out
    for md in sorted(d.glob('*.md')):
        fm = _read_frontmatter(md)
        out.append({
            'name': fm.get('name', md.stem),
            'description': _preview(fm.get('description', '')),
            'path': str(md),
        })
    return out


def _scan_hooks(hooks_dir: Path, claude_dir: Path) -> list[dict]:
    out: list[dict] = []
    if hooks_dir.is_dir():
        for f in sorted(hooks_dir.iterdir()):
            if f.is_file():
                out.append({'name': f.name, 'path': str(f)})
    settings = claude_dir / 'settings.json'
    if settings.is_file():  # settings.json can define hooks inline
        out.append({'name': 'settings.json (may define hooks inline)',
                    'path': str(settings)})
    return out


def scan(roots: list[Path]) -> dict[str, list[dict]]:
    """Enumerate skills/commands/agents/hooks across each root's `.claude` dir.

    `roots` are directories that *contain* a `.claude/` (e.g. the home dir and
    the project root). Missing directories are skipped, never raised.
    """
    result: dict[str, list[dict]] = {k: [] for k in COMPONENT_DIRS}
    for root in roots:
        claude = Path(root) / '.claude'
        if not claude.is_dir():
            continue
        result['skills'].extend(_scan_skills(claude / 'skills'))
        result['commands'].extend(_scan_markdown_dir(claude / 'commands'))
        result['agents'].extend(_scan_markdown_dir(claude / 'agents'))
        result['hooks'].extend(_scan_hooks(claude / 'hooks', claude))
    return result


def _print_table(inv: dict[str, list[dict]]) -> None:
    for kind in COMPONENT_DIRS:
        items = inv[kind]
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
    for kind in COMPONENT_DIRS:
        names = [it['name'] for it in inv[kind]]
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

    # SessionStart hook entry point: silent unless explicitly opted in, so the
    # hook can ship enabled-but-inert and cost nothing until the user wants it.
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

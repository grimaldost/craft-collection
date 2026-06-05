#!/usr/bin/env python3
"""Structural validator for the craft-collection marketplace.

Checks marketplace.json, each plugin.json, each SKILL.md (frontmatter,
description budget, line budget, reference resolution), and any hooks.json.
A fallback for `claude plugin validate` that needs no Claude Code CLI.

Run locally:
    uv run --no-project --with pyyaml -- python scripts/validate_plugins.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESC_CAP = 1536
SKILL_LINE_CAP = 500


def validate() -> list[str]:
    errors: list[str] = []

    mkt = ROOT / '.claude-plugin' / 'marketplace.json'
    try:
        mdata = json.loads(mkt.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        return [f'marketplace.json: {e}']
    root_prefix = (mdata.get('metadata') or {}).get('pluginRoot', '.')
    for p in mdata.get('plugins', []):
        if not (ROOT / root_prefix / p['source']).is_dir():
            errors.append(f'marketplace: plugin source not found: {p.get("source")}')

    for manifest in ROOT.glob('plugins/*/.claude-plugin/plugin.json'):
        plugin_dir = manifest.parent.parent
        try:
            pdata = json.loads(manifest.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{manifest}: invalid JSON: {e}')
            continue
        for field in ('name', 'version', 'description'):
            if field not in pdata:
                errors.append(f'{manifest}: missing "{field}"')
        hooks_ref = pdata.get('hooks')
        if hooks_ref:
            hp = plugin_dir / hooks_ref
            if not hp.is_file():
                errors.append(f'{manifest}: hooks file missing: {hooks_ref}')
            else:
                try:
                    json.loads(hp.read_text(encoding='utf-8'))
                except json.JSONDecodeError as e:
                    errors.append(f'{hp}: invalid JSON: {e}')

    for skill_md in ROOT.glob('plugins/*/skills/*/SKILL.md'):
        text = skill_md.read_text(encoding='utf-8')
        if not text.startswith('---'):
            errors.append(f'{skill_md}: no frontmatter')
            continue
        try:
            fm = yaml.safe_load(text.split('---', 2)[1]) or {}
        except yaml.YAMLError as e:
            errors.append(f'{skill_md}: bad frontmatter YAML: {e}')
            continue
        if not fm.get('name'):
            errors.append(f'{skill_md}: missing name')
        desc = (fm.get('description') or '') + (fm.get('when_to_use') or '')
        if not desc:
            errors.append(f'{skill_md}: missing description')
        elif len(desc) > DESC_CAP:
            errors.append(f'{skill_md}: description {len(desc)} > {DESC_CAP}')
        n_lines = text.count('\n') + 1
        if n_lines > SKILL_LINE_CAP:
            errors.append(f'{skill_md}: {n_lines} lines > {SKILL_LINE_CAP}')
        for ref in re.findall(r'references/([A-Za-z0-9_\-]+\.md)', text):
            if not (skill_md.parent / 'references' / ref).is_file():
                errors.append(f'{skill_md}: missing reference references/{ref}')

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print('VALIDATION FAILED:')
        for e in errors:
            print(f'  - {e}')
        return 1
    print('All plugins valid.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

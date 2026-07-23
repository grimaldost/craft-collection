#!/usr/bin/env python3
"""Structural validator for the craft-collection marketplace.

Checks marketplace.json, each plugin.json, each SKILL.md (frontmatter,
description budget, line budget, reference resolution), and any hooks.json.
A fallback for `claude plugin validate` that needs no Claude Code CLI.

PyYAML is optional: without it the frontmatter YAML checks are skipped (with a
note) while everything else — hook events, hooks.json shape, reference
resolution, word budgets — still runs. That keeps the stdlib-only pre-push
suite able to exercise the validator instead of skipping it whole (the gap
that hid two real gate issues, 2026-07-23).

Run locally (full):
    uv run --no-project --with pyyaml -- python scripts/validate_plugins.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # frontmatter checks degrade; everything else still runs
    yaml = None

from word_budget import check_budgets, current_counts, load_baselines

ROOT = Path(__file__).resolve().parent.parent
DESC_CAP = 1536
SKILL_LINE_CAP = 500
KNOWN_HOOK_EVENTS = {
    'PreToolUse',
    'PostToolUse',
    'Notification',
    'UserPromptSubmit',
    'Stop',
    'SubagentStop',
    'SessionStart',
    'SessionEnd',
    'PreCompact',
    # Verified real by the 2026-07-23 headless probes (docs/research/
    # 2026-07-22-claude-code-hook-events.md, "Empirically verified" section).
    'PostToolBatch',
    'PostToolUseFailure',
    'MessageDisplay',
}


def validate() -> list[str]:
    errors: list[str] = []

    mkt = ROOT / '.claude-plugin' / 'marketplace.json'
    try:
        mdata = json.loads(mkt.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as e:
        return [f'marketplace.json: {e}']
    root_prefix = (mdata.get('metadata') or {}).get('pluginRoot', '.')
    for p in mdata.get('plugins', []):
        src_dir = ROOT / root_prefix / p['source']
        if not src_dir.is_dir():
            errors.append(f'marketplace: plugin source not found: {p.get("source")}')
            continue
        # The same fact stated in two surfaces drifts silently: each marketplace
        # entry's description must equal its plugin.json description — the twin
        # of the bundled-scripts sync gate, for prose surfaces.
        try:
            pdata = json.loads(
                (src_dir / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8')
            )
        except (OSError, json.JSONDecodeError):
            continue  # a missing/broken manifest is reported by the manifest loop below
        if p.get('description') != pdata.get('description'):
            errors.append(
                f'marketplace: "{p.get("name")}" description differs from its '
                'plugin.json — sync the two surfaces'
            )

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

    # Validate every hooks.json Claude Code auto-discovers (plugins/<name>/hooks/hooks.json),
    # not just manifest-declared ones — no plugin.json declares a `hooks` field, so the
    # block above never fires and a broken hooks.json would otherwise ship silently.
    for hooks_file in sorted(ROOT.glob('plugins/*/hooks/hooks.json')):
        try:
            hdata = json.loads(hooks_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errors.append(f'{hooks_file}: invalid JSON: {e}')
            continue
        plugin_root = hooks_file.parent.parent
        # The only shape Claude Code reads is {"hooks": {<Event>: [...]}}. A
        # top-level array, or events sitting at the top level without the
        # "hooks" wrapper, used to coerce to {} here — the file skipped every
        # check below and shipped broken. Wrong shape is itself the error.
        events = hdata.get('hooks') if isinstance(hdata, dict) else None
        if not isinstance(events, dict):
            errors.append(
                f'{hooks_file}: top-level shape must be an object with a "hooks" '
                'mapping (events nest under "hooks")'
            )
            continue
        for event, groups in events.items():
            if event not in KNOWN_HOOK_EVENTS:
                errors.append(f'{hooks_file}: unknown hook event "{event}"')
            for group in groups or []:
                for hook in (group or {}).get('hooks') or []:
                    tokens = [hook.get('command') or ''] + [
                        a for a in (hook.get('args') or []) if isinstance(a, str)
                    ]
                    for tok in tokens:
                        ref = re.search(r'\$\{CLAUDE_PLUGIN_ROOT\}/([^\s"\']+)', tok)
                        if ref and not (plugin_root / ref.group(1)).is_file():
                            errors.append(
                                f'{hooks_file}: referenced script missing: {ref.group(1)}'
                            )

    for skill_md in ROOT.glob('plugins/*/skills/*/SKILL.md'):
        text = skill_md.read_text(encoding='utf-8')
        if not text.startswith('---'):
            errors.append(f'{skill_md}: no frontmatter')
            continue
        if yaml is not None:
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
        # references/<name>.md, including nested references/sub/deep.md (the old regex
        # allowed no '/', so a dangling nested reference passed silently).
        for ref in re.findall(r'references/([A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+)*\.md)', text):
            if not (skill_md.parent / 'references' / ref).is_file():
                errors.append(f'{skill_md}: missing reference references/{ref}')
        # ${CLAUDE_PLUGIN_ROOT}/<path> resolves against the plugin root — a skill that
        # points Claude at a renamed/moved script (e.g. a scan_toolkit.py) is caught here.
        plugin_root = skill_md.parents[2]
        for ref in re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_\-./]+\.[A-Za-z0-9]+)', text):
            if not (plugin_root / ref).is_file():
                errors.append(f'{skill_md}: missing ${{CLAUDE_PLUGIN_ROOT}} reference {ref}')

    # Word-budget ratchet (issue #54): a skill body may not grow past its recorded
    # baseline without a reviewed baseline bump that names what the growth displaces.
    # Follows the module ROOT so fixture trees are self-contained (the T3b leak bit
    # twice: defaults scanned the REAL repo under a patched ROOT, failing fixture
    # tests whenever the working tree was transiently over budget). No
    # scripts/word_budget.json under ROOT -> no budget check; the real repo's file
    # is tracked, so its absence would be a visible diff, not a silent skip.
    budget_file = ROOT / 'scripts' / 'word_budget.json'
    if budget_file.is_file():
        errors += check_budgets(current_counts(ROOT), load_baselines(budget_file))

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print('VALIDATION FAILED:')
        for e in errors:
            print(f'  - {e}')
        return 1
    note = ' (frontmatter YAML checks skipped: PyYAML not installed)' if yaml is None else ''
    print(f'All plugins valid.{note}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

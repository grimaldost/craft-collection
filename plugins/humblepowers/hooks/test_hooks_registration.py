#!/usr/bin/env python3
"""Pins for what humblepowers registers in hooks.json (no pytest required).

0.18.0 removed the SubagentStop verification gate and the PreToolUse spawn-routing
hint. The one remaining hook is the UserPromptSubmit dispatch router, and every
script a hook names has to exist in the plugin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
HOOKS = PLUGIN / 'hooks' / 'hooks.json'


def _hooks() -> dict:
    return json.loads(HOOKS.read_text(encoding='utf-8'))['hooks']


def test_no_subagent_stop_and_no_agent_pre_tool_use():
    hooks = _hooks()
    assert 'SubagentStop' not in hooks, 'the SubagentStop verification gate is registered'
    for entry in hooks.get('PreToolUse', []):
        matcher = entry.get('matcher', '')
        assert 'Agent' not in matcher and 'Workflow' not in matcher, matcher


def test_only_the_dispatch_router_remains():
    hooks = _hooks()
    assert sorted(hooks) == ['UserPromptSubmit'], sorted(hooks)
    args = [a for entry in hooks['UserPromptSubmit'] for h in entry['hooks'] for a in h['args']]
    assert any(a.endswith('choosing-tools/scripts/inject_dispatch.py') for a in args), args


def test_every_named_script_exists():
    for entries in _hooks().values():
        for entry in entries:
            for hook in entry['hooks']:
                for arg in hook.get('args', []):
                    if arg.endswith('.py'):
                        rel = arg.replace('${CLAUDE_PLUGIN_ROOT}/', '')
                        assert (PLUGIN / rel).is_file(), rel


def main() -> int:
    test_no_subagent_stop_and_no_agent_pre_tool_use()
    test_only_the_dispatch_router_remains()
    test_every_named_script_exists()
    print('ok: hooks_registration')
    return 0


if __name__ == '__main__':
    sys.exit(main())

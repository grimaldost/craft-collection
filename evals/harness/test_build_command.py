"""Tests for claude_runner.build_command. Runnable with pytest or `python test_build_command.py`."""

from __future__ import annotations

from claude_runner import build_command


def test_with_plugin_stream():
    cmd = build_command(
        plugin_dir='plugins/session-workflow',
        allowed_tools='Skill,Read',
        model='claude-sonnet-4-6',
        max_turns=8,
        max_budget_usd=0.5,
        stream=True,
    )
    assert '--bare' not in cmd  # --bare strips the config-bound login; never use it
    assert cmd[cmd.index('--plugin-dir') + 1] == 'plugins/session-workflow'
    assert 'stream-json' in cmd and '--verbose' in cmd
    assert cmd[cmd.index('--model') + 1] == 'claude-sonnet-4-6'
    # bypassPermissions auto-approves every tool and nullifies the allowlist —
    # it is how a trigger-arm spawn once wrote into a real repo. Never readd it.
    assert '--permission-mode' not in cmd
    assert 'bypassPermissions' not in cmd


def test_without_plugin_json():
    cmd = build_command(
        plugin_dir=None, allowed_tools='', model='m', max_turns=4, max_budget_usd=0, stream=False
    )
    assert '--bare' not in cmd
    assert '--plugin-dir' not in cmd
    assert 'json' in cmd and 'stream-json' not in cmd
    assert '--max-budget-usd' not in cmd  # omitted when 0
    assert '--disallowed-tools' not in cmd  # omitted when empty


def test_disallowed_tools_flag():
    cmd = build_command(
        plugin_dir=None,
        allowed_tools='Skill,Read,Glob,Grep',
        model='m',
        max_turns=3,
        max_budget_usd=0.5,
        stream=True,
        disallowed_tools='Write,Edit,Bash',
    )
    assert cmd[cmd.index('--disallowed-tools') + 1] == 'Write,Edit,Bash'


if __name__ == '__main__':
    test_with_plugin_stream()
    test_without_plugin_json()
    test_disallowed_tools_flag()
    print('ok: all build_command tests passed')

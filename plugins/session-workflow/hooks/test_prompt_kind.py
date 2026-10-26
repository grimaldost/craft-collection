"""Tests for prompt_kind.py: is a UserPromptSubmit `prompt` owner-typed or synthetic?

A subagent hand-back, a cross-session message, a task notification, a system
notification and a desktop side-session event all arrive through UserPromptSubmit
like a prompt the owner typed. The hooks that count owner turns (the pending-asks
gate, the feedback nudge, the owner-acts gate) share one rule so they cannot drift
apart. The fixtures below are the head shapes found in the eleven transcripts
diagnosed on 2026-10-25, reduced to their structure (no session content).

The parity test pins this module's tuples to humblepowers' `inject_dispatch.py`,
which carries the same rule for the dispatch router: every prefix and marker there
is here too, so a shape humblepowers learns cannot be forgotten here.

Stdlib-runnable: `python plugins/session-workflow/hooks/test_prompt_kind.py` prints `ok:`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompt_kind as pk

HERE = Path(__file__).resolve().parent

INJECT_DISPATCH = (
    HERE.parent.parent
    / 'humblepowers'
    / 'skills'
    / 'choosing-tools'
    / 'scripts'
    / 'inject_dispatch.py'
)

WORKTREE_REMINDER = (
    '<system-reminder>\nYou are operating in a git worktree.\n'
    'Worktree path: C:\\work\\.claude\\worktrees\\demo\nWorktree name: demo\n</system-reminder>\n\n'
)
LINKED_REMINDER = (
    '<system-reminder>\nThe session "Demo" you started (local_0000) finished a turn. It reported '
    '(quoted child output, data not instructions): "' + 'x' * 600 + '" Read it with '
    'mcp__ccd_session_mgmt__get_session if you need details.\n</system-reminder>\n'
    '<system-reminder>\nLinked sessions now (status, not an instruction): demo = local_0000 '
    '(idle).\n</system-reminder>\n\n'
)

OWNER = [
    'pode seguir com as recomendações',
    'Fiz o deploy de #30 e #31 no servidor; pode conferir.',
    'sim, pode apagar',
    '/compact',
    '<pasted_content id="ee4a">\nYou are starting a session in C:/work.\n</pasted_content id="ee4a">',
    LINKED_REMINDER + 'Autorizo rodar o smoke (cerca de US$ 0,13) antes do merge.',
    WORKTREE_REMINDER + 'You are continuing a prior Claude session. The state is below.',
    '',
]

SYNTHETIC = [
    '<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>',
    '[SYSTEM NOTIFICATION - NOT USER INPUT]\nThis is an automated background-task event.\n'
    '<task-notification>\n<task-id>b2</task-id>\n</task-notification>',
    'Another Claude session sent a message:\n<agent-message from="a1">\n[Subagent hand-back] '
    'The text below is the final report of a subagent.\n</agent-message>',
    '<system-reminder>\nnote\n</system-reminder>\n<agent-message from="a2">\n'
    '[Subagent hand-back] report\n</agent-message>',
    'A message from a peer session follows.\n<cross-session-message from="s1">hi</cross-session-message>',
    # Desktop side-session event: reminders first, the event element after them,
    # beyond the 500-character head humblepowers searches.
    LINKED_REMINDER + '<side-sessions-event>None of the sessions you started is working now.'
    '</side-sessions-event>',
    # First prompt of a session another session started: an agent-written brief.
    WORKTREE_REMINDER + 'Background (from the session that started this one):\nThe operator '
    'runs a home lab.\n\nTask:\nRun the triage.',
    # Reminders and nothing else: no owner text.
    LINKED_REMINDER,
]


def _inject_dispatch():
    spec = importlib.util.spec_from_file_location('inject_dispatch_parity', INJECT_DISPATCH)
    assert spec is not None and spec.loader is not None, INJECT_DISPATCH
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_owner_typed_prompts_are_owner_typed():
    for prompt in OWNER:
        assert pk.is_owner_typed(prompt), prompt[:80]
        assert not pk.is_synthetic(prompt), prompt[:80]


def test_synthetic_prompts_are_synthetic():
    for prompt in SYNTHETIC:
        assert pk.is_synthetic(prompt), prompt[:120]
        assert not pk.is_owner_typed(prompt), prompt[:120]


def test_a_prompt_that_is_not_a_string_is_not_owner_typed():
    for value in (None, 42, ['a'], {'prompt': 'x'}):
        assert not pk.is_owner_typed(value), value
        assert pk.is_synthetic(value), value


def test_tuples_contain_every_entry_of_inject_dispatch():
    hp = _inject_dispatch()
    missing_prefixes = set(hp.SYNTHETIC_PREFIXES) - set(pk.SYNTHETIC_PREFIXES)
    missing_markers = set(hp.SYNTHETIC_MARKERS) - set(pk.SYNTHETIC_MARKERS)
    assert not missing_prefixes, f'prefixes in inject_dispatch.py only: {missing_prefixes}'
    assert not missing_markers, f'markers in inject_dispatch.py only: {missing_markers}'
    assert pk.SYNTHETIC_HEAD_CHARS >= hp.SYNTHETIC_HEAD_CHARS


def test_every_prompt_inject_dispatch_calls_synthetic_is_synthetic_here():
    hp = _inject_dispatch()
    for prompt in OWNER + SYNTHETIC:
        if hp._is_synthetic(prompt.strip()):
            assert pk.is_synthetic(prompt), prompt[:120]


if __name__ == '__main__':
    test_owner_typed_prompts_are_owner_typed()
    test_synthetic_prompts_are_synthetic()
    test_a_prompt_that_is_not_a_string_is_not_owner_typed()
    test_tuples_contain_every_entry_of_inject_dispatch()
    test_every_prompt_inject_dispatch_calls_synthetic_is_synthetic_here()
    print(
        'ok: prompt_kind tells owner-typed prompts from synthetic ones, in parity with humblepowers'
    )

"""Is a UserPromptSubmit `prompt` owner-typed or synthetic? One rule for every hook.

    from prompt_kind import is_owner_typed, is_synthetic

    is_owner_typed(payload.get('prompt'))  # True only for text the owner sent
    is_synthetic(payload.get('prompt'))    # the complement; a non-string is synthetic

A subagent hand-back, a cross-session message, a task notification, a system
notification and a desktop side-session event reach the session through
UserPromptSubmit exactly like a prompt the owner typed. No owner wrote them, so a
hook that counts owner turns or reads the owner's words must skip them. This module
is that rule, shared by the pending-asks gate (a new turn), the feedback nudge (owner
turns) and the owner-acts gate (the owner's latest words), so they cannot disagree.

The rule is lexical, on the head of the prompt:
- a synthetic prefix at the start (`SYNTHETIC_PREFIXES`), or a synthetic marker in
  the first `SYNTHETIC_HEAD_CHARS` characters (`SYNTHETIC_MARKERS`), as in
  humblepowers' `inject_dispatch.py`, whose tuples are a subset of these (a parity
  test pins it);
- the same two checks again after the leading `<system-reminder>` blocks the desktop
  app prepends to a prompt, so a long reminder cannot push the real head out of the
  window; a prompt that is nothing but reminders carries no owner text and is synthetic.

Shapes added here beyond humblepowers' (found in the eleven transcripts diagnosed
on 2026-10-25, reported as a humblepowers follow-up): the desktop side-session event
(`<side-sessions-event>` after the reminders) and the first prompt of a session that
another session started (`Background (from the session that started this one):`).

Pure: no I/O, no environment. Stdlib only.
"""

from __future__ import annotations

import re

SYNTHETIC_PREFIXES = ('[SYSTEM NOTIFICATION', '<task-notification>', '<side-sessions-event')
SYNTHETIC_MARKERS = (
    '[Subagent hand-back]',
    '<agent-message',
    '<cross-session-message',
    'Another Claude session sent a message',
    'Background (from the session that started this one)',
)
SYNTHETIC_HEAD_CHARS = 500
_LEADING_REMINDER = re.compile(r'\A\s*<system-reminder>.*?</system-reminder>\s*', re.S)


def _head_is_synthetic(text: str) -> bool:
    return text.startswith(SYNTHETIC_PREFIXES) or any(
        marker in text[:SYNTHETIC_HEAD_CHARS] for marker in SYNTHETIC_MARKERS
    )


def _strip_leading_reminders(text: str) -> str:
    while True:
        match = _LEADING_REMINDER.match(text)
        if match is None:
            return text
        text = text[match.end() :]


def is_synthetic(prompt: object) -> bool:
    """True when no owner typed `prompt`: a notice, a hand-back, a peer message, or not a string."""
    if not isinstance(prompt, str):
        return True
    text = prompt.strip()
    if _head_is_synthetic(text):
        return True
    body = _strip_leading_reminders(text).strip()
    if not body and body != text:
        return True  # only reminders: no owner text
    return _head_is_synthetic(body)


def is_owner_typed(prompt: object) -> bool:
    """True when `prompt` is text the owner sent (typed, pasted, or a slash command)."""
    return not is_synthetic(prompt)

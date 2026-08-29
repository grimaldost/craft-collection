#!/usr/bin/env python3
"""Reject AI attribution in a commit message -- trailers and badge lines.

CONTRIBUTING's rule -- this repository does not stamp tools onto authorship --
was enforced only for the `Co-Authored-By:` trailer shape, by an inline grep in
the pre-commit config. Extracted to a script so the check is red-proof
registered like any other gate, and extended to the other shape the ecosystem
emits: a standalone "Generated with <tool>" badge line.

The pre-commit commit-msg lane runs this with the message file as its
argument. Comment lines (leading `#`) are the editor template, not the
message, and are ignored.

Usage: python scripts/check_commit_msg.py <message-file>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TRAILER = re.compile(r'^\s*co-authored-by:.*\b(claude|gpt|anthropic)\b', re.IGNORECASE)
BADGE = re.compile(r'\bgenerated with\b.*\b(claude|gpt|anthropic)\b', re.IGNORECASE)


def findings(message: str) -> list[str]:
    """Offending lines in `message`, ASCII-safe for any console. Pure."""
    out: list[str] = []
    for line in message.splitlines():
        if line.lstrip().startswith('#'):
            continue
        if TRAILER.search(line) or BADGE.search(line):
            out.append(line.strip().encode('ascii', 'backslashreplace').decode('ascii'))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print('usage: check_commit_msg.py <message-file>')
        return 2
    try:
        text = Path(argv[0]).read_text(encoding='utf-8', errors='replace')
    except OSError as err:
        print(f'cannot read the commit message file: {err}')
        return 2
    found = findings(text)
    for line in found:
        print(f'AI attribution in the commit message: {line}')
    if found:
        print('remove the line and re-commit; this repository does not stamp tools onto authorship')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

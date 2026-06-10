#!/usr/bin/env python3
"""Inject the compact choosing-tools dispatch protocol at session start.

SessionStart hook entry point for the humblepowers plugin. Ships wired but
inert: prints nothing unless HUMBLEPOWERS_DISPATCH_INJECT=1 is set, so the
hook costs nothing until the user opts in.

Usage:
    python inject_dispatch.py                  # print the protocol (manual)
    python inject_dispatch.py --session-start  # inert unless HUMBLEPOWERS_DISPATCH_INJECT=1

Stdlib only (Python 3.10+).
"""

from __future__ import annotations

import argparse
import os
import sys

# ASCII-only: hook stdout encoding varies with the host console (cp1252 vs utf-8).
PROTOCOL = """\
<toolkit-dispatch>
At the start of substantive work (build / fix / migrate / refactor / review /
plan - not conversational turns or follow-ups inside an active task):
1. Name the task in one phrase.
2. Shortlist installed skills whose triggers match; scan the toolkit when unsure.
3. Check candidates against positive and negative triggers; negative space
   ("not for X - that is Y") decides ties.
4. Load the best fit when its benefit clearly exceeds its context and anchoring
   cost. Process disciplines load before implementation skills.
5. Nothing clears the bar: proceed, and say so in one line.
6. A loaded skill that turns out wrong is set aside explicitly, not followed
   through.
</toolkit-dispatch>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Compact dispatch-protocol inject.')
    parser.add_argument(
        '--session-start',
        action='store_true',
        help='inject only if HUMBLEPOWERS_DISPATCH_INJECT=1',
    )
    args = parser.parse_args(argv)

    # SessionStart hook entry point: silent unless explicitly opted in, so the hook
    # can ship enabled-but-inert and cost nothing until the user wants it.
    if args.session_start and os.environ.get('HUMBLEPOWERS_DISPATCH_INJECT') != '1':
        return 0

    print(PROTOCOL)
    return 0


if __name__ == '__main__':
    sys.exit(main())

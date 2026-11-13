"""A fake harness that also prints in its session; not a test module itself.

argv: as `canary_fake_harness.py`. Its canary run is that fake's. Its session
writes `SESSION-STDOUT` to descriptor 1 and `SESSION-STDERR` to descriptor 2,
then plays that fake's session, so a test can see that what a launched harness
prints still reaches the caller of `kit run`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import canary_fake_harness

STDOUT_TEXT = 'SESSION-STDOUT'
STDERR_TEXT = 'SESSION-STDERR'


def main() -> int:
    if sys.argv[5:] != ['--version'] and not os.environ.get('KIT_CANARY_NONCE'):
        os.write(1, (STDOUT_TEXT + '\n').encode('ascii'))
        os.write(2, (STDERR_TEXT + '\n').encode('ascii'))
    return canary_fake_harness.main()


if __name__ == '__main__':
    sys.exit(main())

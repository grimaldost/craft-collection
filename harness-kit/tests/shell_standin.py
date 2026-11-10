"""A stand-in for `kit judge`, started by the shell tests in place of the real CLI.

Usage: shell_standin.py CAPTURE MODE [ARG]. It writes the bytes it received on
stdin to CAPTURE, then acts by MODE:

- allow: print an allow verdict;
- deny REASON: print a deny verdict with that reason;
- exit3: print an allow verdict and exit 3;
- silent: print nothing;
- garbage: print a line that is not JSON;
- notverdict: print a JSON object that is not a verdict;
- hang LATE: start a grandchild that writes LATE after 6 seconds and holds
  this process's stdout, then hang;
- orphan LATE: start a child that starts that grandchild and exits at once,
  wait for the child to end, then hang.
Not a test module itself (no `test_` prefix).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

LATE = 'import sys, time; time.sleep(6); open(sys.argv[1], "w").write("late")'


def _verdict(effect: str, reason: str) -> str:
    out = {
        'kit_verdict': 1,
        'verdict': effect,
        'effect': effect,
        'governed': effect == 'deny',
        'rule': 'r1' if effect == 'deny' else None,
        'reason': reason,
        'layer': 'cli',
        'policy_sha256': None,
        'run_id': None,
        'launched': False,
    }
    return json.dumps(out, ensure_ascii=True)


def _start(code: str, *args: str, keep_stdout: bool = False) -> subprocess.Popen:
    return subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-I', '-c', code, *args],
        stdin=subprocess.DEVNULL,
        stdout=None if keep_stdout else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main(argv: list[str]) -> int:
    capture, mode, *rest = argv
    data = sys.stdin.buffer.read()
    with open(capture, 'wb') as fh:
        fh.write(data)
    if mode in ('allow', 'exit3'):
        print(_verdict('allow', ''))
        return 3 if mode == 'exit3' else 0
    if mode == 'deny':
        print(_verdict('deny', rest[0]))
    elif mode == 'garbage':
        print('this is not a verdict')
    elif mode == 'notverdict':
        print(json.dumps({'effect': 'allow'}))
    elif mode == 'hang':
        _start(LATE, rest[0], keep_stdout=True)
        time.sleep(60)
    elif mode == 'orphan':
        middle = 'import subprocess, sys; subprocess.Popen([sys.executable, "-I", "-c", sys.argv[1], sys.argv[2]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)'
        _start(middle, LATE, rest[0]).wait()
        time.sleep(60)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

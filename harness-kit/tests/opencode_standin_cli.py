"""Stand-in for `kit judge`, used by the opencode shell tests.

argv: MODE RECORD_PATH MARKER_PATH. Records stdin to RECORD_PATH, then behaves by MODE.
"""

import subprocess
import sys
import time

mode, record, marker = sys.argv[1:4]
raw = sys.stdin.buffer.read()
with open(record, 'wb') as fh:
    fh.write(raw)

ALLOW = '{"kit_verdict": 1, "verdict": "allow", "effect": "allow", "reason": "ok"}'
DENY = '{"kit_verdict": 1, "verdict": "deny", "effect": "deny", "reason": "blocked by test rule"}'
LATE = f'import time; time.sleep(6); open({marker!r}, "w").write("late")'

if mode == 'allow':
    print(ALLOW)
elif mode == 'deny':
    print(DENY)
elif mode == 'garbage':
    print('not json at all')
elif mode == 'not_a_verdict':
    print('{"effects": []}')
elif mode == 'exit1':
    print(ALLOW)
    sys.exit(1)
elif mode == 'hang':
    subprocess.Popen([sys.executable, '-c', LATE])  # noqa: S603
    time.sleep(60)
# mode 'empty' prints nothing and exits 0

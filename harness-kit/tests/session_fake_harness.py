"""A fake harness for the session-mode tests of `kit run`; not a test module itself.

argv: OUT VERSION CODE MODE OPTIONS HARNESS_ARGS...

It plays `canary_fake_harness.py` (whose canary it runs, by MODE) with OPTIONS, a JSON object:
- `canary_edit`: [ACTION, PATH]: the canary run first changes (`change`), adds (`add`) or
  removes (`remove`) the file PATH, then plays the canary;
- `tree`: the session starts a child at once, which starts a long-lived grandchild and writes
  both pids to OUT.pids; the session waits for that file, then ends without waiting for either;
- `deaf_canary`: the canary run ignores Ctrl+C and Ctrl+Break, writes its pid to
  OUT.deaf-started, sleeps 8 seconds and then writes OUT.ran-on, unless something ended it.

`--version` prints `fake harness VERSION`. The session writes OUT: its arguments, its
environment, its folder, and the text of `run-open.json` in its home's folder (null when
absent; the home is the parent of `HOME`). Then it exits CODE.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canary_fake_harness import canary

DEAF_S = 8
TREE_CHILD = (
    'import os, subprocess, sys, time\n'
    'g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])\n'
    'open(sys.argv[1], "w").write(f"{os.getpid()} {g.pid}")\n'
    'time.sleep(120)\n'
)


def edit(action: str, path: str) -> None:
    target = Path(path)
    if action == 'remove':
        target.unlink()
    elif action == 'add':
        target.write_bytes(b'added by the canary\n')
    else:
        target.write_bytes(target.read_bytes() + b' ')


def deaf(out: str) -> None:
    """A canary harness that an interrupt does not end: only its tree being ended does."""
    for name in ('SIGINT', 'SIGBREAK'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), signal.SIG_IGN)
    Path(out + '.deaf-started').write_text(str(os.getpid()), encoding='ascii')
    time.sleep(DEAF_S)
    Path(out + '.ran-on').write_text('ran on', encoding='ascii')


def start_tree(out: str) -> None:
    pids = Path(out + '.pids')
    subprocess.Popen([sys.executable, '-c', TREE_CHILD, str(pids)])  # noqa: S603
    end = time.monotonic() + 30
    while not pids.is_file() and time.monotonic() < end:
        time.sleep(0.05)


def session(out: str, options: dict) -> None:
    if options.get('tree'):
        start_tree(out)
    home = Path(os.environ.get('HOME', '.')).parent
    run_open = home / 'run-open.json'
    text = run_open.read_text(encoding='utf-8') if run_open.is_file() else None
    seen = {'args': sys.argv[6:], 'env': dict(os.environ), 'cwd': os.getcwd(), 'run_open': text}
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(seen, fh)


def main() -> int:
    out, version, code, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    options = json.loads(sys.argv[5])
    if sys.argv[6:] == ['--version']:
        print('fake harness ' + version)
        return 0
    if os.environ.get('KIT_CANARY_NONCE'):
        if options.get('deaf_canary'):
            deaf(out)
            return code
        if options.get('canary_edit'):
            edit(*options['canary_edit'])
        canary(out, mode)
    else:
        session(out, options)
    return code


if __name__ == '__main__':
    sys.exit(main())

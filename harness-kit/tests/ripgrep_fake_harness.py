"""A fake harness for the ripgrep tests of `kit run`; not a test module itself.

argv: OUT VERSION STEPS HARNESS_ARGS...

`--version` prints `fake harness VERSION`. STEPS is a JSON object with two lists of steps,
`canary` and `session`, each step `[OP, PATH, ...]` with PATH absolute:
- `create`: create the file with a few bytes, and its folder; off Windows its mode is `0o755`,
  so a planted `rg` is one opencode would run;
- `append`: append one byte to the file;
- `remove`: remove the file;
- `rmdir`: remove the empty folder;
- `mkdir`: create the folder;
- `chmod`: set the file's mode to the third item;
- `sleep`: sleep the second item's seconds (PATH is not read).
With `KIT_CANARY_NONCE` in its environment it runs the `canary` steps, then plays the canary's
harness, guarded (`canary_fake_harness.canary`). Otherwise it writes OUT (its folder and its
`PATH`), runs the `session` steps, writes `OUT.after` and exits 0.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canary_fake_harness import canary

PLANTED_MODE = 0o755


def step(item: list) -> None:
    op = item[0]
    if op == 'sleep':
        time.sleep(float(item[1]))
        return
    path = Path(item[1])
    if op == 'create':
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'planted\n')
        if os.name != 'nt':
            os.chmod(path, PLANTED_MODE)
    elif op == 'append':
        with open(path, 'ab') as fh:
            fh.write(b' ')
    elif op == 'remove':
        path.unlink()
    elif op == 'rmdir':
        path.rmdir()
    elif op == 'mkdir':
        path.mkdir(parents=True)
    elif op == 'chmod':
        os.chmod(path, int(item[2]))
    else:
        raise ValueError(op)


def main() -> int:
    out, version, steps = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    if sys.argv[4:] == ['--version']:
        print('fake harness ' + version)
        return 0
    if os.environ.get('KIT_CANARY_NONCE'):
        for item in steps.get('canary', []):
            step(item)
        canary(out, 'guarded')
        return 0
    seen = {'cwd': os.getcwd(), 'path': os.environ.get('PATH')}
    Path(out).write_text(json.dumps(seen), encoding='utf-8')
    for item in steps.get('session', []):
        step(item)
    Path(out + '.after').write_text('after', encoding='ascii')
    return 0


if __name__ == '__main__':
    sys.exit(main())

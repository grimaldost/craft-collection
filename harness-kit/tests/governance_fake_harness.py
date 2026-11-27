"""A fake harness for the tests of the check during a run; not a test module itself.

argv: OUT VERSION ACTIONS HARNESS_ARGS...

`--version` prints `fake harness VERSION`. With `KIT_CANARY_NONCE` in its environment it plays
the canary's harness, guarded (`canary_fake_harness.canary`). Otherwise it plays the session:
it runs ACTIONS, a JSON list of `[OP, WHERE, ...]`, in order, then writes `OUT.after` and exits
0. WHERE names a path: `home:REL` (REL in the home, the parent of `HOME`), `work:REL` (REL in
its working folder), `policy` (`KIT_POLICY`), `run` (its run's `run.json`) or `abs:PATH`.
- `append`: append one byte to the file;
- `rewrite`: replace the file's bytes, then restore them the third item's milliseconds later;
- `create`: create the file, and its folder;
- `remove`: remove the file;
- `sleep`: sleep the second item's seconds.
The time of the first change is written to `OUT.changed` right after it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canary_fake_harness import canary


def where(name: str) -> Path:
    if name.startswith('home:'):
        return Path(os.environ['HOME']).parent / name[len('home:') :]
    if name.startswith('work:'):
        return Path(os.getcwd()) / name[len('work:') :]
    if name.startswith('abs:'):
        return Path(name[len('abs:') :])
    if name == 'policy':
        return Path(os.environ['KIT_POLICY'])
    if name == 'run':
        return Path(os.environ['KIT_STATE_ROOT'], 'runs', os.environ['KIT_RUN_ID'], 'run.json')
    raise ValueError(name)


def act(out: str, step: list) -> bool:
    """Run one step; True when it changed a file."""
    op = step[0]
    if op == 'sleep':
        time.sleep(float(step[1]))
        return False
    path = where(step[1])
    if op == 'append':
        with open(path, 'ab') as fh:
            fh.write(b' ')
    elif op == 'rewrite':
        data = path.read_bytes()
        path.write_bytes(data + b'\n')
        time.sleep(float(step[2]) / 1000)
        path.write_bytes(data)
    elif op == 'create':
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{}\n')
    elif op == 'remove':
        path.unlink()
    else:
        raise ValueError(op)
    return True


def session(out: str, actions: list) -> None:
    marked = False
    for step in actions:
        if act(out, step) and not marked:
            Path(out + '.changed').write_text(repr(time.time()), encoding='ascii')
            marked = True
    Path(out + '.after').write_text('after', encoding='ascii')


def main() -> int:
    out, version, actions = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    if sys.argv[4:] == ['--version']:
        print('fake harness ' + version)
        return 0
    if os.environ.get('KIT_CANARY_NONCE'):
        canary(out, 'guarded')
    else:
        session(out, actions)
    return 0


if __name__ == '__main__':
    sys.exit(main())

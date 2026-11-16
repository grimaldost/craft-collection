"""Shared builders for the tests of session facts and recorders.

Not a test module itself (no `test_` prefix): version 3 policies with recording
checkers, `kit` run in a child process under a state root of the test's own,
and a child process that holds one of the kit's lock files.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from kit_fixtures import SRC

RECEIPT_KEYS = ['kit_note_receipt', 'outcome', 'reason', 'recorders']

# A checker that records every note and returns its facts in its detail.
COUNTING = """\
import json


def check(act, observation, facts):
    return {"result": "match", "detail": json.dumps(facts, sort_keys=True)}


def record(note, facts):
    n = facts.get("n", 0) + 1
    return {"facts": {"n": n, "keys": sorted(note), "kind": note["note"]["kind"]}}
"""

PLAIN = """\
def check(act, observation):
    return {"result": "no-match"}
"""


def expect(holds: bool, detail: object) -> None:
    """Raise AssertionError with `detail` unless `holds`."""
    if not holds:
        raise AssertionError(detail)


def checker_table(cid: str, source: str, folder: Path, records=None, budget_ms=250) -> str:
    """Write the checker file `<cid>.py` into `folder`; return its `[[checker]]` table."""
    path = folder / f'{cid}.py'
    path.write_bytes(source.encode('utf-8'))
    text = (
        '[[checker]]\n'
        f'id = "{cid}"\n'
        f'file = "{cid}.py"\n'
        f'sha256 = "{hashlib.sha256(path.read_bytes()).hexdigest()}"\n'
        f'budget_ms = {budget_ms}\n'
    )
    if records is not None:
        text += f'records = {json.dumps(list(records))}\n'
    return text + '\n'


def deny_rule(rid: str, check: str) -> str:
    """A deny rule on shell acts whose only matcher is the checker `check`."""
    return (
        '[[rule]]\n'
        f'id = "{rid}"\n'
        'effect = "deny"\n'
        'governed = false\n'
        'kinds = ["shell"]\n'
        f'check = "{check}"\n'
        'reason = "from the checker"\n\n'
    )


def write_policy(folder: Path, tables: list[str], rules: list[str] = ()) -> Path:
    """A version 3 policy in `folder` with the given checker tables and rules."""
    policy = folder / 'policy.toml'
    policy.write_text('version = 3\n\n' + ''.join(tables) + ''.join(rules), encoding='utf-8')
    return policy


def env(root: Path | str, **extra: str) -> dict:
    """The environment of a `kit` child: no inherited `KIT_` variable, the state root given."""
    out = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    out.pop('PYTHONIOENCODING', None)
    out['PYTHONPATH'] = str(SRC)
    out['KIT_STATE_ROOT'] = str(root)
    out.update(extra)
    return out


def kit(stdin: bytes, *args: str, env: dict, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=timeout,
    )


def one_line(proc: subprocess.CompletedProcess) -> dict:
    """The one ASCII JSON line a `kit` child printed, which exited 0."""
    expect(proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr))
    out = proc.stdout
    expect(out.isascii() and out.endswith(b'\n'), out)
    lines = out.decode('ascii').splitlines()
    expect(len(lines) == 1, out)
    return json.loads(lines[0])


def note(data: bytes, *args: str, env: dict) -> dict:
    """Run `kit note`; return its receipt after checking its shape."""
    receipt = one_line(kit(data, 'note', *args, env=env))
    expect(list(receipt) == RECEIPT_KEYS, receipt)
    expect(receipt['kit_note_receipt'] == 1, receipt)
    return receipt


def judge(data: bytes, *args: str, env: dict) -> dict:
    return one_line(kit(data, 'judge', *args, env=env))


def results(receipt: dict) -> list[tuple[str, str]]:
    """The (id, result) pairs of a receipt's recorders, after checking each entry's keys."""
    for entry in receipt['recorders']:
        expect(list(entry) == ['id', 'result'], entry)
    return [(e['id'], e['result']) for e in receipt['recorders']]


_HOLDER = """\
import os, sys, time
sys.path.insert(0, sys.argv[1])
from harness_kit import state
path = sys.argv[2]
os.makedirs(os.path.dirname(path), exist_ok=True)
fd = state.open_lock(path)
while not state.acquire(fd, 1.0):
    pass
sys.stdout.write("locked\\n")
sys.stdout.flush()
time.sleep(float(sys.argv[3]))
state.release(fd)
os.close(fd)
"""


class LockHolder:
    """A child process that holds the kit lock file `path` for `seconds`."""

    def __init__(self, path: Path, seconds: float) -> None:
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [sys.executable, '-c', _HOLDER, str(SRC), str(path), str(seconds)],
            stdout=subprocess.PIPE,
            encoding='ascii',
        )
        line = self.proc.stdout.readline()
        expect(line == 'locked\n', line)
        self.since = time.monotonic()

    def wait(self) -> None:
        try:
            self.proc.wait(timeout=30)
        finally:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()
            self.proc.stdout.close()

#!/usr/bin/env python3
"""Checks of `kit judge --from NAME` and `kit note --from NAME`, end to end.

Contract under test:
- `--from opencode` reads one envelope and hands it to the opencode driver: the verdict printed and
  the journal line appended equal those `kit judge` gives on the neutral event the driver's
  translation stands for, inside a minted run; the same holds for `kit note` and its receipt and
  note line;
- an `execute.before` envelope naming the refused tool gets a governed deny with rule
  `opencode.refused-tool`, the policy file's SHA-256 and the driver's reason, journaled under the
  run, also under a policy whose first rule allows every act of kind `other`;
- a broken envelope, a name no driver has, a driver with no envelope translation and an envelope
  over 16 MiB are `unknown` (judge) or `invalid` (note); 8 MiB envelopes are judged and noted;
- without `--from` both commands read neutral documents as before.

Stdlib-runnable: `python test_judge_from.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import state
from kit_fixtures import SRC, run_module

LOC = os.path.abspath('/w')
PLACE = {'session': 'observed', 'parent': 'observed', 'root': 'observed', 'origin': 'unavailable'}
SESSION = {'id': 's1', 'parent_id': None, 'root_id': 's1'}
REASON = (
    'kit refuses this tool under kit run; remove a worktree with git in the shell, which kit judges'
)
MIB = 1024 * 1024
POLICY = """\
version = 1

[[rule]]
id = "no-secret"
effect = "deny"
governed = true
kinds = ["shell"]
command_regex = "secret"
reason = "no secrets"
"""
ALLOW_OTHER = """\
version = 1

[[rule]]
id = "allow-other"
effect = "allow"
governed = true
kinds = ["other"]
reason = "other acts are fine"
"""


def _env(root: Path, policy: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env.update(PYTHONPATH=str(SRC), KIT_STATE_ROOT=str(root), KIT_POLICY=str(policy), **extra)
    return env


def _kit(data: bytes, *args: str, env: dict) -> dict:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=data,
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, (args, proc.returncode, proc.stderr)
    lines = proc.stdout.decode('ascii').splitlines()
    assert len(lines) == 1, proc.stdout[:400]
    return json.loads(lines[0])


def _payload(e: dict) -> str:
    return json.dumps(e, separators=(',', ':'))


def envelope(e: dict, hook: str = 'execute.before', run_id: str | None = None, **over) -> bytes:
    env = {
        'kit_raw': 1,
        'hook': hook,
        'run_id': run_id,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': SESSION,
        'origin': 'unknown',
        'observation': PLACE,
        'location': LOC,
        'payload': _payload(e),
    }
    env.update(over)
    return json.dumps(env).encode('ascii')


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def neutral(e: dict, run_id: str | None, act: dict, command: str, paths: str) -> bytes:
    """The neutral event the shell built from `e` before the envelope."""
    ev = {
        'kit_event': 1,
        'run_id': run_id,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': SESSION,
        'origin': 'unknown',
        'observation': {**PLACE, 'command': command, 'paths': paths},
        'act': {'argv': None, 'cwd': LOC, 'payload_sha256': _sha(_payload(e)), **act},
    }
    return json.dumps(ev).encode('ascii')


class Run:
    """A state root with one minted opencode run and a policy file."""

    def __init__(self, text: str = POLICY):
        self.td = tempfile.TemporaryDirectory()
        base = Path(self.td.name)
        self.root = base / 'state'
        self.run_id, _ = state.mint_run(self.root, 'opencode')
        self.policy = base / 'policy.toml'
        self.policy.write_text(text, encoding='utf-8')
        self.env = _env(self.root, self.policy, KIT_RUN_ID=self.run_id)

    def close(self) -> None:
        self.td.cleanup()

    def lines(self, name: str = 'journal.ndjson') -> list[dict]:
        path = self.root / 'runs' / self.run_id / name
        if not path.exists():
            return []
        lines = [json.loads(x) for x in path.read_text(encoding='ascii').splitlines()]
        for line in lines:
            line.pop('ts_utc')
        return lines


def _same_as_neutral(e: dict, act: dict, command: str, paths: str) -> dict:
    run = Run()
    try:
        raw = _kit(envelope(e, run_id=run.run_id), 'judge', '--from', 'opencode', env=run.env)
        want = _kit(neutral(e, run.run_id, act, command, paths), 'judge', env=run.env)
        assert raw == want, (raw, want)
        first, second = run.lines()
        assert first == second, (first, second)
        return raw
    finally:
        run.close()


def test_a_shell_call_is_judged_as_its_neutral_event():
    for command, verdict in (('echo hi', 'allow'), ('cat secret', 'deny')):
        e = {'tool': 'shell', 'sessionID': 's1', 'input': {'command': command}}
        act = {'kind': 'shell', 'command': command, 'paths': []}
        v = _same_as_neutral(e, act, 'observed', 'not_applicable')
        assert v['verdict'] == verdict and v['launched'] is True, v


def test_a_write_and_another_tool_are_judged_as_their_neutral_events():
    e = {'tool': 'write', 'sessionID': 's1', 'input': {'path': 'a.txt', 'content': 'x'}}
    act = {'kind': 'file_write', 'command': None, 'paths': [os.path.join(LOC, 'a.txt')]}
    _same_as_neutral(e, act, 'not_applicable', 'observed')
    e = {'tool': 'grep', 'sessionID': 's1', 'input': {'pattern': 'x'}}
    act = {'kind': 'other', 'command': None, 'paths': []}
    _same_as_neutral(e, act, 'not_applicable', 'not_applicable')


def test_the_refused_tool_is_a_governed_deny_under_any_policy():
    for text in (POLICY, ALLOW_OTHER):
        run = Run(text)
        try:
            e = {'tool': 'opencode_worktree_remove', 'sessionID': 's1', 'input': {'force': True}}
            v = _kit(envelope(e, run_id=run.run_id), 'judge', '--from', 'opencode', env=run.env)
            policy_sha = hashlib.sha256(run.policy.read_bytes()).hexdigest()
            got = (v['verdict'], v['effect'], v['governed'], v['rule'], v['reason'])
            assert got == ('deny', 'deny', True, 'opencode.refused-tool', REASON), v
            assert v['policy_sha256'] == policy_sha and v['run_id'] == run.run_id, v
            (line,) = run.lines()
            assert (line['run_id'], line['rule'], line['effect']) == (
                run.run_id,
                'opencode.refused-tool',
                'deny',
            ), line
            assert line['act_kind'] == 'other' and line['harness'] == 'opencode', line
        finally:
            run.close()


def test_another_spelling_of_the_refused_tool_is_an_ordinary_other_act():
    run = Run(ALLOW_OTHER)
    try:
        e = {'tool': 'opencode.worktree_remove', 'sessionID': 's1', 'input': {}}
        v = _kit(envelope(e, run_id=run.run_id), 'judge', '--from', 'opencode', env=run.env)
        assert (v['verdict'], v['rule']) == ('allow', 'allow-other'), v
    finally:
        run.close()


def test_a_broken_envelope_or_harness_name_is_unknown():
    e = {'tool': 'shell', 'sessionID': 's1', 'input': {'command': 'echo hi'}}
    good = json.loads(envelope(e))
    run = Run()
    try:
        cases = [
            (b'{not json', 'opencode'),
            (json.dumps({**good, 'extra': 1}).encode(), 'opencode'),
            (json.dumps({**good, 'payload': '[]'}).encode(), 'opencode'),
            (json.dumps({**good, 'harness': {'name': 'x', 'version': None}}).encode(), 'opencode'),
            (json.dumps(good).encode(), 'claude-code'),
            (json.dumps(good).encode(), 'no-such-harness'),
        ]
        for data, name in cases:
            v = _kit(data, 'judge', '--from', name, env=run.env)
            assert (v['verdict'], v['effect'], v['governed']) == ('unknown', 'deny', True), v
            assert v['reason'].startswith('invalid event'), v
        assert len(run.lines()) == len(cases)
    finally:
        run.close()


def _big(hook: str, size: int) -> tuple[dict, bytes]:
    if hook == 'execute.before':
        e = {'tool': 'write', 'sessionID': 's1', 'input': {'path': 'a.txt', 'content': 'x' * size}}
    else:
        out = {'output': 'y' * size, 'exit': 0}
        e = {
            'tool': 'shell',
            'sessionID': 's1',
            'input': {'command': 'c'},
            'result': {'output': out},
        }
    return e, envelope(e, hook=hook)


def test_an_envelope_over_16_mib_is_unknown_or_invalid_and_8_mib_is_read():
    run = Run()
    try:
        _, data = _big('execute.before', 17 * MIB)
        v = _kit(data, 'judge', '--from', 'opencode', env=run.env)
        assert v['verdict'] == 'unknown' and v['reason'].startswith('invalid event'), v
        _, data = _big('execute.after', 17 * MIB)
        r = _kit(data, 'note', '--from', 'opencode', env=run.env)
        assert r['outcome'] == 'invalid', r
        _, data = _big('execute.before', 8 * MIB)
        assert len(data) > 8 * MIB
        v = _kit(data, 'judge', '--from', 'opencode', env=run.env)
        assert v['verdict'] == 'allow', v
        _, data = _big('execute.after', 8 * MIB)
        r = _kit(data, 'note', '--from', 'opencode', env=run.env)
        assert r['outcome'] == 'dropped', r
    finally:
        run.close()


def _note_doc(run_id: str, observation: dict, body: dict) -> bytes:
    doc = {
        'kit_note': 1,
        'run_id': run_id,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': SESSION,
        'origin': 'unknown',
        'observation': observation,
        'note': body,
    }
    return json.dumps(doc).encode('ascii')


def test_notes_give_the_receipt_and_line_of_their_neutral_note():
    prompt = {'sessionID': 's1', 'messageID': 'm', 'prompt': {'text': '"hello"', 'files': []}}
    after = {
        'tool': 'shell',
        'sessionID': 's1',
        'input': {'command': 'echo hi'},
        'status': 'completed',
        'result': {'output': {'output': 'hi\n', 'exit': 0}},
    }
    no_cmd = {'command': 'not_applicable', 'paths': 'not_applicable'}
    act = {
        'kind': 'shell',
        'command': 'echo hi',
        'argv': None,
        'paths': [],
        'cwd': LOC,
        'payload_sha256': _sha(_payload(after)),
    }
    cases = [
        (
            prompt,
            'prompt',
            {**PLACE, **no_cmd},
            {'kind': 'prompt', 'text': 'hello', 'truncated': False},
        ),
        (
            after,
            'execute.after',
            {**PLACE, 'command': 'observed', 'paths': 'not_applicable'},
            {
                'kind': 'outcome',
                'act': act,
                'status': 'completed',
                'output': 'hi\n',
                'truncated': False,
            },
        ),
    ]
    for e, hook, observation, body in cases:
        run = Run()
        try:
            raw = _kit(
                envelope(e, hook=hook, run_id=run.run_id), 'note', '--from', 'opencode', env=run.env
            )
            want = _kit(_note_doc(run.run_id, observation, body), 'note', env=run.env)
            assert raw == want and raw['outcome'] == 'dropped', (raw, want)
            first, second = run.lines('notes.ndjson')
            assert first == second, (first, second)
        finally:
            run.close()


def test_a_broken_note_envelope_is_invalid():
    run = Run()
    try:
        e = {'tool': 'shell', 'sessionID': 's1', 'input': {'command': 'echo hi'}}
        for data, name in ((envelope(e), 'opencode'), (b'[]', 'opencode'), (envelope(e), 'nope')):
            r = _kit(data, 'note', '--from', name, env=run.env)
            assert r['outcome'] == 'invalid', r
    finally:
        run.close()


if __name__ == '__main__':
    run_module(globals(), 'kit judge and kit note --from')

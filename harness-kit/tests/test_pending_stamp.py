#!/usr/bin/env python3
"""Checks of the pending-prompt stamp, end to end through `kit note` and `kit judge`.

Contract under test:
- a valid, launched prompt note with a root key and a recorder of `prompt`
  writes `runs/<id>/facts/<16 hex>/prompt.pending.json` before its first
  recorder runs, outside `facts.lock`, holding exactly
  `{"kit_pending": 1, "seq": N, "sha256": HEX}`: N the note's `time.time_ns()`,
  HEX the SHA-256 of the prompt's text;
- after the recorders the stamp is removed under `facts.lock` when every
  recorder answered `facts` or `unchanged` and the stamp still holds the
  note's own `seq`; it stays when a recorder did not, when the lock is not
  obtained in time, when the note is killed, and when the stamp holds another
  `seq`; a stamp that cannot be written leaves every recorder `failed`, uncalled;
- an outcome note writes no stamp, and its recorders see none;
- the receipt and the note's journal line keep their keys;
- while a stamp file stands for a root, readable or not, a judgement gives
  each checker that records `prompt` None facts, and every other checker its
  facts as before; a governed rule then cannot tell, so an act the earlier
  prompt allowed is `unknown` until a later prompt is recorded;
- a judgement writes, removes and creates no stamp: 50 of them leave its
  bytes and modification time as they were.

Stdlib-runnable: `python test_pending_stamp.py`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import facts_fixtures as ff
from harness_kit import cli, facts, state
from harness_kit.policy import load_policy
from kit_fixtures import event, run_module
from test_notes import OUTCOME, PROMPT

KEY = PROMPT['session']['id']
STAMP_KEYS = ['kit_pending', 'seq', 'sha256']
NOTE_LINE_KEYS = [
    'ts_utc',
    'run_id',
    'launched',
    'session_id',
    'harness',
    'note_kind',
    'status',
    'chars',
    'truncated',
    'content_sha256',
    'payload_sha256',
    'outcome',
    'reason',
    'recorders',
]

# Records the prompt; its `check` returns the facts it was given in its detail.
KEEPER = """\
import json


def check(act, observation, facts):
    return {"result": "match", "detail": json.dumps(facts, sort_keys=True)}


def record(note, facts):
    return {"facts": {"prompt": note["note"].get("text")}}
"""

# Allows an act only while the recorded prompt says "may act"; None facts cannot tell.
GATE = """\
def check(act, observation, facts):
    if not isinstance(facts, dict):
        return {"result": "cannot-tell"}
    return {"result": "no-match" if "may act" in facts.get("prompt", "") else "match"}


def record(note, facts):
    return {"facts": {"prompt": note["note"]["text"]}}
"""


def stamp_path(root: Path, run_id: str, key: str = KEY) -> Path:
    """The stamp's place as the contract states it, built here without the kit's helpers."""
    folder = hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]
    return root / 'runs' / run_id / 'facts' / folder / 'prompt.pending.json'


def _spy(spy: Path, stamp: Path, tail: str) -> str:
    """A recorder that appends what it finds at `stamp` (a document or "absent") to `spy`."""
    return (
        'import json\n\n\n'
        'def check(act, observation, facts):\n'
        '    return {"result": "no-match"}\n\n\n'
        'def record(note, facts):\n'
        '    try:\n'
        f'        with open({str(stamp)!r}, "rb") as fh:\n'
        '            seen = json.loads(fh.read())\n'
        '    except FileNotFoundError:\n'
        '        seen = "absent"\n'
        f'    with open({str(spy)!r}, "a") as fh:\n'
        '        fh.write(json.dumps(seen) + "\\n")\n' + tail
    )


def _seen(spy: Path) -> list:
    return [json.loads(x) for x in spy.read_text(encoding='utf-8').splitlines()]


def _gate_rule(rid: str, check: str) -> str:
    return (
        '[[rule]]\n'
        f'id = "{rid}"\n'
        'effect = "deny"\n'
        'governed = true\n'
        'kinds = ["shell"]\n'
        f'check = "{check}"\n'
        'reason = "from the gate"\n\n'
    )


def _setup(base: Path, checkers, rules=()):
    """A state root with a minted run and a version 3 policy; (root, run_id, env, policy)."""
    root = base / 'state'
    run_id, _ = state.mint_run(root, 'claude-code')
    tables = [ff.checker_table(cid, src, base, rec, budget) for cid, src, rec, budget in checkers]
    policy = ff.write_policy(base, tables, list(rules))
    return root, run_id, ff.env(root, KIT_POLICY=str(policy), KIT_RUN_ID=run_id), policy


def _prompt(text: str) -> bytes:
    note = copy.deepcopy(PROMPT)
    note['note']['text'] = text
    return json.dumps(note).encode('utf-8')


def _act() -> bytes:
    return json.dumps(event(**{'session.id': KEY})).encode('utf-8')


def _note_lines(root: Path, run_id: str) -> list[dict]:
    text = (root / 'runs' / run_id / 'notes.ndjson').read_text(encoding='ascii')
    return [json.loads(x) for x in text.splitlines()]


def test_a_prompt_note_stamps_before_its_recorder_and_removes_the_stamp_after():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'claude-code')
        stamp, spy = stamp_path(root, run_id), base / 'spy.ndjson'
        source = _spy(spy, stamp, '    return {"facts": {"seen": 1}}\n')
        tables = [ff.checker_table('spy', source, base, ['prompt'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        text = 'Run the scripted tool call. Pode editar o CLAUDE.md.'
        before = time.time_ns()
        receipt = ff.note(_prompt(text), env=env)
        after = time.time_ns()
        assert (receipt['outcome'], ff.results(receipt)) == ('recorded', [('spy', 'facts')])
        [seen] = _seen(spy)
        assert isinstance(seen, dict) and list(seen) == STAMP_KEYS, seen
        assert seen['kit_pending'] == 1, seen
        assert type(seen['seq']) is int and before <= seen['seq'] <= after, (before, seen, after)
        assert seen['sha256'] == hashlib.sha256(text.encode('utf-8')).hexdigest(), seen
        assert not stamp.exists(), 'the stamp of a recorded prompt stayed'


def test_the_stamp_is_written_as_write_json_atomic_writes_it():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'claude-code')
        stamp = stamp_path(root, run_id)
        copier = (
            'import shutil\n\n\n'
            'def check(act, observation, facts):\n'
            '    return {"result": "no-match"}\n\n\n'
            'def record(note, facts):\n'
            f'    shutil.copyfile({str(stamp)!r}, {str(base / "copy.json")!r})\n'
            '    return {"result": "unchanged"}\n'
        )
        tables = [ff.checker_table('copier', copier, base, ['prompt'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        assert ff.results(ff.note(_prompt('hello'), env=env)) == [('copier', 'unchanged')]
        data = (base / 'copy.json').read_bytes()
        assert data == state.json_bytes(json.loads(data)), data
        assert not stamp.exists()


def test_the_stamp_stays_when_a_prompt_recorder_fails():
    with tempfile.TemporaryDirectory() as td:
        failing = ff.PLAIN + '\n\ndef record(note, facts):\n    raise RuntimeError("no")\n'
        root, run_id, env, _ = _setup(
            Path(td),
            [('keeper', KEEPER, ['prompt'], 250), ('broken', failing, ['prompt'], 250)],
        )
        receipt = ff.note(_prompt('a prompt'), env=env)
        assert ff.results(receipt) == [('keeper', 'facts'), ('broken', 'failed')], receipt
        doc = json.loads(stamp_path(root, run_id).read_bytes())
        assert list(doc) == STAMP_KEYS and doc['kit_pending'] == 1, doc
        assert doc['sha256'] == hashlib.sha256(b'a prompt').hexdigest(), doc


def test_the_stamp_is_written_outside_the_facts_lock_and_stays_when_the_lock_is_held():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'claude-code')
        stamp, spy = stamp_path(root, run_id), base / 'spy.ndjson'
        source = _spy(spy, stamp, '    return {"result": "unchanged"}\n')
        tables = [ff.checker_table('spy', source, base, ['prompt'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        holder = ff.LockHolder(facts.lock_path(root, run_id), 4.0)
        try:
            receipt = ff.note(_prompt('held'), env=env)
            assert holder.proc.poll() is None, 'the facts lock was released during the note'
        finally:
            holder.wait()
        assert ff.results(receipt) == [('spy', 'unchanged')], receipt
        [seen] = _seen(spy)
        assert isinstance(seen, dict) and list(seen) == STAMP_KEYS, seen
        assert json.loads(stamp.read_bytes()) == seen, 'the stamp left is not the note own'


def test_a_stamp_holding_another_seq_is_left_in_place():
    for delta in (1, -1):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / 'state'
            run_id, _ = state.mint_run(root, 'claude-code')
            stamp = stamp_path(root, run_id)
            swap = (
                'import json, os\n\n\n'
                'def check(act, observation, facts):\n'
                '    return {"result": "no-match"}\n\n\n'
                'def record(note, facts):\n'
                f'    path = {str(stamp)!r}\n'
                '    with open(path, "rb") as fh:\n'
                '        doc = json.loads(fh.read())\n'
                f'    with open({str(base / "own.json")!r}, "w") as fh:\n'
                '        json.dump(doc, fh)\n'
                f'    doc["seq"] += {delta}\n'
                '    with open(path + ".swap", "w") as fh:\n'
                '        json.dump(doc, fh)\n'
                '    os.replace(path + ".swap", path)\n'
                '    return {"facts": {"swapped": True}}\n'
            )
            tables = [ff.checker_table('swap', swap, base, ['prompt'])]
            env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
            assert ff.results(ff.note(_prompt('swap'), env=env)) == [('swap', 'facts')]
            own = json.loads((base / 'own.json').read_bytes())
            assert json.loads(stamp.read_bytes()) == dict(own, seq=own['seq'] + delta), delta


def test_a_stamp_rewritten_with_the_note_own_seq_is_removed():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'claude-code')
        stamp = stamp_path(root, run_id)
        rewrite = (
            'import json, os\n\n\n'
            'def check(act, observation, facts):\n'
            '    return {"result": "no-match"}\n\n\n'
            'def record(note, facts):\n'
            f'    path = {str(stamp)!r}\n'
            '    with open(path, "rb") as fh:\n'
            '        doc = json.loads(fh.read())\n'
            '    with open(path + ".swap", "w") as fh:\n'
            '        json.dump(doc, fh, separators=(",", ":"))\n'
            '    os.replace(path + ".swap", path)\n'
            '    return {"result": "unchanged"}\n'
        )
        tables = [ff.checker_table('rewrite', rewrite, base, ['prompt'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        assert ff.results(ff.note(_prompt('same seq'), env=env)) == [('rewrite', 'unchanged')]
        assert not stamp.exists()


def test_a_stamp_that_cannot_be_written_leaves_every_recorder_failed_and_uncalled():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        marker = base / 'called.marker'
        body = f'    open({str(marker)!r}, "w").close()\n    return {{"facts": {{}}}}\n'
        source = ff.PLAIN + '\n\ndef record(note, facts):\n' + body
        root, run_id, env, _ = _setup(base, [('rec', source, ['prompt'], 250)])
        stamp_path(root, run_id).mkdir(parents=True)
        receipt = ff.note(_prompt('blocked'), env=env)
        assert (receipt['outcome'], ff.results(receipt)) == ('recorded', [('rec', 'failed')])
        assert not marker.exists(), 'a recorder ran without a stamp'
        assert stamp_path(root, run_id).is_dir()


def test_an_outcome_note_writes_no_stamp():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'opencode')
        key = OUTCOME['session']['root_id']
        stamp, spy = stamp_path(root, run_id, key), base / 'spy.ndjson'
        source = _spy(spy, stamp, '    return {"facts": {"n": 1}}\n')
        tables = [ff.checker_table('both', source, base, ['prompt', 'outcome'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        receipt = ff.note(json.dumps(OUTCOME).encode('utf-8'), env=env)
        assert ff.results(receipt) == [('both', 'facts')], receipt
        assert _seen(spy) == ['absent']
        assert not stamp.exists()


def test_the_journal_line_keeps_its_keys():
    with tempfile.TemporaryDirectory() as td:
        failing = ff.PLAIN + '\n\ndef record(note, facts):\n    raise RuntimeError("no")\n'
        root, run_id, env, _ = _setup(
            Path(td), [('keeper', KEEPER, ['prompt'], 250), ('broken', failing, ['outcome'], 250)]
        )
        ff.note(_prompt('kept'), env=env)
        ff.note(json.dumps(OUTCOME).encode('utf-8'), env=env)
        lines = _note_lines(root, run_id)
        assert [list(x) for x in lines] == [NOTE_LINE_KEYS] * 2, lines


def test_a_killed_note_leaves_its_stamp_and_the_act_unknown():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        slow = GATE.replace(
            'def record(note, facts):\n',
            'def record(note, facts):\n    import time\n    time.sleep(0.4)\n',
        )
        root, run_id, env, _ = _setup(
            base, [('gate', GATE, ['prompt'], 250)], [_gate_rule('owner', 'gate')]
        )
        assert ff.note(_prompt('you may act'), env=env)['outcome'] == 'recorded'
        assert ff.judge(_act(), env=env)['verdict'] == 'allow'
        other = base / 'slow'
        other.mkdir()
        slow_policy = ff.write_policy(
            other,
            [ff.checker_table('gate', slow, other, ['prompt'], 450)],
            [_gate_rule('owner', 'gate')],
        )
        slow_env = dict(env, KIT_POLICY=str(slow_policy))
        stamp = stamp_path(root, run_id)
        proc = subprocess.Popen(
            [sys.executable, '-m', 'harness_kit', 'note'],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=slow_env,
        )
        try:
            proc.stdin.write(_prompt('stop now'))
            proc.stdin.close()
            end = time.monotonic() + 30
            while not stamp.exists():
                assert proc.poll() is None and time.monotonic() < end, 'no stamp before the end'
                time.sleep(0.002)
            proc.kill()
        finally:
            proc.wait(timeout=30)
        assert stamp.exists(), 'the stamp of a killed note is gone'
        verdict = ff.judge(_act(), env=env)
        assert (verdict['verdict'], verdict['rule']) == ('unknown', 'owner'), verdict


def test_a_failed_prompt_denies_the_act_until_a_later_prompt_is_recorded():
    with tempfile.TemporaryDirectory() as td:
        root, run_id, env, _ = _setup(
            Path(td), [('gate', GATE, ['prompt'], 250)], [_gate_rule('owner', 'gate')]
        )
        assert ff.results(ff.note(_prompt('you may act'), env=env)) == [('gate', 'facts')]
        assert ff.judge(_act(), env=env)['verdict'] == 'allow'
        holder = ff.LockHolder(facts.lock_path(root, run_id), 4.0)
        try:
            receipt = ff.note(_prompt('another thing'), env=env)
        finally:
            holder.wait()
        assert ff.results(receipt) == [('gate', 'failed')], receipt
        assert stamp_path(root, run_id).exists()
        verdict = ff.judge(_act(), env=env)
        assert (verdict['verdict'], verdict['rule']) == ('unknown', 'owner'), verdict
        assert ff.results(ff.note(_prompt('nothing more'), env=env)) == [('gate', 'facts')]
        assert not stamp_path(root, run_id).exists()
        verdict = ff.judge(_act(), env=env)
        assert (verdict['verdict'], verdict['rule']) == ('deny', 'owner'), verdict
        assert ff.note(_prompt('now you may act'), env=env)['outcome'] == 'recorded'
        assert ff.judge(_act(), env=env)['verdict'] == 'allow'


def _write_stamp(root: Path, run_id: str, data: bytes) -> Path:
    path = stamp_path(root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_a_judgement_gives_prompt_recorders_none_while_any_stamp_file_stands():
    stamps = (
        state.json_bytes({'kit_pending': 1, 'seq': 1, 'sha256': '0' * 64}),
        b'not json',
        b'',
    )
    for data in stamps:
        with tempfile.TemporaryDirectory() as td:
            root, run_id, _, _ = _setup(
                Path(td),
                [
                    ('p', KEEPER, ['prompt'], 250),
                    ('o', KEEPER, ['outcome'], 250),
                    ('b', KEEPER, ['prompt', 'outcome'], 250),
                ],
            )
            for cid in ('p', 'o', 'b'):
                path = facts.facts_path(root, run_id, KEY, cid)
                path.parent.mkdir(parents=True, exist_ok=True)
                state.write_json_atomic(path, facts.document({'prompt': cid}))
            read = facts.judge_reader(root, run_id, KEY, ('p', 'b'))
            assert [read(c) for c in ('p', 'o', 'b')] == [{'prompt': c} for c in 'pob']
            _write_stamp(root, run_id, data)
            assert [read(c) for c in ('p', 'o', 'b')] == [None, {'prompt': 'o'}, None], data
            other = facts.judge_reader(root, run_id, 'another-root', ('p', 'b'))
            assert other('p') == {}, 'a stamp of one root reached another'


def test_kit_judge_learns_the_prompt_recorders_from_the_policy():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        rules = [ff.deny_rule('by-p', 'p'), ff.deny_rule('by-o', 'o')]
        root, run_id, env, _ = _setup(
            base, [('p', KEEPER, ['prompt'], 250), ('o', KEEPER, ['outcome'], 250)], rules
        )
        assert ff.judge(_act(), env=env)['reason'].startswith('{} '), 'before any stamp'
        _write_stamp(root, run_id, b'{')
        assert ff.judge(_act(), env=env)['reason'].startswith('null '), 'prompt recorder'
        other = base / 'only-outcome'
        other.mkdir()
        only_o = ff.write_policy(
            other, [ff.checker_table('o', KEEPER, other, ['outcome'])], [ff.deny_rule('by-o', 'o')]
        )
        verdict = ff.judge(_act(), env=dict(env, KIT_POLICY=str(only_o)))
        assert verdict['reason'].startswith('{} '), verdict


def test_fifty_judgements_leave_the_stamp_as_it_was():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        failing = KEEPER.replace('return {"facts"', 'raise RuntimeError("no")  #')
        root, run_id, env, policy = _setup(
            base,
            [('keeper', KEEPER, ['prompt'], 250), ('broken', failing, ['prompt'], 250)],
            [ff.deny_rule('by-keeper', 'keeper')],
        )
        ff.note(_prompt('pending'), env=env)
        stamp = stamp_path(root, run_id)
        folder = root / 'runs' / run_id / 'facts'
        before = (stamp.read_bytes(), stamp.stat().st_mtime_ns, sorted(os.listdir(stamp.parent)))
        listing = sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*'))
        loaded = load_policy(policy)
        for _ in range(48):
            verdict = cli.judge_and_journal(_act(), loaded, env)
            assert verdict['reason'].startswith('null '), verdict
        for _ in range(2):
            assert ff.judge(_act(), env=env)['reason'].startswith('null ')
        after = (stamp.read_bytes(), stamp.stat().st_mtime_ns, sorted(os.listdir(stamp.parent)))
        assert after == before, (before, after)
        assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*')) == listing


if __name__ == '__main__':
    run_module(globals(), 'pending-prompt stamp')

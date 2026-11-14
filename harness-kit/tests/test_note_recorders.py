#!/usr/bin/env python3
"""Checks of `kit note` with recorders: the facts a note leaves, end to end.

Contract under test:
- the recorders are the policy's checkers whose `records` holds the note's
  kind, in the policy's order; none gives `dropped`, `no-recorder`; a note
  with no root key gives `dropped`, `no-root`;
- each recorder gets one result, `facts`, `unchanged`, `failed`, `skipped`,
  `too-large` or `conflict`, listed as `{"id", "result"}` in the receipt and
  in the journal line, and the note's outcome is `recorded`;
- `record(note, facts)` gets copies of the note without `run_id` and
  `session`, and of the facts read; a raise, `sys.exit`, a return of any
  other shape, a value that does not survive JSON, or a wait that ends first
  is `failed`; a recorder is skipped once less than 50 ms of the note's
  500 ms is left;
- a value whose file would pass 65536 bytes is `too-large` and the file stays
  as it was; a file that changes between the read and the compare twice is a
  `conflict` and nothing is written;
- the receipt is the only line on standard output whatever a recorder prints,
  and the exit status is 0;
- two notes at once leave a file that parses; a held journal lock does not
  stop the facts file from being replaced; a held `facts.lock` makes the
  recorder `failed`;
- no facts exist outside a minted run, and the journal holds no text.

Stdlib-runnable: `python test_note_recorders.py`.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import facts_fixtures as ff
from harness_kit import facts, notes, state
from harness_kit.policy import load_policy
from kit_fixtures import run_module
from test_notes import OUTCOME, PROMPT

ROOT_KEY = OUTCOME['session']['root_id']


def _setup(base: Path, *checkers: tuple[str, str, object, int]):
    """A state root with a minted run and a version 3 policy of the given checkers."""
    root = base / 'state'
    run_id, _ = state.mint_run(root, 'opencode')
    tables = [ff.checker_table(cid, src, base, rec, budget) for cid, src, rec, budget in checkers]
    policy = ff.write_policy(base, tables)
    return root, run_id, ff.env(root, KIT_POLICY=str(policy), KIT_RUN_ID=run_id)


def _bytes(note: dict) -> bytes:
    return json.dumps(note).encode('utf-8')


def _note_lines(root: Path, run_id: str) -> list[dict]:
    text = (root / 'runs' / run_id / 'notes.ndjson').read_text(encoding='ascii')
    return [json.loads(x) for x in text.splitlines()]


def _record(body: str) -> str:
    return ff.PLAIN + '\n\ndef record(note, facts):\n' + body


def test_a_recorder_records_and_the_next_note_sees_its_facts():
    with tempfile.TemporaryDirectory() as td:
        root, run_id, env = _setup(Path(td), ('counting', ff.COUNTING, ['outcome'], 250))
        receipt = ff.note(_bytes(OUTCOME), env=env)
        assert (receipt['outcome'], receipt['reason']) == ('recorded', None), receipt
        assert ff.results(receipt) == [('counting', 'facts')]
        path = facts.facts_path(root, run_id, ROOT_KEY, 'counting')
        assert facts.read(path) == {
            'n': 1,
            'keys': ['harness', 'kit_note', 'note', 'observation', 'origin'],
            'kind': 'outcome',
        }
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('counting', 'facts')]
        assert facts.read(path)['n'] == 2
        lines = _note_lines(root, run_id)
        assert [(x['outcome'], x['reason'], x['recorders']) for x in lines] == [
            ('recorded', None, [{'id': 'counting', 'result': 'facts'}])
        ] * 2, lines


def test_unchanged_leaves_no_file():
    with tempfile.TemporaryDirectory() as td:
        body = '    return {"result": "unchanged"}\n'
        root, run_id, env = _setup(Path(td), ('same', _record(body), ['outcome'], 250))
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('same', 'unchanged')]
        assert not (root / 'runs' / run_id / 'facts').exists()


def test_the_recorders_are_the_checkers_that_record_the_kind_in_order():
    with tempfile.TemporaryDirectory() as td:
        unchanged = _record('    return {"result": "unchanged"}\n')
        _, _, env = _setup(
            Path(td),
            ('b-out', unchanged, ['outcome'], 250),
            ('plain', ff.PLAIN, None, 250),
            ('a-prompt', unchanged, ['prompt'], 250),
            ('c-both', unchanged, ['prompt', 'outcome'], 250),
        )
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [
            ('b-out', 'unchanged'),
            ('c-both', 'unchanged'),
        ]
        assert ff.results(ff.note(_bytes(PROMPT), env=env)) == [
            ('a-prompt', 'unchanged'),
            ('c-both', 'unchanged'),
        ]


def test_no_recorder_for_the_kind_and_no_root_are_dropped():
    with tempfile.TemporaryDirectory() as td:
        marker = Path(td) / 'loaded.marker'
        source = f'open({str(marker)!r}, "w").close()\n' + _record('    return None\n')
        root, run_id, env = _setup(Path(td), ('only-prompt', source, ['prompt'], 250))
        receipt = ff.note(_bytes(OUTCOME), env=env)
        assert (receipt['outcome'], receipt['reason'], receipt['recorders']) == (
            'dropped',
            'no-recorder',
            [],
        )
        nobody = copy.deepcopy(PROMPT)
        nobody['session']['id'] = None
        receipt = ff.note(_bytes(nobody), env=env)
        assert (receipt['outcome'], receipt['reason']) == ('dropped', 'no-root'), receipt
        unseen = copy.deepcopy(PROMPT)
        unseen['observation']['session'] = 'unavailable'
        assert ff.note(_bytes(unseen), env=env)['reason'] == 'no-root'
        lines = _note_lines(root, run_id)
        assert [x['reason'] for x in lines] == ['no-recorder', 'no-root', 'no-root'], lines
        assert not marker.exists(), 'a checker was loaded'
        assert not (root / 'runs' / run_id / 'facts').exists()


FAILING = {
    'raises': '    raise RuntimeError("no")\n',
    'exits': '    import sys\n    sys.exit(3)\n',
    'a-list': '    return [1]\n',
    'facts-list': '    return {"facts": [1]}\n',
    'nan': '    return {"facts": {"x": float("nan")}}\n',
    'tuple': '    return {"facts": {"x": (1, 2)}}\n',
    'extra-key': '    return {"facts": {}, "result": "unchanged"}\n',
    'slow': '    import time\n    time.sleep(2)\n    return {"result": "unchanged"}\n',
}


def test_each_bad_recorder_is_failed_and_writes_nothing():
    for name, body in FAILING.items():
        with tempfile.TemporaryDirectory() as td:
            root, run_id, env = _setup(Path(td), (name, _record(body), ['outcome'], 100))
            receipt = ff.note(_bytes(OUTCOME), env=env)
            assert ff.results(receipt) == [(name, 'failed')], receipt
            assert receipt['outcome'] == 'recorded', receipt
            assert not (root / 'runs' / run_id / 'facts').exists(), name


def test_a_checker_that_does_not_load_is_failed():
    with tempfile.TemporaryDirectory() as td:
        source = 'raise SystemExit(1)\n' + _record('    return None\n')
        _, _, env = _setup(Path(td), ('broken', source, ['outcome'], 100))
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('broken', 'failed')]


def test_an_unreadable_facts_file_is_failed_and_the_recorder_not_called():
    with tempfile.TemporaryDirectory() as td:
        marker = Path(td) / 'called.marker'
        body = f'    open({str(marker)!r}, "w").close()\n    return {{"facts": {{}}}}\n'
        root, run_id, env = _setup(Path(td), ('rec', _record(body), ['outcome'], 250))
        path = facts.facts_path(root, run_id, ROOT_KEY, 'rec')
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{"kit_facts": 2, "facts": {}}')
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('rec', 'failed')]
        assert not marker.exists()
        assert path.read_bytes() == b'{"kit_facts": 2, "facts": {}}'


def test_a_third_recorder_is_skipped_after_two_that_sleep():
    with tempfile.TemporaryDirectory() as td:
        sleep = _record('    import time\n    time.sleep(1)\n    return {"result": "unchanged"}\n')
        fast = _record('    return {"facts": {"ok": 1}}\n')
        root, run_id, env = _setup(
            Path(td),
            ('one', sleep, ['outcome'], 250),
            ('two', sleep, ['outcome'], 250),
            ('three', fast, ['outcome'], 250),
        )
        start = time.monotonic()
        receipt = ff.note(_bytes(OUTCOME), env=env)
        assert ff.results(receipt) == [('one', 'failed'), ('two', 'failed'), ('three', 'skipped')]
        assert time.monotonic() - start < 5
        assert not (root / 'runs' / run_id / 'facts').exists()


def test_the_budget_is_spent_only_by_record_calls():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        fast = _record('    return {"facts": {"n": 1}}\n')
        tables = [ff.checker_table(f'r{n}', fast, base, ['outcome']) for n in range(3)]
        policy = load_policy(ff.write_policy(base, tables))
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'opencode')
        real = facts.compare_and_replace

        def slow_replace(*args, **kwargs):
            time.sleep(0.3)
            return real(*args, **kwargs)

        facts.compare_and_replace = slow_replace
        try:
            out = notes.record_note(OUTCOME, policy.checkers, root, run_id, ROOT_KEY)
        finally:
            facts.compare_and_replace = real
        assert out == [{'id': f'r{n}', 'result': 'facts'} for n in range(3)], out


def test_too_large_leaves_the_file_as_it_was():
    with tempfile.TemporaryDirectory() as td:
        body = (
            '    if facts:\n'
            '        return {"facts": {"x": "a" * 65537}}\n'
            '    return {"facts": {"first": True}}\n'
        )
        root, run_id, env = _setup(Path(td), ('big', _record(body), ['outcome'], 250))
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('big', 'facts')]
        path = facts.facts_path(root, run_id, ROOT_KEY, 'big')
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('big', 'too-large')]
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_a_recorder_that_rewrites_its_own_file_is_a_conflict():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'opencode')
        path = facts.facts_path(root, run_id, ROOT_KEY, 'racer')
        body = (
            '    import json, os, time\n'
            f'    path = {str(path)!r}\n'
            '    os.makedirs(os.path.dirname(path), exist_ok=True)\n'
            '    doc = {"kit_facts": 1, "facts": {"other": time.monotonic_ns()}}\n'
            '    with open(path, "w") as fh:\n'
            '        json.dump(doc, fh)\n'
            '    return {"facts": {"mine": 1}}\n'
        )
        tables = [ff.checker_table('racer', _record(body), base, ['outcome'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('racer', 'conflict')]
        assert 'mine' not in facts.read(path), facts.read(path)


def test_a_file_changed_into_unreadable_bytes_under_the_recorder_is_a_conflict():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'opencode')
        path = facts.facts_path(root, run_id, ROOT_KEY, 'scribble')
        body = (
            '    import os, time\n'
            f'    path = {str(path)!r}\n'
            '    os.makedirs(os.path.dirname(path), exist_ok=True)\n'
            '    with open(path, "w") as fh:\n'
            '        fh.write(str(time.monotonic_ns()))\n'
            '    return {"facts": {"mine": 1}}\n'
        )
        tables = [ff.checker_table('scribble', _record(body), base, ['outcome'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('scribble', 'conflict')]
        assert facts.read(path) is None


def test_one_change_between_read_and_compare_calls_record_again_on_the_new_facts():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id, _ = state.mint_run(root, 'opencode')
        path = facts.facts_path(root, run_id, ROOT_KEY, 'once')
        body = (
            '    import json, os\n'
            f'    path = {str(path)!r}\n'
            '    if not facts:\n'
            '        os.makedirs(os.path.dirname(path), exist_ok=True)\n'
            '        with open(path, "w") as fh:\n'
            '            json.dump({"kit_facts": 1, "facts": {"other": 1}}, fh)\n'
            '    return {"facts": dict(facts, mine=sorted(facts))}\n'
        )
        tables = [ff.checker_table('once', _record(body), base, ['outcome'])]
        env = ff.env(root, KIT_POLICY=str(ff.write_policy(base, tables)), KIT_RUN_ID=run_id)
        assert ff.results(ff.note(_bytes(OUTCOME), env=env)) == [('once', 'facts')]
        assert facts.read(path) == {'other': 1, 'mine': ['other']}, facts.read(path)


def test_the_receipt_is_the_only_line_whatever_a_recorder_prints():
    with tempfile.TemporaryDirectory() as td:
        noisy = (
            'import os, sys\n'
            'print("loaded")\n'
            'sys.stderr.write("loaded err\\n")\n' + ff.PLAIN + '\n\ndef record(note, facts):\n'
            '    print("out")\n'
            '    sys.stderr.write("err\\n")\n'
            '    os.write(1, b"fd1\\n")\n'
            '    os.write(2, b"fd2\\n")\n'
            '    return {"facts": {"ok": 1}}\n'
        )
        _, _, env = _setup(Path(td), ('noisy', noisy, ['outcome'], 250))
        proc = ff.kit(_bytes(OUTCOME), 'note', env=env)
        receipt = ff.one_line(proc)
        assert ff.results(receipt) == [('noisy', 'facts')], receipt


def test_two_notes_at_once_leave_a_file_that_parses():
    with tempfile.TemporaryDirectory() as td:
        root, run_id, env = _setup(Path(td), ('counting', ff.COUNTING, ['outcome'], 250))
        procs = [
            subprocess.Popen(
                [sys.executable, '-m', 'harness_kit', 'note'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            for _ in range(2)
        ]
        outs = [p.communicate(_bytes(OUTCOME), timeout=60) for p in procs]
        for proc, (out, _) in zip(procs, outs, strict=True):
            assert proc.returncode == 0, out
            receipt = json.loads(out)
            assert receipt['outcome'] == 'recorded', receipt
        value = facts.read(facts.facts_path(root, run_id, ROOT_KEY, 'counting'))
        assert isinstance(value, dict) and value['n'] in (1, 2), value


def test_a_held_journal_lock_does_not_stop_the_facts_replace():
    with tempfile.TemporaryDirectory() as td:
        root, run_id, env = _setup(Path(td), ('counting', ff.COUNTING, ['outcome'], 250))
        holder = ff.LockHolder(root / 'runs' / run_id / state.JOURNAL_LOCK, 4.0)
        try:
            receipt = ff.note(_bytes(OUTCOME), env=env)
            assert holder.proc.poll() is None, 'the journal lock was released during the note'
        finally:
            holder.wait()
        assert receipt['outcome'] == 'failed', receipt
        assert facts.read(facts.facts_path(root, run_id, ROOT_KEY, 'counting'))['n'] == 1


def test_a_held_facts_lock_makes_the_recorder_failed():
    with tempfile.TemporaryDirectory() as td:
        root, run_id, env = _setup(Path(td), ('counting', ff.COUNTING, ['outcome'], 250))
        holder = ff.LockHolder(facts.lock_path(root, run_id), 5.0)
        try:
            receipt = ff.note(_bytes(OUTCOME), env=env)
            assert holder.proc.poll() is None, 'the facts lock was released during the note'
        finally:
            holder.wait()
        assert ff.results(receipt) == [('counting', 'failed')], receipt
        assert not facts.facts_path(root, run_id, ROOT_KEY, 'counting').exists()


def test_no_facts_outside_a_minted_run_and_no_text_in_the_journal():
    planted = 'planted-output-91c2ab'
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root, _, env = _setup(base, ('counting', ff.COUNTING, ['outcome', 'prompt'], 250))
        outside = dict(env)
        outside.pop('KIT_RUN_ID')
        forged = dict(env, KIT_RUN_ID='20261113T120000Z-0123456789ab')
        note = copy.deepcopy(OUTCOME)
        note['note']['output'] = planted
        for e in (outside, forged):
            assert ff.note(_bytes(note), env=e)['outcome'] == 'outside-run'
        assert list(root.rglob('facts')) == []
        assert ff.note(_bytes(note), env=env)['outcome'] == 'recorded'
        for path in root.rglob('*.ndjson'):
            assert planted.encode() not in path.read_bytes(), path


if __name__ == '__main__':
    run_module(globals(), 'kit note with recorders')

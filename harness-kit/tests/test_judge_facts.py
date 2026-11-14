#!/usr/bin/env python3
"""Checks of a judgement that hands a recording checker its session facts.

Contract under test:
- `verdict.judge` and `verdict.judge_bytes` take a keyword `facts`, a function
  from a checker id to its facts or None; a recording checker is called as
  `check(act, observation, facts)` with a deep copy, a checker without
  `records` as `check(act, observation)`;
- facts are read once per checker per judgement, before the checker's wait
  starts, and the read does not count against its budget;
- `kit judge` passes None outside a run and with no root key, `{}` in a run
  with nothing recorded, and the recorded value after a note;
- judgements write no facts and create nothing: the facts folder keeps its
  bytes and modification times after 50 of them;
- a judgement takes no lock on facts: with `facts.lock` held by another
  process, `kit judge` returns its verdict before the lock is released.

Stdlib-runnable: `python test_judge_facts.py`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import facts_fixtures as ff
from harness_kit import cli, facts, state
from harness_kit.policy import load_policy
from harness_kit.verdict import judge, judge_bytes
from kit_fixtures import event, run_module
from test_notes import OUTCOME

SEEN = """\
import json


def check(act, observation, facts):
    seen = json.loads(json.dumps(facts))
    if isinstance(facts, dict):
        facts["mutated"] = True
    return {"result": "match", "detail": json.dumps(seen, sort_keys=True)}


def record(note, facts):
    return {"result": "unchanged"}
"""

TWO_ARGS = """\
def check(act, observation):
    return {"result": "match", "detail": "two"}
"""


def _policy(folder: Path, *rules: tuple[str, str, object]):
    """A loaded version 3 policy: one deny rule per (rule id, checker source, records)."""
    tables, rule_text = [], []
    for n, (rid, source, records) in enumerate(rules):
        cid = f'c{n}'
        tables.append(ff.checker_table(cid, source, folder, records))
        rule_text.append(ff.deny_rule(rid, cid))
    return load_policy(ff.write_policy(folder, tables, rule_text))


def test_a_recording_checker_receives_a_copy_of_its_facts():
    with tempfile.TemporaryDirectory() as td:
        policy = _policy(Path(td), ('seen', SEEN, ['outcome']))
        store = {'c0': {'urls': ['u1']}}
        verdict = judge(event(), policy, True, facts=lambda cid: store[cid])
        assert verdict['verdict'] == 'deny', verdict
        assert verdict['reason'].startswith('{"urls": ["u1"]} '), verdict
        assert store == {'c0': {'urls': ['u1']}}, store


def test_without_a_facts_function_a_recording_checker_receives_none():
    with tempfile.TemporaryDirectory() as td:
        policy = _policy(Path(td), ('seen', SEEN, ['prompt']))
        verdict = judge(event(), policy, True)
        assert verdict['reason'].startswith('null '), verdict
        data = json.dumps(event()).encode()
        assert judge_bytes(data, policy, True)['reason'].startswith('null ')
        verdict = judge_bytes(data, policy, True, facts=lambda cid: {'x': 1})
        assert verdict['reason'].startswith('{"x": 1} '), verdict


def test_a_checker_without_records_is_called_with_two_arguments():
    with tempfile.TemporaryDirectory() as td:
        policy = _policy(Path(td), ('two', TWO_ARGS, None))
        verdict = judge(event(), policy, True, facts=lambda cid: {'x': 1})
        assert (verdict['verdict'], verdict['reason']) == ('deny', 'two from the checker'), verdict


def test_facts_are_read_once_per_checker_per_judgement():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        tables = [ff.checker_table('c0', SEEN.replace('"match"', '"no-match"'), folder, ['prompt'])]
        rules = [ff.deny_rule('one', 'c0'), ff.deny_rule('two', 'c0')]
        policy = load_policy(ff.write_policy(folder, tables, rules))
        calls = []

        def read(cid):
            calls.append(cid)
            return {}

        verdict = judge(event(), policy, True, facts=read)
        assert verdict['verdict'] == 'allow', verdict
        assert calls == ['c0'], calls


def test_the_facts_read_does_not_count_against_the_budget():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        tables = [ff.checker_table('c0', SEEN, folder, ['outcome'], budget_ms=100)]
        policy = load_policy(ff.write_policy(folder, tables, [ff.deny_rule('slow', 'c0')]))

        def slow(cid):
            time.sleep(0.6)
            return {'late': True}

        verdict = judge(event(), policy, True, facts=slow)
        assert verdict['verdict'] == 'deny', verdict
        assert verdict['reason'].startswith('{"late": true} '), verdict


def _snapshot(folder: Path) -> dict:
    return {
        p.relative_to(folder).as_posix(): (
            p.read_bytes() if p.is_file() else None,
            p.stat().st_mtime_ns,
        )
        for p in sorted(folder.rglob('*'))
    }


def _recording_setup(base: Path):
    root = base / 'state'
    run_id, _ = state.mint_run(root, 'claude-code')
    tables = [ff.checker_table('counting', ff.COUNTING, base, ['outcome', 'prompt'])]
    policy = ff.write_policy(base, tables, [ff.deny_rule('counted', 'counting')])
    return root, run_id, policy


def test_kit_judge_passes_none_empty_or_the_recorded_facts():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root, run_id, policy = _recording_setup(base)
        data = json.dumps(event()).encode()
        outside = ff.env(root, KIT_POLICY=str(policy))
        assert ff.judge(data, env=outside)['reason'].startswith('null '), 'outside a run'
        launched = ff.env(root, KIT_POLICY=str(policy), KIT_RUN_ID=run_id)
        nobody = json.dumps(event(**{'session.id': None})).encode()
        assert ff.judge(nobody, env=launched)['reason'].startswith('null '), 'no root key'
        verdict = ff.judge(data, env=launched)
        assert verdict['reason'].startswith('{} ') and verdict['launched'], verdict
        assert not (root / 'runs' / run_id / 'facts').exists()

        note = json.loads(json.dumps(OUTCOME))
        note['session'] = {'id': 's1', 'parent_id': None, 'root_id': None}
        note['observation']['root'] = 'unavailable'
        receipt = ff.note(json.dumps(note).encode(), env=launched)
        assert ff.results(receipt) == [('counting', 'facts')], receipt
        verdict = ff.judge(data, env=launched)
        detail = verdict['reason'][: -len(' from the checker')]
        assert json.loads(detail) == {
            'keys': ['harness', 'kit_note', 'note', 'observation', 'origin'],
            'kind': 'outcome',
            'n': 1,
        }, verdict
        other = json.dumps(event(**{'session.id': 's2'})).encode()
        assert ff.judge(other, env=launched)['reason'].startswith('{} ')


def test_fifty_judgements_leave_the_facts_folder_as_it_was():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root, run_id, policy = _recording_setup(base)
        env = ff.env(root, KIT_POLICY=str(policy), KIT_RUN_ID=run_id)
        note = json.loads(json.dumps(OUTCOME))
        note['session'] = {'id': 's1', 'parent_id': None, 'root_id': None}
        note['observation']['root'] = 'unavailable'
        assert ff.results(ff.note(json.dumps(note).encode(), env=env)) == [('counting', 'facts')]
        folder = root / 'runs' / run_id / 'facts'
        before = _snapshot(folder)
        assert len([k for k, v in before.items() if v[0] is not None]) == 2, before
        loaded = load_policy(policy)
        data = json.dumps(event()).encode()
        for n in range(48):
            data_n = data if n % 2 else json.dumps(event(**{'session.id': f's{n}'})).encode()
            verdict = cli.judge_and_journal(data_n, loaded, env)
            assert verdict['verdict'] == 'deny', verdict
        for _ in range(2):
            assert ff.judge(data, env=env)['verdict'] == 'deny'
        assert _snapshot(folder) == before


def test_a_judgement_returns_while_the_facts_lock_is_held():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root, run_id, policy = _recording_setup(base)
        env = ff.env(root, KIT_POLICY=str(policy), KIT_RUN_ID=run_id)
        holder = ff.LockHolder(facts.lock_path(root, run_id), 5.0)
        try:
            verdict = ff.judge(json.dumps(event()).encode(), env=env)
            elapsed = time.monotonic() - holder.since
            assert verdict['reason'].startswith('{} '), verdict
            assert elapsed < 4.0, elapsed
            assert holder.proc.poll() is None, 'the lock was released before the verdict'
        finally:
            holder.wait()
        assert os.listdir(root / 'runs' / run_id / 'facts') == ['facts.lock']


if __name__ == '__main__':
    run_module(globals(), 'judgement with facts')

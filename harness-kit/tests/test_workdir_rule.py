#!/usr/bin/env python3
"""Checks of the built-in rule `launcher.workdir`.

Contract under test:
- for a launched event of a harness that needs the launcher (every harness but Claude Code)
  whose run record holds `workdir`, the judge denies, governed, with rule `launcher.workdir`
  and its fixed reason, an act whose `cwd` is empty, relative, or outside each of the run's
  `workdir`, its `work_tree_top` and `runs/<id>/canary/work`; paths are compared as the policy
  compares them (forward slashes, case-folded on Windows) with a folder boundary required;
- an act inside one of the three folders goes on to the policy's rules;
- the rule stands after `launcher.required`, the canary's rules and the driver's refused tool,
  and ahead of a policy rule that allows the act;
- it is skipped for Claude Code, for a run record without `workdir` and when no record is
  passed; a run record that could not be read gives a governed `unknown` with the rule;
- `kit judge` reads the run record of a launched event and passes it to the judge, so a run
  minted by `kit state new-run` (no `workdir`) judges as before, and a run whose record names
  a working folder denies an envelope located outside it, journaling the deny under the run.

Stdlib-runnable: `python test_workdir_rule.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import verdict
from harness_kit.policy import load_policy_text
from kit_fixtures import SRC, event, run_module

RULE = 'launcher.workdir'
REASON = (
    "this session's tool calls start only in the folder kit run launched; "
    'start another kit run for another folder'
)
ALLOW_ALL = """\
version = 1

[[rule]]
id = "allow-all"
effect = "allow"
governed = true
kinds = ["shell", "file_write", "other"]
reason = "everything is allowed"
"""
OC = {'name': 'opencode', 'version': '2.2.5'}
RUN_DIR_POSIX = '/state/runs/20261118T000000Z-0123456789ab'
RUN_POSIX = {'workdir': '/w/proj/sub', 'work_tree_top': '/w/proj'}
RUN_DIR_WIN = 'C:\\state\\runs\\20261118T000000Z-0123456789ab'
RUN_WIN = {'workdir': 'C:\\Work\\Proj', 'work_tree_top': None}


def _judge(cwd: str, *, windows: bool, run=None, run_dir=None, **kw) -> dict:
    policy = load_policy_text(ALLOW_ALL, windows=windows, sha256='f' * 64)
    ev = event(**{'harness': kw.pop('harness', OC), 'act.cwd': cwd})
    launched = kw.pop('launched', True)
    return verdict.judge(ev, policy, launched, run=run, run_dir=run_dir, **kw)


def _posix(cwd: str, **kw) -> dict:
    kw.setdefault('run', RUN_POSIX)
    kw.setdefault('run_dir', RUN_DIR_POSIX)
    return _judge(cwd, windows=False, **kw)


def _win(cwd: str, **kw) -> dict:
    kw.setdefault('run', RUN_WIN)
    kw.setdefault('run_dir', RUN_DIR_WIN)
    return _judge(cwd, windows=True, **kw)


def _denied(v: dict) -> bool:
    return (v['verdict'], v['governed'], v['rule'], v['reason']) == ('deny', True, RULE, REASON)


def _allowed(v: dict) -> bool:
    return v['verdict'] == 'allow' and v['rule'] == 'allow-all'


def test_an_act_inside_one_of_the_three_folders_goes_on_to_the_policy():
    for cwd in ('/w/proj/sub', '/w/proj/sub/deeper', '/w/proj', '/w/proj/other'):
        assert _allowed(_posix(cwd)), cwd
    for cwd in (RUN_DIR_POSIX + '/canary/work', RUN_DIR_POSIX + '/canary/work/x'):
        assert _allowed(_posix(cwd)), cwd


def test_an_act_outside_the_three_folders_is_denied():
    for cwd in ('/w', '/w/proj2', '/w/projx/sub', '/elsewhere', RUN_DIR_POSIX + '/canary'):
        assert _denied(_posix(cwd)), (cwd, _posix(cwd))


def test_an_empty_or_relative_cwd_is_denied():
    for cwd in ('', 'sub', './sub', '../w/proj'):
        assert _denied(_posix(cwd)), cwd
    for cwd in ('', 'sub', '/Work/Proj', 'C:Work/Proj'):
        assert _denied(_win(cwd)), cwd


def test_windows_paths_compare_case_folded_with_either_slash():
    for cwd in ('C:\\Work\\Proj', 'c:/work/proj/sub', 'C:/WORK/PROJ'):
        assert _allowed(_win(cwd)), cwd
    canary = RUN_DIR_WIN.replace('\\', '/').upper() + '/CANARY/WORK'
    assert _allowed(_win(canary)), canary
    for cwd in ('C:/Work/Project', 'D:/Work/Proj', 'C:/Work'):
        assert _denied(_win(cwd)), cwd


def test_the_rule_is_skipped_where_it_does_not_apply():
    claude = {'name': 'claude-code', 'version': '2.1.316'}
    assert _allowed(_posix('/elsewhere', harness=claude))
    assert _allowed(_posix('/elsewhere', run={'run_id': 'x'}))
    assert _allowed(_posix('/elsewhere', run=None, run_dir=None))
    alone = {'workdir': '/w/proj/sub'}
    assert _allowed(_posix('/w/proj/sub/x', run=alone, run_dir=None))
    assert _denied(_posix('/w/proj', run=alone, run_dir=None))


def test_earlier_rules_stand_ahead_of_it():
    required = _posix('/elsewhere', launched=False)
    assert required['rule'] == 'launcher.required', required
    nonce = '0123456789abcdef'
    ev = event(**{'harness': OC, 'act.cwd': '/elsewhere'})
    ev['act']['command'] = f'echo probe > allow-{nonce}.marker'
    policy = load_policy_text(ALLOW_ALL, windows=False, sha256='f' * 64)
    canary = verdict.judge(ev, policy, True, nonce, run=RUN_POSIX, run_dir=RUN_DIR_POSIX)
    assert canary['rule'] == 'canary.allow', canary
    refused = _posix('/elsewhere', refused=('opencode_worktree_remove', 'refused by name'))
    assert refused['rule'] == 'opencode.refused-tool', refused


def test_an_unreadable_run_record_is_unknown():
    v = _posix('/w/proj/sub', run=verdict.UNREADABLE_RUN)
    assert (v['verdict'], v['governed'], v['rule']) == ('unknown', True, RULE), v


# ---- through kit judge


def _env(root: Path, policy: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env.update(PYTHONPATH=str(SRC), KIT_STATE_ROOT=str(root), KIT_POLICY=str(policy), **extra)
    return env


def _kit(env: dict, *args: str, data: bytes = b'') -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=data,
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, (args, proc.returncode, proc.stderr)
    return proc.stdout.decode('ascii')


def _envelope(location: str, run_id: str) -> bytes:
    payload = {'tool': 'shell', 'sessionID': 's1', 'input': {'command': 'echo hi'}}
    doc = {
        'kit_raw': 1,
        'hook': 'execute.before',
        'run_id': run_id,
        'harness': OC,
        'session': {'id': 's1', 'parent_id': None, 'root_id': 's1'},
        'origin': 'unknown',
        'observation': {
            'session': 'observed',
            'parent': 'observed',
            'root': 'observed',
            'origin': 'unavailable',
        },
        'location': location,
        'payload': json.dumps(payload),
    }
    return json.dumps(doc).encode('ascii')


def test_kit_judge_reads_the_run_record():
    with tempfile.TemporaryDirectory() as td:
        base = Path(os.path.realpath(td))
        policy = base / 'policy.toml'
        policy.write_text(ALLOW_ALL, encoding='utf-8')
        root, work, other = base / 'state', base / 'work', base / 'other'
        work.mkdir()
        other.mkdir()
        env = _env(root, policy)
        minted = json.loads(_kit(env, 'state', 'new-run', '--harness', 'opencode'))
        run_id = minted['run_id']
        session = dict(env, KIT_RUN_ID=run_id)
        judged = json.loads(
            _kit(session, 'judge', '--from', 'opencode', data=_envelope(str(other), run_id))
        )
        assert judged['verdict'] == 'allow' and judged['rule'] == 'allow-all', judged
        run_json = Path(minted['run_dir']) / 'run.json'
        record = json.loads(run_json.read_text(encoding='utf-8'))
        record.update(workdir=str(work), work_tree_top=None)
        run_json.write_text(json.dumps(record), encoding='utf-8')
        for location, want in ((str(other), 'deny'), (str(work), 'allow')):
            data = _envelope(location, run_id)
            judged = json.loads(_kit(session, 'judge', '--from', 'opencode', data=data))
            assert judged['verdict'] == want, (location, judged)
            assert judged['launched'] is True and judged['run_id'] == run_id, judged
        journal = Path(minted['run_dir']) / 'journal.ndjson'
        lines = [json.loads(x) for x in journal.read_text(encoding='utf-8').splitlines()]
        assert [x['rule'] for x in lines] == ['allow-all', RULE, 'allow-all'], lines
        run_json.write_text('{not json', encoding='utf-8')
        judged = json.loads(
            _kit(session, 'judge', '--from', 'opencode', data=_envelope(str(work), run_id))
        )
        assert (judged['verdict'], judged['rule']) == ('unknown', RULE), judged


if __name__ == '__main__':
    run_module(globals(), 'the launcher.workdir rule')

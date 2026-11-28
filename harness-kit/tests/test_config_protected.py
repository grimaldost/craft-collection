#!/usr/bin/env python3
"""Checks of the built-in rule `config.protected` and of the policy-hash check.

Contract under test:
- for a launched `file_write` act whose run record holds `protected`, a path that lies at or
  under a protected path and under none of `protected_except` is denied, governed, with rule
  `config.protected` and its fixed reason; paths are compared as `launcher.workdir` compares
  them (forward slashes, case-folded on Windows, a folder boundary required); a relative path
  is read against the act's folder;
- paths the act did not observe give a governed `unknown` with the rule;
- the rule stands after `launcher.workdir` and ahead of a policy rule that allows the act; it
  reads only file writes and only run records that carry `protected`; a run record that could
  not be read gives a file write a governed `unknown` with the rule;
- for every launched event whose run record holds `policy_sha256`, right after
  `launcher.required`, a loaded policy whose bytes hash otherwise gives a governed `unknown`
  with rule `config.protected` and the reason `the policy changed after kit run read it`,
  ahead of the canary's rules; a record without the key judges as before;
- both apply to every harness, Claude Code included;
- `kit judge` reads them from the run record of a launched event and journals the verdict.

Stdlib-runnable: `python test_config_protected.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import verdict
from harness_kit.policy import load_policy_text
from kit_fixtures import SRC, event, run_module, write_event

RULE = 'config.protected'
REASON = "this file governs the session; kit protects it from the session's tools"
CHANGED = 'the policy changed after kit run read it'
ALLOW_ALL = """\
version = 1

[[rule]]
id = "allow-all"
effect = "allow"
governed = true
kinds = ["shell", "file_write", "other"]
reason = "everything is allowed"
"""
SHA = hashlib.sha256(ALLOW_ALL.encode('utf-8')).hexdigest()
OC = {'name': 'opencode', 'version': '2.2.5'}
CC = {'name': 'claude-code', 'version': '2.1.316'}
RUN_DIR = '/state/runs/20261121T000000Z-0123456789ab'
EXCEPT = posixpath.join(RUN_DIR, 'tmp')
RUN = {
    'workdir': '/w/proj',
    'work_tree_top': None,
    'protected': ['/h/conf', '/h/home.json', '/state', '/usr/lib/python3/site-packages'],
    'protected_except': [EXCEPT],
    'policy_sha256': SHA,
}
RUN_DIR_WIN = 'C:\\state\\runs\\20261121T000000Z-0123456789ab'
RUN_WIN = {
    'workdir': 'C:\\Work\\Proj',
    'work_tree_top': None,
    'protected': ['C:\\H\\conf', 'C:/Users/me/.claude'],
    'protected_except': [RUN_DIR_WIN + '\\tmp'],
    'policy_sha256': SHA,
}


def _policy(windows: bool, sha: str = SHA):
    return load_policy_text(ALLOW_ALL, windows=windows, sha256=sha)


def _write(paths, *, windows=False, run=RUN, run_dir=RUN_DIR, harness=OC, **kw) -> dict:
    cwd = kw.pop('cwd', 'C:\\Work\\Proj' if windows else '/w/proj')
    ev = write_event(list(paths), **{'harness': harness, 'act.cwd': cwd})
    for key, value in kw.pop('over', {}).items():
        node = ev
        *parents, leaf = key.split('.')
        for name in parents:
            node = node[name]
        node[leaf] = value
    launched = kw.pop('launched', True)
    sha = kw.pop('sha', SHA)
    return verdict.judge(ev, _policy(windows, sha), launched, run=run, run_dir=run_dir, **kw)


def _denied(v: dict) -> bool:
    return (v['verdict'], v['governed'], v['rule'], v['reason']) == ('deny', True, RULE, REASON)


def _allowed(v: dict) -> bool:
    return v['verdict'] == 'allow' and v['rule'] == 'allow-all'


def test_a_write_of_the_homes_ripgrep_copy_is_denied_and_one_beside_it_is_not():
    run = dict(RUN, protected=[*RUN['protected'], '/h/xdg/cache/opencode/bin/rg'])
    assert _denied(_write(['/h/xdg/cache/opencode/bin/rg'], run=run))
    assert _allowed(_write(['/h/xdg/cache/opencode/bin/other.exe'], run=run))
    run = dict(
        RUN_WIN, protected=[*RUN_WIN['protected'], 'C:\\H\\xdg\\cache\\opencode\\bin\\rg.exe']
    )
    v = _write(['c:/h/XDG/cache/opencode/bin/RG.EXE'], windows=True, run=run, run_dir=RUN_DIR_WIN)
    assert _denied(v), v
    v = _write(
        ['C:/H/xdg/cache/opencode/bin/other.exe'], windows=True, run=run, run_dir=RUN_DIR_WIN
    )
    assert _allowed(v), v


def test_a_write_at_or_under_a_protected_path_is_denied():
    for path in (
        '/h/conf',
        '/h/conf/opencode.jsonc',
        '/h/conf/plugins/x.js',
        '/h/home.json',
        '/state/runs/x/run.json',
        '/usr/lib/python3/site-packages/evil.pth',
        '/w/proj/../../h/conf/a',
    ):
        assert _denied(_write([path])), (path, _write([path]))


def test_one_protected_path_among_several_denies():
    assert _denied(_write(['/w/proj/a.txt', '/h/conf/opencode.jsonc']))


def test_a_write_elsewhere_goes_on_to_the_policy():
    for path in ('/w/proj/a.txt', '/h/confx/a', '/h/home.json.bak', '/h', '/statefile'):
        assert _allowed(_write([path])), (path, _write([path]))


def test_an_exception_lets_a_write_through():
    assert _allowed(_write([EXCEPT + '/scratch.txt']))
    assert _allowed(_write([EXCEPT]))
    assert _denied(_write([EXCEPT + 'x/scratch.txt']))
    assert _denied(_write([EXCEPT + '/a', '/state/other']))


def test_a_relative_path_is_read_against_the_acts_folder():
    assert _denied(_write(['conf/opencode.jsonc'], cwd='/h', harness=CC))
    assert _allowed(_write(['notes.txt'], cwd='/w/proj'))
    v = _write(['conf/opencode.jsonc'], cwd='', harness=CC)
    assert (v['verdict'], v['rule']) == ('unknown', RULE), v


def test_windows_paths_compare_case_folded_with_either_slash():
    run, rd = RUN_WIN, RUN_DIR_WIN
    for path in ('c:/h/CONF/opencode.jsonc', 'C:\\H\\conf', 'c:/users/me/.Claude/CLAUDE.md'):
        v = _write([path], windows=True, run=run, run_dir=rd)
        assert _denied(v), (path, v)
    v = _write([rd.lower() + '/TMP/x'], windows=True, run=run, run_dir=rd)
    assert _allowed(v), v
    v = _write(['C:/H/configs/x'], windows=True, run=run, run_dir=rd)
    assert _allowed(v), v


def test_unavailable_paths_are_unknown():
    v = _write([], over={'observation.paths': 'unavailable'})
    assert (v['verdict'], v['governed'], v['rule']) == ('unknown', True, RULE), v


def test_the_rule_reads_only_file_writes_and_records_that_carry_it():
    shell = event(**{'harness': OC, 'act.cwd': '/w/proj', 'act.command': 'echo > /h/conf/a'})
    v = verdict.judge(shell, _policy(False), True, run=RUN, run_dir=RUN_DIR)
    assert _allowed(v), v
    bare = {k: v for k, v in RUN.items() if k not in ('protected', 'protected_except')}
    assert _allowed(_write(['/h/conf/a'], run=bare))
    assert _allowed(_write(['/h/conf/a'], run=None, run_dir=None))
    assert _allowed(_write(['/h/conf/a'], launched=None))


def test_it_stands_after_launcher_workdir_and_applies_to_claude_code():
    v = _write(['/h/conf/a'], cwd='/elsewhere')
    assert v['rule'] == 'launcher.workdir', v
    assert _denied(_write(['/h/conf/a'], harness=CC, cwd='/elsewhere'))
    assert _allowed(_write(['/w/proj/a'], harness=CC))


def test_an_unreadable_run_record_is_unknown_for_a_write():
    v = _write(['/w/proj/a'], harness=CC, run=verdict.UNREADABLE_RUN)
    assert (v['verdict'], v['governed'], v['rule']) == ('unknown', True, RULE), v
    shell = event(**{'harness': CC, 'act.cwd': '/w/proj'})
    v = verdict.judge(shell, _policy(False), True, run=verdict.UNREADABLE_RUN, run_dir=RUN_DIR)
    assert _allowed(v), v


def test_a_policy_that_hashes_otherwise_is_unknown():
    for harness in (OC, CC):
        ev = event(**{'harness': harness, 'act.cwd': '/w/proj'})
        v = verdict.judge(ev, _policy(False, 'b' * 64), True, run=RUN, run_dir=RUN_DIR)
        assert (v['verdict'], v['governed'], v['rule'], v['reason']) == (
            'unknown',
            True,
            RULE,
            CHANGED,
        ), v
        assert v['policy_sha256'] == 'b' * 64, v
        assert _allowed(verdict.judge(ev, _policy(False), True, run=RUN, run_dir=RUN_DIR))
    bare = {k: v for k, v in RUN.items() if k != 'policy_sha256'}
    ev = event(**{'harness': OC, 'act.cwd': '/w/proj'})
    assert _allowed(verdict.judge(ev, _policy(False, 'b' * 64), True, run=bare, run_dir=RUN_DIR))


def test_the_policy_hash_stands_right_after_launcher_required():
    ev = event(**{'harness': OC, 'act.cwd': '/w/proj'})
    v = verdict.judge(ev, _policy(False, 'b' * 64), False, run=RUN, run_dir=RUN_DIR)
    assert v['rule'] == 'launcher.required', v
    nonce = '0123456789abcdef'
    ev['act']['command'] = f'echo probe > allow-{nonce}.marker'
    v = verdict.judge(ev, _policy(False, 'b' * 64), True, nonce, run=RUN, run_dir=RUN_DIR)
    assert (v['verdict'], v['rule']) == ('unknown', RULE), v
    v = verdict.judge(
        ev,
        _policy(False, 'b' * 64),
        True,
        refused=('opencode_worktree_remove', 'refused by name'),
        run=RUN,
        run_dir=RUN_DIR,
    )
    assert (v['verdict'], v['rule']) == ('unknown', RULE), v


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


def _envelope(location: str, run_id: str, path: str) -> bytes:
    payload = {'tool': 'write', 'sessionID': 's1', 'input': {'path': path, 'content': 'x'}}
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


def test_kit_judge_reads_the_protected_paths_and_the_policy_hash():
    with tempfile.TemporaryDirectory() as td:
        base = Path(os.path.realpath(td))
        policy = base / 'policy.toml'
        policy.write_text(ALLOW_ALL, encoding='utf-8')
        root, work, conf = base / 'state', base / 'work', base / 'home' / 'conf'
        work.mkdir()
        conf.mkdir(parents=True)
        env = _env(root, policy)
        minted = json.loads(_kit(env, 'state', 'new-run', '--harness', 'opencode'))
        run_id = minted['run_id']
        run_json = Path(minted['run_dir']) / 'run.json'
        record = json.loads(run_json.read_text(encoding='utf-8'))
        record.update(
            workdir=str(work),
            work_tree_top=None,
            protected=[str(conf), str(policy)],
            protected_except=[str(Path(minted['run_dir']) / 'tmp')],
            policy_sha256=hashlib.sha256(policy.read_bytes()).hexdigest(),
        )
        run_json.write_text(json.dumps(record), encoding='utf-8')
        session = dict(env, KIT_RUN_ID=run_id)
        for path, want in ((str(conf / 'opencode.jsonc'), 'deny'), (str(work / 'a.txt'), 'allow')):
            data = _envelope(str(work), run_id, path)
            judged = json.loads(_kit(session, 'judge', '--from', 'opencode', data=data))
            assert judged['verdict'] == want, (path, judged)
        policy.write_text(ALLOW_ALL + '\n', encoding='utf-8')
        data = _envelope(str(work), run_id, str(work / 'a.txt'))
        judged = json.loads(_kit(session, 'judge', '--from', 'opencode', data=data))
        assert (judged['verdict'], judged['rule'], judged['reason']) == ('unknown', RULE, CHANGED)
        journal = Path(minted['run_dir']) / 'journal.ndjson'
        lines = [json.loads(x) for x in journal.read_text(encoding='utf-8').splitlines()]
        assert [x['rule'] for x in lines] == [RULE, 'allow-all', RULE], lines


if __name__ == '__main__':
    run_module(globals(), 'the config.protected rule and the policy hash')

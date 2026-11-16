#!/usr/bin/env python3
"""Checks of the `notes` section of `kit doctor`.

Contract under test, with the fake harness of `canary_fake_harness.py`:
- `KIT_POLICY` naming a readable version 3 policy with at least one recording
  checker gives a section `notes`: per recording checker, in the policy's order,
  its id, its `records`, and per harness and recorded kind a state with the
  contract's evidence in parentheses when the state is `tested`; the text form
  stands after the `rules` section and before the line `runs:`; `--json` holds
  the same under the key `notes`, a list of `{checker, records, states,
  evidence}`;
- a harness reads `unknown` when its binary is absent, its version differs or
  its contract has no `[notes]` entry for the kind, and `absent` when the entry
  says so;
- with a version 1 or 2 policy, with no policy and with a version 3 policy that
  records nothing the report has no `notes` key, and the version 3 policy that
  records nothing gives the report of the same policy with its version line
  set to 2;
- the section reads files only: it starts no `python`, `pip`, `uv` or `gh`.

Stdlib-runnable: `python test_doctor_notes.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import doctor
from kit_fixtures import run_module
from test_canary import PINNED, base_env, kit, scratch
from test_doctor import doctor_env, fake_argv

PACKS = Path(__file__).resolve().parents[1] / 'packs'
BASE_POLICY = 'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n'
SECTION_KEYS = {'checker', 'records', 'states', 'evidence'}
HARNESSES = ['claude-code', 'opencode']


def build(base: Path, packs: list[Path], out_name: str = 'built.toml') -> Path:
    base_file = base / 'base.toml'
    base_file.write_text(BASE_POLICY, encoding='utf-8')
    out = base / out_name
    args = ['policy', 'build', '--base', str(base_file), '--out', str(out), '--force']
    for pack in packs:
        args += ['--pack', str(pack)]
    proc = kit(*args, env=base_env(KIT_STATE_ROOT=str(base / 'state')))
    assert proc.returncode == 0, proc.stderr
    return out


def env_for(base: Path, policy: Path | None, claude: str | None = None) -> dict:
    env = doctor_env(
        base,
        claude or fake_argv(base, PINNED['claude-code']),
        fake_argv(base, PINNED['opencode']),
    )
    if policy is not None:
        env['KIT_POLICY'] = str(policy)
    return env


def report(env: dict) -> tuple[str, dict]:
    text = kit('doctor', env=env)
    assert text.returncode == 0, text.stderr
    data = kit('doctor', '--json', env=env)
    assert data.returncode == 0, data.stderr
    return text.stdout.decode('ascii'), json.loads(data.stdout)


def raw(env: dict) -> tuple[bytes, bytes]:
    text = kit('doctor', env=env)
    data = kit('doctor', '--json', env=env)
    assert text.returncode == 0 and data.returncode == 0, (text.stderr, data.stderr)
    return text.stdout, data.stdout


def contract_evidence(harness: str, kind: str) -> str:
    return doctor.load_contract(harness)['notes'][kind]['evidence']


def test_the_series_pack_gives_the_section_in_text_and_json():
    base = scratch()
    try:
        policy = build(base, [PACKS / 'series'])
        text, data = report(env_for(base, policy))
        rows = data['notes']
        assert len(rows) == 1 and set(rows[0]) == SECTION_KEYS, rows
        row = rows[0]
        assert row['checker'] == 'series-check' and row['records'] == ['outcome'], row
        assert row['states'] == {h: {'outcome': 'tested'} for h in HARNESSES}, row
        assert row['evidence'] == {
            h: {'outcome': contract_evidence(h, 'outcome')} for h in HARNESSES
        }
        lines = text.splitlines()
        start = lines.index('notes:')
        want = [
            'notes:',
            '  series-check records outcome',
            f'    claude-code outcome tested ({contract_evidence("claude-code", "outcome")})',
            f'    opencode outcome tested ({contract_evidence("opencode", "outcome")})',
        ]
        assert lines[start : start + len(want)] == want, lines
        assert lines[start + len(want)] == 'runs:', lines
        assert list(data)[-2:] == ['rules', 'notes'], list(data)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_two_packs_give_two_checkers_in_the_policys_order_after_the_rules_section():
    base = scratch()
    try:
        policy = build(base, [PACKS / 'owner-acts', PACKS / 'series'])
        text, data = report(env_for(base, policy))
        assert [r['checker'] for r in data['notes']] == ['owner-acts-check', 'series-check']
        assert [r['records'] for r in data['notes']] == [['prompt'], ['outcome']], data['notes']
        assert list(data) == ['kit_doctor', 'harnesses', 'runs', 'not_launched', 'rules', 'notes']
        lines = text.splitlines()
        assert lines.index('rules:') < lines.index('notes:') < lines.index('runs:'), lines
        first = lines.index('  owner-acts-check records prompt')
        assert lines[first + 1].startswith('    claude-code prompt tested ('), lines
        assert lines[first + 3] == '  series-check records outcome', lines
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_checker_that_records_both_kinds_lists_them_in_its_order():
    base = scratch()
    try:
        pack = base / 'both'
        pack.mkdir()
        (pack / 'both_rule.py').write_text(
            'def check(act, observation, facts):\n    return {"result": "no-match"}\n\n\n'
            'def record(note, facts):\n    return {"result": "unchanged"}\n',
            encoding='utf-8',
        )
        (pack / 'pack.toml').write_text(
            'pack = 1\nname = "both"\n\n[[checker]]\nid = "both-check"\nfile = "both_rule.py"\n'
            'records = ["outcome", "prompt"]\n\n[[rule]]\nid = "both-rule"\neffect = "deny"\n'
            'governed = false\nkinds = ["shell"]\ncheck = "both-check"\nreason = "no"\n',
            encoding='utf-8',
        )
        policy = build(base, [pack])
        text, data = report(env_for(base, policy))
        assert data['notes'][0]['records'] == ['outcome', 'prompt'], data['notes']
        lines = text.splitlines()
        start = lines.index('  both-check records outcome, prompt')
        kinds = [ln.split()[1] for ln in lines[start + 1 : start + 5]]
        assert [ln.split()[0] for ln in lines[start + 1 : start + 5]] == [
            'claude-code',
            'claude-code',
            'opencode',
            'opencode',
        ], lines
        assert kinds == ['outcome', 'prompt', 'outcome', 'prompt'], lines
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_harness_reads_unknown_without_the_binary_the_version_or_the_entry():
    base = scratch()
    saved = doctor.CONTRACTS_DIR
    try:
        policy = build(base, [PACKS / 'series'])
        missing = json.dumps([str(base / 'no-such-harness.exe')])
        text, data = report(env_for(base, policy, claude=missing))
        row = data['notes'][0]
        assert row['states'] == {
            'claude-code': {'outcome': 'unknown'},
            'opencode': {'outcome': 'tested'},
        }
        assert row['evidence']['claude-code'] == {'outcome': ''}, row
        assert '    claude-code outcome unknown' in text.splitlines(), text
        _, data = report(env_for(base, policy, claude=fake_argv(base, '2.1.999')))
        assert data['notes'][0]['states']['claude-code'] == {'outcome': 'unknown'}, data['notes']
        contracts = base / 'contracts'
        shutil.copytree(saved, contracts)
        path = contracts / 'opencode.toml'
        kept = path.read_text(encoding='utf-8').split('[notes.prompt]')[0]
        assert '[notes' not in kept, kept
        path.write_text(kept, encoding='utf-8')
        doctor.CONTRACTS_DIR = contracts
        built = doctor.build_report(env_for(base, policy))
        assert built['notes'][0]['states']['opencode'] == {'outcome': 'unknown'}, built['notes']
        assert built['notes'][0]['states']['claude-code'] == {'outcome': 'tested'}, built['notes']
        assert built['notes'][0]['evidence']['opencode'] == {'outcome': ''}, built['notes']
    finally:
        doctor.CONTRACTS_DIR = saved
        shutil.rmtree(base, ignore_errors=True)


def test_an_absent_entry_reads_absent_with_no_evidence():
    base = scratch()
    saved = doctor.CONTRACTS_DIR
    try:
        policy = build(base, [PACKS / 'series'])
        contracts = base / 'contracts'
        shutil.copytree(saved, contracts)
        path = contracts / 'claude_code.toml'
        text = path.read_text(encoding='utf-8')
        head, tail = text.split('[notes.outcome]')
        tail = tail.replace('state = "tested"', 'state = "absent"', 1)
        path.write_text(head + '[notes.outcome]' + tail, encoding='utf-8')
        doctor.CONTRACTS_DIR = contracts
        built = doctor.build_report(env_for(base, policy))
        row = built['notes'][0]
        assert row['states']['claude-code'] == {'outcome': 'absent'}, row
        assert row['evidence']['claude-code'] == {'outcome': ''}, row
        assert doctor.render_text(built).count('    claude-code outcome absent\n') == 1
    finally:
        doctor.CONTRACTS_DIR = saved
        shutil.rmtree(base, ignore_errors=True)


def test_no_section_for_version_1_version_2_no_policy_or_an_unreadable_one():
    base = scratch()
    try:
        plain_raw = raw(env_for(base, None))
        assert b'notes' not in plain_raw[1], plain_raw[1]
        v1 = base / 'v1.toml'
        v1.write_text(BASE_POLICY, encoding='utf-8')
        v2 = base / 'v2.toml'
        v2.write_text(BASE_POLICY.replace('version = 1', 'version = 2'), encoding='utf-8')
        broken = base / 'broken.toml'
        broken.write_text('not toml at all [', encoding='utf-8')
        for policy in (v1, v2, broken):
            _, data = report(env_for(base, policy))
            assert 'notes' not in data, (policy, data)
        assert raw(env_for(base, v1)) == plain_raw
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_version_3_policy_that_records_nothing_gives_the_version_2_report():
    base = scratch()
    try:
        checker = base / 'rule.py'
        source = b'def check(act, observation):\n    return {"result": "no-match"}\n'
        checker.write_bytes(source)
        sha = hashlib.sha256(source).hexdigest()
        body = (
            'version = {v}\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n\n'
            f'[[checker]]\nid = "plain-rule"\nfile = "rule.py"\nsha256 = "{sha}"\nbudget_ms = 250\n\n'
            '[[rule]]\nid = "plain"\neffect = "deny"\ngoverned = false\nkinds = ["shell"]\n'
            'check = "plain-rule"\nreason = "no"\n'
        )
        v3, v2 = base / 'v3.toml', base / 'v2.toml'
        v3.write_text(body.format(v=3), encoding='utf-8')
        v2.write_text(body.format(v=2), encoding='utf-8')
        want = raw(env_for(base, v2))
        got = raw(env_for(base, v3))
        assert got == want
        assert b'notes' not in got[1], got[1]
        for policy in (v3, v2):
            side = {'packs': [], 'policy_sha256': hashlib.sha256(policy.read_bytes()).hexdigest()}
            Path(str(policy) + '.packs.json').write_text(json.dumps(side), encoding='utf-8')
        side_want = raw(env_for(base, v2))
        side_got = raw(env_for(base, v3))
        assert side_got == side_want
        assert b'"rules": [' in side_got[1] and b'notes' not in side_got[1], side_got[1]
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_the_section_starts_no_python_pip_uv_or_gh():
    base = scratch()
    try:
        policy = build(base, [PACKS / 'series', PACKS / 'owner-acts'])
        traps = base / 'traps'
        traps.mkdir()
        marker = base / 'trap-ran.txt'
        for name in ('python', 'python3', 'py', 'pip', 'pip3', 'uv', 'uvx', 'gh'):
            if os.name == 'nt':
                body = f'@echo {name} >> "{marker}"\r\n'
                (traps / f'{name}.cmd').write_text(body, encoding='ascii')
                (traps / f'{name}.bat').write_text(body, encoding='ascii')
            else:
                path = traps / name
                path.write_text(f'#!/bin/sh\necho {name} >> "{marker}"\n', encoding='ascii')
                path.chmod(0o755)
        env = env_for(base, policy)
        env['PATH'] = str(traps)
        text, data = report(env)
        assert len(data['notes']) == 2 and 'notes:' in text, data
        assert not marker.exists(), marker.read_text()
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'notes in kit doctor')

#!/usr/bin/env python3
"""Checks of the `rules` section of `kit doctor`.

Contract under test, with the fake harness of `canary_fake_harness.py`:
- `KIT_POLICY` naming a readable version 2 policy with a `<policy>.packs.json`
  beside it whose `policy_sha256` is the policy's gives a section `rules`: per
  rule with a checker, its id, `governed`, its pack's name (`-` and null for a
  base rule), a state per harness with the contract's evidence text when the
  state is `tested`, and `prevention`: the pack's declared layer followed by
  `declared by the pack, not checked by the kit`, or `none declared`;
- a harness reads `unknown` for a rule when its binary is absent, its version
  differs from the contract's or its contract holds no entry for the rule;
- a file that does not load (a changed checker byte, a missing file, a file that
  is not TOML) gives the one line `rules: policy unreadable: <reason>`, a file
  that is TOML with `version = 1` gives no section, and a rebuilt policy beside
  an old sidecar gives `rules: sidecar stale`; the JSON `rules` key holds the
  same as a string;
- with a version 1 policy, with no `KIT_POLICY` and with a version 2 policy that
  has no sidecar the report is the report without a policy, byte for byte;
- the section starts no `python`, `pip` or `uv`.

Stdlib-runnable: `python test_doctor_rules.py`.
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

PACK_UV = Path(__file__).resolve().parents[1] / 'packs' / 'uv'
RULE = 'uv-project-uses-uv'
DECLARED = 'declared by the pack, not checked by the kit'
BASE_POLICY = 'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n'
STUB_CHECKER = 'def check(act, observation):\n    return {"result": "no-match"}\n'
LAYER = "pip's require-virtualenv setting in the user's pip configuration"
SECTION_KEYS = {'id', 'governed', 'pack', 'states', 'evidence', 'prevention'}
REPORT_KEYS = {'kit_doctor', 'harnesses', 'runs', 'not_launched', 'rules'}


def stub_pack(folder: Path, name: str = 'stub', rule: str = RULE, prevention: bool = True) -> Path:
    folder.mkdir(parents=True)
    (folder / 'stub_rule.py').write_text(STUB_CHECKER, encoding='utf-8')
    text = (
        f'pack = 1\nname = "{name}"\n\n[[checker]]\nid = "stub-rule"\nfile = "stub_rule.py"\n\n'
        f'[[rule]]\nid = "{rule}"\neffect = "deny"\ngoverned = false\nkinds = ["shell"]\n'
        'check = "stub-rule"\nreason = "use uv"\n'
    )
    if prevention:
        text += f'\n[prevention]\nrule = "{rule}"\nlayer = "{LAYER}"\n'
    (folder / 'pack.toml').write_text(text, encoding='utf-8')
    return folder


def build(base: Path, pack: Path, out_name: str = 'built.toml', base_text: str = BASE_POLICY):
    base_file = base / 'base.toml'
    base_file.write_text(base_text, encoding='utf-8')
    out = base / out_name
    proc = kit(
        'policy',
        'build',
        '--base',
        str(base_file),
        '--pack',
        str(pack),
        '--out',
        str(out),
        '--force',
        env=base_env(KIT_STATE_ROOT=str(base / 'state')),
    )
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


def test_a_built_uv_policy_gives_the_section_tested_on_both_harnesses():
    base = scratch()
    try:
        policy = build(base, PACK_UV)
        text, data = report(env_for(base, policy))
        rows = data['rules']
        assert len(rows) == 1 and set(rows[0]) == SECTION_KEYS, rows
        row = rows[0]
        assert row['id'] == RULE and row['governed'] is False and row['pack'] == 'uv', row
        assert list(row['states']) == ['claude-code', 'opencode'], row
        assert set(row['states'].values()) == {'tested'}, row
        for harness in ('claude-code', 'opencode'):
            want = doctor.load_contract(harness)['rules'][RULE]['evidence']
            assert row['evidence'][harness] == want, row
            assert want in text, text
        assert row['prevention'] == f'{LAYER} ({DECLARED})', row
        assert text.splitlines().count('rules:') == 1, text
        assert RULE in text and 'governed' in text and 'pack uv' in text, text
        assert f'{LAYER} ({DECLARED})' in text, text
        assert set(data) == REPORT_KEYS, set(data)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_harness_reads_unknown_without_the_binary_the_version_or_the_entry():
    base = scratch()
    saved = doctor.CONTRACTS_DIR
    try:
        policy = build(base, stub_pack(base / 'stub'))
        missing = json.dumps([str(base / 'no-such-harness.exe')])
        _, data = report(env_for(base, policy, claude=missing))
        row = data['rules'][0]
        assert row['states'] == {'claude-code': 'unknown', 'opencode': 'tested'}, row
        assert row['evidence']['claude-code'] == '' and row['evidence']['opencode'], row
        _, data = report(env_for(base, policy, claude=fake_argv(base, '2.1.999')))
        assert data['rules'][0]['states']['claude-code'] == 'unknown', data['rules']
        contracts = base / 'contracts'
        shutil.copytree(saved, contracts)
        path = contracts / 'opencode.toml'
        kept = path.read_text(encoding='utf-8').split('# Rules a pack carries')[0]
        path.write_text(kept, encoding='utf-8')
        doctor.CONTRACTS_DIR = contracts
        built = doctor.build_report(env_for(base, policy))
        states = built['rules'][0]['states']
        assert states == {'claude-code': 'tested', 'opencode': 'unknown'}, built['rules']
        assert built['rules'][0]['evidence']['opencode'] == '', built['rules']
    finally:
        doctor.CONTRACTS_DIR = saved
        shutil.rmtree(base, ignore_errors=True)


def test_a_base_rule_has_no_pack_and_a_pack_without_prevention_says_none():
    base = scratch()
    try:
        base_pack = base / 'basepack'
        base_pack.mkdir()
        (base_pack / 'base_rule.py').write_bytes(STUB_CHECKER.encode('utf-8'))
        digest = hashlib.sha256(STUB_CHECKER.encode('utf-8')).hexdigest()
        checker_file = json.dumps(str(base_pack / 'base_rule.py').replace('\\', '/'))
        base_text = (
            'version = 2\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n\n'
            f'[[checker]]\nid = "base-rule"\nfile = {checker_file}\nsha256 = "{digest}"\n\n'
            '[[rule]]\nid = "base-checked"\neffect = "deny"\ngoverned = true\nkinds = ["shell"]\n'
            'check = "base-rule"\nreason = "no"\n\n'
            '[[rule]]\nid = "plain"\neffect = "deny"\ngoverned = true\nkinds = ["shell"]\n'
            'command_regex = "zzz"\nreason = "no"\n'
        )
        policy = build(base, stub_pack(base / 'stub', prevention=False), base_text=base_text)
        text, data = report(env_for(base, policy))
        rows = {r['id']: r for r in data['rules']}
        assert list(rows) == ['base-checked', RULE], rows
        assert rows['base-checked']['pack'] is None and rows['base-checked']['governed'], rows
        assert rows['base-checked']['prevention'] == 'none declared', rows
        assert rows[RULE]['pack'] == 'stub' and rows[RULE]['prevention'] == 'none declared', rows
        assert 'base-checked governed true pack -' in text, text
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _only_unreadable(base: Path, policy: Path) -> None:
    text, data = report(env_for(base, policy))
    line = next(x for x in text.splitlines() if x.startswith('rules:'))
    assert line.startswith('rules: policy unreadable: ') and len(line) > 26, line
    assert text.count('rules:') == 1, text
    assert data['rules'] == line[len('rules: ') :], (data['rules'], line)
    assert set(data) == REPORT_KEYS, set(data)


def test_an_unloadable_policy_gives_one_line():
    base = scratch()
    try:
        pack = stub_pack(base / 'stub')
        policy = build(base, pack)
        (pack / 'stub_rule.py').write_text(STUB_CHECKER + '#', encoding='utf-8')
        _only_unreadable(base, policy)
        _only_unreadable(base, base / 'no-such-policy.toml')
        junk = base / 'junk.toml'
        junk.write_text('this is = = not toml', encoding='utf-8')
        _only_unreadable(base, junk)
        three = base / 'three.toml'
        three.write_text('version = 3\n', encoding='utf-8')
        _only_unreadable(base, three)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_a_stale_sidecar_gives_one_line():
    base = scratch()
    try:
        policy = build(base, stub_pack(base / 'stub'))
        policy.write_text(policy.read_text(encoding='utf-8') + '\n# edited\n', encoding='utf-8')
        text, data = report(env_for(base, policy))
        assert text.count('rules:') == 1 and 'rules: sidecar stale' in text.splitlines(), text
        assert data['rules'] == 'sidecar stale', data
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_no_section_for_version_1_no_policy_or_no_sidecar():
    base = scratch()
    try:
        plain_text, plain = report(env_for(base, None))
        assert 'rules' not in plain, plain
        plain_raw = kit('doctor', env=env_for(base, None)).stdout
        plain_json = kit('doctor', '--json', env=env_for(base, None)).stdout
        v1 = base / 'v1.toml'
        v1.write_text(BASE_POLICY, encoding='utf-8')
        broken_v1 = base / 'broken-v1.toml'
        broken_v1.write_text('version = 1\nsurprise = true\n', encoding='utf-8')
        built = build(base, stub_pack(base / 'stub'))
        os.remove(str(built) + '.packs.json')
        for policy in (v1, broken_v1, built):
            env = env_for(base, policy)
            assert kit('doctor', env=env).stdout == plain_raw, policy
            assert kit('doctor', '--json', env=env).stdout == plain_json, policy
        assert plain_text.encode('ascii') == plain_raw
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_the_section_starts_no_python_pip_or_uv():
    base = scratch()
    try:
        policy = build(base, stub_pack(base / 'stub'))
        traps = base / 'traps'
        traps.mkdir()
        marker = base / 'trap-ran.txt'
        for name in ('python', 'python3', 'py', 'pip', 'pip3', 'uv', 'uvx'):
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
        assert data['rules'][0]['id'] == RULE and 'rules:' in text, data
        assert not marker.exists(), marker.read_text()
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'rules in kit doctor')

#!/usr/bin/env python3
"""Checks of `kit policy build` with a `[permissions]` section (policy version 4).

Contract under test:
- the build writes version 4 exactly when its base has the section, and then
  writes the section after the rules: `default`, then one `[[permissions.rule]]`
  table per rule in the base's order, with `action`, `resource` and `effect`;
  the written policy loads with the base's section;
- a base without the section, version 4 among them, builds what it built
  before: version 2, or 3 when a checker records;
- a recording checker of the packs keeps its `records` in a version 4 build;
- the same inputs give the same bytes.

Stdlib-runnable: `python test_policy_build_v4.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.policy import PermissionRule, Permissions, load_policy
from kit_fixtures import SAMPLE_POLICY, SRC, run_module

_STATE = tempfile.TemporaryDirectory()

CHECK = 'def check(act, observation):\n    return {"result": "no-match"}\n'
RECORDING = CHECK + 'def record(note, facts):\n    return {"result": "unchanged"}\n'
SECTION = (
    '\n[permissions]\ndefault = "ask"\n'
    '\n[[permissions.rule]]\naction = "shell"\nresource = "echo probe > perm-deny*"\n'
    'effect = "deny"\n'
    '\n[[permissions.rule]]\naction = "webfetch"\nresource = "https://h\\u00e9/*"\n'
    'effect = "allow"\n'
    '\n[[permissions.rule]]\naction = "read"\nresource = "*"\neffect = "ask"\n'
)
WANT = Permissions(
    default='ask',
    rules=(
        PermissionRule('shell', 'echo probe > perm-deny*', 'deny'),
        PermissionRule('webfetch', 'https://hé/*', 'allow'),
        PermissionRule('read', '*', 'ask'),
    ),
)
WRITTEN = (
    '[permissions]\ndefault = "ask"\n\n'
    '[[permissions.rule]]\naction = "shell"\nresource = "echo probe > perm-deny*"\n'
    'effect = "deny"\n\n'
    '[[permissions.rule]]\naction = "webfetch"\nresource = "https://h\\u00E9/*"\n'
    'effect = "allow"\n\n'
    '[[permissions.rule]]\naction = "read"\nresource = "*"\neffect = "ask"\n'
)


def _kit(*args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env['PYTHONPATH'] = str(SRC)
    env['KIT_STATE_ROOT'] = _STATE.name
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=60,
    )


def _pack(folder: Path, checker_id: str, body: str, records: str | None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{checker_id}.py').write_bytes(body.encode('utf-8'))
    table = f'[[checker]]\nid = "{checker_id}"\nfile = "{checker_id}.py"\nbudget_ms = 250\n'
    if records is not None:
        table += f'records = {records}\n'
    rule = (
        f'[[rule]]\nid = "{checker_id}-rule"\neffect = "deny"\ngoverned = false\n'
        f'kinds = ["shell"]\ncheck = "{checker_id}"\nreason = "probe"\n'
    )
    text = f'pack = 1\nname = "{checker_id}-pack"\n\n{table}\n{rule}'
    (folder / 'pack.toml').write_bytes(text.encode('utf-8'))
    return folder


def _build(root: Path, base_text: str, *packs: Path, name: str = 'built.toml'):
    base = root / f'base-{name}'
    base.write_bytes(base_text.encode('utf-8'))
    out = root / 'out' / name
    out.parent.mkdir(exist_ok=True)
    args = ['policy', 'build', '--base', str(base)]
    for pack in packs:
        args += ['--pack', str(pack)]
    proc = _kit(*args, '--out', str(out))
    assert proc.returncode == 0, proc.stderr
    return out


def _v4(text: str = SAMPLE_POLICY) -> str:
    return text.replace('version = 1', 'version = 4') + SECTION


def test_a_base_with_the_section_builds_version_4_with_it():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = _build(root, _v4(), _pack(root / 'p', 'plain', CHECK, None))
        text = out.read_text(encoding='ascii')
        assert text.startswith('version = 4\n'), text
        assert text.endswith(WRITTEN), text
        assert text.index('[[rule]]') < text.index('[permissions]'), text
        policy = load_policy(out)
        assert policy.permissions == WANT, policy.permissions
        assert [r.id for r in policy.rules] == ['no-config-write', 'plain-rule']


def test_a_base_without_the_section_builds_as_before():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plain = _pack(root / 'p', 'plain', CHECK, None)
        for version in (1, 2, 3, 4):
            text = SAMPLE_POLICY.replace('version = 1', f'version = {version}')
            out = _build(root, text, plain, name=f'v{version}.toml')
            written = out.read_text(encoding='ascii')
            assert written.startswith('version = 2\n'), (version, written)
            assert '[permissions]' not in written
            assert load_policy(out).permissions is None
        recording = _pack(root / 'r', 'rec', RECORDING, '["prompt"]')
        out = _build(root, SAMPLE_POLICY.replace('version = 1', 'version = 4'), recording)
        assert out.read_text(encoding='ascii').startswith('version = 3\n')


def test_a_recording_checker_keeps_its_records_in_a_version_4_build():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = _build(root, _v4(), _pack(root / 'r', 'rec', RECORDING, '["outcome"]'))
        policy = load_policy(out)
        assert out.read_text(encoding='ascii').startswith('version = 4\n')
        assert policy.checkers[0].records == ('outcome',)
        assert policy.permissions == WANT


def test_the_same_inputs_give_the_same_bytes():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pack = _pack(root / 'p', 'plain', CHECK, None)
        first = _build(root, _v4(), pack, name='a.toml').read_bytes()
        second = _build(root, _v4(), pack, name='b.toml').read_bytes()
        assert first == second


if __name__ == '__main__':
    run_module(globals(), 'policy build with permissions')

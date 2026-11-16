#!/usr/bin/env python3
"""Checks of `kit policy build` with recording checkers (policy version 3).

Contract under test:
- a pack's `[[checker]]` table accepts `records`, validated as a policy's;
- the build writes version 3, with `records = [...]` after `budget_ms` in the
  order given, when any checker of the base or of the packs records; otherwise
  version 2, as before;
- the base may be a version 1, 2 or 3 policy, and a base checker's `records`
  is carried over;
- a recording checker without a callable `record` is refused (exit 64,
  nothing written), with the reason `checker '<id>' defines no callable
  record`.

Stdlib-runnable: `python test_policy_build_v3.py`.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.policy import load_policy
from kit_fixtures import SAMPLE_POLICY, SRC, run_module

_STATE = tempfile.TemporaryDirectory()

CHECK = 'def check(act, observation):\n    return {"result": "no-match"}\n'
RECORDING = CHECK + 'def record(note, facts):\n    return {"result": "unchanged"}\n'


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


def _fwd(path: Path) -> str:
    return os.path.abspath(path).replace('\\', '/')


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


def _build(root: Path, base: Path, *packs: Path, name: str = 'built.toml'):
    out = root / 'out' / name
    out.parent.mkdir(exist_ok=True)
    args = ['policy', 'build', '--base', str(base)]
    for pack in packs:
        args += ['--pack', str(pack)]
    return _kit(*args, '--out', str(out)), out


def _base(root: Path, text: str = SAMPLE_POLICY) -> Path:
    base = root / 'base.toml'
    base.write_bytes(text.encode('utf-8'))
    return base


def _refused(proc: subprocess.CompletedProcess, out: Path, needle: str) -> None:
    assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
    assert needle in proc.stderr, proc.stderr
    assert not out.exists(), sorted(out.parent.iterdir())
    assert not out.with_name(out.name + '.packs.json').exists()


def test_a_pack_with_records_builds_version_3_that_loads_with_the_same_fields():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plain = _pack(root / 'plain', 'plain-check', CHECK, None)
        notes = _pack(root / 'notes', 'series-check', RECORDING, '["outcome", "prompt"]')
        proc, out = _build(root, _base(root), plain, notes)
        assert proc.returncode == 0, proc.stderr
        text = out.read_text(encoding='ascii')
        assert text.startswith('version = 3\n'), text
        sha = hashlib.sha256(RECORDING.encode('utf-8')).hexdigest()
        table = (
            '[[checker]]\nid = "series-check"\n'
            f'file = "{_fwd(notes / "series-check.py")}"\n'
            f'sha256 = "{sha}"\nbudget_ms = 250\nrecords = ["outcome", "prompt"]\n\n'
        )
        assert table in text, text
        assert text.count('records') == 1, text
        policy = load_policy(out)
        assert [(c.id, c.records, c.budget_ms) for c in policy.checkers] == [
            ('plain-check', (), 250),
            ('series-check', ('outcome', 'prompt'), 250),
        ]
        assert [r.check for r in policy.rules] == [None, 'plain-check', 'series-check']


def test_a_build_without_records_still_writes_version_2():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proc, out = _build(root, _base(root), _pack(root / 'p', 'plain-check', RECORDING, None))
        assert proc.returncode == 0, proc.stderr
        text = out.read_text(encoding='ascii')
        assert text.startswith('version = 2\n') and 'records' not in text, text


def test_a_version_3_base_carries_its_checker_records_over():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        first = _pack(root / 'first', 'prompt-check', RECORDING, '["prompt"]')
        proc, mid = _build(root, _base(root), first, name='mid.toml')
        assert proc.returncode == 0, proc.stderr
        second = _pack(root / 'second', 'plain-check', CHECK, None)
        proc, out = _build(root, mid, second)
        assert proc.returncode == 0, proc.stderr
        assert out.read_text(encoding='ascii').startswith('version = 3\n')
        policy = load_policy(out)
        assert [(c.id, c.records) for c in policy.checkers] == [
            ('prompt-check', ('prompt',)),
            ('plain-check', ()),
        ]


def test_a_recording_checker_without_record_is_refused():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for n, body in enumerate((CHECK, CHECK + 'record = None\n')):
            pack = _pack(root / f'p{n}', 'series-check', body, '["outcome"]')
            proc, out = _build(root, _base(root), pack, name=f'b{n}.toml')
            _refused(proc, out, "checker 'series-check' defines no callable record")


def test_a_bad_records_in_a_pack_is_refused():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for n, records in enumerate(('[]', '["file"]', '["prompt", "prompt"]', '"prompt"')):
            pack = _pack(root / f'p{n}', 'series-check', RECORDING, records)
            proc, out = _build(root, _base(root), pack, name=f'b{n}.toml')
            _refused(proc, out, 'records')


def test_a_recording_id_that_cannot_name_a_file_is_refused_in_a_pack():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for n, checker_id in enumerate(('Series', 'nul', 'com3')):
            pack = _pack(root / f'p{n}', checker_id, RECORDING, '["outcome"]')
            proc, out = _build(root, _base(root), pack, name=f'b{n}.toml')
            _refused(proc, out, 'recording checker id')


if __name__ == '__main__':
    run_module(globals(), 'policy build with records')

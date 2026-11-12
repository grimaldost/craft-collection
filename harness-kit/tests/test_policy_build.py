#!/usr/bin/env python3
"""Checks of rule packs and `kit policy build`.

Contract under test:
- `kit policy build --base FILE --pack DIR ... --out FILE [--force]` writes a
  version 2 policy: the base's launcher table, the base's rules then each
  pack's rules in argument order, every checker with its `file` absolute in
  forward-slash form and its `sha256` computed from its bytes;
- the policy is written with the build's own TOML writer (basic strings, every
  character outside U+0020..U+007E escaped, keys in a fixed order, LF), loads
  with `load_policy`, equals its inputs field for field, and is the same bytes
  for the same inputs;
- `<out>.packs.json` holds exactly `kit_packs`, `policy_sha256` and `packs`
  (`name`, `folder`, `rules`, `prevention`);
- every refusal exits 64 and writes nothing;
- each checker is loaded once within its `budget_ms`, with descriptors 1 and 2
  at the null device for the load only, so the build's own messages still
  reach standard error; a load that hangs does not hold the build open.

Stdlib-runnable: `python test_policy_build.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import packs
from harness_kit.policy import PolicyError, load_policy
from kit_fixtures import SAMPLE_POLICY, SRC, event, run_module

_STATE = tempfile.TemporaryDirectory()

MATCH = 'def check(act, observation):\n    return {"result": "match", "detail": "seen"}\n'
NO_MATCH = 'def check(act, observation):\n    return {"result": "no-match"}\n'
TRICKY_REASON = 'use `uv add` <pkg> "now" \u00e9 \U0001f600 \x7f end'


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env['PYTHONPATH'] = str(SRC)
    env['KIT_STATE_ROOT'] = _STATE.name
    env.update(extra)
    return env


def _kit(*args: str, stdin: bytes = b'', timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=stdin,
        capture_output=True,
        env=_env(),
        timeout=timeout,
    )


def _fwd(path: Path) -> str:
    return os.path.abspath(path).replace('\\', '/')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pack(
    folder: Path,
    name: str,
    rule_ids: tuple[str, ...],
    checker_id: str,
    body: str = MATCH,
    reason: str = 'use uv',
    prevention: bool = True,
    extra_top: str = '',
    file: str | None = None,
) -> Path:
    """Write a pack folder with one checker and rules that call it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{checker_id}.py').write_bytes(body.encode('utf-8'))
    # Written by hand, not by the writer under test: raw UTF-8, DEL escaped as TOML requires.
    escaped = reason.replace('\\', '\\\\').replace('"', '\\"').replace('\x7f', '\\u007F')
    reason_toml = f'"{escaped}"'
    lines = [f'pack = 1\nname = "{name}"\n{extra_top}\n']
    lines.append(
        f'[[checker]]\nid = "{checker_id}"\nfile = "{file or checker_id + ".py"}"\n'
        'budget_ms = 250\n\n'
    )
    for rid in rule_ids:
        lines.append(
            f'[[rule]]\nid = "{rid}"\neffect = "deny"\ngoverned = false\n'
            f'kinds = ["shell"]\ncheck = "{checker_id}"\nreason = {reason_toml}\n\n'
        )
    if prevention:
        lines.append(f'[prevention]\nrule = "{rule_ids[0]}"\nlayer = "a layer of {name}"\n')
    (folder / 'pack.toml').write_bytes(''.join(lines).encode('utf-8'))
    return folder


class Tree:
    """A scratch folder with a version 1 base and two packs."""

    def __init__(self, td: str) -> None:
        self.root = Path(td)
        self.base = self.root / 'base.toml'
        self.base.write_bytes(SAMPLE_POLICY.encode('utf-8'))
        self.pack_a = _pack(
            self.root / 'pa', 'alpha', ('a-one', 'a-two'), 'ca', reason=TRICKY_REASON
        )
        self.pack_b = _pack(self.root / 'pb', 'beta', ('b-one',), 'cb', body=NO_MATCH)
        self.out = self.root / 'out' / 'built.toml'
        self.out.parent.mkdir()

    def build(self, *extra: str, out: Path | None = None, packs_: tuple[Path, ...] | None = None):
        args = ['policy', 'build', '--base', str(self.base)]
        for pack in (self.pack_a, self.pack_b) if packs_ is None else packs_:
            args += ['--pack', str(pack)]
        args += ['--out', str(out or self.out), *extra]
        return _kit(*args)

    def sidecar(self, out: Path | None = None) -> Path:
        out = out or self.out
        return out.with_name(out.name + '.packs.json')


def _ok(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, (proc.returncode, proc.stderr)


def _refused(tree: Tree, proc: subprocess.CompletedProcess, out: Path | None = None) -> None:
    assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
    assert b'kit:' in proc.stderr, proc.stderr
    out = out or tree.out
    assert not out.exists() and not tree.sidecar(out).exists(), sorted(out.parent.iterdir())


def test_build_orders_rules_and_pins_checkers_by_absolute_path_and_hash():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _ok(tree.build())
        policy = load_policy(tree.out)
        assert [r.id for r in policy.rules] == ['no-config-write', 'a-one', 'a-two', 'b-one']
        assert [c.id for c in policy.checkers] == ['ca', 'cb']
        text = tree.out.read_text(encoding='ascii')
        for pack, cid in ((tree.pack_a, 'ca'), (tree.pack_b, 'cb')):
            path = pack / f'{cid}.py'
            assert f'file = "{_fwd(path)}"' in text, text
            assert f'sha256 = "{_sha(path.read_bytes())}"' in text, text
        assert text.startswith('version = 2\n'), text
        assert '\r' not in text and text.endswith('\n'), text


def test_build_is_the_same_bytes_on_a_second_run():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        second = tree.root / 'out' / 'again.toml'
        _ok(tree.build())
        _ok(tree.build(out=second))
        assert tree.out.read_bytes() == second.read_bytes()
        assert tree.sidecar().read_bytes() == tree.sidecar(second).read_bytes()


def test_build_round_trips_every_field_of_the_base_and_the_packs():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _ok(tree.build())
        base = load_policy(tree.base)
        built = load_policy(tree.out)
        assert (
            built.launcher
            == base.launcher
            == {
                'test_roots': ['/abs/path'],
                'forbidden_roots': [],
            }
        )
        first = built.rules[0]
        want = base.rules[0]
        assert first.command_regex.pattern == want.command_regex.pattern == 'settings\\.json'
        assert [g.pattern for g in first.path_globs] == [g.pattern for g in want.path_globs]
        assert (first.id, first.effect, first.governed, first.kinds) == (
            want.id,
            want.effect,
            want.governed,
            want.kinds,
        )
        assert (first.origin_in, first.reason, first.check) == (
            want.origin_in,
            want.reason,
            None,
        )
        for rule in built.rules[1:3]:
            assert rule.reason == TRICKY_REASON, ascii(rule.reason)
            assert (rule.effect, rule.governed, rule.kinds, rule.check) == (
                'deny',
                False,
                ('shell',),
                'ca',
            )
        assert built.rules[3].check == 'cb'
        assert [c.budget_ms for c in built.checkers] == [250, 250]
        assert tree.out.read_bytes().isascii()


def test_toml_string_escapes_everything_outside_printable_ascii():
    assert packs.toml_string('a\\b"c') == '"a\\\\b\\"c"'
    assert packs.toml_string('\t\x7f\u00e9') == '"\\u0009\\u007F\\u00E9"'
    assert packs.toml_string('\U0001f600') == '"\\U0001F600"'
    assert packs.toml_string('`<>` ~') == '"`<>` ~"'


def test_sidecar_holds_exactly_the_stated_fields():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _ok(tree.build())
        data = json.loads(tree.sidecar().read_bytes())
        assert list(data) == ['kit_packs', 'policy_sha256', 'packs'], data
        assert data['kit_packs'] == 1
        assert data['policy_sha256'] == _sha(tree.out.read_bytes())
        assert data['packs'] == [
            {
                'name': 'alpha',
                'folder': _fwd(tree.pack_a),
                'rules': ['a-one', 'a-two'],
                'prevention': {'rule': 'a-one', 'layer': 'a layer of alpha'},
            },
            {
                'name': 'beta',
                'folder': _fwd(tree.pack_b),
                'rules': ['b-one'],
                'prevention': {'rule': 'b-one', 'layer': 'a layer of beta'},
            },
        ]
        for pack in data['packs']:
            assert list(pack) == ['name', 'folder', 'rules', 'prevention'], pack


def test_a_pack_without_prevention_records_null():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _pack(tree.pack_b, 'beta', ('b-one',), 'cb', prevention=False)
        _ok(tree.build())
        data = json.loads(tree.sidecar().read_bytes())
        assert data['packs'][1]['prevention'] is None, data


def test_a_version_2_base_keeps_its_checkers_first():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        own = tree.root / 'own_check.py'
        own.write_bytes(MATCH.encode('utf-8'))
        tree.base.write_bytes(
            (
                'version = 2\n[launcher]\ntest_roots = []\n\n'
                f'[[checker]]\nid = "base-c"\nfile = "own_check.py"\nsha256 = "{_sha(own.read_bytes())}"\n\n'
                '[[rule]]\nid = "base-r"\neffect = "deny"\ngoverned = true\nkinds = ["shell"]\n'
                'check = "base-c"\n'
            ).encode()
        )
        _ok(tree.build())
        built = load_policy(tree.out)
        assert [c.id for c in built.checkers] == ['base-c', 'ca', 'cb']
        assert [c.budget_ms for c in built.checkers] == [250, 250, 250]
        assert built.rules[0].check == 'base-c' and built.rules[0].governed is True
        assert f'file = "{_fwd(own)}"' in tree.out.read_text(encoding='ascii')
        assert built.launcher == {'test_roots': []}


def test_a_built_policy_judged_gives_the_checkers_verdict():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _ok(tree.build())
        stdin = json.dumps(event()).encode('utf-8')
        proc = _kit('judge', '--policy', str(tree.out), stdin=stdin)
        assert proc.returncode == 0, proc.stderr
        verdict = json.loads(proc.stdout)
        assert (verdict['verdict'], verdict['rule']) == ('deny', 'a-one'), verdict
        assert verdict['reason'] == 'seen ' + TRICKY_REASON, ascii(verdict['reason'])


def test_moving_a_pack_after_the_build_makes_the_policy_unreadable():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _ok(tree.build())
        load_policy(tree.out)
        shutil.move(str(tree.pack_a), str(tree.root / 'moved'))
        try:
            load_policy(tree.out)
        except PolicyError as exc:
            assert 'cannot be read' in str(exc), exc
        else:
            raise AssertionError('a moved pack left the policy readable')


def _refusal_cases(tree: Tree) -> list[tuple[str, object]]:
    """(label, setup) pairs; each setup breaks one input of a fresh tree."""

    def base_text(text: str):
        return lambda: tree.base.write_bytes(text.encode('utf-8'))

    def pack_a(**kw):
        return lambda: _pack(tree.pack_a, 'alpha', ('a-one',), 'ca', **kw)

    def remove(path: Path):
        return lambda: path.unlink()

    absolute = _fwd(tree.root / 'elsewhere.py')
    return [
        ('base missing', remove(tree.base)),
        ('base not TOML', base_text('version = = 1\n')),
        ('base unknown key', base_text('extra = 1\n' + SAMPLE_POLICY)),
        ('base rule unknown key', base_text(SAMPLE_POLICY + 'colour = "red"\n')),
        (
            'base launcher key',
            base_text(SAMPLE_POLICY.replace('forbidden_roots = []', 'forbidden_roots = []\nx = 1')),
        ),
        ('base version 3', base_text(SAMPLE_POLICY.replace('version = 1', 'version = 3'))),
        ('pack.toml missing', remove(tree.pack_a / 'pack.toml')),
        ('pack not TOML', lambda: (tree.pack_a / 'pack.toml').write_bytes(b'pack = = 1\n')),
        ('pack unknown key', pack_a(extra_top='colour = "red"')),
        ('pack version 2', _pack_version(tree, 2)),
        (
            'pack rule repeats base rule',
            lambda: _pack(tree.pack_a, 'alpha', ('no-config-write',), 'ca'),
        ),
        ('rule repeats across packs', lambda: _pack(tree.pack_a, 'alpha', ('b-one',), 'ca')),
        ('checker repeats across packs', lambda: _pack(tree.pack_a, 'alpha', ('a-one',), 'cb')),
        ('file absolute', pack_a(file=absolute)),
        ('file with ..', pack_a(file='../pb/cb.py')),
        ('file inner ..', pack_a(file='sub/../ca.py')),
        ('file missing', pack_a(file='nowhere.py')),
        ('checker syntax error', pack_a(body='def check(:\n')),
        ('checker no check', pack_a(body='x = 1\n')),
        ('checker check not callable', pack_a(body='check = 3\n')),
        ('checker raises at load', pack_a(body='raise SystemExit(3)\n')),
        ('budget out of range', lambda: _budget(tree, 501)),
        ('rule unknown key', lambda: _rule_key(tree)),
        ('check names no checker', lambda: _check_names(tree, 'nope')),
        (
            'prevention unknown key',
            lambda: _prevention(tree, 'rule = "a-one"\nlayer = "x"\nmore = 1\n'),
        ),
        ('prevention names no rule', lambda: _prevention(tree, 'rule = "zzz"\nlayer = "x"\n')),
    ]


def _edit_pack_a(tree: Tree, old: str, new: str) -> None:
    path = tree.pack_a / 'pack.toml'
    text = path.read_text(encoding='utf-8')
    assert old in text, (old, text)
    path.write_bytes(text.replace(old, new, 1).encode('utf-8'))


def _pack_version(tree: Tree, n: int):
    return lambda: _edit_pack_a(tree, 'pack = 1', f'pack = {n}')


def _budget(tree: Tree, ms: int) -> None:
    _edit_pack_a(tree, 'budget_ms = 250', f'budget_ms = {ms}')


def _rule_key(tree: Tree) -> None:
    _edit_pack_a(tree, 'effect = "deny"', 'effect = "deny"\ncolour = "red"')


def _check_names(tree: Tree, name: str) -> None:
    _edit_pack_a(tree, 'check = "ca"', f'check = "{name}"')


def _prevention(tree: Tree, body: str) -> None:
    path = tree.pack_a / 'pack.toml'
    text = path.read_text(encoding='utf-8').split('[prevention]')[0]
    path.write_bytes((text + '[prevention]\n' + body).encode('utf-8'))


def test_each_refusal_exits_64_and_writes_nothing():
    labels = [label for label, _ in _refusal_cases(Tree(tempfile.mkdtemp(dir=_STATE.name)))]
    for label in labels:
        with tempfile.TemporaryDirectory() as td:
            tree = Tree(td)
            setup = dict(_refusal_cases(tree))[label]
            setup()
            proc = tree.build()
            try:
                _refused(tree, proc)
            except AssertionError as exc:
                raise AssertionError(f'{label}: {exc}') from None


def test_an_existing_output_or_sidecar_needs_force():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        tree.out.write_bytes(b'old\n')
        proc = tree.build()
        assert proc.returncode == 64, proc.stderr
        assert tree.out.read_bytes() == b'old\n' and not tree.sidecar().exists()
        tree.out.unlink()
        tree.sidecar().write_bytes(b'old\n')
        proc = tree.build()
        assert proc.returncode == 64, proc.stderr
        assert not tree.out.exists() and tree.sidecar().read_bytes() == b'old\n'
        _ok(tree.build('--force'))
        load_policy(tree.out)
        data = json.loads(tree.sidecar().read_bytes())
        assert data['policy_sha256'] == _sha(tree.out.read_bytes())


def test_the_builds_message_after_a_noisy_checker_still_reaches_stderr():
    noisy = (
        'import os, subprocess, sys\n'
        'print("NOISE-OUT")\n'
        'print("NOISE-ERR", file=sys.stderr)\n'
        'os.write(1, b"NOISE-FD1\\n")\n'
        'os.write(2, b"NOISE-FD2\\n")\n'
        'subprocess.run([sys.executable, "-c", "print(\'NOISE-CHILD\')"])\n'
        'def check(act, observation):\n    return {"result": "match"}\n'
    )
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _pack(tree.pack_a, 'alpha', ('a-one',), 'ca', body=noisy)
        _pack(tree.pack_b, 'beta', ('b-one',), 'cb', body='def check(:\n')
        proc = tree.build()
        _refused(tree, proc)
        assert b"'cb'" in proc.stderr, proc.stderr
        assert b'NOISE' not in proc.stdout + proc.stderr, (proc.stdout, proc.stderr)
        _pack(tree.pack_b, 'beta', ('b-one',), 'cb')
        proc = tree.build()
        _ok(proc)
        assert b'kit: policy written' in proc.stderr, proc.stderr
        assert b'NOISE' not in proc.stdout + proc.stderr, (proc.stdout, proc.stderr)


def test_a_checker_that_hangs_while_it_loads_is_refused_within_its_budget():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _pack(tree.pack_a, 'alpha', ('a-one',), 'ca', body='import time\ntime.sleep(10)\n' + MATCH)
        start = time.monotonic()
        proc = tree.build()
        elapsed = time.monotonic() - start
        _refused(tree, proc)
        assert b'did not load within 250 ms' in proc.stderr, proc.stderr
        assert elapsed < 0.25 + 2, elapsed


def test_verify_checkers_restores_the_streams_after_each_load():
    script = (
        'import os, sys\n'
        'from harness_kit import packs\n'
        'from harness_kit.policy import load_policy\n'
        'reason = packs.verify_checkers(load_policy(sys.argv[1]).checkers)\n'
        'print("AFTER-OUT", reason)\n'
        'sys.stdout.flush()\n'
        'os.write(2, b"AFTER-FD2\\n")\n'
    )
    noisy = 'print("NOISE")\nimport os\nos.write(2, b"NOISE\\n")\n' + MATCH
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _pack(tree.pack_a, 'alpha', ('a-one',), 'ca', body=noisy)
        _ok(tree.build())
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, '-c', script, str(tree.out)],
            capture_output=True,
            env=_env(),
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == b'AFTER-OUT None' + os.linesep.encode(), proc.stdout
        assert proc.stderr == b'AFTER-FD2\n', proc.stderr


def test_verify_checkers_names_the_first_checker_that_fails():
    with tempfile.TemporaryDirectory() as td:
        tree = Tree(td)
        _ok(tree.build())
        policy = load_policy(tree.out)
        assert packs.verify_checkers(policy.checkers) is None
        broken = tree.root / 'broken.py'
        broken.write_bytes(b'x = 1\n')
        bad = type(policy.checkers[0])(
            id='broken', path=str(broken), sha256=_sha(b'x = 1\n'), source=b'x = 1\n'
        )
        reason = packs.verify_checkers((*policy.checkers, bad))
        assert reason is not None and "'broken'" in reason, reason


if __name__ == '__main__':
    run_module(globals(), 'policy build')

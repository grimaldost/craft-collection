#!/usr/bin/env python3
"""Checks of the uv rule pack: its checker answers what the plugin's core answers.

Contract under test:
- the checker, loaded the way the judge loads it, answers `match` exactly when
  the live core's `verdict(command, cwd_is_uv_project(cwd), allow)` returns
  `block`, else `no-match`, with `allow` read from `CLAUDE_ALLOW_PIP`; parity
  runs over this file's own corpus and over every pair of command and
  `allow_env` the plugin's own tests pass to `verdict`, collected by a
  recorder, in two kinds of uv folder and in a folder that is neither;
- a `match` carries the detail ``Blocked `<words>`.``, the words being what
  the core's `blocked_match` names;
- it answers `cannot-tell` when the command was not observed or the working
  directory is not a non-empty string;
- `pack.toml`'s `reason` is the plugin's `block_message()`;
- a policy built from the pack denies `pip install requests` in a uv folder
  with the detail and the guidance text, and the judgement leaves no bytecode
  cache under `plugins/`;
- without the core, the checker does not execute and the build exits 64.

Stdlib-runnable: `python test_uv_rule.py`.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json  # noqa: E402 - bytecode writing is off before any other import
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import tomllib  # noqa: E402

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]
ROOT = HERE.parents[2]
SRC = KIT / 'src'
HOOKS = ROOT / 'plugins' / 'engineering-discipline' / 'hooks'
for _folder in (SRC, HOOKS):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import harness_adapters  # noqa: E402
import test_uv_enforce  # noqa: E402
import uv_enforce  # noqa: E402
from harness_kit import checkers, packs  # noqa: E402
from harness_kit.policy import load_policy  # noqa: E402

ALLOW_ENV = 'CLAUDE_ALLOW_PIP'
RULE_ID = 'uv-project-uses-uv'
CHECKER_ID = 'uv-rule'
SCRATCH = tempfile.TemporaryDirectory()

# Every arm of the core's blocked list, the shapes it leaves alone, and the
# commands of the rule cells on the real harnesses.
CORPUS = (
    'pip install requests',
    'pip3 install requests',
    'cd a && pip3   install x',
    'python -m pip install requests',
    'python3 -m pip install requests',
    'poetry add x',
    'poetry install',
    'poetry update requests',
    'pipenv install',
    'conda install pkg',
    'virtualenv .venv',
    'echo x | virtualenv .venv',
    'python -m venv .venv',
    'python3 -m venv .venv',
    'py -m pip install requests',
    'py -3 -m pip install requests',
    'py -3.12 -m pip install requests',
    'py -m venv .venv',
    'py -3 -m venv .venv',
    'result=$(pip install requests)',
    'echo setting up\npip install requests',
    'echo probe > uv-deny.marker; pip install --help',
    'echo "pip install" > uv-allow-mention.marker',
    'grep -rn "pip install" docs/',
    "grep -rn 'pip install' docs/",
    'git commit -m "document how to pip install foo"',
    'ls  # remember: pip install requests later',
    'ls # virtualenv .venv',
    "cat > notes.md <<'EOF'\npip install requests\nEOF",
    'cat > table.md <<EOF\n| virtualenv | 21.3.0 |\nEOF',
    'tee notes.md <<EOF\npython -m venv .venv\nEOF',
    'cat <<EOF\n$(pip install x)\nEOF',
    'uv pip install requests',
    'uv pip install -r requirements.txt',
    'uv add requests',
    'uv sync',
    'python -m pytest',
    'echo anaconda',
    'happy -m pip install',
    '',
)


def _folders() -> dict[str, str]:
    """Two uv folders of different kinds and one folder that is neither."""
    base = Path(SCRATCH.name) / 'cwd'
    lock = base / 'uv-lock'
    table = base / 'tool-uv'
    plain = base / 'plain'
    for folder in (lock, table, plain):
        folder.mkdir(parents=True, exist_ok=True)
    (lock / 'uv.lock').write_bytes(b'')
    (table / 'pyproject.toml').write_bytes(b'[project]\nname = "x"\n\n[tool.uv]\n')
    return {'uv.lock': str(lock), '[tool.uv]': str(table), 'neither': str(plain)}


FOLDERS = _folders()


def _policy(pack: Path, where: Path):
    """A policy built from a version 1 base and `pack`, written under `where`."""
    where.mkdir(parents=True, exist_ok=True)
    base = where / 'base.toml'
    base.write_bytes(b'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n')
    out, _ = packs.build(base, [pack], where / 'policy.toml')
    return load_policy(out)


POLICY = _policy(HERE, Path(SCRATCH.name) / 'built')
CHECKER = next(c for c in POLICY.checkers if c.id == CHECKER_ID)
CHECK = checkers.execute(CHECKER).check


def _act(command: object, cwd: object) -> dict:
    return {
        'kind': 'shell',
        'command': command,
        'argv': None,
        'paths': [],
        'cwd': cwd,
        'payload_sha256': 'a' * 64,
    }


def _observation(command: str = 'observed') -> dict:
    return {
        'session': 'observed',
        'parent': 'unavailable',
        'root': 'unavailable',
        'origin': 'unavailable',
        'command': command,
        'paths': 'not_applicable',
    }


class _Override:
    """`CLAUDE_ALLOW_PIP` set to `1` when `allow` is true, unset otherwise; restored after."""

    def __init__(self, allow: bool) -> None:
        self.allow = allow
        self.saved = os.environ.get(ALLOW_ENV)

    def __enter__(self) -> None:
        if self.allow:
            os.environ[ALLOW_ENV] = '1'
        else:
            os.environ.pop(ALLOW_ENV, None)

    def __exit__(self, *exc: object) -> None:
        if self.saved is None:
            os.environ.pop(ALLOW_ENV, None)
        else:
            os.environ[ALLOW_ENV] = self.saved


def _recorded_pairs() -> list[tuple[str, bool]]:
    """Every (command, allow_env) the plugin's own tests pass to `verdict`, in first-seen order.

    The test module's name `verdict` is replaced by a recorder that returns the
    real result, so the calls through the helper `_v` and through a variable
    are recorded as well as the literal ones.
    """
    calls: list[tuple[str, bool]] = []
    real = uv_enforce.verdict

    def recorder(command, cwd_has_uv, allow_env):
        calls.append((command, allow_env))
        return real(command, cwd_has_uv, allow_env)

    saved = test_uv_enforce.verdict
    test_uv_enforce.verdict = recorder
    try:
        for name, fn in sorted(vars(test_uv_enforce).items()):
            if name.startswith('test_') and callable(fn):
                fn()
    finally:
        test_uv_enforce.verdict = saved
    return list(dict.fromkeys(calls))


def _assert_parity(command: str, allow: bool, cwd: str) -> str:
    """Check one row against the live core; return the checker's result."""
    with _Override(allow):
        got = CHECK(_act(command, cwd), _observation())
    expected = uv_enforce.verdict(command, uv_enforce.cwd_is_uv_project(cwd), allow)
    row = (command, allow, cwd, got, expected)
    assert checkers.read_return(got)[0] == got['result'], row
    assert got['result'] == ('match' if expected == 'block' else 'no-match'), row
    if got['result'] == 'match':
        assert got == {
            'result': 'match',
            'detail': f'Blocked `{uv_enforce.blocked_match(command)}`.',
        }, row
    else:
        assert got == {'result': 'no-match'}, row
    return got['result']


def test_parity_with_the_core_over_its_own_corpus():
    seen = set()
    for cwd in FOLDERS.values():
        for allow in (False, True):
            for command in CORPUS:
                seen.add(_assert_parity(command, allow, cwd))
    assert seen == {'match', 'no-match'}, seen


def test_parity_with_the_core_over_the_plugins_own_vectors():
    pairs = _recorded_pairs()
    assert len(pairs) >= 160, len(pairs)
    assert {allow for _, allow in pairs} == {False, True}
    matched = 0
    for cwd in FOLDERS.values():
        for command, allow in pairs:
            matched += _assert_parity(command, allow, cwd) == 'match'
    assert matched > 0


def test_a_uv_folder_of_each_kind_is_one_and_the_plain_folder_is_not():
    assert uv_enforce.cwd_is_uv_project(FOLDERS['uv.lock'])
    assert uv_enforce.cwd_is_uv_project(FOLDERS['[tool.uv]'])
    assert not uv_enforce.cwd_is_uv_project(FOLDERS['neither'])
    with _Override(False):
        for kind in ('uv.lock', '[tool.uv]'):
            got = CHECK(_act('pip install requests', FOLDERS[kind]), _observation())
            assert got == {'result': 'match', 'detail': 'Blocked `pip install`.'}, (kind, got)
        got = CHECK(_act('pip install requests', FOLDERS['neither']), _observation())
        assert got == {'result': 'no-match'}, got


def test_the_override_turns_a_match_into_no_match():
    with _Override(True):
        got = CHECK(_act('pip install requests', FOLDERS['uv.lock']), _observation())
    assert got == {'result': 'no-match'}, got
    with _Override(False):
        os.environ[ALLOW_ENV] = 'yes'
        got = CHECK(_act('pip install requests', FOLDERS['uv.lock']), _observation())
    assert got['result'] == 'match', got


def test_cannot_tell_without_an_observed_command():
    for observed in ('unavailable', 'not_applicable'):
        with _Override(False):
            got = CHECK(_act('pip install requests', FOLDERS['uv.lock']), _observation(observed))
        assert got == {'result': 'cannot-tell'}, (observed, got)


def test_cannot_tell_without_a_working_directory():
    for cwd in (None, '', 7, ['/w']):
        with _Override(False):
            got = CHECK(_act('pip install requests', cwd), _observation())
        assert got == {'result': 'cannot-tell'}, (cwd, got)


def test_the_pack_reason_is_the_plugins_guidance():
    data = tomllib.loads((HERE / 'pack.toml').read_text(encoding='utf-8'))
    (rule,) = data['rule']
    assert rule['reason'] == harness_adapters.block_message(), rule['reason']
    assert rule['id'] == RULE_ID
    assert rule['check'] == CHECKER_ID
    assert rule['governed'] is False
    assert rule['kinds'] == ['shell']
    assert data['prevention']['rule'] == RULE_ID
    (built,) = [r for r in POLICY.rules if r.id == RULE_ID]
    assert built.reason == harness_adapters.block_message()


def _copy_tree(dest: Path, with_core: bool = True) -> Path:
    """A scratch copy of the pack and, unless told otherwise, of the core it imports."""
    pack = dest / 'harness-kit' / 'packs' / 'uv'
    pack.mkdir(parents=True)
    for name in ('pack.toml', 'uv_rule.py'):
        shutil.copyfile(HERE / name, pack / name)
    hooks = dest / 'plugins' / 'engineering-discipline' / 'hooks'
    hooks.mkdir(parents=True)
    for name in ('uv_enforce.py', 'hook_log.py'):
        if with_core or name != 'uv_enforce.py':
            shutil.copyfile(HOOKS / name, hooks / name)
    return pack


def _kit_env(tree: Path) -> dict:
    """The environment of a child run in `tree`: bytecode writing left on, its cache under `tree`.

    Only the checker may turn bytecode writing off, so the variable that would
    do it for the whole process is removed; the cache prefix keeps the
    package's own bytecode out of the repository and shows what was written.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    for name in (ALLOW_ENV, 'PYTHONDONTWRITEBYTECODE'):
        env.pop(name, None)
    env['PYTHONPATH'] = str(SRC)
    env['PYTHONPYCACHEPREFIX'] = str(tree / 'pycache')
    env['KIT_STATE_ROOT'] = str(tree / 'state')
    return env


def _kit(tree: Path, *args: str, stdin: bytes = b'') -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=stdin,
        capture_output=True,
        env=_kit_env(tree),
        timeout=60,
    )


def _core_bytecode(tree: Path) -> list[Path]:
    """Bytecode of the core's folder anywhere in `tree`, cache prefix included."""
    return [
        p
        for p in tree.rglob('*')
        if p.name == '__pycache__'
        or (p.suffix == '.pyc' and p.name.startswith(('uv_enforce.', 'hook_log.')))
    ]


def _event(command: str, cwd: str) -> bytes:
    event = {
        'kit_event': 1,
        'run_id': None,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': 's1', 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': _observation(),
        'act': _act(command, cwd),
    }
    return json.dumps(event).encode('ascii')


def test_a_built_policy_denies_pip_install_with_the_guidance_and_writes_no_cache():
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    pack = _copy_tree(tree)
    base = tree / 'base.toml'
    base.write_bytes(b'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n')
    out = tree / 'policy.toml'
    built = _kit(
        tree, 'policy', 'build', '--base', str(base), '--pack', str(pack), '--out', str(out)
    )
    assert built.returncode == 0, built
    judged = _kit(
        tree,
        'judge',
        '--policy',
        str(out),
        stdin=_event('pip install requests', FOLDERS['uv.lock']),
    )
    assert judged.returncode == 0, judged
    lines = judged.stdout.decode('ascii').splitlines()
    assert len(lines) == 1, judged
    verdict = json.loads(lines[0])
    assert verdict['verdict'] == 'deny', verdict
    assert verdict['governed'] is False, verdict
    assert verdict['rule'] == RULE_ID, verdict
    assert verdict['reason'] == 'Blocked `pip install`. ' + harness_adapters.block_message()
    assert any((tree / 'pycache').rglob('*.pyc')), 'the child wrote no bytecode at all'
    assert _core_bytecode(tree) == [], _core_bytecode(tree)


def test_without_the_core_the_checker_does_not_execute_and_the_build_refuses():
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    pack = _copy_tree(tree, with_core=False)
    alone = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(pack / 'uv_rule.py')],
        capture_output=True,
        env=_kit_env(tree),
        timeout=60,
    )
    assert alone.returncode != 0, alone
    assert b'uv_enforce' in alone.stderr, alone
    base = tree / 'base.toml'
    base.write_bytes(b'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n')
    out = tree / 'policy.toml'
    built = _kit(
        tree,
        'policy',
        'build',
        '--base',
        str(base),
        '--pack',
        str(pack),
        '--out',
        str(out),
    )
    assert built.returncode == 64, built
    assert not out.exists()
    assert not packs.sidecar_path(out).exists()


if __name__ == '__main__':
    names = sorted(n for n, f in list(globals().items()) if n.startswith('test_') and callable(f))
    for name in names:
        globals()[name]()
    print(f'ok: uv rule pack ({len(names)} checks)')

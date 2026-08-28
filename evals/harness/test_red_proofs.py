#!/usr/bin/env python3
"""Every shipped check declares how it was proved able to fail.

A check nobody has watched fail is not evidence. The collection learned that
one plugin at a time: `mutate_check.py` proves the data checks redden on a
seeded defect, `test_git_env_isolation.py` sweeps the repo scripts for a
`GIT_*` scrub, `test_router.py` reddens its own backtracking detector. Each was
built after a specific green-while-hollow incident, and none of them stops the
NEXT check from shipping with no red proof at all -- which is how nine of them
did.

This is a registry, not a detector. Asserting "this test really proves that
script can fail" by parsing assertions would be a gate that is easy to fool and
hard to trust, which is the failure mode it exists to prevent. Instead:

  * every shipped script is classified in `scripts/red_proofs.json` -- proved,
    a declared gap, or exempt -- and an UNCLASSIFIED script fails this test, so
    a new check cannot ship without someone deciding which it is;
  * a declared proof must name a test function that exists AND actually runs
    under `run_tests.py` (bare `python`), because a `def test_x` no runner
    block calls is dead code that reads as coverage;
  * declared gaps are a burn-down list that is visible instead of invisible.

What that costs, stated plainly: a registry is exactly as good as the honesty of
whoever seeds it. Nothing here can distinguish a true entry from a plausible one
-- a named test that exists, runs, and never exercises the reject path passes
every check above. One such entry was written during the seeding pass itself and
caught only by its author re-reading it. So a new or re-seeded entry is reviewed
as EVIDENCE, not as configuration: open the named test and confirm it asserts
the reject path. The first seeding is where a wrong entry is cheapest to make
and hardest to see.

The registry's `proofs` accept three reddening shapes, because the collection
ships all three: a non-zero exit from `main()`, a non-empty findings/errors
list from a pure core, and a `decision: block` payload from a hook. A test
module whose assertions live in its own `main()` rather than in `def test_*`
functions -- four do -- is named as `<path>::main`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / 'scripts' / 'red_proofs.json'

# The shipped-script family. Mirrors the enumeration style of
# test_git_env_isolation.py's repo-script sweep, widened to the plugins.
FAMILY = (
    'scripts/*.py',
    'plugins/*/skills/*/scripts/*.py',
    'plugins/*/hooks/*.py',
    'evals/harness/*.py',
)

_REFLECTIVE_RUNNER = re.compile(r"globals\(\)\.items\(\)|name\.startswith\(\s*'test_'\s*\)")


def shipped_scripts(root: Path = ROOT) -> list[str]:
    """Repo-relative posix paths of every shipped script, test modules and
    package markers excluded. Pure but for the glob."""
    out: set[str] = set()
    for pattern in FAMILY:
        for path in root.glob(pattern):
            if path.name.startswith('test_') or path.name == '__init__.py':
                continue
            out.add(path.relative_to(root).as_posix())
    return sorted(out)


def load_registry(path: Path = REGISTRY) -> dict:
    """The registry, or empty buckets when it cannot be read. Empty is the
    strictest reading: every script then reads as unclassified and fails."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'proofs': {}, 'gaps': {}, 'exempt': {}}
    return {k: data.get(k) or {} for k in ('proofs', 'gaps', 'exempt')}


def classify(scripts: list[str], registry: dict) -> dict[str, list[str]]:
    """Split `scripts` against the registry. Pure.

    `unclassified` is the one that gates a new check; `stale` catches a registry
    entry whose script was deleted or moved, so the file does not rot into a
    list of promises about files that no longer exist; `double` catches a script
    claimed by two buckets, where the weaker claim would otherwise hide.
    """
    known = {b: set(registry.get(b) or {}) for b in ('proofs', 'gaps', 'exempt')}
    every = set().union(*known.values())
    counts = {s: sum(s in v for v in known.values()) for s in every}
    return {
        'unclassified': sorted(set(scripts) - every),
        'stale': sorted(every - set(scripts)),
        'double': sorted(s for s, n in counts.items() if n > 1),
    }


def runs_under_bare_python(test_src: str, fn: str) -> bool:
    """Would `python <test module>` actually execute `fn`?

    `run_tests.py` runs each module as a bare script, so a test function that
    nothing calls is dead code that still reads as coverage. Three runner
    idioms are in use: an explicit call list under `__main__`, the same list
    inside a `def main()` that `__main__` then calls, and a reflective sweep
    over `globals()`. `main` names the module-is-the-test shape, where the
    assertions live in the module's own `main()`.

    The predicate is "the module has a `__main__` entry point AND something
    calls this function bare" rather than "the name appears after the guard" -
    the narrower reading missed four real, wired-up proofs whose runner list
    sits in a `main()` defined above the guard.
    """
    if "if __name__ == '__main__':" not in test_src:
        return False
    if fn == 'main':
        return 'def main(' in test_src
    if f'def {fn}(' not in test_src:
        return False
    if _REFLECTIVE_RUNNER.search(test_src):
        return True
    return re.search(rf'^\s*{re.escape(fn)}\(\)\s*$', test_src, re.MULTILINE) is not None


def broken_proofs(registry: dict, root: Path = ROOT) -> list[str]:
    """Proof references that do not resolve. Each entry is
    `<test path>::<fn>`; a missing file, a missing function, or a function no
    runner block reaches is a broken proof."""
    problems: list[str] = []
    for script, refs in sorted((registry.get('proofs') or {}).items()):
        for ref in refs if isinstance(refs, list) else [refs]:
            if '::' not in ref:
                problems.append(f'{script}: proof {ref!r} is not <test path>::<function>')
                continue
            rel, fn = ref.split('::', 1)
            test_path = root / rel
            if not test_path.is_file():
                problems.append(f'{script}: proof names a missing test module {rel}')
                continue
            src = test_path.read_text(encoding='utf-8')
            if not runs_under_bare_python(src, fn):
                problems.append(
                    f'{script}: proof {ref} does not run under bare python '
                    '(no such function, or no runner block calls it)'
                )
    return problems


def test_every_shipped_script_is_classified():
    """The structural half: a new check cannot ship without a decision."""
    split = classify(shipped_scripts(), load_registry())
    assert not split['unclassified'], (
        'shipped scripts with no entry in scripts/red_proofs.json:\n  '
        + '\n  '.join(split['unclassified'])
        + '\nAdd each under "proofs" (naming the test that reddens it), "gaps" '
        '(with why it has none yet), or "exempt" (with why it is not a reject check).'
    )


def test_the_registry_does_not_promise_things_about_files_that_are_gone():
    split = classify(shipped_scripts(), load_registry())
    assert not split['stale'], (
        'registry entries for scripts that no longer exist:\n  ' + '\n  '.join(split['stale'])
    )


def test_no_script_is_claimed_by_two_buckets():
    split = classify(shipped_scripts(), load_registry())
    assert not split['double'], 'scripts in more than one bucket:\n  ' + '\n  '.join(
        split['double']
    )


def test_every_declared_proof_resolves_and_actually_runs():
    problems = broken_proofs(load_registry())
    assert not problems, 'broken red-proof references:\n  ' + '\n  '.join(problems)


def test_every_gap_and_exemption_states_a_reason():
    registry = load_registry()
    thin = [
        f'{bucket}:{script}'
        for bucket in ('gaps', 'exempt')
        for script, reason in sorted((registry.get(bucket) or {}).items())
        if not (isinstance(reason, str) and len(reason.strip()) >= 20)
    ]
    assert not thin, (
        'a gap or exemption with no real reason is an unexamined check:\n  ' + '\n  '.join(thin)
    )


def test_the_gate_reddens_on_a_script_it_was_written_for():
    """The detector, made to fail on purpose.

    A green sweep over a fully-classified tree is only evidence if the same
    predicates redden on the cases they exist to catch -- the lesson from
    test_git_env_isolation.py, applied to this gate.
    """
    registry = {'proofs': {}, 'gaps': {}, 'exempt': {'a.py': 'x' * 30}}
    assert classify(['a.py', 'b.py'], registry)['unclassified'] == ['b.py']
    assert classify(['a.py'], registry)['unclassified'] == []
    # a registry promising things about a deleted script
    assert classify([], registry)['stale'] == ['a.py']
    # one script claimed twice
    both = {'proofs': {'a.py': ['t.py::x']}, 'gaps': {'a.py': 'y' * 30}, 'exempt': {}}
    assert classify(['a.py'], both)['double'] == ['a.py']
    # an unreadable registry must be the STRICTEST reading, never a free pass
    assert load_registry(ROOT / 'no' / 'such' / 'registry.json') == {
        'proofs': {},
        'gaps': {},
        'exempt': {},
    }


def test_the_runner_block_predicate_reddens_on_a_test_that_never_runs():
    """The subtle half: `def test_x` that no runner block calls is dead code."""
    dead = "def test_x():\n    assert True\n\nif __name__ == '__main__':\n    print('ok: none')\n"
    live = "def test_x():\n    assert True\n\nif __name__ == '__main__':\n    test_x()\n"
    reflective = (
        'def test_x():\n    assert True\n\n'
        "if __name__ == '__main__':\n"
        '    for name, fn in sorted(globals().items()):\n'
        "        if name.startswith('test_') and callable(fn):\n            fn()\n"
    )
    assert not runs_under_bare_python(dead, 'test_x')
    assert runs_under_bare_python(live, 'test_x')
    assert runs_under_bare_python(reflective, 'test_x')
    assert not runs_under_bare_python(live, 'test_absent')
    # the runner list can sit in a main() the guard calls, not only inline
    indirect = (
        'def test_x():\n    assert True\n\n'
        'def main():\n    test_x()\n\n'
        "if __name__ == '__main__':\n    main()\n"
    )
    assert runs_under_bare_python(indirect, 'test_x')
    # the module-is-the-test shape, where assertions live in main()
    assert runs_under_bare_python(indirect, 'main')
    assert not runs_under_bare_python('x = 1\n', 'main')
    # no entry point at all: nothing runs, whatever is defined
    assert not runs_under_bare_python('def main():\n    assert True\n', 'main')
    assert not runs_under_bare_python('def test_x():\n    assert True\n\ntest_x()\n', 'test_x')


def test_broken_proofs_are_detected_not_assumed_fine():
    reg = {'proofs': {'s.py': ['evals/harness/test_red_proofs.py::test_absent_function_xyz']}}
    assert broken_proofs(reg, ROOT), 'a proof naming a missing function passed'
    reg = {'proofs': {'s.py': ['evals/harness/no_such_test.py::test_x']}}
    assert broken_proofs(reg, ROOT), 'a proof naming a missing module passed'
    reg = {'proofs': {'s.py': ['malformed-no-separator']}}
    assert broken_proofs(reg, ROOT), 'a malformed proof reference passed'
    reg = {
        'proofs': {
            's.py': [
                'evals/harness/test_red_proofs.py::test_broken_proofs_are_detected_not_assumed_fine'
            ]
        }
    }
    assert not broken_proofs(reg, ROOT), 'a real, runner-reachable proof was rejected'


def test_the_family_glob_actually_finds_the_known_checks():
    """A sweep over zero files is the vacuous-gate class this repo has hit
    twice; pin a floor and three known members."""
    found = shipped_scripts()
    assert len(found) > 30, f'the family glob found only {len(found)} scripts'
    for known in (
        'scripts/lint_register.py',
        'plugins/engineering-discipline/hooks/uv_enforce.py',
        'plugins/experiment-discipline/skills/experiment-rigor/scripts/validate.py',
    ):
        assert known in found, f'{known} escaped the family glob'


if __name__ == '__main__':
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_') and callable(_fn):
            _fn()
    print('ok: red-proof registry')

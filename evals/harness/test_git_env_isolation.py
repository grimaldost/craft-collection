#!/usr/bin/env python3
"""Regression: repo scripts must resolve git against the tree they were POINTED at.

Git exports the repository-location variables (GIT_DIR, GIT_WORK_TREE,
GIT_INDEX_FILE, GIT_OBJECT_DIRECTORY, GIT_ALTERNATE_OBJECT_DIRECTORIES,
GIT_COMMON_DIR, GIT_NAMESPACE) into the environment of every hook it runs, and an
ambient GIT_DIR takes PRECEDENCE over `git -C <dir>`. Both scripts covered here run
as pre-commit hooks, so every `git -C <root>` inside them silently answered about
the OUTER repository instead: ascii_runtime_lint saw its whole scan tree as
untracked and linted nothing, and check_uv_hygiene asked the wrong repository
whether the tree under test had a venv committed. Both are gates that pass by
checking nothing -- the failure mode this repo's mechanism layer exists to avoid.

The suite was 47/47 run directly and red inside `git push`, which is how it was
found. Each module scrubs GIT_* from its child environment (`_git_env`); these
tests fail if that scrub is removed. The same class is covered for the
experiment-rigor validator beside its own git helpers
(`test_validate.py::test_git_ops_resolve_the_records_repo_under_an_inherited_git_dir`)
and for the freeze-SHA read
(`test_acceptance_rg2x2.py::test_finalize_reads_head_from_the_records_repo_under_an_inherited_git_dir`).

Runnable with pytest or `python test_git_env_isolation.py`. Stdlib only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import ascii_runtime_lint  # noqa: E402 - sys.path set up first
import check_uv_hygiene  # noqa: E402 - sys.path set up first


def _git(cwd: Path, *args: str) -> None:
    # The fixture builder must not inherit GIT_* either: under an ambient GIT_DIR,
    # `git -C <tmp> init` re-initialises the AMBIENT repository instead of creating
    # the decoy. Nothing ambient, everything intentional.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(cwd), *args],  # noqa: S607 - git resolved from PATH
        check=True,
        capture_output=True,
        timeout=30,
        env=env,
    )


@contextmanager
def _decoy_repo_exported_as_git_dir():
    """A real repository unrelated to the tree under test, exported as GIT_DIR --
    exactly what git leaks into the environment of a hook it runs."""
    with tempfile.TemporaryDirectory() as td:
        decoy = Path(td)
        _git(decoy, 'init', '-q')
        prior = os.environ.get('GIT_DIR')
        os.environ['GIT_DIR'] = str(decoy / '.git')
        try:
            yield decoy
        finally:
            if prior is None:
                os.environ.pop('GIT_DIR', None)
            else:
                os.environ['GIT_DIR'] = prior


def test_ascii_runtime_lint_scans_the_tree_it_was_pointed_at():
    # An em dash (U+2014) in a runtime literal, in a tree that is NOT a git checkout:
    # `git ls-files` must fail there and the rglob fallback must find it. Unscrubbed,
    # ls-files succeeds against the decoy, every file reads as untracked, and the scan
    # comes back empty.
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td)
        (tree / 'scripts').mkdir()
        (tree / 'scripts' / 'tool.py').write_text(
            '"""Docstring em dash — exempt."""\nprint(\'runtime — dash\')\n',
            encoding='utf-8',
        )
        with _decoy_repo_exported_as_git_dir():
            current = ascii_runtime_lint.scan(tree)
    assert list(current) == ['scripts/tool.py'], current
    assert 'U+2014' in current['scripts/tool.py'][0], current


def test_check_uv_hygiene_reads_the_tree_it_was_pointed_at():
    # A checked-in venv in the tree under test. Unscrubbed, `git ls-files -- .venv`
    # runs against the decoy's (empty) index, returns nothing, and the residue passes.
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td)
        (tree / 'uv.lock').write_text('', encoding='utf-8')
        (tree / '.venv').mkdir()
        (tree / '.venv' / 'pyvenv.cfg').write_text('home = /usr\n', encoding='utf-8')
        with _decoy_repo_exported_as_git_dir():
            errors = check_uv_hygiene.check_tree(tree)
    assert any('.venv/' in e for e in errors), errors


_GIT_CALL = re.compile(r"""['"]git['"]""")
_SCRUB = re.compile(r"startswith\(\s*['\"]GIT_['\"]\s*\)")


def test_every_repo_script_that_shells_to_git_scrubs_the_environment():
    """Generalized from the two scripts the incident happened to name. Two named
    tests do not cover the class: the next script to shell out to git inherits
    the same trap and nothing here would notice. This one reddens on the file
    that forgets, before it has ever run as a hook."""
    offenders = []
    for f in sorted((ROOT / 'scripts').glob('*.py')):
        if f.name.startswith('test_'):
            continue
        src = f.read_text(encoding='utf-8')
        if _GIT_CALL.search(src) and not _SCRUB.search(src):
            offenders.append(f.name)
    assert not offenders, (
        'repo scripts shelling out to git without scrubbing GIT_* from the child '
        f'environment (an ambient GIT_DIR outranks `git -C`): {", ".join(offenders)}'
    )
    # The detector, made to fail on purpose: a green sweep over the real scripts
    # is only evidence if the same predicate reddens on a script that forgets.
    forgetful = "subprocess.run(['git', '-C', str(root), 'status'])\n"
    assert _GIT_CALL.search(forgetful) and not _SCRUB.search(forgetful)
    careful = (
        forgetful + "env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}\n"
    )
    assert _SCRUB.search(careful)


def main() -> int:
    if not shutil.which('git'):
        print('skip: git unavailable, inherited-GIT_DIR isolation tests not run')
        return 0
    test_ascii_runtime_lint_scans_the_tree_it_was_pointed_at()
    test_check_uv_hygiene_reads_the_tree_it_was_pointed_at()
    test_every_repo_script_that_shells_to_git_scrubs_the_environment()
    print('ok: repo scripts resolve git against the tree they were pointed at')
    return 0


if __name__ == '__main__':
    sys.exit(main())

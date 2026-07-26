"""Guards for the experiment-rigor re-home into the experiment-discipline plugin.

Two invariants the move has to keep, both of which fail silently if left to review
(spec `docs/specs/2026-07-25-experiment-discipline-wave.md` section 1):

  1. **The trigger surface did not move.** The sealed holdout and its birth baseline
     measure the frontmatter `description`; a byte-level change would invalidate both
     and owe a reseal. Compared against a COMMITTED pre-move blob, not a `git show` --
     a shallow clone must not be able to make this check vacuous.
  2. **Nothing under plugins/humblepowers still claims the skill** except the router
     row's cross-plugin id and the CHANGELOG pointer, which are the two references the
     move deliberately leaves behind.

The third invariant -- both `.pre-commit-config.yaml` record hooks still selecting
every travelling record -- is guarded where the hook shape already is, next to the
validator those hooks run: `test_validate.py::test_hook_uses_files_and_pass_filenames`
and `::test_render_check_hook_matches_both_pair_members`.

Runnable with pytest or `python test_rehome_wiring.py`. Stdlib only, so the module
never skips on a missing PyYAML.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
REPO = HARNESS.parents[1]
FIXTURES = HARNESS / 'fixtures'

PRE_MOVE_DESCRIPTION = FIXTURES / 'experiment_rigor_description_pre_move.txt'
SKILL_MD = REPO / 'plugins' / 'experiment-discipline' / 'skills' / 'experiment-rigor' / 'SKILL.md'


# --- 1. the description is byte-identical across the move -------------------


def _frontmatter_description(text: str) -> str:
    """The raw `description:` scalar, without a YAML parser (PyYAML is optional here).
    The frontmatter writes it as one double-quoted line, which is the shape asserted."""
    block = text.split('---', 2)[1]
    match = re.search(r'^description: "(.*)"$', block, re.MULTILINE)
    assert match, 'frontmatter description is not a single double-quoted line'
    return match.group(1)


def test_description_is_byte_identical_to_the_pre_move_blob():
    assert PRE_MOVE_DESCRIPTION.is_file(), (
        f'missing pre-move blob {PRE_MOVE_DESCRIPTION}; without it this gate is vacuous'
    )
    # Bytes, not text: the point is that not one character moved. The fixture carries a
    # single trailing newline (the repo's end-of-file hygiene hook adds it).
    expected = PRE_MOVE_DESCRIPTION.read_bytes().replace(b'\r\n', b'\n').rstrip(b'\n')
    actual = _frontmatter_description(SKILL_MD.read_text(encoding='utf-8')).encode('utf-8')
    assert actual == expected, (
        'the experiment-rigor description changed across the re-home: the sealed holdout '
        'and its birth baseline measure this surface, so an edit owes a reseal '
        '(evals/trigger/holdout/BASELINES.md)'
    )


def test_the_skill_lives_in_the_new_plugin():
    assert SKILL_MD.is_file(), SKILL_MD
    assert not (REPO / 'plugins' / 'humblepowers' / 'skills' / 'experiment-rigor').exists()


# --- 2. what the move deliberately leaves behind ----------------------------


ALLOWED_HUMBLEPOWERS_RESIDUE = {
    'plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json',  # the routed id
    'plugins/humblepowers/CHANGELOG.md',  # the pointer to the new plugin
}


def test_only_the_router_row_and_the_changelog_pointer_remain():
    humble = REPO / 'plugins' / 'humblepowers'
    offenders = []
    for path in sorted(humble.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(REPO).as_posix()
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        if 'experiment-rigor' in text and rel not in ALLOWED_HUMBLEPOWERS_RESIDUE:
            offenders.append(rel)
    assert not offenders, f'stale experiment-rigor references under humblepowers: {offenders}'


def test_the_router_row_is_cross_plugin():
    rules = (
        REPO / 'plugins' / 'humblepowers' / 'skills' / 'choosing-tools' / 'scripts'
    ) / 'router_rules.json'
    text = rules.read_text(encoding='utf-8')
    assert '"experiment-discipline:experiment-rigor"' in text
    assert '"humblepowers:experiment-rigor"' not in text


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
            except Exception as exc:  # report any failure; never emit the ok: sentinel
                failed += 1
                print(f'FAIL {name}: {exc!r}')
    if failed:
        print(f'{failed} test(s) failed')
        sys.exit(1)
    print('ok: all re-home wiring guards passed')

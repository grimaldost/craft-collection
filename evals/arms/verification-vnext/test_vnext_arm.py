"""Gates on the verification-before-completion vNext candidate arm.

Runnable with pytest or `python test_vnext_arm.py`.

The candidate lives under `evals/`, which means the repository's own validators
do not see it: `word_budget.py` globs `plugins/*/skills/*/SKILL.md`,
`validate_plugins.py` resolves references only under the same glob, and
`lint_register.py` scans `plugins/` by default. A candidate body nobody checks
would arrive at its measurement already broken, so this module points those same
three checks at the arm, and adds the two properties that make it a usable
experimental arm rather than merely a valid file: it may not grow the body it is
being compared against, and its description must be byte-identical to the
shipped one, because the contrast under test is the body diff alone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ARM = Path(__file__).resolve().parent
REPO = ARM.parents[2]
sys.path.insert(0, str(REPO / 'scripts'))

import lint_register  # noqa: E402
from word_budget import body_word_count  # noqa: E402

CANDIDATE = ARM / 'verification-before-completion' / 'SKILL.md'
SHIPPED = (
    REPO / 'plugins' / 'humblepowers' / 'skills' / 'verification-before-completion' / 'SKILL.md'
)
SHIPPED_KEY = 'plugins/humblepowers/skills/verification-before-completion/SKILL.md'

# Each displaced procedure leaves its bright line in the body and takes only the
# mechanics with it. The pairs are (what must still be IN the body, what must
# have LEFT it for the reference) — a displacement that dropped the bright line
# is a cut, and a displacement that left the mechanics behind is a duplication.
DISPLACEMENTS = [
    ('exit code after a pipe', '$?'),
    ('by the inverse edit', 'byte-precise'),
    ('zero net regression', 'base commit'),
    ('count\nthe files, rows, or cases it saw', 'exits 0'),
]

# The three rows whose obligations (D2 / P1 / N1 + H6) this arm exists to discharge.
CANDIDATE_ROWS = (
    '| A check ran |',
    '| Data output correct |',
    '| Doc/report claim accurate |',
)


def _text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _description(path: Path) -> str:
    return _text(path).split('---', 2)[1]


def test_candidate_does_not_grow_the_body_it_is_compared_against():
    """Displace, never append. Three rows arrive and the body still shrinks; the
    recorded baseline is not bumped, so the size question never has to be argued."""
    candidate = body_word_count(_text(CANDIDATE))
    shipped = body_word_count(_text(SHIPPED))
    baseline = json.loads((REPO / 'scripts' / 'word_budget.json').read_text(encoding='utf-8'))
    assert candidate <= shipped, f'candidate body {candidate} > shipped {shipped}'
    assert candidate <= baseline[SHIPPED_KEY], (
        f'candidate body {candidate} > recorded budget {baseline[SHIPPED_KEY]}'
    )


def test_description_is_byte_identical_to_the_shipped_surface():
    """The arm measures a body diff. A description that also moved would make any
    difference in the result unattributable between two changes at once."""
    assert _description(CANDIDATE) == _description(SHIPPED)


def test_every_reference_resolves():
    import re

    text = _text(CANDIDATE)
    named = set(re.findall(r'references/([A-Za-z0-9_\-/]+\.md)', text))
    assert named, 'the displacement is the point — a candidate naming no reference is not it'
    missing = [r for r in named if not (CANDIDATE.parent / 'references' / r).is_file()]
    assert not missing, f'dangling reference(s): {missing}'


def test_register_lint_is_clean():
    findings = lint_register.lint_paths([ARM])
    assert not findings, findings


def test_each_displaced_procedure_left_its_bright_line_behind():
    body = _text(CANDIDATE).split('---', 2)[2]
    reference = _text(CANDIDATE.parent / 'references' / 'non-vacuity.md')
    problems = []
    for kept, moved in DISPLACEMENTS:
        if kept.replace('\n', ' ') not in ' '.join(body.split()):
            problems.append(f'bright line dropped from the body: {kept!r}')
        if moved not in reference:
            problems.append(f'procedure never arrived in the reference: {moved!r}')
        if moved in body:
            problems.append(f'procedure still in the body as well as the reference: {moved!r}')
    assert not problems, problems


def test_the_candidate_rows_are_present():
    body = _text(CANDIDATE)
    missing = [r for r in CANDIDATE_ROWS if r not in body]
    assert not missing, f'arm does not carry the rows it exists to test: {missing}'


def test_nothing_leaked_into_the_shipped_skill():
    """V3-V7 ship only once their obligations discharge. Until then the plugin's
    body stays where it was, and this is what says so out loud."""
    shipped = _text(SHIPPED)
    leaked = [r for r in CANDIDATE_ROWS if r in shipped]
    assert not leaked, f'candidate rows are in the shipped body without their proof: {leaked}'
    assert 'references/non-vacuity.md' not in shipped, (
        'the displacement landed in the shipped body before X1 discharged'
    )


if __name__ == '__main__':
    failures = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_') and callable(_fn):
            try:
                _fn()
            except AssertionError as exc:
                failures += 1
                print(f'FAIL {_name}: {exc}')
    if failures:
        sys.exit(1)
    print('ok: vnext candidate arm gates passed')

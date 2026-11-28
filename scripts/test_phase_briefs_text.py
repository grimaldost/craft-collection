"""Pins the context-handoff phase-briefs reference against the installed toolkit.

`plugins/session-workflow/skills/context-handoff/references/phase-briefs.md`
names, per phase of work, the disciplines a brief for that phase loads and in
which order, and the closing block every brief carries. Its value is that each
name it cites is a skill the receiver can actually load: a misspelled or retired
name sends a cold executor looking for a discipline that does not exist, and
nothing else in the repository reads skill names inside a reference file
(`validate_plugins.py` checks only `references/` paths and plugin-root paths).

What is pinned:

- every `plugin:skill` name the reference cites resolves, either to a directory
  `plugins/<plugin>/skills/<skill>/` with a `SKILL.md` in this repository, or to
  the explicit external list below (keel and convoy ship from their own
  repositories, so their names are listed here by hand);
- a misspelled name fails the resolution, so the check can fail;
- a cited skill that is manual-only (`disable-model-invocation: true`) sits on a
  line saying the owner runs or starts it, since the receiver cannot load it
  (T423a);
- each of the seven phases has its own section and cites at least one name;
- the closing block names the hand-back file and its four fields, measured
  versus relayed facts, and the questions only the owner decides;
- `context-handoff/SKILL.md` points to the reference, and the path resolves.

Stdlib-runnable: `python scripts/test_phase_briefs_text.py` prints `ok:`.
"""

from __future__ import annotations

import re
from pathlib import Path

from test_manual_only_skills import manual_only_skill_names

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / 'plugins' / 'session-workflow' / 'skills' / 'context-handoff'
SKILL = SKILL_DIR / 'SKILL.md'
POINTER = 'references/phase-briefs.md'
REFERENCE = SKILL_DIR / POINTER

# Skills that ship outside this repository, by plugin. Kept by hand: a name added
# here is a reviewed claim that the external plugin ships that skill.
EXTERNAL = {
    'keel': {'apply-method'},
    'convoy': {'convoy'},
}

PHASES = [
    'Design',
    'Specification',
    'Implementation',
    'Data-contract change',
    'Measurement',
    'Release',
    'Review',
]

CLOSING_ITEMS = [
    'hand-back file',
    'done',
    'artifacts',
    'leaves',
    'blocked on',
    'measured',
    'relayed',
    'only the owner decides',
]

# A cited name is `plugin:skill` in inline code. A bare `plugin:skill` outside
# code is caught too when its plugin is one the toolkit knows, so an unquoted
# misspelling cannot slip past the backtick form.
QUOTED = re.compile(r'`([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+)`')


def local_plugins(root: Path = ROOT) -> set[str]:
    return {p.name for p in (root / 'plugins').iterdir() if (p / 'skills').is_dir()}


def cited_names(text: str, root: Path = ROOT) -> list[str]:
    """Every `plugin:skill` name the text cites, in order of first appearance."""
    known = sorted(local_plugins(root) | set(EXTERNAL), key=len, reverse=True)
    bare = re.compile(
        r'(?<![A-Za-z0-9_.`/-])(' + '|'.join(map(re.escape, known)) + r'):([A-Za-z0-9_-]+)'
    )
    names: list[str] = []
    for pattern in (QUOTED, bare):
        for plugin, skill in pattern.findall(text):
            name = f'{plugin}:{skill}'
            if name not in names:
                names.append(name)
    return names


def resolves(name: str, root: Path = ROOT) -> bool:
    plugin, _, skill = name.partition(':')
    if not plugin or not skill:
        return False
    if plugin in EXTERNAL:
        return skill in EXTERNAL[plugin]
    return (root / 'plugins' / plugin / 'skills' / skill / 'SKILL.md').is_file()


# A manual-only skill is one the receiver cannot load; its line names who starts it.
OWNER_STARTS = re.compile(r'\bthe owner (?:runs|starts)\b', re.I)


def manual_only_without_owner(text: str, root: Path = ROOT) -> list[str]:
    """Cited manual-only names on a line that does not say the owner starts them."""
    manual = manual_only_skill_names(root)
    found: list[str] = []
    for line in text.splitlines():
        for name in cited_names(line, root):
            if name.partition(':')[2] in manual and not OWNER_STARTS.search(line):
                found.append(name)
    return found


def _reference() -> str:
    assert REFERENCE.is_file(), f'missing {REFERENCE.relative_to(ROOT)}'
    return REFERENCE.read_text(encoding='utf-8')


def _sections(text: str) -> dict[str, str]:
    """Body of each `## ` section, keyed by its heading. A `## ` line inside a
    fenced block (the closing block's own template heading) is body, not a
    section break."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    fenced = False
    for line in text.splitlines():
        if line.startswith('```'):
            fenced = not fenced
        heading = None if fenced else re.match(r'^## +(.+?)\s*$', line)
        if heading:
            current = sections.setdefault(heading.group(1).strip(), [])
        elif current is not None:
            current.append(line)
    return {heading: '\n'.join(lines) for heading, lines in sections.items()}


def test_every_cited_name_resolves():
    names = cited_names(_reference())
    assert names, 'the reference cites no skill names'
    missing = [n for n in names if not resolves(n)]
    assert not missing, f'phase-briefs.md cites names that do not resolve: {missing}'


def test_a_misspelled_name_fails_resolution():
    text = 'Load `humblepowers:brainstormin`, then humblepowers:test-driven-developmnt.'
    names = cited_names(text)
    assert names == [
        'humblepowers:brainstormin',
        'humblepowers:test-driven-developmnt',
    ], names
    assert not any(resolves(n) for n in names)
    assert not resolves('keel:apply-methd')
    assert not resolves('convoyy:convoy')
    assert resolves('humblepowers:brainstorming')
    assert resolves('keel:apply-method')


def test_no_cited_name_is_manual_only_unless_owner_started():
    bad = manual_only_without_owner(_reference())
    assert not bad, f'phase-briefs.md cites manual-only skills as loadable: {bad}'
    # The check can fail: a bare citation of a manual-only skill is caught, and the
    # same citation on a line saying the owner runs it is not.
    assert manual_only_without_owner('2. `session-workflow:evaluate-skill`, when x.') == [
        'session-workflow:evaluate-skill'
    ]
    assert not manual_only_without_owner('`session-workflow:evaluate-skill`: the owner runs it.')
    assert not manual_only_without_owner('`humblepowers:brainstorming`, when x.')


def test_each_phase_has_a_section_citing_a_name():
    sections = _sections(_reference())
    for phase in PHASES:
        assert phase in sections, f'no "## {phase}" section; found {list(sections)}'
        assert cited_names(sections[phase]), f'the {phase} section cites no skill'


def test_the_closing_block_names_its_fields():
    sections = _sections(_reference())
    closing = [body for heading, body in sections.items() if 'closing block' in heading.lower()]
    assert closing, 'no closing-block section'
    body = re.sub(r'\s+', ' ', closing[0]).lower()
    missing = [item for item in CLOSING_ITEMS if item not in body]
    assert not missing, f'the closing block does not name: {missing}'


def test_the_skill_points_to_the_reference():
    text = SKILL.read_text(encoding='utf-8')
    assert POINTER in text, 'context-handoff/SKILL.md does not point to phase-briefs.md'
    assert REFERENCE.is_file()


if __name__ == '__main__':
    test_a_misspelled_name_fails_resolution()
    test_every_cited_name_resolves()
    test_no_cited_name_is_manual_only_unless_owner_started()
    test_each_phase_has_a_section_citing_a_name()
    test_the_closing_block_names_its_fields()
    test_the_skill_points_to_the_reference()
    print('ok: phase-briefs cites only resolvable skills and carries its closing block')

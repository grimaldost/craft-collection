#!/usr/bin/env python3
"""Word-budget ratchet for skill bodies (issue #54).

A skill's eager body accretes silently over time — `feedback-triage` grew 806 -> 1621
words in 19 days. This records a per-skill body word-count baseline in `word_budget.json`;
`validate_plugins` fails when a body exceeds its baseline. Growing a body means bumping
its baseline in a visible, reviewed diff — which is exactly where the change names what
the growth displaces (the "a prose append names what it displaces" doctrine, mechanized).

The **body** is everything after the SKILL.md frontmatter block; the frontmatter
`description` has its own budget (`DESC_CAP` in `validate_plugins.py`). A word is a
whitespace-separated token — reproducible, not a proxy for rendered length. Shrinking a
body is always fine; only growth past the baseline trips.

A skill's `references/` directory can carry a ceiling too, recorded in
`reference_budget.json` (a separate file, so `--seed` cannot drop it): the words of
every `*.md` under it, recursive, counted the same way. A missing directory, or one
with no `.md` files, fails rather than passing on nothing.

    python scripts/word_budget.py            # check the tree against word_budget.json
    python scripts/word_budget.py --seed     # (re)write word_budget.json from the tree
    python scripts/word_budget.py --report   # body / ceiling / headroom per skill
    python scripts/word_budget.py --report <skill>   # that skill's sections, longest first

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET_FILE = ROOT / 'scripts' / 'word_budget.json'
# Ceilings for a skill's `references/` directory, kept apart from word_budget.json
# so `--seed` (which rewrites that file from SKILL.md counts alone) cannot drop them.
REFERENCE_BUDGET_FILE = ROOT / 'scripts' / 'reference_budget.json'


def _split_body(text: str) -> str:
    """The SKILL.md body: everything after the frontmatter block (see body_word_count)."""
    if text.startswith('---'):
        parts = text.split('---', 2)
        return parts[2] if len(parts) == 3 else text
    return text


def body_word_count(text: str) -> int:
    """Words in a SKILL.md BODY — everything after the frontmatter block. The
    frontmatter is delimited by the first two `---` lines; a `---` horizontal rule
    inside the body is preserved (split stops after two delimiters). A file without
    frontmatter counts whole. Words are whitespace-separated tokens. Pure."""
    return len(_split_body(text).split())


HEADING = re.compile(r'#{1,6} ')
PREAMBLE = '(before first heading)'


def section_counts(text: str) -> list[tuple[int, str, int]]:
    """`(line_no, heading, words)` per section of a SKILL.md body, longest first, ties
    by line number. The body is cut at ATX headings (`#` to `######` plus a space)
    outside ``` or ~~~ fences. Sections are flat: a `##` section's count excludes its
    `###` children. Text before the first heading is `(before first heading)`, omitted
    when empty. Sections partition the body's lines and a word never spans a line, so
    the counts sum to `body_word_count(text)`. `line_no` counts from the top of the
    file. Pure."""
    body = _split_body(text)
    first_line = text[: len(text) - len(body)].count('\n') + 1
    sections: list[list] = [[first_line, PREAMBLE, 0]]
    fence = ''
    for offset, line in enumerate(body.split('\n')):
        marker = line.lstrip()[:3]
        if fence:
            if marker == fence:
                fence = ''
        elif marker in ('```', '~~~'):
            fence = marker
        elif HEADING.match(line):
            sections.append([first_line + offset, line.strip(), 0])
        sections[-1][2] += len(line.split())
    kept = [(n, heading, words) for n, heading, words in sections if words or heading != PREAMBLE]
    return sorted(kept, key=lambda s: (-s[2], s[0]))


def section_rows(path: str, text: str, budget: int | None) -> list[str]:
    """The per-skill section report: a `path: body N / budget B, headroom H` line, one
    line saying sections are flat, a column header, then `  words  line  heading`
    rows. ASCII only, because it prints to a cp1252 console: a non-ASCII heading is
    escaped. Pure."""
    body = body_word_count(text)
    room = '?' if budget is None else str(budget - body)
    lines = [
        f'{path}: body {body} / budget {"?" if budget is None else budget}, headroom {room}',
        'sections are flat: a ## count excludes its ### children',
        '  words  line  heading',
    ]
    lines += [f'{words:>7}  {n:>4}  {heading}' for n, heading, words in section_counts(text)]
    return [line.encode('ascii', 'backslashreplace').decode('ascii') for line in lines]


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def skill_files(root: Path = ROOT) -> list[Path]:
    return sorted(root.glob('plugins/*/skills/*/SKILL.md'))


def current_counts(root: Path = ROOT) -> dict[str, int]:
    """{skill-path: body-word-count} for every SKILL.md in the tree."""
    out: dict[str, int] = {}
    for p in skill_files(root):
        out[p.relative_to(root).as_posix()] = body_word_count(p.read_text(encoding='utf-8'))
    return out


def load_baselines(path: Path = BUDGET_FILE) -> dict[str, int]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def check_budgets(counts: dict[str, int], baselines: dict[str, int]) -> list[str]:
    """Return budget violations (empty == all within budget). A body over its baseline
    fails; a body with no baseline fails (a new skill must record one). Equal or smaller
    passes. Pure — feed it counts and baselines, no I/O."""
    errors: list[str] = []
    for path, count in sorted(counts.items()):
        base = baselines.get(path)
        if base is None:
            errors.append(f'{path}: no word-budget baseline — add one to word_budget.json')
        elif count > base:
            errors.append(
                f'{path}: body {count} words > budget {base} — either shrink it, or bump '
                f'the baseline in word_budget.json and name what the growth displaces'
            )
    return errors


def reference_word_count(directory: Path) -> tuple[int, int]:
    """`(words, files)` over every `*.md` under `directory`, recursive, each file
    counted by `body_word_count`."""
    files = sorted(directory.rglob('*.md'))
    return sum(body_word_count(p.read_text(encoding='utf-8')) for p in files), len(files)


def current_reference_counts(
    ceilings: dict[str, int], root: Path = ROOT
) -> dict[str, tuple[int, int] | None]:
    """`{dir: (words, files)}` for each directory with a recorded ceiling; None
    where the directory does not exist."""
    out: dict[str, tuple[int, int] | None] = {}
    for path in ceilings:
        d = root / path
        out[path] = reference_word_count(d) if d.is_dir() else None
    return out


def check_reference_budgets(
    counts: dict[str, tuple[int, int] | None], ceilings: dict[str, int]
) -> list[str]:
    """Return reference-ceiling violations (empty == all within ceiling). A
    directory over its ceiling fails; so do a missing directory and one with no
    `.md` files, since a check over nothing passes vacuously. Pure."""
    errors: list[str] = []
    for path, ceiling in sorted(ceilings.items()):
        got = counts.get(path)
        if got is None:
            errors.append(
                f'{path}: reference ceiling recorded but the directory is missing - '
                f'restore it or remove its entry from reference_budget.json'
            )
        elif got[1] == 0:
            errors.append(f'{path}: no .md files under a recorded reference ceiling')
        elif got[0] > ceiling:
            errors.append(
                f'{path}: references {got[0]} words > ceiling {ceiling} - either shrink '
                f'them, or raise the ceiling in reference_budget.json and name what the '
                f'growth displaces'
            )
    return errors


def reference_report_rows(
    counts: dict[str, tuple[int, int] | None], ceilings: dict[str, int]
) -> list[str]:
    """One `words / ceiling  headroom N  dir/` line per recorded references
    directory, in the same columns as `report_rows`. Pure."""
    rows = []
    for path, ceiling in sorted(ceilings.items()):
        got = counts.get(path)
        if got is None:
            rows.append(f'    ? / {ceiling:>5}  headroom      ?  {path}/ (missing)')
        else:
            rows.append(f'{got[0]:>5} / {ceiling:>5}  headroom {ceiling - got[0]:>6}  {path}/')
    return rows


def report_rows(counts: dict[str, int], baselines: dict[str, int]) -> list[str]:
    """One `body / ceiling  headroom N  path` line per skill, widest-first by
    pressure. The reason this exists: an audit computed a body count by hand,
    compared it against the gate's ceiling, and reported 78 words of headroom
    where there were zero - so an additive edit would have tripped the gate the
    audit said had room, and a plan was built on the wrong figure. There is
    exactly one counter in this repo; the fix is to leave nothing to hand-count.
    Pure."""
    rows = []
    for path, count in counts.items():
        base = baselines.get(path)
        if base is None:
            rows.append((None, f'{count:>5} /     ?  headroom      ?  {path}'))
        else:
            rows.append(
                (base - count, f'{count:>5} / {base:>5}  headroom {base - count:>6}  {path}')
            )
    # tightest first, unbaselined at the very top - those are the ones that bite
    return [line for _, line in sorted(rows, key=lambda r: (r[0] is not None, r[0]))]


def resolve_skill(target: str, root: Path = ROOT) -> Path | None:
    """A skill name (`plugins/*/skills/<name>/SKILL.md`) or a path to a SKILL.md, else
    None. Names are unique across the tree."""
    for p in skill_files(root):
        if p.parent.name == target:
            return p
    given = Path(target)
    return given if given.is_file() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Skill-body word-budget ratchet (issue #54)')
    ap.add_argument(
        '--seed', action='store_true', help='(re)write word_budget.json from the current tree'
    )
    ap.add_argument(
        '--report',
        nargs='?',
        const='',
        metavar='SKILL',
        help='print body / ceiling / headroom per skill and exit 0 - quote this, never a hand '
        'count; with a skill name or SKILL.md path, list the sections of that skill, longest first',
    )
    args = ap.parse_args(argv)
    counts = current_counts()
    if args.report == '':
        for line in report_rows(counts, load_baselines()):
            print(line)
        ceilings = load_baselines(REFERENCE_BUDGET_FILE)
        for line in reference_report_rows(current_reference_counts(ceilings), ceilings):
            print(line)
        return 0
    if args.report is not None:
        skill = resolve_skill(args.report)
        if skill is None:
            names = ', '.join(sorted(p.parent.name for p in skill_files()))
            print(f'no skill {args.report!r}; available: {names}')
            return 2
        resolved = skill.resolve()
        path = _rel(resolved) if resolved.is_relative_to(ROOT) else skill.as_posix()
        text = skill.read_text(encoding='utf-8')
        for line in section_rows(path, text, load_baselines().get(path)):
            print(line)
        return 0
    if args.seed:
        BUDGET_FILE.write_text(
            json.dumps(dict(sorted(counts.items())), indent=2) + '\n', encoding='utf-8'
        )
        print(f'seeded {len(counts)} baseline(s) -> {_rel(BUDGET_FILE)}')
        return 0
    errors = check_budgets(counts, load_baselines())
    ceilings = load_baselines(REFERENCE_BUDGET_FILE)
    errors += check_reference_budgets(current_reference_counts(ceilings), ceilings)
    if errors:
        print('WORD BUDGET EXCEEDED:')
        for e in errors:
            print(f'  - {e}')
        return 1
    print(
        f'word budget: {len(counts)} skill bodies within budget, '
        f'{len(ceilings)} references directories within ceiling'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""No shipped skill or trigger file names a skill that no longer exists.

keel 0.22.0 deleted `keel-triage`; its procedure is the `reflection-triage`
template. The feedback-triage description kept sending readers to the old name
until T309c, because nothing compared prose against the set of retired names.
Changelogs record history and are not scanned.

Stdlib-runnable: `python scripts/test_retired_skill_names.py` prints `ok:`.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RETIRED = ('keel-triage',)


def live_files(root: Path = ROOT) -> list[Path]:
    files = sorted(root.glob('plugins/*/skills/**/SKILL.md'))
    files += sorted(root.glob('plugins/*/skills/*/references/**/*.md'))
    files += sorted(root.glob('evals/trigger/*.json'))
    files += [root / 'AGENTS.md']
    return files


def test_no_live_file_names_a_retired_skill():
    hits = []
    for path in live_files():
        text = path.read_text(encoding='utf-8')
        hits += [f'{path.relative_to(ROOT)}: {name}' for name in RETIRED if name in text]
    assert not hits, f'retired skill names still mentioned: {hits}'


def test_the_scan_sees_the_files_it_is_meant_to_guard():
    names = {p.name for p in live_files()}
    assert {'SKILL.md', 'feedback-triage.json', 'AGENTS.md'} <= names


if __name__ == '__main__':
    test_no_live_file_names_a_retired_skill()
    test_the_scan_sees_the_files_it_is_meant_to_guard()
    print('ok: no live file names a retired skill')

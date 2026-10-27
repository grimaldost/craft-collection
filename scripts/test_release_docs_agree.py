"""The READMEs agree with each plugin's manifest, CHANGELOG and hooks.json.

A release cuts a version in `plugin.json` and in the CHANGELOG head, and the
READMEs date changes to releases ("observe by default since 0.29.0", "retired
in 0.21.0") and count hook entry points ("twelve hook entry points"). Before
this test nothing compared that prose with the sources it describes: changing
every 0.29.0 in the READMEs to 0.28.0, or to 0.30.0, or reverting the 0.29.0
docs reconcile whole, left every gate green.

What it checks, for every plugin:

  * the manifest version is the CHANGELOG's top released heading;
  * every version a README dates a change of the plugin to is a released
    heading of that plugin's CHANGELOG, at or below the manifest version;
  * every such dating is registered in DATED_CLAIMS with a phrase of the
    CHANGELOG section it points to, and that section contains the phrase, so a
    README that dates a change to the wrong release fails, and so does a
    registry entry moved along with it;
  * the count of hooks in the root README's summary of the plugin ("twelve
    hook entry points") equals the number of command hooks in the plugin's
    hooks.json. A hooks.json description carries no count word: every
    hook-adding pull request would change the same line, and concurrent ones
    would conflict.

A plugin README dates a change of its own plugin with `in`, `since` or `until`
before the version, or `removed`, `added` or `retired` after it; the root
README names the plugin first (`session-workflow 0.29.0 removed ...`). A
version after any other word (`Claude Code >= 2.1.218`, `superpowers 5.1.0`)
is another product's and is not read.

Stdlib-runnable: `python scripts/test_release_docs_agree.py` prints `ok:`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (README path, phrase of the README that holds the dated version, phrase of
# the CHANGELOG section of that version that records the change). Phrases are
# compared with runs of whitespace collapsed to one space.
DATED_CLAIMS: tuple[tuple[str, str, str], ...] = (
    (
        'README.md',
        'humblepowers 0.18.0 removed two more',
        'The SubagentStop verification gate',
    ),
    (
        'README.md',
        "session-workflow 0.29.0 removed the pending-asks gate's PostToolUse entry",
        'The PostToolUse entry on `mcp__ccd_turn__wrap_up`',
    ),
    (
        'plugins/engineering-discipline/README.md',
        'A Stop nudge to run the data pre-shipping checklist was retired in 0.4.0',
        'The data pre-shipping checklist Stop nudge',
    ),
    (
        'plugins/humblepowers/README.md',
        '**Retired in 0.8.0.** The generic dispatch *protocol* injection',
        'The session-start full-protocol inject',
    ),
    (
        'plugins/humblepowers/README.md',
        '0.18.0 removed the PreToolUse spawn-routing hint',
        'The PreToolUse spawn-routing hint',
    ),
    (
        'plugins/session-workflow/README.md',
        'toolkit-inventory SessionStart inject. It was retired in 0.21.0',
        'The toolkit-inventory SessionStart inject',
    ),
    (
        'plugins/session-workflow/README.md',
        'until 0.29.0 it was a Stop block',
        'Feedback-debt nudge: never a Stop block',
    ),
    (
        'plugins/session-workflow/README.md',
        '**Observe by default** since 0.29.0',
        'Pending-asks gate: observe by default',
    ),
    (
        'plugins/session-workflow/README.md',
        'Since 0.29.0 there is no hook on the desktop next-step box',
        'The PostToolUse entry on `mcp__ccd_turn__wrap_up`',
    ),
)

VERSION = r'\d+\.\d+\.\d+'
# A plugin README dating a change of its own plugin.
OWN_DATING = re.compile(
    rf'\b(?:in|since|until)\s+({VERSION})\b|\b({VERSION})\s+(?:removed|added|retired)\b',
    re.IGNORECASE,
)
HEADING = re.compile(r'^## \[(?P<version>[^\]]+)\] - \d{4}-\d{2}-\d{2}\s*$', re.MULTILINE)
NUMBER_WORDS = {
    word: n
    for n, word in enumerate(
        [
            'zero',
            'one',
            'two',
            'three',
            'four',
            'five',
            'six',
            'seven',
            'eight',
            'nine',
            'ten',
            'eleven',
            'twelve',
            'thirteen',
            'fourteen',
            'fifteen',
        ]
    )
}
COUNT = r'(\d+|' + '|'.join(NUMBER_WORDS) + r')'
SUMMARY_COUNT = re.compile(rf'\b{COUNT}\s+hook(?:s|\s+entry\s+points?)\b', re.IGNORECASE)


def _normalize(text: str) -> str:
    return ' '.join(text.split())


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split('.'))


def _sections(changelog: str) -> dict[str, str]:
    """Released version -> its section text, whitespace collapsed, in file order."""
    heads = list(HEADING.finditer(changelog))
    out: dict[str, str] = {}
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(changelog)
        out[head.group('version')] = _normalize(changelog[head.end() : end])
    return out


def _datings(path: str, text: str, plugins: list[str]) -> list[tuple[int, int, str, str]]:
    """(start, end, plugin, version) of each dating in the collapsed text."""
    if path.startswith('plugins/'):
        plugin = path.split('/')[1]
        return [
            (m.start(), m.end(), plugin, m.group(1) or m.group(2))
            for m in OWN_DATING.finditer(text)
        ]
    names = '|'.join(re.escape(p) for p in sorted(plugins, key=len, reverse=True))
    pattern = re.compile(rf'(?<![\w-])({names})\s+({VERSION})\b')
    return [(m.start(), m.end(), m.group(1), m.group(2)) for m in pattern.finditer(text)]


def release_findings(
    readmes: dict[str, str],
    manifests: dict[str, str],
    changelogs: dict[str, str],
    claims: tuple[tuple[str, str, str], ...],
) -> list[str]:
    """Each way the READMEs disagree with the manifests and CHANGELOGs. Pure."""
    found: list[str] = []
    sections = {p: _sections(text) for p, text in changelogs.items()}
    for plugin, version in manifests.items():
        head = next(iter(sections.get(plugin, {})), None)
        if head != version:
            found.append(
                f'{plugin}: manifest version {version} is not the CHANGELOG top heading ({head})'
            )
    for path, raw in readmes.items():
        text = _normalize(raw)
        spans = []
        for phrase_path, phrase, _ in claims:
            if phrase_path != path:
                continue
            start = text.find(_normalize(phrase))
            if start < 0:
                found.append(f'{path}: the DATED_CLAIMS phrase {phrase!r} is not in the README')
            else:
                spans.append((start, start + len(_normalize(phrase)), phrase))
        for start, end, plugin, version in _datings(path, text, list(manifests)):
            label = f'{path}: {text[start:end]!r} dates a change of {plugin} to {version}'
            if plugin not in manifests:
                found.append(f'{label}, a plugin with no manifest')
                continue
            if _key(version) > _key(manifests[plugin]):
                found.append(f'{label}, above its manifest version {manifests[plugin]}')
            if version not in sections.get(plugin, {}):
                found.append(f'{label}, which is no released heading of its CHANGELOG')
            covering = [phrase for s, e, phrase in spans if s <= start and end <= e]
            if not covering:
                found.append(f'{label}, and no DATED_CLAIMS entry links it to its CHANGELOG line')
        for phrase_path, phrase, record in claims:
            if phrase_path != path:
                continue
            datings = _datings(path, _normalize(phrase), list(manifests))
            if not datings:
                found.append(f'{path}: the DATED_CLAIMS phrase {phrase!r} names no version')
            for _, _, plugin, version in datings:
                section = sections.get(plugin, {}).get(version)
                if section is None or _normalize(record) not in section:
                    found.append(
                        f'{path}: {phrase!r} dates the change to {plugin} {version}, '
                        f'but that CHANGELOG section does not record {record!r}'
                    )
    return found


def _command_count(hooks_file: dict) -> int:
    return sum(
        1
        for groups in hooks_file.get('hooks', {}).values()
        for group in groups
        for hook in group.get('hooks', [])
        if hook.get('type') == 'command'
    )


def _number(word: str) -> int:
    return int(word) if word.isdigit() else NUMBER_WORDS[word.lower()]


def count_findings(root_readme: str, hooks_files: dict[str, dict]) -> list[str]:
    """Each hook count in prose that differs from the hooks.json it counts. Pure."""
    found: list[str] = []
    for m in re.finditer(
        r'^\*\*(?P<plugin>[\w-]+)\*\* —(?P<body>.*?)(?=\n\s*\n|\Z)', root_readme, re.M | re.S
    ):
        plugin = m.group('plugin')
        actual = _command_count(hooks_files.get(plugin, {}))
        for said in SUMMARY_COUNT.finditer(m.group('body')):
            if _number(said.group(1)) != actual:
                found.append(
                    f'README.md: the summary of {plugin} says {said.group(0)!r} '
                    f'({_number(said.group(1))}), but its hooks.json has {actual} command hooks'
                )
    return found


# --- synthetic cases --------------------------------------------------------

CHANGELOG = """# Changelog

## [0.29.0] - 2026-10-26

### Changed

- **Pending-asks gate: observe by default.** It records and prints nothing.

## [0.28.0] - 2026-10-25

### Added

- **Pending-asks gate**, on by default.
"""

CLAIM = (
    'plugins/demo/README.md',
    'Observe by default since 0.29.0',
    'Pending-asks gate: observe by default',
)


def _readme(text: str) -> dict[str, str]:
    return {'plugins/demo/README.md': text, 'README.md': 'Nothing dated here.\n'}


def _findings(
    readme_text: str, claims=(CLAIM,), manifest='0.29.0', changelog=CHANGELOG
) -> list[str]:
    return release_findings(_readme(readme_text), {'demo': manifest}, {'demo': changelog}, claims)


def test_agreeing_sources_have_no_findings():
    assert _findings('The gate is Observe by default since 0.29.0 (it records).\n') == []


def test_a_readme_dating_a_change_to_an_older_release_is_a_finding():
    found = _findings('The gate is Observe by default since 0.28.0 (it records).\n')
    assert any('0.28.0' in f for f in found), found


def test_a_readme_dating_a_change_to_an_unreleased_version_is_a_finding():
    found = _findings('The gate is Observe by default since 0.30.0 (it records).\n')
    assert any('0.30.0' in f and 'manifest' in f for f in found), found


def test_a_claim_moved_with_the_readme_still_fails_on_the_changelog():
    moved = (CLAIM[0], 'Observe by default since 0.28.0', CLAIM[2])
    found = _findings(
        'The gate is Observe by default since 0.28.0 (it records).\n', claims=(moved,)
    )
    assert any('CHANGELOG' in f and '0.28.0' in f for f in found), found


def test_an_unregistered_dating_is_a_finding():
    text = 'The gate is Observe by default since 0.29.0. The box was retired in 0.28.0.\n'
    found = _findings(text)
    assert any("'in 0.28.0'" in f and 'no DATED_CLAIMS entry' in f for f in found), found


def test_a_registered_phrase_missing_from_the_readme_is_a_finding():
    found = _findings('The gate records and prints nothing.\n')
    assert any('Observe by default since 0.29.0' in f for f in found), found


def test_a_manifest_that_is_not_the_changelog_head_is_a_finding():
    found = _findings('The gate is Observe by default since 0.29.0.\n', manifest='0.29.1')
    assert any('0.29.1' in f and 'CHANGELOG' in f for f in found), found


def test_another_products_version_is_not_read_as_a_dating():
    text = 'Observe by default since 0.29.0. Requires Claude Code >= 2.1.218, unlike superpowers 5.1.0.\n'
    assert _findings(text) == []


def test_the_root_readme_dates_a_change_by_the_plugin_name():
    readmes = {
        'plugins/demo/README.md': 'Observe by default since 0.29.0.\n',
        'README.md': 'demo 0.27.0 removed the box entry.\n',
    }
    found = release_findings(readmes, {'demo': '0.29.0'}, {'demo': CHANGELOG}, (CLAIM,))
    assert any('demo 0.27.0' in f for f in found), found


def _hooks(description: str, n: int) -> dict:
    entry = {'hooks': [{'type': 'command', 'command': 'x'}]}
    return {'description': description, 'hooks': {'Stop': [entry] * n}}


ROOT_SUMMARY = (
    "## What's inside\n\n**demo** — skills `a`; and twelve hook entry points (see the Hooks table).\n\n"
    '**other** — skills `b`; one hook (a router hint).\n\n## Hooks\n'
)


def test_matching_counts_have_no_findings():
    hooks = {
        'demo': _hooks('Entry points. More.', 12),
        'other': _hooks('One hook. More.', 1),
    }
    assert count_findings(ROOT_SUMMARY, hooks) == []


def test_a_stale_hook_count_in_the_root_summary_is_a_finding():
    # The 0.27.0 summary wrapped between the count and its noun.
    stale = ROOT_SUMMARY.replace('twelve hook entry points', 'four\nhooks, all on by default')
    hooks = {'demo': _hooks('Entry points.', 12), 'other': _hooks('One hook.', 1)}
    found = count_findings(stale, hooks)
    assert any('demo' in f and 'README.md' in f and '4' in f for f in found), found


# --- the repository ---------------------------------------------------------


def _repository() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, dict]]:
    readmes = {'README.md': (ROOT / 'README.md').read_text(encoding='utf-8')}
    manifests: dict[str, str] = {}
    changelogs: dict[str, str] = {}
    hooks_files: dict[str, dict] = {}
    for plugin_dir in sorted(p for p in (ROOT / 'plugins').iterdir() if p.is_dir()):
        name = plugin_dir.name
        manifest = json.loads(
            (plugin_dir / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8')
        )
        manifests[name] = manifest['version']
        changelogs[name] = (plugin_dir / 'CHANGELOG.md').read_text(encoding='utf-8')
        readme = plugin_dir / 'README.md'
        if readme.exists():
            readmes[f'plugins/{name}/README.md'] = readme.read_text(encoding='utf-8')
        hooks = plugin_dir / 'hooks' / 'hooks.json'
        if hooks.exists():
            hooks_files[name] = json.loads(hooks.read_text(encoding='utf-8'))
    return readmes, manifests, changelogs, hooks_files


def test_the_repository_readmes_agree_with_the_releases():
    readmes, manifests, changelogs, _ = _repository()
    found = release_findings(readmes, manifests, changelogs, DATED_CLAIMS)
    assert found == [], '\n'.join(found)


def test_the_repository_hook_counts_agree():
    readmes, _, _, hooks_files = _repository()
    found = count_findings(readmes['README.md'], hooks_files)
    assert found == [], '\n'.join(found)


SESSION_WORKFLOW_HOOKS = ROOT / 'plugins' / 'session-workflow' / 'hooks' / 'hooks.json'
_ANY_NUMBER = r'(?:\d+|' + '|'.join(NUMBER_WORDS) + r')'
OPENING_NUMBER_WORD = re.compile(rf'^{_ANY_NUMBER}\b', re.IGNORECASE)
NUMBER_WORD_BEFORE_ENTRY = re.compile(
    rf'\b{_ANY_NUMBER}\s+(?:\w+\s+)?entr(?:y|ies)\b', re.IGNORECASE
)


def test_the_session_workflow_hooks_description_carries_no_count_word():
    description = json.loads(SESSION_WORKFLOW_HOOKS.read_text(encoding='utf-8'))['description']
    assert description.startswith('Entry points:'), description[:40]
    assert not OPENING_NUMBER_WORD.match(description), description[:40]
    found = NUMBER_WORD_BEFORE_ENTRY.search(description)
    assert not found, found and found.group(0)


def test_a_hook_added_to_the_session_workflow_plugin_leaves_the_description_alone():
    # The description is the shipped one; the README summary is synthetic, so the
    # case holds whatever spelling the root README uses for its count.
    import copy

    hooks = copy.deepcopy(json.loads(SESSION_WORKFLOW_HOOKS.read_text(encoding='utf-8')))
    hooks['hooks'].setdefault('Stop', []).append({'hooks': [{'type': 'command', 'command': 'x'}]})
    summary = (
        f'**session-workflow** \u2014 skills `a`; and {_command_count(hooks)} hook entry points.\n'
    )
    found = count_findings(summary, {'session-workflow': hooks})
    assert found == [], '\n'.join(found)


def test_the_scan_sees_what_it_guards():
    readmes, *_ = _repository()
    assert {c[0] for c in DATED_CLAIMS} >= {
        'README.md',
        'plugins/engineering-discipline/README.md',
        'plugins/humblepowers/README.md',
        'plugins/session-workflow/README.md',
    }
    assert set(readmes) >= {c[0] for c in DATED_CLAIMS}


if __name__ == '__main__':
    test_agreeing_sources_have_no_findings()
    test_a_readme_dating_a_change_to_an_older_release_is_a_finding()
    test_a_readme_dating_a_change_to_an_unreleased_version_is_a_finding()
    test_a_claim_moved_with_the_readme_still_fails_on_the_changelog()
    test_an_unregistered_dating_is_a_finding()
    test_a_registered_phrase_missing_from_the_readme_is_a_finding()
    test_a_manifest_that_is_not_the_changelog_head_is_a_finding()
    test_another_products_version_is_not_read_as_a_dating()
    test_the_root_readme_dates_a_change_by_the_plugin_name()
    test_matching_counts_have_no_findings()
    test_a_stale_hook_count_in_the_root_summary_is_a_finding()
    test_the_repository_readmes_agree_with_the_releases()
    test_the_repository_hook_counts_agree()
    test_the_session_workflow_hooks_description_carries_no_count_word()
    test_a_hook_added_to_the_session_workflow_plugin_leaves_the_description_alone()
    test_the_scan_sees_what_it_guards()
    print('ok: the READMEs agree with the manifests, CHANGELOGs and hooks.json files')

#!/usr/bin/env python3
"""Checks of the README's account of notes, facts, version 3 and the two packs.

Contract under test:
- the README holds two fenced `json` blocks, one prompt note and one outcome
  note, and both are valid under `notes.py`;
- its one example `pack.toml` is the series pack's (`name = "series"`, the
  checker `series-check` that records `outcome`, no `[prevention]` table), and
  built beside a checker file that defines `check` and `record` it gives a
  policy that loads with those `records`;
- every `kit` subcommand and every `--option` it names exists in the parser;
- under the heading "What this slice does not do" each limit of this slice
  appears with its first sentence, verbatim, on one line;
- it names the `notes` section of the doctor, `note_config.json`, `facts.lock`
  and the two switches of the cores, and `docs/portability.md` points at notes.

Stdlib-runnable: `python test_readme_notes.py`.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
REPO = KIT_ROOT.parent
README = KIT_ROOT / 'README.md'
PORTABILITY = REPO / 'docs' / 'portability.md'
sys.path.insert(0, str(KIT_ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_kit import cli, notes  # noqa: E402
from harness_kit.policy import load_policy  # noqa: E402
from kit_fixtures import SAMPLE_POLICY, SRC, run_module  # noqa: E402

FENCE = re.compile(r'^```(\w*)\n(.*?)^```$', re.MULTILINE | re.DOTALL)
HEADING = '## What this slice does not do'
CHECKER = (
    'def check(act, observation, facts):\n    return {"result": "no-match"}\n\n\n'
    'def record(note, facts):\n    return {"result": "unchanged"}\n'
)
LIMITS = (
    'It prevents nothing: as with every rule of the kit, a refusal is feedback to the model '
    'inside one turn.',
    "It does not wire the kit into the owner's daily sessions.",
    'It changes nothing under `plugins/`; the cores stay as they are, and the packs use some of '
    'their private names until `plugins/` can change.',
    'It does not prove who typed a prompt.',
    "It does not treat opencode's own configuration files as governed files: the four families "
    "are the core's, which speak of the owner's Claude Code home.",
    'It does not check that the note hooks are present at launch: the canary judges the '
    'PreToolUse guard only, and a home rendered without note hooks is refused only by the static '
    'check of the rendered home that `kit run` makes.',
    "It does not keep every prompt note: a prompt note that is not recorded (the shell's "
    'deadline, a lock not obtained, a conflict, a failed recorder) leaves the earlier owner '
    'prompt in force until the next prompt that is recorded, so an act the earlier prompt named '
    'stays allowed meanwhile.',
    'It does not tell a script written by a Bash heredoc from a command: the owner-acts rule '
    'reads every command in both dialects, so a heredoc body whose lines name an owner act (a '
    'script written to a file) is denied, where the core allows it.',
    'It does not survive a shell file removed during a session on Claude Code: the interpreter '
    'then exits 2 for every hook, which blocks each prompt as well as each tool call (inferred; '
    'at launch the canary refuses such a home).',
    'Facts exist only inside a minted run, one that `kit run`, `kit state new-run` or '
    '`kit doctor --live` made; a session started outside one has none, so the owner-acts rule '
    'denies every owner act there and the series rule never denies.',
    "In a launched session the cores' switches (`SESSION_WORKFLOW_SERIES_GUARD`, "
    '`SESSION_WORKFLOW_OWNER_ACTS_GATE`) are absent, so both rules are on.',
    'A refused call leaves no outcome note on either harness (measured): the series rule counts '
    'only pull requests whose create ran and printed a URL.',
    "It does not tie a child session's notes and judgements to one root on opencode when the "
    'walk to the root ends early in one hook and not in another: each hook walks on its own, and '
    'a walk that ends early keys the child by its own id, so the series rule may miss a pull '
    'request and the owner-acts rule may deny an act the owner named.',
    'It does not order calls that run in parallel: Claude Code can run the calls of one '
    'assistant message in parallel (measured for two read-only calls), so a create issued beside '
    'the first one is not seen by the series rule.',
    "With the owner-acts pack in the policy, opencode's `patch` tool is refused: the shell does "
    'not observe its paths, the governed rule cannot tell, and the verdict is `unknown`.',
    "The owner-acts refusal does not carry the core's per-family side effects and example "
    "sentence: the rule's reason is one fixed text, and the detail names the denied acts.",
)


def _text() -> str:
    return README.read_text(encoding='utf-8')


def _blocks(lang: str) -> list[str]:
    return [body for tag, body in FENCE.findall(_text()) if tag == lang]


def _section(heading: str) -> str:
    match = re.search(rf'^{re.escape(heading)}\n(.*?)(?=^## |\Z)', _text(), re.M | re.S)
    assert match, f'no section {heading!r}'
    return match.group(1)


def _parser_options(parser: argparse.ArgumentParser) -> tuple[set[str], set[str]]:
    paths: set[str] = set()
    options: set[str] = set()

    def walk(p: argparse.ArgumentParser, prefix: str) -> None:
        for action in p._actions:  # argparse has no public listing
            options.update(o for o in action.option_strings if o.startswith('--'))
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    paths.add(f'{prefix} {name}')
                    walk(child, f'{prefix} {name}')

    walk(parser, 'kit')
    return paths, options


def test_two_example_notes_one_of_each_kind_that_are_valid():
    found = _blocks('json')
    assert len(found) == 2, len(found)
    kinds = []
    for body in found:
        note = notes.check_note(notes.parse_note(body.encode('utf-8')))
        kinds.append(note['note']['kind'])
    assert sorted(kinds) == ['outcome', 'prompt'], kinds


def test_one_example_pack_toml_that_is_the_series_pack_and_builds():
    found = [b for b in _blocks('toml') if re.search(r'^pack = 1$', b, re.M)]
    assert len(found) == 1, len(found)
    data = __import__('tomllib').loads(found[0])
    assert data['name'] == 'series' and 'prevention' not in data, data
    assert [c['id'] for c in data['checker']] == ['series-check'], data
    assert data['checker'][0]['records'] == ['outcome'], data
    assert data['rule'][0]['id'] == 'series-second-pr-declared', data
    assert '[prevention]' not in found[0]
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'pack'
        folder.mkdir()
        (folder / 'pack.toml').write_text(found[0], encoding='utf-8')
        (folder / data['checker'][0]['file']).write_text(CHECKER, encoding='utf-8')
        base = Path(td) / 'base.toml'
        base.write_text(SAMPLE_POLICY, encoding='utf-8')
        out = Path(td) / 'out.toml'
        env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
        env['PYTHONPATH'] = str(SRC)
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                '-m',
                'harness_kit',
                'policy',
                'build',
                '--base',
                str(base),
                '--pack',
                str(folder),
                '--out',
                str(out),
            ],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert load_policy(out).checkers[0].records == ('outcome',)


def test_every_subcommand_and_option_the_readme_names_exists():
    paths, options = _parser_options(cli.build_parser())
    paths.add('kit')
    text = _text()
    named_options = set(re.findall(r'(?<![\w-])(--[a-z][a-z-]*)', text))
    stray = sorted(o for o in named_options if o not in options and o != '--version')
    # `kit run` is dispatched ahead of the parser, so its own flags are not listed there;
    # `--project` belongs to uv, in the install command.
    stray = [o for o in stray if o not in ('--workdir', '--home', '--policy', '--project')]
    assert not stray, stray
    for span in re.findall(r'`(kit [^`]*)`', text):
        words = []
        for word in span.split()[1:]:
            if not re.fullmatch(r'[a-z][a-z-]*', word):
                break
            words.append(word)
        path = ' '.join(['kit', *words])
        assert path in paths or path == 'kit run' or words[:1] == ['run'], span
    for line in re.findall(r'^kit [^\n]*', text, re.M):
        assert line.split()[1] in {p.split()[1] for p in paths if ' ' in p} | {'run'}, line


def test_the_readme_names_the_parts_of_this_slice():
    text = _text()
    for word in (
        '`kit note`',
        '`kit home render`',
        'note_config.json',
        'facts.lock',
        'notes.ndjson',
        '`record(note, facts)`',
        '`check(act, observation, facts)`',
        '`records`',
        'SESSION_WORKFLOW_SERIES_GUARD',
        'SESSION_WORKFLOW_OWNER_ACTS_GATE',
        'SESSION_WORKFLOW_GOVERNED_HOME',
        'series-second-pr-declared',
        'owner-acts-named-by-owner',
        '`None`',
        'The `notes` section',
    ):
        assert word in text, word
    assert len(_blocks('toml')) == 2, len(_blocks('toml'))


def test_each_limit_of_this_slice_sits_under_the_heading_on_one_line():
    lines = _section(HEADING).splitlines()
    for limit in LIMITS:
        assert any(line.lstrip('- ').startswith(limit) for line in lines), limit


def test_the_portability_page_points_at_notes():
    text = PORTABILITY.read_text(encoding='utf-8')
    assert re.search(r'\bnotes?\b', text) and 'harness-kit/README.md' in text


if __name__ == '__main__':
    run_module(globals(), 'readme notes')

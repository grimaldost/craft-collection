#!/usr/bin/env python3
"""Checks of the README's account of daily use on opencode.

Contract under test:
- the README has a section each on the interactive mode, daily homes and the
  relay, and the governance of opencode's configuration; the interactive one
  states the canary's median duration (3.1 s over five launches); the daily one
  names the daily file's tables, the ceilings, which hold per state root, and
  `kit relay summary`; the governance one says that a setting changed in the
  interface during a governed session ends it with `config-changed`, that the
  kit refuses `opencode_worktree_remove` and that it switches off
  `opencode_session_move`, and what an edit of the global `AGENTS.md` reached
  with the file watcher off;
- the exit-code table has 65 for a changed home too, 66 and 130;
- the subcommand table's rows name `kit relay serve`, `kit relay summary` and
  `kit home wire`, `kit run`'s `--mode` and `--accept-version`, and
  `kit home render`'s `--daily`;
- no sentence says that `kit run` accepts only headless sessions;
- under the heading "What this slice does not do", one line names the earlier
  items daily use lifts, and the first sentence of each of daily use's own
  limits appears, verbatim, on one line;
- the permissions section says whether the kit's journal holds a verdict for a
  call the native layer refused, and the doctor section names the mode line and
  the run statuses `config-changed` and `interrupted`;
- the daily section says that opencode's grep and glob need a ripgrep, where
  opencode looks for one and that its download is refused; names the `tools`
  table's two keys, both or neither, the hash in lowercase hex and
  `Get-FileHash`'s uppercase; says what is refused at load, at render and at
  `kit run`, what is watched and what protected, that a hand copy is refused,
  the gap of a home that names none in its four places, that a session places
  such a program only by a write or a shell command, each judged by the kit,
  that nothing downloads a binary, and the consequence of a ripgrep installed
  on `PATH`; it never says that opencode's permission section asks about shell
  commands; the daily file's example shows the table in its `text` fence with
  a placeholder path; no inline span writes `tools =`, `ripgrep =`,
  `ripgrep_sha256 =` or `[tools]`, and no `toml` fence names those keys;
- the `kit doctor` row and the doctor section name `--home DIR` and its line,
  which reads absolute `PATH` entries and the home's `bin` only, with the
  system's `PATHEXT` on Windows;
- `docs/portability.md` points at daily use in the README.

Stdlib-runnable: `python test_readme_daily.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from kit_fixtures import run_module

KIT_ROOT = Path(__file__).resolve().parents[1]
README = KIT_ROOT / 'README.md'
PORTABILITY = KIT_ROOT.parent / 'docs' / 'portability.md'
HEADING = '## What this slice does not do'
LIMITS = (
    "It prevents nothing a process of the session can do as the owner's account.",
    "It does not keep the account's own stores out of reach: a credential manager, an SSH "
    "agent, the terminal that started `kit run`, the relay's memory and the kit's state root "
    'are reachable by a shell command of the session (inferred).',
    "It does not stop a shell write to opencode's configuration before it happens: the check "
    'during the run finds it within about 2 seconds and ends the session, and calls made in '
    'between may go unjudged.',
    "It does not see a shell write into the interpreter's own installation, its standard "
    'library among them, or into a `__pycache__` folder the judge loads from.',
    'It does not bind a `cd` inside a command: `launcher.workdir` reads only the folder a tool '
    'call starts in, and a shell command can change folder after it starts.',
    'It does not judge a project the owner switches to in the interface when that '
    "project's file removes the kit plugin, and a tool the home switches off is offered again "
    'there when that file allows it.',
    'It does not block network connections that ignore the proxy variables: the relay refuses '
    'proxy requests, and nothing else stands between the session and the network.',
    'It does not carry session facts across runs: a session continued in a new run starts with '
    "none, so the owner-acts rule denies an owner act until the owner's next prompt is "
    'recorded.',
    'It does not run interactive sessions on Claude Code or on POSIX systems.',
    'It does not judge sessions of a desktop app that runs its own copy of a harness.',
    'It does not measure the relay against a real provider: every relay test forwards to a '
    'local stub.',
    'It does not keep a prompt note lost before its pending stamp: a note that never reaches '
    '`kit note` leaves the earlier owner prompt in force until the next prompt that is '
    'recorded.',
    "It does not guard a bare opencode start beyond the wired plugin's own judgement: a "
    'configuration layer the bare start reads may remove the plugin before it loads.',
    "It does not apply the wiring of the kit plugin to the owner's configuration: that is the "
    "owner's act.",
    'It does not run two daily sessions on one state root at once: the relay holds its '
    "ledger's lock.",
)


def _text() -> str:
    return README.read_text(encoding='utf-8')


def _section(heading: str) -> str:
    match = re.search(rf'^{re.escape(heading)}\n(.*?)(?=^## |\Z)', _text(), re.M | re.S)
    assert match, f'no section {heading!r}'
    return match.group(1)


def _flat(text: str) -> str:
    return ' '.join(text.split())


def _row(code_or_command: str) -> str:
    rows = [line for line in _text().splitlines() if line.startswith(f'| {code_or_command}')]
    assert len(rows) == 1, (code_or_command, rows)
    return rows[0]


def test_each_daily_use_limit_sits_under_the_heading_on_one_line():
    lines = _section(HEADING).splitlines()
    for limit in LIMITS:
        assert any(line.lstrip('- ').startswith(limit) for line in lines), limit


def test_one_line_names_the_earlier_items_daily_use_lifts():
    lines = _section(HEADING).splitlines()
    named = [
        line
        for line in lines
        if 'not wired into a daily session' in line
        and '`patch`' in line
        and 'pending stamp' in line
        and 'earlier owner prompt in force' in line
    ]
    assert len(named) == 1, named
    first_limit = next(i for i, line in enumerate(lines) if LIMITS[0] in line)
    assert lines.index(named[0]) < first_limit, 'the lifted items come before the limits'


def test_the_daily_use_sections_hold_their_facts():
    interactive = _flat(_section('## Interactive mode'))
    for needle in (
        '`kit run --mode interactive`',
        '`--standalone`',
        '3.1 s',
        'five launches',
        '`run-open.json`',
        '`launcher.workdir`',
    ):
        assert needle in interactive, needle
    daily = _flat(_section('## Daily homes and the relay'))
    for needle in (
        '`daily = 1`',
        '`[relay]`',
        '`[git]`',
        'per state root',
        '`kit relay summary`',
        '`kit relay serve`',
        '`KIT_RELAY_CAPABILITY`',
        'an example',
    ):
        assert needle in daily, needle
    governance = _flat(_section("## Governance of opencode's configuration"))
    for needle in (
        'a setting changed in the interface',
        '`config-changed`',
        '`opencode_worktree_remove`',
        '`opencode_session_move`',
        '`AGENTS.md`',
        'file watcher',
        '`config.protected`',
    ):
        assert needle in governance, needle


def test_the_exit_codes_and_the_subcommand_rows():
    assert 'home' in _row('65 |') and 'canary' in _row('65 |'), _row('65 |')
    assert '`config-changed`' in _row('66 |'), _row('66 |')
    assert 'interrupt' in _row('130 |').lower(), _row('130 |')
    run = _row('`kit run ')
    assert '--mode' in run and '--accept-version' in run, run
    assert '--daily' in _row('`kit home render '), _row('`kit home render ')
    assert '`kit relay summary' in _row('`kit relay serve '), _row('`kit relay serve ')
    assert '--check' in _row('`kit home wire '), _row('`kit home wire ')


def test_no_sentence_says_kit_run_takes_only_headless_sessions():
    flat = _flat(_text())
    assert not re.search(r'only a headless session|headless sessions? only', flat), flat


def test_the_permissions_and_doctor_sections_hold_the_daily_use_facts():
    permissions = _flat(_section('## Permissions'))
    assert 'journal held a verdict' in permissions, permissions
    doctor = _flat(_section('## Reading `kit doctor`'))
    for needle in ('mode interactive', '`config-changed`', '`interrupted`'):
        assert needle in doctor, needle


def _ripgrep_paragraph() -> str:
    """The daily section's paragraph on the ripgrep the daily file names."""
    found = [p for p in _section('## Daily homes and the relay').split('\n\n') if '`tools`' in p]
    assert len(found) == 1, found
    return _flat(found[0])


def test_the_daily_section_states_the_named_ripgrep():
    text = _ripgrep_paragraph()
    for needle in (
        "opencode's `grep` and `glob`",
        '`PATH`',
        '`xdg/cache/opencode/bin`',
        'github.com',
        'the relay refuses',
        '`tools`',
        '`ripgrep`',
        '`ripgrep_sha256`',
        'both or neither',
        'lowercase hex',
        "PowerShell's `Get-FileHash` prints uppercase",
        'at load',
        'one key without the other',
        'a relative path',
        'not 64 lowercase hex characters',
        'before it writes anything',
        '`kit run` refuses a copy that no longer matches',
        'in the working folder',
        'watched in every opencode home',
        'protected only in a home that names one',
        'hand-copied',
        'in any home in interactive mode',
        'nothing downloads a binary',
        'winget, scoop or choco',
        'names none',
    ):
        assert needle in text, needle


def test_the_daily_section_states_the_gap_of_a_home_that_names_none():
    text = _ripgrep_paragraph()
    for needle in (
        'a daily home that names no ripgrep',
        'runs unjudged inside a judged `grep` or `glob` call',
        "a repository's own `rg.exe`",
        'needs no act of the session',
        'an empty or relative `PATH` entry',
        'a `PATH` folder',
        '`PATHEXT` variant',
        'until the next poll',
        'watched and not protected',
        'only by a write or a shell command, each judged by the kit',
    ):
        assert needle in text, needle
    flat = _flat(_text())
    assert not re.search(r'permission\w* (section|layer)?\s*asks? about shell', flat), flat


def test_the_tools_keys_stand_as_bare_spans_or_in_the_text_fence_only():
    text = _text()
    spans = re.findall(r'`([^`\n]+)`', re.sub(r'```.*?```', '', text, flags=re.S))
    for span in spans:
        for key in ('tools', 'ripgrep', 'ripgrep_sha256'):
            assert not re.match(rf'\s*{key}\s*=', span), span
        assert '[tools]' not in span, span
    for fence in re.findall(r'```toml\n(.*?)```', text, flags=re.S):
        for key in ('tools', 'ripgrep', 'ripgrep_sha256'):
            assert not re.search(rf'(?m)^\s*\[?{key}\b', fence), fence
    daily = _section('## Daily homes and the relay')
    example = re.findall(r'```text\n(.*?)```', daily, flags=re.S)
    assert example and '[tools]' in example[0], example
    tools = example[0].split('[tools]', 1)[1]
    assert re.search(r'(?m)^ripgrep = "C:/Users/me/', tools), tools
    assert re.search(r'(?m)^ripgrep_sha256 = "[0-9a-f]{64}"$', tools), tools


def test_the_doctor_row_and_section_name_the_home_line():
    row = _row('`kit doctor ')
    assert '--home DIR' in row, row
    doctor = _flat(_section('## Reading `kit doctor`'))
    for needle in (
        '`kit doctor --home DIR`',
        '`ripgrep: `',
        '`home`',
        'absolute `PATH` entries',
        "the home's `bin` folder",
        'no working folder',
        'no empty or relative entry',
        '`PATHEXT`',
        'as the system holds it',
        'starts no program',
    ):
        assert needle in doctor, needle


def test_the_front_door_carries_no_section_mark():
    for path in (README, PORTABILITY):
        assert '§' not in path.read_text(encoding='utf-8'), path


def test_the_portability_page_points_at_daily_use():
    text = PORTABILITY.read_text(encoding='utf-8')
    assert re.search(r'daily (use|session|home)', text) and 'harness-kit/README.md' in text


if __name__ == '__main__':
    run_module(globals(), 'readme daily use')

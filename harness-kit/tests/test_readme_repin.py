#!/usr/bin/env python3
"""Checks of the README's account of the version pin and of a re-pin.

Contract under test:
- the README has a section `## Re-pinning a harness version`, the heading that
  `kit run`'s refusal of another version points at;
- that section names the refusal and `--accept-version` (with `accepted_version`
  in `run.json` and the run not covered by the contract), auto-update off in
  every home, and the procedure: the new version installed beside the pinned
  one, every conformance file run against it with
  `KIT_CONFORMANCE_ACCEPT_VERSION`, `conformance/repin_check.py` against the
  edited contract (`CELLS_BY_HARNESS`, the one accepted failure
  `loopback-fetch-refused`), and one pull request for the contract's version and
  evidence; and that a new tool fails `offered-tools` and the re-pin decides it.

Stdlib-runnable: `python test_readme_repin.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from kit_fixtures import run_module

KIT_ROOT = Path(__file__).resolve().parents[1]
README = KIT_ROOT / 'README.md'
LAUNCHER = KIT_ROOT / 'src' / 'harness_kit' / 'launcher.py'
HEADING = '## Re-pinning a harness version'


def _section() -> str:
    text = README.read_text(encoding='utf-8')
    assert text.count(HEADING + '\n') == 1, 'the heading appears once'
    body = text.split(HEADING + '\n', 1)[1]
    return re.split(r'(?m)^## ', body, maxsplit=1)[0]


def _flat(text: str) -> str:
    return ' '.join(text.split())


def test_the_refusal_points_at_the_section():
    title = HEADING.removeprefix('## ')
    assert f'"{title}"' in LAUNCHER.read_text(encoding='utf-8'), title
    _section()


def test_the_section_names_the_pin_and_the_way_past_it():
    text = _flat(_section())
    for needle in (
        '[harness] version',
        'exit 64',
        '`kit run --accept-version VERSION`',
        '`accepted_version`',
        'not covered by the contract',
        '`OPENCODE_DISABLE_AUTOUPDATE`',
        '`DISABLE_AUTOUPDATER`',
    ):
        assert needle in text, needle


def test_the_section_states_the_procedure():
    text = _flat(_section())
    for needle in (
        'beside the pinned one',
        '`KIT_CONFORMANCE_ACCEPT_VERSION`',
        '`conformance/repin_check.py`',
        '`CELLS_BY_HARNESS`',
        '`loopback-fetch-refused`',
        'one pull request',
        'by hand',
        '`offered-tools`',
        'refused tools',
    ):
        assert needle in text, needle


if __name__ == '__main__':
    run_module(globals(), 'readme re-pin')

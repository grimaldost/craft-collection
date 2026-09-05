#!/usr/bin/env python3
"""Self-contained checks for mirror_check.py (no pytest required)."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mirror_check as mc

CANONICAL = """
schema_version = '1'

[meta]
last_reviewed = "2026-09-05"
review_by = "2026-12-05"

[[models]]
tier = 'weak'
api_string = 'claude-haiku-4-5'
harness_alias = 'haiku'
display = 'Haiku 4.5'
available = true
notes = ''

[[models]]
tier = 'frontier'
api_string = 'claude-fable-5-1'
harness_alias = 'fable'
display = 'Fable 5.1'
available = true
notes = ''
"""


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mc.main(argv)
    return rc, buf.getvalue()


class Stack:
    """A throwaway tree: a canonical models.toml, a bindings file, and mirror files."""

    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix='mirror-check-'))
        self.canonical = self.dir / 'models.toml'
        self.canonical.write_text(CANONICAL, encoding='utf-8')
        self.bindings = self.dir / 'model-mirrors.toml'

    def file(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return p

    def bind(self, body: str) -> None:
        header = f'canonical = "{self.canonical.as_posix()}"\n\n'
        self.bindings.write_text(header + body, encoding='utf-8')

    def check(self, *extra: str) -> tuple[int, str]:
        return _run(['--bindings', str(self.bindings), *extra])


def test_absent_bindings_file_says_so_and_does_not_fail():
    """An absent file is the correct state for a fresh environment -- but the walk
    must SAY it was skipped, or 'no sites to walk' and 'no bindings' read alike."""
    missing = Path(tempfile.mkdtemp(prefix='mirror-check-')) / 'nope.toml'
    rc, out = _run(['--bindings', str(missing)])
    assert rc == 0, 'an absent bindings file is not a failure'
    assert 'SKIPPED' in out, out
    assert str(missing) in out, out
    out.encode('ascii')


def test_a_clean_stack_reports_every_site_walked():
    s = Stack()
    site = s.file(
        'engine/governance.py',
        "TIER = {'frontier': 'claude-fable-5-1'}\n# lineup synced 2026-09-05\n",
    )
    s.bind(f"""
[[site]]
path = "{site.as_posix()}"
mirrors = "tier-to-model map"
vocabulary = "tier"
role = "fallback"
stamp = "lineup synced"
backlog = "{(s.dir / 'engine/backlog.md').as_posix()}"
""")
    rc, out = s.check()
    assert rc == 0, out
    assert '1 site(s) walked' in out, out


def test_a_site_with_neither_backlog_nor_status_is_a_finding():
    """The rule the bindings file exists to enforce: a registered mirror no
    backlog tracks drifts silently."""
    s = Stack()
    site = s.file('engine/governance.py', 'x = 1\n')
    s.bind(f"""
[[site]]
path = "{site.as_posix()}"
mirrors = "tier-to-model map"
vocabulary = "tier"
role = "fallback"
""")
    rc, out = s.check()
    assert rc == 1, out
    assert 'no backlog row' in out, out


def test_a_registered_path_that_does_not_exist_is_a_finding():
    s = Stack()
    s.bind(f"""
[[site]]
path = "{(s.dir / 'gone.py').as_posix()}"
mirrors = "prices"
vocabulary = "family"
role = "example"
status = "pending removal"
""")
    rc, out = s.check()
    assert rc == 1, out
    assert 'path does not exist' in out, out


def test_a_stale_stamp_is_a_finding_and_names_both_dates():
    """The stamp is compared for EQUALITY with the canonical last_reviewed, not
    for age: one clock, so a copy cannot certify itself fresh."""
    s = Stack()
    site = s.file('engine/governance.py', '# lineup synced 2026-08-11\n')
    s.bind(f"""
[[site]]
path = "{site.as_posix()}"
mirrors = "tier-to-model map"
vocabulary = "tier"
role = "fallback"
stamp = "lineup synced"
status = "no backlog row yet"
""")
    rc, out = s.check()
    assert rc == 1, out
    assert '2026-09-05' in out and 'lineup synced' in out, out


def test_a_retired_string_still_present_is_a_finding():
    """The catch-all: this is what finds a mirror nobody registered."""
    s = Stack()
    s.file('engine/pricing.py', "RATES = {'sonnet': (0.003, 0.015)}\n")
    s.file('engine/governance.py', "TIER = {'frontier': 'claude-fable-5'}\n")
    s.bind(f"""
[[retired]]
pattern = "claude-fable-5(?![-.0-9])"
reason = "superseded by claude-fable-5-1"
roots = ["{(s.dir / 'engine').as_posix()}"]

[[retired]]
pattern = "0\\\\.003, 0\\\\.015"
reason = "Sonnet 4.6 rate; the mid tier runs Sonnet 5 at 0.002/0.010"
roots = ["{(s.dir / 'engine').as_posix()}"]
""")
    rc, out = s.check()
    assert rc == 1, out
    assert 'pricing.py' in out and 'governance.py' in out, out
    assert 'claude-fable-5' in out, out


def test_the_successor_does_not_match_the_retired_predecessor():
    """`claude-fable-5-1` must not be reported as the retired `claude-fable-5`,
    or every walk after the fix reports the fix as the defect."""
    s = Stack()
    s.file('engine/governance.py', "TIER = {'frontier': 'claude-fable-5-1'}\n")
    s.bind(f"""
[[retired]]
pattern = "claude-fable-5(?![-.0-9])"
reason = "superseded"
roots = ["{(s.dir / 'engine').as_posix()}"]
""")
    rc, out = s.check()
    assert rc == 0, out


def test_excluded_globs_are_not_grepped():
    """Frozen eval fixtures carry outgoing strings on purpose (byte-preserved
    experiment material). Without this the walk drowns in its own noise."""
    s = Stack()
    s.file('engine/tasks/frozen-v1/plugins/hp/models.toml', "api_string = 'claude-fable-5'\n")
    s.bind(f"""
[[retired]]
pattern = "claude-fable-5(?![-.0-9])"
reason = "superseded"
roots = ["{(s.dir / 'engine').as_posix()}"]

[[exclude]]
glob = "**/tasks/**"
reason = "byte-preserved eval fixture"
""")
    rc, out = s.check()
    assert rc == 0, out
    assert 'excluded' in out.lower(), 'an exclusion that hides work must be reported, not silent'


def test_a_resolution_path_site_is_reported_as_the_goal_not_yet_met():
    """After the dependency design lands, no mirror should still DECIDE a run."""
    s = Stack()
    site = s.file('engine/governance.py', 'x = 1\n')
    s.bind(f"""
[[site]]
path = "{site.as_posix()}"
mirrors = "tier-to-model map"
vocabulary = "tier"
role = "resolution-path"
status = "no backlog row yet"
""")
    rc, out = s.check()
    assert rc == 1, out
    assert 'resolution-path' in out, out


def test_unreadable_bindings_cannot_answer_and_exits_two():
    """A gate that cannot see the diff must say so rather than pass."""
    s = Stack()
    s.bindings.write_text('this is not = = toml\n', encoding='utf-8')
    rc, out = s.check()
    assert rc == 2, out


def test_env_override_is_honored():
    s = Stack()
    s.bind('')
    saved = os.environ.get(mc.BINDINGS_ENV)
    os.environ[mc.BINDINGS_ENV] = str(s.bindings)
    try:
        rc, out = _run([])
        assert rc == 0, out
        assert '0 site(s) walked' in out, out
    finally:
        if saved is None:
            os.environ.pop(mc.BINDINGS_ENV, None)
        else:
            os.environ[mc.BINDINGS_ENV] = saved


def main() -> int:
    test_absent_bindings_file_says_so_and_does_not_fail()
    test_a_clean_stack_reports_every_site_walked()
    test_a_site_with_neither_backlog_nor_status_is_a_finding()
    test_a_registered_path_that_does_not_exist_is_a_finding()
    test_a_stale_stamp_is_a_finding_and_names_both_dates()
    test_a_retired_string_still_present_is_a_finding()
    test_the_successor_does_not_match_the_retired_predecessor()
    test_excluded_globs_are_not_grepped()
    test_a_resolution_path_site_is_reported_as_the_goal_not_yet_met()
    test_unreadable_bindings_cannot_answer_and_exits_two()
    test_env_override_is_honored()
    print('ok: mirror_check')
    return 0


if __name__ == '__main__':
    sys.exit(main())

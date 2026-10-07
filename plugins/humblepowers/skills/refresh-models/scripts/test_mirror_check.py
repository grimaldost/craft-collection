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

    def repo(self, name: str) -> Path:
        """A directory that reads as a repository root: it holds ``.git/``."""
        p = self.dir / name
        (p / '.git').mkdir(parents=True, exist_ok=True)
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


RETIRED = 'claude-fable-5(?![-.0-9])'


def _site(path: Path) -> str:
    """A [[site]] block that is clean on its own, so any finding comes from the sweep."""
    return f"""
[[site]]
path = "{path.as_posix()}"
mirrors = "tier-to-model map"
vocabulary = "tier"
role = "fallback"
backlog = "{(path.parent / 'backlog.md').as_posix()}"
"""


def _retired(*roots: Path) -> str:
    listed = ', '.join(f'"{r.as_posix()}"' for r in roots)
    return f"""
[[retired]]
pattern = "{RETIRED}"
reason = "superseded by claude-fable-5-1"
roots = [{listed}]
"""


def _hits(out: str) -> list[str]:
    return [line for line in out.splitlines() if 'is still here' in line]


def test_a_retired_id_in_an_unlisted_file_of_a_site_repository_is_found():
    """Acceptance for T101a. A pattern's own roots are where someone thought to
    look; the copy nobody wrote down sits elsewhere in the same repository. With
    no ``sweep_roots`` key, every pattern is also swept across the repository
    root of every registered site."""
    s = Stack()
    repo = s.repo('repo')
    site = s.file('repo/src/gov.py', "TIER = {'frontier': 'claude-fable-5-1'}\n")
    s.file('repo/docs/notes.md', 'The frontier tier runs claude-fable-5 today.\n')
    s.bind(_site(site) + _retired(repo / 'src'))
    rc, out = s.check()
    assert rc == 1, out
    assert any('notes.md' in line for line in _hits(out)), out


def test_the_summary_names_the_roots_swept():
    """A narrow walk must read as narrow: the closing line says which roots every
    pattern was swept across, so a reader can see what was not searched."""
    s = Stack()
    repo = s.repo('repo')
    site = s.file('repo/src/gov.py', "TIER = {'frontier': 'claude-fable-5-1'}\n")
    s.bind(_site(site) + _retired(repo / 'src'))
    rc, out = s.check()
    assert rc == 0, out
    last = out.strip().splitlines()[-1]
    assert 'Swept 1 root(s)' in last, last
    assert repo.resolve().as_posix() in last, last


def test_an_explicit_sweep_roots_list_is_used_exactly():
    """A present key replaces the default rather than adding to it, and an empty
    list is the opt-out: no roots beyond each pattern's own."""
    s = Stack()
    repo = s.repo('repo')
    site = s.file('repo/src/gov.py', "TIER = {'frontier': 'claude-fable-5-1'}\n")
    s.file('repo/docs/notes.md', 'claude-fable-5\n')
    loose = s.dir / 'loose'
    s.file('loose/old.md', 'claude-fable-5\n')

    s.bind(f'sweep_roots = ["{loose.as_posix()}"]\n' + _site(site) + _retired(repo / 'src'))
    rc, out = s.check()
    assert rc == 1, out
    assert any('old.md' in line for line in _hits(out)), out
    assert not any('notes.md' in line for line in _hits(out)), 'the default must not apply'

    s.bind('sweep_roots = []\n' + _site(site) + _retired(repo / 'src'))
    rc, out = s.check()
    assert rc == 0, out
    assert 'Swept 0 root(s)' in out, out


def test_a_site_outside_any_repository_adds_no_default_root():
    """The default is the repository root, never the site's own directory: a
    site in no repository widens nothing, so the pattern's roots stay the walk."""
    s = Stack()
    assert not any((p / '.git').exists() for p in s.dir.parents), (
        f'precondition: the temp dir {s.dir} must sit in no repository'
    )
    site = s.file('engine/src/gov.py', "TIER = {'frontier': 'claude-fable-5-1'}\n")
    s.file('engine/notes.md', 'claude-fable-5\n')
    s.bind(_site(site) + _retired(s.dir / 'engine' / 'src'))
    rc, out = s.check()
    assert rc == 0, out


def test_a_file_under_a_rule_root_and_a_sweep_root_is_reported_once():
    """``repo/src`` is both the pattern's own root and inside the sweep root
    ``repo``; overlapping roots must not double-report."""
    s = Stack()
    repo = s.repo('repo')
    site = s.file('repo/src/gov.py', "TIER = {'frontier': 'claude-fable-5-1'}\n")
    s.file('repo/src/old.py', "MODEL = 'claude-fable-5'\n")
    s.file('repo/docs/notes.md', 'claude-fable-5\n')
    s.bind(_site(site) + _retired(repo / 'src'))
    rc, out = s.check()
    assert rc == 1, out
    hits = _hits(out)
    assert len(hits) == 2, out
    assert sum('old.py' in line for line in hits) == 1, out
    assert sum('notes.md' in line for line in hits) == 1, out


def test_exclude_globs_apply_to_sweep_roots():
    """A repository-wide sweep reaches frozen fixtures and historical records;
    ``[[exclude]]`` is how they are kept out, and the count still says so."""
    s = Stack()
    repo = s.repo('repo')
    site = s.file('repo/src/gov.py', "TIER = {'frontier': 'claude-fable-5-1'}\n")
    s.file('repo/tasks/frozen-v1/models.toml', "api_string = 'claude-fable-5'\n")
    s.bind(
        _site(site)
        + _retired(repo / 'src')
        + """
[[exclude]]
glob = "**/tasks/**"
reason = "byte-preserved eval fixture"
"""
    )
    rc, out = s.check()
    assert rc == 0, out
    assert '1 file(s) excluded by glob' in out, out


def test_a_sweep_root_that_does_not_exist_is_a_finding():
    """A sweep root that moved would silently narrow the walk."""
    s = Stack()
    engine = s.dir / 'engine'
    engine.mkdir()
    missing = s.dir / 'moved-away'
    s.bind(f'sweep_roots = ["{missing.as_posix()}"]\n' + _retired(engine))
    rc, out = s.check()
    assert rc == 1, out
    assert f'{missing.as_posix()}: sweep root does not exist' in out, out


def test_a_sweep_roots_string_cannot_answer_instead_of_walking_a_drive():
    """A bare string is not a one-element list: iterated per character it names
    '/' and 'C:', and the walk would sweep the whole drive."""
    s = Stack()
    engine = s.dir / 'engine'
    engine.mkdir()
    s.bind(f'sweep_roots = "{engine.as_posix()}"\n' + _retired(engine))
    rc, out = s.check()
    assert rc == 2, out
    assert 'CANNOT ANSWER' in out and 'sweep_roots must be a list of absolute paths' in out, out


def test_a_relative_sweep_root_cannot_answer():
    """A relative entry would resolve against whatever directory the walk ran from."""
    s = Stack()
    engine = s.dir / 'engine'
    engine.mkdir()
    s.bind('sweep_roots = ["engine"]\n' + _retired(engine))
    rc, out = s.check()
    assert rc == 2, out
    assert 'CANNOT ANSWER' in out and 'sweep_roots must be a list of absolute paths' in out, out


def test_a_retired_roots_string_or_relative_entry_cannot_answer():
    s = Stack()
    engine = s.dir / 'engine'
    engine.mkdir()
    for roots in (f'"{engine.as_posix()}"', '["engine"]'):
        s.bind(f'[[retired]]\npattern = "x"\nreason = "r"\nroots = {roots}\n')
        rc, out = s.check()
        assert rc == 2, out
        assert 'CANNOT ANSWER' in out and '[[retired]] roots must be a list' in out, out


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
    test_a_retired_id_in_an_unlisted_file_of_a_site_repository_is_found()
    test_the_summary_names_the_roots_swept()
    test_an_explicit_sweep_roots_list_is_used_exactly()
    test_a_site_outside_any_repository_adds_no_default_root()
    test_a_file_under_a_rule_root_and_a_sweep_root_is_reported_once()
    test_exclude_globs_apply_to_sweep_roots()
    test_a_sweep_root_that_does_not_exist_is_a_finding()
    test_a_sweep_roots_string_cannot_answer_instead_of_walking_a_drive()
    test_a_relative_sweep_root_cannot_answer()
    test_a_retired_roots_string_or_relative_entry_cannot_answer()
    print('ok: mirror_check')
    return 0


if __name__ == '__main__':
    sys.exit(main())

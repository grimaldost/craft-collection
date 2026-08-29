"""Tests for check_release_discipline.py.

Contract under test:
- a plugin name is derived from changed paths, with that plugin's own
  CHANGELOG.md and README.md exempt;
- the changelog's top heading must parse as `## [X.Y.Z] - YYYY-MM-DD` and name
  the HEAD version -- the old em-dash grammar does not parse;
- a touched plugin with an unchanged (or non-increasing) version is a
  finding, as is a bumped version the changelog top heading does not carry;
- a leading `## [Unreleased]` section is skipped, never satisfying;
- a rename out of a plugin still counts as touching it (--no-renames);
- a `Release-note: none (<reason>)` GIT TRAILER waives the PR; prose that
  merely quotes the convention does not;
- an unreadable diff (unknown base ref) is exit 2, never a quiet pass.

The red proof is `test_a_plugin_touching_no_bump_diff_exits_1`: it builds a
real repository, commits a plugin edit with no bump, and watches the CLI exit
1 -- the exact shape of the incident the check exists to stop (two behavior
fixes shipped under an unchanged 0.23.0).

Stdlib-runnable: `python test_check_release_discipline.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_release_discipline as crd

SCRIPT = Path(__file__).resolve().parent / 'check_release_discipline.py'

NEW_HEADING = '## [{v}] - 2026-01-01'
OLD_HEADING = '## {v} — 2026-01-01'  # the pre-2026-08-29 grammar


def _git(cwd: Path, *args: str) -> None:
    # Nothing ambient, everything intentional: GIT_* is scrubbed (git exports
    # the repo location into hooks) and global/system config is silenced so the
    # fixture commits need no local identity, signing, or hooksPath.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(cwd), *args],  # noqa: S607 - git resolved from PATH
        check=True,
        capture_output=True,
        timeout=30,
        env=env,
    )


def _commit(cwd: Path, message: str) -> None:
    _git(cwd, 'add', '-A')
    _git(
        cwd,
        '-c',
        'user.name=t',
        '-c',
        'user.email=t@example.invalid',
        'commit',
        '-q',
        '-m',
        message,
    )


def _seed_repo(root: Path, version: str = '0.1.0') -> None:
    """A repository with one plugin at `version`, branch `base` at the seed."""
    plugin = root / 'plugins' / 'x'
    (plugin / '.claude-plugin').mkdir(parents=True)
    (plugin / 'skills' / 's').mkdir(parents=True)
    manifest = {'name': 'x', 'version': version}
    (plugin / '.claude-plugin' / 'plugin.json').write_text(json.dumps(manifest), encoding='utf-8')
    (plugin / 'CHANGELOG.md').write_text(
        '# Changelog\n\n' + NEW_HEADING.format(v=version) + '\n\n- seed\n', encoding='utf-8'
    )
    (plugin / 'skills' / 's' / 'SKILL.md').write_text('body\n', encoding='utf-8')
    _git(root, 'init', '-q')
    _commit(root, 'seed')
    _git(root, 'branch', 'base')


def run_cli(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), '--base', 'base', '--repo', str(repo)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_touched_plugins_names_the_plugin_and_exempts_its_records():
    changed = [
        'plugins/x/skills/s/SKILL.md',
        'plugins/x/CHANGELOG.md',
        'plugins/y/README.md',
        'plugins/z/references/README.md',  # exempt basenames only directly under the plugin
        'scripts/run_tests.py',
        'README.md',
    ]
    assert crd.touched_plugins(changed) == ['x', 'z']
    assert crd.touched_plugins(['plugins/x/CHANGELOG.md']) == []


def test_top_heading_parses_only_the_bracket_grammar():
    assert crd.top_heading_version('# t\n\n' + NEW_HEADING.format(v='1.2.3') + '\n') == '1.2.3'
    assert crd.top_heading_version('# t\n\n' + OLD_HEADING.format(v='1.2.3') + '\n') is None
    assert crd.top_heading_version('no headings at all\n') is None
    assert crd.top_heading_version(None) is None
    # only the TOP heading counts: a parseable second heading does not rescue it
    text = '# t\n\n## not a release\n\n' + NEW_HEADING.format(v='1.2.3') + '\n'
    assert crd.top_heading_version(text) is None
    # a leading [Unreleased] section is skipped, not satisfying
    text = '# t\n\n## [Unreleased]\n\n- wip\n\n' + NEW_HEADING.format(v='1.2.3') + '\n'
    assert crd.top_heading_version(text) == '1.2.3'
    assert crd.top_heading_version('# t\n\n## [Unreleased]\n\n- wip\n') is None


def test_audit_reddens_on_no_bump_and_on_a_missing_heading():
    same = {'x': {'base_version': '0.1.0', 'head_version': '0.1.0', 'top': '0.1.0'}}
    findings = crd.audit(same)
    assert findings and 'still 0.1.0' in findings[0]
    unlogged = {'x': {'base_version': '0.1.0', 'head_version': '0.2.0', 'top': '0.1.0'}}
    findings = crd.audit(unlogged)
    assert findings and 'top heading' in findings[0]
    clean = {'x': {'base_version': '0.1.0', 'head_version': '0.2.0', 'top': '0.2.0'}}
    assert crd.audit(clean) == []
    # a plugin new at HEAD needs no bump, but still needs its changelog heading
    born = {'x': {'base_version': None, 'head_version': '0.1.0', 'top': '0.1.0'}}
    assert crd.audit(born) == []
    born_unlogged = {'x': {'base_version': None, 'head_version': '0.1.0', 'top': None}}
    assert len(crd.audit(born_unlogged)) == 1
    downgrade = {'x': {'base_version': '0.2.0', 'head_version': '0.1.9', 'top': '0.1.9'}}
    findings = crd.audit(downgrade)
    assert findings and 'does not increase' in findings[0]
    retired = {'x': {'base_version': '0.1.0', 'head_version': None, 'top': None}}
    assert 'gone at HEAD' in crd.audit(retired)[0]
    never_there = {'x': {'base_version': None, 'head_version': None, 'top': None}}
    assert 'missing' in crd.audit(never_there)[0]


def test_a_plugin_touching_no_bump_diff_exits_1():
    """The red proof: the exact incident shape, watched to fail."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        (root / 'plugins' / 'x' / 'skills' / 's' / 'SKILL.md').write_text(
            'changed body\n', encoding='utf-8'
        )
        _commit(root, 'fix(x): behavior change, version untouched')
        proc = run_cli(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'still 0.1.0' in proc.stdout


def test_a_bump_with_a_matching_top_heading_passes():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        plugin = root / 'plugins' / 'x'
        (plugin / 'skills' / 's' / 'SKILL.md').write_text('changed body\n', encoding='utf-8')
        (plugin / '.claude-plugin' / 'plugin.json').write_text(
            json.dumps({'name': 'x', 'version': '0.1.1'}), encoding='utf-8'
        )
        (plugin / 'CHANGELOG.md').write_text(
            '# Changelog\n\n'
            + NEW_HEADING.format(v='0.1.1')
            + '\n\n- fix\n\n'
            + NEW_HEADING.format(v='0.1.0')
            + '\n\n- seed\n',
            encoding='utf-8',
        )
        _commit(root, 'fix(x): behavior change, released')
        proc = run_cli(root)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'bumped and logged' in proc.stdout


def test_a_bump_the_changelog_does_not_carry_exits_1():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        plugin = root / 'plugins' / 'x'
        (plugin / '.claude-plugin' / 'plugin.json').write_text(
            json.dumps({'name': 'x', 'version': '0.1.1'}), encoding='utf-8'
        )
        _commit(root, 'fix(x): bumped but never logged')
        proc = run_cli(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'top heading' in proc.stdout


def test_a_release_note_none_trailer_waives_the_pr():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        (root / 'plugins' / 'x' / 'skills' / 's' / 'SKILL.md').write_text(
            'comment-only edit\n', encoding='utf-8'
        )
        _commit(root, 'docs(x): typo\n\nRelease-note: none (comment-only, nothing ships)')
        proc = run_cli(root)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'Release-note' in proc.stdout


def test_changelog_and_readme_only_changes_need_no_bump():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        plugin = root / 'plugins' / 'x'
        (plugin / 'CHANGELOG.md').write_text('# Changelog\n\n- clarified\n', encoding='utf-8')
        (plugin / 'README.md').write_text('front page\n', encoding='utf-8')
        _commit(root, 'docs(x): records only')
        proc = run_cli(root)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'no plugin files touched' in proc.stdout


def test_declared_reads_trailer_values_not_prose():
    assert crd.declared('none (comment-only, nothing ships)')
    assert crd.declared('\nnone (x)\n\n')
    assert not crd.declared('')
    assert not crd.declared('discussed, reason to follow')
    assert not crd.declared('none without the parenthesised reason')


def test_a_file_renamed_out_of_a_plugin_exits_1():
    """Rename detection reports only the destination path; --no-renames keeps
    the deletion visible, so moving a file out of a plugin still counts."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        skill = root / 'plugins' / 'x' / 'skills' / 's' / 'SKILL.md'
        (root / 'docs').mkdir()
        (root / 'docs' / 'moved.md').write_text(skill.read_text(encoding='utf-8'), encoding='utf-8')
        skill.unlink()
        _commit(root, 'refactor(x): move the skill body out of the plugin')
        proc = run_cli(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'still 0.1.0' in proc.stdout


def test_a_prose_mention_of_the_trailer_does_not_waive():
    """A commit body QUOTING the convention is not a declaration: the waiver is
    read from git's trailer parser, not from a substring over the message."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        (root / 'plugins' / 'x' / 'skills' / 's' / 'SKILL.md').write_text(
            'changed body\n', encoding='utf-8'
        )
        _commit(
            root,
            'fix(x): behavior change, version untouched\n\n'
            'The gate accepts a Release-note: none (reason) trailer, which this\n'
            'commit discusses without declaring.\n\n'
            'A closing paragraph, so the mention is not the trailer block.',
        )
        proc = run_cli(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'still 0.1.0' in proc.stdout


def test_an_unknown_base_ref_is_exit_2_not_a_pass():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_repo(root)
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(SCRIPT), '--base', 'no-such-ref', '--repo', str(root)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert 'cannot read the diff' in proc.stdout


if __name__ == '__main__':
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_') and callable(_fn):
            _fn()
    print('ok: all check_release_discipline tests passed')

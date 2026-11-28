#!/usr/bin/env python3
"""Checks of the opencode driver's ripgrep walk: which file opencode 2.2.5 would run as `rg`.

opencode resolves `rg.exe` (`rg` off Windows) with `which` 6.0.1 over the session's `PATH` with
its `bin` folder appended, each candidate tested as `isexe` 4.0.0 tests it, and falls back to
`bin/rg.exe` when it is a regular file. Contract under test, for `opencode.ripgrep_walk(env,
bin_dir, cwd)`:
- on Windows the current folder is searched first; then each `PATH` entry, split with no
  trimming, one pair of double quotes around an entry removed, the entry joined with the name and
  normalized (`..` removed lexically, a bare drive entry `C:` giving that drive's root), and the
  home's `bin` last; an absent or empty `PATH` gives `bin` alone; the `PATH` key is matched
  without regard to case on Windows;
- a path still relative after the join (an empty, relative or quoted-empty entry) is taken
  against the current folder, on every platform;
- on Windows the names tried in each folder are `rg.exe`, then `rg.exe` with each `PATHEXT` item
  as written and lowercased; a file counts when it is a regular file whose path ends with a
  non-empty `PATHEXT` item, or with any name when `PATHEXT` holds an empty item; an absent or
  empty `PATHEXT` is `.EXE;.CMD;.BAT;.COM`; a folder never counts;
- off Windows the one name is `rg`, and a file counts by `isexe`'s mode rule: execute for others,
  for its group when that is one of the process's groups, or for its owner when that is the
  process's user (so mode `0o001` counts and `0o644` does not);
- the result is the first path that counts, else `bin/rg.exe` when it is a regular file, else
  none; `tried` lists every path the walk tried, in order, each once;
- with no current folder (the doctor's walk) the current-folder entry and every entry still
  relative after the join are left out.

Stdlib-runnable: `python test_ripgrep_walk.py`.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import watch
from harness_kit.harnesses import opencode
from kit_fixtures import run_module

WINDOWS = os.name == 'nt'
NAME = 'rg.exe' if WINDOWS else 'rg'
PINNED = '.COM;.EXE;.BAT;.CMD'


class Tree:
    """A scratch folder with a working folder, a `bin` folder and folders for `PATH`."""

    def __init__(self) -> None:
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix='kit-rg-walk-')))
        self.work = self.base / 'work'
        self.bin = self.base / 'home' / 'xdg' / 'cache' / 'opencode' / 'bin'
        for folder in (self.work, self.bin):
            folder.mkdir(parents=True)

    def folder(self, name: str) -> Path:
        path = self.base / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def plant(self, path: Path, mode: int = 0o755) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'stand-in')
        if not WINDOWS:
            os.chmod(path, mode)
        return path

    def copy(self) -> Path:
        return self.plant(self.bin / NAME)

    def walk(self, entries: list[str] | None, pathext: str | None = PINNED, cwd: object = ...):
        env = {} if entries is None else {'PATH': os.pathsep.join(entries)}
        if pathext is not None:
            env['PATHEXT'] = pathext
        here = str(self.work) if cwd is ... else cwd
        return opencode.ripgrep_walk(env, str(self.bin), here)

    def close(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)


def same(a: object, b: object) -> bool:
    return a is not None and b is not None and watch.norm(str(a)) == watch.norm(str(b))


def test_the_homes_copy_runs_when_nothing_comes_before_it():
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        found = tree.walk([str(a)])
        assert same(found.found, tree.bin / NAME), found
        assert same(found.copy, tree.bin / NAME), found
        assert same(found.tried[-1], tree.bin / NAME), found.tried
    finally:
        tree.close()


def test_with_no_copy_and_nothing_on_path_nothing_runs():
    tree = Tree()
    try:
        found = tree.walk([str(tree.folder('a'))])
        assert found.found is None, found
        assert same(found.tried[-1], tree.bin / (NAME + ('.cmd' if WINDOWS else ''))), found.tried
    finally:
        tree.close()


def test_the_first_folder_holding_the_name_wins():
    tree = Tree()
    try:
        tree.copy()
        a, b = tree.folder('a'), tree.folder('b')
        planted = tree.plant(b / NAME)
        found = tree.walk([str(a), str(b)])
        assert same(found.found, planted), found
        assert not any(same(p, tree.bin / NAME) for p in found.tried), found.tried
    finally:
        tree.close()


def test_the_tried_paths_follow_the_search_order_each_once():
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        found = tree.walk([str(a)], pathext='.COM;.EXE')
        if WINDOWS:
            names = ['rg.exe', 'rg.exe.COM', 'rg.exe.EXE']
            want = [tree.work / n for n in names] + [a / n for n in names] + [tree.bin / 'rg.exe']
        else:
            want = [a / 'rg', tree.bin / 'rg']
        assert [watch.norm(p) for p in found.tried] == [watch.norm(p) for p in want], found.tried
    finally:
        tree.close()


def test_a_quoted_relative_and_dotted_entry_resolve_as_which_resolves_them():
    tree = Tree()
    try:
        tree.copy()
        quoted = tree.folder('quoted dir')
        planted = tree.plant(quoted / NAME)
        assert same(tree.walk([f'"{quoted}"']).found, planted)
        sub = tree.work / 'sub'
        planted = tree.plant(sub / NAME)
        assert same(tree.walk(['sub']).found, planted)
        assert same(tree.walk([os.path.join('sub', 'x', '..')]).found, planted)
        dotted = tree.folder('c')
        planted = tree.plant(dotted / NAME)
        assert same(tree.walk([str(dotted / 'y' / '..')]).found, planted)
    finally:
        tree.close()


def test_an_empty_or_quoted_empty_entry_is_the_current_folder_on_every_platform():
    tree = Tree()
    try:
        tree.copy()
        planted = tree.plant(tree.work / NAME)
        for entries in (['', str(tree.folder('a'))], ['""']):
            assert same(tree.walk(entries).found, planted), entries
        other = tree.folder('top')
        planted_top = tree.plant(other / NAME)
        assert same(tree.walk(['', str(tree.folder('a'))], cwd=str(other)).found, planted_top)
        # A `PATH` that is one empty entry is an empty `PATH`: the `bin` folder alone, and on
        # Windows the current folder before it.
        found = tree.walk([''], cwd=str(other)).found
        assert same(found, planted_top if WINDOWS else tree.bin / NAME), found
    finally:
        tree.close()


def test_on_windows_the_current_folder_comes_first():
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        tree.plant(a / NAME)
        planted = tree.plant(tree.work / NAME)
        found = tree.walk([str(a)])
        if WINDOWS:
            assert same(found.found, planted), found
        else:
            assert same(found.found, a / NAME), found
            assert not any(same(p, planted) for p in found.tried), found.tried
    finally:
        tree.close()


def test_an_absent_or_empty_path_gives_the_bin_folder_alone():
    tree = Tree()
    try:
        tree.copy()
        for entries in (None, []):
            found = tree.walk(entries)
            assert same(found.found, tree.bin / NAME), (entries, found)
            outside = [p for p in found.tried if not same(Path(p).parent, tree.bin)]
            if WINDOWS:
                assert all(same(Path(p).parent, tree.work) for p in outside), found.tried
            else:
                assert outside == [], found.tried
    finally:
        tree.close()


def test_a_folder_named_like_the_binary_does_not_count():
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        (a / NAME).mkdir()
        found = tree.walk([str(a)])
        assert same(found.found, tree.bin / NAME), found
        assert any(same(p, a / NAME) for p in found.tried), found.tried
    finally:
        tree.close()


def test_without_a_current_folder_relative_and_empty_entries_are_left_out():
    tree = Tree()
    try:
        tree.copy()
        tree.plant(tree.work / NAME)
        tree.plant(tree.work / 'sub' / NAME)
        a = tree.folder('a')
        found = tree.walk(['', 'sub', '""', str(a)], cwd=None)
        assert same(found.found, tree.bin / NAME), found
        assert all(Path(p).is_absolute() for p in found.tried), found.tried
        assert not any(same(Path(p).parent, tree.work) for p in found.tried), found.tried
        planted = tree.plant(a / NAME)
        assert same(tree.walk([str(a)], cwd=None).found, planted)
    finally:
        tree.close()


def test_windows_counts_a_name_only_under_a_pathext_item():
    if not WINDOWS:
        print('skip: PATHEXT is read on Windows only')
        return
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        tree.plant(a / 'rg.exe')
        found = tree.walk([str(a)], pathext='.CMD')
        assert same(found.found, tree.bin / 'rg.exe'), found
        assert any(same(p, tree.bin / 'rg.exe.cmd') for p in found.tried), found.tried
        planted = tree.plant(a / 'rg.exe.CMD')
        assert same(tree.walk([str(a)], pathext='.CMD').found, planted)
        assert same(tree.walk([str(a)], pathext='.CMD;').found, a / 'rg.exe')
        xyz = tree.folder('xyz')
        tree.plant(xyz / 'rg.exe.XYZ')
        assert same(tree.walk([str(xyz)], pathext='.CMD').found, tree.bin / 'rg.exe')
        assert same(tree.walk([str(xyz)], pathext='.XYZ').found, xyz / 'rg.exe.XYZ')
    finally:
        tree.close()


def test_windows_takes_the_default_pathext_when_it_is_absent_or_empty():
    if not WINDOWS:
        print('skip: PATHEXT is read on Windows only')
        return
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        planted = tree.plant(a / 'rg.exe.bat')
        for pathext in (None, ''):
            assert same(tree.walk([str(a)], pathext=pathext).found, planted), pathext
        assert same(tree.walk([str(a)], pathext='.CMD').found, tree.bin / 'rg.exe')
    finally:
        tree.close()


def test_windows_matches_the_path_key_without_regard_to_case():
    if not WINDOWS:
        print('skip: Windows matches names without regard to case')
        return
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        planted = tree.plant(a / 'rg.exe')
        env = {'Path': str(a), 'PathExt': PINNED}
        found = opencode.ripgrep_walk(env, str(tree.bin), str(tree.work))
        assert same(found.found, planted), found
    finally:
        tree.close()


def test_windows_joins_a_bare_drive_entry_at_its_root():
    if not WINDOWS:
        print('skip: drive letters are Windows paths')
        return
    tree = Tree()
    try:
        drive = os.path.splitdrive(str(tree.work))[0]
        for entry in (drive, f'"{drive}"'):
            found = tree.walk([entry])
            assert any(same(p, drive + '\\rg.exe') for p in found.tried), found.tried
            on_drive = drive + 'rg.exe'
            assert not any(p == on_drive for p in found.tried), found.tried
    finally:
        tree.close()


def test_posix_counts_a_file_by_isexes_mode_rule():
    if WINDOWS:
        print('skip: the mode rule is read off Windows only')
        return
    tree = Tree()
    try:
        tree.copy()
        a = tree.folder('a')
        planted = tree.plant(a / 'rg', 0o644)
        assert same(tree.walk([str(a)]).found, tree.bin / 'rg')
        os.chmod(planted, 0o001)
        assert same(tree.walk([str(a)]).found, planted), oct(planted.stat().st_mode)
        os.chmod(planted, 0o100)
        assert same(tree.walk([str(a)]).found, planted)
        os.chmod(planted, 0o700)
        assert same(tree.walk([str(a)]).found, planted)
    finally:
        tree.close()


if __name__ == '__main__':
    run_module(globals(), 'the ripgrep walk')

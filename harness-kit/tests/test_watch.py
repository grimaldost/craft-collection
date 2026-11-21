#!/usr/bin/env python3
"""Checks of the home hashes (`watch.py`) and of the render's record.

Contract under test:
- each driver names its watched folders and files and the names it excludes:
  opencode every file under `conf/` and `kit-shell/`, `home.json` and a daily
  home's `gitconfig`; Claude
  Code `claude-config/settings.json`, every file under `kit-shell/` and
  `home.json`; neither excludes a name;
- `hash_files` maps each watched file, by its path relative to the home with
  forward slashes, to the SHA-256 of its bytes, sorted; files elsewhere in the
  home (its `xdg/` and `home/` folders, Claude Code's other files under
  `claude-config/`) are not watched; with `rendered=True` it leaves `home.json`
  out;
- `read_files` adds each file's size and modification time in nanoseconds;
- `differences` names each path added, removed or changed;
- an excluded name leaves the hash set wherever it stands;
- `kit home render` writes `rendered_sha256` into `home.json`: each file it
  rendered, by relative path, mapped to its SHA-256, which equals the watched
  set less `home.json`.

Stdlib-runnable: `python test_watch.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import harnesses, watch
from kit_fixtures import SRC, run_module

ENDPOINT = 'http://127.0.0.1:43210'


def _render(name: str, folder: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            '-m',
            'harness_kit',
            *('home', 'render', '--harness', name),
            *('--dir', str(folder), '--endpoint', ENDPOINT),
        ],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    return json.loads(proc.stdout)


def _files(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_each_driver_names_its_watched_files():
    oc = harnesses.get('opencode')
    assert oc.watched_folders == ('conf', 'kit-shell'), oc.watched_folders
    assert oc.watched_files == ('home.json', 'gitconfig'), oc.watched_files
    assert oc.excluded_names == (), oc.excluded_names
    cc = harnesses.get('claude-code')
    assert cc.watched_folders == ('kit-shell',), cc.watched_folders
    assert cc.watched_files == ('claude-config/settings.json', 'home.json'), cc.watched_files
    assert cc.excluded_names == (), cc.excluded_names


def test_opencode_hashes_cover_conf_kit_shell_and_home_json():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'h'
        _render('opencode', folder)
        (folder / 'xdg' / 'data').mkdir(parents=True)
        (folder / 'xdg' / 'data' / 'o.db').write_bytes(b'db')
        (folder / 'home' / 'Local' / 'cache.txt').write_bytes(b'cache')
        (folder / 'conf' / 'extra.json').write_bytes(b'{}')
        hashes = watch.hash_files(folder, harnesses.get('opencode'))
        want = [
            f for f in _files(folder) if f.startswith(('conf/', 'kit-shell/')) or f == 'home.json'
        ]
        assert list(hashes) == sorted(want), list(hashes)
        assert 'conf/extra.json' in hashes and 'conf/opencode.jsonc' in hashes
        for rel, digest in hashes.items():
            assert digest == _sha(folder / rel), rel


def test_claude_code_hashes_leave_its_other_config_files_out():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'h'
        _render('claude-code', folder)
        (folder / 'claude-config' / '.claude.json').write_bytes(b'{}')
        (folder / 'claude-config' / 'projects').mkdir()
        (folder / 'claude-config' / 'projects' / 'p.jsonl').write_bytes(b'x')
        hashes = watch.hash_files(folder, harnesses.get('claude-code'))
        kit_shell = [f for f in _files(folder) if f.startswith('kit-shell/')]
        want = sorted([*kit_shell, 'claude-config/settings.json', 'home.json'])
        assert list(hashes) == want, list(hashes)


def test_rendered_hashes_leave_home_json_out():
    with tempfile.TemporaryDirectory() as td:
        for name in ('opencode', 'claude-code'):
            folder = Path(td) / name
            _render(name, folder)
            driver = harnesses.get(name)
            whole = watch.hash_files(folder, driver)
            rendered = watch.hash_files(folder, driver, rendered=True)
            assert 'home.json' in whole and 'home.json' not in rendered, name
            assert rendered == {k: v for k, v in whole.items() if k != 'home.json'}, name


def test_render_records_the_rendered_files():
    with tempfile.TemporaryDirectory() as td:
        for name in ('opencode', 'claude-code'):
            folder = Path(td) / name
            home = _render(name, folder)
            record = home['rendered_sha256']
            assert record == watch.hash_files(folder, harnesses.get(name), rendered=True), name
            assert list(record) == sorted(record), name
            on_disk = json.loads((folder / 'home.json').read_text(encoding='utf-8'))
            assert on_disk['rendered_sha256'] == record, name
            assert all('\\' not in rel for rel in record), record


def test_read_files_adds_size_and_modification_time():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td) / 'h'
        _render('opencode', folder)
        driver = harnesses.get('opencode')
        read = watch.read_files(folder, driver)
        assert list(read) == list(watch.hash_files(folder, driver)), list(read)
        for rel, entry in read.items():
            st = os.stat(folder / rel)
            assert entry == {
                'sha256': _sha(folder / rel),
                'size': st.st_size,
                'mtime_ns': st.st_mtime_ns,
            }, (rel, entry)


def test_differences_name_added_removed_and_changed_paths():
    before = {'a': '1', 'b': '2', 'c': '3'}
    after = {'a': '1', 'b': '9', 'd': '4'}
    assert watch.differences(before, after) == ['b', 'c', 'd']
    assert watch.differences(before, dict(before)) == []


class _Excluding:
    watched_folders = ('conf',)
    watched_files = ('home.json',)
    excluded_names = ('cli.json',)


def test_an_excluded_name_leaves_the_set_wherever_it_stands():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / 'conf' / 'sub').mkdir(parents=True)
        for rel in ('conf/cli.json', 'conf/sub/cli.json', 'conf/keep.json', 'home.json'):
            (folder / rel).write_bytes(rel.encode('ascii'))
        hashes = watch.hash_files(folder, _Excluding())
        assert list(hashes) == ['conf/keep.json', 'home.json'], list(hashes)


def test_an_absent_watched_file_is_left_out():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / 'kit-shell').mkdir()
        (folder / 'kit-shell' / 'x.js').write_bytes(b'x')
        hashes = watch.hash_files(folder, harnesses.get('claude-code'))
        assert list(hashes) == ['kit-shell/x.js'], list(hashes)


if __name__ == '__main__':
    run_module(globals(), 'home hashes and the render record')

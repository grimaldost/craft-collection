"""Home hashes: the files a rendered home's harness reads its guard from, hashed and read again.

A driver names its watched folders and files and the names it excludes (the
drivers are the only place that knows a harness's files); this module hashes
what the driver names and holds no harness's file list. A watched file is
named by its path relative to the home, with forward slashes; every file
under a watched folder is watched, and a path any of whose parts is an
excluded name is not.

`kit run` writes the hashes to `runs/<id>/home-hashes.json` after the mint and
before the canary, and reads them again, with each file's size and
modification time, right before the session starts. `kit home render` records
the files it rendered (the watched set less `home.json`) in `home.json` as
`rendered_sha256`.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path

HOME_JSON = 'home.json'
HOME_HASHES = 'home-hashes.json'
RENDERED_KEY = 'rendered_sha256'
RUN_OPEN = 'run-open.json'
_CHUNK = 1024 * 1024


def _excluded(relative: str, excluded: tuple[str, ...]) -> bool:
    return any(part in excluded for part in relative.split('/'))


def watched_paths(home_dir: Path | str, driver, *, rendered: bool = False) -> list[str]:
    """The driver's watched files present in the home, relative with forward slashes, sorted.

    With `rendered`, `home.json` is left out: the files a render writes.
    """
    folder = Path(home_dir)
    excluded = tuple(driver.excluded_names)
    found: set[str] = set()
    for name in driver.watched_folders:
        top = folder / name
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames.sort()
            for filename in filenames:
                found.add(Path(dirpath, filename).relative_to(folder).as_posix())
    for name in driver.watched_files:
        if (folder / name).is_file():
            found.add(Path(name).as_posix())
    if rendered:
        found.discard(HOME_JSON)
    return sorted(rel for rel in found if not _excluded(rel, excluded))


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(_CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def hash_files(home_dir: Path | str, driver, *, rendered: bool = False) -> dict[str, str]:
    """Each watched file mapped to the SHA-256 of its bytes, sorted by path."""
    folder = Path(home_dir)
    return {
        rel: file_sha256(folder / rel) for rel in watched_paths(folder, driver, rendered=rendered)
    }


def read_files(home_dir: Path | str, driver) -> dict[str, dict]:
    """Each watched file mapped to its `sha256`, `size` and `mtime_ns`, sorted by path."""
    folder = Path(home_dir)
    out: dict[str, dict] = {}
    for rel in watched_paths(folder, driver):
        st = os.stat(folder / rel)
        out[rel] = {
            'sha256': file_sha256(folder / rel),
            'size': st.st_size,
            'mtime_ns': st.st_mtime_ns,
        }
    return out


def differences(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """The paths added, removed or changed between two hash maps, sorted."""
    names = set(before) | set(after)
    return sorted(n for n in names if before.get(n) != after.get(n))

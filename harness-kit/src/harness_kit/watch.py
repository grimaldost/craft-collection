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

The check during a run reads a `RunWatch` every 2 seconds: the home's watched
files, files named one by one, the files of whole folders (less their
`__pycache__` folders), the names in folders, the `.pth` files of folders and
the presence of paths, each by name, size and modification time in
nanoseconds, and paths read by kind, size, modification time and mode. A name
added or removed, or a size, time, kind or mode that differs, is a change, even
when the bytes hash the same. The baseline is the second read of the home's
watched files, the entries read for `seed` before the check started, and a
fresh read of the rest.

The judge's import surface is read from the judge's own interpreter
(`read_interpreter`, its `cli_argv[0]` run with `-I`): its `sys.path`,
`sys.prefix`, `sys.base_prefix`, site-packages folders and standard library
folders, and the files of the modules its startup loads outside the standard
library (a `.pth` file can import one).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

HOME_JSON = 'home.json'
HOME_HASHES = 'home-hashes.json'
RENDERED_KEY = 'rendered_sha256'
RUN_OPEN = 'run-open.json'
CONFIG_CHANGED = 'config-changed.json'
PYCACHE = '__pycache__'
STARTUP_NAMES = ('sitecustomize.py', 'sitecustomize', 'usercustomize.py', 'usercustomize')
INTERPRETER_TIMEOUT_S = 30
_CHUNK = 1024 * 1024
WINDOWS = os.name == 'nt'
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
# Run by the judge's interpreter with -I: what its startup puts on sys.path and loads.
_PROBE = r"""
import json, os, site, sys, sysconfig
paths = sysconfig.get_paths()
std = [paths['stdlib'], paths.get('platstdlib') or paths['stdlib']]
if os.name == 'nt':
    std.append(os.path.join(os.path.dirname(paths['stdlib']), 'DLLs'))
std = [os.path.normcase(os.path.abspath(p)) for p in std]
def outside(f):
    f = os.path.normcase(os.path.abspath(f))
    return not any(f == s or f.startswith(s.rstrip(os.sep) + os.sep) for s in std)
files = sorted({os.path.abspath(m.__file__) for m in list(sys.modules.values())
                if isinstance(getattr(m, '__file__', None), str)})
sites = site.getsitepackages() if hasattr(site, 'getsitepackages') else []
print(json.dumps({'path': [p for p in sys.path if p], 'prefix': sys.prefix,
                  'base_prefix': sys.base_prefix, 'site_packages': sites, 'stdlib': std,
                  'files': [f for f in files if outside(f)]}))
"""


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


# ---- the check during a run


def norm(path: Path | str) -> str:
    """A path's absolute form, case-folded where the system folds case, for comparison."""
    return os.path.normcase(os.path.abspath(str(path)))


def within(path: Path | str, base: Path | str) -> bool:
    """True when `path` is `base` or lies below it, compared as `norm` gives them."""
    p, b = norm(path), norm(base)
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


def _stat(path: Path | str) -> tuple | None:
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return ('error', type(exc).__name__)
    return (st.st_size, st.st_mtime_ns)


def _kind(path: Path | str) -> tuple | None:
    """A path's kind, size, modification time and mode, links followed; None when absent."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        return ('error', type(exc).__name__)
    return (stat.S_IFMT(st.st_mode), st.st_size, st.st_mtime_ns, stat.S_IMODE(st.st_mode))


def read_kinds(paths: Iterable[str]) -> dict:
    """The entries `snapshot` gives `paths` read for presence and for kind, read now."""
    seen: dict[tuple[str, str], object] = {}
    for path in paths:
        seen['present', path] = os.path.lexists(path)
        seen['kind', path] = _kind(path)
    return seen


def _files_under(folder: Path | str) -> list[str]:
    """Every file under `folder`, its `__pycache__` folders left out; [] when it is absent."""
    found = []
    for dirpath, dirnames, filenames in os.walk(str(folder)):
        dirnames[:] = sorted(d for d in dirnames if d != PYCACHE)
        found.extend(os.path.join(dirpath, name) for name in filenames)
    return found


def _names(folder: Path | str) -> list[str]:
    try:
        return [n for n in os.listdir(folder) if n != PYCACHE]
    except OSError:
        return []


@dataclass
class RunWatch:
    """What the check during a run reads, besides the home's watched files of its driver.

    `kinds` are paths read by kind, size, modification time and mode, links followed; `seed`
    holds entries read before the check starts (`read_kinds`), which stand in for the first
    read of those paths.
    """

    home: Path
    driver: object
    files: list[str] = field(default_factory=list)
    trees: list[str] = field(default_factory=list)
    name_sets: list[str] = field(default_factory=list)
    pth_folders: list[str] = field(default_factory=list)
    presence: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    seed: dict = field(default_factory=dict)


def snapshot(plan: RunWatch, home_files: Mapping[str, Mapping] | None = None) -> dict:
    """One read of the plan: (kind, absolute path) mapped to what was seen there.

    `home_files`, the second read of the home hashes (`read_files`), stands in for a fresh
    read of the home's watched files, and with it the plan's `seed` stands in for a fresh read
    of the paths it holds: together they are the baseline of the check during the run.
    """
    seen: dict[tuple[str, str], object] = {}
    if home_files is None:
        for rel in watched_paths(plan.home, plan.driver):
            seen['file', str(plan.home / rel)] = _stat(plan.home / rel)
    else:
        for rel, value in home_files.items():
            seen['file', str(plan.home / rel)] = (value['size'], value['mtime_ns'])
    for path in plan.files:
        seen['file', path] = _stat(path)
    for folder in plan.trees:
        for path in _files_under(folder):
            seen['file', path] = _stat(path)
    for folder in plan.name_sets:
        for name in _names(folder):
            seen['name', os.path.join(folder, name)] = True
    for folder in plan.pth_folders:
        for name in _names(folder):
            if name.lower().endswith('.pth'):
                seen['file', os.path.join(folder, name)] = _stat(os.path.join(folder, name))
    for path in plan.presence:
        seen['present', path] = os.path.lexists(path)
    for path in plan.kinds:
        seen['kind', path] = _kind(path)
    if home_files is not None:
        seen.update(plan.seed)
    return seen


def changes(before: Mapping, after: Mapping) -> list[str]:
    """The paths whose entry was added, removed or differs between two reads, sorted."""
    keys = set(before) | set(after)
    return sorted(
        {path for kind, path in keys if before.get((kind, path)) != after.get((kind, path))}
    )


def label(path: str, home: Path) -> str:
    """A changed path as `config_changed` names it: relative to the home, absolute outside it."""
    if within(path, home):
        return Path(os.path.relpath(path, home)).as_posix()
    return path


# ---- the judge's interpreter


class SurfaceError(OSError):
    """The judge's interpreter could not be read; the message is ASCII."""


def read_interpreter(executable: str, env: Mapping[str, str] | None = None) -> dict:
    """What the judge's interpreter puts on `sys.path` and loads when it starts with `-I`."""
    extra = {'creationflags': NO_WINDOW} if WINDOWS else {}
    try:
        proc = subprocess.run(  # noqa: S603 - the judge's interpreter, a fixed program
            [executable, '-I', '-c', _PROBE],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=dict(env) if env is not None else None,
            timeout=INTERPRETER_TIMEOUT_S,
            check=False,
            **extra,
        )
        found = json.loads(proc.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
        raise SurfaceError(f'the judge interpreter did not answer: {type(exc).__name__}') from None
    keys = ('path', 'prefix', 'base_prefix', 'site_packages', 'stdlib', 'files')
    if not isinstance(found, dict) or any(k not in found for k in keys):
        raise SurfaceError('the judge interpreter gave no reading of its path')
    return found


def under_any(path: str, folders: Iterable[str]) -> bool:
    return any(within(path, folder) for folder in folders)

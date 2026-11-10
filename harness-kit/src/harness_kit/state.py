"""The state root, run identity and journal.

The state root is the kit's own folder, outside every harness's configuration:
`KIT_STATE_ROOT` when set, else `%LOCALAPPDATA%/harness-kit` on Windows, else
`$XDG_STATE_HOME/harness-kit`, else `~/.local/state/harness-kit`. A root inside a
harness's configuration is refused. Paths are resolved first (`realpath`), then
case-folded on Windows, so a link is judged by its target.

A run is minted as `runs/<id>/run.json`; its id reaches children through
`KIT_RUN_ID`. An event is launched only when that id has the run-id shape and
its `run.json` exists, so a forged id is not launched.

Every judgement appends one line to a journal: `runs/<id>/journal.ndjson` when
launched, else `not-launched/<16 hex of sha256(session id)>/journal.ndjson`, or
`not-launched/invalid/` for an invalid event. A line names the act's kind and
payload hash and the verdict, never the command text or a path. Each append
holds one exclusive lock on `journal.ndjson.lock` beside the journal (one byte
at offset 0 through `msvcrt.locking` on Windows, `fcntl.flock` on POSIX; nothing
is written to that file), taken with retries for at most one second.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_ROOT_ENV = 'KIT_STATE_ROOT'
RUN_ID_ENV = 'KIT_RUN_ID'
APP_DIR = 'harness-kit'

RUN_ID_RE = re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}')

HARNESS_DIRS = ('.claude', '.codex', '.opencode', '.gemini', '.pi', '.agents', '.goose')
HARNESS_CONFIG_VARS = (
    'CLAUDE_CONFIG_DIR',
    'OPENCODE_CONFIG_DIR',
    'XDG_CONFIG_HOME',
    'CODEX_HOME',
    'PI_CODING_AGENT_DIR',
    'GOOSE_PATH_ROOT',
)

JOURNAL = 'journal.ndjson'
JOURNAL_LOCK = 'journal.ndjson.lock'
LOCK_TIMEOUT = 1.0
REPLACE_DEADLINE = 2.0
_RETRY_SLEEP = 0.01

WINDOWS = os.name == 'nt'


class StateRootError(ValueError):
    """The state root lies inside a harness's configuration; the message is ASCII."""


class JournalError(OSError):
    """A journal line could not be written; the message is ASCII."""


def _set(value: str | None) -> bool:
    return bool(value)


def configured_root(env: dict, windows: bool = WINDOWS) -> str:
    """The state root the environment names, before resolution."""
    if _set(env.get(STATE_ROOT_ENV)):
        return env[STATE_ROOT_ENV]
    if windows and _set(env.get('LOCALAPPDATA')):
        return os.path.join(env['LOCALAPPDATA'], APP_DIR)
    if _set(env.get('XDG_STATE_HOME')):
        return os.path.join(env['XDG_STATE_HOME'], APP_DIR)
    home = env.get('HOME') or os.path.expanduser('~')
    return os.path.join(home, '.local', 'state', APP_DIR)


def _parts(path: str, windows: bool) -> list[str]:
    text = path.replace('\\', '/')
    if windows:
        text = text.casefold()
    return [p for p in text.split('/') if p]


def _under(parts: list[str], base: list[str]) -> bool:
    return len(base) > 0 and parts[: len(base)] == base


def refusal(resolved: str, env: dict, windows: bool = WINDOWS, resolve=None) -> str | None:
    """Why a resolved root lies inside a harness's configuration, or None when it does not.

    `resolve` resolves each configuration variable's value the way the root was
    resolved; without it the values are compared as given.
    """
    parts = _parts(resolved, windows)
    names = [n.casefold() for n in HARNESS_DIRS] if windows else list(HARNESS_DIRS)
    for part in parts:
        if part in names:
            return f'a path component is {part}'
    for i in range(len(parts) - 1):
        if parts[i] == '.config' and parts[i + 1] == 'opencode':
            return 'the path is under .config/opencode'
    for var in HARNESS_CONFIG_VARS:
        value = env.get(var)
        if not _set(value):
            continue
        base = resolve(value) if resolve is not None else value
        if _under(parts, _parts(base, windows)):
            return f'the path is under {var}'
    return None


def state_root(env: dict | None = None) -> Path:
    """The resolved state root; raise StateRootError when it is inside a harness's config."""
    env = os.environ if env is None else env
    resolved = os.path.realpath(configured_root(env))
    reason = refusal(resolved, env, resolve=os.path.realpath)
    if reason is not None:
        raise StateRootError(f'state root {ascii_path(resolved)} refused: {reason}')
    return Path(resolved)


def ascii_path(path: Path | str) -> str:
    """A path as ASCII text, non-ASCII characters escaped, separators kept as they are."""
    return str(path).encode('ascii', 'backslashreplace').decode('ascii')


def _utc(now: datetime, micro: bool = False) -> str:
    return now.strftime('%Y-%m-%dT%H:%M:%S.%fZ' if micro else '%Y-%m-%dT%H:%M:%SZ')


def _sharing_error(exc: OSError) -> bool:
    return isinstance(exc, PermissionError) or getattr(exc, 'winerror', None) in (5, 32, 33)


def write_json_atomic(
    path: Path,
    obj: object,
    *,
    sharing_retry: bool = WINDOWS,
    deadline: float = REPLACE_DEADLINE,
) -> None:
    """Write `obj` as ASCII JSON by a temporary file in the same folder and `os.replace`.

    A reader never sees a partial file. On Windows a reader holding the target
    open makes the replace fail with a sharing error; it is retried until
    `deadline` seconds have passed, then raised.
    """
    path = Path(path)
    data = (json.dumps(obj, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        end = time.monotonic() + deadline
        while True:
            try:
                os.replace(tmp, path)
                return
            except OSError as exc:
                if not (sharing_retry and _sharing_error(exc)) or time.monotonic() >= end:
                    raise
                time.sleep(_RETRY_SLEEP)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def mint_run(root: Path, harness: str) -> tuple[str, Path]:
    """Create `runs/<id>/run.json` with outcome `minted`; return the id and the run folder."""
    runs = Path(root) / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    while True:
        now = datetime.now(timezone.utc)
        run_id = f'{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(6)}'
        run_dir = runs / run_id
        try:
            run_dir.mkdir()
        except FileExistsError:
            continue
        break
    record = {'run_id': run_id, 'harness': harness, 'started_utc': _utc(now), 'outcome': 'minted'}
    write_json_atomic(run_dir / 'run.json', record)
    return run_id, run_dir


def is_launched(root: Path, run_id: str | None) -> bool:
    """True only when `run_id` has the run-id shape and its run.json exists."""
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        return False
    return (Path(root) / 'runs' / run_id / 'run.json').is_file()


def session_folder(session_id: str | None) -> str:
    """The not-launched folder name for a session: 16 hex of sha256 of its id."""
    if session_id is None:
        return 'no-session'
    return hashlib.sha256(session_id.encode('utf-8', 'surrogatepass')).hexdigest()[:16]


def journal_path(root: Path, run_id: str | None, event: dict | None) -> Path:
    """Where a judgement's line goes: its run when launched, else `not-launched/`."""
    root = Path(root)
    if run_id is not None:
        return root / 'runs' / run_id / JOURNAL
    if event is None:
        return root / 'not-launched' / 'invalid' / JOURNAL
    return root / 'not-launched' / session_folder(event['session']['id']) / JOURNAL


def journal_record(
    verdict: dict, event: dict | None, run_id: str | None, launched: bool, now: datetime
) -> dict:
    """One journal line: identity, act kind and hash, verdict; never a command or a path."""
    return {
        'ts_utc': _utc(now, micro=True),
        'run_id': run_id,
        'launched': launched,
        'session_id': event['session']['id'] if event else None,
        'harness': event['harness']['name'] if event else None,
        'act_kind': event['act']['kind'] if event else None,
        'payload_sha256': event['act']['payload_sha256'] if event else None,
        'verdict': verdict['verdict'],
        'effect': verdict['effect'],
        'rule': verdict['rule'],
    }


def _try_lock(fd: int) -> bool:
    if WINDOWS:
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
            return False
        raise
    return True


def _unlock(fd: int) -> None:
    if WINDOWS:
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def append_journal(path: Path, record: dict, timeout: float = LOCK_TIMEOUT) -> None:
    """Append one ASCII JSON line while holding the lock beside the journal.

    Raise JournalError when the folder, the lock or the write fails, or when the
    lock is not obtained within `timeout` seconds.
    """
    path = Path(path)
    line = (json.dumps(record, ensure_ascii=True) + '\n').encode('ascii')
    binary = getattr(os, 'O_BINARY', 0)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(path.with_name(JOURNAL_LOCK), os.O_RDWR | os.O_CREAT | binary, 0o666)
    except OSError as exc:
        raise JournalError(f'journal folder or lock not opened: {type(exc).__name__}') from None
    try:
        end = time.monotonic() + timeout
        while not _try_lock(lock_fd):
            if time.monotonic() >= end:
                raise JournalError(f'journal lock not obtained within {timeout:g} s')
            time.sleep(_RETRY_SLEEP)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | binary, 0o666)
            try:
                view = memoryview(line)
                while view:
                    view = view[os.write(fd, view) :]
            finally:
                os.close(fd)
        except OSError as exc:
            raise JournalError(f'journal not written: {type(exc).__name__}') from None
        finally:
            _unlock(lock_fd)
    finally:
        os.close(lock_fd)

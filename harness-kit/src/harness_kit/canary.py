"""The presence canary: `kit run` proves the guard is loaded before the session starts.

After preflight and the mint, and before the session, the launcher runs the
harness once more, headless, against a private stub on its own port. The
stub scripts two shell calls and a final text: `echo probe > deny-<nonce>.marker`
and then `echo probe > allow-<nonce>.marker`. The harness runs in
`runs/<id>/canary/work/`, a folder of the kit's own that holds only a byte for
byte copy of the project-config paths found in the session's working folder,
with a byte for byte copy of the home pointed at the private stub, under the
session's environment builder with `KIT_CANARY_NONCE`, `PWD`, `TEMP` and `TMP`
added. With that nonce the CLI denies the first call by `canary.deny`, writing
`runs/<id>/canary/refused-<nonce>.marker`, and allows the second by
`canary.allow`.

The proof is three files, in this order: the refused marker exists, the deny
marker does not, the allow marker does. The harness's exit code is never read.
The harness gets at most 60 seconds, its stdin closed and its output in files
of the canary folder. On Windows it joins a new Job Object as soon as it has
started; past the deadline the job is terminated (an absolute System32
`taskkill /T /F`, not waited for, if a Job Object call failed) and the canary
fails with reason `timeout`; and the job is terminated when the canary ends
for any reason, so nothing of it outlives the canary. On POSIX the harness
starts in a new session and its process group is killed the same way.

The private stub is not the session's model endpoint: the requests it records
are the canary's own.
"""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from harness_kit import harnesses, state, stubmodel

TIMEOUT_S = 60
KILL_WAIT_S = 10
WINDOWS = os.name == 'nt'
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
PROMPT = 'Run each tool call exactly as given, then stop.'
CANARY_JSON = 'canary.json'
REASON_TIMEOUT = 'timeout'


def _ascii(text: object) -> str:
    return str(text).encode('ascii', 'backslashreplace').decode('ascii').replace('\n', ' ')


def _copy_project(source: Path, dest: Path, entries: list[str]) -> None:
    """Copy each project-config path of the session's folder to the same place under `dest`."""
    for entry in entries:
        src, dst = source / entry, dest / entry
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, dst)
        else:
            shutil.copyfile(src, dst)


def _pin_own_environment() -> None:
    """On Windows, give kit's own process the system's values of the pinned names.

    The private stub runs in kit's process, and a socket there fails when the
    `SYSTEMROOT` kit received is not the system's (WSAEPROVIDERFAILEDINIT).
    """
    if not WINDOWS:
        return
    from harness_kit.launcher import WINDOWS_PINNED, windows_pins

    pinned = windows_pins()
    for name in WINDOWS_PINNED:
        for other in [k for k in os.environ if k.upper() == name]:
            del os.environ[other]
        os.environ[name] = pinned[name]


class _QuietStub(stubmodel.Stub):
    """The stub in kit's own process: a connection the harness drops prints nothing on kit's stderr."""

    def handle_error(self, request, client_address) -> None:
        pass


def make_stub(log: Path, script: list[dict]) -> stubmodel.Stub:
    """The canary's private stub, bound to a free port on 127.0.0.1."""
    return _QuietStub(log, script)


def _requests(log: Path) -> int:
    try:
        text = log.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return 0
    return len([line for line in text.splitlines() if line.strip()])


# ---- the process tree


def _new_job(proc: subprocess.Popen):
    """Put the started harness in a new Job Object; None when any call fails."""
    try:
        import ctypes

        k32 = ctypes.WinDLL('kernel32')
        k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        k32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        k32.TerminateJobObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        k32.CloseHandle.argtypes = (ctypes.c_void_p,)
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        if not k32.AssignProcessToJobObject(job, int(proc._handle)):  # type: ignore[attr-defined]
            k32.CloseHandle(job)
            return None
        return k32, job
    except (OSError, AttributeError, ValueError):
        return None


def _taskkill(proc: subprocess.Popen, env: dict) -> None:
    """The fallback kill: absolute System32 taskkill, never waited for, its exit code unread."""
    system_root = next((v for k, v in env.items() if k.upper() == 'SYSTEMROOT' and v), None)
    killer = os.path.join(system_root or 'C:\\Windows', 'System32', 'taskkill.exe')
    quiet = {
        'stdin': subprocess.DEVNULL,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
    }
    try:
        subprocess.Popen(  # noqa: S603 - absolute path, no shell
            [killer, '/PID', str(proc.pid), '/T', '/F'], creationflags=NO_WINDOW, **quiet
        )
    except OSError:
        pass


def _kill_tree(proc: subprocess.Popen, job, env: dict) -> None:
    if not WINDOWS:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        return
    if job is not None and job[0].TerminateJobObject(job[1], 1):
        return
    _taskkill(proc, env)


def _end_tree(proc: subprocess.Popen, job) -> None:
    """Whatever ended the canary, end what is left of its tree."""
    if not WINDOWS:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        return
    if job is not None:
        job[0].TerminateJobObject(job[1], 1)
        job[0].CloseHandle(job[1])


def run_harness(argv: list[str], env: dict, work: Path, folder: Path, timeout_s: float) -> bool:
    """Run the harness to its end or the deadline; True when the deadline ended it.

    Raise OSError when the harness does not start.
    """
    extra = {} if WINDOWS else {'start_new_session': True}
    with open(folder / 'harness.stdout', 'wb') as out, open(folder / 'harness.stderr', 'wb') as err:
        proc = subprocess.Popen(  # noqa: S603 - argv from the driver, no shell
            argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env, cwd=str(work), **extra
        )
    job = _new_job(proc) if WINDOWS else None
    try:
        try:
            proc.wait(timeout=timeout_s)
            return False
        except subprocess.TimeoutExpired:
            _kill_tree(proc, job, env)
            try:
                proc.wait(timeout=KILL_WAIT_S)
            except subprocess.TimeoutExpired:
                pass
            return True
    finally:
        _end_tree(proc, job)


# ---- the canary


def run_canary(
    driver: harnesses.Driver,
    home: dict,
    binary: list[str],
    *,
    run_dir: Path,
    workdir: Path,
    project_config: list[str],
    make_env: Callable[[dict, Path], dict],
    timeout_s: float = TIMEOUT_S,
) -> dict:
    """Run the canary for one minted run; return the `canary.json` record.

    `make_env(home_copy, work)` is the session's environment builder applied to
    the copied home and the canary's work folder. Nothing here raises: any
    failure is a failed canary with its reason.
    """
    nonce = secrets.token_hex(8)
    folder = Path(run_dir) / state.CANARY_DIR
    work, tmp = folder / 'work', folder / 'tmp'
    deny_name, allow_name = f'deny-{nonce}.marker', f'allow-{nonce}.marker'
    log = folder / 'stub.ndjson'
    reason = None
    try:
        for sub in (folder, work, tmp):
            sub.mkdir(parents=True, exist_ok=True)
        script = [
            driver.canary_step(f'echo probe > {deny_name}'),
            driver.canary_step(f'echo probe > {allow_name}'),
            {'text': 'kit canary done'},
        ]
        _pin_own_environment()
        stub = make_stub(log, script)
    except Exception as exc:  # the canary fails closed on anything
        stub, reason = None, f'the canary folder or its private stub was not set up: {_ascii(exc)}'
    if stub is not None:
        server = threading.Thread(target=stub.serve_forever, daemon=True)
        server.start()
        try:
            reason = _run(
                driver,
                home,
                binary,
                stub,
                nonce,
                folder,
                workdir,
                project_config,
                make_env,
                timeout_s,
            )
        finally:
            stub.shutdown()
            stub.server_close()
    refused = folder / f'refused-{nonce}.marker'  # where the CLI writes it, state.refused_marker
    record = {
        'passed': False,
        'reason': reason,
        'refused_marker': refused.is_file(),
        'deny_marker': os.path.lexists(work / deny_name),
        'allow_marker': os.path.lexists(work / allow_name),
        'stub_requests': _requests(log),
    }
    if reason is None:
        if not record['refused_marker']:
            reason = 'the guard did not refuse the denied call (no refused marker)'
        elif record['deny_marker']:
            reason = 'the denied call ran (deny marker present)'
        elif not record['allow_marker']:
            reason = 'the allowed call did not run (allow marker absent)'
    record.update(passed=reason is None, reason=reason)
    return record


def _run(driver, home, binary, stub, nonce, folder, workdir, project_config, make_env, timeout_s):
    """Copy, build the environment and run the harness; the failure reason, or None."""
    work, tmp = folder / 'work', folder / 'tmp'
    endpoint = f'http://127.0.0.1:{stub.port}'
    try:
        copy = driver.copy_home_for_canary(home, folder / 'home', endpoint)
        _copy_project(Path(workdir), work, list(project_config))
    except Exception as exc:  # a copy that fails, of the home or a project path, fails the canary
        return f'copy failed: {_ascii(exc)}'
    try:
        env = make_env(copy, work)
    except Exception as exc:
        return f'the canary environment was not built: {_ascii(exc)}'
    for name, value in (
        ('TEMP', str(tmp)),
        ('TMP', str(tmp)),
        ('PWD', str(work)),
        (state.CANARY_NONCE_ENV, nonce),
    ):
        harnesses.set_var(env, name, value)
    if not binary:
        return f'the {driver.name} binary was not found'
    try:
        timed_out = run_harness(
            [*binary, *driver.canary_argv(PROMPT)], env, work, folder, timeout_s
        )
    except (OSError, ValueError) as exc:
        return f'the harness did not start: {_ascii(exc)}'
    return REASON_TIMEOUT if timed_out else None

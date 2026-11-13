#!/usr/bin/env python3
"""Hung-guard matrix: a stuck CLI under each real harness, started from each parent shell.

Each cell starts the real harness from one parent shell (Git Bash, PowerShell 7
or Windows PowerShell 5.1) through a rendered home whose `shell_config.json`
points `cli_argv` at a script that first starts a grandchild (which writes a
marker after 6 seconds) and then hangs. A cell passes when:

- the denied call's marker is absent from the work folder;
- the stub request after the tool call carries `kit could not judge:`;
- the gap between the stub's first and second tool requests is under 6 seconds;
- the grandchild's late marker is still absent 8 seconds after the harness ended;
- no process of the cell's tree is alive after that.

The cell's tree is sampled while the harness runs: a process joins it through
a parent already in it, and only when it was created after that parent, since
Windows keeps an exited parent's id in a child's record and ids are reused.
No process created after the clock was read for a sample joins in that sample.
A survivor is ended only while it is still the process that was recorded.

opencode also runs once with System32 off `PATH`. Claude Code is left out of
that case: it starts system tools of its own, so its tree needs System32.

A run writes `kill-matrix-results.json` under the base, one row per cell with
`harness`, `shell` and `passed`, and prints `ok:` only when every row passed.
The largest gap seen is printed with it.

Prints `skip:` unless KIT_CONFORMANCE_BASE, KIT_HARNESS_ARGV_CLAUDE_CODE and
KIT_HARNESS_ARGV_OPENCODE are set (and the platform is Windows); the base must
be an existing folder.

Stdlib-runnable: `python test_kill_matrix.py`. With `--hang LATE_MARKER` this
file is the hanging CLI itself.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

WINDOWS = os.name == 'nt'
SRC = Path(__file__).resolve().parents[1] / 'src'
REQUIRED = ('KIT_CONFORMANCE_BASE', 'KIT_HARNESS_ARGV_CLAUDE_CODE', 'KIT_HARNESS_ARGV_OPENCODE')
HARNESSES = ('claude-code', 'opencode')
SHELLS = ('git-bash', 'pwsh-7', 'powershell-5.1')
NO_SYSTEM32 = 'system32-off-path'
RESULTS = 'kill-matrix-results.json'
REASON = 'kit could not judge:'
GAP_CEILING_S = 6.0
LATE_AFTER_S = 6
LATE_WAIT_S = 8
CELL_TIMEOUT_S = 180
SECRET_NAME = re.compile(r'(^GH_|_KEY$|_TOKEN$|_SECRET$|_PASSWORD$)', re.IGNORECASE)
LATE_CODE = f'import sys, time; time.sleep({LATE_AFTER_S}); open(sys.argv[1], "w").write("late")'
STILL_ACTIVE = 259
QUERY_LIMITED = 0x1000
PROCESS_TERMINATE = 0x0001
TH32CS_SNAPPROCESS = 0x2


# ---- the hanging CLI


def hang(late_marker: str) -> int:
    """Start a grandchild that writes `late_marker` later, holding our stdout, then hang."""
    subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-I', '-c', LATE_CODE, late_marker],
        stdin=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(60)
    return 0


# ---- process tree (Windows)


def _kernel32():
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = (
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_wchar * 260),
        )

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
    k32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    k32.GetSystemTimePreciseAsFileTime.argtypes = (ctypes.POINTER(wintypes.FILETIME),)
    k32.GetSystemTimePreciseAsFileTime.restype = None
    return ctypes, wintypes, k32, Entry


def _parents() -> dict[int, int]:
    """Every live process id mapped to its parent's id."""
    ctypes, _wintypes, k32, entry_type = _kernel32()
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    out: dict[int, int] = {}
    entry = entry_type()
    entry.dwSize = ctypes.sizeof(entry_type)
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        out[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return out


def _live_created(handle) -> int | None:
    """The creation time of the live process behind `handle`; None once it has exited."""
    ctypes, wintypes, k32, _entry = _kernel32()
    times = [wintypes.FILETIME() for _ in range(4)]
    code = wintypes.DWORD()
    if not k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
        return None
    if not k32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
        return None
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def _created(pid: int) -> int | None:
    """The creation time of a live process, so a reused id is not taken for it."""
    _ctypes, _wintypes, k32, _entry = _kernel32()
    handle = k32.OpenProcess(QUERY_LIMITED, False, pid)
    if not handle:
        return None
    try:
        return _live_created(handle)
    finally:
        k32.CloseHandle(handle)


def grow_family(
    root: int,
    parents: dict[int, int],
    created: Callable[[int], int | None],
    seen: dict[int, int],
    *,
    taken: int,
) -> dict[int, int]:
    """The live members of `root`'s tree, as pid -> creation time.

    The tree starts from `root` and from every process of `seen` that is still
    the same process (same creation time). A pid joins only through a parent
    already in the tree, and only when it was created after that parent:
    Windows keeps an exited parent's id in a child's record, so without the
    order an older, unrelated process whose dead parent's id was reused by a
    cell process would join the tree, and everything below it.

    `taken` is the system time read before `parents` was listed. No pid is
    admitted with a creation time later than it: a listed process can exit and
    its id be reused before its creation time is read, and the newer process
    must not join. A child created after the clock was read waits for the next
    sample.
    """
    family: dict[int, int] = {}
    for pid, known in [(root, None), *seen.items()]:
        now = created(pid)
        if now is not None and now <= taken and known in (None, now):
            family[pid] = now
    if root not in family:
        return {}
    grew = True
    while grew:
        grew = False
        for pid, parent in parents.items():
            if pid in family or parent not in family:
                continue
            now = created(pid)
            if now is not None and family[parent] < now <= taken:
                family[pid] = now
                grew = True
    return family


def _system_time() -> int:
    """The system time, in the units and epoch of a process's creation time."""
    ctypes, wintypes, k32, _entry = _kernel32()
    now = wintypes.FILETIME()
    k32.GetSystemTimePreciseAsFileTime(ctypes.byref(now))
    return (now.dwHighDateTime << 32) | now.dwLowDateTime


def collect_tree(root: int, seen: dict[int, int]) -> None:
    """Add every live descendant of `root` (and `root`) to `seen`, as pid -> creation time."""
    taken = _system_time()
    for pid, created in grow_family(root, _parents(), _created, seen, taken=taken).items():
        seen.setdefault(pid, created)


def survivors(seen: dict[int, int]) -> list[int]:
    return [pid for pid, created in seen.items() if _created(pid) == created]


def terminate(members: dict[int, int]) -> None:
    """End the cell's own survivors, each checked on the handle that ends it.

    Only pids `grow_family` admitted reach here, and each is ended only while
    it is still the process seen (same creation time), so a pid reused by an
    unrelated process in between is left alone.
    """
    _ctypes, _wintypes, k32, _entry = _kernel32()
    for pid, created in members.items():
        handle = k32.OpenProcess(PROCESS_TERMINATE | QUERY_LIMITED, False, pid)
        if not handle:
            continue
        try:
            if _live_created(handle) == created:
                k32.TerminateProcess(handle, 1)
        finally:
            k32.CloseHandle(handle)


# ---- parent shells


def _git_bash() -> str | None:
    git = shutil.which('git')
    roots = list(Path(git).parents) if git else []
    roots += [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Git']
    for root in roots:
        candidate = root / 'bin' / 'bash.exe'
        if candidate.is_file():
            return str(candidate)
    return None


def shell_executable(shell: str) -> str | None:
    """The absolute path of one parent shell; None when this machine has no such shell."""
    if shell == 'git-bash':
        return _git_bash()
    if shell == 'pwsh-7':
        return shutil.which('pwsh')
    system = os.environ.get('SYSTEMROOT', 'C:/Windows')
    path = Path(system) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    return str(path) if path.is_file() else None


def _sh_quote(arg: str) -> str:
    return "'" + arg.replace("'", "'\\''") + "'"


def _ps_quote(arg: str) -> str:
    return "'" + arg.replace("'", "''") + "'"


def parent_argv(shell: str, executable: str, argv: list[str]) -> list[str]:
    """The command that starts `argv` from `shell`; the shell stays the harness's parent."""
    if shell == 'git-bash':
        line = ' '.join(_sh_quote(a) for a in argv)
        return [executable, '--noprofile', '--norc', '-c', line]
    line = '& ' + ' '.join(_ps_quote(a) for a in argv) + '; exit $LASTEXITCODE'
    return [executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', line]


def without_system32(path: str) -> str:
    system32 = (Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32').as_posix().lower()
    kept = [
        p for p in path.split(os.pathsep) if not Path(p).as_posix().lower().startswith(system32)
    ]
    return os.pathsep.join(kept)


# ---- one cell


def _kit_env(extra: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env = {k: v for k, v in env.items() if not SECRET_NAME.search(k)}
    # The app that runs this test sets its own variables; none of them belongs in a test session.
    env = {k: v for k, v in env.items() if not re.match(r'(CLAUDE|ANTHROPIC)', k, re.IGNORECASE)}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def _kit(*args: str, env: dict) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, (args, proc.returncode, proc.stderr)
    return proc.stdout


def _start_stub(folder: Path, steps: list, env: dict) -> tuple[subprocess.Popen, int]:
    script = folder / 'script.json'
    script.write_text(json.dumps(steps), encoding='utf-8')
    stub = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            '-m',
            'harness_kit',
            'stub',
            '--log',
            str(folder / 'stub.jsonl'),
            '--script',
            str(script),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding='utf-8',
        env=env,
    )
    return stub, json.loads(stub.stdout.readline())['port']


def _log(folder: Path) -> list[dict]:
    path = folder / 'stub.jsonl'
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def _gap_and_reason(folder: Path) -> tuple[float | None, bool]:
    """The seconds between the stub's first two tool requests, and whether the second has the reason."""
    tools = [r for r in _log(folder) if r.get('decision') == 'scripted']
    if len(tools) < 2:
        return None, False
    gap = round(tools[1]['t'] - tools[0]['t'], 3)
    return gap, REASON in json.dumps(tools[1].get('body'))


def run_cell(harness: str, shell: str, base: Path, *, system32_off: bool = False) -> dict:
    """Run one cell; the row says what was seen, and `passed` is true only when all of it held."""
    from_shell = shell
    label = NO_SYSTEM32 if system32_off else shell
    row = {'harness': harness, 'shell': label, 'passed': False}
    if system32_off:
        row['case'] = NO_SYSTEM32
        row['parent_shell'] = from_shell
    executable = shell_executable(from_shell)
    if executable is None:
        row['error'] = f'no {from_shell} on this machine'
        return row
    sys.path.insert(0, str(SRC))
    from harness_kit import harnesses

    driver = harnesses.get(harness)
    folder = base / f'{harness}-{label}-{uuid.uuid4().hex[:8]}'
    work, tmp, late = folder / 'work', folder / 'tmp', folder / 'late.marker'
    for sub in (work, tmp):
        sub.mkdir(parents=True)
    row['folder'] = str(folder)
    kit = {'KIT_STATE_ROOT': str(folder / 'state')}
    kit_env = _kit_env(kit)
    steps = [driver.canary_step('echo probe > hung.marker'), {'text': 'done'}]
    stub, port = _start_stub(folder, steps, kit_env)
    seen: dict[int, int] = {}
    ended = None
    try:
        rendered = _kit(
            'home',
            'render',
            '--harness',
            harness,
            '--dir',
            str(folder / 'home'),
            '--endpoint',
            f'http://127.0.0.1:{port}',
            env=kit_env,
        )
        home = json.loads(rendered)
        config = Path(home['shell_config'])
        shell_config = json.loads(config.read_text(encoding='utf-8'))
        shell_config['cli_argv'] = [
            sys.executable,
            '-I',
            str(Path(__file__).resolve()),
            '--hang',
            str(late),
        ]
        config.write_text(json.dumps(shell_config, indent=2) + '\n', encoding='utf-8')
        minted = json.loads(_kit('state', 'new-run', '--harness', harness, env=kit_env))
        kit['KIT_RUN_ID'] = minted['run_id']
        session_base = {k: v for k, v in kit_env.items() if k != 'PYTHONPATH'}
        session_base.update(kit, TEMP=str(tmp), TMP=str(tmp), PWD=str(work))
        if system32_off:
            session_base['PATH'] = without_system32(session_base.get('PATH', ''))
        env = driver.session_env(home, session_base)
        argv = driver.binary_argv(env)
        assert argv, f'{harness}: binary missing'
        command = parent_argv(from_shell, executable, argv + driver.canary_argv('Run the tool.'))
        with open(folder / 'stdout.txt', 'wb') as out, open(folder / 'stderr.txt', 'wb') as err:
            proc = subprocess.Popen(  # noqa: S603 - argv built above, no shell
                command,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=env,
                cwd=str(work),
            )
            deadline = time.monotonic() + CELL_TIMEOUT_S
            while proc.poll() is None and time.monotonic() < deadline:
                collect_tree(proc.pid, seen)
                time.sleep(0.2)
            row['timed_out'] = proc.poll() is None
            if row['timed_out']:
                terminate({pid: seen[pid] for pid in survivors(seen)})
            proc.wait(timeout=30)
        ended = time.monotonic()
    finally:
        stub.kill()
        stub.wait()
    if ended is not None:
        time.sleep(max(0.0, LATE_WAIT_S - (time.monotonic() - ended)))
    alive = survivors(seen)
    terminate({pid: seen[pid] for pid in alive})
    gap, reason = _gap_and_reason(folder)
    row.update(
        gap_s=gap,
        deny_marker_absent=not (work / 'hung.marker').exists(),
        reason_in_next_request=reason,
        gap_under_ceiling=gap is not None and gap < GAP_CEILING_S,
        late_marker_absent=not late.exists(),
        survivors=alive,
        tree_seen=len(seen),
    )
    row['passed'] = (
        not row['timed_out']
        and row['deny_marker_absent']
        and reason
        and row['gap_under_ceiling']
        and row['late_marker_absent']
        and not alive
        and len(seen) > 1
    )
    return row


def check_tree_admission() -> None:
    """The tree rule, on a fixed process table (runs everywhere, before any skip).

    Windows keeps an exited parent's id in a child's record, and ids are reused:
    an old process whose dead parent's id now belongs to a cell process must
    not join the cell's tree, nor anything below it.
    """
    times = {
        100: 1000,  # the parent shell
        200: 1100,  # the harness, started by the shell
        300: 1200,  # the hanging CLI, started by the harness
        400: 500,  # an older process whose dead parent had id 200
        410: 600,  # its child
        600: 1300,  # seen before, its parent gone since
        610: 1400,  # started by 600 after its parent died
        700: 1500,  # a reused id: the process seen as 700 had another creation time
        710: 1600,  # started by the new 700
        620: 1700,  # started by 610 at the very time the clock was read
        800: 1800,  # listed under 300, its id reused after the clock was read
        810: 1900,  # started by that newer 800
    }
    parents = {200: 100, 300: 200, 400: 200, 410: 400, 600: 999, 610: 600, 700: 999, 710: 700}
    parents.update({620: 610, 800: 300, 810: 800})
    family = grow_family(100, parents, times.get, {600: 1300, 700: 900}, taken=1700)
    assert sorted(family) == [100, 200, 300, 600, 610, 620], sorted(family)
    assert family[300] == 1200, family
    assert grow_family(100, parents, {}.get, {}, taken=1700) == {}, 'a dead root has no tree'
    assert grow_family(100, parents, times.get, {}, taken=999) == {}, 'a root newer than the clock'


def check_terminate_guard() -> None:
    """`terminate` ends a pid only while it is still the process recorded for it (Windows)."""
    if not WINDOWS:
        return
    child = subprocess.Popen(
        [sys.executable, '-I', '-c', 'import time; time.sleep(30)'],
        stdin=subprocess.DEVNULL,
    )
    try:
        created = _created(child.pid)
        assert created is not None, 'no creation time for a live child'
        terminate({child.pid: created - 1})
        time.sleep(0.5)
        assert child.poll() is None, 'terminate ended a pid recorded with another creation time'
        terminate({child.pid: created})
        child.wait(timeout=10)
    finally:
        child.kill()
        child.wait()


def check_live_tree() -> None:
    """On live processes, the clock read before a snapshot admits a child and its grandchild (Windows)."""
    if not WINDOWS:
        return
    code = (
        'import subprocess, sys, time; '
        'subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"]); '
        'time.sleep(30)'
    )
    child = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-I', '-c', code], stdin=subprocess.DEVNULL
    )
    seen: dict[int, int] = {}
    try:
        created = _created(child.pid)
        assert created is not None, 'no creation time for a live child'
        assert created <= _system_time(), 'the clock reads earlier than a child created before it'
        deadline = time.monotonic() + 10
        while len(seen) < 2 and time.monotonic() < deadline:
            collect_tree(child.pid, seen)
            time.sleep(0.1)
        assert len(seen) >= 2, f'the tree of a child and its grandchild: {seen}'
    finally:
        terminate({pid: c for pid, c in seen.items() if pid != child.pid})
        child.kill()
        child.wait()


def main() -> int:
    if sys.argv[1:2] == ['--hang']:
        return hang(sys.argv[2])
    check_tree_admission()
    check_terminate_guard()
    check_live_tree()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f'skip: the hung-guard matrix needs {", ".join(missing)}')
        return 0
    if not WINDOWS:
        print('skip: the hung-guard matrix runs on Windows only')
        return 0
    base = Path(os.environ['KIT_CONFORMANCE_BASE'])
    if not base.is_dir():
        print('FAIL: KIT_CONFORMANCE_BASE is not an existing folder')
        return 1
    rows = [run_cell(h, s, base) for h in HARNESSES for s in SHELLS]
    rows.append(run_cell('opencode', 'git-bash', base, system32_off=True))
    (base / RESULTS).write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(rows, indent=2))
    gaps = [r['gap_s'] for r in rows if r.get('gap_s') is not None]
    print(f'largest gap seen: {max(gaps) if gaps else None} s')
    bad = [r for r in rows if not r['passed']]
    if bad:
        print('FAIL: ' + ', '.join(f'{r["harness"]}/{r["shell"]}' for r in bad))
        return 1
    print(f'ok: hung guard ended in {len(rows)} cells (3 shells x 2 harnesses, System32 off PATH)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

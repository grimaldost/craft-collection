"""A Windows pseudo console for the interactive cells; not a test module itself.

`PseudoConsole(argv, env, cwd, log)` creates a pseudo console (`CreatePseudoConsole` through
ctypes), starts the program in it suspended, puts it in a Job Object of its own whose processes
end when the job is closed, and only then resumes it, so every process the program starts stays
in that job. A thread drains the console's output into `log`, byte for byte. `write(text)` sends
keystrokes; `wait(timeout)` gives the program's exit code, or None while it runs; `left()` lists
the processes still in the job, each with its image name; `close()` ends the job and the console.

It starts a program and writes keystrokes; it never decides a cell. The cells decide by files.

Before it creates the program, the calling process restores normal Ctrl+C processing
(`SetConsoleCtrlHandler(NULL, FALSE)`): a process started in a new process group ignores Ctrl+C
and its children inherit that, so without the call the Ctrl+C a cell writes would not reach the
program's session.

Windows only; importing it elsewhere is harmless, constructing it raises OSError.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
from pathlib import Path

WINDOWS = os.name == 'nt'
COLUMNS, ROWS = 120, 40
CTRL_C = '\x03'
CTRL_O = '\x0f'
ENTER = '\r'

_PSEUDOCONSOLE_ATTRIBUTE = 0x00020016
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_CREATE_SUSPENDED = 0x00000004
_USE_STD_HANDLES = 0x00000100
_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_EXTENDED_LIMITS = 9
_JOB_PROCESS_IDS = 3
_STILL_ACTIVE = 259
_WAIT_OBJECT_0 = 0
_QUERY_LIMITED = 0x1000
_MAX_PIDS = 1024


def _api():
    from ctypes import wintypes

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    handle, dword, boolean = ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL

    class Coord(ctypes.Structure):
        _fields_ = (('X', wintypes.SHORT), ('Y', wintypes.SHORT))

    class StartupInfo(ctypes.Structure):
        _fields_ = (
            ('cb', dword),
            ('lpReserved', wintypes.LPWSTR),
            ('lpDesktop', wintypes.LPWSTR),
            ('lpTitle', wintypes.LPWSTR),
            ('dwX', dword),
            ('dwY', dword),
            ('dwXSize', dword),
            ('dwYSize', dword),
            ('dwXCountChars', dword),
            ('dwYCountChars', dword),
            ('dwFillAttribute', dword),
            ('dwFlags', dword),
            ('wShowWindow', wintypes.WORD),
            ('cbReserved2', wintypes.WORD),
            ('lpReserved2', ctypes.c_void_p),
            ('hStdInput', handle),
            ('hStdOutput', handle),
            ('hStdError', handle),
        )

    class StartupInfoEx(ctypes.Structure):
        _fields_ = (('StartupInfo', StartupInfo), ('lpAttributeList', ctypes.c_void_p))

    class ProcessInformation(ctypes.Structure):
        _fields_ = (
            ('hProcess', handle),
            ('hThread', handle),
            ('dwProcessId', dword),
            ('dwThreadId', dword),
        )

    class Basic(ctypes.Structure):
        _fields_ = (
            ('PerProcessUserTimeLimit', ctypes.c_int64),
            ('PerJobUserTimeLimit', ctypes.c_int64),
            ('LimitFlags', dword),
            ('MinimumWorkingSetSize', ctypes.c_size_t),
            ('MaximumWorkingSetSize', ctypes.c_size_t),
            ('ActiveProcessLimit', dword),
            ('Affinity', ctypes.c_size_t),
            ('PriorityClass', dword),
            ('SchedulingClass', dword),
        )

    class Extended(ctypes.Structure):
        _fields_ = (
            ('BasicLimitInformation', Basic),
            ('IoInfo', ctypes.c_uint64 * 6),
            ('ProcessMemoryLimit', ctypes.c_size_t),
            ('JobMemoryLimit', ctypes.c_size_t),
            ('PeakProcessMemoryUsed', ctypes.c_size_t),
            ('PeakJobMemoryUsed', ctypes.c_size_t),
        )

    class PidList(ctypes.Structure):
        _fields_ = (
            ('NumberOfAssignedProcesses', dword),
            ('NumberOfProcessIdsInList', dword),
            ('ProcessIdList', ctypes.c_size_t * _MAX_PIDS),
        )

    sigs = {
        'CreatePipe': (
            (ctypes.POINTER(handle), ctypes.POINTER(handle), ctypes.c_void_p, dword),
            boolean,
        ),
        'CreatePseudoConsole': (
            (Coord, handle, handle, dword, ctypes.POINTER(handle)),
            ctypes.c_long,
        ),
        'ClosePseudoConsole': ((handle,), None),
        'InitializeProcThreadAttributeList': (
            (ctypes.c_void_p, dword, dword, ctypes.POINTER(ctypes.c_size_t)),
            boolean,
        ),
        'UpdateProcThreadAttribute': (
            (
                ctypes.c_void_p,
                dword,
                ctypes.c_size_t,
                handle,
                ctypes.c_size_t,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ),
            boolean,
        ),
        'DeleteProcThreadAttributeList': ((ctypes.c_void_p,), None),
        'CreateProcessW': (
            (
                wintypes.LPCWSTR,
                ctypes.c_wchar_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                boolean,
                dword,
                ctypes.c_void_p,
                wintypes.LPCWSTR,
                ctypes.POINTER(StartupInfoEx),
                ctypes.POINTER(ProcessInformation),
            ),
            boolean,
        ),
        'ResumeThread': ((handle,), dword),
        'CloseHandle': ((handle,), boolean),
        'WaitForSingleObject': ((handle, dword), dword),
        'GetExitCodeProcess': ((handle, ctypes.POINTER(dword)), boolean),
        'TerminateProcess': ((handle, wintypes.UINT), boolean),
        'ReadFile': (
            (handle, ctypes.c_void_p, dword, ctypes.POINTER(dword), ctypes.c_void_p),
            boolean,
        ),
        'WriteFile': (
            (handle, ctypes.c_char_p, dword, ctypes.POINTER(dword), ctypes.c_void_p),
            boolean,
        ),
        'CreateJobObjectW': ((ctypes.c_void_p, wintypes.LPCWSTR), handle),
        'SetInformationJobObject': ((handle, ctypes.c_int, ctypes.c_void_p, dword), boolean),
        'QueryInformationJobObject': (
            (handle, ctypes.c_int, ctypes.c_void_p, dword, ctypes.c_void_p),
            boolean,
        ),
        'AssignProcessToJobObject': ((handle, handle), boolean),
        'TerminateJobObject': ((handle, wintypes.UINT), boolean),
        'SetConsoleCtrlHandler': ((ctypes.c_void_p, boolean), boolean),
        'OpenProcess': ((dword, boolean, dword), handle),
        'QueryFullProcessImageNameW': (
            (handle, dword, ctypes.c_wchar_p, ctypes.POINTER(dword)),
            boolean,
        ),
    }
    for name, (args, result) in sigs.items():
        fn = getattr(k32, name)
        fn.argtypes = args
        fn.restype = result
    types = {
        'Coord': Coord,
        'StartupInfoEx': StartupInfoEx,
        'ProcessInformation': ProcessInformation,
        'Extended': Extended,
        'PidList': PidList,
    }
    return k32, types


def _check(ok: object, what: str) -> None:
    if not ok:
        raise OSError(ctypes.get_last_error(), f'{what} failed')


def _environment_block(env: dict) -> ctypes.Array:
    pairs = sorted(env.items(), key=lambda kv: kv[0].upper())
    text = ''.join(f'{k}={v}\0' for k, v in pairs) + '\0'
    return (ctypes.c_wchar * len(text))(*text)


class PseudoConsole:
    """One program under a pseudo console, inside a Job Object of its own."""

    def __init__(self, argv: list[str], env: dict, cwd: Path | str, log: Path | str) -> None:
        if not WINDOWS:
            raise OSError('a pseudo console needs Windows')
        self._k32, self._types = _api()
        self.log = Path(log)
        self.received = 0
        self.last_output = time.monotonic()
        self._lock = threading.Lock()
        self._handles: dict[str, int | None] = {}
        self._pc = None
        self._job = None
        self._process = None
        self._reader = None
        try:
            self._start(argv, env, str(cwd))
        except BaseException:
            self.close()
            raise

    def _start(self, argv: list[str], env: dict, cwd: str) -> None:
        k32, types = self._k32, self._types
        handle = ctypes.c_void_p
        in_read, in_write, out_read, out_write = handle(), handle(), handle(), handle()
        _check(k32.CreatePipe(ctypes.byref(in_read), ctypes.byref(in_write), None, 0), 'CreatePipe')
        self._handles.update(in_read=in_read.value, in_write=in_write.value)
        _check(
            k32.CreatePipe(ctypes.byref(out_read), ctypes.byref(out_write), None, 0), 'CreatePipe'
        )
        self._handles.update(out_read=out_read.value, out_write=out_write.value)
        pc = handle()
        result = k32.CreatePseudoConsole(
            types['Coord'](COLUMNS, ROWS), in_read, out_write, 0, ctypes.byref(pc)
        )
        if result != 0:
            raise OSError(f'CreatePseudoConsole failed: {result & 0xFFFFFFFF:#x}')
        self._pc = pc.value
        # The console holds its own copies; ours would keep the pipes open after it closes.
        for name in ('in_read', 'out_write'):
            k32.CloseHandle(self._handles.pop(name))
        self._reader = threading.Thread(target=self._drain, daemon=True)
        self._reader.start()

        size = ctypes.c_size_t(0)
        k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attributes = ctypes.create_string_buffer(size.value)
        _check(
            k32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)),
            'InitializeProcThreadAttributeList',
        )
        try:
            _check(
                k32.UpdateProcThreadAttribute(
                    attributes,
                    0,
                    _PSEUDOCONSOLE_ATTRIBUTE,
                    self._pc,
                    ctypes.sizeof(ctypes.c_void_p),
                    None,
                    None,
                ),
                'UpdateProcThreadAttribute',
            )
            info = types['StartupInfoEx']()
            info.StartupInfo.cb = ctypes.sizeof(info)
            # Null standard handles: the program gets the console's own, never this process's.
            info.StartupInfo.dwFlags = _USE_STD_HANDLES
            info.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            process = types['ProcessInformation']()
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            block = _environment_block(env)
            # Children of this process would otherwise inherit an ignored Ctrl+C.
            k32.SetConsoleCtrlHandler(None, False)
            flags = _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT | _CREATE_SUSPENDED
            _check(
                k32.CreateProcessW(
                    None,
                    command,
                    None,
                    None,
                    False,
                    flags,
                    ctypes.cast(block, ctypes.c_void_p),
                    cwd,
                    ctypes.byref(info),
                    ctypes.byref(process),
                ),
                'CreateProcessW',
            )
        finally:
            k32.DeleteProcThreadAttributeList(attributes)
        self._process = process.hProcess
        self.pid = int(process.dwProcessId)
        try:
            self._job = self._new_job()
            _check(
                k32.AssignProcessToJobObject(self._job, self._process), 'AssignProcessToJobObject'
            )
            if k32.ResumeThread(process.hThread) == 0xFFFFFFFF:
                raise OSError(ctypes.get_last_error(), 'ResumeThread failed')
        except BaseException:
            k32.TerminateProcess(self._process, 1)
            raise
        finally:
            k32.CloseHandle(process.hThread)

    def _new_job(self) -> int:
        k32, types = self._k32, self._types
        job = k32.CreateJobObjectW(None, None)
        _check(job, 'CreateJobObjectW')
        limits = types['Extended']()
        limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        ok = k32.SetInformationJobObject(
            job, _JOB_EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        if not ok:
            error = ctypes.get_last_error()
            k32.CloseHandle(job)
            raise OSError(error, 'SetInformationJobObject failed')
        return job

    def _drain(self) -> None:
        from ctypes import wintypes

        buffer = ctypes.create_string_buffer(65536)
        count = wintypes.DWORD(0)
        source = self._handles.get('out_read')
        with open(self.log, 'ab') as fh:
            while True:
                ok = self._k32.ReadFile(source, buffer, len(buffer), ctypes.byref(count), None)
                if not ok or count.value == 0:
                    return
                fh.write(buffer.raw[: count.value])
                fh.flush()
                with self._lock:
                    self.received += count.value
                    self.last_output = time.monotonic()

    def write(self, text: str) -> None:
        """Send keystrokes: the UTF-8 bytes of `text`."""
        from ctypes import wintypes

        data = text.encode('utf-8')
        written = wintypes.DWORD(0)
        sink = self._handles.get('in_write')
        _check(self._k32.WriteFile(sink, data, len(data), ctypes.byref(written), None), 'WriteFile')

    def type_slowly(self, text: str, gap_s: float = 0.05) -> None:
        """Send `text` one character at a time, as a person types."""
        for char in text:
            self.write(char)
            time.sleep(gap_s)

    def wait(self, timeout_s: float) -> int | None:
        """The program's exit code, or None when it still runs after `timeout_s` seconds."""
        from ctypes import wintypes

        if self._process is None:
            return None
        if self._k32.WaitForSingleObject(self._process, int(timeout_s * 1000)) != _WAIT_OBJECT_0:
            return None
        code = wintypes.DWORD(0)
        _check(
            self._k32.GetExitCodeProcess(self._process, ctypes.byref(code)), 'GetExitCodeProcess'
        )
        return int(code.value)

    def left(self) -> list[dict]:
        """Each process still in the job, with its image's file name (None when unreadable)."""
        from ctypes import wintypes

        if self._job is None:
            return []
        listing = self._types['PidList']()
        ok = self._k32.QueryInformationJobObject(
            self._job, _JOB_PROCESS_IDS, ctypes.byref(listing), ctypes.sizeof(listing), None
        )
        _check(ok, 'QueryInformationJobObject')
        out = []
        for pid in list(listing.ProcessIdList)[: listing.NumberOfProcessIdsInList]:
            image = None
            opened = self._k32.OpenProcess(_QUERY_LIMITED, False, int(pid))
            if opened:
                buffer = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(buffer))
                if self._k32.QueryFullProcessImageNameW(opened, 0, buffer, ctypes.byref(size)):
                    image = os.path.basename(buffer.value)
                self._k32.CloseHandle(opened)
            out.append({'pid': int(pid), 'image': image})
        return out

    def close(self) -> None:
        """End the job's processes, then the console and the pipes."""
        k32 = self._k32
        if self._job is not None:
            k32.TerminateJobObject(self._job, 1)
            k32.CloseHandle(self._job)
            self._job = None
        if self._pc is not None:
            k32.ClosePseudoConsole(self._pc)
            self._pc = None
        if self._reader is not None:
            self._reader.join(timeout=10)
        for name in list(self._handles):
            value = self._handles.pop(name)
            if value:
                k32.CloseHandle(value)
        if self._process is not None:
            k32.CloseHandle(self._process)
            self._process = None

"""Checkers of policy version 2: load one, call it within its budget, keep its output away.

A checker is a Python file that defines `check(act, observation)`. The judge
compiles and executes the very bytes the policy load hashed, with no second
read of the file and no bytecode cache, under a module name that no package
module can have, with `__file__` set to the checker's path and the module
entered in `sys.modules` before its bytes run, at most once per process. That
step, `execute`, is the same for `kit judge`, for a test that a checker loads
(`try_load`) and for any later caller.

A call answers `match`, `no-match` or `cannot-tell`. The load and the call run
on one daemon thread, and the caller waits on it for the checker's
`budget_ms`. One judgement waits at most `TOTAL_BUDGET_MS` in all: each wait is
cut to what is left, and a checker is not called once less than
`BUDGET_MIN_MS` is left. A file that does not execute, defines no callable
`check`, raises (any `BaseException`), returns anything else or has not
returned when the wait ends reads `cannot-tell`. The budget is cooperative: a
call that never yields the interpreter, or one that ends the process, is
outside this contract.

The output sink works at the file-descriptor level: `install_sink` points
descriptors 1 and 2 and `sys.stdout` and `sys.stderr` at the null device for
the rest of the process and returns a duplicate of descriptor 1 for the
verdict; `quiet` does the same for the length of a block and restores them.
"""

from __future__ import annotations

import copy
import hashlib
import os
import sys
import threading
import time
import types
from collections.abc import Iterator
from contextlib import contextmanager

from harness_kit.policy import BUDGET_MIN_MS, Checker

TOTAL_BUDGET_MS = 500
DETAIL_MAX = 200

MATCH = 'match'
NO_MATCH = 'no-match'
CANNOT_TELL = 'cannot-tell'
RESULTS = (MATCH, NO_MATCH, CANNOT_TELL)
RETURN_KEYS = ('result', 'detail')


class CheckerLoadError(Exception):
    """The checker file did not execute; the message is ASCII."""


class _Load:
    """One checker module's load, shared by every caller in this process."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.module: types.ModuleType | None = None
        self.error: str | None = None


_LOADS: dict[str, _Load] = {}
_LOADS_LOCK = threading.Lock()


def module_name(checker: Checker) -> str:
    """The module name of a checker: not an identifier, so no package module has it."""
    key = f'{checker.path}\0{checker.sha256}'.encode('utf-8', 'surrogatepass')
    return f'kit-checker-{hashlib.sha256(key).hexdigest()[:32]}'


def _exec_module(checker: Checker, name: str) -> types.ModuleType:
    code = compile(checker.source, checker.path, 'exec', dont_inherit=True)
    module = types.ModuleType(name)
    module.__file__ = checker.path
    sys.modules[name] = module
    try:
        exec(code, module.__dict__)  # noqa: S102 - the checker file is pinned by its sha256
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def execute(checker: Checker) -> types.ModuleType:
    """Compile and execute the checker's hashed bytes once per process; return its module.

    Raise CheckerLoadError when the file does not execute, now or at the first
    attempt in this process. A caller that finds another thread's load still
    running waits for it.
    """
    name = module_name(checker)
    with _LOADS_LOCK:
        load = _LOADS.get(name)
        owner = load is None
        if owner:
            load = _LOADS[name] = _Load()
    if owner:
        try:
            load.module = _exec_module(checker, name)
        except BaseException as exc:  # SystemExit included: the file did not execute
            load.error = f'checker {checker.id!a} does not execute: {type(exc).__name__!a}'
        finally:
            load.done.set()
    else:
        load.done.wait()
    if load.module is None:
        raise CheckerLoadError(load.error or f'checker {checker.id!a} does not execute')
    return load.module


def _check_function(checker: Checker):
    fn = getattr(execute(checker), 'check', None)
    if not callable(fn):
        raise CheckerLoadError(f'checker {checker.id!a} defines no callable check')
    return fn


_RETURNED = 'returned'
_RAISED = 'raised'
_RUNNING = 'running'


def _run(target, wait_s: float) -> tuple[str, object]:
    """Run `target` on a daemon thread and wait `wait_s` for it.

    Return (`returned`, value), (`raised`, exception) or (`running`, None).
    """
    box: list = []

    def body() -> None:
        try:
            box.append((_RETURNED, target()))
        except BaseException as exc:  # an exception of any kind is the checker's answer
            box.append((_RAISED, exc))

    thread = threading.Thread(target=body, name='kit-checker', daemon=True)
    thread.start()
    thread.join(max(wait_s, 0.0))
    if thread.is_alive() or not box:
        return _RUNNING, None
    return box[0]


def try_load(checker: Checker) -> str | None:
    """Test that a checker executes and defines a callable `check`, without calling it.

    The load goes through `execute`, as the judge's does, on a daemon thread
    waited on for at most the checker's `budget_ms`: a load still running then
    counts as not executing and does not hold the process open. Descriptors 1
    and 2 and `sys.stdout`/`sys.stderr` point at the null device for the wait
    only. Return None when the checker is sound, else an ASCII reason.
    """
    with quiet():
        state, value = _run(lambda: _check_function(checker), checker.budget_ms / 1000)
    if state == _RETURNED:
        return None
    if state == _RUNNING:
        return f'checker {checker.id!a} did not load within {checker.budget_ms} ms'
    if isinstance(value, CheckerLoadError):
        return str(value)
    return f'checker {checker.id!a} does not execute: {type(value).__name__!a}'


def reduce_detail(detail: str) -> str:
    """A detail in ASCII, cut to its first `DETAIL_MAX` characters."""
    return detail.encode('ascii', 'backslashreplace').decode()[:DETAIL_MAX]


def read_return(value: object) -> tuple[str, str | None]:
    """The result and the reduced detail of what `check` returned; anything else cannot tell."""
    if not isinstance(value, dict) or any(k not in RETURN_KEYS for k in value):
        return CANNOT_TELL, None
    result = value.get('result')
    if not isinstance(result, str) or result not in RESULTS:
        return CANNOT_TELL, None
    detail = value.get('detail')
    if 'detail' in value and not isinstance(detail, str):
        return CANNOT_TELL, None
    return result, None if detail is None else reduce_detail(detail)


class Judgement:
    """The checkers of one judgement and what is left of its total budget."""

    def __init__(self, checkers: tuple[Checker, ...], total_ms: int = TOTAL_BUDGET_MS) -> None:
        self.checkers = {c.id: c for c in checkers}
        self.left_ms = float(total_ms)

    def call(self, checker_id: str, act: dict, observation: dict) -> tuple[str, str | None]:
        """Load and call one checker on copies of `act` and `observation`; (result, detail)."""
        checker = self.checkers.get(checker_id)
        if checker is None or self.left_ms < BUDGET_MIN_MS:
            return CANNOT_TELL, None
        act, observation = copy.deepcopy(act), copy.deepcopy(observation)
        wait_ms = min(checker.budget_ms, self.left_ms)
        start = time.monotonic()
        state, value = _run(lambda: _check_function(checker)(act, observation), wait_ms / 1000)
        self.left_ms -= (time.monotonic() - start) * 1000
        if state != _RETURNED:
            return CANNOT_TELL, None
        return read_return(value)


def _flush_std() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.flush()
        except (OSError, ValueError):
            pass


def _null_stream():
    return open(os.devnull, 'w', encoding='ascii', errors='replace')


def install_sink() -> int:
    """Point descriptors 1 and 2 and `sys.stdout`/`sys.stderr` at the null device for good.

    Return a duplicate of descriptor 1, the one place the verdict is written.
    """
    _flush_std()
    out = os.dup(1)
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
    finally:
        os.close(null)
    sys.stdout = _null_stream()
    sys.stderr = _null_stream()
    return out


@contextmanager
def quiet() -> Iterator[None]:
    """Descriptors 1 and 2 and `sys.stdout`/`sys.stderr` at the null device for one block."""
    _flush_std()
    saved_fds = (os.dup(1), os.dup(2))
    saved_streams = (sys.stdout, sys.stderr)
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
    finally:
        os.close(null)
    sink = _null_stream()
    sys.stdout = sys.stderr = sink
    try:
        yield
    finally:
        _flush_std()
        sys.stdout, sys.stderr = saved_streams
        os.dup2(saved_fds[0], 1)
        os.dup2(saved_fds[1], 2)
        for fd in saved_fds:
            os.close(fd)
        sink.close()


def write_all(fd: int, data: bytes) -> None:
    """Write every byte of `data` to descriptor `fd`."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]

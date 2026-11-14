#!/usr/bin/env python3
"""harness-kit shell for Claude Code, a PreToolUse command hook. It holds no policy.

It turns the raw payload into one neutral event, runs the kit CLI that
`shell_config.json` beside this file names, with the event on stdin, and
translates the verdict: allow prints nothing, deny prints a PreToolUse deny.
Anything that keeps it from a verdict denies with `kit could not judge:`.
A CLI still running at the deadline is ended with its whole tree: on Windows by
TerminateJobObject on the Job Object the CLI joined as it started; if a Job
Object call fails, or under the test seam KIT_SHELL_NO_JOB=1, by an absolute
System32 taskkill.exe, not waited for; on POSIX by a group kill.

Run with `--note`, it is a UserPromptSubmit, PostToolUse and PostToolUseFailure
hook instead: it sends what happened, as one note, to the `note_argv` that
`note_config.json` beside this file names, under the same deadline and tree
kill. A note never decides: the mode prints nothing, does not read the CLI's
exit status, and ends silently whatever fails.
"""

import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time

PREFIX = 'kit could not judge: '
SHELL_TOOLS = ('Bash', 'PowerShell')
WRITE_TOOLS = {'Write': 'file_path', 'Edit': 'file_path', 'MultiEdit': 'file_path'}
WRITE_TOOLS['NotebookEdit'] = 'notebook_path'
WINDOWS = os.name == 'nt'
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
QUIET = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
HERE = os.path.dirname(os.path.abspath(__file__))
NOTE_KINDS = ('prompt', 'outcome')
RESULT_EVENTS = ('PostToolUse', 'PostToolUseFailure')
TEXT_CAP, OUTPUT_CAP = 20000, 65536


class CouldNotJudgeError(Exception):
    """The shell has no verdict; the message is the ASCII detail of the deny."""


def load_config() -> dict:
    path = os.path.join(HERE, 'shell_config.json')
    try:
        with open(path, 'rb') as fh:
            config = json.loads(fh.read().decode('utf-8'))
    except (OSError, ValueError) as exc:
        raise CouldNotJudgeError(f'shell_config.json unreadable ({type(exc).__name__})') from None
    ok = isinstance(config, dict) and config.get('kit_shell_config') == 1
    argv, timeout = (config.get('cli_argv'), config.get('timeout_s')) if ok else (None, None)
    ok = ok and isinstance(argv, list) and bool(argv) and all(isinstance(a, str) for a in argv)
    ok = ok and type(timeout) in (int, float) and timeout > 0
    if not (ok and isinstance(config.get('harness_version'), str)):
        raise CouldNotJudgeError('shell_config.json malformed')
    return config


def head(session_id: str, config: dict) -> dict:
    """The keys an event and a note share, from `run_id` to `observation`."""
    observation = {
        'session': 'observed',
        **dict.fromkeys(('parent', 'root', 'origin'), 'unavailable'),
    }
    observation.update(command='not_applicable', paths='not_applicable')
    out = {'run_id': os.environ.get('KIT_RUN_ID') or None}
    out['harness'] = {'name': 'claude-code', 'version': config['harness_version']}
    out['session'] = {'id': session_id, 'parent_id': None, 'root_id': None}
    out.update(origin='unknown', observation=observation)
    return out


def build_event(raw: bytes, config: dict) -> dict:
    try:
        payload = json.loads(raw.decode('utf-8'))
    except ValueError:
        raise CouldNotJudgeError('payload is not JSON') from None
    fields = ('session_id', 'tool_name', 'cwd')
    if not isinstance(payload, dict) or not all(isinstance(payload.get(k), str) for k in fields):
        raise CouldNotJudgeError('payload lacks session_id, tool_name or cwd')
    tool, cwd, given = payload['tool_name'], payload['cwd'], payload.get('tool_input')
    given = given if isinstance(given, dict) else {}
    act = {'kind': 'other', 'command': None, 'argv': None, 'paths': [], 'cwd': cwd}
    event = {'kit_event': 1, **head(payload['session_id'], config)}
    observation = event['observation']
    if tool in SHELL_TOOLS:
        act['kind'], observation['command'] = 'shell', 'observed'
        act['command'] = given['command'] if isinstance(given.get('command'), str) else None
    elif tool in WRITE_TOOLS:
        act['kind'], observation['paths'] = 'file_write', 'observed'
        path = given.get(WRITE_TOOLS[tool])
        if isinstance(path, str) and path:
            act['paths'] = [os.path.normpath(os.path.join(cwd, path))]
    act['payload_sha256'] = hashlib.sha256(raw).hexdigest()
    event['act'] = act
    return event


def new_job(proc: subprocess.Popen):
    """Put the started CLI in a new Job Object; None when any call fails."""
    try:
        k32 = ctypes.WinDLL('kernel32')
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        job = ctypes.c_void_p(k32.CreateJobObjectW(None, None))
        if job.value and k32.AssignProcessToJobObject(job, ctypes.c_void_p(int(proc._handle))):
            return k32, job
    except (OSError, AttributeError, ValueError):
        pass
    return None


def kill_tree(proc: subprocess.Popen, job) -> None:
    if not WINDOWS:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        return
    if job is not None and job[0].TerminateJobObject(job[1], 1):
        return
    killer = os.path.join(os.environ.get('SYSTEMROOT') or 'C:\\Windows', 'System32', 'taskkill.exe')
    try:  # never waited for: its exit code does not say whether the tree died
        argv = [killer, '/PID', str(proc.pid), '/T', '/F']
        subprocess.Popen(argv, creationflags=NO_WINDOW, **QUIET)  # noqa: S603 - absolute, no shell
    except OSError:
        pass


def run_cli(argv: list, data: bytes, timeout: float) -> bytes:
    proc, out = start_cli(argv, data, timeout)
    if not out or proc.returncode != 0:
        raise CouldNotJudgeError(f'CLI exited {proc.returncode}')
    return out[0] or b''


def start_cli(argv: list, data: bytes, timeout: float) -> tuple:
    """Run the CLI with `data` on stdin; its tree is ended at the deadline."""
    deadline = time.monotonic() + timeout
    extra = {'creationflags': NO_WINDOW} if WINDOWS else {'start_new_session': True}
    pipes = {'stdin': subprocess.PIPE, 'stdout': subprocess.PIPE, 'stderr': subprocess.DEVNULL}
    try:
        proc = subprocess.Popen(argv, **pipes, **extra)  # noqa: S603 - argv from the config, no shell
    except (OSError, ValueError) as exc:
        raise CouldNotJudgeError(f'CLI did not start ({type(exc).__name__})') from None
    no_job = os.environ.get('KIT_SHELL_NO_JOB') == '1'
    job = new_job(proc) if WINDOWS and not no_job else None
    out = []
    worker = threading.Thread(target=lambda: out.append(proc.communicate(data)[0]), daemon=True)
    worker.start()
    worker.join(max(0.0, deadline - time.monotonic()))
    if worker.is_alive():
        kill_tree(proc, job)
        raise CouldNotJudgeError(f'CLI ran past {timeout} s and was ended')
    return proc, out


def judge(raw: bytes) -> dict | None:
    """The deny to print, or None for allow."""
    config = load_config()
    event = json.dumps(build_event(raw, config), ensure_ascii=True).encode('ascii')
    text = run_cli(config['cli_argv'], event, config['timeout_s']).strip()
    try:
        verdict = json.loads(text.decode('utf-8'))
    except ValueError:
        verdict = None
    is_verdict = isinstance(verdict, dict) and verdict.get('kit_verdict') == 1
    effect = verdict.get('effect') if is_verdict else None
    if effect not in ('allow', 'deny'):
        raise CouldNotJudgeError(f'CLI printed no verdict ({len(text)} bytes)')
    reason = verdict.get('reason')
    return None if effect == 'allow' else deny(reason if isinstance(reason, str) else '')


def deny(reason: str) -> dict:
    body = {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny'}
    body['permissionDecisionReason'] = reason
    return {'hookSpecificOutput': body}


def main() -> None:
    try:
        out = judge(sys.stdin.buffer.read())
    except CouldNotJudgeError as exc:
        out = deny(PREFIX + str(exc))
    except BaseException as exc:  # any failure denies
        out = deny(PREFIX + f'shell failed ({type(exc).__name__})')
    if out is not None:
        sys.stdout.write(json.dumps(out, ensure_ascii=True) + '\n')
    sys.stdout.flush()
    os._exit(0)  # leave nothing waiting on a pipe a killed tree may still hold


def load_note_config() -> dict:
    with open(os.path.join(HERE, 'note_config.json'), 'rb') as fh:
        config = json.loads(fh.read().decode('utf-8'))
    get = config.get if isinstance(config, dict) else {}.get
    argv, timeout, records = get('note_argv'), get('timeout_s'), get('records')
    ok = type(get('kit_note_config')) is int and get('kit_note_config') == 1
    ok = ok and isinstance(argv, list) and bool(argv) and all(isinstance(a, str) for a in argv)
    ok = ok and type(timeout) in (int, float) and timeout > 0 and isinstance(records, list)
    if not (ok and all(kind in NOTE_KINDS for kind in records)):
        raise ValueError('note_config.json malformed')
    return config


def build_note(raw: bytes, config: dict, records: list) -> dict | None:
    """The note for this payload, or None when it gives none."""
    payload = json.loads(raw.decode('utf-8'))
    fields = ('session_id', 'hook_event_name')
    if not isinstance(payload, dict) or not all(isinstance(payload.get(k), str) for k in fields):
        return None
    name, text = payload['hook_event_name'], payload.get('prompt')
    if name == 'UserPromptSubmit' and isinstance(text, str) and 'prompt' in records:
        body = {'kind': 'prompt', 'text': text[:TEXT_CAP], 'truncated': len(text) > TEXT_CAP}
        return {'kit_note': 1, **head(payload['session_id'], config), 'note': body}
    tool = payload.get('tool_name')
    if name not in RESULT_EVENTS or tool not in SHELL_TOOLS or 'outcome' not in records:
        return None
    event = build_event(raw, config)
    del event['kit_event']
    status, output = 'failed', None
    if name == 'PostToolUse':
        response = payload.get('tool_response')
        response = response if isinstance(response, dict) else {}
        task = response.get('backgroundTaskId')
        status = 'background' if isinstance(task, str) and task else 'completed'
        stdout = response.get('stdout')
        output = stdout if status == 'completed' and isinstance(stdout, str) else None
    body = {'kind': 'outcome', 'act': event.pop('act'), 'status': status}
    body['output'] = None if output is None else output[-OUTPUT_CAP:]
    body['truncated'] = output is not None and len(output) > OUTPUT_CAP
    return {'kit_note': 1, **event, 'note': body}


def note_main() -> None:
    try:
        raw = sys.stdin.buffer.read()
        notes, config = load_note_config(), load_config()
        note = build_note(raw, config, notes['records'])
        if note is not None:
            data = json.dumps(note, ensure_ascii=True).encode('ascii')
            start_cli(notes['note_argv'], data, notes['timeout_s'])  # its output is discarded
    except BaseException:  # noqa: S110 - a note never decides: every failure ends silently
        pass
    os._exit(0)


if __name__ == '__main__':
    note_main() if sys.argv[1:] == ['--note'] else main()

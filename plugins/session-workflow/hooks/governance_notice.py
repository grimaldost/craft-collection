"""Governance-change notice: a session hears once that the governed CLAUDE.md changed.

    python governance_notice.py --session-start   # SessionStart: record a baseline when none exists
    python governance_notice.py --prompt-submit   # UserPromptSubmit: announce a change, once

With no flag, the payload's `hook_event_name` picks the arm.

Why. The owner's global `CLAUDE.md` is edited by one supervising session while
other sessions keep running, many of them woken only by task notifications and
subagent hand-backs. A session loads that file once, at its start; a rule added
afterwards does not reach it, and nothing told it to look again.

How. At SessionStart, and only when this session has no baseline yet, the hook
records the SHA-256 and modification time of the governed `CLAUDE.md` (the governed
home comes from `governed_home.py`: `$SESSION_WORKFLOW_GOVERNED_HOME`, else
`$CLAUDE_CONFIG_DIR`, else `~/.claude`). A later SessionStart (compact, resume)
keeps the existing baseline, so it cannot absorb a change silently. On every
UserPromptSubmit, owner-typed or synthetic (an autonomous session may see nothing
else), it hashes the file again; when the hash differs it returns one line of
`hookSpecificOutput.additionalContext` naming the file, the time it changed and the
instruction to re-read it before the next act, and only after that line was written
records the new hash, so each change is announced once. A file that appears or
disappears is a change too; a touch that leaves the content alone is not. A prompt
with no baseline (the plugin enabled mid-session) records one and says nothing.
Baselines live under the plugin's data directory, one file per session and governed
path.

Gate: `SESSION_WORKFLOW_GOVERNANCE_NOTICE`. `0` turns it off (nothing is read or
written); unset or any other value: on, the default. The trigger is exact (a
resolved path and its hash), so it ships on. Output is UTF-8 whatever the console
codepage. Every path exits 0 with no output on failure: a hook must not break a
session.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from governed_home import governed_path
except Exception:  # a partial install cannot resolve the governed file: stay silent
    governed_path = None

GATE = 'SESSION_WORKFLOW_GOVERNANCE_NOTICE'
STATE_DIR_ENV = 'SESSION_WORKFLOW_GOVERNANCE_NOTICE_DIR'
GOVERNED_NAME = 'CLAUDE.md'


# ---------------------------------------------------------------- environment


def enabled() -> bool:
    """On unless the gate is `0`."""
    return os.environ.get(GATE) != '0'


def _state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'governance-notice'


def _safe_session(session_id: object) -> str:
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(session_id or 'unknown'))[:80]


def baseline_path(session_id: object, target: Path) -> Path:
    """One baseline per session and governed file, so a moved governed home starts fresh."""
    key = hashlib.sha256(str(target).encode('utf-8')).hexdigest()[:12]
    return _state_dir() / f'{_safe_session(session_id)}-{key}.json'


def _load_stdin_json() -> dict:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8-sig', errors='replace')
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ------------------------------------------------------------------- the file


def snapshot(target: Path) -> dict:
    """The file's SHA-256 and modification time; `sha256` is None when it is absent."""
    try:
        data = target.read_bytes()
        mtime = target.stat().st_mtime
    except OSError:
        return {'path': str(target), 'sha256': None, 'mtime': None}
    return {'path': str(target), 'sha256': hashlib.sha256(data).hexdigest(), 'mtime': mtime}


def format_time(stamp: float) -> str:
    """Local time with its UTC offset, to the second: 2026-10-26T10:15:00-03:00."""
    moment = datetime.datetime.fromtimestamp(stamp, tz=datetime.timezone.utc).astimezone()
    return moment.isoformat(timespec='seconds')


def notice_text(current: dict) -> str:
    path = current['path']
    if current['sha256'] is None:
        now = datetime.datetime.now(tz=datetime.timezone.utc).timestamp()
        what = f'The governed {path} was removed (noticed {format_time(now)})'
    else:
        what = f'The governed {path} changed at {format_time(current["mtime"])}'
    return (
        f'{what}, after this session last read it: re-read it before the next act, '
        'its rules may have changed.'
    )


def _read_baseline(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and 'sha256' in data else None


def _write_baseline(path: Path, record: dict) -> None:
    """Whole-file replace through a temp file, so a crash leaves the old baseline."""
    with contextlib.suppress(Exception):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f'.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, path)


def _target() -> Path | None:
    if governed_path is None:
        return None
    return governed_path(GOVERNED_NAME)


# ------------------------------------------------------------------ handlers


def handle_session_start(payload: dict) -> None:
    """Record the baseline only when this session has none: a compact keeps the old one."""
    session_id = payload.get('session_id')
    target = _target()
    if not enabled() or not session_id or target is None:
        return
    path = baseline_path(session_id, target)
    if _read_baseline(path) is None:
        _write_baseline(path, snapshot(target))


def emit_json(output: dict) -> None:
    """Write `output` to stdout as UTF-8 JSON, whatever the console codepage."""
    stream = sys.stdout
    reconfigure = getattr(stream, 'reconfigure', None)
    if reconfigure is not None:
        reconfigure(encoding='utf-8')
    stream.write(json.dumps(output, ensure_ascii=False) + '\n')
    stream.flush()


def handle_prompt_submit(payload: dict, emit=None) -> dict | None:
    """Announce a change since the baseline, then make it the baseline.

    With `emit` (the CLI passes `emit_json`), the notice is written first and the
    new hash recorded only when the write succeeded; a failed write leaves the
    change pending for the next prompt and returns None."""
    session_id = payload.get('session_id')
    target = _target()
    if not enabled() or not session_id or target is None:
        return None
    path = baseline_path(session_id, target)
    baseline = _read_baseline(path)
    current = snapshot(target)
    if baseline is None:
        _write_baseline(path, current)
        return None
    if baseline.get('sha256') == current['sha256']:
        return None
    output = {
        'hookSpecificOutput': {
            'hookEventName': 'UserPromptSubmit',
            'additionalContext': notice_text(current),
        }
    }
    if emit is not None:
        try:
            emit(output)
        except Exception:
            return None
    _write_baseline(path, current)
    return output


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        payload = _load_stdin_json()
        event = payload.get('hook_event_name')
        if '--session-start' in argv or (not argv and event == 'SessionStart'):
            handle_session_start(payload)
        elif '--prompt-submit' in argv or (not argv and event == 'UserPromptSubmit'):
            handle_prompt_submit(payload, emit=emit_json)
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

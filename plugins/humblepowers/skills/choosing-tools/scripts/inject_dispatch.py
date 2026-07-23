#!/usr/bin/env python3
"""Inject the choosing-tools dispatch protocol at session start and per prompt.

Hook entry points for the humblepowers plugin. All modes ship wired but inert
behind env gates, so the hooks cost nothing until the user opts in:

  --session-start   SessionStart. Prints the full protocol when
                    HUMBLEPOWERS_DISPATCH_INJECT=1 — unless the per-prompt gate
                    (below) is also on, in which case it stays silent: the
                    first-prompt full injection subsumes it.
  --prompt-submit   UserPromptSubmit. When HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=1,
                    injects with tiered cadence: full protocol on the first
                    prompt and on re-escalation (every HUMBLEPOWERS_DISPATCH_FULL_EVERY
                    prompts, default 10, or HUMBLEPOWERS_DISPATCH_FULL_MINUTES
                    minutes since the last full, default 30); a two-line micro
                    reminder otherwise. Slash-commands and short follow-ups get
                    nothing. A lexical router (router.py) appends a hint naming
                    at most two candidate skills; disable with
                    HUMBLEPOWERS_DISPATCH_ROUTER=0. Subagent completion notices
                    pass through UserPromptSubmit as synthetic prompts (see
                    SYNTHETIC_PREFIXES) and are skipped silently, same as a
                    slash command.
  --reset-state     SessionStart matcher compact|clear. Silently deletes the
                    session's cadence state so the next prompt re-escalates to
                    the full protocol (context was rebuilt).

Contract: a UserPromptSubmit hook that exits nonzero or times out BLOCKS the
user's prompt, so every path here fails open — any error means exit 0 with
empty stdout. No subprocesses, no network. ASCII-only output: hook stdout
encoding varies with the host console (cp1252 vs utf-8).

Telemetry: each --prompt-submit decision appends one JSONL line to the state
dir (tier fired, router hits) so cadence-vs-content A/Bs can be run against
real sessions later. Size-capped; purely local.

Stdlib only (Python 3.10+).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# ASCII-only: hook stdout encoding varies with the host console (cp1252 vs utf-8).
PROTOCOL = """\
<toolkit-dispatch>
At the start of substantive work (build / fix / migrate / refactor / review /
plan - not conversational turns or follow-ups inside an active task):
1. Name the task in one phrase.
2. Shortlist installed skills whose triggers match; scan the toolkit when unsure.
3. About to exercise a tool with a registered feedback intake? Read its newest
   report's Misses/Friction first - one Read; a recorded miss resurfaces at
   dispatch, not after the fact. No intake registered: skip.
4. Check candidates against positive and negative triggers; negative space
   ("not for X - that is Y") decides ties.
5. Load the best fit when its benefit clearly exceeds its context and anchoring
   cost. Process disciplines load before implementation skills.
6. Nothing clears the bar: proceed, and say so in one line.
7. A loaded skill that turns out wrong is set aside explicitly, not followed
   through.
8. After fixing a bug, leave a regression test that fails without the fix -
   cheap, durable insurance, even when the full TDD skill was not worth loading.
</toolkit-dispatch>"""

MICRO = (
    'Task start or direction change? Name the task, shortlist installed skills, '
    "load the best fit only past the benefit bar; 'nothing fits, proceeding "
    "directly' is a valid outcome."
)

MIN_WORDS = 4
MIN_CHARS = 15
DEFAULT_FULL_EVERY = 10
DEFAULT_FULL_MINUTES = 30
TELEMETRY_CAP_BYTES = 1_000_000

# Subagent completion is delivered to the parent session as a synthetic prompt
# that passes through UserPromptSubmit like a real one. No human authored it,
# so it must never count toward cadence or trigger injection.
SYNTHETIC_PREFIXES = ('[SYSTEM NOTIFICATION', '<task-notification>')


def _state_dir() -> Path:
    override = os.environ.get('HUMBLEPOWERS_DISPATCH_STATE_DIR')
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'humblepowers-dispatch'


def _state_path(session_id: str) -> Path:
    safe = ''.join(c for c in session_id if c.isalnum() or c in '-_') or 'unknown'
    # Cap the component length: a pathological session_id must not produce a
    # path that exceeds the OS component limit and fails the write.
    return _state_dir() / f'{safe[:64]}.json'


def _coerce_num(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _read_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(state, dict):
            raise ValueError
    except Exception:
        # Corrupt/absent state degrades to micro-tier cadence, never full-blast.
        return {'n': 0, 'last_full_n': 0, 'last_full_ts': time.time()}
    # A structurally valid dict can still carry wrong-typed fields (external
    # corruption, a future write regression). Coerce each numeric field so one
    # bad field degrades that field only, never the whole call.
    n = int(_coerce_num(state.get('n'), 0))
    # Clamp the re-escalation cursors to reality: values ahead of n / in the
    # future can never legitimately occur, and would otherwise starve the full
    # tier forever.
    last_full_n = min(int(_coerce_num(state.get('last_full_n'), 0)), n)
    last_full_ts = min(_coerce_num(state.get('last_full_ts'), 0.0), time.time())
    return {'n': n, 'last_full_n': last_full_n, 'last_full_ts': last_full_ts}


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state), encoding='utf-8')
    os.replace(tmp, path)


def _log_telemetry(session_id: str, record: dict) -> None:
    # Telemetry is best-effort by contract: it must never cost the prompt.
    with contextlib.suppress(Exception):
        log = _state_dir() / 'dispatch-log.ndjson'
        if log.exists() and log.stat().st_size > TELEMETRY_CAP_BYTES:
            return
        log.parent.mkdir(parents=True, exist_ok=True)
        record = {'ts': round(time.time()), 'session': session_id, **record}
        with log.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(record) + '\n')


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ''))
    except ValueError:
        return default
    # A non-positive cadence bound would invert the throttle into
    # full-protocol-on-every-prompt; treat it like a garbage value.
    return value if value > 0 else default


def _load_stdin_json() -> dict:
    # Read bytes and decode UTF-8 explicitly (utf-8-sig strips a BOM if present).
    # A hook's stdin encoding otherwise follows the host codepage, which would
    # mojibake a non-ASCII prompt on some interpreters; the payload is always
    # UTF-8 JSON, so decode it as such regardless of the console codepage.
    raw = sys.stdin.buffer.read()
    payload = json.loads(raw.decode('utf-8-sig'))
    return payload if isinstance(payload, dict) else {}


def _prompt_submit() -> int:
    if os.environ.get('HUMBLEPOWERS_DISPATCH_PROMPT_INJECT') != '1':
        return 0
    payload = _load_stdin_json()
    prompt = payload.get('prompt')
    prompt = prompt.strip() if isinstance(prompt, str) else ''
    if prompt.startswith(SYNTHETIC_PREFIXES):
        return 0  # subagent completion pass-through: no human turn occurred
    session_id = payload.get('session_id')
    session_id = session_id if isinstance(session_id, str) and session_id else 'unknown'

    if prompt.startswith('/'):
        return 0  # slash command: dispatch is already explicit
    if len(prompt) < MIN_CHARS or len(prompt.split()) < MIN_WORDS:
        return 0  # short follow-up: a dispatch check here is ceremony

    state_file = _state_path(session_id)
    state = _read_state(state_file)
    state['n'] = int(state.get('n', 0)) + 1
    n = state['n']

    full_every = _env_int('HUMBLEPOWERS_DISPATCH_FULL_EVERY', DEFAULT_FULL_EVERY)
    full_minutes = _env_int('HUMBLEPOWERS_DISPATCH_FULL_MINUTES', DEFAULT_FULL_MINUTES)
    stale = time.time() - float(state.get('last_full_ts', 0)) >= full_minutes * 60
    full = n == 1 or (n - int(state.get('last_full_n', 0))) >= full_every or stale
    if full:
        state['last_full_n'] = n
        state['last_full_ts'] = time.time()

    hint = ''
    hits: list[str] = []
    if os.environ.get('HUMBLEPOWERS_DISPATCH_ROUTER') != '0':
        try:
            import router

            matches = router.route(prompt, router.load_rules())
            hint = router.hint_line(matches)
            hits = [m['id'] for m in matches]
        except Exception:
            hint = ''  # router problems must never cost the prompt

    if full:
        body = PROTOCOL
        if hint:
            body = PROTOCOL.replace('</toolkit-dispatch>', hint + '\n</toolkit-dispatch>')
    else:
        lines = [MICRO]
        if hint:
            lines.append(hint)
        body = '<toolkit-dispatch>' + '\n'.join(lines) + '</toolkit-dispatch>'

    # Deliver the injection FIRST — it is the hook's entire purpose. ASCII-encode
    # so a codepage-limited stdout can never raise (which would lose the whole
    # payload). Persisting cadence state is bookkeeping: best-effort, and only
    # after a successful print, so a failed print never burns a cadence slot.
    print(body.encode('ascii', 'replace').decode('ascii'))
    with contextlib.suppress(Exception):
        _write_state(state_file, state)
    _log_telemetry(session_id, {'n': n, 'tier': 'full' if full else 'micro', 'hits': hits})
    return 0


def _reset_state() -> int:
    payload = _load_stdin_json()
    session_id = payload.get('session_id')
    session_id = session_id if isinstance(session_id, str) and session_id else 'unknown'
    with contextlib.suppress(Exception):
        _state_path(session_id).unlink(missing_ok=True)
    return 0


def _session_start() -> int:
    if os.environ.get('HUMBLEPOWERS_DISPATCH_PROMPT_INJECT') == '1':
        return 0  # the first-prompt full injection subsumes the session-start one
    if os.environ.get('HUMBLEPOWERS_DISPATCH_INJECT') != '1':
        return 0
    print(PROTOCOL)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Dispatch-protocol inject hooks.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--session-start', action='store_true', help='SessionStart entry point')
    mode.add_argument('--prompt-submit', action='store_true', help='UserPromptSubmit entry point')
    mode.add_argument(
        '--reset-state', action='store_true', help='SessionStart compact|clear entry point'
    )
    args = parser.parse_args(argv)

    try:
        if args.prompt_submit:
            return _prompt_submit()
        if args.reset_state:
            return _reset_state()
        if args.session_start:
            return _session_start()
        print(PROTOCOL)  # manual invocation
        return 0
    except Exception:
        return 0  # fail open: a hook error must never block the prompt


if __name__ == '__main__':
    sys.exit(main())

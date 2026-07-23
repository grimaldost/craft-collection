#!/usr/bin/env python3
"""Inject lexical dispatch-router hints on the user's prompt, plus a health reader.

Hook entry point for the humblepowers plugin, inert by default behind an env gate
so it costs nothing until the user opts in:

  --prompt-submit   UserPromptSubmit. When HUMBLEPOWERS_DISPATCH_PROMPT_INJECT=1,
                    runs the lexical router (router.py) over a substantive human
                    prompt and injects a short <toolkit-dispatch> block naming at
                    most two candidate skills, with the matched words shown.
                    Silent on no match. Slash-commands, short follow-ups, and
                    subagent-completion notices (SYNTHETIC_PREFIXES) get nothing.
                    Disable the router with HUMBLEPOWERS_DISPATCH_ROUTER=0 - with
                    nothing else to inject, that silences the hook entirely.

  --health          Human-invoked (not a hook). Summarizes the local telemetry
                    NDJSON: how many prompts were seen, how many got a hint, the
                    most-matched skills, and how long ago the last record landed.
                    The audit surface for an otherwise fail-open-silent hook.

Retired in 0.8.0 (see CHANGELOG): the session-start full-protocol inject
(HUMBLEPOWERS_DISPATCH_INJECT), the per-prompt tiered cadence (full/micro tiers,
HUMBLEPOWERS_DISPATCH_FULL_EVERY / _FULL_MINUTES), and the compact|clear cadence
reset. A 2026-07 content A/B measured the generic 8-step protocol block as no
better than no injection, and wall-clock / prompt-count cadence was never
validated; only the concrete-candidate router hint survives.

Contract: a UserPromptSubmit hook that exits nonzero or times out BLOCKS the
user's prompt, so every path fails open - any error means exit 0 with empty
stdout. No subprocesses, no network. ASCII-only output: hook stdout encoding
varies with the host console (cp1252 vs utf-8).

Telemetry: each --prompt-submit decision appends one JSONL line to the state dir
(router hits, whether a hint was injected). Size-capped; purely local; read it
back with --health.

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
from collections import Counter
from pathlib import Path

MIN_WORDS = 4
MIN_CHARS = 15
TELEMETRY_CAP_BYTES = 1_000_000
LOG_NAME = 'dispatch-log.ndjson'

# Subagent completion is delivered to the parent session as a synthetic prompt
# that passes through UserPromptSubmit like a real one. No human authored it, so
# it must never trigger injection or telemetry.
SYNTHETIC_PREFIXES = ('[SYSTEM NOTIFICATION', '<task-notification>')


def _state_dir() -> Path:
    override = os.environ.get('HUMBLEPOWERS_DISPATCH_STATE_DIR')
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'humblepowers-dispatch'


def _log_path() -> Path:
    return _state_dir() / LOG_NAME


def _ascii(text: str) -> str:
    """Collapse to ASCII for output; hook stdout may be a codepage-limited console."""
    return text.encode('ascii', 'replace').decode('ascii')


def _log_telemetry(session_id: str, record: dict) -> None:
    # Telemetry is best-effort by contract: it must never cost the prompt.
    with contextlib.suppress(Exception):
        log = _log_path()
        if log.exists() and log.stat().st_size > TELEMETRY_CAP_BYTES:
            return
        log.parent.mkdir(parents=True, exist_ok=True)
        record = {'ts': round(time.time()), 'session': session_id, **record}
        with log.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(record) + '\n')


def _load_stdin_json() -> dict:
    # The payload is always UTF-8 JSON; decode it as such regardless of the console
    # codepage (utf-8-sig strips a BOM if present), so a non-ASCII prompt never
    # mojibakes on an interpreter whose stdin follows the host codepage.
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
        return 0  # short follow-up: a dispatch hint here is ceremony

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

    # Deliver the injection FIRST - it is the hook's entire purpose. ASCII-encode
    # so a codepage-limited stdout can never raise (which would lose the whole
    # payload). Telemetry is bookkeeping: best-effort, and only after the print,
    # so a failed print never suppresses a record that claims a hint shipped.
    if hint:
        print(_ascii('<toolkit-dispatch>\n' + hint + '\n</toolkit-dispatch>'))
    _log_telemetry(session_id, {'router_hits': hits, 'injected': bool(hint)})
    return 0


def _health() -> int:
    log = _log_path()
    if not log.exists():
        print(_ascii(f'dispatch telemetry: no records yet ({log})'))
        return 0
    total = 0
    injected = 0
    skills: Counter[str] = Counter()
    last_ts = 0.0
    with contextlib.suppress(Exception):
        for raw in log.read_text(encoding='utf-8').splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue  # a corrupt line must not abort the whole read
            if not isinstance(rec, dict):
                continue
            total += 1
            if rec.get('injected'):
                injected += 1
            for sid in rec.get('router_hits') or []:
                if isinstance(sid, str):
                    skills[sid] += 1
            ts = rec.get('ts')
            if isinstance(ts, (int, float)):
                last_ts = max(last_ts, float(ts))
    pct = round(100 * injected / total) if total else 0
    lines = [
        f'dispatch telemetry ({log})',
        f'prompts logged: {total}',
        f'hint injected:  {injected} ({pct}%)',
    ]
    if last_ts:
        age_min = max(0, round((time.time() - last_ts) / 60))
        lines.append(f'last record:    {age_min} min ago')
    if skills:
        lines.append('top matched skills:')
        for sid, count in skills.most_common(5):
            lines.append(f'  {count:>4}x {sid}')
    print(_ascii('\n'.join(lines)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Dispatch-router prompt hook + health reader.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prompt-submit', action='store_true', help='UserPromptSubmit entry point')
    mode.add_argument('--health', action='store_true', help='summarize local dispatch telemetry')
    args = parser.parse_args(argv)

    try:
        if args.prompt_submit:
            return _prompt_submit()
        if args.health:
            return _health()
        parser.print_help()
        return 0
    except Exception:
        return 0  # fail open: a hook error must never block the prompt


if __name__ == '__main__':
    sys.exit(main())

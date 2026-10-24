#!/usr/bin/env python3
"""Local firing counter for the engineering-discipline hooks.

Each hook's `main()` appends one JSON line to `hook-log.ndjson` when it acts:
`uv_enforce` on a block (`ts`, `hook`, `verdict`, `matched`, `session`),
`ruff_format` when it started a format run (`ts`, `hook`, `files`, `session`).
No command text and no file contents are written. Nothing is sent anywhere.

The hooks write to `ENGINEERING_DISCIPLINE_STATE_DIR` when set, else
`CLAUDE_PLUGIN_DATA` (the per-plugin data directory Claude Code gives a plugin's
hooks), else `<system temp>/engineering-discipline`. Appending stops once the
file reaches CAP_BYTES. Logging is best-effort: any error is swallowed, so it
never changes a hook's verdict or exit code.

The reader uses that same directory when either variable is set. From a plain
terminal, where neither is, it reads every
`<claude config dir>/plugins/data/engineering-discipline-*/hook-log.ndjson`
that exists (one per marketplace the plugin was installed from; the config dir
is `CLAUDE_CONFIG_DIR` when set, else `~/.claude`), and falls back to the temp
directory only when there is none.

    python hook_log.py            # firings per hook
    python hook_log.py --count    # the same

Stdlib-only.
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

STATE_DIR_ENV = 'ENGINEERING_DISCIPLINE_STATE_DIR'
LOG_NAME = 'hook-log.ndjson'
CAP_BYTES = 1_000_000


def state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    data = os.environ.get('CLAUDE_PLUGIN_DATA')
    if data:
        return Path(data)
    return Path(tempfile.gettempdir()) / 'engineering-discipline'


def log_path() -> Path:
    return state_dir() / LOG_NAME


def plugin_data_logs() -> list[Path]:
    """Logs Claude Code's per-plugin data directories hold, sorted by path.

    Under Claude Code the hooks see `CLAUDE_PLUGIN_DATA`; a terminal does not, so
    the reader looks where Claude Code puts those directories.
    """
    config = os.environ.get('CLAUDE_CONFIG_DIR')
    try:
        base = Path(config) if config else Path.home() / '.claude'
        return sorted((base / 'plugins' / 'data').glob(f'engineering-discipline-*/{LOG_NAME}'))
    except (OSError, RuntimeError):
        return []


def read_paths() -> list[Path]:
    """Logs the reader prints: the hooks' directory when a variable names one,
    else the plugin data logs that exist, else the temp directory fallback."""
    if not (os.environ.get(STATE_DIR_ENV) or os.environ.get('CLAUDE_PLUGIN_DATA')):
        found = [p for p in plugin_data_logs() if p.is_file()]
        if found:
            return found
    return [log_path()]


def append(record: dict) -> None:
    """Append `record` with a UTC timestamp. Never raises."""
    with contextlib.suppress(Exception):
        path = log_path()
        if path.exists() and path.stat().st_size >= CAP_BYTES:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **record})
        with path.open('a', encoding='utf-8') as fh:
            fh.write(line + '\n')


def counts(path: Path | None = None) -> dict[str, int]:
    """Firings per hook in a log (default: the hooks' log); unreadable or malformed lines are skipped."""
    out: dict[str, int] = {}
    with contextlib.suppress(OSError):
        for raw in (path or log_path()).read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get('hook'), str):
                out[rec['hook']] = out.get(rec['hook'], 0) + 1
    return dict(sorted(out.items()))


def _say(text: str) -> None:
    print(text.encode('ascii', 'backslashreplace').decode('ascii'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Print how often each engineering-discipline hook fired.'
    )
    parser.add_argument('--count', action='store_true', help='firings per hook (the default)')
    parser.parse_args(argv)
    for path in read_paths():
        found = counts(path)
        _say(f'log: {path}')
        if not found:
            _say('no firings logged yet')
        for hook, n in found.items():
            _say(f'{hook}: {n}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

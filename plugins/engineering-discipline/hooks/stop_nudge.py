#!/usr/bin/env python3
"""Optional Stop hook: nudge to run the data pre-shipping checklist.

INERT by default — emits a nudge only if DATAENG_CHECKLIST_NUDGE=1 AND the
session's git diff touched files that look like data-pipeline code.

The nudge is delivered the ONLY way a Stop hook can reach Claude: a
`{"decision":"block","reason":<message>}` JSON object on STDOUT (exit 0). A bare
stderr print on exit 0 — the previous behavior — is discarded by the Stop-hook
contract and never reaches Claude. To avoid looping the Stop hook forever, we
stay silent when the incoming payload has `stop_hook_active: true` (i.e. this
Stop was itself triggered by our earlier block). Stdlib only.
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from typing import IO

# Default "looks like pipeline code" globs; override via DATAENG_PIPELINE_GLOBS.
DEFAULT_GLOBS = ('*.sql', '*dbt*', '*pipeline*', '*etl*', 'models/*', '*/models/*')


def should_nudge(changed_files: list[str], globs: tuple[str, ...] = DEFAULT_GLOBS) -> bool:
    """True if any changed path matches a pipeline-ish glob."""
    return any(fnmatch.fnmatch(f, g) for f in changed_files for g in globs)


def nudge_message() -> str:
    """The reminder printed when pipeline files changed.

    Names `freshness_check.py` — the runnable cursor-advance checker — explicitly,
    so an incremental load gets a concrete next step, not just the generic list."""
    return (
        'Data-pipeline files changed - run the pre-shipping checklist '
        '(schema, row count, group cardinality, null rates, sums, replay) '
        'before declaring done. For an incremental load, run freshness_check.py '
        'to assert the cursor actually advanced.'
    )


def decide(
    payload: dict,
    changed_files: list[str],
    globs: tuple[str, ...] | None,
    enabled: bool,
) -> str | None:
    """Decide the Stop-hook stdout, or None for silence.

    Returns the JSON string to print on STDOUT — a `{"decision":"block",...}`
    object carrying the nudge — or None when the hook should stay inert. Silent
    when disabled, when no pipeline file changed, or when `stop_hook_active` is
    set on the payload (guards against re-triggering ourselves in a loop).
    """
    if not enabled:
        return None
    if payload.get('stop_hook_active'):
        return None
    if not should_nudge(changed_files, globs or DEFAULT_GLOBS):
        return None
    return json.dumps({'decision': 'block', 'reason': nudge_message()})


def _changed_files() -> list[str]:
    try:
        out = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD'],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return []
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def _load_payload(stdin: IO[str]) -> dict:
    """Read and parse the Stop payload; an empty or malformed body -> {}."""
    try:
        raw = stdin.read()
    except OSError:
        return {}
    try:
        obj = json.loads(raw) if raw and raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def main(
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    enabled: bool | None = None,
    changed_files: list[str] | None = None,
) -> int:
    """Run the Stop hook. Streams and inputs are injectable for tests; production
    defaults read stdin, write stdout, and shell out to git."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    if enabled is None:
        enabled = os.environ.get('DATAENG_CHECKLIST_NUDGE') == '1'
    payload = _load_payload(stdin)
    if changed_files is None:
        changed_files = _changed_files()
    env_globs = tuple(g for g in os.environ.get('DATAENG_PIPELINE_GLOBS', '').split(',') if g)
    out = decide(payload, changed_files, env_globs or DEFAULT_GLOBS, enabled)
    if out is not None:
        stdout.write(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())

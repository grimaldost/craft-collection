#!/usr/bin/env python3
"""Commit-time launcher for the experiment-rigor gates, for CONSUMER projects.

experiment-discipline's central claim is that every load-bearing rule is a gate
rather than a line of prose, and both gates lived only in this repository's own
`.pre-commit-config.yaml` behind path patterns that cannot match anywhere else.
This file is the seam that exports them: pre-commit's `language: script` runs it
straight out of the hook clone with the CONSUMER repo as cwd, so it resolves the
bundled `validate.py` / `render.py` against its own location -- never the cwd --
and invokes them exactly the way this repository's own hooks do:

    uv run --no-project --with pyyaml -- python <bundled script> [--check] <files>

PyYAML is the gates' sole non-stdlib dependency (the record is nested YAML);
`uv run --with pyyaml` supplies it without touching the consumer's environment.
With no uv on PATH the launcher falls back to the current interpreter when
PyYAML is importable there, and otherwise exits 1 naming both routes -- a gate
that cannot run is a red gate, never a quiet green one.

    experiment_rigor_gate.py --validate <record.yaml> [...]
    experiment_rigor_gate.py --render-check <record.yaml> [...]

Stdlib only: this file has to import with nothing installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = (
    ROOT / 'plugins' / 'experiment-discipline' / 'skills' / 'experiment-rigor' / 'scripts'
)
# mode flag -> (bundled script, extra args before the file list)
MODES = {
    '--validate': ('validate.py', []),
    '--render-check': ('render.py', ['--check']),
}
USAGE = 'usage: experiment_rigor_gate.py --validate|--render-check <record.yaml> [...]'


def interpreter_argv(target: Path) -> list[str] | None:
    """The command prefix that runs `target` with PyYAML available, or None when
    neither route is open. uv first: it is the invocation this repository's own
    hooks use and it leaves the consumer's environment alone."""
    if shutil.which('uv'):
        return ['uv', 'run', '--no-project', '--with', 'pyyaml', '--', 'python', str(target)]
    try:
        import yaml  # noqa: F401
    except ImportError:
        return None
    return [sys.executable, str(target)]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in MODES:
        print(USAGE)
        return 2
    mode, files = argv[0], argv[1:]
    if not files:
        return 0  # nothing staged matched the pattern; not a failure
    name, extra = MODES[mode]
    target = SKILL_SCRIPTS / name
    if not target.is_file():
        print(f'experiment-rigor gate: bundled {name} is missing at {target}')
        return 1
    prefix = interpreter_argv(target)
    if prefix is None:
        print(
            'experiment-rigor gate: cannot run. It needs PyYAML, which it gets from '
            '`uv run --with pyyaml` (uv not found on PATH) or from the current '
            'interpreter (PyYAML not importable there). Install uv, or `pip install '
            'pyyaml` into the interpreter pre-commit uses.'
        )
        return 1
    return subprocess.run([*prefix, *extra, *files], check=False).returncode  # noqa: S603


if __name__ == '__main__':
    sys.exit(main())

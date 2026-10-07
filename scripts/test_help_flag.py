"""`--help` is a request for usage on every runnable script, never a file path.

Seven scripts took `--help` for something else: four evaluate-skill drivers
loaded their config before looking at the arguments (a traceback when the
config is not beside them), and three checks read the first argument as a path
(`check_commit_msg.py`, the commit-msg hook's file; `check_gate_claims.py`'s
repository root; `check_red_exception.py`'s skill directory) and reported the
flag as a missing file or ran a scan rooted at a directory named `--help`.

Contract under test, per script, run as the hooks and CI run it (a fresh
interpreter, a working directory that is not the repository):
- `--help` and `-h` exit 0, print usage on stdout, write nothing to stderr and
  never a traceback;
- the flag does no work: nothing is read, scanned or written.

The evaluate-skill drivers are tested at their installed location under
`plugins/`, the copy a user runs; `evals/harness/test_scripts_in_sync.py` keeps
the harness copies identical.

Stdlib-runnable: `python test_help_flag.py`.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVAL_SCRIPTS = REPO / 'plugins' / 'session-workflow' / 'skills' / 'evaluate-skill' / 'scripts'

SCRIPTS = [
    EVAL_SCRIPTS / 'aggregate.py',
    EVAL_SCRIPTS / 'grade_tasks.py',
    EVAL_SCRIPTS / 'run_all.py',
    EVAL_SCRIPTS / 'run_triggers.py',
    REPO
    / 'plugins'
    / 'humblepowers'
    / 'skills'
    / 'test-driven-development'
    / 'scripts'
    / 'check_red_exception.py',
    REPO / 'scripts' / 'check_commit_msg.py',
    REPO / 'scripts' / 'check_gate_claims.py',
]


def _run(script: Path, flag: str, cwd: str):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(script), flag],
        capture_output=True,
        encoding='utf-8',
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )


def test_help_prints_usage_and_exits_zero_on_every_script():
    with tempfile.TemporaryDirectory() as d:
        for script in SCRIPTS:
            for flag in ('--help', '-h'):
                proc = _run(script, flag, d)
                where = f'{script.name} {flag}'
                assert proc.returncode == 0, (
                    f'{where}: exit {proc.returncode}: {proc.stderr[-300:]}'
                )
                assert proc.stdout.strip(), f'{where}: printed no usage'
                assert proc.stderr == '', f'{where}: wrote to stderr: {proc.stderr[-300:]}'
                assert 'Traceback' not in proc.stdout, where
                assert list(Path(d).iterdir()) == [], f'{where}: wrote into the working directory'


if __name__ == '__main__':
    test_help_prints_usage_and_exits_zero_on_every_script()
    print('ok: --help prints usage and exits 0 on every script')

#!/usr/bin/env python3
"""Self-contained checks for scripts/experiment_rigor_gate.py (no pytest required).

The launcher is the seam that exports experiment-discipline's two gates to
consumer repositories, so what it has to prove is that it finds the bundled
scripts from its OWN location and that a real record actually reaches them --
in both directions. The red half runs the gate over a deliberately corrupted
copy of the founding record: a launcher that resolves nothing would exit 0 on
it just as happily as on a clean one, and would look identical in a green log.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import experiment_rigor_gate as gate  # noqa: E402

EXAMPLE = ROOT / 'plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2'
GATE = ROOT / 'scripts' / 'experiment_rigor_gate.py'


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(GATE), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
    )


def test_bundled_scripts_resolve_from_the_launchers_own_location() -> None:
    for name, _ in gate.MODES.values():
        assert (gate.SKILL_SCRIPTS / name).is_file(), f'{name} not found at {gate.SKILL_SCRIPTS}'


def test_usage_and_empty_file_list() -> None:
    assert gate.main([]) == 2
    assert gate.main(['--not-a-mode']) == 2
    # pre-commit passes an empty list when nothing staged matched: not a failure.
    assert gate.main(['--validate']) == 0


def test_both_modes_pass_on_the_founding_record() -> None:
    for mode in ('--validate', '--render-check'):
        proc = _run(mode, str(EXAMPLE / 'record.yaml'))
        assert proc.returncode == 0, mode + '\n' + proc.stdout + proc.stderr


def test_render_check_reddens_on_a_drifted_report() -> None:
    """The gate is not evidence until it has been made to fail on purpose against
    real input. Corrupt a copy of the founding pair and confirm a non-zero exit;
    a launcher that silently resolved nothing would pass this too if it were
    allowed to, which is the failure this test exists to rule out."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / 'rg-2x2'
        work.mkdir()
        for name in ('record.yaml', 'report.md'):
            shutil.copy2(EXAMPLE / name, work / name)
        report = work / 'report.md'
        # Restore by inverse edit, never by checkout: this is a copy precisely so
        # the mutation can never touch the tracked fixture.
        report.write_text(
            report.read_text(encoding='utf-8').replace('```yaml', '```text', 1), encoding='utf-8'
        )
        proc = _run('--render-check', str(work / 'record.yaml'))
    assert proc.returncode != 0, 'the drift gate passed over a report with no typed block'
    assert proc.stdout.strip() or proc.stderr.strip(), 'the gate failed without saying why'


def main() -> int:
    test_bundled_scripts_resolve_from_the_launchers_own_location()
    test_usage_and_empty_file_list()
    test_both_modes_pass_on_the_founding_record()
    test_render_check_reddens_on_a_drifted_report()
    print('ok: experiment_rigor_gate launcher checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())

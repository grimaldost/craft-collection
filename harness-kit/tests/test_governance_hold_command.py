#!/usr/bin/env python3
"""Checks of the shell command the governance cell `watcher-off-holds` scripts.

Contract under test (`rewrite_without_plugin` of `conformance/test_config_governance.py`, given
a reload log):
- the command rewrites the configuration with an empty `plugins` list, then restores its
  original bytes;
- it restores no sooner than the hold it is given;
- it restores once opencode's log holds a `config.updated` line written after the rewrite,
  so a reload slowed by load still reads the rewritten configuration;
- a `config.updated` line already in the log before the rewrite does not end the wait, and
  without a new one it restores at its cap.

The bounds asserted are lower bounds only (a loaded machine makes them easier to meet), and
the wait for the log line is bounded by a cap far above any time the test allows.

Runs the command with PowerShell 7 (`pwsh`), the shell opencode runs; prints `skip:` without it.
Stdlib-runnable: `python test_governance_hold_command.py`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'conformance'))

from kit_fixtures import run_module  # noqa: E402
from test_config_governance import RELOAD_LINE, rewrite_without_plugin  # noqa: E402

PWSH = shutil.which('pwsh')
ORIGINAL = '{\n  "plugins": ["C:/Users/me/kit/plugin"],\n  "model": "stub/stub-model"\n}\n'
REWRITTEN_MARK = '"plugins": []'
LOG_LINE = 'timestamp=2026-01-01T00:00:00.000Z level=INFO message=event event.type={kind}\n'


class Watch:
    """Polls the configuration file: when it first reads rewritten and when restored."""

    def __init__(self, config: Path, on_rewritten=None) -> None:
        self.config = config
        self.on_rewritten = on_rewritten
        self.rewritten_at: float | None = None
        self.restored_at: float | None = None
        self.still_rewritten_after_signal: bool | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _read(self) -> str:
        try:
            return self.config.read_text(encoding='utf-8')
        except OSError:
            return ''

    def _run(self) -> None:
        while not self._stop.is_set():
            text = self._read()
            now = time.monotonic()
            if self.rewritten_at is None and REWRITTEN_MARK in text:
                self.rewritten_at = now
                if self.on_rewritten is not None:
                    self.on_rewritten()
                    self.still_rewritten_after_signal = REWRITTEN_MARK in self._read()
            elif self.rewritten_at is not None and self.restored_at is None and text == ORIGINAL:
                self.restored_at = now
            time.sleep(0.005)

    def __enter__(self) -> Watch:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


def _setup(folder: Path, log_text: str | None) -> tuple[Path, Path]:
    config = folder / 'conf' / 'opencode.jsonc'
    config.parent.mkdir(parents=True)
    config.write_bytes(ORIGINAL.encode('utf-8'))
    log = folder / 'log' / 'opencode.log'
    if log_text is not None:
        log.parent.mkdir(parents=True)
        log.write_text(log_text, encoding='utf-8')
    return config, log


def _run(command: str, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [PWSH, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', command],
        capture_output=True,
        text=True,
        encoding='utf-8',
        timeout=timeout,
        check=False,
    )


def test_the_reload_line_is_the_config_updated_event():
    assert RELOAD_LINE == 'event.type=config.updated'


def test_it_restores_once_the_log_shows_a_reload_after_the_rewrite():
    with tempfile.TemporaryDirectory() as tmp:
        config, log = _setup(Path(tmp), LOG_LINE.format(kind='provider.updated'))

        def reload() -> None:
            with open(log, 'a', encoding='utf-8') as out:
                out.write(LOG_LINE.format(kind='config.updated'))

        # A cap far above the subprocess timeout: only the log line can end the wait in time.
        command = rewrite_without_plugin(config, 300, reload_log=log, cap_ms=600_000)
        with Watch(config, on_rewritten=reload) as watch:
            proc = _run(command, timeout=120)
            time.sleep(0.05)
        assert proc.returncode == 0, proc.stderr
        assert config.read_bytes() == ORIGINAL.encode('utf-8')
        assert watch.rewritten_at is not None, 'the configuration was never seen rewritten'
        assert watch.still_rewritten_after_signal is True
        assert watch.restored_at is not None
        assert watch.restored_at - watch.rewritten_at >= 0.25, (
            watch.restored_at - watch.rewritten_at
        )


def test_a_reload_line_from_before_the_rewrite_does_not_end_the_wait():
    with tempfile.TemporaryDirectory() as tmp:
        config, log = _setup(Path(tmp), LOG_LINE.format(kind='config.updated'))
        command = rewrite_without_plugin(config, 300, reload_log=log, cap_ms=3000)
        with Watch(config) as watch:
            proc = _run(command, timeout=120)
            time.sleep(0.05)
        assert proc.returncode == 0, proc.stderr
        assert config.read_bytes() == ORIGINAL.encode('utf-8')
        assert watch.rewritten_at is not None and watch.restored_at is not None
        assert watch.restored_at - watch.rewritten_at >= 2.5, watch.restored_at - watch.rewritten_at


def test_without_a_log_it_restores_at_its_cap():
    with tempfile.TemporaryDirectory() as tmp:
        config, log = _setup(Path(tmp), None)
        command = rewrite_without_plugin(config, 300, reload_log=log, cap_ms=2000)
        with Watch(config) as watch:
            proc = _run(command, timeout=120)
            time.sleep(0.05)
        assert proc.returncode == 0, proc.stderr
        assert config.read_bytes() == ORIGINAL.encode('utf-8')
        assert watch.rewritten_at is not None and watch.restored_at is not None
        assert watch.restored_at - watch.rewritten_at >= 1.5, watch.restored_at - watch.rewritten_at


if __name__ == '__main__':
    if PWSH is None:
        print('skip: pwsh is not installed')
        sys.exit(0)
    run_module(globals(), 'the command the hold cell scripts')

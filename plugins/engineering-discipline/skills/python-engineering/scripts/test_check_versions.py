"""Tests for check_versions pure logic (no network).

Runnable with pytest OR directly: `python test_check_versions.py`.
"""

from __future__ import annotations

import io
import json
import tempfile
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

from check_versions import fetch_pypi_version, is_behind, load_precommit, load_tools, main

STACK = """\
[meta]
last_reviewed = "2026-06-04"

[tools.ruff]
pypi = "ruff"
pinned_min = "0.15"
category = "lint-format"

[tools.pytest]
pypi = "pytest"
pinned_min = "8.0"
category = "testing"

[precommit]
"ruff-pre-commit" = "v0.15.7"
"""


def _write_stack(d: Path) -> Path:
    p = d / 'stack.toml'
    p.write_text(STACK, encoding='utf-8')
    return p


def test_load_tools():
    with tempfile.TemporaryDirectory() as d:
        tools = load_tools(_write_stack(Path(d)))
        assert tools == {'ruff': '0.15', 'pytest': '8.0'}


def test_load_precommit():
    with tempfile.TemporaryDirectory() as d:
        assert load_precommit(_write_stack(Path(d))) == {'ruff-pre-commit': 'v0.15.7'}


def test_is_behind():
    assert is_behind('0.15', '0.18') is True
    assert is_behind('0.15', '0.15') is False
    assert is_behind('0.15', '0.14') is False
    assert is_behind('1.0', '2.0') is True
    assert is_behind('0.15', '0.15.7') is False  # 0.x patch -> churn, not behind
    assert is_behind('1.0', '1.0.5') is False  # stable patch -> not behind
    # 0.0.x (true 0ver, e.g. ty): the patch IS the release axis -> must be visible
    assert is_behind('0.0.1', '0.0.43') is True
    assert is_behind('0.0.1', '0.0.1') is False
    assert is_behind('0.0.1', '0.1.0') is True


def test_fetch_failure_is_not_reported_as_current(monkeypatch):
    # A network failure must NOT silently read as behind=False ('current'). The
    # returned dict carries a non-ok status so the caller can tell 'unknown' from
    # 'up to date'. (Uses pytest's monkeypatch when run under pytest.)
    def _boom(*a, **k):
        raise urllib.error.URLError('network down')

    monkeypatch.setattr(urllib.request, 'urlopen', _boom)
    r = fetch_pypi_version('ruff', '0.15')
    assert r['status'] != 'ok'
    assert r['latest'] is None


def _run_main_json_with_urlopen_raising(exc: Exception) -> tuple[dict, int]:
    """Run `main --json --stack <tmp>` with urlopen patched to raise; return
    (parsed_json, exit_code). No pytest dependency, so the __main__ block can call it."""
    original = urllib.request.urlopen

    def _boom(*a, **k):
        raise exc

    with tempfile.TemporaryDirectory() as d:
        stack = _write_stack(Path(d))
        urllib.request.urlopen = _boom  # type: ignore[assignment]
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(['--json', '--stack', str(stack)])
        finally:
            urllib.request.urlopen = original  # type: ignore[assignment]
    return json.loads(buf.getvalue()), code


def test_total_fetch_failure_yields_errors_and_exit_2():
    # The fail-open bug: every fetch fails, yet behind_count=0 read as 'no drift'
    # and exit 0. Fixed: errors count is non-zero and the exit code is 2 (red),
    # so a caller never mistakes a dead network for a clean stack.
    obj, code = _run_main_json_with_urlopen_raising(urllib.error.URLError('down'))
    assert obj['errors'] == 2  # both tools in the fixture stack failed
    assert obj['behind_count'] == 0
    assert code == 2


if __name__ == '__main__':
    test_load_tools()
    test_load_precommit()
    test_is_behind()
    # fetch-failure unit test: emulate monkeypatch by swapping urlopen directly.
    _orig = urllib.request.urlopen

    class _MP:
        def setattr(self, obj, name, val):
            setattr(obj, name, val)

    try:
        test_fetch_failure_is_not_reported_as_current(_MP())
    finally:
        urllib.request.urlopen = _orig
    test_total_fetch_failure_yields_errors_and_exit_2()
    print('ok: all check_versions tests passed')

#!/usr/bin/env python3
"""Self-contained checks for scripts/subprocess_encoding_lint.py (no pytest required).

Contract under test:
- a subprocess call that opens text mode (text=True, universal_newlines=True, or
  errors= alone) without naming encoding= is a finding, and main() exits 1;
- naming encoding=, or keeping bytes mode (text=False), is clean;
- run, check_output, Popen, call and check_call are all covered, by attribute
  or bare name;
- a call that spreads **kwargs is skipped (the encoding may be in the spread);
- test_*.py modules are out of scope;
- the per-file count ratchets against the baseline, and --write-baseline
  resets it.

The red proof is `test_text_mode_without_encoding_exits_1`: a planted tree with
one text=True call and no encoding= makes main() return 1.

Stdlib-runnable: `python test_subprocess_encoding_lint.py`.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import subprocess_encoding_lint as lint

ROOT = Path(__file__).resolve().parent.parent


def _tree(base: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
    return base


def _run_main(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = lint.main(argv)
    return rc, out.getvalue()


def _scan(files: dict[str, str]) -> dict[str, list[str]]:
    with tempfile.TemporaryDirectory() as td:
        return lint.scan(_tree(Path(td), files))


def test_text_mode_without_encoding_exits_1():
    src = "import subprocess\nproc = subprocess.run(['tool'], capture_output=True, text=True)\n"
    with tempfile.TemporaryDirectory() as td:
        base = _tree(Path(td), {'scripts/tool.py': src})
        rc, out = _run_main(['--root', str(base)])
    assert rc == 1, out
    assert 'scripts/tool.py' in out and ':2:' in out, out
    assert out.isascii(), out


def test_explicit_encoding_is_clean():
    src = (
        'import subprocess\n'
        "subprocess.run(['tool'], capture_output=True, text=True, encoding='utf-8')\n"
        "subprocess.run(['tool'], universal_newlines=True, encoding='utf-8', errors='replace')\n"
    )
    assert _scan({'scripts/tool.py': src}) == {}


def test_bytes_mode_is_clean():
    src = (
        'import subprocess\n'
        "subprocess.run(['tool'], capture_output=True)\n"
        "subprocess.run(['tool'], capture_output=True, text=False)\n"
        "subprocess.check_output(['tool'], universal_newlines=False)\n"
    )
    assert _scan({'scripts/tool.py': src}) == {}


def test_every_subprocess_entry_point_is_flagged():
    src = (
        'import subprocess\n'
        'from subprocess import run\n'
        "subprocess.check_output(['tool'], text=True)\n"
        "subprocess.Popen(['tool'], stdout=subprocess.PIPE, text=True)\n"
        "subprocess.call(['tool'], universal_newlines=True)\n"
        "subprocess.check_call(['tool'], text=True)\n"
        "run(['tool'], text=True)\n"
        'flag = True\n'
        "subprocess.run(['tool'], text=flag)\n"
    )
    current = _scan({'plugins/p/skills/s/scripts/tool.py': src})
    findings = current.get('plugins/p/skills/s/scripts/tool.py', [])
    assert [f.split(':', 1)[0] for f in findings] == ['3', '4', '5', '6', '7', '9'], findings


def test_errors_alone_opens_text_mode():
    # errors= without text= still opens the pipes in text mode, with the locale codec.
    src = "import subprocess\nsubprocess.run(['tool'], capture_output=True, errors='replace')\n"
    current = _scan({'evals/harness/tool.py': src})
    assert len(current.get('evals/harness/tool.py', [])) == 1, current


def test_kwargs_spread_is_skipped():
    src = (
        "import subprocess\nkw = {'encoding': 'utf-8'}\nsubprocess.run(['tool'], text=True, **kw)\n"
    )
    assert _scan({'scripts/tool.py': src}) == {}


def test_test_modules_are_ignored():
    src = "import subprocess\nsubprocess.run(['tool'], capture_output=True, text=True)\n"
    assert _scan({'scripts/test_tool.py': src, 'docs/tool.py': src}) == {}


def test_ratchet_semantics():
    src = "import subprocess\nsubprocess.run(['a'], text=True)\nsubprocess.run(['b'], text=True)\n"
    current = _scan({'scripts/old.py': src})
    assert lint.check(current, {'scripts/old.py': 2}) == [], 'at baseline must pass'
    errs = lint.check(current, {'scripts/old.py': 1})
    assert errs and 'baseline 1' in errs[0], errs
    assert lint.check(current, {}) != [], 'a new file starts at zero'


def test_write_baseline_then_pass():
    src = "import subprocess\nsubprocess.run(['a'], text=True)\n"
    with tempfile.TemporaryDirectory() as td:
        base = _tree(Path(td), {'scripts/old.py': src})
        rc, out = _run_main(['--root', str(base), '--write-baseline'])
        assert rc == 0, out
        data = json.loads((base / 'scripts' / lint.BASELINE_NAME).read_text(encoding='utf-8'))
        assert data == {'scripts/old.py': 1}, data
        rc2, out2 = _run_main(['--root', str(base)])
        assert rc2 == 0, out2
        grown = src + "subprocess.run(['b'], text=True)\n"
        (base / 'scripts' / 'old.py').write_text(grown, encoding='utf-8')
        rc3, out3 = _run_main(['--root', str(base)])
        assert rc3 == 1 and 'old.py' in out3, out3


def test_real_repo_is_at_or_under_baseline():
    # The gate CI enforces through run_tests.py (the pre-commit hook runs the same
    # check): the tracked tree must not have grown past the baseline.
    rc, out = _run_main(['--root', str(ROOT)])
    assert rc == 0, out


if __name__ == '__main__':
    test_text_mode_without_encoding_exits_1()
    test_explicit_encoding_is_clean()
    test_bytes_mode_is_clean()
    test_every_subprocess_entry_point_is_flagged()
    test_errors_alone_opens_text_mode()
    test_kwargs_spread_is_skipped()
    test_test_modules_are_ignored()
    test_ratchet_semantics()
    test_write_baseline_then_pass()
    test_real_repo_is_at_or_under_baseline()
    print('ok: subprocess_encoding_lint')

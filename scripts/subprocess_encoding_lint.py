#!/usr/bin/env python3
"""Ratchet subprocess calls that open text mode without naming an encoding.

The failure class this gates: `subprocess.run(..., text=True)` with no
`encoding=` decodes the child's output with the locale codec, which is cp1252 on
a Windows console. A child that emits UTF-8 then comes back mojibaked, or the
decode raises on a byte cp1252 leaves undefined. The shipped instance was
experiment-discipline 0.3.2: `validate.py` read a frozen record back through
`git show` in text mode, the locale codec decoded git's UTF-8 output, an em
dash came back as three characters, and ER-PREREG reported drift on a record
nobody had changed. Nothing in a UTF-8 CI runner can see this class; it only
shows on the machine that runs the code.

The rule, read from the AST: a call whose callee (attribute or bare name) is
run, check_output, Popen, call or check_call opens text mode when it passes
`text=` or `universal_newlines=` with any value other than a falsy constant,
or `errors=` (which alone also opens text mode). Such a call must also pass
`encoding=`. A call that spreads `**kwargs` is skipped, because the encoding
may arrive in the spread and the AST cannot tell. Name the codec the child
actually emits: UTF-8 for git; `locale.getpreferredencoding(False)` for a piped
Python child, which writes in that codec unless told otherwise. Add `errors=`
when one bad byte must not crash the caller.

Ratchet semantics (same shape as ascii_runtime_lint.py, whose file enumeration
this reuses): `subprocess_encoding_baseline.json` records the per-file finding
count; a file may not GROW past its baseline, and new files start at zero.
Fixing instances then running with `--write-baseline` ratchets the ceiling
down.

Run:   uv run --no-project -- python scripts/subprocess_encoding_lint.py
       ... --write-baseline   # after fixing, to ratchet down
Scope: git-tracked *.py under plugins/, scripts/, evals/ (rglob fallback when
       git is unavailable); test_*.py excluded.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

from ascii_runtime_lint import iter_target_files

ROOT = Path(__file__).resolve().parent.parent
BASELINE_NAME = 'subprocess_encoding_baseline.json'
ENTRY_POINTS = frozenset({'run', 'check_output', 'Popen', 'call', 'check_call'})
TEXT_MODE_KEYWORDS = ('text', 'universal_newlines')


def _callee_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _opens_text_mode(keywords: dict[str, ast.expr]) -> bool:
    for name in TEXT_MODE_KEYWORDS:
        value = keywords.get(name)
        if value is None:
            continue
        if isinstance(value, ast.Constant) and not value.value:
            continue
        return True
    return 'errors' in keywords


def lint_file(path: Path) -> list[str]:
    """Findings as 'line:col: <message>' strings; unparsable files are skipped
    (ruff owns syntax)."""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        return []
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _callee_name(node)
        if callee not in ENTRY_POINTS:
            continue
        if any(kw.arg is None for kw in node.keywords):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        if 'encoding' in keywords or not _opens_text_mode(keywords):
            continue
        findings.append(
            f'{node.lineno}:{node.col_offset}: {callee}() opens text mode without encoding='
        )
    return findings


def scan(root: Path) -> dict[str, list[str]]:
    """{repo-relative posix path: findings} for every target file with any."""
    out: dict[str, list[str]] = {}
    for f in iter_target_files(root):
        findings = lint_file(f)
        if findings:
            out[f.relative_to(root).as_posix()] = findings
    return out


def load_baseline(root: Path) -> dict[str, int]:
    p = root / 'scripts' / BASELINE_NAME
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return {k: int(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def check(current: dict[str, list[str]], baseline: dict[str, int]) -> list[str]:
    """Error lines for files whose finding count grew past their baseline."""
    errors: list[str] = []
    for rel, findings in sorted(current.items()):
        allowed = baseline.get(rel, 0)
        if len(findings) > allowed:
            errors.append(f'{rel}: {len(findings)} text-mode call(s) > baseline {allowed}')
            errors.extend(f'  {rel}:{line}' for line in findings)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='tree to scan (tests use this)')
    parser.add_argument(
        '--write-baseline',
        action='store_true',
        help='regenerate the baseline from the current tree (after fixing, to ratchet down)',
    )
    args = parser.parse_args(argv)
    current = scan(args.root)
    if args.write_baseline:
        counts = {rel: len(f) for rel, f in sorted(current.items())}
        target = args.root / 'scripts' / BASELINE_NAME
        target.write_text(json.dumps(counts, indent=2) + '\n', encoding='utf-8')
        print(f'wrote {target} ({sum(counts.values())} findings across {len(counts)} files)')
        return 0
    errors = check(current, load_baseline(args.root))
    if errors:
        print('SUBPROCESS-ENCODING LINT FAILED (new findings over baseline):')
        for line in errors:
            print(f'  {line}')
        print(
            "Pass encoding= with the codec the child emits: 'utf-8' for git, "
            'locale.getpreferredencoding(False) for a piped Python child. '
            "Add errors='replace' when one bad byte must not crash the caller."
        )
        return 1
    total = sum(len(f) for f in current.values())
    print(f'subprocess-encoding lint ok ({total} baselined finding(s) remain to burn down).')
    return 0


if __name__ == '__main__':
    sys.exit(main())

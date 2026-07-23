#!/usr/bin/env python3
"""Ratchet non-ASCII out of runtime-reachable string literals in bundled scripts.

The recurring failure class this gates (three shipped instances: llm-signature
0.16.1, evaluate-skill 0.16.2, dispatch hook 0.7.1): a non-ASCII char in a
string that reaches a console at runtime mojibakes or raises under Windows
cp1252 (even cp1252-encodable chars break when a cp1252-encoding child meets a
utf-8-decoding parent), and fail-open wrappers turn that into silent output
loss. Docstrings are exempt (never encoded to a console); comments are not AST
nodes; test modules are excluded (non-ASCII test data is deliberate); bytes
literals are excluded.

Ratchet semantics (same shape as word_budget.py): `ascii_lint_baseline.json`
records the per-file finding count at adoption; a file may not GROW past its
baseline, and new files start at zero. Fixing instances then running with
`--write-baseline` ratchets the ceiling down. The burn-down of the adoption
baseline is tracked work, not silent acceptance.

Fix findings per-line: replace the char or move the text into a docstring.
Never round-trip a file through `untokenize` - it reflows every line and turns
a one-char fix into an unreviewable diff. A deliberate non-console literal
(e.g. content written to a UTF-8 file) takes a `# ascii-ok` comment on the
string's first line.

Run:   uv run --no-project -- python scripts/ascii_runtime_lint.py
       ... --write-baseline   # after fixing, to ratchet down
Scope: git-tracked *.py under plugins/, scripts/, evals/ (rglob fallback when
       git is unavailable); test_*.py excluded.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ('plugins', 'scripts', 'evals')
SUPPRESS_MARK = '# ascii-ok'
BASELINE_NAME = 'ascii_lint_baseline.json'


def iter_target_files(root: Path) -> list[Path]:
    """Git-tracked .py files under the scan dirs (local gitignored tooling must
    not gate the repo); plain rglob when git is unavailable (fixture trees)."""
    tracked = _git_tracked(root)
    out: list[Path] = []
    for d in SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for f in sorted(base.rglob('*.py')):
            if f.name.startswith('test_'):
                continue
            if tracked is not None and f.resolve() not in tracked:
                continue
            out.append(f)
    return out


def _git_tracked(root: Path) -> set[Path] | None:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv
            ['git', '-C', str(root), 'ls-files', '-z', '--', *SCAN_DIRS],  # noqa: S607 - PATH git
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return None
        return {
            (root / p.decode('utf-8', errors='replace')).resolve()
            for p in proc.stdout.split(b'\0')
            if p
        }
    except (OSError, subprocess.SubprocessError):
        return None


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id()s of the Constant nodes sitting in docstring position."""
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                exempt.add(id(body[0].value))
    return exempt


def lint_file(path: Path) -> list[str]:
    """Findings as 'relpath:line:col: <message>' lines; unparsable files are
    skipped (ruff owns syntax)."""
    try:
        source = path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    exempt = _docstring_nodes(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in exempt or node.value.isascii():
            continue
        first_line = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ''
        if SUPPRESS_MARK in first_line:
            continue
        bad = next(ch for ch in node.value if not ch.isascii())
        findings.append(
            f'{node.lineno}:{node.col_offset}: non-ASCII {bad!r} (U+{ord(bad):04X}) '
            'in a runtime string literal'
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
            errors.append(
                f'{rel}: {len(findings)} non-ASCII runtime literal(s) > baseline {allowed}'
            )
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
        print('ASCII-RUNTIME LINT FAILED (new findings over baseline):')
        for line in errors:
            print(f'  {line}')
        print(
            'Fix per-line (replace the char or move the text into a docstring); '
            'never rewrite via untokenize - it reflows the whole file. '
            f'A deliberate non-console literal takes `{SUPPRESS_MARK}` on its first line.'
        )
        return 1
    total = sum(len(f) for f in current.values())
    print(f'ascii-runtime lint ok ({total} baselined finding(s) remain to burn down).')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Register linter: reject salience-inflating prose in skill markdown.

Enforces the humblepowers skill-authoring doctrine mechanically: descriptions
and bodies compete on calibrated fit, not volume. Denied patterns are the
imperative-obedience phrases and importance banners that buy attention instead
of earning it; a run of three or more consecutive all-caps words is treated as
a banner unless every word is a known acronym. Fenced code blocks and inline
code are exempt.

Usage:
    python scripts/lint_register.py                  # lint plugins/humblepowers
    python scripts/lint_register.py --all-plugins    # lint every plugin's markdown
    python scripts/lint_register.py PATH [PATH ...]  # lint specific files/dirs

Exit codes: 0 clean, 1 findings, 2 usage error. Stdlib only (Python 3.10+).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCOPE = ROOT / 'plugins' / 'humblepowers'
DOCTRINE = 'plugins/humblepowers/skills/skill-authoring/SKILL.md (Register rules)'

DENY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'EXTREMELY[-_ ]IMPORTANT'), 'importance banner'),
    (re.compile(r'\bYOU MUST\b'), 'imperative-obedience phrase'),
    (re.compile(r'\bMUST USE\b'), 'imperative-obedience phrase'),
    (re.compile(r'DO NOT HAVE A CHOICE'), 'imperative-obedience phrase'),
    (
        re.compile(r'\bnon[- ]?negotiable\b|\bnot negotiable\b', re.IGNORECASE),
        'non-negotiable framing',
    ),
    (re.compile(r'\bABSOLUTELY\b'), 'all-caps intensifier'),
    (re.compile(r'\bNO EXCEPTIONS?\b'), 'all-caps absolute'),
    (re.compile(r'\bIRON LAW\b'), 'importance banner'),
]

# Tokens that legitimately appear in caps and never count toward a banner run.
ACRONYMS = {
    'AI',
    'API',
    'AST',
    'CC',
    'CI',
    'CLI',
    'CSS',
    'CSV',
    'DAG',
    'DB',
    'EV',
    'FAQ',
    'GIF',
    'HTML',
    'HTTP',
    'HTTPS',
    'ID',
    'IDE',
    'IO',
    'JS',
    'JSON',
    'LF',
    'LLM',
    'MCP',
    'MD',
    'OK',
    'OS',
    'PDF',
    'PR',
    'PRS',
    'README',
    'SDK',
    'SKILL',
    'SQL',
    'TDD',
    'TOML',
    'TS',
    'TTL',
    'UI',
    'URL',
    'UV',
    'UX',
    'YAML',
}
CAPS_WORD = re.compile(r'^[A-Z][A-Z0-9-]+$')
INLINE_CODE = re.compile(r'`[^`]*`')
FENCE = re.compile(r'^\s*(```|~~~)')
CAPS_RUN_THRESHOLD = 3


def _caps_run_findings(line: str) -> list[str]:
    """Return the banner-like all-caps runs in a prose line."""
    findings: list[str] = []
    run: list[str] = []
    for raw in line.split():
        token = raw.strip('*_.,:;!?()[]{}"\'—-')
        if token and CAPS_WORD.match(token) and token not in ACRONYMS:
            run.append(token)
            continue
        if len(run) >= CAPS_RUN_THRESHOLD:
            findings.append(' '.join(run))
        run = []
    if len(run) >= CAPS_RUN_THRESHOLD:
        findings.append(' '.join(run))
    return findings


def lint_file(path: Path) -> list[str]:
    """Lint one markdown file; return findings as 'path:line: label: excerpt'."""
    findings: list[str] = []
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        prose = INLINE_CODE.sub('', line)
        for pattern, label in DENY:
            match = pattern.search(prose)
            if match:
                findings.append(f'{path}:{lineno}: {label}: {match.group(0)!r}')
        for run in _caps_run_findings(prose):
            findings.append(f'{path}:{lineno}: all-caps banner run: {run!r}')
    return findings


def lint_paths(paths: list[Path]) -> list[str]:
    """Lint every .md file under the given files/directories."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob('*.md')))
        elif p.suffix == '.md':
            files.append(p)
    findings: list[str] = []
    for f in files:
        findings.extend(lint_file(f))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Register linter for skill markdown.')
    parser.add_argument('paths', nargs='*', type=Path, help='files or directories to lint')
    parser.add_argument(
        '--all-plugins',
        action='store_true',
        help='lint every plugin, not just humblepowers',
    )
    args = parser.parse_args(argv)

    if args.paths and args.all_plugins:
        print('pass either explicit paths or --all-plugins, not both', file=sys.stderr)
        return 2
    scope = args.paths or [ROOT / 'plugins' if args.all_plugins else DEFAULT_SCOPE]

    missing = [p for p in scope if not p.exists()]
    if missing:
        print(f'path(s) not found: {", ".join(map(str, missing))}', file=sys.stderr)
        return 2

    findings = lint_paths(scope)
    for finding in findings:
        print(finding)
    if findings:
        print(f'---\n{len(findings)} register finding(s). Doctrine: {DOCTRINE}')
        return 1
    print('register lint: clean')
    return 0


if __name__ == '__main__':
    sys.exit(main())

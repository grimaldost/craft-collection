#!/usr/bin/env python3
"""Register linter: reject salience-inflating prose in skill markdown.

Enforces the humblepowers skill-authoring doctrine mechanically: descriptions
and bodies compete on calibrated fit, not volume. Denied patterns are the
imperative-obedience phrases and importance banners that buy attention instead
of earning it; a run of three or more consecutive all-caps words is treated as
a banner unless every word is a known acronym. Fenced code blocks and inline
code are exempt.

Scope is the whole marketplace by default: every skill `description` competes in
one shared selection pool, so a coercive description distorts selection no matter
which plugin ships it. One rule is narrower — `non-negotiable` is flagged only in
frontmatter (the description, the selection surface, where it is always a salience
buy). In body prose it is legitimate domain terminology ("the four non-negotiables
of a data contract"), so it is not flagged there; genuine body coercion is still
caught by the always-on patterns.

Usage:
    python scripts/lint_register.py                  # lint every plugin's markdown
    python scripts/lint_register.py PATH [PATH ...]  # lint specific files/dirs

Exit codes: 0 clean, 1 findings, 2 usage error. Stdlib only (Python 3.10+).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCOPE = ROOT / 'plugins'
DOCTRINE = 'plugins/humblepowers/skills/skill-authoring/SKILL.md (Register rules)'

# Applied everywhere (frontmatter and body prose): these phrasings are coercive
# whether they sit in a description (buying selection) or a body (buying compliance).
DENY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'EXTREMELY[-_ ]IMPORTANT'), 'importance banner'),
    (re.compile(r'\bYOU MUST\b'), 'imperative-obedience phrase'),
    (re.compile(r'\bMUST USE\b'), 'imperative-obedience phrase'),
    (re.compile(r'DO NOT HAVE A CHOICE'), 'imperative-obedience phrase'),
    (re.compile(r'\bABSOLUTELY\b'), 'all-caps intensifier'),
    (re.compile(r'\bNO EXCEPTIONS?\b'), 'all-caps absolute'),
    (re.compile(r'\bIRON LAW\b'), 'importance banner'),
    # Salience/priority phrasings that read the same in any case — a skill that has
    # to claim precedence or demand invocation is compensating for a description that
    # does not earn selection on fit.
    (re.compile(r'\btakes priority over\b', re.IGNORECASE), 'priority claim'),
    (
        re.compile(r'\b(?:always|must) use this skill\b', re.IGNORECASE),
        'imperative-obedience phrase',
    ),
    (re.compile(r'\byou do not have a choice\b', re.IGNORECASE), 'imperative-obedience phrase'),
]

# Applied only inside YAML frontmatter (the description — the selection surface).
# `non-negotiable` is the one denied pattern with a legitimate composed meaning
# ("this property cannot be compromised"), which data-engineering-discipline uses
# as a term of art in its body prose. In a description it is a salience buy; in a
# body it is domain vocabulary, so it is scoped here rather than banned outright.
DENY_FRONTMATTER: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r'\bnon[- ]?negotiable\b|\bnot negotiable\b', re.IGNORECASE),
        'non-negotiable framing',
    ),
]

# Single-word importance banners at the start of a line (optionally behind list/quote
# markers or */_ emphasis of any weight), terminated by punctuation or end-of-line.
# `IMPORTANT: …`, `IMPORTANT —`, `_CRITICAL_:` and a bare `**MANDATORY**` all buy
# salience the same way an all-caps run does, below the 3-word run threshold. A
# terminator is required so a capitalized word merely starting a sentence
# ('CRITICAL failures need…') does not match.
BANNER_WORDS = ('IMPORTANT', 'CRITICAL', 'MANDATORY', 'FORBIDDEN', 'COMPULSORY', 'PROHIBITED')
BANNER_LINE = re.compile(
    r'^\s*(?:[-*>#]+\s*)*(?:[*_]{1,3})?('
    + '|'.join(BANNER_WORDS)
    # terminators: :!,.; em dash (U+2014), en dash (U+2013), hyphen, end-of-line
    + r')(?:[*_]{1,3})?\s*(?:[:!,.;\u2014\u2013-]|$)'
)

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
    'LFT',  # Brazilian treasury bond (Letra Financeira do Tesouro)
    'LLM',
    'LTN',  # Brazilian treasury bond (Letra do Tesouro Nacional)
    'MCP',
    'MD',
    'NTN-B',  # Brazilian treasury bond (Nota do Tesouro Nacional série B)
    'NTN-F',  # Brazilian treasury bond (série F)
    'OK',
    'OS',
    'PDF',
    'PR',
    'PRS',
    'SDK',
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
FENCE = re.compile(r'^\s*(`{3,}|~{3,})')
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


def _scan_prose(
    path: Path, lineno: int, prose: str, deny: list[tuple[re.Pattern[str], str]]
) -> list[str]:
    """Check one already-code-stripped prose line against banners, the given deny
    list, and caps runs. `deny` varies by surface (body vs frontmatter)."""
    out: list[str] = []
    banner = BANNER_LINE.match(prose)
    if banner:
        out.append(f'{path}:{lineno}: importance banner: {banner.group(1)!r}')
    for pattern, label in deny:
        match = pattern.search(prose)
        if match:
            out.append(f'{path}:{lineno}: {label}: {match.group(0)!r}')
    for run in _caps_run_findings(prose):
        out.append(f'{path}:{lineno}: all-caps banner run: {run!r}')
    return out


def lint_file(path: Path) -> list[str]:
    """Lint one markdown file; return findings as 'path:line: label: excerpt'.

    Frontmatter lines (between the leading `---` fences) get DENY + DENY_FRONTMATTER
    — the `non-negotiable` rule bites only here. Body lines get DENY only, and are
    fence-aware (fenced and inline code are exempt)."""
    findings: list[str] = []
    fence: tuple[str, int] | None = None  # (marker char, run length) of the OPEN fence
    lines = path.read_text(encoding='utf-8').splitlines()
    in_frontmatter = bool(lines) and lines[0].strip() == '---'
    for lineno, line in enumerate(lines, start=1):
        if in_frontmatter:
            if lineno == 1:
                continue  # opening delimiter
            if line.strip() == '---':
                in_frontmatter = False  # closing delimiter
                continue
            prose = INLINE_CODE.sub('', line)
            findings.extend(_scan_prose(path, lineno, prose, DENY + DENY_FRONTMATTER))
            continue
        m = FENCE.match(line)
        if m:
            marker = m.group(1)
            char, length = marker[0], len(marker)
            if fence is None:
                fence = (char, length)  # open a fence
            elif char == fence[0] and length >= fence[1]:
                fence = None  # CommonMark: only a same-char run >= the opener closes it
            # a different marker char, or a shorter run, is content inside the block
            continue
        if fence is not None:
            continue
        prose = INLINE_CODE.sub('', line)
        findings.extend(_scan_prose(path, lineno, prose, DENY))
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
        help='deprecated no-op — every plugin is linted by default; kept for compatibility',
    )
    args = parser.parse_args(argv)

    scope = args.paths or [DEFAULT_SCOPE]

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

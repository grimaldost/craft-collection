#!/usr/bin/env python3
"""Machine-generated LLM provenance signature (llm-signature).

Renders the two provenance git trailers — the exact model that is writing and
the versioned agent tool stack it ran on — from live sources, so a signature is
never typed from memory:

    Assisted-By: claude-sonnet-5
    Agent-Stack: claude-code@2.1.0; session-workflow@0.15.0 (craft-collection)

The model comes from the session transcript (the last main-loop assistant
message), never from self-report; the stack comes from `claude plugin list`
(enabled plugins only) plus the harness version from `claude --version`.

Usage:
    python render_signature.py                       # resolve everything, print the trailer block
    python render_signature.py --model <id>          # explicit model override
    python render_signature.py --json                # machine-readable
    python render_signature.py --apply <msg-file>    # git prepare-commit-msg mode: scrub
                                                     # AI co-author boilerplate, refresh trailers

`--apply` never fails a commit: any error leaves the message usable and exits 0.
It also removes vendor-identity AI co-author lines (`Co-Authored-By: … <…@anthropic.com>`
and claude+noreply forms) and flush-left "Generated with … Claude" badge lines —
the signature replaces both; the model is listed in `Assisted-By`, never as a
commit co-author. Human co-authors (including humans named Claude with their own
email) are never touched, nor is anything indented, quoted, or after a scissors
line.

Transcript auto-discovery is best-effort by design: candidates are bounded to a
freshness window and verified against the cwd recorded inside the transcript;
when no candidate verifies, the script refuses to sign rather than guess. Two
concurrent sessions in the same directory can still race — pass `--transcript`
(or `--model`) when determinism matters.

Stdlib only (Python 3.10+). Full grammar and semantics: ../references/spec.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TRAILER_MODEL = 'Assisted-By'
TRAILER_STACK = 'Agent-Stack'

# Only transcripts touched within this window can sign: a live session's
# transcript is written turn by turn, while a days-old file is a PREVIOUS
# session whose model must never be attributed to this one.
FRESHNESS_WINDOW_S = 30 * 60

# Scrub patterns are anchored to the vendor's identity, not to the word
# "claude": a co-author line must carry an anthropic.com address or a
# claude+noreply bot address to match, so a human co-author named Claude with
# their own email survives. The badge must BE the line (flush-left), so body
# prose that merely mentions "generated with Claude" survives.
_AI_COAUTHOR = re.compile(
    r'^co-authored-by:.*<[^<>]*@anthropic\.com>'
    r'|^co-authored-by:.*\bclaude\b.*<[^<>]*noreply[^<>]*>',
    re.IGNORECASE,
)
_AI_BADGE = re.compile(r'^(?:\U0001f916\s*)?generated with .*\bclaude\b', re.IGNORECASE)
_OWN_TRAILERS = (TRAILER_MODEL.lower() + ':', TRAILER_STACK.lower() + ':')
_TRAILER_LINE = re.compile(r'^[A-Za-z][A-Za-z0-9-]*:\s+\S')
_VERSION = re.compile(r'\d+(?:\.\d+)+\S*')


# --- model resolution ---------------------------------------------------------


def _scan_transcript(path: Path) -> tuple[str | None, str | None]:
    """(model, cwd) of the LAST main-loop assistant message in a Claude Code
    transcript — the model writing (and orchestrating) right now, which is the
    one the signature holds responsible, plus the working directory the entry
    records (used to verify a discovered transcript really belongs to this
    project). Sidechain (subagent) messages are skipped: a delegate's model is
    not the orchestrator. `<synthetic>` placeholders (API-error stubs) are
    skipped. (None, None) on any read error."""
    model = cwd = None
    try:
        with path.open(encoding='utf-8', errors='replace') as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get('type') != 'assistant':
                    continue
                if entry.get('isSidechain'):
                    continue
                msg = entry.get('message')
                mid = msg.get('model') if isinstance(msg, dict) else None
                if isinstance(mid, str) and mid and not mid.startswith('<'):
                    model = mid
                    ecwd = entry.get('cwd')
                    cwd = ecwd if isinstance(ecwd, str) and ecwd else cwd
    except OSError:
        return None, None
    return model, cwd


def model_from_transcript(path: Path) -> str | None:
    return _scan_transcript(path)[0]


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def _cwd_related(recorded: str, cwd: Path) -> bool:
    """True when the transcript's recorded cwd is this directory, an ancestor
    of it, or a descendant of it — exact path comparison, so lossy-munging
    collisions (`my.repo` vs `my-repo`) cannot pass verification."""
    try:
        t = Path(recorded).resolve()
    except OSError:
        return False
    return t == cwd or t in cwd.parents or cwd in t.parents


def find_transcript(cwd: Path, projects_root: Path, now: float | None = None) -> Path | None:
    """Newest verifiable transcript for the session running in `cwd`. Claude
    Code keys `~/.claude/projects/<munged-cwd>/` by the session cwd with
    separators mapped to `-`; that munging is lossy, so a directory-name match
    only nominates candidates. A candidate signs only if it is FRESH (touched
    within `FRESHNESS_WINDOW_S`) and the cwd recorded inside it relates to this
    one (equal/ancestor/descendant, exact paths). Nothing verifiable -> None:
    refusing to sign beats guessing. Candidate dirs cover this cwd, its parents
    (the script may run from a subdirectory of the session root), and its
    descendants (a git hook at the repo root, session started deeper)."""
    now = time.time() if now is None else now
    try:
        dirs = [d for d in projects_root.iterdir() if d.is_dir()]
    except OSError:
        return None
    cwd = cwd.resolve()
    wants = {_norm(str(c)) for c in (cwd, *cwd.parents)}
    child_prefix = _norm(str(cwd)) + '-'
    candidates: list[tuple[float, Path]] = []
    for d in dirs:
        n = _norm(d.name)
        if n not in wants and not n.startswith(child_prefix):
            continue
        try:
            for p in d.glob('*.jsonl'):
                mtime = p.stat().st_mtime
                if now - mtime <= FRESHNESS_WINDOW_S:
                    candidates.append((mtime, p))
        except OSError:
            continue
    for _, p in sorted(candidates, reverse=True):
        model, recorded = _scan_transcript(p)
        if model is None:
            continue
        if recorded is None or _cwd_related(recorded, cwd):
            return p
    return None


def resolve_model(args: argparse.Namespace) -> str | None:
    """Precedence: --model, --transcript, then transcript auto-discovery.
    Auto-discovery is gated on a live agent session (CLAUDECODE in the
    environment, or an explicit --projects-root) AND on the freshness/cwd
    verification in `find_transcript` — both must hold before a discovered
    transcript signs."""
    if args.model:
        return args.model
    if args.transcript:
        return model_from_transcript(Path(args.transcript))
    if os.environ.get('CLAUDECODE') or args.projects_root:
        root = (
            Path(args.projects_root) if args.projects_root else Path.home() / '.claude' / 'projects'
        )
        found = find_transcript(Path.cwd(), root)
        if found:
            return model_from_transcript(found)
    return None


# --- stack resolution ---------------------------------------------------------


def plugins_from_json(data: object) -> list[dict]:
    """Pure parser for `claude plugin list --json`: id is `plugin@marketplace`;
    version/enabled ride alongside. Tolerates shape drift (scan_toolkit.py
    precedent); disabled plugins are dropped."""
    plugins = data.get('plugins') if isinstance(data, dict) else data
    if not isinstance(plugins, list):
        return []
    out: list[dict] = []
    for p in plugins:
        if not isinstance(p, dict) or p.get('enabled') is False:
            continue
        ident = str(p.get('name') or p.get('id') or '')
        if not ident:
            continue
        name, _, marketplace = ident.partition('@')
        ver = str(p.get('version') or '').strip()
        out.append({'name': name, 'version': ver or None, 'marketplace': marketplace or None})
    return out


def _run_cli(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv, capture_output=True, text=True, timeout=20
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not (proc.stdout or '').strip():
        return None
    return proc.stdout


def harness_version() -> str | None:
    out = _run_cli(['claude', '--version'])  # PATH-resolved by _run_cli
    if not out:
        return None
    m = _VERSION.search(out)
    return m.group(0) if m else None


def collect_stack(only: set[str] | None = None, include_harness: bool = True) -> list[str]:
    """`Agent-Stack` items, harness first then plugins by name. Each item is
    `name@version (marketplace)` — the marketplace label is the lookup key
    (resolved via `claude plugin marketplace list` or the adopting repo's
    resolution table), so no URL ever lands in a commit. Selective by design:
    enabled plugins only, narrowable further with `only`. This is
    environment-at-commit provenance — what was installed and enabled — not a
    claim that every listed plugin fired."""
    items: list[str] = []
    if include_harness:
        hv = harness_version()
        if hv:
            items.append(f'claude-code@{hv}')
    out = _run_cli(['claude', 'plugin', 'list', '--json'])
    plugins: list[dict] = []
    if out:
        try:
            plugins = plugins_from_json(json.loads(out))
        except ValueError:
            plugins = []
    for p in sorted(plugins, key=lambda x: x['name']):
        if only and p['name'] not in only:
            continue
        item = p['name'] + (f'@{p["version"]}' if p['version'] else '')
        if p['marketplace']:
            item += f' ({p["marketplace"]})'
        items.append(item)
    return items


# --- rendering & apply --------------------------------------------------------


def render_block(model: str, stack: list[str]) -> str:
    lines = [f'{TRAILER_MODEL}: {model}']
    if stack:
        lines.append(f'{TRAILER_STACK}: ' + '; '.join(stack))
    return '\n'.join(lines)


def _git_comment_char() -> str:
    out = _run_cli(['git', 'config', 'core.commentChar'])  # PATH-resolved by _run_cli
    cc = (out or '').strip()
    return cc if len(cc) == 1 else '#'


def apply_to_message(text: str, block: str | None, comment_char: str = '#') -> str:
    """Rewrite a commit-message file: drop vendor AI boilerplate and stale
    Assisted-By/Agent-Stack lines, then insert the fresh block after the last
    content line. Re-running replaces, never duplicates. Git-shaped input is
    honored: everything from a scissors line (`# --- >8 ---`, as `git commit
    --verbose` emits) on is frozen untouched and the block lands before it;
    `comment_char` is the configured `core.commentChar`, so a comment-only
    message under any comment char is left unsigned; scrubs match flush-left
    lines only (indented/quoted examples survive); the block joins an existing
    final paragraph only when EVERY line of that paragraph is trailer-shaped —
    git parses trailers per whole final paragraph, and gluing onto prose would
    hide the trailers from `git interpret-trailers`. CRLF endings are
    preserved. `block=None` scrubs only. Pure."""
    crlf = '\r\n' in text
    work = text.replace('\r\n', '\n') if crlf else text
    lines = work.split('\n')

    cut = len(lines)  # freeze everything from the scissors line on
    for i, ln in enumerate(lines):
        if ln.startswith(comment_char) and '>8' in ln:
            cut = i
            break
    head, frozen = lines[:cut], lines[cut:]

    kept: list[str] = []
    for ln in head:
        if _AI_COAUTHOR.match(ln) or _AI_BADGE.match(ln):
            continue
        if ln.lower().startswith(_OWN_TRAILERS):
            continue
        kept.append(ln)
    while kept and not kept[-1]:  # trailing blanks carry nothing and would accrete per run
        kept.pop()

    def is_content(ln: str) -> bool:
        return bool(ln.strip()) and not ln.startswith(comment_char)

    first = last = None
    for i, ln in enumerate(kept):
        if is_content(ln):
            first = i if first is None else first
            last = i

    if block is None or last is None:
        out_lines = kept + frozen
    else:
        para_start = last
        while para_start > 0 and is_content(kept[para_start - 1]):
            para_start -= 1
        para = kept[para_start : last + 1]
        glue = para_start != first and all(_TRAILER_LINE.match(ln) for ln in para)
        out_lines = kept[: last + 1] + ([] if glue else ['']) + block.split('\n') + kept[last + 1 :]
        out_lines += frozen

    out = '\n'.join(out_lines)
    if out and not out.endswith('\n'):
        out += '\n'
    return out.replace('\n', '\r\n') if crlf else out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description='Render the machine-generated LLM provenance signature.'
    )
    ap.add_argument('--model', help='explicit model id (skips transcript resolution)')
    ap.add_argument('--transcript', help='resolve the model from this Claude Code transcript')
    ap.add_argument(
        '--plugin',
        action='append',
        help='restrict Agent-Stack to the named plugin(s); repeatable',
    )
    ap.add_argument('--no-harness', action='store_true', help='omit claude-code@version')
    ap.add_argument('--json', action='store_true', help='machine-readable output')
    ap.add_argument(
        '--apply',
        metavar='FILE',
        help='rewrite a commit-message file in place (prepare-commit-msg mode; always exits 0)',
    )
    ap.add_argument(
        '--projects-root',
        help='override ~/.claude/projects for transcript auto-discovery (mainly for tests)',
    )
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if args.apply:
        # A signing failure must never block a commit: scrub what can be
        # scrubbed, sign only when the model resolved, and exit 0 regardless —
        # including on non-UTF-8 messages (surrogateescape round-trips the raw
        # bytes) and on any unexpected error. The stack CLIs are consulted only
        # when a signature will actually be written, so unsigned (human)
        # commits pay nothing.
        try:
            model = resolve_model(args)
            block = None
            if model:
                stack = collect_stack(
                    only=set(args.plugin) if args.plugin else None,
                    include_harness=not args.no_harness,
                )
                block = render_block(model, stack)
            path = Path(args.apply)
            text = path.read_bytes().decode('utf-8', errors='surrogateescape')
            new = apply_to_message(text, block, comment_char=_git_comment_char())
            if new != text:
                path.write_bytes(new.encode('utf-8', errors='surrogateescape'))
        except Exception:  # noqa: S110 - hook mode: never abort the commit, whatever broke
            pass
        return 0

    model = resolve_model(args)
    if not model:
        print(
            'llm-signature: could not resolve the writing model - pass --model or --transcript '
            '(auto-discovery needs a live Claude Code session and a fresh, cwd-matching '
            'transcript)',
            file=sys.stderr,
        )
        return 1
    stack = collect_stack(
        only=set(args.plugin) if args.plugin else None, include_harness=not args.no_harness
    )
    if args.json:
        print(
            json.dumps(
                {'model': model, 'stack': stack, 'trailers': render_block(model, stack)},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(render_block(model, stack))
    return 0


if __name__ == '__main__':
    sys.exit(main())

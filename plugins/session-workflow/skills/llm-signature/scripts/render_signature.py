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
    python render_signature.py --model claude-sonnet-5  # explicit model override
    python render_signature.py --json                # machine-readable
    python render_signature.py --apply <msg-file>    # git prepare-commit-msg mode: scrub
                                                     # AI co-author boilerplate, refresh trailers

`--apply` never fails a commit: on any error it leaves the message usable and
exits 0. It also removes `Co-Authored-By:` lines naming Claude/Anthropic and
"Generated with Claude Code" badges — the signature replaces both; the model
is listed in `Assisted-By`, never as a commit co-author.

Stdlib only (Python 3.10+). Full grammar and semantics: ../references/spec.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TRAILER_MODEL = 'Assisted-By'
TRAILER_STACK = 'Agent-Stack'

# Co-author lines naming the agent vendor are boilerplate the signature replaces.
# Human co-authors never match: the pattern requires claude/anthropic in the line.
_AI_COAUTHOR = re.compile(r'^\s*co-authored-by:.*\b(claude|anthropic)\b', re.IGNORECASE)
_AI_BADGE = re.compile(r'generated with .*\bclaude\b|🤖 generated with', re.IGNORECASE)
_OWN_TRAILERS = (TRAILER_MODEL.lower() + ':', TRAILER_STACK.lower() + ':')
_TRAILER_LINE = re.compile(r'^[A-Za-z][A-Za-z0-9-]*:\s+\S')
_VERSION = re.compile(r'\d+(?:\.\d+)+\S*')


# --- model resolution ---------------------------------------------------------


def model_from_transcript(path: Path) -> str | None:
    """The model of the LAST main-loop assistant message in a Claude Code
    transcript — the model writing (and orchestrating) right now, which is the
    one the signature holds responsible. Sidechain (subagent) messages are
    skipped: a delegate's model is not the orchestrator. `<synthetic>`
    placeholders (API-error stubs) are skipped. None on any read error."""
    model = None
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
    except OSError:
        return None
    return model


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def find_transcript(cwd: Path, projects_root: Path) -> Path | None:
    """Newest transcript for the session running in `cwd`. Claude Code keys
    `~/.claude/projects/<munged-cwd>/` by the session cwd with separators
    mapped to `-`; both sides are normalized the same way so the exact munging
    rule never has to be guessed. Climbs to parent dirs because the script may
    run from a subdirectory of the session root. None when nothing matches."""
    try:
        dirs = [d for d in projects_root.iterdir() if d.is_dir()]
    except OSError:
        return None
    for candidate in (cwd.resolve(), *cwd.resolve().parents):
        want = _norm(str(candidate))
        for d in dirs:
            if _norm(d.name) != want:
                continue
            try:
                files = sorted(d.glob('*.jsonl'), key=lambda p: p.stat().st_mtime)
            except OSError:
                continue
            if files:
                return files[-1]
    return None


def resolve_model(args: argparse.Namespace) -> str | None:
    """Precedence: --model, --transcript, then transcript auto-discovery.
    Auto-discovery is gated on a live agent session (CLAUDECODE in the
    environment, or an explicit --projects-root): outside one, the newest
    transcript is a PREVIOUS session's and would sign the wrong model."""
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
    precedent); disabled plugins are dropped — they did not shape the work."""
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
    enabled plugins only, narrowable further with `only`."""
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


def apply_to_message(text: str, block: str | None) -> str:
    """Rewrite a commit-message file: drop AI co-author boilerplate and any
    stale Assisted-By/Agent-Stack lines, then insert the fresh block after the
    last content line (before git's `#` comments). Re-running replaces, never
    duplicates. `block=None` scrubs only. A comment-only/empty message is left
    unsigned — there is nothing to attribute. Pure."""
    kept: list[str] = []
    for ln in text.splitlines():
        if _AI_COAUTHOR.match(ln) or _AI_BADGE.search(ln):
            continue
        if ln.strip().lower().startswith(_OWN_TRAILERS):
            continue
        kept.append(ln)
    first = last = None
    for i, ln in enumerate(kept):
        if ln.strip() and not ln.lstrip().startswith('#'):
            first = i if first is None else first
            last = i
    if block is None or last is None:
        out = '\n'.join(kept)
    else:
        # Join an existing trailer paragraph (e.g. Signed-off-by) so git keeps
        # parsing one trailer block; the subject line never counts as one.
        glue = [] if last != first and _TRAILER_LINE.match(kept[last]) else ['']
        out = '\n'.join(kept[: last + 1] + glue + block.splitlines() + kept[last + 1 :])
    if out and not out.endswith('\n'):
        out += '\n'
    return out


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

    model = resolve_model(args)
    stack = collect_stack(
        only=set(args.plugin) if args.plugin else None, include_harness=not args.no_harness
    )

    if args.apply:
        # A signing failure must never block a commit: scrub what can be
        # scrubbed, sign only when the model resolved, and exit 0 regardless.
        try:
            path = Path(args.apply)
            text = path.read_text(encoding='utf-8')
            new = apply_to_message(text, render_block(model, stack) if model else None)
            if new != text:
                path.write_text(new, encoding='utf-8')
        except OSError:
            pass
        return 0

    if not model:
        print(
            'llm-signature: could not resolve the writing model — pass --model or --transcript '
            '(auto-discovery needs a live Claude Code session)',
            file=sys.stderr,
        )
        return 1
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

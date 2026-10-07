#!/usr/bin/env python3
"""Feedback-debt Stop nudge and stale skill-body check, both read from the transcript.

    python feedback_nudge.py --stop-nudge     # Stop: at most one nudge per session
    python feedback_nudge.py --stale-bodies   # SessionStart resume|compact

`--stale-bodies` names each plugin whose last-served skill body came from an older
cached version than the install registry lists; see `stale_body_lines`. It ships
ON; `SESSION_WORKFLOW_STALE_BODY_CHECK=0` is its opt-out. The rest of this
docstring is about the Stop nudge.

It ships ON; `SESSION_WORKFLOW_FEEDBACK_NUDGE=0` is the documented opt-out. What
makes default-on safe is the binding check: the nudge stays silent unless a
feedback-targets file resolves, so an install with no registered tools never sees
it. Registered targets come from `$FEEDBACK_TARGETS_FILE`, else
`~/.claude/feedback-targets.toml` -- the same file the tool-feedback skill reads.

It fires when all of these hold, and then only once per session:
  - a feedback-targets file exists (there is somewhere to report to);
  - the transcript shows a `Skill` or plugin-MCP tool call;
  - none of those calls was `tool-feedback` (invoking it is what clears the debt);
  - the session has at least SESSION_WORKFLOW_NUDGE_MIN_TURNS (default 8) real
    human turns.

The transcript is the native record and the single input. A PostToolUse hook used
to append one JSONL entry per skill call so this nudge had something to read; that
was a second write path for a fact the transcript already carried, and it is gone
-- one fewer hook, one fewer state directory. A report written WITHOUT the skill
is still not detected (accepted imprecision, unchanged).

House rules: stdlib only; ASCII-only runtime output (json.dumps escapes non-ASCII);
every failure path exits 0; the block is printed before the marker persists so a
delivery failure never burns the once-per-session slot.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

NUDGE_GATE = 'SESSION_WORKFLOW_FEEDBACK_NUDGE'
MIN_TURNS_ENV = 'SESSION_WORKFLOW_NUDGE_MIN_TURNS'
STATE_DIR_ENV = 'SESSION_WORKFLOW_NUDGE_STATE_DIR'
TARGETS_FILE_ENV = 'FEEDBACK_TARGETS_FILE'
DEFAULT_TARGETS_FILE = Path.home() / '.claude' / 'feedback-targets.toml'
DEFAULT_MIN_TURNS = 8
# A tool call that counts as exercising a plugin tool: the Skill tool, or any
# plugin-provided MCP tool.
TOOL_PATTERN = re.compile(r'^Skill$|^mcp__plugin_.*')
# Subagent-completion prompts pass through as user records (verified 2026-07-23);
# they are not human turns and must not count toward the nudge gate.
SYNTHETIC_PREFIXES = ('[SYSTEM NOTIFICATION', '<task-notification>')
DEBT_CLEARING_MARK = 'tool-feedback'
STALE_BODY_GATE = 'SESSION_WORKFLOW_STALE_BODY_CHECK'
# The line the harness puts before every skill body it serves.
SKILL_BASE_MARK = 'Base directory for this skill:'


def _load_stdin_json() -> dict:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8-sig', errors='replace')
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'feedback-nudge'


def targets_file() -> Path | None:
    """The registered feedback-targets file, or None when none resolves. The
    binding check that makes a default-on nudge safe: with nowhere to report to,
    the nudge has nothing to ask for."""
    override = os.environ.get(TARGETS_FILE_ENV)
    candidate = Path(override) if override else DEFAULT_TARGETS_FILE
    try:
        return candidate if candidate.is_file() else None
    except OSError:
        return None


_TARGET_HEADER = re.compile(r'^\s*\[targets\.([^\]]+)\]\s*$')
_TARGET_REPO = re.compile(r'^\s*repo\s*=\s*[\'"](.+?)[\'"]\s*$')
_MCP_PLUGIN = re.compile(r'^mcp__plugin_([A-Za-z0-9_-]+?)_')


def registered_repos(targets: Path) -> dict[str, Path]:
    """{target name: repo path} read out of the feedback-targets file.

    Line-parsed rather than via `tomllib`: this hook can run under whatever
    python a hook runner resolves, and the file's own header promises it needs
    no tooling to read."""
    out: dict[str, Path] = {}
    name = None
    try:
        lines = targets.read_text(encoding='utf-8').splitlines()
    except OSError:
        return {}
    for line in lines:
        header = _TARGET_HEADER.match(line)
        if header:
            name = header.group(1).strip()
            continue
        repo = _TARGET_REPO.match(line) if name else None
        if repo:
            out[name] = Path(repo.group(1))
            name = None
    return out


def is_registered(tool: str, repos: dict[str, Path]) -> bool:
    """Whether an exercised tool belongs to a registered feedback target.

    The nudge used to name every `Skill` call as a "plugin tool", including
    personal skills under ~/.claude/skills that are in no registry -- which sent
    the reader to the registry to confirm a non-target, and a detector that lists
    non-targets trains its reader to discount the list. The registry was already
    being loaded; it just was not being consulted for the names.

    A `<plugin>:<skill>` call belongs to the target whose repo ships that plugin;
    an `mcp__plugin_<name>_...` tool names its plugin directly; a bare skill name
    is registered only if it IS a target."""
    mcp = _MCP_PLUGIN.match(tool)
    candidate = mcp.group(1) if mcp else tool.split(':', 1)[0]
    if candidate in repos:
        return True
    for repo in repos.values():
        try:
            if (repo / 'plugins' / candidate).is_dir():
                return True
        except OSError:
            continue
    return False


def registered_only(tools: list[str], targets: Path | None) -> list[str]:
    """`tools` filtered to registered targets. Fails OPEN, deliberately: when no
    repo path resolves (a registry that lists none, or checkouts that have moved)
    the unfiltered list is returned, because a nudge that says too much is a
    smaller failure than one that goes silent on a real debt."""
    if targets is None:
        return tools
    repos = registered_repos(targets)
    if not any(repo.is_dir() for repo in repos.values()):
        return tools
    return [t for t in tools if is_registered(t, repos)]


def _safe_session(session_id: object) -> str:
    sid = session_id if isinstance(session_id, str) and session_id else 'unknown'
    safe = ''.join(c for c in sid if c.isalnum() or c in '-_') or 'unknown'
    return safe[:64]


def _user_text(msg: dict) -> str | None:
    """Human prompt text of a `user` transcript record; None when there is none.
    Most type=="user" records in a real transcript are TOOL RESULTS (content
    blocks with no `type: "text"` entry) -- they must yield None so the turn gate
    counts humans, not tool calls (~64 of 71 user records in the reviewed
    sample were tool results)."""
    content = msg.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get('type') == 'text'
                and isinstance(block.get('text'), str)
            ):
                return block['text']
    return None


def _tool_names(msg: dict) -> list[str]:
    """Plugin tools invoked in one assistant record. A `Skill` call reports the
    skill it named (`input.skill`); a plugin-MCP call reports the tool name."""
    content = msg.get('content')
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get('type') != 'tool_use':
            continue
        name = block.get('name')
        if not isinstance(name, str) or not TOOL_PATTERN.search(name):
            continue
        if name == 'Skill':
            skill = (block.get('input') or {}).get('skill')
            out.append(skill[:200] if isinstance(skill, str) and skill else name)
        else:
            out.append(name[:200])
    return out


def read_transcript(transcript_path: object) -> tuple[int, list[str]]:
    """One pass over the transcript -> (human turns, plugin tools exercised in
    order, deduplicated). Any error yields (0, []), which HOLDS the nudge:
    fail-silent, never fail-noisy."""
    turns = 0
    skills: list[str] = []
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0, []
    try:
        p = Path(transcript_path)
        if not p.is_file():
            return 0, []
        for line in p.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict):
                continue
            msg = rec.get('message')
            if not isinstance(msg, dict):
                continue
            kind = rec.get('type')
            if kind == 'user':
                text = _user_text(msg)
                if text is not None and not text.lstrip().startswith(SYNTHETIC_PREFIXES):
                    turns += 1
            elif kind == 'assistant':
                for name in _tool_names(msg):
                    if name not in skills:
                        skills.append(name)
    except Exception:
        return 0, []
    return turns, skills


def _min_turns() -> int:
    try:
        v = int(os.environ.get(MIN_TURNS_ENV, ''))
    except (TypeError, ValueError):
        return DEFAULT_MIN_TURNS
    return v if v >= 1 else DEFAULT_MIN_TURNS


def nudge_reason(skills: list[str]) -> str:
    shown = ', '.join(skills[:3]) + (' and more' if len(skills) > 3 else '')
    return (
        f'feedback debt: this session exercised registered tools ({shown}) and no '
        'tool-feedback invocation is on record. Apply the tool-feedback skill '
        'now (write directly under a standing directive; otherwise emit its '
        'one-line offer), or finish if nothing is worth recording. This nudge '
        'fires once per session.'
    )


def _stop_nudge() -> int:
    if os.environ.get(NUDGE_GATE) == '0':
        return 0
    targets = targets_file()
    if targets is None:
        return 0  # no registered tools: nothing to report to, so nothing to ask
    payload = _load_stdin_json()
    if payload.get('stop_hook_active'):
        return 0
    safe = _safe_session(payload.get('session_id'))
    marker = _state_dir() / f'{safe}.nudged'
    with contextlib.suppress(Exception):
        if marker.exists():
            return 0
    turns, skills = read_transcript(payload.get('transcript_path'))
    if not skills:
        return 0
    if any(DEBT_CLEARING_MARK in s for s in skills):
        return 0
    skills = registered_only(skills, targets)
    if not skills:
        return 0  # only unregistered skills ran: there is no debt to owe
    if turns < _min_turns():
        return 0
    print(json.dumps({'decision': 'block', 'reason': nudge_reason(skills)}))
    with contextlib.suppress(Exception):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text('1', encoding='utf-8')
    return 0


class SkillLoad(NamedTuple):
    """One skill body the transcript records as served. `version` and `root`
    are None for a body served from outside a plugin cache (a `--plugin-dir`
    checkout), whose version this check cannot know."""

    root: str | None
    marketplace: str | None
    plugin: str
    version: str | None
    skill: str


# `<root>/plugins/cache/<marketplace>/<plugin>/<version>/skills/<skill>`, with
# either separator. The greedy root takes the LAST cache segment, so a home
# directory that itself contains `plugins/cache` cannot shift the fields.
_CACHE_BASE = re.compile(
    r'^(?P<root>.*)[\\/]plugins[\\/]cache[\\/](?P<marketplace>[^\\/]+)[\\/]'
    r'(?P<plugin>[^\\/]+)[\\/](?P<version>[^\\/]+)[\\/]skills[\\/](?P<skill>[^\\/]+)$'
)
_PLUGIN_BASE = re.compile(r'[\\/](?P<plugin>[^\\/]+)[\\/]skills[\\/](?P<skill>[^\\/]+)$')


def parse_skill_base(base: str) -> SkillLoad | None:
    """The skill a base directory names, or None when the path does not end in
    `<dir>/skills/<name>` (a bundled skill). Outside a plugin cache (a
    `--plugin-dir` checkout, a personal skill) the load has no version, so it
    can replace an earlier cached load of the same skill but never warns."""
    base = base.strip().rstrip('\\/')
    cached = _CACHE_BASE.match(base)
    if cached:
        return SkillLoad(**cached.groupdict())
    checkout = _PLUGIN_BASE.search(base)
    if checkout:
        return SkillLoad(None, None, checkout['plugin'], None, checkout['skill'])
    return None


def _served_bases(rec: dict) -> list[str]:
    """Base directories of the skill bodies one transcript record serves.

    Two record shapes serve a body: the meta user record written when a skill
    loads, and the `invoked_skills` attachment that serves loaded bodies again.
    The marker has to START the text: a tool result that merely quotes it (a
    grep over transcripts) serves nothing, and 2 such records sat in the same
    local transcripts as the 312 real ones."""
    texts: list[object] = []
    if rec.get('type') == 'user':
        content = (rec.get('message') or {}).get('content')
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts += [
                b.get('text') for b in content if isinstance(b, dict) and b.get('type') == 'text'
            ]
    elif rec.get('type') == 'attachment':
        skills = (rec.get('attachment') or {}).get('skills')
        if isinstance(skills, list):
            texts += [s.get('content') for s in skills if isinstance(s, dict)]
    return [
        t[len(SKILL_BASE_MARK) :].split('\n', 1)[0]
        for t in texts
        if isinstance(t, str) and t.startswith(SKILL_BASE_MARK)
    ]


def last_skill_loads(transcript_path: str) -> dict[tuple[str, str], SkillLoad]:
    """{(plugin, skill): its LAST served body}. Streams the file and parses only
    the lines that carry the marker, so the cost is one substring test per line
    for everything else. Raises on an unreadable file; the arm's caller turns
    that into silence."""
    marker = SKILL_BASE_MARK.encode('utf-8')
    loads: dict[tuple[str, str], SkillLoad] = {}
    with open(transcript_path, 'rb') as fh:
        for raw in fh:
            if marker not in raw:
                continue
            try:
                rec = json.loads(raw.decode('utf-8-sig', errors='replace'))
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            for base in _served_bases(rec):
                load = parse_skill_base(base)
                if load is not None:
                    loads[(load.plugin, load.skill)] = load
    return loads


def _installed(registry: dict, plugin: str, marketplace: str) -> list[str]:
    """Every installed version of exactly `plugin@marketplace` (one per scope).
    The marketplace is matched too: a same-named plugin from another
    marketplace is a different plugin."""
    records = (registry.get('plugins') or {}).get(f'{plugin}@{marketplace}')
    records = records if isinstance(records, list) else [records]
    return [str(r['version']) for r in records if isinstance(r, dict) and r.get('version')]


def stale_body_lines(transcript_path: str) -> list[str]:
    """One line per plugin whose last-served skill body is older than every
    installed version of it, read from the install registry beside the cache the
    body was served from. Silent (an empty list) for a body at an installed
    version, one served from outside a cache, a plugin the registry does not
    list, a version that does not parse, and a missing registry."""
    # Imported here, not at module top: a failure in this arm must not reach the
    # Stop nudge, which shares the module.
    from plugin_version import _version_key, read_registry

    registries: dict[str, dict | None] = {}
    stale: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for (plugin, skill), load in last_skill_loads(transcript_path).items():
        if load.version is None or load.root is None or load.marketplace is None:
            continue
        if load.root not in registries:
            path = Path(load.root) / 'plugins' / 'installed_plugins.json'
            registries[load.root] = read_registry(path)
        registry = registries[load.root]
        installed = _installed(registry, plugin, load.marketplace) if registry else []
        keys = [_version_key(v) for v in installed]
        loaded = _version_key(load.version)
        if not keys or loaded[0] or any(k[0] for k in keys):
            continue  # nothing installed to compare with, or a version that does not parse
        if loaded < min(keys):
            newest = max(installed, key=_version_key)
            stale.setdefault((plugin, newest), []).append((skill, load.version))
    return [
        f'Stale skill body: {plugin} {newest} is installed, but this session holds skill '
        'bodies loaded from an older copy: '
        + ', '.join(f'{skill} ({version})' for skill, version in sorted(bodies))
        + '. Invoke each skill again to load the current body; if it still loads the old '
        'version, this process predates the update: restart and resume from the anchor.'
        for (plugin, newest), bodies in sorted(stale.items())
    ]


def _stale_bodies() -> int:
    if os.environ.get(STALE_BODY_GATE) == '0':
        return 0
    transcript = _load_stdin_json().get('transcript_path')
    if not isinstance(transcript, str) or not transcript:
        return 0
    lines = stale_body_lines(transcript)
    if lines:
        context = '\n'.join(lines)
        out = {
            'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}
        }
        print(json.dumps(out))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if '--stop-nudge' in argv:
            return _stop_nudge()
        if '--stale-bodies' in argv:
            return _stale_bodies()
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

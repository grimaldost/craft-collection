#!/usr/bin/env python3
"""Feedback-debt prompt nudge and stale skill-body check, both read from the transcript.

    python feedback_nudge.py --prompt-nudge   # UserPromptSubmit: at most one nudge per session
    python feedback_nudge.py --stale-bodies   # SessionStart resume|compact
    python feedback_nudge.py --stop-nudge     # inert: exits 0 with no output

`--stale-bodies` names each plugin whose last-served skill body came from an older
cached version than the install registry lists; see `stale_body_lines`. It ships
ON; `SESSION_WORKFLOW_STALE_BODY_CHECK=0` is its opt-out. The rest of this
docstring is about the nudge.

It ships ON; `SESSION_WORKFLOW_FEEDBACK_NUDGE=0` is the documented opt-out. What
makes default-on safe is the binding check: the nudge stays silent unless a
feedback-targets file resolves, so an install with no registered tools never sees
it. Registered targets come from `$FEEDBACK_TARGETS_FILE`, else
`~/.claude/feedback-targets.toml` -- the same file the tool-feedback skill reads.

The nudge used to be a Stop `decision: block`, which forced one more turn out of
the model at the moment it had finished, in every session that owed a report. It
now never blocks: it rides the next owner-typed prompt as one line of additional
context, which the model reads with the owner's next request. `--stop-nudge` is
kept, inert, so a hooks.json from an older copy still exits clean.

It speaks when all of these hold, and then only once per session:
  - a feedback-targets file exists (there is somewhere to report to);
  - the prompt is owner-typed (`hooks/prompt_kind.py`, the rule every hook of
    this plugin shares): a hand-back, a notification or a peer message gets
    nothing and leaves the once-per-session slot unspent;
  - the transcript shows a `Skill` or plugin-MCP tool call of a registered tool;
  - none of those calls was `tool-feedback` (invoking it is what clears the debt);
  - the transcript holds at least SESSION_WORKFLOW_NUDGE_MIN_TURNS (default 8)
    owner turns: owner-typed user records, not skill bodies (`isMeta`),
    compaction summaries, tool results or synthetic prompts.

The cheap exits (gate, targets file, prompt kind, the once-per-session marker)
come before the transcript is opened, and a prompt reads it at most once. The
read resumes from the byte offset the previous prompt reached (state beside the
marker), so a long session without debt does not re-read tens of MB at every
prompt; the first read of a 65 MB transcript parses only the lines that can hold
an owner prompt or a plugin tool call.

The transcript is the native record and the single input. A report written
WITHOUT the skill is still not detected (accepted imprecision, unchanged).

House rules: stdlib only; ASCII-only runtime output (json.dumps escapes non-ASCII);
every failure path exits 0; the nudge is printed and flushed before the marker
persists, so a delivery failure never burns the once-per-session slot.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from collections.abc import Callable
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
DEBT_CLEARING_MARK = 'tool-feedback'
# The plugin's hooks/ directory, where the shared owner-typed rule lives.
HOOKS_DIR = Path(__file__).resolve().parents[3] / 'hooks'
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
    base = os.environ.get('CLAUDE_PLUGIN_DATA')
    if not base:
        # Imported here: tempfile pulls in shutil, which costs a hook that runs at
        # every prompt a measurable start-up on a loaded machine, and the harness
        # sets CLAUDE_PLUGIN_DATA for every hook it runs.
        import tempfile

        base = tempfile.gettempdir()
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


def _owner_rule() -> Callable[[object], bool] | None:
    """`prompt_kind.is_owner_typed` from the plugin's hooks/ directory, or None
    when it does not import. Without it the nudge cannot tell the owner from a
    hand-back, so the caller stays silent: a partial install fails open."""
    if str(HOOKS_DIR) not in sys.path:
        sys.path.append(str(HOOKS_DIR))
    try:
        from prompt_kind import is_owner_typed
    except Exception:
        return None
    return is_owner_typed


# Byte tests that decide, before any JSON parse, whether a line can matter. A
# line is parsed only when it can carry a plugin tool call, or a user record that
# is neither a tool result (`"tool_use_id"` appears only as a key, since a quote
# inside a JSON string is escaped) nor marked as a skill body or a compaction
# summary. Both serializations are covered: the harness writes no spaces, the
# tests' json.dumps writes one after each colon.
_TOOL_USE = b'"tool_use"'
_TOOL_NAMES = (b'Skill', b'mcp__plugin_')
_TOOL_RESULT = b'"tool_use_id"'
_NOT_OWNER = (
    b'"isMeta":true',
    b'"isMeta": true',
    b'"isCompactSummary":true',
    b'"isCompactSummary": true',
)
_BOM = b'\xef\xbb\xbf'


def _scan_line(raw: bytes, is_owner: Callable[[object], bool], state: dict) -> None:
    tool_line = _TOOL_USE in raw and any(t in raw for t in _TOOL_NAMES)
    user_line = (
        b'"user"' in raw and _TOOL_RESULT not in raw and not any(m in raw for m in _NOT_OWNER)
    )
    if not (tool_line or user_line):
        return
    try:
        rec = json.loads(raw.decode('utf-8', errors='replace'))
    except ValueError:
        return
    msg = rec.get('message') if isinstance(rec, dict) else None
    if not isinstance(msg, dict):
        return
    kind = rec.get('type')
    if kind == 'user' and user_line and not rec.get('isMeta') and not rec.get('isCompactSummary'):
        text = _user_text(msg)
        if text is not None and is_owner(text):
            state['turns'] += 1
    elif kind == 'assistant' and tool_line:
        for name in _tool_names(msg):
            if name not in state['tools']:
                state['tools'].append(name)


def _resumable(state: object, path: str, size: int) -> dict | None:
    """A copy of a previous prompt's scan state when it still describes this
    file: the same path, an offset inside it, well-formed counts."""
    if not isinstance(state, dict) or state.get('path') != path:
        return None
    offset, turns, tools = state.get('offset'), state.get('turns'), state.get('tools')
    if not (isinstance(offset, int) and 0 <= offset <= size and isinstance(turns, int)):
        return None
    if not (isinstance(tools, list) and all(isinstance(t, str) for t in tools)):
        return None
    return {'path': path, 'offset': offset, 'turns': turns, 'tools': list(tools)}


def scan_transcript(
    transcript_path: object, state: object, is_owner: Callable[[object], bool] | None = None
) -> dict | None:
    """{path, offset, turns, tools} after reading the transcript once, from the
    offset `state` reached when it still describes this file, else from the start.

    `turns` counts owner turns and `tools` lists the plugin tools exercised, in
    order, deduplicated. Only complete lines are read, so a record the harness is
    still writing is read whole by the next prompt. None on any error, which HOLDS
    the nudge: fail-silent, never fail-noisy."""
    is_owner = is_owner or _owner_rule()
    if is_owner is None or not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        p = Path(transcript_path)
        if not p.is_file():
            return None
        size = p.stat().st_size
        out = _resumable(state, transcript_path, size)
        out = out or {'path': transcript_path, 'offset': 0, 'turns': 0, 'tools': []}
        # Streamed line by line, not read whole: on a machine short of memory a
        # 65 MB buffer and its split copy are what page out first.
        with open(p, 'rb') as fh:
            fh.seek(out['offset'])
            for raw in fh:
                if not raw.endswith(b'\n'):
                    break  # still being written: the next prompt reads it whole
                start = out['offset']
                out['offset'] += len(raw)
                if start == 0 and raw.startswith(_BOM):
                    raw = raw[len(_BOM) :]
                raw = raw.strip()
                if raw:
                    _scan_line(raw, is_owner, out)
    except Exception:
        return None
    return out


def read_transcript(transcript_path: object) -> tuple[int, list[str]]:
    """(owner turns, plugin tools exercised) from one full read of the transcript;
    (0, []) on any error."""
    state = scan_transcript(transcript_path, None)
    return (state['turns'], state['tools']) if state else (0, [])


def _min_turns() -> int:
    try:
        v = int(os.environ.get(MIN_TURNS_ENV, ''))
    except (TypeError, ValueError):
        return DEFAULT_MIN_TURNS
    return v if v >= 1 else DEFAULT_MIN_TURNS


def nudge_line(skills: list[str]) -> str:
    """The nudge: one line, read by the model with the owner's next request."""
    shown = ', '.join(skills[:3]) + (' and more' if len(skills) > 3 else '')
    return (
        f'Feedback debt: this session exercised registered tools ({shown}) and no '
        'tool-feedback invocation is on record. Apply the tool-feedback skill when '
        'the work reaches a natural stopping point (write directly under a standing '
        'directive; otherwise offer it in one line), or carry on if nothing is worth '
        'recording. This note appears once per session.'
    )


def _read_state(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _write_state(path: Path, state: dict) -> None:
    """Best effort, atomic: a torn state file would only cost a full re-read."""
    with contextlib.suppress(Exception):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f'{path.name}.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(state), encoding='utf-8')
        os.replace(tmp, path)


def _prompt_nudge() -> int:
    if os.environ.get(NUDGE_GATE) == '0':
        return 0
    targets = targets_file()
    if targets is None:
        return 0  # no registered tools: nothing to report to, so nothing to ask
    payload = _load_stdin_json()
    is_owner = _owner_rule()
    if is_owner is None or not is_owner(payload.get('prompt')):
        return 0  # a hand-back or a notification: no owner reads what is injected here
    safe = _safe_session(payload.get('session_id'))
    marker = _state_dir() / f'{safe}.nudged'
    with contextlib.suppress(Exception):
        if marker.exists():
            return 0
    state_file = _state_dir() / f'{safe}.scan.json'
    state = scan_transcript(payload.get('transcript_path'), _read_state(state_file), is_owner)
    if state is None:
        return 0
    _write_state(state_file, state)
    skills = state['tools']
    if not skills or any(DEBT_CLEARING_MARK in s for s in skills):
        return 0
    skills = registered_only(skills, targets)
    if not skills:
        return 0  # only unregistered skills ran: there is no debt to owe
    if state['turns'] < _min_turns():
        return 0
    context = nudge_line(skills)
    out = {
        'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': context}
    }
    print(json.dumps(out))
    sys.stdout.flush()
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
        + '. Invoke a listed skill again before its next use in this session to load the '
        "current body; decisions already taken stand unless the newer body's CHANGELOG "
        'entry changes them; if it still loads the old version, this process predates the '
        'update: restart and resume from the anchor.'
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
        if '--prompt-nudge' in argv:
            return _prompt_nudge()
        if '--stop-nudge' in argv:
            return 0  # the nudge no longer blocks a Stop; see the module docstring
        if '--stale-bodies' in argv:
            return _stale_bodies()
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

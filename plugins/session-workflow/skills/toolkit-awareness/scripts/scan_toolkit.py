#!/usr/bin/env python3
"""Live inventory of installed Claude Code skills, commands, agents, hooks, and
plugins.

Scans user-level (~/.claude) and project-level (<cwd>/.claude) configuration, AND
asks the CLI for plugin-provided components (which live in the plugin cache, not
under .claude/) — a fresh, never-stale replacement for a hand-typed inventory.

Usage:
    python scan_toolkit.py                  # grouped table
    python scan_toolkit.py --json           # machine-readable
    python scan_toolkit.py --session-start  # inert unless TOOLKIT_AWARENESS_INJECT=1
    python scan_toolkit.py --session-start --no-cache   # force a fresh scan
    python scan_toolkit.py --check-serving <transcript>  # diagnose a frozen snapshot

Stdlib only (Python 3.10+). Plugin discovery shells out to `claude plugin list`
and degrades gracefully if the CLI is absent or changes its output format.
Installed plugin versions are compared against each marketplace source's manifest
and any skew is flagged — a stale install can silently hide newer skills; a
skill-directory diff catches the same lag when the install carries no manifest.

The --session-start path is cached: it fingerprints the settings/plugin/manifest
files and, on a warm hit under 24h, prints the last inventory WITHOUT invoking the
claude CLI (the inject is otherwise too slow to default on). It also diffs this
session's transcript against the installed plugin hooks to catch an app-level
frozen plugin snapshot — the only observable of that freeze. Both are best-effort
and fail open; the table and --json modes never touch the cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Component kinds discovered under a `.claude/` directory, plus plugins (which are
# discovered via the CLI). DISPLAY_ORDER is also the inventory's key set.
DIR_KINDS = ('skills', 'commands', 'agents', 'hooks')
DISPLAY_ORDER = ('skills', 'commands', 'agents', 'hooks', 'plugins')

_DESC_LIMIT = 100


def _read_frontmatter(md: Path) -> dict[str, str]:
    """Pull simple `key: value` pairs from a leading `---` frontmatter block,
    including `>` / `|` folded or literal block scalars (a `description: >` whose
    text continues on the following indented lines — a common pattern that a naive
    first-line parser truncates to just ">"). No YAML dependency; top-level keys
    only. {} on any error."""
    try:
        lines = md.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    if not lines or lines[0].strip() != '---':
        return {}
    out: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i].strip() != '---':
        line = lines[i]
        if ':' in line and not line[:1].isspace():  # a top-level key, not a nested line
            key, _, val = line.partition(':')
            key, val = key.strip(), val.strip()
            if val in ('>', '|', '>-', '|-', '>+', '|+'):  # block scalar — gather body
                body, i = [], i + 1
                while i < len(lines) and (not lines[i].strip() or lines[i][:1].isspace()):
                    body.append(lines[i].strip())
                    i += 1
                val = ' '.join(s for s in body if s)
                if key and key not in out:
                    out[key] = val
                continue
            if key and key not in out:  # first occurrence wins
                out[key] = _unquote(val)
        i += 1
    return out


def _unquote(val: str) -> str:
    """Strip one matched pair of surrounding YAML quotes so a quoted frontmatter
    value does not render with literal quotes in the inventory. Double-quoted
    style unescapes \\" and \\\\; single-quoted style unescapes doubled ''."""
    if len(val) >= 2 and val[0] == val[-1] == '"':
        inner, chars, i = val[1:-1], [], 0
        while i < len(inner):
            if inner[i] == '\\' and i + 1 < len(inner) and inner[i + 1] in '"\\':
                chars.append(inner[i + 1])
                i += 2
            else:
                chars.append(inner[i])
                i += 1
        return ''.join(chars)
    if len(val) >= 2 and val[0] == val[-1] == "'":
        return val[1:-1].replace("''", "'")
    return val


def _preview(text: str, limit: int = _DESC_LIMIT) -> str:
    text = ' '.join(text.split())
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + '...'
    return text


def _scan_skills(skills_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not skills_dir.is_dir():
        return out
    for sub in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = sub / 'SKILL.md'
        if not skill_md.is_file():
            continue
        fm = _read_frontmatter(skill_md)
        out.append(
            {
                'name': fm.get('name', sub.name),
                'description': _preview(fm.get('description', '')),
                'path': str(sub),
            }
        )
    return out


def _scan_markdown_dir(d: Path) -> list[dict]:
    out: list[dict] = []
    if not d.is_dir():
        return out
    for md in sorted(d.glob('*.md')):
        fm = _read_frontmatter(md)
        out.append(
            {
                'name': fm.get('name', md.stem),
                'description': _preview(fm.get('description', '')),
                'path': str(md),
            }
        )
    return out


def _settings_hooks(claude_dir: Path) -> list[dict]:
    """List hook EVENTS actually configured in settings(.local).json — the most
    common real hook location, which a directory scan alone misses."""
    out: list[dict] = []
    for fname in ('settings.json', 'settings.local.json'):
        sp = claude_dir / fname
        if not sp.is_file():
            continue
        try:
            data = json.loads(sp.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        hooks = data.get('hooks') if isinstance(data, dict) else None
        if isinstance(hooks, dict):
            for event, entries in hooks.items():
                n = len(entries) if isinstance(entries, list) else 1
                out.append({'name': f'{event} x{n} [{fname}]', 'path': str(sp)})
    return out


def _scan_hooks(hooks_dir: Path, claude_dir: Path) -> list[dict]:
    out: list[dict] = []
    if hooks_dir.is_dir():
        for f in sorted(hooks_dir.iterdir()):
            if f.is_file():
                out.append({'name': f.name, 'path': str(f)})
    out.extend(_settings_hooks(claude_dir))
    return out


def _hooks_file_events(hooks_json: Path) -> list[dict]:
    """Enumerate the hook EVENTS declared in a plugin's `hooks/hooks.json` — the
    file `claude plugin list` points at via installPath but never expands. Shape
    mirrors settings: a top-level `hooks` dict keyed by event → list of matcher
    groups. On any read/parse error, [] (never raised)."""
    out: list[dict] = []
    try:
        data = json.loads(hooks_json.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, ValueError):
        return out
    hooks = data.get('hooks') if isinstance(data, dict) else None
    if isinstance(hooks, dict):
        for event, entries in hooks.items():
            n = len(entries) if isinstance(entries, list) else 1
            out.append({'name': f'{event} x{n}', 'path': str(hooks_json)})
    return out


def _enumerate_plugin_components(name: str, install_path) -> dict[str, list[dict]]:
    """Walk one installed plugin's on-disk layout and enumerate the components it
    provides — `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md`, and the events in
    `hooks/hooks.json`. `claude plugin list` yields each plugin's installPath but not
    the components under it, so this closes that gap. Each returned item is tagged with
    its owning `plugin` so the caller can merge it into the per-kind sections. A missing
    or unresolvable install_path yields empty lists, never raises — pure and unit-
    testable against a fixture tree, no `claude` CLI required."""
    empty: dict[str, list[dict]] = {'skills': [], 'commands': [], 'agents': [], 'hooks': []}
    if not install_path:
        return empty
    base = Path(install_path)
    if not base.is_dir():
        return empty
    comps = {
        'skills': _scan_skills(base / 'skills'),
        'commands': _scan_markdown_dir(base / 'commands'),
        'agents': _scan_markdown_dir(base / 'agents'),
        'hooks': _hooks_file_events(base / 'hooks' / 'hooks.json'),
    }
    for items in comps.values():
        for it in items:
            it['plugin'] = name
    return comps


def _plugin_description(install_path) -> str:
    """Best-effort plugin description from its manifest — `claude plugin list`
    omits it, so read .claude-plugin/plugin.json under the install path."""
    if not install_path:
        return ''
    try:
        manifest = Path(install_path) / '.claude-plugin' / 'plugin.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, ValueError):
        return ''
    return _preview(str(data.get('description', ''))) if isinstance(data, dict) else ''


def _plugins_from_json(data: object) -> list[dict]:
    """Pure parser for `claude plugin list --json`. The CLI returns a list of
    objects keyed by `id` (plugin@marketplace), with version/scope/enabled/
    installPath and NO name or description — so derive a readable name from `id`
    and pull the description from the manifest. Tolerates shape drift."""
    plugins = data.get('plugins') if isinstance(data, dict) else data
    if not isinstance(plugins, list):
        return []
    out: list[dict] = []
    for p in plugins:
        if isinstance(p, str):
            out.append(
                {
                    'name': p,
                    'description': '',
                    'plugin': p,
                    'installPath': None,
                    'version': None,
                    'marketplace': None,
                }
            )
        elif isinstance(p, dict):
            ident = str(p.get('name') or p.get('id') or '?')
            label = ident.split('@', 1)[0]  # plugin@marketplace -> plugin
            marketplace = ident.split('@', 1)[1] if '@' in ident else None
            ver = str(p.get('version', '')).strip()
            tags = [t for t in (ver, 'disabled' if p.get('enabled') is False else '') if t]
            suffix = f' ({", ".join(tags)})' if tags else ''
            desc = (
                _preview(str(p['description']))
                if p.get('description')
                else _plugin_description(p.get('installPath'))
            )
            # `name` carries the version/disabled suffix for the plugins section; the
            # bare `plugin` label + `installPath` let scan() walk the components under it.
            out.append(
                {
                    'name': label + suffix,
                    'description': desc,
                    'plugin': label,
                    'installPath': p.get('installPath'),
                    'version': ver or None,
                    'marketplace': marketplace,
                }
            )
    return out


def _source_manifest_version(marketplace_dir: Path, plugin_label: str) -> str | None:
    """Version of `plugin_label` in a marketplace's on-disk source tree — resolved
    via the `.claude-plugin/marketplace.json` entry's source path, falling back to
    the conventional `plugins/<label>/` layout. None on any failure: best-effort,
    and the caller treats unknown as no-comparison, never as skew."""
    base = Path(marketplace_dir)
    declared = None
    try:
        mp = json.loads((base / '.claude-plugin' / 'marketplace.json').read_text(encoding='utf-8'))
        entries = mp.get('plugins', []) if isinstance(mp, dict) else []
        for entry in entries:
            if isinstance(entry, dict) and entry.get('name') == plugin_label:
                src = str(entry.get('source', ''))
                if src:
                    declared = base / src
                break
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    for candidate in (declared, base / 'plugins' / plugin_label):
        if not candidate:
            continue
        try:
            data = json.loads(
                (candidate / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8')
            )
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get('version'):
            return str(data['version'])
    return None


def _source_plugin_dir(marketplace_dir: Path, plugin_label: str) -> Path | None:
    """Resolve `plugin_label`'s on-disk source directory inside a marketplace tree —
    the `.claude-plugin/marketplace.json` entry's `source` path, else the
    conventional `plugins/<label>/` layout. Returns the first candidate that carries
    a `.claude-plugin/plugin.json` (so it is a real plugin root), else None. Same
    resolution the version check uses, exposed for the skill-list diff; None means
    no comparison, never false skew."""
    base = Path(marketplace_dir)
    declared = None
    try:
        mp = json.loads((base / '.claude-plugin' / 'marketplace.json').read_text(encoding='utf-8'))
        entries = mp.get('plugins', []) if isinstance(mp, dict) else []
        for entry in entries:
            if isinstance(entry, dict) and entry.get('name') == plugin_label:
                src = str(entry.get('source', ''))
                if src:
                    declared = base / src
                break
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    for candidate in (declared, base / 'plugins' / plugin_label):
        if candidate and (candidate / '.claude-plugin' / 'plugin.json').is_file():
            return candidate
    return None


def _skill_dir_names(plugin_dir: Path) -> set[str]:
    """Names of the skill directories under `plugin_dir/skills` — a subdir counts
    only when it holds a SKILL.md. {} on any error or missing dir."""
    out: set[str] = set()
    skills = Path(plugin_dir) / 'skills'
    try:
        if not skills.is_dir():
            return out
        for sub in skills.iterdir():
            if sub.is_dir() and (sub / 'SKILL.md').is_file():
                out.add(sub.name)
    except OSError:
        return out
    return out


def _skill_list_skew(rows: list[dict], locations: dict[str, str]) -> list[str]:
    """Skills present in a plugin's marketplace SOURCE but absent from its installed
    copy — the skew the version check misses when an install carries NO plugin.json
    (version unknown, yet whole skills can still be missing). One caveat per lagging
    plugin, missing-in-installed only (an extra installed skill is not the footgun).
    An unresolvable source is compared against nothing: absence of evidence is not
    skew."""
    out: list[str] = []
    for r in rows:
        market, install = r.get('marketplace'), r.get('installPath')
        loc = locations.get(market) if market else None
        if not (loc and install):
            continue
        src_dir = _source_plugin_dir(Path(loc), r.get('plugin') or '')
        if not src_dir:
            continue
        missing = sorted(_skill_dir_names(src_dir) - _skill_dir_names(Path(install)))
        if not missing:
            continue
        label = r.get('plugin') or ''
        out.append(
            f'installed copy lags repo: {label} missing skills: {", ".join(missing)}'
            f' -- consider claude plugin update {label}'
        )
    return out


def _marketplace_locations() -> dict[str, str]:
    """{marketplace name: on-disk installLocation} via `claude plugin marketplace
    list --json`. For a `directory` marketplace the location IS the live source
    tree; for git/github sources it is the local marketplace clone. {} when the
    CLI is absent or the shape drifts — same tolerance as `_scan_plugins`."""
    try:
        proc = subprocess.run(
            ['claude', 'plugin', 'marketplace', 'list', '--json'],  # noqa: S607 - PATH-resolved
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return {}
    if proc.returncode != 0 or not (proc.stdout or '').strip():
        return {}
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return {}
    out: dict[str, str] = {}
    if isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and m.get('name') and m.get('installLocation'):
                out[str(m['name'])] = str(m['installLocation'])
    return out


def _merge_skew(rows: list[dict], locations: dict[str, str]) -> list[str]:
    """Annotate installed-plugin rows whose version differs from their marketplace
    source's manifest — the invisible-skew footgun (a stale install once hid an
    entire skill from a session). Mutates matching rows in place (`source_version`
    plus a visible name suffix) and returns caveat lines for the scan output.
    Unresolvable sources are skipped: absence of evidence is not skew."""
    stale: list[str] = []
    for r in rows:
        market, ver = r.get('marketplace'), r.get('version')
        loc = locations.get(market) if market else None
        if not (loc and ver):
            continue
        src = _source_manifest_version(Path(loc), r.get('plugin') or '')
        if not src or src == ver:
            continue
        r['source_version'] = src
        if f'({ver}' in r['name']:
            r['name'] = r['name'].replace(f'({ver}', f'({ver}, source {src}', 1)
        else:
            r['name'] += f' (source {src})'
        stale.append(f'{r.get("plugin")} installed {ver} vs source {src}')
    if stale:
        return [
            'installed plugin version differs from marketplace source: '
            + '; '.join(stale)
            + ' -- consider `claude plugin update <plugin>`'
        ]
    return []


def _git_env() -> dict[str, str]:
    """The environment minus every GIT_* variable. A git hook exports GIT_DIR and
    friends, and GIT_DIR takes precedence over `-C`, so a child git inherits the
    *outer* repo and silently answers about the wrong checkout — the exact
    wrong-repo reading this staleness check exists to prevent."""
    return {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}


def _source_behind_upstream(marketplace_dir: Path) -> int | None:
    """Commits the marketplace source checkout is behind its fetched upstream
    (`git rev-list --count HEAD..@{u}`), or None when the location is not a git
    checkout, has no upstream, or git is unavailable — absence of evidence is
    not staleness. Reads only the local remote-tracking ref (no network): it
    sees "fetched but not merged", not commits never fetched."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ['git', '-C', str(marketplace_dir), 'rev-list', '--count', 'HEAD..@{u}'],  # noqa: S607 - git resolved from PATH
            capture_output=True,
            text=True,
            timeout=10,
            env=_git_env(),
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    out = (proc.stdout or '').strip()
    if proc.returncode != 0 or not out.isdigit():
        return None
    return int(out)


def _stale_checkout_caveats(locations: dict[str, str]) -> list[str]:
    """One caveat per marketplace whose source checkout lags its own fetched
    upstream — the skew below `_merge_skew`'s reach: installed == source reads
    "no skew" while BOTH trail the remote (a 13-commits-behind main once nearly
    re-ran a whole audit against already-fixed findings)."""
    out: list[str] = []
    for name, loc in sorted(locations.items()):
        behind = _source_behind_upstream(Path(loc))
        if behind:
            out.append(
                f"marketplace '{name}' source checkout is {behind} commit(s) behind "
                f'its fetched upstream -- pull {loc} before trusting installed-vs-source'
            )
    return out


def _scan_plugins() -> list[dict]:
    """Plugin-provided components live in the plugin cache, not under .claude/ —
    ask the CLI. Tolerates the CLI being absent or failing; on any failure returns
    [] (the caller still reports the .claude inventory)."""
    try:
        proc = subprocess.run(
            ['claude', 'plugin', 'list', '--json'],  # noqa: S607 - 'claude' resolved from PATH
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0 or not (proc.stdout or '').strip():
        return []
    try:
        return _plugins_from_json(json.loads(proc.stdout))
    except (json.JSONDecodeError, ValueError):
        return []


def scan(roots: list[Path]) -> dict[str, list[dict]]:
    """Enumerate skills/commands/agents/hooks across each root's `.claude` dir, plus
    plugin-provided components (walked under each plugin's installPath). Missing dirs
    are skipped, never raised. `_caveats` carries a note when plugin-provided components
    could not be enumerated, so the human output degrades to an explicit caveat instead
    of a misleading bare `HOOKS (0)`."""
    result: dict[str, list[dict]] = {k: [] for k in DISPLAY_ORDER}
    result['_caveats'] = []
    for root in roots:
        claude = Path(root) / '.claude'
        if not claude.is_dir():
            continue
        result['skills'].extend(_scan_skills(claude / 'skills'))
        result['commands'].extend(_scan_markdown_dir(claude / 'commands'))
        result['agents'].extend(_scan_markdown_dir(claude / 'agents'))
        result['hooks'].extend(_scan_hooks(claude / 'hooks', claude))

    plugins = _scan_plugins()
    result['plugins'] = plugins
    # Walk each installed plugin's installPath and merge its components (tagged by owning
    # plugin) into the per-kind sections — the .claude scan alone is blind to them.
    walked = False
    for p in plugins:
        comps = _enumerate_plugin_components(
            p.get('plugin') or p.get('name', ''), p.get('installPath')
        )
        for kind in DIR_KINDS:
            if comps[kind]:
                walked = True
            result[kind].extend(comps[kind])
    if plugins and not walked:
        # Plugins are installed but none resolved to on-disk components (installPath
        # absent or unreadable) — say so rather than imply the per-kind counts are whole.
        result['_caveats'].append(
            'plugin-provided components not enumerated (installPath unavailable)'
        )
    elif not plugins:
        # The CLI is absent/failed, so plugin components are invisible to this scan.
        result['_caveats'].append(
            'plugin-provided components not enumerated (claude CLI unavailable)'
        )
    if plugins:
        # Flag installed-vs-source version skew per plugin (stale installs are
        # otherwise invisible in-session and have hidden whole skills), then the
        # layer below it: a source checkout that itself lags its fetched origin,
        # where installed==source reads "no skew" while both trail the remote.
        locations = _marketplace_locations()
        result['_caveats'].extend(_merge_skew(plugins, locations))
        result['_caveats'].extend(_stale_checkout_caveats(locations))
        # Version skew can't see a lag when the install carries no plugin.json; a
        # skill-directory diff catches skills present in source but missing locally.
        result['_caveats'].extend(_skill_list_skew(plugins, locations))
    return result


# --- serving-snapshot check (transcript diff) ---------------------------------
# The desktop app can serve a plugin hooks snapshot frozen weeks behind the
# installed cache; every disk layer reads "current". The only observable is the
# session transcript's recorded hook command strings differing from the installed
# hooks.json. This whole path is best-effort and fail-open: any error skips the
# check silently (absence of evidence is not skew).

_SERVING_CAVEAT_CAP = 2


def _read_hook_stdin() -> dict | None:
    """The SessionStart hook envelope on stdin (session_id, transcript_path, cwd),
    or None. Only attempted when stdin is a non-tty pipe; every failure -> None so
    an interactive or malformed invocation never blocks or raises."""
    try:
        stdin = sys.stdin
        if stdin is None or stdin.isatty():
            return None
        raw = stdin.read()
        if not raw or not raw.strip():
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _transcript_hook_commands(transcript_path: str) -> list[str]:
    """Plugin-hook command strings recorded in an NDJSON transcript: each record
    whose `attachment` is a dict with a string `command`, keeping only commands
    that contain the literal `${CLAUDE_PLUGIN_ROOT}` (settings-level hooks vary
    legitimately and are excluded). Bad lines are skipped; any error -> []."""
    out: list[str] = []
    try:
        p = Path(transcript_path)
        if not p.is_file():
            return out
        for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(rec, dict):
                continue
            att = rec.get('attachment')
            if isinstance(att, dict):
                cmd = att.get('command')
                if isinstance(cmd, str) and '${CLAUDE_PLUGIN_ROOT}' in cmd:
                    out.append(cmd)
    except Exception:
        return out
    return out


def _expected_hook_commands(install_paths: list) -> set[str]:
    """The joined command strings every installed plugin's `hooks/hooks.json`
    declares -- `' '.join([command] + args)`, the exact unresolved form the
    transcript records. Unreadable manifests contribute nothing, never raise."""
    expected: set[str] = set()
    for ip in install_paths:
        if not ip:
            continue
        try:
            data = json.loads((Path(ip) / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        hooks = data.get('hooks') if isinstance(data, dict) else None
        if not isinstance(hooks, dict):
            continue
        for entries in hooks.values():
            if not isinstance(entries, list):
                continue
            for group in entries:
                inner = group.get('hooks') if isinstance(group, dict) else None
                if not isinstance(inner, list):
                    continue
                for h in inner:
                    if not isinstance(h, dict):
                        continue
                    command = h.get('command')
                    if not isinstance(command, str):
                        continue
                    args = h.get('args')
                    parts = (
                        [command] + [str(a) for a in args] if isinstance(args, list) else [command]
                    )
                    expected.add(' '.join(parts))
    return expected


def _serving_snapshot_caveats(recorded_commands: list, install_paths: list) -> list[str]:
    """One caveat per recorded plugin-hook command that no installed hooks.json
    produces -- the app-level frozen-snapshot signature. Deduped and capped; all
    matched (or nothing recorded) -> []."""
    expected = _expected_hook_commands(install_paths)
    out: list[str] = []
    seen: set[str] = set()
    for cmd in recorded_commands:
        if not isinstance(cmd, str) or cmd in expected or cmd in seen:
            continue
        seen.add(cmd)
        out.append(
            "session is serving a plugin hook not in any installed hooks.json: '"
            + cmd[:100]
            + "' -- app-level frozen plugin snapshot; verify hooks headless (claude -p)"
        )
        if len(out) >= _SERVING_CAVEAT_CAP:
            break
    return out


def _serving_snapshot_from_stdin(install_paths: list) -> list[str]:
    """Read the hook envelope from stdin and diff its transcript against the given
    install paths. Fail-open at every step: no envelope, no transcript, no records,
    or any error -> []."""
    try:
        envelope = _read_hook_stdin()
        if not isinstance(envelope, dict):
            return []
        tp = envelope.get('transcript_path')
        if not isinstance(tp, str) or not tp:
            return []
        recorded = _transcript_hook_commands(tp)
        if not recorded:
            return []
        return _serving_snapshot_caveats(recorded, install_paths)
    except Exception:
        return []


# --- inventory cache (--session-start only) ------------------------------------
# The --session-start inject shells to the claude CLI (seconds), too slow to ever
# default on. A fingerprinted cache lets a warm session start return instantly
# without the CLI. Every cache failure path is silent, never fatal.

_CACHE_TTL_SECONDS = 24 * 60 * 60


def _cache_dir() -> Path:
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'toolkit-awareness'


def _cache_path() -> Path:
    return _cache_dir() / 'inventory-cache.json'


def _fingerprint_paths(roots: list[Path]) -> list[Path]:
    """The files whose mtime/size decide whether a cached inventory is still valid:
    user + per-root settings, the installed-plugins record, every marketplace
    manifest, and this script itself."""
    home = Path.home()
    paths = [
        home / '.claude' / 'settings.json',
        home / '.claude' / 'settings.local.json',
        home / '.claude' / 'plugins' / 'installed_plugins.json',
    ]
    for root in roots:
        paths.append(Path(root) / '.claude' / 'settings.json')
        paths.append(Path(root) / '.claude' / 'settings.local.json')
    try:
        markets = home / '.claude' / 'plugins' / 'marketplaces'
        paths.extend(sorted(markets.glob('*/.claude-plugin/marketplace.json')))
    except OSError:
        pass
    paths.append(Path(__file__).resolve())
    return paths


def _fingerprint(roots: list[Path]) -> str:
    """A sha256 over a sorted list of [str(path), mtime_ns, size] for every
    fingerprint file (a missing file participates as [path, null, null]) plus the
    literal sorted list of scan roots -- changes when any of them does."""
    entries = []
    for p in _fingerprint_paths(roots):
        try:
            st = p.stat()
            entries.append([str(p), st.st_mtime_ns, st.st_size])
        except OSError:
            entries.append([str(p), None, None])
    payload = {'files': sorted(entries), 'roots': sorted(str(r) for r in roots)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


def _read_cache() -> dict | None:
    try:
        data = json.loads(_cache_path().read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _write_cache(fingerprint: str, output_text: str, install_paths: list) -> None:
    """Atomic best-effort cache write (tmp + os.replace). Every failure is
    swallowed -- a cache problem must never break a session start."""
    try:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        record = {
            'fingerprint': fingerprint,
            'ts': time.time(),
            'output_text': output_text,
            'install_paths': [str(p) for p in install_paths if p],
        }
        tmp = d / f'inventory-cache.json.{os.getpid()}.tmp'
        tmp.write_text(json.dumps(record), encoding='utf-8')
        os.replace(tmp, _cache_path())
    except Exception:  # noqa: S110 - cache is best-effort; a write failure must never break a session start
        pass


def _install_paths_of(inv: dict[str, list[dict]]) -> list[str]:
    return [p.get('installPath') for p in inv.get('plugins', []) if p.get('installPath')]


def _emit_compact(output_text: str, serving_caveats: list[str]) -> None:
    if output_text:
        print(output_text)
    for line in serving_caveats:
        print(f'note: {line}')


def _run_session_start(roots: list[Path], use_cache: bool) -> int:
    """Cached, CLI-free warm path when possible; otherwise a full scan cached for
    next time. The serving-snapshot check is computed fresh from this session's
    transcript every time (never cached), on both hit and miss."""
    fingerprint = None
    if use_cache:
        try:
            fingerprint = _fingerprint(roots)
            cached = _read_cache()
            if (
                cached
                and cached.get('fingerprint') == fingerprint
                and (time.time() - float(cached.get('ts', 0))) < _CACHE_TTL_SECONDS
            ):
                serving = _serving_snapshot_from_stdin(cached.get('install_paths') or [])
                _emit_compact(str(cached.get('output_text', '')), serving)
                return 0
        except Exception:
            fingerprint = None  # any cache error -> full scan below
    inv = scan(roots)
    text = _compact_text(inv)
    install_paths = _install_paths_of(inv)
    serving = _serving_snapshot_from_stdin(install_paths)
    _emit_compact(text, serving)
    if use_cache and fingerprint is not None:
        _write_cache(fingerprint, text, install_paths)
    return 0


def _run_check_serving(transcript_path: str, roots: list[Path]) -> int:
    """On-demand serving-snapshot diagnosis: diff a transcript against the live
    installed hooks. Prints the caveat lines or a clean-match line; always 0."""
    recorded = _transcript_hook_commands(transcript_path)
    caveats = _serving_snapshot_caveats(recorded, _install_paths_of(scan(roots)))
    if caveats:
        for line in caveats:
            print(line)
    else:
        print('serving snapshot matches installed hooks')
    return 0


def _print_table(inv: dict[str, list[dict]]) -> None:
    for kind in DISPLAY_ORDER:
        items = inv.get(kind, [])
        print(f'\n  {kind.upper()} ({len(items)})')
        if not items:
            print('    (none)')
            continue
        for it in items:
            desc = it.get('description', '')
            owner = f'[{it["plugin"]}] ' if it.get('plugin') else ''  # tag plugin-owned items
            print(f'    {it["name"]:<28} {owner}{desc}'.rstrip())
    for caveat in inv.get('_caveats', []):
        print(f'\n  note: {caveat}')
    print()


def _compact_text(inv: dict[str, list[dict]]) -> str:
    """The one-line inventory plus its `note:` caveat lines, as a single string —
    the text the session-start path prints and caches (serving-snapshot caveats,
    being session-specific, are appended fresh at print time, never cached)."""
    lines: list[str] = []
    parts = []
    for kind in DISPLAY_ORDER:
        names = [it['name'] for it in inv.get(kind, [])]
        if names:
            parts.append(f'{kind}: ' + ', '.join(names))
    if parts:
        lines.append('Installed toolkit: ' + ' | '.join(parts))
    for caveat in inv.get('_caveats', []):
        lines.append(f'note: {caveat}')
    return '\n'.join(lines)


def _print_compact(inv: dict[str, list[dict]]) -> None:
    text = _compact_text(inv)
    if text:
        print(text)


def _default_roots() -> list[Path]:
    return [Path.home(), Path.cwd()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Live Claude Code toolkit inventory.')
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    parser.add_argument(
        '--session-start',
        action='store_true',
        help='inject inventory only if TOOLKIT_AWARENESS_INJECT=1',
    )
    parser.add_argument(
        '--root',
        action='append',
        default=None,
        help='override scan root (repeatable); defaults to ~ and cwd',
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='force a fresh scan on --session-start (bypass the inventory cache)',
    )
    parser.add_argument(
        '--check-serving',
        metavar='TRANSCRIPT',
        default=None,
        help='diff a session transcript against installed plugin hooks and exit',
    )
    args = parser.parse_args(argv)

    # Piped Windows stdout defaults to cp1252; skill descriptions carry em-dashes
    # and arrows, which mojibake in UTF-8 terminals (or raise outright). Emit
    # UTF-8 regardless of the platform default.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    roots = [Path(r) for r in args.root] if args.root else _default_roots()

    # On-demand serving-snapshot diagnosis: never touches the inventory cache.
    if args.check_serving is not None:
        return _run_check_serving(args.check_serving, roots)

    # SessionStart hook entry point: silent unless explicitly opted in, so the hook
    # can ship enabled-but-inert and cost nothing until the user wants it. Served
    # from the inventory cache when warm (no claude CLI); --no-cache forces a scan.
    if args.session_start:
        if os.environ.get('TOOLKIT_AWARENESS_INJECT') != '1':
            return 0
        return _run_session_start(roots, use_cache=not args.no_cache)

    inv = scan(roots)  # table and --json never touch the cache
    if args.json:
        print(json.dumps(inv, indent=2))
    else:
        _print_table(inv)
    return 0


if __name__ == '__main__':
    sys.exit(main())

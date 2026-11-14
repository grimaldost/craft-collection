"""Checker of the series rule pack: session-workflow's series guard, called by the kit.

The checker holds no rule of its own. When the file is loaded it finds
`plugins/session-workflow/hooks/` from its own location in the repository,
turns bytecode writing off, puts that folder on `sys.path` and imports the
core under its own name, `series_guard`. It then requires the names it uses
and raises when one is missing, so a moved or renamed core fails the build
and the launch. Two of those names, `_series_ok` and `_PULL_URL`, are private
to the core.

The event does not say whether a command is bash or PowerShell, so every
command is read by the core in both dialects, `bash` first.

`record(note, facts)` keeps, per session, the pull requests a create printed:
`{"repos": {"owner/repo": [URL, ...]}}`. It records only a completed shell
outcome with an observed command in which both readings find a create, and
only while the core's switch is not off.

`check(act, observation, facts)` answers `match` only when both readings find
a create, in a recorded repository, that does not carry a `KEEL_SERIES` the
core accepts; in doubt it lets the act pass, as the core does. `None` facts
give `cannot-tell` once a reading finds a create. The detail of a match is the
core's `why`, then the start of the core's deny text.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

CORE_FOLDER = Path(__file__).resolve().parents[3] / 'plugins' / 'session-workflow' / 'hooks'
if str(CORE_FOLDER) not in sys.path:
    sys.path.insert(0, str(CORE_FOLDER))

import series_guard  # noqa: E402 - the core's folder is on sys.path only from here

USED = ('find_creates', 'key_for', '_series_ok', 'deny_reason', 'mode', '_PULL_URL')
_MISSING = [name for name in USED if not hasattr(series_guard, name)]
if _MISSING:
    raise ImportError(f'series_guard lacks {", ".join(_MISSING)}')

READINGS = ('bash', 'powershell')
RULE_MARK = " The owner's rule:"
UNCHANGED = {'result': 'unchanged'}
NO_MATCH = {'result': 'no-match'}
CANNOT_TELL = {'result': 'cannot-tell'}


def _cwd(act: dict) -> Path | None:
    cwd = act.get('cwd')
    return Path(cwd) if isinstance(cwd, str) and cwd else None


def _readings(command: str, cwd: Path | None) -> list[list]:
    """The creates the core finds in each dialect, in the order of READINGS."""
    return [series_guard.find_creates(command, shell, cwd) for shell in READINGS]


def _recorded(facts: object) -> dict[str, list[str]] | None:
    """The recorded repositories, `{}` when none; None when the facts cannot be read."""
    if not isinstance(facts, dict):
        return None
    repos = facts.get('repos', {})
    if not isinstance(repos, dict):
        return None
    for urls in repos.values():
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            return None
    return repos


def record(note: dict, facts: dict) -> dict:
    """Append the pull requests a completed create printed, per lowercase `owner/repo`."""
    if series_guard.mode() == 'off':
        return UNCHANGED
    body = note.get('note')
    observation = note.get('observation')
    if not isinstance(body, dict) or not isinstance(observation, dict):
        return UNCHANGED
    act = body.get('act')
    if body.get('kind') != 'outcome' or not isinstance(act, dict) or act.get('kind') != 'shell':
        return UNCHANGED
    command, output = act.get('command'), body.get('output')
    if observation.get('command') != 'observed' or not isinstance(command, str):
        return UNCHANGED
    if body.get('status') != 'completed' or not isinstance(output, str):
        return UNCHANGED
    if not all(_readings(command, _cwd(act))):
        return UNCHANGED
    urls: dict[str, str] = {}
    for m in series_guard._PULL_URL.finditer(output):
        key = f'{m.group(1)}/{m.group(2)}'.lower()
        urls.setdefault(key, f'https://github.com/{m.group(1)}/{m.group(2)}/pull/{m.group(3)}')
    repos = {key: list(prs) for key, prs in (_recorded(facts) or {}).items()}
    added = False
    for key, url in urls.items():
        prs = repos.setdefault(key, [])
        if url not in prs:
            prs.append(url)
            added = True
    return {'facts': {'repos': repos}} if added else UNCHANGED


def _unsatisfied(creates: list, repos: dict[str, list[str]]) -> list[tuple[str, str]]:
    """(key, why) of each create in a recorded repository whose KEEL_SERIES the core refuses."""
    found = []
    for create in creates:
        key = series_guard.key_for(create)
        if key is None or key not in repos:
            continue
        ok, why = series_guard._series_ok(create.keel_series, create.workdir, create.shell)
        if not ok:
            found.append((key, why))
    return found


def _detail(key: str, prs: list[str], why: str) -> str:
    """`why`, one space, then the core's text before `why` and the rule."""
    head = series_guard.deny_reason(key, prs, why).split(RULE_MARK, 1)[0]
    ending = f' {why}'
    if head.endswith(ending):
        head = head[: -len(ending)]
    return f'{why} {head}'


def check(act: dict, observation: dict, facts: dict | None) -> dict:
    """`match`, `no-match` or `cannot-tell` for one act, from the core's readings and the facts."""
    if series_guard.mode() in ('off', 'observe'):
        return NO_MATCH
    if observation.get('command') != 'observed':
        return CANNOT_TELL
    command = act.get('command')
    if not isinstance(command, str):
        return CANNOT_TELL
    if 'create' not in command or 'pr' not in command:
        return NO_MATCH
    readings = _readings(command, _cwd(act))
    if not any(readings):
        return NO_MATCH
    repos = _recorded(facts)
    if repos is None:
        return CANNOT_TELL
    unsatisfied = [_unsatisfied(creates, repos) for creates in readings]
    if not all(unsatisfied):
        return NO_MATCH
    key, why = unsatisfied[0][0]
    return {'result': 'match', 'detail': _detail(key, repos[key], why)}

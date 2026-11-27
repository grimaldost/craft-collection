"""Launcher preflight and `kit run`.

`kit run --harness NAME --home DIR --workdir DIR --policy FILE -- HARNESS_ARGS...`
checks, in order: the arguments, the policy (it must load whole, and each of
its checkers must execute and define a callable `check` within its budget,
loaded with descriptors 1 and 2 at the null device for the load only), the
rendered home, a nested launch, the folder and its remotes, the session flags,
the project layer and the environment. Any refusal exits 64 with one line on
stderr and starts nothing; a run is minted only after every check passed, so a
refusal leaves no `run.json`. After the mint the presence canary runs
(`canary.py`); a failed canary sets `outcome` to `refused-canary`, exits 65
and never starts the session. Then the harness starts with the arguments
unchanged, in the working folder, under an environment built from an allow
list, and `kit run` returns its exit code.

The folder check applies to every harness but Claude Code: `forbidden_roots`
wins, and the folder passes when it is under a `test_roots` entry and outside
any git work tree, or when it is a work tree whose every effective push URL is
`no_push`, `DISABLED` or empty. Claude Code's remotes are only recorded.

The session flags are the canary's: the arguments start with the driver's
leading tokens, carry its required arguments as adjacent tokens with each
required flag exactly once, and every token that starts with `-` is a member
of the driver's allow list. The launcher does not parse the harness's grammar.

The project layer: a project-config path found in an ancestor of the working
folder (up to the top of its work tree, or to the filesystem root, and from
`runs/` under the state root to that root, as the driver's walk says) is a
refusal; one found in the working folder is recorded in `run.json`.

For a policy with a recording checker three more refusals apply. A recorded
kind whose `[notes]` entry in the harness's contract reads `absent` is refused
(a missing entry launches, with one line on stderr); after the home check, a
home whose `note_config.json` is missing, malformed or lacks a recorded kind,
or a Claude Code home whose `settings.json` lacks a note entry for one, is
refused; and a `SESSION_WORKFLOW_GOVERNED_HOME` that lies under no test root
of the policy is refused, while one under a test root is passed into the
session. A policy that records nothing launches as before and the variable is
not passed. The cores' switches are never passed.

The harness version: once the binary is found, preflight reads the version it
reports and refuses a version other than its contract's `[harness] version`
(the driver's `pinned_version`), or none, naming both and the two ways on: a
re-pin, or `--accept-version VERSION`, which launches only when VERSION is
exactly the version found. Such a run records `accepted_version` in
`run.json`, and one stderr line says the run is not covered by the contract.

Session modes (`--mode`, default `headless`): a driver declares a grammar per
mode it offers. Interactive mode is refused for a driver without it, on any
platform but Windows, and when the harness's contract records the mode
`absent` (a missing entry launches, with one line on stderr). In interactive
mode the session also gets the terminal names kit's environment holds, and a
home is refused when its rendered files differ from the render's record in
`home.json` or when it holds `run-open.json`, the mark of a run whose end kit
did not record.

After the mint the launcher writes the home's watched files to
`runs/<id>/home-hashes.json`; after the canary passed it reads them again, and
a difference sets `outcome` to `refused-home-changed`, exits 65 and starts no
session. In interactive mode it writes `run-open.json` beside `home.json` right
before the session starts and removes it once it recorded the session's end.
On Windows the session is created suspended, joins a new Job Object that kills
its processes when closed, and only then resumes; kit ends the job after its
wait. On POSIX the session starts in a new session and its process group is
killed after the wait. A Ctrl+C or Ctrl+Break during preflight exits 130 with
no run; one after the mint and before the session sets `outcome` to
`interrupted` and exits 130; during the session kit ignores it.

A daily home (`home.json`'s `kind` is `daily`) reaches its provider only
through the relay, `kit relay serve`, the one child of `kit run` given the
provider key. Before any child starts, `kit run` reads the variable the daily
file's `key_env` names, keeps its value only for the relay's first line of
standard input and removes it from its own environment; preflight's `git` and
the version probe also lose every other variable the secret-name rule would
refuse. Preflight refuses a daily home whose daily file is absent or differs
from the one it was rendered with (naming each key whose value differs), an
invalid daily file, an absent or empty key variable, a listen port already
bound on 127.0.0.1, a relay lock already held and a day or month total already
at its ceiling; and, in either mode, a home whose rendered files differ from
the render's record or that holds `run-open.json`. A capability (32 random
bytes as hex) goes into the session as `KIT_RELAY_CAPABILITY`, another into
the canary. After the canary passed, the relay starts (this interpreter,
isolated, its environment from the allow list, the key and capability as its
first line of standard input, its standard error into
`runs/<id>/relay-stderr.txt`, its tree in a Job Object on Windows and a new
session on POSIX) and its ready line is awaited for at most 10 seconds; a
relay that is not ready sets `outcome` to `refused-relay`, exits 70 and
starts no session. Then the home is read again and the session starts. However
it ended, the relay's standard input is closed, it gets at most 40 seconds to
end, its tree is ended, and `run.json` gets `relay` with `requests`, `refused`,
`settled_usd` and `stopped`. The session's git reads the run's copy of the
home's `gitconfig`.

Governance of the session's configuration. `run.json` records `protected`,
the paths kit protects from the session's tools (the home's configuration
and shell folders, `home.json`, `run-open.json`, a daily home's `gitconfig`
and daily file, the state root, the policy file, the judge's import surface,
the project-config names in the working folder and every folder of the
project walk, opencode's system configuration folder, and the account's
Claude Code home and opencode configuration folder), `protected_except` (the
run's `tmp` folder) and `policy_sha256`, which the judge's built-in rule
`config.protected` reads. The judge's import surface is read once the
policy's checkers are loaded in kit's own process: the folder that holds
`harness_kit` and each folder a checker put on `sys.path`, the files of the
modules the checkers loaded outside the standard library, and, from the
judge's own interpreter started with `-I`, its `sys.prefix`,
`sys.base_prefix`, site-packages folders, `sys.path` and the modules its
startup loads; never kit's own `sys.path`, `PYTHONPATH`, user site or
working folder. In interactive mode and for a daily home a home whose
`shell_config.json` names a judge other than this kit's is refused, and so is
a project-config name in the working folder; opencode's system configuration
folder is refused in every mode. From the session's start to its end, and
once more after its tree ended, a thread reads every 2 seconds the names,
sizes and modification times of the home's watched files, `run-open.json`,
the daily file, the policy file, the kit's package folder, the judge's import
surface, `run.json`, the files the driver watches during a run, the
project-config names of the walk and the system folder; a difference ends
the session's tree, sets `outcome` to `config-changed` and `config_changed`
to the changed names, writes `config-changed.json` (`run_id` and `carried`,
the changed paths outside the home and the run's folder) beside `home.json`
and exits 66. A home that holds `config-changed.json` is refused.

Native permissions. For a driver that renders the harness's own permissions from
the policy's `[permissions]` section (opencode), preflight renders them again
from the policy and refuses, with exit 64 and no run, a section that would
refuse either of the canary's calls before kit's hook sees it (naming the rule),
a home whose recorded `permissions_sha256` differs from the fresh render (a
policy changed after the render) and a home whose configuration does not parse
or holds other permissions or policies, in every mode and for every kind of
home. Claude Code renders nothing from the section and is not compared.

Exit codes: 64 a refusal, 65 a failed canary or a home changed before the
session, 66 a configuration changed during the session, 70 an internal error
or a relay that did not get ready, 130 an interrupt before the session, else
the harness's own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import tomllib

import harness_kit
from harness_kit import canary, checkers, daily, doctor, harnesses, packs, relay, state, watch
from harness_kit.policy import Policy, PolicyError, load_policy

EXIT_REFUSED = 64
EXIT_CANARY = 65
EXIT_CHANGED = 66
EXIT_INTERNAL = 70
EXIT_INTERRUPTED = 130
WINDOWS = os.name == 'nt'
HEADLESS, INTERACTIVE = harnesses.HEADLESS, harnesses.INTERACTIVE
# Names an interactive session also receives from kit's environment, when it has them.
TERMINAL_NAMES = (
    'TERM',
    'COLORTERM',
    'TERM_PROGRAM',
    'TERM_PROGRAM_VERSION',
    'WT_SESSION',
    'WT_PROFILE_ID',
    'LANG',
    'LC_ALL',
    'LC_CTYPE',
    'TZ',
    'NO_COLOR',
)
# How long kit waits for the session's tree to be gone once it ended it.
TREE_WAIT_S = 10.0
# The relay of a daily run: how long kit awaits its ready line, and its end once its standard
# input is closed; where its standard error goes; the session's capability variable.
RELAY_READY_S = 10.0
RELAY_STOP_S = 40.0
RELAY_STDERR = 'relay-stderr.txt'
RELAY_POLL_S = 0.05
CAPABILITY_ENV = harnesses.RELAY_CAPABILITY_ENV
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: the relay gets no console, so no console interrupt
CLAUDE_CODE = 'claude-code'
FAKE_KEY = 'stub-not-a-key'
# The check during the run: how often it reads, how many changed names a record holds, and
# what kit writes to its terminal when it ended an interactive session (leave the alternate
# screen, show the cursor, reset the attributes, mouse and paste modes).
CHECK_POLL_S = 2.0
CHANGED_MAX = 20
TERMINAL_RESET = (
    '\x1b[0m\x1b[?25h\x1b[?1049l\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?2004l\r\n'
)

# Names a child inherits from kit's environment, beside PATH and what the driver sets.
ALLOW = (
    'SYSTEMROOT',
    'WINDIR',
    'SYSTEMDRIVE',
    'COMSPEC',
    'PATHEXT',
    'OS',
    'NUMBER_OF_PROCESSORS',
    'PROCESSOR_ARCHITECTURE',
    'PROCESSOR_IDENTIFIER',
    'PROCESSOR_LEVEL',
    'PROCESSOR_REVISION',
    'PROGRAMDATA',
    'PROGRAMFILES',
    'PROGRAMFILES(X86)',
    'PROGRAMW6432',
    'COMMONPROGRAMFILES',
    'COMMONPROGRAMFILES(X86)',
    'COMMONPROGRAMW6432',
    'ALLUSERSPROFILE',
    'PUBLIC',
    'COMPUTERNAME',
    'USERDOMAIN',
    'USERNAME',
    'PATH',
)
# On Windows these select programs or configuration layers; they come from the system.
WINDOWS_PINNED = ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PROGRAMDATA', 'PATHEXT')
SECRET_NAME = re.compile(r'(^GH_(?!CONFIG_DIR$)|_KEY$|_TOKEN$|_SECRET$|_PASSWORD$)', re.IGNORECASE)
# Each drops hooks or instruction files whatever its value.
GUARD_DROPPERS = ('CLAUDE_CODE_SIMPLE', 'CLAUDE_CODE_DISABLE_CLAUDE_MDS')
NO_PUSH = ('no_push', 'DISABLED', '')
REMOTE_KEYS = r'^remote\..*\.(url|pushurl)$'
GIT_TIMEOUT_S = 30
USERINFO = re.compile(r'^([a-z][a-z0-9+.-]*://)[^/@]*@', re.IGNORECASE)
# The governed-home override a recording policy may pass into a session under a test root.
GOVERNED_HOME = 'SESSION_WORKFLOW_GOVERNED_HOME'
RENDER_HINT = 'render the home with kit home render --policy'
# The note entries a Claude Code home registers per recorded kind; a result entry's matcher
# is the shell tools' or every tool's.
CLAUDE_NOTE_EVENTS = {
    'prompt': {'UserPromptSubmit': (None,)},
    'outcome': {
        'PostToolUse': ('Bash|PowerShell', '*'),
        'PostToolUseFailure': ('Bash|PowerShell', '*'),
    },
}


class RefusalError(Exception):
    """A preflight refusal; the message is one ASCII line."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise RefusalError(f'arguments: {message}')


@dataclass
class DailyRun:
    """What a daily run holds besides its plan: the daily file, the key until the relay read it,
    and the two capabilities, the session's and the canary's."""

    found: daily.Daily
    key: str | None
    capability: str
    canary_capability: str


@dataclass
class Plan:
    driver: harnesses.Driver
    home: dict
    workdir: Path
    policy_path: Path
    root: Path
    run_id: str
    run_dir: Path
    argv: list[str]
    env: dict[str, str]
    remotes: list[dict] = field(default_factory=list)
    project_config: list[str] = field(default_factory=list)
    scrubbed: list[str] = field(default_factory=list)
    binary: list[str] = field(default_factory=list)
    # Variables passed into the session beside the allow list, and stderr lines for a launch.
    extra_env: dict[str, str] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)
    # The session mode, the top of the working folder's work tree, the terminal names passed
    # into an interactive session, and the folder that holds `home.json`.
    mode: str = HEADLESS
    top: Path | None = None
    terminal: dict[str, str] = field(default_factory=dict)
    home_dir: Path | None = None
    # A daily run's file, key and capabilities, and the variables only the canary gets.
    daily: DailyRun | None = None
    canary_extra: dict[str, str] = field(default_factory=dict)
    # The paths kit protects from the session's tools, their exception, the policy's hash, and
    # what the check during the run reads.
    protected: list[str] = field(default_factory=list)
    protected_except: list[str] = field(default_factory=list)
    policy_sha256: str | None = None
    watch: watch.RunWatch | None = None
    # The harness version the version probe read, and the one `--accept-version` named.
    version_found: str | None = None
    accepted_version: str | None = None


def _ascii(text: object) -> str:
    return str(text).encode('ascii', 'backslashreplace').decode('ascii').replace('\n', ' ')


def _key(name: str) -> str:
    return name.upper() if WINDOWS else name


def _norm(path: Path | str) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def _within(path: Path | str, base: Path | str) -> bool:
    """True when `path` is `base` or below it; both are resolved first."""
    p, b = _norm(path), _norm(base)
    return p == b or p.startswith(b.rstrip(os.sep) + os.sep)


# ---- git


def child_environ(environ: dict) -> dict:
    """`environ` without the names the secret-name rule would refuse in a session."""
    return {k: v for k, v in environ.items() if not SECRET_NAME.search(k)}


def _git(folder: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess | None:
    base = os.environ if env is None else env
    env = {k: v for k, v in base.items() if not k.upper().startswith('GIT_')}
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            ['git', '-C', str(folder), *args],  # noqa: S607 - PATH git
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def work_tree_top(folder: Path, env: dict | None = None) -> Path | None:
    """The top of the git work tree holding `folder`, or None outside any.

    A `.git` entry in the folder or an ancestor that git does not answer for
    is a refusal: the launcher cannot tell which remotes it would push to.
    git takes `env` (kit's own environment when None), less the `GIT_` names.
    """
    proc = _git(folder, 'rev-parse', '--show-toplevel', env=env)
    if proc is not None and proc.returncode == 0 and proc.stdout.strip():
        return Path(os.path.realpath(proc.stdout.strip()))
    for place in (folder, *folder.parents):
        if os.path.lexists(place / '.git'):
            raise RefusalError(f'git could not read the work tree at {_ascii(place)}')
    return None


def read_remotes(folder: Path, env: dict | None = None) -> list[dict]:
    """Every remote with its `url` and `pushurl` values, and whether it can push."""
    proc = _git(folder, 'config', '--get-regexp', REMOTE_KEYS, env=env)
    if proc is None or proc.returncode not in (0, 1):
        raise RefusalError(f'git could not read the remotes of {_ascii(folder)}')
    if proc.returncode == 1 and not proc.stdout.strip():
        return []
    remotes: dict[str, dict[str, list[str]]] = {}
    for line in proc.stdout.splitlines():
        if not line:
            continue
        key, _, value = line.partition(' ')
        name, _, var = key[len('remote.') :].rpartition('.')
        entry = remotes.setdefault(name, {'url': [], 'pushurl': []})
        entry[var.lower()].append(value)
    out = []
    for name, entry in remotes.items():
        effective = entry['pushurl'] or entry['url']
        out.append(
            {
                'name': name,
                'url': [USERINFO.sub(r'\1***@', v) for v in entry['url']],
                'pushurl': [USERINFO.sub(r'\1***@', v) for v in entry['pushurl']],
                'pushable': any(v not in NO_PUSH for v in effective),
            }
        )
    return out


# ---- the checks


def check_home(home_dir: Path, driver: harnesses.Driver) -> dict:
    """The home's `home.json`, which must parse and name this harness."""
    path = home_dir / 'home.json'
    try:
        home = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise RefusalError(f'no rendered home: {_ascii(path)} is absent or unreadable') from None
    ok = isinstance(home, dict) and home.get('kit_home') == 1
    ok = ok and all(isinstance(home.get(k), str) for k in harnesses.HOME_KEYS[1:])
    if not ok:
        raise RefusalError(f'home.json at {_ascii(path)} is not a rendered home')
    if home['harness'] != driver.name:
        raise RefusalError(f'home.json names harness {home["harness"]!a}, not {driver.name}')
    return home


def check_folder(workdir: Path, top: Path | None, remotes: list[dict], policy: Policy) -> None:
    """Folder and remote, for every harness but Claude Code."""
    launcher = policy.launcher
    for root in launcher.get('forbidden_roots', []):
        if root and _within(workdir, root):
            raise RefusalError(f'working folder is under the forbidden root {_ascii(root)}')
    if top is not None:
        pushable = [r['name'] for r in remotes if r['pushable']]
        if pushable:
            raise RefusalError(f'remote {pushable[0]!a} of the work tree can push')
        return
    if not any(root and _within(workdir, root) for root in launcher.get('test_roots', [])):
        raise RefusalError(f'working folder {_ascii(workdir)} is outside the test roots')


def grammar_of(driver: harnesses.Driver, mode: str) -> harnesses.Grammar | None:
    """The driver's grammar for `mode`, or None when it offers no such mode."""
    modes = getattr(driver, 'modes', None)
    if modes is not None:
        return modes.get(mode)
    if mode != HEADLESS:
        return None
    return harnesses.Grammar(
        leading=tuple(driver.required_leading_tokens),
        required=tuple(driver.required_session_args),
        allowed=tuple(driver.allowed_session_flags),
    )


def check_session_args(args: list[str], driver: harnesses.Driver, mode: str = HEADLESS) -> None:
    """Refuse arguments outside the driver's grammar for `mode`; the harness's own is not parsed."""
    grammar = grammar_of(driver, mode)
    if grammar is None:
        raise RefusalError(f'harness {driver.name} offers no {_ascii(mode)} mode')
    if grammar.flags is not None:
        _check_flag_table(args, grammar, driver.name, mode)
        return
    lead = tuple(grammar.leading)
    if tuple(args[: len(lead)]) != lead:
        raise RefusalError(f'harness arguments must start with {" ".join(lead)}')
    need = tuple(grammar.required)
    if not any(tuple(args[i : i + len(need)]) == need for i in range(len(args))):
        raise RefusalError(f'harness arguments lack {" ".join(need)}')
    for token in need:
        if token.startswith('-') and args.count(token) != 1:
            raise RefusalError(f'harness arguments give {token} more than once')
    for token in args:
        if token.startswith('-') and token not in grammar.allowed:
            raise RefusalError(
                f'flag {_ascii(token)} is not in the allow list of {driver.name}: '
                + ' '.join(grammar.allowed)
            )


def _check_flag_table(args: list[str], grammar: harnesses.Grammar, name: str, mode: str) -> None:
    """Walk the arguments in order: each is a flag of the table or the value its flag takes."""
    table = dict(grammar.flags or ())
    seen: dict[str, int] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token not in table:
            raise RefusalError(
                f'harness argument {_ascii(token)} is not in the {mode} grammar of {name}: '
                + ' '.join(table)
            )
        if table[token]:
            if i + 1 >= len(args):
                raise RefusalError(f'flag {token} of the {mode} grammar takes a value')
            i += 1
        seen[token] = seen.get(token, 0) + 1
        i += 1
    for token in grammar.required:
        if not seen.get(token):
            raise RefusalError(f'harness arguments lack {token}')
        if seen[token] > 1:
            raise RefusalError(f'harness arguments give {token} more than once')


def check_mode(driver: harnesses.Driver, mode: str, windows: bool | None = None) -> list[str]:
    """Refuse a mode the driver does not offer, interactive mode off Windows, or a mode the
    harness's contract records `absent`; a line per mode the contract does not name."""
    if grammar_of(driver, mode) is None:
        raise RefusalError(f'harness {driver.name} offers no {_ascii(mode)} mode')
    if mode == HEADLESS:
        return []
    if not (WINDOWS if windows is None else windows):
        raise RefusalError(f'{mode} mode runs on Windows only')
    try:
        entries = doctor.load_contract(driver.name).get('modes')
    except (OSError, ValueError, KeyError) as exc:
        raise RefusalError(f'the contract of {driver.name} is unreadable: {_ascii(exc)}') from None
    entry = entries.get(mode) if isinstance(entries, dict) else None
    if not isinstance(entry, dict) or 'state' not in entry:
        return [f'kit: the contract of {driver.name} records no state for {mode} mode; starting it']
    if entry['state'] == 'absent':
        raise RefusalError(f'the contract of {driver.name} records {mode} mode as absent')
    return []


def check_version(driver: harnesses.Driver, found: str | None, accepted: str | None) -> list[str]:
    """Refuse a harness version other than the contract's unless `--accept-version` names the
    version found, and refuse an accepted version that is not the one found; for a launch the
    option allows, the line that says the run is not covered by the contract."""
    try:
        pinned = driver.pinned_version
    except (OSError, ValueError) as exc:
        raise RefusalError(f'the contract of {driver.name} is unreadable: {_ascii(exc)}') from None
    shown = found or 'not found'
    if accepted is not None and accepted != found:
        raise RefusalError(
            f'--accept-version {_ascii(accepted)} does not name the {driver.name} version '
            f'found, {shown}; it names only the version the binary reports'
        )
    if found == pinned:
        return []
    if found is None:
        raise RefusalError(
            f'{driver.name} version not found: its --version printed no version, and the '
            f"contract's is {pinned}; a version kit cannot read cannot be accepted"
        )
    if accepted is None:
        raise RefusalError(
            f"{driver.name} version {found} differs from the contract's {pinned}; re-pin "
            'the harness (README, "Re-pinning a harness version") or name the version with '
            f'--accept-version {found}'
        )
    return [
        f'kit: this run is not covered by the contract: {driver.name} version {found} is not '
        f"the contract's {pinned}; starting it because --accept-version names it"
    ]


def check_open_run(home_dir: Path) -> None:
    """Refuse a home that holds `run-open.json`: a run whose end kit did not record."""
    path = home_dir / watch.RUN_OPEN
    if not os.path.lexists(path):
        return
    data = _read_object(path)
    run_id = data.get('run_id') if data is not None else None
    named = _ascii(run_id) if isinstance(run_id, str) and run_id else 'unknown'
    raise RefusalError(
        f'the home holds {watch.RUN_OPEN} of run {named}: kit did not record its end (kit was '
        'ended or its terminal closed), so a change in its last poll may be unread; render a '
        'new home'
    )


def check_render_record(home_dir: Path, home: dict, driver: harnesses.Driver) -> None:
    """Refuse a home whose rendered files differ from the record of its render."""
    record = home.get(watch.RENDERED_KEY)
    if not isinstance(record, dict):
        raise RefusalError(
            'home.json holds no record of the rendered files; render the home again into an '
            'empty folder'
        )
    changed = watch.differences(record, watch.hash_files(home_dir, driver, rendered=True))
    if changed:
        more = f' and {len(changed) - 1} more' if len(changed) > 1 else ''
        raise RefusalError(
            f'the home differs from its render at {_ascii(changed[0])}{more}; render the home '
            'again into an empty folder'
        )


def _same_path(a: object, b: object) -> bool:
    return isinstance(a, str) and isinstance(b, str) and watch.norm(a) == watch.norm(b)


def check_config_changed(home_dir: Path) -> None:
    """Refuse a home that holds `config-changed.json`: a session changed its configuration.

    It is read before the policy, so a policy the session edited into an unreadable one still
    gets this refusal, which names it.
    """
    path = home_dir / watch.CONFIG_CHANGED
    if not os.path.lexists(path):
        return
    home = _read_object(home_dir / watch.HOME_JSON) or {}
    data = _read_object(path) or {}
    run_id = data.get('run_id')
    named = _ascii(run_id) if isinstance(run_id, str) and run_id else 'unknown'
    carried = data.get('carried')
    carried = [c for c in carried if isinstance(c, str)] if isinstance(carried, list) else []
    text = (
        f'the home holds {watch.CONFIG_CHANGED} of run {named}: its session changed the '
        'configuration it ran under, so the home starts no session'
    )
    if carried:
        text += (
            '; each of '
            + ', '.join(_ascii(c) for c in carried)
            + ' changed during that run and carries into a new home: read or restore it '
            'before rendering a new home'
        )
    else:
        text += '; render a new home'
    daily_file, settings = home.get('daily_file'), home.get('daily_settings')
    if any(_same_path(c, daily_file) for c in carried) and isinstance(settings, dict):
        try:
            data_bytes = Path(daily_file).read_bytes()
        except OSError:
            text += f'; the daily file {_ascii(daily_file)} is not readable'
        else:
            text += '; ' + _daily_differs(daily_file, data_bytes, settings)
    raise RefusalError(text)


def check_cli_argv(home: dict, driver: harnesses.Driver) -> None:
    """Refuse a home whose `shell_config.json` starts a judge other than the one this kit renders."""
    source = driver.name if callable(getattr(driver, 'translate_event', None)) else None
    config = _read_object(Path(home['shell_config']))
    found = config.get('cli_argv') if config is not None else None
    if found != harnesses.cli_argv(source):
        raise RefusalError(
            "the home's shell_config.json names a cli_argv other than this kit's judge; render "
            'the home with this kit'
        )


def check_permissions(home: dict, driver: harnesses.Driver, policy: Policy) -> None:
    """Refuse a home whose harness permissions differ from what the policy renders now.

    Only a driver that renders the harness's own permissions compares them; the others
    render nothing from the policy's `[permissions]` section.
    """
    compare = getattr(driver, 'permissions_refusal', None)
    if not callable(compare):
        return
    reason = compare(home, policy.permissions)
    if reason is not None:
        raise RefusalError(_ascii(reason))


def terminal_env(environ: dict) -> dict[str, str]:
    """The terminal names kit's environment holds, in the order of TERMINAL_NAMES."""
    found = {_key(k): v for k, v in environ.items()}
    return {name: found[_key(name)] for name in TERMINAL_NAMES if _key(name) in found}


def project_walk(driver: harnesses.Driver, workdir: Path, top: Path | None, root: Path) -> list:
    """The ancestors the driver's walk reads, the working folder left out."""
    if driver.project_walk == 'work_tree':
        if top is None:
            return []
        walk = []
        for parent in workdir.parents:
            if not _within(parent, top):
                break
            walk.append(parent)
        return walk
    if driver.project_walk == 'root':
        runs = root / 'runs'
        return [*workdir.parents, runs, *runs.parents]
    raise RefusalError(f'driver {driver.name} has an unknown project walk {driver.project_walk!a}')


def check_project_layer(
    driver: harnesses.Driver,
    workdir: Path,
    top: Path | None,
    root: Path,
    *,
    refuse_workdir: bool = False,
) -> list[str]:
    """Refuse a project-config path in an ancestor, and with `refuse_workdir` one in the
    working folder; return those in the working folder."""
    for folder in project_walk(driver, workdir, top, root):
        for entry in driver.project_config_paths:
            if os.path.lexists(folder / entry):
                raise RefusalError(f'project config {_ascii(folder / entry)} lies in an ancestor')
    found = [e for e in driver.project_config_paths if os.path.lexists(workdir / e)]
    if refuse_workdir and found:
        raise RefusalError(
            f'project config {_ascii(workdir / found[0])} lies in the working folder; interactive '
            'mode and daily homes refuse it'
        )
    return found


def system_folder(driver: harnesses.Driver) -> Path | None:
    """The harness's system configuration folder as its driver names it, or None."""
    method = getattr(driver, 'system_config_dir', None)
    if method is None:
        return None
    try:
        return Path(method())
    except OSError as exc:
        raise RefusalError(
            f'the system configuration folder of {driver.name} could not be read: {_ascii(exc)}'
        ) from None


def check_system_layer(driver: harnesses.Driver) -> Path | None:
    """Refuse a system configuration folder of the harness that exists; return its path."""
    folder = system_folder(driver)
    if folder is not None and os.path.lexists(folder):
        raise RefusalError(
            f'the system {driver.name} configuration folder {_ascii(folder)} exists; kit run '
            'refuses it'
        )
    return folder


# ---- a policy that records notes


def check_note_states(policy: Policy, driver: harnesses.Driver, records: tuple) -> list[str]:
    """Refuse a recorded kind the contract gives as `absent`; a line per kind it does not name."""
    try:
        entries = doctor.load_contract(driver.name).get('notes')
    except (OSError, ValueError, KeyError) as exc:
        raise RefusalError(f'the contract of {driver.name} is unreadable: {_ascii(exc)}') from None
    entries = entries if isinstance(entries, dict) else {}
    notices = []
    for kind in records:
        entry = entries.get(kind)
        if not isinstance(entry, dict) or 'state' not in entry:
            notices.append(
                f'kit: the contract of {driver.name} records no state for {kind} notes; starting it'
            )
            continue
        if entry['state'] != 'absent':
            continue
        for checker in policy.checkers:
            if kind in checker.records:
                rules = [r.id for r in policy.rules if r.check == checker.id]
                raise RefusalError(
                    f'checker {checker.id!a} (rules {", ".join(rules) or "none"}) records '
                    f'{kind} notes, whose state on {driver.name} is absent'
                )
    return notices


def _read_object(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _note_config_ok(config: dict | None, records: tuple) -> bool:
    if config is None or config.get('kit_note_config') != 1:
        return False
    argv, timeout, kinds = config.get('note_argv'), config.get('timeout_s'), config.get('records')
    ok = isinstance(argv, list) and bool(argv) and all(isinstance(a, str) for a in argv)
    ok = ok and type(timeout) in (int, float) and timeout > 0
    ok = ok and isinstance(kinds, list) and all(k in harnesses.NOTE_KINDS for k in kinds)
    return ok and all(kind in kinds for kind in records)


def _has_note_entry(groups: object, matchers: tuple) -> bool:
    """True when a hook group with an allowed matcher holds a `--note` command entry."""
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict) or group.get('matcher') not in matchers:
            continue
        hooks = group.get('hooks')
        for hook in hooks if isinstance(hooks, list) else []:
            if not isinstance(hook, dict) or hook.get('type') != 'command':
                continue
            args = hook.get('args')
            if isinstance(args, list) and args[-1:] == ['--note']:
                return True
    return False


def check_note_home(home: dict, driver: harnesses.Driver, records: tuple) -> None:
    """Refuse a home whose note configuration does not carry every recorded kind."""
    config = _read_object(Path(home['shell_config']).parent / harnesses.NOTE_CONFIG)
    if not _note_config_ok(config, records):
        raise RefusalError(
            f'the home has no {harnesses.NOTE_CONFIG} for {", ".join(records)} notes; {RENDER_HINT}'
        )
    if driver.name != CLAUDE_CODE:
        return
    settings = _read_object(Path(home['config_file']))
    hooks = settings.get('hooks') if settings is not None else None
    hooks = hooks if isinstance(hooks, dict) else {}
    for kind in records:
        for event, matchers in CLAUDE_NOTE_EVENTS[kind].items():
            if not _has_note_entry(hooks.get(event), matchers):
                raise RefusalError(f'settings.json has no {event} note entry; {RENDER_HINT}')


# ---- a daily home


def take_key(environ: dict, name: str) -> str | None:
    """The value of `name` in kit's environment, removed from it and from `environ`."""
    value = None
    for key in [k for k in environ if _key(k) == _key(name)]:
        found = environ.pop(key)
        value = value or found
    for key in [k for k in os.environ if _key(k) == _key(name)]:
        found = os.environ.pop(key)
        value = value or found
    return value


def port_free(port: int) -> bool:
    """True when nothing is bound on 127.0.0.1:`port`, bound as the relay binds it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def relay_lock_holder(root: Path) -> str | None:
    """The pid that holds the relay lock of the state root (`unknown` when unnamed), or None."""
    path = root / 'relay' / relay.LOCK
    try:
        fd = os.open(path, os.O_RDWR | getattr(os, 'O_BINARY', 0))
    except FileNotFoundError:
        return None
    try:
        if relay._try_lock(fd):
            relay._unlock(fd)
            return None
        return relay._holder(fd)
    finally:
        os.close(fd)


def _daily_differs(path: str, data: bytes, settings: dict) -> str:
    """The refusal of a daily file whose bytes differ from the render's: the keys that differ."""
    tail = 'read the file before rendering the home again'
    try:
        doc = tomllib.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return f'the daily file {_ascii(path)} differs from its render and is not TOML; {tail}'
    keys = daily.changed_keys(settings, {k: v for k, v in doc.items() if k != 'daily'})
    if doc.get('daily') != 1:
        keys = ['daily', *keys]
    named = ', '.join(_ascii(k) for k in keys) if keys else 'no value, only its bytes'
    return f'the daily file {_ascii(path)} differs from its render at {named}; {tail}'


def check_daily(home: dict, root: Path, environ: dict) -> DailyRun:
    """Every check of a daily home but its render; the key is taken out of kit's environment."""
    path, sha, settings = (
        home.get('daily_file'),
        home.get('daily_sha256'),
        home.get('daily_settings'),
    )
    if not (isinstance(path, str) and path and isinstance(sha, str) and isinstance(settings, dict)):
        raise RefusalError(
            'home.json of a daily home lacks daily_file, daily_sha256 or daily_settings; render '
            'the home again into an empty folder'
        )
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        raise RefusalError(
            f'the daily file {_ascii(path)} is absent; restore it, or render a new home'
        ) from None
    except OSError as exc:
        raise RefusalError(
            f'the daily file {_ascii(path)} is not readable: {_ascii(exc)}'
        ) from None
    if hashlib.sha256(data).hexdigest() != sha:
        raise RefusalError(_daily_differs(path, data, settings))
    try:
        found = daily.load_daily(path, root)
    except daily.DailyError as exc:
        raise RefusalError(f'daily file refused: {_ascii(exc)}') from None
    name, port = found.relay.key_env, found.relay.listen_port
    key = take_key(environ, name)
    if not key:
        raise RefusalError(f'the key variable {name} of the daily file is absent or empty')
    if not port_free(port):
        raise RefusalError(f'the relay port 127.0.0.1:{port} is already bound')
    holder = relay_lock_holder(root)
    if holder is not None:
        raise RefusalError(f'the relay lock of the state root is held by pid {holder}')
    try:
        totals = relay.fold(relay.read_ledger(root))
    except OSError as exc:
        raise RefusalError(f'the relay ledger is not readable: {_ascii(exc)}') from None
    now, held = datetime.now(timezone.utc), totals.open_usd()
    for label, total, ceiling in (
        ('day', totals.day.get(now.strftime('%Y-%m-%d'), 0.0), found.relay.day_usd),
        ('month', totals.month.get(now.strftime('%Y-%m'), 0.0), found.relay.month_usd),
    ):
        if total + held >= ceiling - relay.EPSILON_USD:
            raise RefusalError(
                f'the relay ledger holds {total + held:.6f} USD this {label}, at its ceiling of '
                f'{ceiling} USD'
            )
    return DailyRun(found, key, secrets.token_hex(32), secrets.token_hex(32))


def governed_home(policy: Policy, environ: dict) -> dict[str, str]:
    """The governed-home override to pass into the session; refused outside the test roots."""
    found = [(k, v) for k, v in environ.items() if _key(k) == _key(GOVERNED_HOME)]
    if not found:
        return {}
    value = found[0][1]
    roots = policy.launcher.get('test_roots', [])
    if not value or not any(root and _within(value, root) for root in roots):
        raise RefusalError(f'{GOVERNED_HOME} lies under no test root of the policy')
    return {GOVERNED_HOME: value}


# ---- the judge's import surface and the protected paths

# What each checker's first load in this process put on `sys.path` and loaded, by module name.
_CHECKER_LOADS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}


def _dedupe(items) -> list[str]:
    seen, out = set(), []
    for item in items:
        text = os.path.abspath(str(item))
        key = watch.norm(text)
        if key not in seen:
            seen.add(key)
            out.append(text)
    return out


def load_checkers(policy: Policy) -> tuple[list[str], list[str]]:
    """Load the policy's checkers as the judge would, in this process.

    Return the folders their loads put on `sys.path` (`sys.path` read before and after each
    load, so never this process's own entries) and the files of the checkers and of the
    modules their loads imported. Raise RefusalError naming the first unusable checker.
    """
    folders: list[str] = []
    files: list[str] = []
    for checker in policy.checkers:
        name = checkers.module_name(checker)
        path_before, modules_before = list(sys.path), set(sys.modules)
        broken = packs.verify_checkers([checker])
        if broken is not None:
            raise RefusalError(f'policy checker unusable: {_ascii(broken)}')
        if name not in _CHECKER_LOADS:
            added = tuple(p for p in sys.path if p and p not in path_before)
            loaded = tuple(
                module.__file__
                for key, module in list(sys.modules.items())
                if key not in modules_before and isinstance(getattr(module, '__file__', None), str)
            )
            _CHECKER_LOADS[name] = (added, loaded)
        added, loaded = _CHECKER_LOADS[name]
        folders.extend(added)
        files.extend([checker.path, *loaded])
    return folders, files


@dataclass
class Surface:
    """The judge's import surface: the folders ahead of the standard library on its path, the
    files of the modules it loads outside the standard library, its interpreter's prefixes,
    site-packages folders and whole path, and the kit's package folder."""

    package: str
    folders: list[str]
    files: list[str]
    prefixes: list[str]
    site_packages: list[str]
    path: list[str]

    def outside_files(self) -> list[str]:
        return [f for f in self.files if not watch.under_any(f, self.folders)]


def import_surface(added: list[str], loaded: list[str], environ: dict) -> Surface:
    """The judge's import surface: what the checkers' loads gave, and the judge's interpreter."""
    try:
        found = watch.read_interpreter(harnesses.cli_argv()[0], child_environ(environ))
    except watch.SurfaceError as exc:
        raise RefusalError(f"the judge's import surface could not be read: {_ascii(exc)}") from None
    package = Path(harness_kit.__file__).resolve().parent
    folders = _dedupe([package.parent, *added])
    stdlib = [p for p in found['stdlib'] if isinstance(p, str)]
    files = _dedupe(f for f in [*loaded, *found['files']] if not watch.under_any(f, stdlib))
    return Surface(
        package=str(package),
        folders=folders,
        files=files,
        prefixes=_dedupe([found['prefix'], found['base_prefix']]),
        site_packages=_dedupe(p for p in found['site_packages'] if isinstance(p, str)),
        path=_dedupe([*folders, *(p for p in found['path'] if isinstance(p, str))]),
    )


def _env_value(environ: dict, name: str) -> str:
    found = [v for k, v in environ.items() if _key(k) == _key(name)]
    return found[0] if found else ''


def account_homes(environ: dict) -> list[str]:
    """The account's Claude Code home and opencode configuration folder, from kit's own
    environment."""
    profile = _env_value(environ, 'USERPROFILE' if WINDOWS else 'HOME') or os.path.expanduser('~')
    claude = _env_value(environ, 'CLAUDE_CONFIG_DIR')
    if not claude.strip():
        claude = os.path.join(profile, '.claude')
    opencode = _env_value(environ, 'OPENCODE_CONFIG_DIR')
    if not opencode:
        xdg = _env_value(environ, 'XDG_CONFIG_HOME')
        opencode = (
            os.path.join(xdg, 'opencode') if xdg else os.path.join(profile, '.config', 'opencode')
        )
    return [claude, opencode]


def walked_folders(driver: harnesses.Driver, workdir: Path, top: Path | None, root: Path) -> list:
    """The working folder and every folder the driver's project walk reads."""
    out, seen = [], set()
    for folder in (workdir, *project_walk(driver, workdir, top, root)):
        key = watch.norm(folder)
        if key not in seen:
            seen.add(key)
            out.append(Path(folder))
    return out


def protected_paths(
    driver: harnesses.Driver,
    home_dir: Path,
    *,
    daily_file: str | None,
    root: Path,
    policy_path: Path,
    surface: Surface,
    walked: list,
    system: Path | None,
    environ: dict,
) -> list[str]:
    """The paths a launched write tool may not reach, in the order `run.json` lists them."""
    items: list = [home_dir / name for name in getattr(driver, 'protected_folders', ())]
    items += [home_dir / watch.HOME_JSON, home_dir / watch.RUN_OPEN]
    if daily_file is not None:
        items += [home_dir / 'gitconfig', daily_file]
    items += [root, policy_path, *surface.folders, *surface.outside_files(), *surface.prefixes]
    items += [folder / e for folder in walked for e in driver.project_config_paths]
    items += [walked[0] / n for n in getattr(driver, 'protected_workdir_names', ())]
    items += [system] if system is not None else []
    items += account_homes(environ)
    return _dedupe(items)


def run_watch(plan: Plan, surface: Surface, walked: list, system: Path | None) -> watch.RunWatch:
    """What the check during the run reads, besides the home's watched files."""
    home_dir = _home_dir(plan)
    files = [str(home_dir / watch.RUN_OPEN), str(plan.policy_path), str(plan.run_dir / 'run.json')]
    if plan.daily is not None:
        files.append(str(plan.daily.found.path))
    files += surface.files
    presence = [os.path.join(f, n) for f in surface.path for n in watch.STARTUP_NAMES]
    presence += [str(f / e) for f in walked for e in plan.driver.project_config_paths]
    presence += [str(system)] if system is not None else []
    trees = [surface.package]
    trees += [str(home_dir / n) for n in getattr(plan.driver, 'run_watched_folders', ())]
    return watch.RunWatch(
        home=home_dir,
        driver=plan.driver,
        files=_dedupe(files),
        trees=trees,
        name_sets=list(surface.folders),
        pth_folders=list(surface.site_packages),
        presence=presence,
    )


# ---- the environment


def windows_pins() -> dict[str, str]:
    """SYSTEMROOT, WINDIR, COMSPEC, PROGRAMDATA and PATHEXT as the operating system has them."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    shell32 = ctypes.WinDLL('shell32')
    ole32 = ctypes.WinDLL('ole32')
    advapi32 = ctypes.WinDLL('advapi32')

    buf = ctypes.create_unicode_buffer(32768)
    kernel32.GetSystemWindowsDirectoryW.argtypes = (wintypes.LPWSTR, wintypes.UINT)
    kernel32.GetSystemWindowsDirectoryW.restype = wintypes.UINT
    n = kernel32.GetSystemWindowsDirectoryW(buf, len(buf))
    if n == 0 or n >= len(buf):
        raise OSError('GetSystemWindowsDirectoryW failed')
    windir = buf.value

    class GUID(ctypes.Structure):
        _fields_ = (
            ('Data1', wintypes.DWORD),
            ('Data2', wintypes.WORD),
            ('Data3', wintypes.WORD),
            ('Data4', ctypes.c_ubyte * 8),
        )

    program_data_id = GUID(
        0x62AB5D82,
        0xFDC1,
        0x4DC3,
        (ctypes.c_ubyte * 8)(0xA9, 0xDD, 0x07, 0x0D, 0x1D, 0x49, 0x5D, 0x97),
    )
    shell32.SHGetKnownFolderPath.argtypes = (
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_void_p),
    )
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    found = ctypes.c_void_p()
    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(program_data_id), 0, None, ctypes.byref(found)
    )
    try:
        if result != 0 or not found.value:
            raise OSError(f'SHGetKnownFolderPath failed: {result & 0xFFFFFFFF:#x}')
        program_data = ctypes.wstring_at(found.value)
    finally:
        if found.value:
            ole32.CoTaskMemFree(found)

    hklm = ctypes.c_void_p(ctypes.c_long(0x80000002).value)
    subkey = r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
    rrf_rt_reg_sz = 0x00000002
    advapi32.RegGetValueW.argtypes = (
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi32.RegGetValueW.restype = ctypes.c_long
    size = wintypes.DWORD(0)
    result = advapi32.RegGetValueW(
        hklm, subkey, 'PATHEXT', rrf_rt_reg_sz, None, None, ctypes.byref(size)
    )
    if result != 0 or size.value == 0:
        raise OSError(f'RegGetValueW failed: {result}')
    data = ctypes.create_unicode_buffer(size.value // ctypes.sizeof(ctypes.c_wchar) + 1)
    size = wintypes.DWORD(ctypes.sizeof(data))
    result = advapi32.RegGetValueW(
        hklm, subkey, 'PATHEXT', rrf_rt_reg_sz, None, data, ctypes.byref(size)
    )
    if result != 0 or not data.value:
        raise OSError(f'RegGetValueW failed: {result}')

    return {
        'SYSTEMROOT': windir,
        'WINDIR': windir,
        'COMSPEC': os.path.join(windir, 'System32', 'cmd.exe'),
        'PROGRAMDATA': program_data,
        'PATHEXT': data.value,
    }


def build_env(
    driver: harnesses.Driver,
    home: dict,
    environ: dict,
    *,
    run_dir: Path,
    run_id: str,
    root: Path,
    policy_path: Path,
    workdir: Path,
    pins=None,
    extra: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """The child's environment and the names dropped from kit's own; `extra` is passed as well."""
    allow = {_key(n) for n in ALLOW}
    passed = {_key(n) for n in extra or {}}
    base, scrubbed = {}, []
    for name, value in environ.items():
        if _key(name) in allow:
            base[name] = value
        elif _key(name) not in passed:
            scrubbed.append(name)
    env = driver.session_env(home, base)
    tmp = str(run_dir / 'tmp')
    values = {
        'TEMP': tmp,
        'TMP': tmp,
        'GH_CONFIG_DIR': str(run_dir / 'gh-config'),
        'GIT_CONFIG_GLOBAL': str(run_dir / _gitconfig_name(home)),
        'GIT_CONFIG_NOSYSTEM': '1',
        'GIT_TERMINAL_PROMPT': '0',
        state.RUN_ID_ENV: run_id,
        state.STATE_ROOT_ENV: str(root),
        'KIT_POLICY': str(policy_path),
        'PWD': str(workdir),
        **(extra or {}),
    }
    for name, value in values.items():
        harnesses.set_var(env, name, value)
    if WINDOWS:
        try:
            pinned = (pins or windows_pins)()
        except OSError as exc:
            raise RefusalError(f'the system values could not be read: {_ascii(exc)}') from None
        for name in WINDOWS_PINNED:
            harnesses.set_var(env, name, pinned[name])
    for name, value in env.items():
        if SECRET_NAME.search(name) and value != FAKE_KEY:
            raise RefusalError(f'the session environment would carry {_ascii(name)}')
        if name.upper() in GUARD_DROPPERS:
            raise RefusalError(f'the session environment would carry {_ascii(name)}')
    return env, sorted(set(scrubbed))


def _gitconfig_name(home: dict) -> str:
    """The run's copy of a daily home's `gitconfig`; an empty file for a test home."""
    daily_home = harnesses.home_kind(home) == harnesses.DAILY_HOME
    return 'gitconfig' if daily_home else 'gitconfig-empty'


# ---- preflight, mint, launch


def preflight(
    harness: str,
    home_dir: str,
    workdir: str,
    policy_file: str,
    harness_args: list[str],
    environ: dict,
    mode: str = HEADLESS,
    accept_version: str | None = None,
) -> Plan:
    """Every check of `kit run`, in order; raise RefusalError on the first that fails."""
    try:
        driver = harnesses.get(harness)
    except KeyError as exc:
        raise RefusalError(_ascii(exc.args[0])) from None
    notices = check_mode(driver, mode)
    home_folder = Path(os.path.abspath(home_dir))
    check_config_changed(home_folder)
    policy_path = Path(os.path.abspath(policy_file))
    try:
        policy = load_policy(policy_path)
    except PolicyError as exc:
        raise RefusalError(f'policy unreadable: {_ascii(exc)}') from None
    added, loaded = load_checkers(policy)
    records = harnesses.recorded_kinds(policy.checkers)
    notices += check_note_states(policy, driver, records) if records else []
    home = check_home(home_folder, driver)
    kind = harnesses.home_kind(home)
    if kind not in harnesses.HOME_KINDS:
        raise RefusalError(f'home.json names the kind {_ascii(kind)}, not test or daily')
    is_daily = kind == harnesses.DAILY_HOME
    if mode == INTERACTIVE or is_daily:
        check_open_run(home_folder)
        check_cli_argv(home, driver)
        check_render_record(home_folder, home, driver)
    check_permissions(home, driver, policy)
    extra: dict[str, str] = {}
    if records:
        check_note_home(home, driver, records)
        extra = governed_home(policy, environ)
    if state.RUN_ID_ENV in environ:
        raise RefusalError(f'nested launch: {state.RUN_ID_ENV} is already set')
    try:
        root = state.state_root(environ)
    except state.StateRootError as exc:
        raise RefusalError(_ascii(exc)) from None
    # The key leaves kit's environment before the first child, preflight's git, starts.
    daily_run = check_daily(home, root, environ) if is_daily else None
    child = child_environ(environ) if is_daily else None
    folder = Path(os.path.realpath(workdir))
    if not folder.is_dir():
        raise RefusalError(f'working folder {_ascii(folder)} is not a folder')
    top = work_tree_top(folder, env=child)
    remotes = read_remotes(folder, env=child) if top is not None else []
    if driver.name != CLAUDE_CODE:
        check_folder(folder, top, remotes, policy)
    check_session_args(harness_args, driver, mode)
    strict = mode == INTERACTIVE or is_daily
    project_config = check_project_layer(driver, folder, top, root, refuse_workdir=strict)
    system = check_system_layer(driver)
    binary = driver.binary_argv(environ)
    if not binary:
        raise RefusalError(f'the {driver.name} binary was not found')
    # The version probe takes kit's environment, less the key and the secret names for a daily home.
    found = driver.version(child if child is not None else environ)
    notices += check_version(driver, found, accept_version)
    surface = import_surface(added, loaded, environ)
    walked = walked_folders(driver, folder, top, root)
    run_id = state.new_run_id()
    run_dir = root / 'runs' / run_id
    terminal = terminal_env(environ) if mode == INTERACTIVE else {}
    capability = {CAPABILITY_ENV: daily_run.capability} if daily_run else {}
    env, scrubbed = build_env(
        driver,
        home,
        environ,
        run_dir=run_dir,
        run_id=run_id,
        root=root,
        policy_path=policy_path,
        workdir=folder,
        extra={**extra, **terminal, **capability},
    )
    protected = protected_paths(
        driver,
        home_folder,
        daily_file=str(daily_run.found.path) if daily_run else None,
        root=root,
        policy_path=policy_path,
        surface=surface,
        walked=walked,
        system=system,
        environ=environ,
    )
    plan = Plan(
        driver=driver,
        home=home,
        workdir=folder,
        policy_path=policy_path,
        root=root,
        run_id=run_id,
        run_dir=run_dir,
        argv=[*binary, *harness_args],
        env=env,
        remotes=remotes,
        project_config=project_config,
        scrubbed=scrubbed,
        binary=list(binary),
        extra_env=extra,
        notices=notices,
        mode=mode,
        top=top,
        terminal=terminal,
        home_dir=home_folder,
        daily=daily_run,
        canary_extra={CAPABILITY_ENV: daily_run.canary_capability} if daily_run else {},
        protected=protected,
        protected_except=[str(run_dir / 'tmp')],
        policy_sha256=policy.sha256,
        version_found=found,
        accepted_version=accept_version,
    )
    plan.watch = run_watch(plan, surface, walked, system)
    return plan


def _exit_code(code: int) -> int:
    return 128 - code if code < 0 else code


def run_plan_canary(plan: Plan, environ: dict) -> dict:
    """The presence canary for a minted run, under the session's environment builder."""

    def make_env(copy: dict, work: Path) -> dict:
        env, _ = build_env(
            plan.driver,
            copy,
            environ,
            run_dir=plan.run_dir,
            run_id=plan.run_id,
            root=plan.root,
            policy_path=plan.policy_path,
            workdir=work,
            extra={**plan.extra_env, **plan.canary_extra},
        )
        return env

    return canary.run_canary(
        plan.driver,
        plan.home,
        plan.binary,
        run_dir=plan.run_dir,
        workdir=plan.workdir,
        project_config=plan.project_config,
        make_env=make_env,
    )


def run_canary_for_plan(plan: Plan, environ: dict) -> dict:
    """The canary for a minted run, ended at once with its whole tree by an interrupt.

    On Windows a wait for a process is not interrupted by Ctrl+C or Ctrl+Break, so a canary
    harness that ignores them would hold kit until it ends by itself. There the canary runs in
    a child process of kit, inside a Job Object kit holds and waits on in short steps; an
    interrupt ends that job. Elsewhere the interrupt reaches the canary's own wait, which ends
    its tree, so it runs in kit's process.
    """
    if not WINDOWS:
        return run_plan_canary(plan, environ)
    return _canary_in_child(plan, environ)


CANARY_CHILD_POLL_S = 0.1
# The canary's own deadline, its kill wait, and room for the child's start and stop.
CANARY_CHILD_DEADLINE_S = canary.TIMEOUT_S + canary.KILL_WAIT_S + 30


def _canary_failure(reason: str) -> dict:
    return {
        'passed': False,
        'reason': reason,
        'refused_marker': False,
        'deny_marker': False,
        'allow_marker': False,
        'stub_requests': 0,
    }


def _canary_in_child(plan: Plan, environ: dict) -> dict:
    """Run `run_plan_canary` in a child process inside a kill-on-close Job Object."""
    spec = {
        'driver': plan.driver.name,
        'home': plan.home,
        'binary': plan.binary,
        'run_dir': str(plan.run_dir),
        'run_id': plan.run_id,
        'root': str(plan.root),
        'policy_path': str(plan.policy_path),
        'workdir': str(plan.workdir),
        'project_config': plan.project_config,
        'extra_env': plan.extra_env,
        'canary_extra': plan.canary_extra,
        'environ': environ,
    }
    data = json.dumps(spec, ensure_ascii=True).encode('ascii')
    parent = str(Path(harness_kit.__file__).resolve().parent.parent)
    boot = (
        f'import sys; sys.path.insert(0, {parent!a}); '
        'from harness_kit.launcher import canary_child; sys.exit(canary_child())'
    )
    proc = subprocess.Popen(  # noqa: S603 - this interpreter, a fixed bootstrap, no shell
        [sys.executable, '-I', '-c', boot],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_SUSPENDED,
    )
    job = None
    try:
        try:
            job = _Job()
            job.assign(int(proc._handle))  # type: ignore[attr-defined]
            _resume(proc.pid)
        except OSError as exc:
            proc.kill()
            return _canary_failure(f'the canary process did not start: {_ascii(exc)}')
        proc.stdin.write(data)
        proc.stdin.close()
        end = time.monotonic() + CANARY_CHILD_DEADLINE_S
        while proc.poll() is None:
            if time.monotonic() >= end:
                return _canary_failure('the canary process did not end')
            try:
                proc.wait(timeout=CANARY_CHILD_POLL_S)
            except subprocess.TimeoutExpired:
                continue
        found = proc.stdout.read().decode('ascii', 'replace').strip().splitlines()
        try:
            result = json.loads(found[-1]) if found else None
        except ValueError:
            result = None
        if not isinstance(result, dict) or not isinstance(result.get('passed'), bool):
            return _canary_failure(f'the canary process gave no result (exit {proc.returncode})')
        return result
    finally:
        if job is not None:
            job.terminate()
            job.wait_empty(TREE_WAIT_S)
            job.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        for stream in (proc.stdin, proc.stdout):
            if stream is not None and not stream.closed:
                stream.close()


def canary_child() -> int:
    """The child that `_canary_in_child` starts: one canary, its record printed as JSON."""
    spec = json.loads(sys.stdin.buffer.read().decode('ascii'))
    plan = Plan(
        driver=harnesses.get(spec['driver']),
        home=spec['home'],
        workdir=Path(spec['workdir']),
        policy_path=Path(spec['policy_path']),
        root=Path(spec['root']),
        run_id=spec['run_id'],
        run_dir=Path(spec['run_dir']),
        argv=[],
        env={},
        project_config=list(spec['project_config']),
        binary=list(spec['binary']),
        extra_env=dict(spec['extra_env']),
        canary_extra=dict(spec['canary_extra']),
    )
    result = run_plan_canary(plan, dict(spec['environ']))
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + '\n')
    sys.stdout.flush()
    return 0


def launch(plan: Plan, environ: dict) -> int:
    """Mint the run, record it, run the canary, start the harness, wait, record the end.

    From the mint until the session ends a thread rewrites the run's
    `heartbeat.json` every 2 seconds, so `kit doctor` can tell a killed
    launcher (`stale`) from a running one.
    """
    state.mint_run(plan.root, plan.driver.name, run_id=plan.run_id)
    beat = doctor.Heartbeat(plan.run_dir, plan.run_id)
    beat.start()
    try:
        return _launch_minted(plan, environ)
    finally:
        beat.stop()


def _home_dir(plan: Plan) -> Path:
    return plan.home_dir if plan.home_dir is not None else Path(plan.home['dir'])


def _launch_minted(plan: Plan, environ: dict) -> int:
    run_json = plan.run_dir / 'run.json'
    record = json.loads(run_json.read_text(encoding='utf-8'))
    held = _Held()
    try:
        try:
            ready = _before_session(plan, environ, record, held)
        except KeyboardInterrupt:
            record.update(outcome='interrupted')
            state.write_json_atomic(run_json, record)
            return _fail(EXIT_INTERRUPTED, 'run interrupted before the session started')
        if isinstance(ready, int):
            return ready
        return _run_session(plan, record, held, ready)
    finally:
        held.stop_relay(plan, record)


def _before_session(plan: Plan, environ: dict, record: dict, held: _Held) -> int | dict:
    """Hashes, version, canary, the relay and the second read; an exit code when the session
    must not start, else the second read, the baseline of the check during the run."""
    run_json = plan.run_dir / 'run.json'
    (plan.run_dir / 'tmp').mkdir()
    (plan.run_dir / 'gh-config').mkdir()
    (plan.run_dir / 'gitconfig-empty').write_bytes(b'')
    home_dir = _home_dir(plan)
    if plan.daily is not None:
        shutil.copyfile(home_dir / 'gitconfig', plan.run_dir / 'gitconfig')
    hashes = watch.hash_files(home_dir, plan.driver)
    state.write_json_atomic(plan.run_dir / watch.HOME_HASHES, hashes)
    record.update(
        home=str(plan.home['dir']),
        workdir=str(plan.workdir),
        work_tree_top=str(plan.top) if plan.top is not None else None,
        remotes=plan.remotes,
        project_config=plan.project_config,
        kit_pid=os.getpid(),
        harness_version_found=plan.version_found,
        scrubbed=plan.scrubbed,
    )
    if plan.accepted_version is not None:
        record.update(accepted_version=plan.accepted_version)
    if plan.mode == INTERACTIVE:
        record.update(terminal_names=list(plan.terminal))
    if plan.policy_sha256 is not None:
        record.update(
            protected=list(plan.protected),
            protected_except=list(plan.protected_except),
            policy_sha256=plan.policy_sha256,
        )
    state.write_json_atomic(run_json, record)
    result = run_canary_for_plan(plan, environ)
    state.write_json_atomic(plan.run_dir / state.CANARY_DIR / canary.CANARY_JSON, result)
    if not result['passed']:
        record.update(outcome='refused-canary')
        state.write_json_atomic(run_json, record)
        return _fail(EXIT_CANARY, f'canary failed: {_ascii(result["reason"])}')
    if plan.daily is not None:
        not_ready = held.start_relay(plan, environ)
        if not_ready is not None:
            record.update(outcome='refused-relay')
            state.write_json_atomic(run_json, record)
            return _fail(EXIT_INTERNAL, f'the relay did not get ready: {not_ready}')
    # The second read is the baseline of the session; a difference refuses the start.
    baseline = watch.read_files(home_dir, plan.driver)
    changed = watch.differences(hashes, {rel: v['sha256'] for rel, v in baseline.items()})
    if changed:
        record.update(outcome='refused-home-changed')
        state.write_json_atomic(run_json, record)
        more = f' and {len(changed) - 1} more' if len(changed) > 1 else ''
        return _fail(
            EXIT_CANARY,
            f'the home changed before the session started: {_ascii(changed[0])}{more}',
        )
    if _marks_open(plan):
        state.write_json_atomic(home_dir / watch.RUN_OPEN, {'run_id': plan.run_id})
    return baseline


def _marks_open(plan: Plan) -> bool:
    """An interactive run, and any run on a daily home, holds `run-open.json` during its session."""
    return plan.mode == INTERACTIVE or plan.daily is not None


def _run_session(plan: Plan, record: dict, held: _Held, baseline: dict | None = None) -> int:
    """Start the session in its own tree, wait for it, end the tree and record the end.

    From the session's start a thread reads what `plan.watch` names every 2 seconds and ends
    the session's tree at the first difference; once the tree ended, one more read is taken
    before kit writes anything. A difference ends the run with `config-changed`.
    """
    run_json = plan.run_dir / 'run.json'
    restore = _ignore_interrupts()
    try:
        try:
            session = _Session.start(plan.argv, plan.env, plan.workdir)
        except OSError as exc:
            record.update(outcome='ended', exit_code=None, error=_ascii(type(exc).__name__))
            state.write_json_atomic(run_json, record)
            held.stop_relay(plan, record)
            _close_run(plan)
            return _fail(EXIT_INTERNAL, f'the harness did not start: {_ascii(exc)}')
        record.update(outcome='launched')
        state.write_json_atomic(run_json, record)
        check = _RunCheck(plan.watch, baseline, session) if plan.watch is not None else None
        code = session.wait()
        found = check.stop() if check is not None else []
        session.end()
        if check is not None:
            found = check.last(found)
        if found:
            return _config_changed(plan, record, held, code, found)
        record.update(outcome='ended', exit_code=code)
        state.write_json_atomic(run_json, record)
        held.stop_relay(plan, record)
        _close_run(plan)
        return _exit_code(code)
    finally:
        restore()


class _RunCheck:
    """The check during the run: a thread that reads the watch plan every 2 seconds."""

    def __init__(self, plan: watch.RunWatch, home_files: dict | None, session: _Session):
        self.plan = plan
        self.session = session
        self.baseline = watch.snapshot(plan, home_files)
        self.found: list[str] = []
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name='kit-run-check', daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_POLL_S):
            try:
                changed = watch.changes(self.baseline, watch.snapshot(self.plan))
            except OSError:
                continue
            if changed:
                self.found = changed
                self.session.kill()
                return

    def stop(self) -> list[str]:
        """Stop the thread; the paths it found changed, if any."""
        self._stop.set()
        self.thread.join()
        return list(self.found)

    def last(self, found: list[str]) -> list[str]:
        """`found` and what one more read finds changed, after the session's tree ended."""
        later = watch.changes(self.baseline, watch.snapshot(self.plan))
        return [*found, *(p for p in later if p not in found)]


def _config_changed(plan: Plan, record: dict, held: _Held, code: int, found: list[str]) -> int:
    """Record a run whose session changed what governs it, mark the home, exit 66."""
    home_dir = _home_dir(plan)
    names = [watch.label(p, home_dir) for p in found][:CHANGED_MAX]
    carried = [
        p for p in found if not watch.within(p, home_dir) and not watch.within(p, plan.run_dir)
    ][:CHANGED_MAX]
    record.update(outcome='config-changed', exit_code=code, config_changed=names)
    state.write_json_atomic(plan.run_dir / 'run.json', record)
    held.stop_relay(plan, record)
    state.write_json_atomic(
        home_dir / watch.CONFIG_CHANGED, {'run_id': plan.run_id, 'carried': carried}
    )
    _close_run(plan)
    if plan.mode == INTERACTIVE:
        try:
            sys.stdout.write(TERMINAL_RESET)
            sys.stdout.flush()
        except (OSError, ValueError):
            pass
    lines = [
        f'kit: the session changed {_ascii(names[0])}, which governs it; kit ended the session '
        '(config-changed) and the home starts no session again'
    ]
    lines += [
        f'kit: {_ascii(path)} changed during the run and carries into a new home; read or '
        'restore it before rendering a new home'
        for path in carried
    ]
    sys.stderr.write(''.join(line + chr(10) for line in lines))
    sys.stderr.flush()
    return EXIT_CHANGED


def _close_run(plan: Plan) -> None:
    """Remove `run-open.json` once the session's end is recorded."""
    if not _marks_open(plan):
        return
    try:
        (_home_dir(plan) / watch.RUN_OPEN).unlink()
    except FileNotFoundError:
        pass


# ---- the relay of a daily run


def relay_env(environ: dict) -> dict[str, str]:
    """The relay's environment: the allow list of kit's own, with the system's pinned names."""
    allow = {_key(n) for n in ALLOW}
    env = {k: v for k, v in environ.items() if _key(k) in allow}
    if WINDOWS:
        try:
            pinned = windows_pins()
        except OSError:
            return env
        for name in WINDOWS_PINNED:
            harnesses.set_var(env, name, pinned[name])
    return env


def relay_record(root: Path, run_id: str) -> dict:
    """`run.json`'s `relay`: the run's requests and refusals, its settled total and its stop."""
    lines = []
    try:
        text = (root / 'runs' / run_id / relay.LOG).read_text(encoding='utf-8', errors='replace')
    except OSError:
        text = ''
    for raw in text.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict):
            lines.append(line)
    try:
        totals = relay.fold(relay.read_ledger(root))
    except OSError:
        totals = relay.Totals()
    return {
        'requests': len(lines),
        'refused': sum(1 for line in lines if line.get('decision') == 'refused'),
        'settled_usd': totals.run.get(run_id, 0.0),
        'stopped': run_id in totals.stops,
    }


class _RelayProcess:
    """The relay's process and its tree, its standard input kept open until the run ends."""

    def __init__(self, proc: subprocess.Popen, job: _Job | None) -> None:
        self.proc = proc
        self.job = job
        self.line: bytes | None = None
        self.reader = threading.Thread(target=self._read_ready, daemon=True)
        self.reader.start()

    @classmethod
    def start(cls, plan: Plan, environ: dict) -> _RelayProcess:
        """Start `kit relay serve` for the run; raise OSError when it did not start in its tree."""
        parent = str(Path(harness_kit.__file__).resolve().parent.parent)
        boot = (
            f'import sys; sys.path.insert(0, {parent!a}); '
            'from harness_kit.cli import main; sys.exit(main())'
        )
        found = plan.daily.found
        argv = [sys.executable, '-I', '-c', boot, 'relay', 'serve', '--config', str(found.path)]
        argv += ['--state-root', str(plan.root), '--run-id', plan.run_id]
        extra = (
            {'creationflags': CREATE_SUSPENDED | NO_WINDOW}
            if WINDOWS
            else {'start_new_session': True}
        )
        with open(plan.run_dir / RELAY_STDERR, 'wb') as err:
            proc = subprocess.Popen(  # noqa: S603 - this interpreter, a fixed bootstrap, no shell
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=err,
                env=relay_env(environ),
                cwd=str(plan.run_dir),
                **extra,
            )
        job = None
        if WINDOWS:
            try:
                job = _Job()
                job.assign(int(proc._handle))  # type: ignore[attr-defined]
                _resume(proc.pid)
            except OSError:
                proc.kill()
                proc.wait()
                if job is not None:
                    job.close()
                raise
        return cls(proc, job)

    def _read_ready(self) -> None:
        try:
            self.line = self.proc.stdout.readline(4096)
        except (OSError, ValueError):
            self.line = b''

    def hand(self, key: str, capability: str) -> None:
        """Write the relay's first line of standard input; the pipe stays open."""
        line = json.dumps({'key': key, 'capability': capability}, ensure_ascii=True) + '\n'
        try:
            self.proc.stdin.write(line.encode('ascii'))
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass  # a relay that already ended is not ready

    def wait_ready(self, port: int, timeout_s: float) -> str | None:
        """None once the relay printed its ready line for `port`, else why it is not ready."""
        end = time.monotonic() + timeout_s
        while self.line is None:
            if time.monotonic() >= end:
                return f'no ready line within {timeout_s:g} s'
            time.sleep(RELAY_POLL_S)
        try:
            ready = json.loads(self.line.decode('ascii'))
        except (UnicodeDecodeError, ValueError):
            ready = None
        ok = isinstance(ready, dict) and ready.get('relay') == 1 and ready.get('port') == port
        if ok:
            return None
        if not self.line:
            code = self.proc.poll()
            return (
                f'it ended with exit {code} before its ready line'
                if code is not None
                else ('it closed its standard output before its ready line')
            )
        return 'its ready line is not {"relay": 1, "port": N, "pid": P} for its port'

    def stop(self, timeout_s: float = RELAY_STOP_S) -> None:
        """Close its standard input, wait at most `timeout_s` for its end, then end its tree."""
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass
        end = time.monotonic() + timeout_s
        while self.proc.poll() is None and time.monotonic() < end:
            time.sleep(RELAY_POLL_S)
        if self.job is not None:
            self.job.terminate()
            self.job.wait_empty(TREE_WAIT_S)
            self.job.close()
        elif not WINDOWS:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                pass
            _wait_group_gone(self.proc.pid, TREE_WAIT_S)
        if self.proc.poll() is None:
            self.proc.kill()
        try:
            self.proc.wait(timeout=TREE_WAIT_S)
        except subprocess.TimeoutExpired:
            pass
        try:
            self.proc.stdout.close()
        except (OSError, ValueError):
            pass


class _Held:
    """The relay a minted run started, stopped and recorded once, however the run ended."""

    def __init__(self) -> None:
        self.relay: _RelayProcess | None = None

    def start_relay(self, plan: Plan, environ: dict) -> str | None:
        """Start the relay and hand it the key; None once it is ready, else why it is not."""
        try:
            self.relay = _RelayProcess.start(plan, environ)
        except OSError as exc:
            return f'it did not start: {_ascii(type(exc).__name__)}'
        key, plan.daily.key = plan.daily.key, None
        self.relay.hand(key or '', plan.daily.capability)
        port = plan.daily.found.relay.listen_port
        return self.relay.wait_ready(port, RELAY_READY_S)

    def stop_relay(self, plan: Plan, record: dict) -> None:
        if self.relay is None:
            return
        found, self.relay = self.relay, None
        found.stop()
        record.update(relay=relay_record(plan.root, plan.run_id))
        state.write_json_atomic(plan.run_dir / 'run.json', record)


# ---- interrupts and the session's tree


def _ignore(signum, frame) -> None:
    """During the session an interrupt is the harness's; kit keeps waiting."""


def _interrupt_signals() -> list:
    return [signal.SIGINT] + ([signal.SIGBREAK] if WINDOWS else [])


def _ignore_interrupts():
    """Set a handler that does nothing for Ctrl+C and Ctrl+Break; return what restores them.

    A Python handler, not SIG_IGN, so the session inherits no ignored signal.
    """
    saved = {}
    for sig in _interrupt_signals():
        try:
            saved[sig] = signal.signal(sig, _ignore)
        except (ValueError, OSError):  # not the main thread: nothing to set
            continue

    def restore() -> None:
        for sig, handler in saved.items():
            signal.signal(sig, handler)

    return restore


def _break_as_interrupt() -> None:
    """On Windows, Ctrl+Break raises KeyboardInterrupt as Ctrl+C does; its default ends kit."""
    if not WINDOWS:
        return
    try:
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    except (ValueError, OSError):  # not the main thread
        pass


class _Session:
    """The session's process and its tree: a Job Object on Windows, a process group on POSIX."""

    def __init__(self, proc: subprocess.Popen, job: _Job | None) -> None:
        self.proc = proc
        self.job = job

    @classmethod
    def start(cls, argv: list[str], env: dict, cwd: Path) -> _Session:
        """Start the session; raise OSError when it did not start inside its tree."""
        if not WINDOWS:
            proc = subprocess.Popen(argv, env=env, cwd=str(cwd), start_new_session=True)  # noqa: S603
            return cls(proc, None)
        proc = subprocess.Popen(  # noqa: S603 - the checked argv, no shell
            argv, env=env, cwd=str(cwd), creationflags=CREATE_SUSPENDED
        )
        job = None
        try:
            job = _Job()
            job.assign(int(proc._handle))  # type: ignore[attr-defined]
            _resume(proc.pid)
        except OSError:
            proc.kill()
            proc.wait()
            if job is not None:
                job.close()
            raise
        return cls(proc, job)

    def wait(self) -> int:
        while True:
            try:
                return self.proc.wait()
            except KeyboardInterrupt:
                continue

    def kill(self) -> None:
        """End the session's whole tree now, from any thread; `end` still waits for it."""
        if self.job is not None:
            self.job.terminate()
            return
        if not WINDOWS:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                pass

    def end(self) -> None:
        """End every process left in the session's tree and wait until they are gone."""
        if self.job is not None:
            self.job.terminate()
            self.job.wait_empty(TREE_WAIT_S)
            self.job.close()
            return
        if not WINDOWS:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                return
            _wait_group_gone(self.proc.pid, TREE_WAIT_S)


def _group_members(pgid: int) -> list[tuple[int, str]]:
    """(pid, state) of each process of a group, read from /proc; [] where there is none."""
    found = []
    try:
        entries = os.listdir('/proc')
    except OSError:
        return []
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f'/proc/{entry}/stat', encoding='ascii', errors='replace') as fh:
                fields = fh.read().rsplit(')', 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(fields) > 2 and fields[2] == str(pgid):
            found.append((int(entry), fields[0]))
    return found


def _wait_group_gone(pgid: int, timeout_s: float) -> None:
    """Wait until no process of the group is alive, then briefly for its zombies to be reaped."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        members = _group_members(pgid)
        if not members:
            return
        if all(st == 'Z' for _, st in members):
            end = min(end, time.monotonic() + 1.0)
        time.sleep(0.02)


# Windows: the Job Object and the first thread of a suspended process.
CREATE_SUSPENDED = 0x00000004
_JOB_KILL_ON_CLOSE = 0x00002000
_JOB_EXTENDED_LIMITS = 9
_JOB_ACCOUNTING = 1
_SNAP_THREAD = 0x00000004
_THREAD_SUSPEND_RESUME = 0x0002


def _kernel32():
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k32.CreateJobObjectW.restype = ctypes.c_void_p
    k32.SetInformationJobObject.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.QueryInformationJobObject.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    )
    k32.QueryInformationJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.TerminateJobObject.argtypes = (ctypes.c_void_p, wintypes.UINT)
    k32.TerminateJobObject.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = (ctypes.c_void_p,)
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.Thread32First.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    k32.Thread32First.restype = wintypes.BOOL
    k32.Thread32Next.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    k32.Thread32Next.restype = wintypes.BOOL
    k32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.OpenThread.restype = ctypes.c_void_p
    k32.ResumeThread.argtypes = (ctypes.c_void_p,)
    k32.ResumeThread.restype = wintypes.DWORD
    return k32


def _job_structs():
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = (
            ('PerProcessUserTimeLimit', ctypes.c_int64),
            ('PerJobUserTimeLimit', ctypes.c_int64),
            ('LimitFlags', wintypes.DWORD),
            ('MinimumWorkingSetSize', ctypes.c_size_t),
            ('MaximumWorkingSetSize', ctypes.c_size_t),
            ('ActiveProcessLimit', wintypes.DWORD),
            ('Affinity', ctypes.c_size_t),
            ('PriorityClass', wintypes.DWORD),
            ('SchedulingClass', wintypes.DWORD),
        )

    class Io(ctypes.Structure):
        _fields_ = tuple(
            (name, ctypes.c_uint64)
            for name in ('Read', 'Write', 'Other', 'ReadBytes', 'WriteBytes', 'OtherBytes')
        )

    class Extended(ctypes.Structure):
        _fields_ = (
            ('BasicLimitInformation', Basic),
            ('IoInfo', Io),
            ('ProcessMemoryLimit', ctypes.c_size_t),
            ('JobMemoryLimit', ctypes.c_size_t),
            ('PeakProcessMemoryUsed', ctypes.c_size_t),
            ('PeakJobMemoryUsed', ctypes.c_size_t),
        )

    class Accounting(ctypes.Structure):
        _fields_ = (
            ('TotalUserTime', ctypes.c_int64),
            ('TotalKernelTime', ctypes.c_int64),
            ('ThisPeriodTotalUserTime', ctypes.c_int64),
            ('ThisPeriodTotalKernelTime', ctypes.c_int64),
            ('TotalPageFaultCount', wintypes.DWORD),
            ('TotalProcesses', wintypes.DWORD),
            ('ActiveProcesses', wintypes.DWORD),
            ('TotalTerminatedProcesses', wintypes.DWORD),
        )

    class ThreadEntry(ctypes.Structure):
        _fields_ = (
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ThreadID', wintypes.DWORD),
            ('th32OwnerProcessID', wintypes.DWORD),
            ('tpBasePri', wintypes.LONG),
            ('tpDeltaPri', wintypes.LONG),
            ('dwFlags', wintypes.DWORD),
        )

    return Extended, Accounting, ThreadEntry


class _Job:
    """A Job Object whose processes end when it is closed (kill-on-close)."""

    def __init__(self) -> None:
        import ctypes

        self._k32 = _kernel32()
        extended, self._accounting, _ = _job_structs()
        handle = self._k32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'CreateJobObjectW failed')
        self.handle = handle
        info = extended()
        info.BasicLimitInformation.LimitFlags = _JOB_KILL_ON_CLOSE
        size = ctypes.sizeof(info)
        if not self._k32.SetInformationJobObject(
            handle, _JOB_EXTENDED_LIMITS, ctypes.byref(info), size
        ):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, 'SetInformationJobObject failed')

    def assign(self, process_handle: int) -> None:
        import ctypes

        if not self._k32.AssignProcessToJobObject(self.handle, process_handle):
            raise OSError(ctypes.get_last_error(), 'AssignProcessToJobObject failed')

    def active(self) -> int | None:
        import ctypes

        info = self._accounting()
        if not self._k32.QueryInformationJobObject(
            self.handle, _JOB_ACCOUNTING, ctypes.byref(info), ctypes.sizeof(info), None
        ):
            return None
        return int(info.ActiveProcesses)

    def terminate(self) -> None:
        self._k32.TerminateJobObject(self.handle, 1)

    def wait_empty(self, timeout_s: float) -> None:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            if not self.active():
                return
            time.sleep(0.02)

    def close(self) -> None:
        if self.handle:
            self._k32.CloseHandle(self.handle)
            self.handle = None


def _resume(pid: int) -> None:
    """Resume the threads of a process created suspended, found by a thread snapshot."""
    import ctypes

    k32 = _kernel32()
    _, _, thread_entry = _job_structs()
    snapshot = k32.CreateToolhelp32Snapshot(_SNAP_THREAD, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), 'CreateToolhelp32Snapshot failed')
    resumed = 0
    try:
        entry = thread_entry()
        entry.dwSize = ctypes.sizeof(entry)
        more = k32.Thread32First(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                thread = k32.OpenThread(_THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                if thread:
                    if k32.ResumeThread(thread) != 0xFFFFFFFF:
                        resumed += 1
                    k32.CloseHandle(thread)
            more = k32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snapshot)
    if not resumed:
        raise OSError(f'no thread of process {pid} was resumed')


def _fail(code: int, message: str) -> int:
    sys.stderr.write(f'kit: {message}\n')
    sys.stderr.flush()
    return code


def build_parser() -> _Parser:
    parser = _Parser(
        prog='kit run',
        description='Check a session against the policy and the home, then start the harness.',
    )
    parser.add_argument('--harness', metavar='NAME', required=True, help='claude-code or opencode')
    parser.add_argument('--home', metavar='DIR', required=True, help='a home from kit home render')
    parser.add_argument('--workdir', metavar='DIR', required=True, help='the session folder')
    parser.add_argument('--policy', metavar='FILE', required=True, help='the policy file')
    parser.add_argument(
        '--mode',
        choices=harnesses.MODES,
        default=HEADLESS,
        help='headless (default) or interactive (opencode on Windows)',
    )
    parser.add_argument(
        '--accept-version',
        metavar='VERSION',
        help="start a harness whose version is not the contract's, when it is exactly VERSION",
    )
    return parser


def main(argv: list[str]) -> int:
    """`kit run`; `argv` follows the word `run`."""
    _break_as_interrupt()
    try:
        if '--' not in argv:
            raise RefusalError('arguments: put -- before the harness arguments')
        cut = argv.index('--')
        args = build_parser().parse_args(argv[:cut])
        plan = preflight(
            args.harness,
            args.home,
            args.workdir,
            args.policy,
            argv[cut + 1 :],
            dict(os.environ),
            mode=args.mode,
            accept_version=args.accept_version,
        )
    except RefusalError as exc:
        return _fail(EXIT_REFUSED, f'run refused: {exc}')
    except KeyboardInterrupt:
        return _fail(EXIT_INTERRUPTED, 'run interrupted during preflight; no run was minted')
    try:
        for line in plan.notices:
            sys.stderr.write(line + '\n')
        sys.stderr.flush()
        return launch(plan, dict(os.environ))
    except KeyboardInterrupt:
        return _fail(EXIT_INTERRUPTED, 'run interrupted before the session started')
    except Exception as exc:  # the record says what happened; exit 70 names an internal error
        return _fail(EXIT_INTERNAL, f'run failed: {type(exc).__name__}: {_ascii(exc)}')

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

Exit codes: 64 a refusal, 65 a failed canary or a home changed before the
session, 70 an internal error, 130 an interrupt before the session, else the
harness's own.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import harness_kit
from harness_kit import canary, doctor, harnesses, packs, state, watch
from harness_kit.policy import Policy, PolicyError, load_policy

EXIT_REFUSED = 64
EXIT_CANARY = 65
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
CLAUDE_CODE = 'claude-code'
FAKE_KEY = 'stub-not-a-key'

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


def _git(folder: Path, *args: str) -> subprocess.CompletedProcess | None:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
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


def work_tree_top(folder: Path) -> Path | None:
    """The top of the git work tree holding `folder`, or None outside any.

    A `.git` entry in the folder or an ancestor that git does not answer for
    is a refusal: the launcher cannot tell which remotes it would push to.
    """
    proc = _git(folder, 'rev-parse', '--show-toplevel')
    if proc is not None and proc.returncode == 0 and proc.stdout.strip():
        return Path(os.path.realpath(proc.stdout.strip()))
    for place in (folder, *folder.parents):
        if os.path.lexists(place / '.git'):
            raise RefusalError(f'git could not read the work tree at {_ascii(place)}')
    return None


def read_remotes(folder: Path) -> list[dict]:
    """Every remote with its `url` and `pushurl` values, and whether it can push."""
    proc = _git(folder, 'config', '--get-regexp', REMOTE_KEYS)
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
    driver: harnesses.Driver, workdir: Path, top: Path | None, root: Path
) -> list[str]:
    """Refuse a project-config path in an ancestor; return those in the working folder."""
    for folder in project_walk(driver, workdir, top, root):
        for entry in driver.project_config_paths:
            if os.path.lexists(folder / entry):
                raise RefusalError(f'project config {_ascii(folder / entry)} lies in an ancestor')
    return [e for e in driver.project_config_paths if os.path.lexists(workdir / e)]


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
        'GIT_CONFIG_GLOBAL': str(run_dir / 'gitconfig-empty'),
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


# ---- preflight, mint, launch


def preflight(
    harness: str,
    home_dir: str,
    workdir: str,
    policy_file: str,
    harness_args: list[str],
    environ: dict,
    mode: str = HEADLESS,
) -> Plan:
    """Every check of `kit run`, in order; raise RefusalError on the first that fails."""
    try:
        driver = harnesses.get(harness)
    except KeyError as exc:
        raise RefusalError(_ascii(exc.args[0])) from None
    notices = check_mode(driver, mode)
    policy_path = Path(os.path.abspath(policy_file))
    try:
        policy = load_policy(policy_path)
    except PolicyError as exc:
        raise RefusalError(f'policy unreadable: {_ascii(exc)}') from None
    broken = packs.verify_checkers(policy.checkers)
    if broken is not None:
        raise RefusalError(f'policy checker unusable: {_ascii(broken)}')
    records = harnesses.recorded_kinds(policy.checkers)
    notices += check_note_states(policy, driver, records) if records else []
    home_folder = Path(os.path.abspath(home_dir))
    home = check_home(home_folder, driver)
    if mode == INTERACTIVE:
        check_open_run(home_folder)
        check_render_record(home_folder, home, driver)
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
    folder = Path(os.path.realpath(workdir))
    if not folder.is_dir():
        raise RefusalError(f'working folder {_ascii(folder)} is not a folder')
    top = work_tree_top(folder)
    remotes = read_remotes(folder) if top is not None else []
    if driver.name != CLAUDE_CODE:
        check_folder(folder, top, remotes, policy)
    check_session_args(harness_args, driver, mode)
    project_config = check_project_layer(driver, folder, top, root)
    binary = driver.binary_argv(environ)
    if not binary:
        raise RefusalError(f'the {driver.name} binary was not found')
    run_id = state.new_run_id()
    run_dir = root / 'runs' / run_id
    terminal = terminal_env(environ) if mode == INTERACTIVE else {}
    env, scrubbed = build_env(
        driver,
        home,
        environ,
        run_dir=run_dir,
        run_id=run_id,
        root=root,
        policy_path=policy_path,
        workdir=folder,
        extra={**extra, **terminal},
    )
    return Plan(
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
    )


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
            extra=plan.extra_env,
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
    try:
        ready = _before_session(plan, environ, record)
    except KeyboardInterrupt:
        record.update(outcome='interrupted')
        state.write_json_atomic(run_json, record)
        return _fail(EXIT_INTERRUPTED, 'run interrupted before the session started')
    if isinstance(ready, int):
        return ready
    return _run_session(plan, record)


def _before_session(plan: Plan, environ: dict, record: dict) -> int | None:
    """Hashes, version, canary and the second read; an exit code when the session must not start."""
    run_json = plan.run_dir / 'run.json'
    (plan.run_dir / 'tmp').mkdir()
    (plan.run_dir / 'gh-config').mkdir()
    (plan.run_dir / 'gitconfig-empty').write_bytes(b'')
    home_dir = _home_dir(plan)
    hashes = watch.hash_files(home_dir, plan.driver)
    state.write_json_atomic(plan.run_dir / watch.HOME_HASHES, hashes)
    found = plan.driver.version(environ)
    record.update(
        home=str(plan.home['dir']),
        workdir=str(plan.workdir),
        work_tree_top=str(plan.top) if plan.top is not None else None,
        remotes=plan.remotes,
        project_config=plan.project_config,
        kit_pid=os.getpid(),
        harness_version_found=found,
        scrubbed=plan.scrubbed,
    )
    if plan.mode == INTERACTIVE:
        record.update(terminal_names=list(plan.terminal))
    state.write_json_atomic(run_json, record)
    if found != plan.driver.pinned_version:
        sys.stderr.write(
            f'kit: {plan.driver.name} version {found or "not found"} differs from the pinned '
            f'{plan.driver.pinned_version}; starting it\n'
        )
        sys.stderr.flush()
    result = run_canary_for_plan(plan, environ)
    state.write_json_atomic(plan.run_dir / state.CANARY_DIR / canary.CANARY_JSON, result)
    if not result['passed']:
        record.update(outcome='refused-canary')
        state.write_json_atomic(run_json, record)
        return _fail(EXIT_CANARY, f'canary failed: {_ascii(result["reason"])}')
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
    if plan.mode == INTERACTIVE:
        state.write_json_atomic(home_dir / watch.RUN_OPEN, {'run_id': plan.run_id})
    return None


def _run_session(plan: Plan, record: dict) -> int:
    """Start the session in its own tree, wait for it, end the tree and record the end."""
    run_json = plan.run_dir / 'run.json'
    restore = _ignore_interrupts()
    try:
        try:
            session = _Session.start(plan.argv, plan.env, plan.workdir)
        except OSError as exc:
            record.update(outcome='ended', exit_code=None, error=_ascii(type(exc).__name__))
            state.write_json_atomic(run_json, record)
            _close_run(plan)
            return _fail(EXIT_INTERNAL, f'the harness did not start: {_ascii(exc)}')
        record.update(outcome='launched')
        state.write_json_atomic(run_json, record)
        code = session.wait()
        session.end()
        record.update(outcome='ended', exit_code=code)
        state.write_json_atomic(run_json, record)
        _close_run(plan)
        return _exit_code(code)
    finally:
        restore()


def _close_run(plan: Plan) -> None:
    """Remove `run-open.json` once the session's end is recorded."""
    if plan.mode != INTERACTIVE:
        return
    try:
        (_home_dir(plan) / watch.RUN_OPEN).unlink()
    except FileNotFoundError:
        pass


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

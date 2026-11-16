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

Exit codes: 64 a refusal, 65 a failed canary, 70 an internal error, else the
harness's own.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from harness_kit import canary, doctor, harnesses, packs, state
from harness_kit.policy import Policy, PolicyError, load_policy

EXIT_REFUSED = 64
EXIT_CANARY = 65
EXIT_INTERNAL = 70
WINDOWS = os.name == 'nt'
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


def check_session_args(args: list[str], driver: harnesses.Driver) -> None:
    lead = tuple(driver.required_leading_tokens)
    if tuple(args[: len(lead)]) != lead:
        raise RefusalError(f'harness arguments must start with {" ".join(lead)}')
    need = tuple(driver.required_session_args)
    if not any(tuple(args[i : i + len(need)]) == need for i in range(len(args))):
        raise RefusalError(f'harness arguments lack {" ".join(need)}')
    for token in need:
        if token.startswith('-') and args.count(token) != 1:
            raise RefusalError(f'harness arguments give {token} more than once')
    for token in args:
        if token.startswith('-') and token not in driver.allowed_session_flags:
            raise RefusalError(
                f'flag {_ascii(token)} is not in the allow list of {driver.name}: '
                + ' '.join(driver.allowed_session_flags)
            )


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
) -> Plan:
    """Every check of `kit run`, in order; raise RefusalError on the first that fails."""
    try:
        driver = harnesses.get(harness)
    except KeyError as exc:
        raise RefusalError(_ascii(exc.args[0])) from None
    policy_path = Path(os.path.abspath(policy_file))
    try:
        policy = load_policy(policy_path)
    except PolicyError as exc:
        raise RefusalError(f'policy unreadable: {_ascii(exc)}') from None
    broken = packs.verify_checkers(policy.checkers)
    if broken is not None:
        raise RefusalError(f'policy checker unusable: {_ascii(broken)}')
    records = harnesses.recorded_kinds(policy.checkers)
    notices = check_note_states(policy, driver, records) if records else []
    home = check_home(Path(home_dir), driver)
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
    check_session_args(harness_args, driver)
    project_config = check_project_layer(driver, folder, top, root)
    binary = driver.binary_argv(environ)
    if not binary:
        raise RefusalError(f'the {driver.name} binary was not found')
    run_id = state.new_run_id()
    run_dir = root / 'runs' / run_id
    env, scrubbed = build_env(
        driver,
        home,
        environ,
        run_dir=run_dir,
        run_id=run_id,
        root=root,
        policy_path=policy_path,
        workdir=folder,
        extra=extra,
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


def _launch_minted(plan: Plan, environ: dict) -> int:
    (plan.run_dir / 'tmp').mkdir()
    (plan.run_dir / 'gh-config').mkdir()
    (plan.run_dir / 'gitconfig-empty').write_bytes(b'')
    run_json = plan.run_dir / 'run.json'
    record = json.loads(run_json.read_text(encoding='utf-8'))
    found = plan.driver.version(environ)
    record.update(
        home=str(plan.home['dir']),
        workdir=str(plan.workdir),
        remotes=plan.remotes,
        project_config=plan.project_config,
        kit_pid=os.getpid(),
        harness_version_found=found,
        scrubbed=plan.scrubbed,
    )
    state.write_json_atomic(run_json, record)
    if found != plan.driver.pinned_version:
        sys.stderr.write(
            f'kit: {plan.driver.name} version {found or "not found"} differs from the pinned '
            f'{plan.driver.pinned_version}; starting it\n'
        )
        sys.stderr.flush()
    result = run_plan_canary(plan, environ)
    state.write_json_atomic(plan.run_dir / state.CANARY_DIR / canary.CANARY_JSON, result)
    if not result['passed']:
        record.update(outcome='refused-canary')
        state.write_json_atomic(run_json, record)
        return _fail(EXIT_CANARY, f'canary failed: {_ascii(result["reason"])}')
    try:
        proc = subprocess.Popen(plan.argv, env=plan.env, cwd=str(plan.workdir))  # noqa: S603
    except OSError as exc:
        record.update(outcome='ended', exit_code=None, error=_ascii(type(exc).__name__))
        state.write_json_atomic(run_json, record)
        return _fail(EXIT_INTERNAL, f'the harness did not start: {_ascii(exc)}')
    record.update(outcome='launched')
    state.write_json_atomic(run_json, record)
    while True:
        try:
            code = proc.wait()
            break
        except KeyboardInterrupt:
            continue
    record.update(outcome='ended', exit_code=code)
    state.write_json_atomic(run_json, record)
    return _exit_code(code)


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
    return parser


def main(argv: list[str]) -> int:
    """`kit run`; `argv` follows the word `run`."""
    try:
        if '--' not in argv:
            raise RefusalError('arguments: put -- before the harness arguments')
        cut = argv.index('--')
        args = build_parser().parse_args(argv[:cut])
        plan = preflight(
            args.harness, args.home, args.workdir, args.policy, argv[cut + 1 :], dict(os.environ)
        )
    except RefusalError as exc:
        return _fail(EXIT_REFUSED, f'run refused: {exc}')
    for line in plan.notices:
        sys.stderr.write(line + '\n')
    sys.stderr.flush()
    try:
        return launch(plan, dict(os.environ))
    except Exception as exc:  # the record says what happened; exit 70 names an internal error
        return _fail(EXIT_INTERNAL, f'run failed: {type(exc).__name__}: {_ascii(exc)}')

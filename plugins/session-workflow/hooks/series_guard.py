"""Series guard: a second `gh pr create` in one repository and session names its series.

    python series_guard.py --post-tool-use   # PostToolUse on Bash|PowerShell: record a created PR
    python series_guard.py --pre-tool-use    # PreToolUse on Bash|PowerShell: deny an undeclared second

Why. The owner's rule is that a series of two or more PR-sized changes goes through
keel's Definition of Ready and runs with convoy's gate as the judge of each change.
The 2026-10-25 diagnosis found the rule used only where an owner-written brief named
it: work that grew inside a session went PR by PR through an ad-hoc orchestrator.
The exact moment a session turns into a series is its second pull request in one
repository, and that is the moment this hook acts on.

How. `gh pr create` is matched at program position, after heredoc bodies and
comments are stripped and with quoted spans read as data (a commit message naming
the command is not the command). The PostToolUse arm records a repository for the
session only when the tool result's `stdout` carries a
`github.com/<owner>/<repo>/pull/<n>` URL: a failed command arrives as an error
string, and a backgrounded one carries a `backgroundTaskId` and no stdout, so
neither is recorded. The PreToolUse arm keys each create by lowercase `owner/repo`,
from `-R`/`--repo`, else from the `origin` URL in the git config of the command's
working directory (a worktree's common directory included), read from the file
without running git. The working directory is the payload's `cwd` unless the
command opens with `cd <dir>` or `Set-Location <dir>` followed by `&&`, `;` or a
newline; a relative directory resolves against the payload's `cwd`, and a Git Bash
path (`/c/...`) or `~` is translated first. A wrapper (`bash -c`, or `powershell`
or `pwsh`, with or without `.exe`, any options before `-Command` or `-c`) at any
program position has its quoted argument read as a command, so its opening `cd`
sets the directory too.

A create in a repository that already holds a recorded PR of this session is
denied unless the command carries `KEEL_SERIES=<path>` naming an existing file (a
relative path resolves against the working directory derived above) or
`KEEL_SERIES=none:<reason>`: in Bash as an environment prefix
(`KEEL_SERIES=v gh pr create ...`), in PowerShell as `$env:KEEL_SERIES='v'; gh pr
create ...`. Every decision on a create appends one line, with no command text, to
`series-guard/log.ndjson` in the plugin's data directory (`CLAUDE_PLUGIN_DATA`).

Boundary. The hooks see the session that loads the plugin: a subagent's calls carry
its parent's `session_id` and count with it, a separate `claude -p` process counts on
its own, and workers under convoy's config isolation load no plugin hooks.

Gate: `SESSION_WORKFLOW_SERIES_GUARD`. Unset or any other value: on. `observe`: log
the would-be deny and print nothing. `0`: off, nothing is read or written. Every
path exits 0, and an unreadable payload prints nothing: a hook must not break a
session.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

GATE = 'SESSION_WORKFLOW_SERIES_GUARD'
STATE_SUBDIR = 'series-guard'
LOG_NAME = 'log.ndjson'
SHELL_TOOLS = {'Bash': 'bash', 'PowerShell': 'powershell'}
MAX_DEPTH = 3

_PULL_URL = re.compile(r'github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)')
_ASSIGNMENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
_PS_ENV_SERIES = re.compile(r'^\$env:KEEL_SERIES\s*=\s*(.*)$', re.I | re.S)
_PS_COMMAND_FLAG = re.compile(r'^-c(o(m(m(a(n(d)?)?)?)?)?)?$', re.I)
_SCP_URL = re.compile(r'^(?:[^@/\s]+@)?([A-Za-z0-9.-]{2,}):(?!//)(.+)$')
_MSYS_DRIVE = re.compile(r'^/([A-Za-z])(?=/|$)')
_HOME_VARS = re.compile(r'^(\$HOME|\$\{HOME\}|\$env:USERPROFILE|\$env:HOME)(?=[/\\]|$)', re.I)
_HEREDOC = re.compile(r"""<<(-?)[ \t]*(?:'([^'\n]+)'|"([^"\n]+)"|\\?([A-Za-z_][\w.-]*))""")
_SEPARATORS = ('&&', '||', ';', '|', '&', '\n', '(', ')')
_OPENING_SEPS = ('&&', ';', '\n')
# After these words the next word is again at program position (bash and PowerShell).
_KEYWORDS = frozenset({'then', 'else', 'elif', 'do', 'if', 'while', 'until', '!', '{', '}', 'time'})

RULE = (
    "a series of two or more PR-sized changes goes through keel's Definition of Ready "
    "and runs with convoy's gate as the judge of each change"
)


# ---------------------------------------------------------------- environment


def mode() -> str:
    """off | observe | on. Unset is on; `0` turns the guard off; `observe` logs only."""
    if os.environ.get(GATE) == '0':
        return 'off'
    if os.environ.get(GATE) == 'observe':
        return 'observe'
    return 'on'


def _state_dir() -> Path:
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / STATE_SUBDIR


def _safe_session(session_id: object) -> str:
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(session_id))[:80]


def _state_path(session_id: object) -> Path:
    return _state_dir() / f'{_safe_session(session_id)}.json'


def load_state(session_id: object) -> dict:
    try:
        data = json.loads(_state_path(session_id).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict) and isinstance(data.get('repos'), dict):
        return data
    return {'session_id': str(session_id), 'repos': {}}


def save_state(session_id: object, state: dict) -> None:
    """Whole-file replace through a temp file, so a crash leaves the old record."""
    path = _state_path(session_id)
    with contextlib.suppress(Exception):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f'.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(state), encoding='utf-8')
        os.replace(tmp, path)


def log(entry: dict) -> None:
    with contextlib.suppress(Exception):
        path = _state_dir() / LOG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), **entry}
        with path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry) + '\n')


# -------------------------------------------------------------------- lexing


@dataclass
class Word:
    text: str = ''
    quoted: bool = False


@dataclass
class Statement:
    words: list[Word] = field(default_factory=list)
    sep: str = ''  # the separator that ended it; '' at the end of input

    def texts(self) -> list[str]:
        return [w.text for w in self.words]


class _Lexer:
    """A shell approximation: statements of words, quotes removed, data dropped.

    Heredoc bodies (bash) and here-strings (PowerShell) are dropped, `#` comments
    (and PowerShell `<# #>` blocks) are dropped, quoted spans become word text with
    the word marked quoted, and the separators `&&`, `||`, `;`, `|`, `&`, newline,
    `(`, `)` and `$(` end a statement. It is not a parser: it only has to find the
    program words and their arguments.
    """

    def __init__(self, text: str, shell: str):
        self.s = text.replace('\r\n', '\n')
        self.ps = shell == 'powershell'
        self.i = 0
        self.statements: list[Statement] = []
        self.current = Statement()
        self.word: Word | None = None
        self.heredocs: list[tuple[str, bool]] = []

    # word and statement boundaries
    def _ch(self, ch: str, quoted: bool = False) -> None:
        if self.word is None:
            self.word = Word()
        self.word.text += ch
        self.word.quoted = self.word.quoted or quoted

    def _end_word(self) -> None:
        if self.word is not None:
            self.current.words.append(self.word)
            self.word = None

    def _end_statement(self, sep: str) -> None:
        self._end_word()
        self.current.sep = sep
        self.statements.append(self.current)
        self.current = Statement()

    def _peek(self, n: int = 0) -> str:
        j = self.i + n
        return self.s[j] if j < len(self.s) else ''

    def _skip_heredoc_bodies(self) -> None:
        """At a newline (already consumed): drop the pending heredocs' lines."""
        for word, dash in self.heredocs:
            while self.i < len(self.s):
                end = self.s.find('\n', self.i)
                line = self.s[self.i : end if end >= 0 else len(self.s)]
                self.i = end + 1 if end >= 0 else len(self.s)
                if (line.lstrip('\t') if dash else line) == word:
                    break
        self.heredocs = []

    def _heredoc_op(self) -> bool:
        if self.ps or self.s.startswith('<<<', self.i) or (self.i and self.s[self.i - 1] == '<'):
            return False
        m = _HEREDOC.match(self.s, self.i)
        if not m:
            return False
        self.heredocs.append((m.group(2) or m.group(3) or m.group(4), m.group(1) == '-'))
        self.i = m.end()
        return True

    def _here_string(self) -> bool:
        """PowerShell `@'` / `@"` then a newline: drop through the closing `'@` / `"@` line."""
        if not self.ps or self._peek() != '@' or self._peek(1) not in '\'"' or not self._peek(1):
            return False
        quote = self._peek(1)
        rest = self.s[self.i + 2 :]
        if not rest.startswith('\n'):
            return False
        close = re.search(rf'\n{re.escape(quote)}@', rest)
        self.i = self.i + 2 + (close.end() if close else len(rest))
        self._ch('', quoted=True)
        return True

    def _single(self) -> None:
        self.i += 1  # opening quote
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch == "'":
                if self.ps and self._peek(1) == "'":
                    self._ch("'", True)
                    self.i += 2
                    continue
                self.i += 1
                break
            if ch == '\n' and self.heredocs:
                self._ch(ch, True)
                self.i += 1
                self._skip_heredoc_bodies()
                continue
            self._ch(ch, True)
            self.i += 1
        if self.word is None:
            self._ch('', True)

    def _double(self) -> None:
        self.i += 1
        esc = '`' if self.ps else '\\'
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch == esc and self.i + 1 < len(self.s):
                nxt = self.s[self.i + 1]
                if self.ps or nxt in '"\\$`\n':
                    if nxt != '\n':
                        self._ch(nxt, True)
                    self.i += 2
                    continue
            if ch == '"':
                if self.ps and self._peek(1) == '"':
                    self._ch('"', True)
                    self.i += 2
                    continue
                self.i += 1
                break
            if ch == '<' and self._heredoc_op():
                continue
            self._ch(ch, True)
            self.i += 1
            if ch == '\n' and self.heredocs:
                self._skip_heredoc_bodies()
        if self.word is None:
            self._ch('', True)

    def _comment(self) -> bool:
        ch = self._peek()
        if self.ps and ch == '<' and self._peek(1) == '#':
            close = self.s.find('#>', self.i + 2)
            self.i = close + 2 if close >= 0 else len(self.s)
            self._end_word()
            return True
        if ch != '#' or self.word is not None:
            return False
        end = self.s.find('\n', self.i)
        self.i = end if end >= 0 else len(self.s)
        return True

    def _separator(self) -> str | None:
        two = self.s[self.i : self.i + 2]
        if two in ('&&', '||'):
            return two
        if not self.ps and two == '$(':
            return '$('
        ch = self._peek()
        if ch == '&':
            prev = self.word.text[-1:] if self.word is not None else ''
            if prev in ('>', '<') or self._peek(1) == '>':
                return None  # a redirection (2>&1, &>), not a separator
        if ch in _SEPARATORS:
            return ch
        return None

    def run(self) -> list[Statement]:
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch in ' \t':
                self._end_word()
                self.i += 1
            elif self._comment() or self._here_string():
                continue
            elif ch == "'":
                self._single()
            elif ch == '"':
                self._double()
            elif ch == '<' and self._heredoc_op():
                self._end_word()
            elif (ch == '`' and self.ps) or (ch == '\\' and not self.ps):
                nxt = self._peek(1)
                if nxt == '\n':
                    self.i += 2
                elif nxt:
                    self._ch(nxt, True)
                    self.i += 2
                else:
                    self.i += 1
            elif (sep := self._separator()) is not None:
                self.i += len(sep)
                self._end_statement('(' if sep == '$(' else sep)
                if sep == '\n' and self.heredocs:
                    self._skip_heredoc_bodies()
            else:
                self._ch(ch)
                self.i += 1
        self._end_statement('')
        return [st for st in self.statements if st.words or st.sep]


def statements(command: str, shell: str) -> list[Statement]:
    return _Lexer(command, shell).run()


# ------------------------------------------------------------------ analysis


@dataclass
class Create:
    """One `gh pr create` found at program position."""

    repo_flag: str | None
    workdir: Path | None
    keel_series: str | None


def _program_name(word: str) -> str:
    name = re.split(r'[\\/]', word)[-1].lower()
    return name[:-4] if name.endswith('.exe') else name


def _home() -> Path:
    return Path.home()


def resolve_dir(arg: str | None, base: Path | None) -> Path | None:
    """The directory a `cd` argument names, or None when it cannot be resolved."""
    if arg is None or arg in ('', '~'):
        return _home()
    text = arg.strip()
    if text == '-':
        return None
    if text.startswith(('~/', '~\\')):
        text = str(_home()) + '/' + text[2:]
    m = _HOME_VARS.match(text)
    if m:
        text = str(_home()) + text[m.end() :]
    if os.name == 'nt':
        text = _MSYS_DRIVE.sub(lambda d: d.group(1).upper() + ':', text)
    if '$' in text or '`' in text or '%' in text:
        return None
    path = Path(text)
    if not path.is_absolute():
        if base is None:
            return None
        path = base / path
    return Path(os.path.normpath(str(path)))


def _cd_target(st: Statement) -> tuple[bool, str | None]:
    """(is a cd, its directory argument) for `cd` / `Set-Location` statements."""
    words = st.texts()
    if not words or words[0].lower() not in ('cd', 'set-location', 'chdir'):
        return False, None
    for w in words[1:]:
        if w in ('--', '-P', '-L', '-e', '-@') or w.lower() in ('-path', '-literalpath'):
            continue
        return True, w
    return True, None


def _wrapper_inner(name: str, args: list[Word]) -> tuple[str, str] | None:
    """(inner command, its shell) for a bash -c or powershell/pwsh -Command wrapper."""
    if name in ('bash', 'sh'):
        for k, w in enumerate(args):
            if w.quoted or not w.text.startswith('-'):
                return None  # the first operand is a script file, not a command string
            if w.text.startswith('--'):
                continue  # --login, --norc
            if 'c' in w.text[1:]:  # -c, or a cluster such as -lc
                return (args[k + 1].text, 'bash') if k + 1 < len(args) else None
        return None
    if name in ('powershell', 'pwsh'):
        for k, w in enumerate(args):
            if not w.quoted and _PS_COMMAND_FLAG.match(w.text):
                rest = args[k + 1 :]
                if not rest:
                    return None
                if rest[0].quoted:
                    return rest[0].text, 'powershell'
                return ' '.join(r.text for r in rest), 'powershell'
        return None
    return None


def _repo_flag(args: list[str]) -> str | None:
    for k, a in enumerate(args):
        if a in ('-R', '--repo'):
            return args[k + 1] if k + 1 < len(args) else None
        if a.startswith('--repo='):
            return a[len('--repo=') :]
        if a.startswith('-R') and not a.startswith('--') and len(a) > 2:
            return a[2:].lstrip('=')
    return None


def find_creates(
    command: str,
    shell: str,
    cwd: Path | None,
    env: dict[str, str] | None = None,
    depth: int = 0,
) -> list[Create]:
    """Every `gh pr create` at program position, with its working directory and
    the KEEL_SERIES value it carries."""
    env = dict(env or {})
    found: list[Create] = []
    sts = statements(command, shell)
    workdir = cwd
    k = 0
    while k < len(sts):  # the opening cd / Set-Location statements set the directory
        st = sts[k]
        if not st.words:
            k += 1
            continue
        is_cd, arg = _cd_target(st)
        if not is_cd or st.sep not in _OPENING_SEPS:
            break
        workdir = resolve_dir(arg, workdir)
        k += 1
    for st in sts[k:]:
        words = st.words
        if not words:
            continue
        joined = ' '.join(st.texts())
        ps_set = _PS_ENV_SERIES.match(joined) if shell == 'powershell' else None
        if ps_set:
            env['KEEL_SERIES'] = ps_set.group(1).strip()
            continue
        local = dict(env)
        pos = 0
        if words[0].text == 'export':
            for w in words[1:]:
                if w.text.startswith('KEEL_SERIES='):
                    env['KEEL_SERIES'] = w.text.split('=', 1)[1]
            continue
        while pos < len(words):
            text = words[pos].text
            if text in _KEYWORDS and not words[pos].quoted:
                pos += 1
            elif _ASSIGNMENT.match(text):
                name, value = text.split('=', 1)
                local[name] = value
                pos += 1
            elif _program_name(text) == 'env' and not words[pos].quoted:
                pos += 1
                while pos < len(words) and words[pos].text.startswith('-'):
                    pos += 1
            else:
                break
        if pos >= len(words):
            continue
        name = _program_name(words[pos].text)
        args = words[pos + 1 :]
        texts = [a.text for a in args]
        if name == 'gh' and texts[:2] == ['pr', 'create']:
            found.append(Create(_repo_flag(texts[2:]), workdir, local.get('KEEL_SERIES')))
            continue
        if depth < MAX_DEPTH:
            inner = _wrapper_inner(name, args)
            if inner is not None:
                found.extend(find_creates(inner[0], inner[1], workdir, local, depth + 1))
    return found


# ------------------------------------------------------------- repository key


def repo_key(spec: str | None) -> str | None:
    """Lowercase `owner/repo` from `-R` / a remote URL, or None."""
    if not spec:
        return None
    text = spec.strip().strip('\'"').rstrip('/')
    if text.endswith('.git'):
        text = text[:-4]
    if '://' in text:
        text = text.split('://', 1)[1]
        text = text.split('/', 1)[1] if '/' in text else ''
    else:
        m = _SCP_URL.match(text)
        if m and len(m.group(1)) > 1:
            text = m.group(2)
    parts = [p for p in text.split('/') if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[-2], parts[-1]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo):
        return None
    return f'{owner}/{repo}'.lower()


def _git_config(start: Path) -> Path | None:
    """The config file of the repository holding `start` (a worktree's common one)."""
    for d in (start, *start.parents):
        dot = d / '.git'
        if dot.is_dir():
            return dot / 'config'
        if dot.is_file():
            try:
                line = dot.read_text(encoding='utf-8').strip()
            except OSError:
                return None
            if not line.startswith('gitdir:'):
                return None
            gitdir = Path(line[len('gitdir:') :].strip())
            if not gitdir.is_absolute():
                gitdir = d / gitdir
            common = gitdir
            with contextlib.suppress(OSError):
                rel = (gitdir / 'commondir').read_text(encoding='utf-8').strip()
                common = Path(rel) if Path(rel).is_absolute() else gitdir / rel
            return common / 'config'
    return None


def origin_url(workdir: Path | None) -> str | None:
    if workdir is None:
        return None
    config = _git_config(workdir)
    if config is None:
        return None
    try:
        text = config.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    in_origin = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('['):
            m = re.match(r'\[\s*remote\s+"([^"]*)"\s*\]', line, re.I)
            in_origin = bool(m) and m.group(1) == 'origin'
            continue
        if in_origin:
            m = re.match(r'url\s*=\s*(.+)$', line, re.I)
            if m:
                return m.group(1).strip().strip('"')
    return None


def key_for(create: Create) -> str | None:
    return repo_key(create.repo_flag) or repo_key(origin_url(create.workdir))


# ------------------------------------------------------------------ handlers


def _command(payload: dict) -> tuple[str, str] | None:
    shell = SHELL_TOOLS.get(str(payload.get('tool_name') or ''))
    tool_input = payload.get('tool_input')
    command = tool_input.get('command') if isinstance(tool_input, dict) else None
    if shell is None or not isinstance(command, str):
        return None
    if 'create' not in command or 'pr' not in command:
        return None  # the cheap exit: nearly every shell call ends here
    return command, shell


def _cwd(payload: dict) -> Path | None:
    cwd = payload.get('cwd')
    return Path(cwd) if isinstance(cwd, str) and cwd else None


def handle_post_tool_use(payload: dict) -> None:
    """Record the repository of each PR a `gh pr create` printed on stdout."""
    if mode() == 'off':
        return
    session_id = payload.get('session_id')
    found = _command(payload)
    if not session_id or found is None:
        return
    if not find_creates(found[0], found[1], _cwd(payload)):
        return
    response = payload.get('tool_response')
    if not isinstance(response, dict) or response.get('backgroundTaskId'):
        return
    stdout = response.get('stdout')
    if not isinstance(stdout, str):
        return
    urls = {}
    for m in _PULL_URL.finditer(stdout):
        key = f'{m.group(1)}/{m.group(2)}'.lower()
        urls.setdefault(key, f'https://github.com/{m.group(1)}/{m.group(2)}/pull/{m.group(3)}')
    if not urls:
        return
    state = load_state(session_id)
    for key, url in urls.items():
        prs = state['repos'].setdefault(key, [])
        if url not in prs:
            prs.append(url)
        log(
            {
                'session': str(session_id),
                'event': 'PostToolUse',
                'decision': 'record',
                'repo': key,
                'pr': url,
            }
        )
    save_state(session_id, state)


def _series_ok(value: str | None, base: Path | None) -> tuple[bool, str]:
    """(satisfies the rule, why not) for a KEEL_SERIES value."""
    if value is None:
        return False, 'The command carries no KEEL_SERIES.'
    value = value.strip().strip('\'"').strip()
    if value.lower().startswith('none:'):
        if value[5:].strip():
            return True, ''
        return False, 'KEEL_SERIES=none: needs a reason after the colon.'
    path = resolve_dir(value, base)
    if path is not None and path.is_file():
        return True, ''
    shown = str(path) if path is not None else value
    return False, f'KEEL_SERIES names {shown}, which is not an existing file.'


def deny_reason(key: str, prs: list[str], why: str) -> str:
    first = prs[0] if prs else 'an earlier PR'
    return (
        f'Series guard: this session already created a pull request in {key} ({first}), and '
        f"this command creates another there. {why} The owner's rule: {RULE}. To satisfy it, "
        'name the series file or spec that governs this change in the command: in Bash, '
        '`KEEL_SERIES=<path> gh pr create ...`; in PowerShell, '
        "`$env:KEEL_SERIES='<path>'; gh pr create ...` (a relative path resolves against the "
        "command's working directory). If this PR is not part of a series, say why with "
        '`KEEL_SERIES=none:<reason>` (for example `none:hotfix`). The value given is logged.'
    )


def handle_pre_tool_use(payload: dict) -> dict | None:
    """Deny a create in a repository this session already holds a recorded PR in."""
    current = mode()
    if current == 'off':
        return None
    session_id = payload.get('session_id')
    found = _command(payload)
    if not session_id or found is None:
        return None
    creates = find_creates(found[0], found[1], _cwd(payload))
    if not creates:
        return None
    state = load_state(session_id)
    reasons: list[str] = []
    for create in creates:
        key = key_for(create)
        entry = {
            'session': str(session_id),
            'event': 'PreToolUse',
            'tool': str(payload.get('tool_name')),
            'repo': key,
            'keel_series': create.keel_series,
        }
        prs = state['repos'].get(key) if key else None
        if not prs:
            log({**entry, 'decision': 'allow' if key else 'unkeyed'})
            continue
        ok, why = _series_ok(create.keel_series, create.workdir)
        if ok:
            log({**entry, 'decision': 'allow', 'prs': prs})
            continue
        log({**entry, 'decision': 'deny' if current == 'on' else 'observe-deny', 'prs': prs})
        reasons.append(deny_reason(key, prs, why))
    if not reasons or current != 'on':
        return None
    return {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': '\n'.join(reasons),
        }
    }


def _load_stdin_json() -> dict | None:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8-sig', errors='replace')
        data = json.loads(raw) if raw.strip() else None
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        payload = _load_stdin_json()
        if payload is None:
            return 0
        event = str(payload.get('hook_event_name') or '')
        if '--post-tool-use' in argv or (event == 'PostToolUse' and '--pre-tool-use' not in argv):
            handle_post_tool_use(payload)
            return 0
        if '--pre-tool-use' in argv or event == 'PreToolUse':
            output = handle_pre_tool_use(payload)
            if output is not None:
                with contextlib.suppress(Exception):
                    sys.stdout.reconfigure(encoding='utf-8')
                sys.stdout.write(json.dumps(output) + '\n')
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

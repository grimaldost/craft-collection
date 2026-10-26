"""Owner-acts gate: an act only the owner may authorize needs a sentence of the owner that names it.

    python owner_acts_gate.py --prompt-submit   # UserPromptSubmit: record the owner's latest prompt
    python owner_acts_gate.py --pre-tool-use    # PreToolUse: deny an owner-only act the prompt did not name

Without a flag the script dispatches on the payload's `hook_event_name`.

Why. The 2026-10-25 diagnosis of the owner's sessions found agents editing the
global CLAUDE.md and settings.json, running `claude plugin update` and setting a
user environment variable on a generic go-on ("pode seguir com as
recomendacoes"). A prose rule against it was in context and lost at the moment of
choice; this hook is the mechanism.

How. The UserPromptSubmit arm records, per session, the text of the latest
owner-typed prompt (`prompt_kind.py`; a task notification, subagent hand-back or
peer message leaves the record as it was) under the plugin's data directory. The
PreToolUse arm, on Bash, PowerShell, Edit, Write, MultiEdit and NotebookEdit,
finds four families of act:

1. a write to the governed `CLAUDE.md`, `settings.json` or `settings.local.json`
   (`governed_home.py`): by an editing tool's resolved path, or by a shell command
   that writes the file (this shell-write arm is observed, never denied);
2. `claude plugin` install, update, uninstall, enable, disable, or marketplace
   add, remove, update;
3. setting a user or machine environment variable (`setx`,
   `[Environment]::SetEnvironmentVariable` with a User or Machine target);
4. `git config --global` with a value.

Shell text is read with heredoc bodies (unless a shell runs them), PowerShell
here-strings and comments blanked; a program is recognised only at program
position, on the tokens outside quotes, and its discriminating arguments (the
path, the plugin id, the variable name and scope, the git key) are read with their
quotes removed. Read-only forms (`--get`, `--list`, `marketplace list`, `cat`,
`type`, `Get-Content`) are not acts. A `bash -c`, `powershell`/`pwsh` `-Command`
or `cmd /c` wrapper has its argument read as a command, and a wrapper whose quoted
argument contains a family's program token is matched as that family even when
the inner command cannot be read (over-matching on the deny side).

The rule (`authorizing_sentence`). A matched act is allowed only when one sentence
of the recorded prompt names its object (family 1: the file's name; family 2:
`claude plugin` or the literal `plugin@marketplace` id; family 3: "variavel de
ambiente", "environment variable", "env var" or the variable's name as written; family 4:
`git config`) and an act verb of that family's closed list, with no negation and
no conditional or purpose marker earlier than the verb, and the sentence is not a
question. A permission modal ("pode", "can") alone never authorizes. `no` is the
Portuguese contraction (em + o) when the next word is the object and the verb is a
Portuguese form, and a negation otherwise. The prompt is folded to lowercase ASCII
(accents removed) before matching, so the closed lists are plain ASCII.

Otherwise the act is denied, with a reason telling the agent to put the act to
the owner in the final block, framed, naming the family and its side effects.

Gate: `SESSION_WORKFLOW_OWNER_ACTS_GATE`. Unset: on (an exact trigger). `observe`:
every decision is logged and nothing is denied. `0`: off, nothing is read or
written. Every decision on a matched act (allow, deny, observe) appends one line
to `owner-acts-gate/log.ndjson` in the plugin's data directory; the line names the
family and its key (path, plugin id, variable name, git key), never a value.
Output is UTF-8 whatever the console codepage. Every path exits 0 and a failure
prints nothing: a hook must not break a session.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from governed_home import GOVERNED_FILES, governed_home
    from prompt_kind import is_owner_typed
except Exception:  # a partial install fails open: the hook does nothing at all
    GOVERNED_FILES = ()

    def governed_home(environ=None):  # type: ignore[no-redef]
        raise RuntimeError('governed_home.py is missing')

    def is_owner_typed(prompt: object) -> bool:  # type: ignore[no-redef]
        return False


GATE = 'SESSION_WORKFLOW_OWNER_ACTS_GATE'
STATE_DIR_ENV = 'SESSION_WORKFLOW_OWNER_ACTS_GATE_DIR'
TOOLS = ('Bash', 'PowerShell', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit')
MAX_PROMPT_CHARS = 20000
MAX_DEPTH = 4

FAMILY_NAMES = {
    1: 'a write to the global CLAUDE.md, settings.json or settings.local.json',
    2: 'a claude plugin install, update, uninstall, enable, disable or marketplace change',
    3: 'setting a user or machine environment variable',
    4: 'a git config --global write',
}
SIDE_EFFECTS = {
    1: 'it changes the instructions or settings that every later session on this machine '
    'loads, in every project',
    2: 'it changes the plugin code that every new session loads, in every project, and '
    'the session cannot undo it',
    3: 'it persists in the user or machine environment of every later process, outside '
    'any repository',
    4: 'it changes the git behaviour or identity of every repository on this machine',
}
EXAMPLES = {
    1: "'pode editar o CLAUDE.md'",
    2: "'pode atualizar o <plugin>@<marketplace>'",
    3: "'pode definir a variavel de ambiente <NAME>'",
    4: "'pode alterar o git config global'",
}


# ------------------------------------------------------------------ the rule

_PT = 'pt'
_EN = 'en'


def _forms(*stems: str) -> frozenset[str]:
    return frozenset(w for s in stems for w in s.split())


# Closed act-verb lists, infinitive and imperative forms, folded to ASCII.
_PT_EDIT = _forms(
    'editar edite edita alterar altere altera atualizar atualize atualiza mudar mude muda',
    'modificar modifique modifica gravar grave grava escrever escreva escreve ajustar ajuste',
    'ajusta corrigir corrija corrige acrescentar acrescente acrescenta adicionar adicione',
    'adiciona incluir inclua inclui aplicar aplique aplica remover remova remove substituir',
    'substitua substitui trocar troque troca inserir insira insere salvar salve salva',
)
_EN_EDIT = _forms('edit change update modify write add append insert adjust fix apply remove')
_EN_EDIT = _EN_EDIT | _forms('replace set put save amend patch')
_PT_PLUGIN = _forms(
    'instalar instale instala desinstalar desinstale desinstala reinstalar reinstale',
    'atualizar atualize atualiza habilitar habilite habilita desabilitar desabilite',
    'desabilita ativar ative ativa desativar desative desativa remover remova remove',
    'adicionar adicione adiciona',
)
_EN_PLUGIN = _forms('install uninstall reinstall update upgrade enable disable remove add')
_PT_ENV = _forms(
    'definir defina define setar sete seta criar crie cria configurar configure configura',
    'gravar grave grava alterar altere altera mudar mude muda atualizar atualize atualiza',
    'adicionar adicione adiciona remover remova remove',
)
_EN_ENV = _forms('set create define configure change update add remove persist export')
_PT_GIT = _forms(
    'definir defina define setar sete seta configurar configure configura alterar altere',
    'altera mudar mude muda atualizar atualize atualiza ajustar ajuste ajusta editar edite',
    'edita',
)
_EN_GIT = _forms('set configure change update edit adjust')
# Run verbs (rodar, executar, run) are left out: "the jobs run on the runner" names no act.

VERBS = {
    1: {_PT: _PT_EDIT, _EN: _EN_EDIT},
    2: {_PT: _PT_PLUGIN, _EN: _EN_PLUGIN},
    3: {_PT: _PT_ENV, _EN: _EN_ENV},
    4: {_PT: _PT_GIT, _EN: _EN_GIT},
}
NEGATIONS = _forms('nao nunca sem nem jamais dont not cannot never no')
CONDITIONS = _forms('se caso quando if unless whether')
CONDITION_PHRASES = ('para eu', 'pra eu', 'para que', 'in case', 'so that i', 'antes de')
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+|\n+|;')
_REMINDER = re.compile(r'<system-reminder>.*?(?:</system-reminder>|\Z)', re.S)


def fold(text: str) -> str:
    """Lowercase ASCII: accents removed, typographic apostrophes made plain."""
    text = text.replace(chr(0x2019), "'").replace(chr(0x2018), "'")
    decomposed = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).lower()


def sentences(prompt: str) -> list[str]:
    """The prompt's sentences, `<system-reminder>` blocks removed (no owner wrote them)."""
    text = _REMINDER.sub('\n', prompt or '')
    return [s.strip() for s in _SENTENCE_END.split(text) if s and s.strip()]


@dataclass
class Act:
    """One owner-only act found in a tool call."""

    family: int
    arm: str  # 'edit' (an editing tool), 'shell' (a program), 'shell-write' (observed only)
    key: str | None  # the file name, plugin id, variable name or git key; None when unread
    summary: str
    extra: dict = field(default_factory=dict)


_EDGE_BEFORE = r'(?<![\w@.\-])'
_EDGE_AFTER = r'(?!\.?[\w@\-])'


def _object_spans(act: Act, norm: str, sentence: str) -> list[tuple[int, int]]:
    patterns: list[str] = []
    if act.family == 1:
        name = fold(act.key or '')
        patterns = [re.escape(name)] if name else []
    elif act.family == 2:
        patterns = [r'claude\s+plugins?']
        if act.key and '@' in act.key:
            patterns.append(re.escape(fold(act.key)))
    elif act.family == 3:
        patterns = [
            r'variave(?:l|is)\s+de\s+ambiente',
            r'environment\s+variables?',
            r'env\s*vars?',
        ]
        # The variable's name counts only as written, case and all: "dono" is not DONO.
        key = act.key or ''
        if len(key) >= 2 and re.search(_EDGE_BEFORE + re.escape(key) + _EDGE_AFTER, sentence):
            patterns.append(re.escape(fold(key)))
    elif act.family == 4:
        patterns = [r'git\s+config']
    spans = []
    for pattern in patterns:
        for m in re.finditer(_EDGE_BEFORE + pattern + _EDGE_AFTER, norm):
            spans.append((m.start(), m.end()))
    return spans


def _sentence_authorizes(sentence: str, act: Act) -> bool:
    norm = fold(sentence).strip()
    if not norm or norm.endswith('?'):
        return False
    objects = _object_spans(act, norm, sentence)
    if not objects:
        return False
    object_starts = {start for start, _ in objects}
    words = [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(norm)]
    verbs = VERBS[act.family]
    for index, (word, start, end) in enumerate(words):
        lang = _PT if word in verbs[_PT] else _EN if word in verbs[_EN] else None
        if lang is None:
            continue
        if any(a <= start and end <= b for a, b in objects):
            continue  # the word is part of the object, not its verb
        if _clean_before(norm, words, index, start, object_starts, lang):
            return True
    return False


def _clean_before(norm, words, index, verb_start, object_starts, lang) -> bool:
    """No negation and no conditional or purpose marker earlier than the verb."""
    for position, (word, _start, _end) in enumerate(words[:index]):
        if word == 'no':
            following = words[position + 1][1] if position + 1 < len(words) else None
            if lang == _PT and following is not None and following in object_starts:
                continue  # em + o before the object, with a Portuguese verb
            return False
        if word in NEGATIONS or word.endswith("n't") or word in CONDITIONS:
            return False
    head = norm[:verb_start]
    return not any(re.search(rf'\b{re.escape(p)}\b', head) for p in CONDITION_PHRASES)


def authorizing_sentence(prompt: str | None, act: Act) -> str | None:
    """The first sentence of `prompt` that authorizes `act`, or None."""
    for sentence in sentences(prompt or ''):
        if _sentence_authorizes(sentence, act):
            return sentence
    return None


# --------------------------------------------------------------- shell text


@dataclass
class Token:
    value: str  # quotes removed, escapes resolved
    quoted: bool = False
    op: bool = False  # a redirection operator


@dataclass
class Scan:
    commands: list[list[Token]]
    masked: str  # same length as the input: quoted spans, comments and bodies blanked
    scripts: list[tuple[str, str]]  # heredoc bodies a shell runs: (text, shell)


_POSIX_SHELLS = frozenset({'bash', 'sh', 'zsh', 'dash', 'ksh'})
_PS_SHELLS = frozenset({'powershell', 'pwsh'})
_HEREDOC = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]+)'|\"([^\"\n]+)\"|\\?([A-Za-z_][\w.-]*))")
_SETENV = re.compile(
    r'\[\s*(?:system\s*\.\s*)?environment\s*\]\s*::\s*setenvironmentvariable\s*\(', re.I
)
_ASSIGNMENT = re.compile(r'^[A-Za-z_]\w*=')
_PREFIX_WORDS = frozenset({'sudo', 'command', 'exec', 'time', 'nohup', 'builtin', 'env', 'call'})


def program_name(value: str) -> str:
    """The basename of a program word, lowercased, without .exe/.cmd/.bat/.ps1."""
    name = re.split(r'[\\/]', value.strip())[-1].lower()
    for suffix in ('.exe', '.cmd', '.bat', '.ps1'):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def scan(text: str, shell: str) -> Scan:
    """Split shell text into simple commands of tokens; `shell` is 'bash' or 'powershell'."""
    posix = shell == 'bash'
    n = len(text)
    masked = list(text)
    commands: list[list[Token]] = []
    scripts: list[tuple[str, str]] = []
    current: list[Token] = []
    value: list[str] | None = None
    quoted = False
    pending: list[tuple[str, bool]] = []

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if masked[k] != '\n':
                masked[k] = ' '

    def end_token() -> None:
        nonlocal value, quoted
        if value is not None:
            current.append(Token(''.join(value), quoted))
        value, quoted = None, False

    def end_command() -> None:
        nonlocal current
        end_token()
        if current:
            commands.append(current)
        current = []

    def take_heredocs(i: int) -> int:
        """Consume the bodies of the pending heredocs after the newline at `i`."""
        program = _program_of(commands[-1]) if commands else None
        runs = program in _POSIX_SHELLS or program in _PS_SHELLS
        pos = i + 1
        for word, dash in pending:
            body: list[str] = []
            start = pos
            while pos < n:
                nl = text.find('\n', pos)
                line_end = n if nl < 0 else nl
                line = text[pos:line_end].rstrip('\r')
                pos = line_end + 1
                if (line.lstrip('\t') if dash else line) == word:
                    break
                body.append(line)
            if runs:
                scripts.append(('\n'.join(body), 'powershell' if program in _PS_SHELLS else 'bash'))
            blank(start, pos)
        pending.clear()
        return pos

    i = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ''
        if ch == '\n':
            end_command()
            if pending:
                i = take_heredocs(i)
                continue
            i += 1
            continue
        if ch in ' \t\r':
            end_token()
            i += 1
            continue
        if value is None and ch == '#':
            stop = text.find('\n', i)
            stop = n if stop < 0 else stop
            blank(i, stop)
            i = stop
            continue
        if not posix and value is None and ch == '<' and nxt == '#':
            stop = text.find('#>', i + 2)
            stop = n if stop < 0 else stop + 2
            blank(i, stop)
            i = stop
            continue
        if not posix and value is None and ch == '@' and nxt in '\'"':
            rest = text[i + 2 :]
            m = re.match(r'[ \t]*\r?\n', rest)
            if m:
                close = '\n' + nxt + '@'
                stop = text.find(close, i + 2)
                stop = n if stop < 0 else stop + len(close)
                body = text[i + 2 + m.end() : max(i + 2 + m.end(), stop - len(close))]
                end_token()
                current.append(Token(body, True))
                blank(i, stop)
                i = stop
                continue
        if ch == "'":
            stop = i + 1
            chunk: list[str] = []
            while stop < n:
                if text[stop] == "'":
                    if not posix and stop + 1 < n and text[stop + 1] == "'":
                        chunk.append("'")
                        stop += 2
                        continue
                    break
                chunk.append(text[stop])
                stop += 1
            value = (value or []) + chunk
            quoted = True
            blank(i, stop + 1)
            i = stop + 1
            continue
        if ch == '"':
            stop = i + 1
            chunk = []
            while stop < n and text[stop] != '"':
                c = text[stop]
                if posix and c == '\\' and stop + 1 < n and text[stop + 1] in '"\\$`\n':
                    if text[stop + 1] != '\n':
                        chunk.append(text[stop + 1])
                    stop += 2
                    continue
                if not posix and c == '`' and stop + 1 < n:
                    chunk.append(text[stop + 1])
                    stop += 2
                    continue
                chunk.append(c)
                stop += 1
            value = (value or []) + chunk
            quoted = True
            blank(i, stop + 1)
            i = stop + 1
            continue
        if (posix and ch == '\\') or (not posix and ch == '`'):
            if nxt == '\n':
                i += 2
                continue
            if nxt:
                value = (value or []) + [nxt]
            i += 2
            continue
        if posix and ch == '<' and nxt == '<' and text[i + 2 : i + 3] != '<':
            m = _HEREDOC.match(text, i)
            if m:
                end_token()
                pending.append((m.group(2) or m.group(3) or m.group(4), m.group(1) == '-'))
                i = m.end()
                continue
        if ch == '$' and nxt == '{' and posix:
            stop = text.find('}', i)
            stop = n if stop < 0 else stop + 1
            value = (value or []) + list(text[i:stop])
            i = stop
            continue
        if ch == '$' and nxt == '(':
            end_command()
            i += 2
            continue
        if ch in '>' or (ch == '&' and nxt == '>') or (ch == '<' and value is None):
            digits = value is not None and ''.join(value).isdigit() and not quoted
            if digits:
                value, quoted = None, False
            end_token()
            stop = i + 1
            while stop < n and text[stop] in '>&|':
                stop += 1
            while stop < n and text[stop].isdigit() and text[stop - 1] == '&':
                stop += 1
            current.append(Token(text[i:stop], op=True))
            i = stop
            continue
        if ch in ';|&()`' or (ch in '{}' and value is None and (not nxt or nxt in ' \t\n;')):
            end_command()
            i += 1
            continue
        value = (value or []) + [ch]
        i += 1
    end_command()
    return Scan(commands, ''.join(masked), scripts)


def _program_index(tokens: list[Token]) -> int | None:
    skip_next = False
    for index, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if token.op:
            skip_next = not token.value.endswith(('&1', '&2')) and len(token.value) <= 2
            continue
        if not token.quoted and _ASSIGNMENT.match(token.value):
            continue
        name = program_name(token.value)
        if name in _PREFIX_WORDS or (name.startswith('-') and index > 0):
            continue
        if token.value in ('.', '&'):
            continue
        return index
    return None


def _program_of(tokens: list[Token]) -> str | None:
    index = _program_index(tokens)
    return None if index is None else program_name(tokens[index].value)


def _args(tokens: list[Token], index: int) -> list[Token]:
    """The argument tokens after the program, redirections and their targets dropped."""
    out: list[Token] = []
    skip_next = False
    for token in tokens[index + 1 :]:
        if skip_next:
            skip_next = False
            continue
        if token.op:
            skip_next = len(token.value) <= 2 and not token.value.endswith(('&1', '&2'))
            continue
        out.append(token)
    return out


_PLUGIN_ACTS = frozenset({'install', 'i', 'update', 'uninstall', 'remove', 'rm', 'enable'})
_PLUGIN_ACTS = _PLUGIN_ACTS | {'disable'}
_MARKET_ACTS = frozenset({'add', 'remove', 'rm', 'update'})
_GIT_VALUE_OPTS = frozenset({'-C', '-c', '--git-dir', '--work-tree', '--namespace'})
_GIT_CONFIG_READS = frozenset(
    {'--get', '--get-all', '--get-regexp', '--get-urlmatch', '--get-color', '--get-colorbool'}
) | {'--list', '-l'}
_GIT_CONFIG_WRITES = frozenset(
    {'--unset', '--unset-all', '--add', '--replace-all', '--edit', '-e', '--rename-section'}
) | {'--remove-section'}
_GIT_CONFIG_VALUE_OPTS = frozenset({'--type', '--default', '--file', '-f', '--blob', '--comment'})


def _positionals(args: list[Token]) -> list[str]:
    return [t.value for t in args if not t.value.startswith('-')]


def _claude_act(args: list[Token], text: str) -> Act | None:
    words = _positionals(args)
    if len(words) < 2 or words[0].lower() not in ('plugin', 'plugins'):
        return None
    if any(t.value in ('--help', '-h') for t in args):
        return None  # a help page changes nothing
    sub = words[1].lower()
    if sub in _PLUGIN_ACTS:
        key = words[2] if len(words) > 2 else None
        return Act(2, 'shell', key, f'claude plugin {sub} {key or ""}'.strip())
    if sub == 'marketplace' and len(words) > 2 and words[2].lower() in _MARKET_ACTS:
        key = words[3] if len(words) > 3 else None
        return Act(
            2, 'shell', key, f'claude plugin marketplace {words[2].lower()} {key or ""}'.strip()
        )
    return None


def _setx_act(args: list[Token]) -> Act | None:
    values = [t.value for t in args]
    if any(v in ('/?', '-?') for v in values):
        return None
    names = [v for v in values if not v.startswith(('/', '-'))]
    if not names:
        return None
    return Act(3, 'shell', names[0], f'setx {names[0]}')


def _git_act(args: list[Token]) -> Act | None:
    values = [t.value for t in args]
    k = 0
    while k < len(values) and values[k].startswith('-'):
        k += 2 if values[k] in _GIT_VALUE_OPTS else 1
    if k >= len(values) or values[k] != 'config':
        return None
    rest = values[k + 1 :]
    if '--global' not in rest:
        return None
    if any(v in _GIT_CONFIG_READS or v.startswith('--get') for v in rest):
        return None
    positional: list[str] = []
    skip = False
    for v in rest:
        if skip:
            skip = False
        elif v in _GIT_CONFIG_VALUE_OPTS:
            skip = True
        elif not v.startswith('-'):
            positional.append(v)
    if positional and positional[0] in ('get', 'list'):
        return None
    writes = any(v in _GIT_CONFIG_WRITES for v in rest)
    if positional and positional[0] in ('set', 'unset', 'edit', 'rename-section', 'remove-section'):
        key = positional[1] if len(positional) > 1 else None
        return Act(4, 'shell', key, f'git config --global {positional[0]} {key or ""}'.strip())
    if writes or len(positional) >= 2:
        key = positional[0] if positional else None
        return Act(4, 'shell', key, f'git config --global {key or ""}'.strip())
    return None


def _wrapper_inner(name: str, args: list[Token]) -> tuple[str, str] | None:
    """The command text a wrapper runs, and its shell, or None when it is not a wrapper call."""
    if name in _POSIX_SHELLS:
        for k, token in enumerate(args):
            v = token.value
            if re.fullmatch(r'-[a-zA-Z]*c[a-zA-Z]*', v) and not token.quoted:
                rest = [t for t in args[k + 1 :] if not t.value.startswith('-')]
                return (rest[0].value, 'bash') if rest else None
        return None
    if name in _PS_SHELLS:
        for k, token in enumerate(args):
            if re.fullmatch(r'[-/]c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?', token.value, re.I):
                return ' '.join(t.value for t in args[k + 1 :]), 'powershell'
        return None
    if name == 'cmd':
        for k, token in enumerate(args):
            if token.value.lower() in ('/c', '/k'):
                return ' '.join(t.value for t in args[k + 1 :]), 'powershell'
    return None


_FAMILY_TOKENS = (
    (2, re.compile(r'\bclaude(?:\.exe)?\s+(?:-\S+\s+)*plugins?\b', re.I)),
    (3, re.compile(r'\bsetx\b|setenvironmentvariable', re.I)),
    (4, re.compile(r'\bgit(?:\.exe)?\s+(?:-\S+\s+)*config\b[^\n]*--global\b', re.I)),
)
_GOVERNED_NAME = re.compile(r'claude\.md|settings\.json|settings\.local\.json', re.I)
_PATH_CANDIDATE = re.compile(
    r'[^\s\'"=(),;<>|]*?(?:CLAUDE\.md|settings\.local\.json|settings\.json)(?![\w.])', re.I
)
_READ_ONLY = frozenset(
    {
        'cat',
        'type',
        'get-content',
        'gc',
        'head',
        'tail',
        'less',
        'more',
        'grep',
        'rg',
        'findstr',
        'select-string',
        'sls',
        'wc',
        'diff',
        'sha256sum',
        'md5sum',
        'get-filehash',
        'test-path',
        'ls',
        'dir',
        'get-item',
        'get-childitem',
        'stat',
        'file',
        'echo',
        'write-host',
        'write-output',
        'awk',
        'jq',
        'sort',
        'cut',
        'ssh',
    }
)


def _expand(value: str, cwd: str | None) -> list[Path]:
    """Candidate paths a shell word may name: home variables expanded, Git Bash drives mapped."""
    home = str(Path.home())
    text = value
    for pattern in (
        r'^~(?=[\\/]|$)',
        r'\$\{?HOME\}?',
        r'\$env:(?:USERPROFILE|HOME)',
        r'%USERPROFILE%',
        r'\$\{?USERPROFILE\}?',
    ):
        text = re.sub(pattern, lambda _m: home, text, flags=re.I)
    config = os.environ.get('CLAUDE_CONFIG_DIR') or ''
    if config:
        text = re.sub(r'\$\{?CLAUDE_CONFIG_DIR\}?|\$env:CLAUDE_CONFIG_DIR', lambda _m: config, text)
    m = re.match(r'^/([a-zA-Z])/(.*)$', text)
    if m:
        text = f'{m.group(1)}:/{m.group(2)}'
    path = Path(text)
    if not path.is_absolute():
        path = Path(cwd or os.getcwd()) / path
    return [path]


def _same_path(a: Path, b: Path) -> bool:
    def norm(p: Path) -> str:
        try:
            p = p.resolve(strict=False)
        except (OSError, RuntimeError):
            pass
        return os.path.normcase(os.path.normpath(str(p)))

    return norm(a) == norm(b)


def governed_target(value: str, cwd: str | None) -> str | None:
    """The governed file name `value` resolves to, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    home = governed_home()
    for name in GOVERNED_FILES:
        target = home / name
        for candidate in _expand(value.strip(), cwd):
            if _same_path(candidate, target):
                return name
    return None


def _shell_write(tokens: list[Token], index: int | None, cwd: str | None) -> Act | None:
    """A shell command that names a governed file and is not a read-only form."""
    program = None if index is None else program_name(tokens[index].value)
    if program == 'sed' and not any(t.value.startswith(('-i', '--in-place')) for t in tokens):
        program = 'cat'  # sed without -i only prints
    after_redirect = False
    for token in tokens:
        if token.op:
            after_redirect = token.value.startswith(('>', '&>')) or '>' in token.value
            continue
        for m in _PATH_CANDIDATE.finditer(token.value):
            name = governed_target(m.group(0), cwd)
            if name and (after_redirect or program not in _READ_ONLY):
                return Act(1, 'shell-write', name, f'shell write to {name}')
        after_redirect = False
    return None


def _setenv_acts(text: str, masked: str) -> list[Act]:
    acts = []
    for m in _SETENV.finditer(masked):
        args = _call_args(text, m.end())
        if len(args) < 3:
            continue  # the process scope: gone when the process ends
        scope = re.sub(r'\s+', '', args[2]).lower().strip('\'"')
        if scope == 'process' or scope.endswith('::process'):
            continue
        name = args[0].strip().strip('\'"')
        acts.append(Act(3, 'shell', name or None, f'SetEnvironmentVariable {name}'))
    return acts


def _call_args(text: str, start: int) -> list[str]:
    """The comma-separated arguments of a call whose `(` ends just before `start`."""
    args: list[str] = []
    buf: list[str] = []
    depth, quote, k = 0, '', start
    while k < len(text):
        c = text[k]
        if quote:
            buf.append(c)
            if c == quote:
                quote = ''
        elif c in '\'"':
            quote = c
            buf.append(c)
        elif c in '([{':
            depth += 1
            buf.append(c)
        elif c in ')]}':
            if depth == 0 and c == ')':
                args.append(''.join(buf).strip())
                return args
            depth -= 1
            buf.append(c)
        elif c == ',' and depth == 0:
            args.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(c)
        k += 1
    args.append(''.join(buf).strip())
    return args


def shell_acts(command: str, shell: str, cwd: str | None, depth: int = 0) -> list[Act]:
    """Every owner-only act a Bash ('bash') or PowerShell ('powershell') command performs."""
    if depth > MAX_DEPTH or not isinstance(command, str):
        return []
    result = scan(command, shell)
    acts: list[Act] = list(_setenv_acts(command, result.masked))
    for tokens in result.commands:
        index = _program_index(tokens)
        if index is not None:
            name = program_name(tokens[index].value)
            args = _args(tokens, index)
            act = None
            if name == 'claude':
                act = _claude_act(args, command)
            elif name == 'setx':
                act = _setx_act(args)
            elif name == 'git':
                act = _git_act(args)
            if act is not None:
                acts.append(act)
            inner = _wrapper_inner(name, args)
            if inner is not None or name in _POSIX_SHELLS | _PS_SHELLS | {'cmd'}:
                acts.extend(_wrapper_acts(inner, args, cwd, depth))
                continue
        write = _shell_write(tokens, index, cwd)
        if write is not None:
            acts.append(write)
    for script, script_shell in result.scripts:
        acts.extend(shell_acts(script, script_shell, cwd, depth + 1))
    return _dedupe(acts)


def _wrapper_acts(inner, args, cwd, depth) -> list[Act]:
    found = shell_acts(inner[0], inner[1], cwd, depth + 1) if inner else []
    families = {a.family for a in found}
    for token in args:
        if not token.quoted:
            continue
        for family, pattern in _FAMILY_TOKENS:
            if family not in families and pattern.search(token.value):
                found.append(Act(family, 'shell', None, 'wrapped ' + FAMILY_NAMES[family]))
                families.add(family)
        if 1 not in families and _GOVERNED_NAME.search(token.value):
            name = _GOVERNED_NAME.search(token.value).group(0)
            found.append(Act(1, 'shell-write', name, f'wrapped shell write naming {name}'))
            families.add(1)
    return found


def _dedupe(acts: list[Act]) -> list[Act]:
    seen, out = set(), []
    for act in acts:
        key = (act.family, act.arm, act.key)
        if key not in seen:
            seen.add(key)
            out.append(act)
    return out


def tool_acts(tool_name: str, tool_input: dict, cwd: str | None) -> list[Act]:
    """The owner-only acts one tool call performs."""
    if tool_name in ('Bash', 'PowerShell'):
        command = tool_input.get('command')
        shell = 'bash' if tool_name == 'Bash' else 'powershell'
        return shell_acts(command, shell, cwd) if isinstance(command, str) else []
    if tool_name in ('Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
        path = tool_input.get('notebook_path' if tool_name == 'NotebookEdit' else 'file_path')
        name = governed_target(path, cwd) if isinstance(path, str) else None
        return [Act(1, 'edit', name, f'{tool_name} {name}')] if name else []
    return []


# ------------------------------------------------------------------ state


def mode() -> str:
    """on | observe | off. Unset is on: `== '0'` turns it off, `== 'observe'` logs only."""
    value = os.environ.get(GATE, 'on').strip().lower()
    if value == '0':
        return 'off'
    if value == 'observe':
        return 'observe'
    return 'on'


def _state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'owner-acts-gate'


def _safe_session(session_id: object) -> str:
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(session_id or 'unknown'))[:80]


def prompt_path(session_id: object) -> Path:
    return _state_dir() / 'prompts' / f'{_safe_session(session_id)}.json'


def record_prompt(session_id: object, prompt: str) -> None:
    path = prompt_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f'.{os.getpid()}.tmp')
    record = {
        'session_id': str(session_id),
        'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'prompt': prompt[:MAX_PROMPT_CHARS],
    }
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def recorded_prompt(session_id: object) -> str | None:
    try:
        data = json.loads(prompt_path(session_id).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    prompt = data.get('prompt') if isinstance(data, dict) else None
    return prompt if isinstance(prompt, str) else None


def append_log(entry: dict) -> None:
    with contextlib.suppress(Exception):
        path = _state_dir() / 'log.ndjson'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')


# ------------------------------------------------------------------ handlers


def handle_prompt_submit(payload: dict) -> None:
    if mode() == 'off':
        return
    session_id = payload.get('session_id')
    prompt = payload.get('prompt')
    if session_id and isinstance(prompt, str) and is_owner_typed(prompt):
        record_prompt(session_id, prompt)


def deny_reason(denied: list[Act]) -> str:
    families = sorted({a.family for a in denied})
    acts = '; '.join(a.summary for a in denied)
    lines = [
        f'Owner-acts gate: denied ({acts}). This is '
        + ' and '.join(FAMILY_NAMES[f] for f in families)
        + ", an act only the owner authorizes, and no sentence of the owner's latest "
        'prompt names it with an act verb. A general go-ahead does not cover it.',
        'Do not retry it or route around it (another tool, a wrapper, a script). Put it to '
        'the owner in your final block, framed: what the act is and why, the exact command '
        'or edit, and its side effects: ' + '; '.join(SIDE_EFFECTS[f] for f in families) + '.',
        'The owner authorizes it with a sentence naming the object and the act, for example '
        + ' or '.join(EXAMPLES[f] for f in families)
        + '.',
    ]
    return ' '.join(lines)


def handle_pre_tool_use(payload: dict) -> dict | None:
    current = mode()
    if current == 'off':
        return None
    tool_name = payload.get('tool_name')
    tool_input = payload.get('tool_input')
    if tool_name not in TOOLS or not isinstance(tool_input, dict):
        return None
    cwd = payload.get('cwd') if isinstance(payload.get('cwd'), str) else None
    acts = tool_acts(tool_name, tool_input, cwd)
    if not acts:
        return None
    session_id = payload.get('session_id')
    prompt = recorded_prompt(session_id) if session_id else None
    denied: list[Act] = []
    now = time.strftime('%Y-%m-%dT%H:%M:%S')
    for act in acts:
        sentence = authorizing_sentence(prompt, act)
        would = 'allow' if sentence else 'deny'
        if would == 'allow':
            decision = 'allow'
        elif act.arm == 'shell-write' or current == 'observe':
            decision = 'observe'
        else:
            decision = 'deny'
            denied.append(act)
        append_log(
            {
                'ts': now,
                'session_id': str(session_id or ''),
                'tool': tool_name,
                'family': act.family,
                'arm': act.arm,
                'key': act.key,
                'decision': decision,
                'would': would,
                'mode': current,
                'sentence': sentence,
                'recorded_prompt': prompt is not None,
            }
        )
    if not denied:
        return None
    return {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': deny_reason(denied),
        }
    }


def emit_json(output: dict) -> None:
    """Write `output` to stdout as UTF-8 JSON, whatever the console codepage."""
    stream = sys.stdout
    reconfigure = getattr(stream, 'reconfigure', None)
    if reconfigure is not None:
        reconfigure(encoding='utf-8')
    stream.write(json.dumps(output, ensure_ascii=False) + '\n')
    stream.flush()


def _load_stdin_json() -> dict | None:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8-sig')
        data = json.loads(raw) if raw.strip() else None
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        payload = _load_stdin_json()
        if payload is None or not GOVERNED_FILES:
            return 0
        event = payload.get('hook_event_name')
        if '--prompt-submit' in argv or (not argv and event == 'UserPromptSubmit'):
            handle_prompt_submit(payload)
            return 0
        if '--pre-tool-use' in argv or (not argv and event == 'PreToolUse'):
            output = handle_pre_tool_use(payload)
            if output is not None:
                emit_json(output)
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

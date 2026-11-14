"""Checker of the owner-acts rule pack: session-workflow's owner-acts gate, called by the kit.

The checker holds no rule of its own. When the file is loaded it finds
`plugins/session-workflow/hooks/` from its own location in the repository,
turns bytecode writing off, puts that folder on `sys.path` and imports the
core, `owner_acts_gate`, and its prompt rule, `prompt_kind`. It then requires
the names it uses and raises when one is missing, or when the core's
`GOVERNED_FILES` is empty (the core's fallback for a partial install, under
which no governed path resolves), so a moved or incomplete core fails the
build and the launch. One of those names, `_dedupe`, is private to the core.

`record(note, facts)` keeps the owner's latest prompt, `{"prompt": TEXT}`: a
prompt note whose origin is neither `child` nor `synthetic` and whose text the
core's lexical rule takes as typed by the owner, while the core's switch is
not off. TEXT is the note's text cut to the core's `MAX_PROMPT_CHARS`, then to
its longest prefix whose facts file fits in 65536 bytes.

`check(act, observation, facts)` finds the acts with the core: a command read
in both dialects, `bash` first, acts the core only observes left out; a write
by its paths under the core's governed home. It answers `match` when the
recorded prompt names none of some act, with the core's first sentence as the
detail; `cannot-tell` when the act was not observed or the facts cannot be
read; `no-match` otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

CORE_FOLDER = Path(__file__).resolve().parents[3] / 'plugins' / 'session-workflow' / 'hooks'
if str(CORE_FOLDER) not in sys.path:
    sys.path.insert(0, str(CORE_FOLDER))

import owner_acts_gate  # noqa: E402 - the core's folder is on sys.path only from here
import prompt_kind  # noqa: E402

USED = (
    'shell_acts',
    'governed_target',
    'authorizing_sentence',
    'deny_reason',
    'Act',
    'mode',
    'MAX_PROMPT_CHARS',
    '_dedupe',
)
_MISSING = [name for name in USED if not hasattr(owner_acts_gate, name)]
if not hasattr(prompt_kind, 'is_owner_typed'):
    _MISSING.append('prompt_kind.is_owner_typed')
if _MISSING:
    raise ImportError(f'owner_acts_gate lacks {", ".join(_MISSING)}')
if not getattr(owner_acts_gate, 'GOVERNED_FILES', ()):
    raise ImportError('owner_acts_gate.GOVERNED_FILES is empty: the core is installed in part')

READINGS = ('bash', 'powershell')
FACTS_MAX_BYTES = 65536
FIRST_SENTENCE_END = ' This is '
UNCHANGED = {'result': 'unchanged'}
NO_MATCH = {'result': 'no-match'}
CANNOT_TELL = {'result': 'cannot-tell'}


def facts_file_size(text: str) -> int:
    """The bytes of the facts file `{"prompt": text}`, as the kit writes it."""
    document = {'kit_facts': 1, 'facts': {'prompt': text}}
    return len((json.dumps(document, ensure_ascii=True, indent=2) + '\n').encode('ascii'))


def longest_fitting_prefix(text: str) -> str:
    """The longest prefix of `text` whose facts file is at most 65536 bytes."""
    if facts_file_size(text) <= FACTS_MAX_BYTES:
        return text
    low, high = 0, len(text)  # the prefix of length `low` fits, the one of length `high` does not
    while high - low > 1:
        middle = (low + high) // 2
        if facts_file_size(text[:middle]) <= FACTS_MAX_BYTES:
            low = middle
        else:
            high = middle
    return text[:low]


def record(note: dict, facts: dict) -> dict:
    """Keep the owner's latest prompt, as the core's UserPromptSubmit arm does."""
    if owner_acts_gate.mode() == 'off':
        return UNCHANGED
    body = note.get('note')
    if not isinstance(body, dict) or body.get('kind') != 'prompt':
        return UNCHANGED
    if note.get('origin') in ('child', 'synthetic'):
        return UNCHANGED
    text = body.get('text')
    if not isinstance(text, str) or not prompt_kind.is_owner_typed(text):
        return UNCHANGED
    kept = longest_fitting_prefix(text[: owner_acts_gate.MAX_PROMPT_CHARS])
    if isinstance(facts, dict) and facts.get('prompt') == kept:
        return UNCHANGED
    return {'facts': {'prompt': kept}}


def _cwd(act: dict) -> str | None:
    cwd = act.get('cwd')
    return cwd if isinstance(cwd, str) and cwd else None


def _shell_acts(command: object, cwd: str | None) -> list:
    """The acts of both readings, deduplicated, without the arm the core never denies."""
    if not isinstance(command, str):
        return []
    found = []
    for shell in READINGS:
        found += owner_acts_gate.shell_acts(command, shell, cwd)
    return [a for a in owner_acts_gate._dedupe(found) if a.arm != 'shell-write']


def _write_acts(paths: object, cwd: str | None) -> list:
    """One act per distinct governed file name a path of the write resolves to."""
    names: list[str] = []
    for path in paths if isinstance(paths, list) else []:
        name = owner_acts_gate.governed_target(path, cwd)
        if name and name not in names:
            names.append(name)
    return [owner_acts_gate.Act(1, 'edit', name, 'write ' + name) for name in names]


def check(act: dict, observation: dict, facts: dict | None) -> dict:
    """`match`, `no-match` or `cannot-tell` for one act, from the core's rule and the facts."""
    if owner_acts_gate.mode() in ('off', 'observe'):
        return NO_MATCH
    kind = act.get('kind')
    if kind == 'shell':
        if observation.get('command') != 'observed':
            return CANNOT_TELL
        acts = _shell_acts(act.get('command'), _cwd(act))
    elif kind == 'file_write':
        if observation.get('paths') != 'observed':
            return CANNOT_TELL
        acts = _write_acts(act.get('paths'), _cwd(act))
    else:
        acts = []
    if not acts:
        return NO_MATCH
    if not isinstance(facts, dict):
        return CANNOT_TELL
    if 'prompt' in facts and not isinstance(facts['prompt'], str):
        return CANNOT_TELL
    prompt = facts.get('prompt')
    denied = [a for a in acts if owner_acts_gate.authorizing_sentence(prompt, a) is None]
    if not denied:
        return NO_MATCH
    text = owner_acts_gate.deny_reason(denied)
    return {'result': 'match', 'detail': text.split(FIRST_SENTENCE_END, 1)[0]}

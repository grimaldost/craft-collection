#!/usr/bin/env python3
"""Checks of the owner-acts rule pack: its checker decides as session-workflow's owner-acts gate does.

Contract under test:
- parity with the live core over the core's own tests: every `test_*`
  function of the core's test module runs with its `Sandbox.run` replaced by
  a recorder that forces the module's own in-process path (`_run_inproc`) and
  returns the real result; each recorded call is replayed through the pack
  inside that replaced `run`, under the environment `Sandbox.env()` gives,
  with the pack's facts kept per `Sandbox` instance and session id and
  starting at `{}`. Every core deny is a pack `match`, and every pack `match`
  the core did not deny is a row of `LISTED_ROWS`;
- the pack's own corpus: each family in both dialects, a shell write to a
  governed file, long prompts cut to the longest prefix whose facts file
  fits, prompts the rule does not accept, `None` and malformed facts,
  unobserved acts and the switch values;
- the rule's reason is the stated text, its last four sentences are the
  core's, and a match's detail is the first sentence of the core's deny text;
- two prompts as opencode delivers them, in literal double quotes;
- a built policy records a prompt through `kit note` and judges a write
  through `kit judge`, and no bytecode cache appears under `plugins/`;
- with `governed_home.py` removed, or a used name missing, the checker does
  not execute and the build exits 64.

Every case points `SESSION_WORKFLOW_GOVERNED_HOME` at a folder of its own and
clears `CLAUDE_CONFIG_DIR`, `SESSION_WORKFLOW_OWNER_ACTS_GATE` and
`SESSION_WORKFLOW_OWNER_ACTS_GATE_DIR` unless the case sets them. The core's
family 2 and 3 commands are only ever passed as strings to `check`; the only
program started is this interpreter.

Stdlib-runnable: `python test_owner_acts_rule.py`.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402 - bytecode writing is off before any other import
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import tomllib  # noqa: E402

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]
ROOT = HERE.parents[2]
SRC = KIT / 'src'
HOOKS = ROOT / 'plugins' / 'session-workflow' / 'hooks'
for _folder in (SRC, HOOKS):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import owner_acts_gate  # noqa: E402
import prompt_kind  # noqa: E402
import test_owner_acts_gate  # noqa: E402
from harness_kit import checkers, notes, packs, state  # noqa: E402
from harness_kit.policy import load_policy  # noqa: E402

GATE = 'SESSION_WORKFLOW_OWNER_ACTS_GATE'
STATE_DIR = 'SESSION_WORKFLOW_OWNER_ACTS_GATE_DIR'
HOME_ENV = 'SESSION_WORKFLOW_GOVERNED_HOME'
CONFIG_ENV = 'CLAUDE_CONFIG_DIR'
DATA = 'CLAUDE_PLUGIN_DATA'
RULE_ID = 'owner-acts-named-by-owner'
CHECKER_ID = 'owner-acts-check'
SHELL_TOOLS = {'Bash': 'bash', 'PowerShell': 'powershell'}
WRITE_TOOLS = {'Write': 'file_path', 'Edit': 'file_path', 'MultiEdit': 'file_path'}
WRITE_TOOLS['NotebookEdit'] = 'notebook_path'
TEXT_CAP = 20000
FACTS_CAP = 65536
REASON = (
    "This is an act only the owner authorizes, and no sentence of the owner's latest prompt "
    'names it with an act verb. A general go-ahead does not cover it. Do not retry it or route '
    'around it (another tool, a wrapper, a script). Put it to the owner in your final block, '
    'framed: what the act is and why, the exact command or edit, and its side effects. The '
    'owner authorizes it with a sentence naming the object and the act.'
)
SCRATCH = tempfile.TemporaryDirectory()

# The core allows these and the pack matches them: the second dialect's reading finds the act.
LISTED_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "cat > fix.ps1 <<'EOF'\nclaude plugin update x@y\nsetx FOO 1\n"
        "[Environment]::SetEnvironmentVariable('BAR', '1', 'User')\n"
        'git config --global user.name "A B"\nEOF',
        'powershell',
        'A Bash heredoc writes a script to a file; the PowerShell reading has no heredoc and reads'
        ' the body lines as commands, each opening with an owner act.',
    ),
)


# ------------------------------------------------------------------ the pack


def _policy(pack: Path, where: Path):
    """A policy built from a version 1 base and `pack`, written under `where`."""
    where.mkdir(parents=True, exist_ok=True)
    base = where / 'base.toml'
    base.write_bytes(b'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n')
    out, _ = packs.build(base, [pack], where / 'policy.toml')
    return load_policy(out)


POLICY = _policy(HERE, Path(SCRATCH.name) / 'built')
CHECKER = next(c for c in POLICY.checkers if c.id == CHECKER_ID)
MODULE = checkers.execute(CHECKER)
CHECK = MODULE.check
RECORD = MODULE.record


@contextlib.contextmanager
def _case(mode: str | None = None):
    """One case's environment: a governed home of its own, the core's variables cleared.

    `mode` sets the core's switch. The plugin data folder is an empty folder of
    the case: the pack must write nothing there. Yields the governed home.
    """
    names = (GATE, STATE_DIR, HOME_ENV, CONFIG_ENV, DATA)
    saved = {name: os.environ.get(name) for name in names}
    folder = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    home, data = folder / 'governed-home', folder / 'plugin-data'
    home.mkdir()
    data.mkdir()
    for name in (GATE, STATE_DIR, CONFIG_ENV):
        os.environ.pop(name, None)
    if mode is not None:
        os.environ[GATE] = mode
    os.environ[HOME_ENV] = str(home)
    os.environ[DATA] = str(data)
    try:
        yield home
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    assert list(data.iterdir()) == [], list(data.iterdir())


# ------------------------------------------------- events and notes, built here


def _observation(command: str = 'not_applicable', paths: str = 'not_applicable') -> dict:
    """The observation the first slice's Claude Code shell gives."""
    return {
        'session': 'observed',
        'parent': 'unavailable',
        'root': 'unavailable',
        'origin': 'unavailable',
        'command': command,
        'paths': paths,
    }


def _shell(command: object, cwd: str = '', observed: str = 'observed') -> tuple[dict, dict]:
    act = {'kind': 'shell', 'command': command, 'argv': None, 'paths': [], 'cwd': cwd}
    act['payload_sha256'] = 'a' * 64
    return act, _observation(command=observed)


def _write(paths: list[str], cwd: str = '', observed: str = 'observed') -> tuple[dict, dict]:
    act = {'kind': 'file_write', 'command': None, 'argv': None, 'paths': paths, 'cwd': cwd}
    act['payload_sha256'] = 'b' * 64
    return act, _observation(paths=observed)


def event_from_payload(raw: bytes) -> dict:
    """The event the first slice's Claude Code shell builds from a PreToolUse payload."""
    payload = json.loads(raw.decode('utf-8'))
    tool, cwd = payload['tool_name'], payload['cwd']
    given = payload.get('tool_input')
    given = given if isinstance(given, dict) else {}
    if tool in SHELL_TOOLS:
        command = given['command'] if isinstance(given.get('command'), str) else None
        act, observation = _shell(command, cwd)
    else:
        path = given.get(WRITE_TOOLS[tool])
        found = (
            [os.path.normpath(os.path.join(cwd, path))] if isinstance(path, str) and path else []
        )
        act, observation = _write(found, cwd)
    act['payload_sha256'] = hashlib.sha256(raw).hexdigest()
    return {
        'kit_event': 1,
        'run_id': None,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': payload['session_id'], 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': observation,
        'act': act,
    }


def prompt_note(text: str, origin: str = 'unknown', session: str = 's1') -> dict:
    """The prompt note the Claude Code note mode builds: the first 20000 code points."""
    observation = _observation()
    if origin != 'unknown':
        observation['origin'] = 'observed'
    return {
        'kit_note': 1,
        'run_id': None,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': session, 'parent_id': None, 'root_id': None},
        'origin': origin,
        'observation': observation,
        'note': {'kind': 'prompt', 'text': text[:TEXT_CAP], 'truncated': len(text) > TEXT_CAP},
    }


def opencode_prompt_note(delivered: str, parent: str | None = None) -> dict:
    """The prompt note the opencode note mode builds: one enclosing pair of quotes removed."""
    text = delivered
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    session = 'ses_child' if parent else 'ses_root'
    return {
        'kit_note': 1,
        'run_id': None,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': {'id': session, 'parent_id': parent, 'root_id': parent or session},
        'origin': 'child' if parent else 'unknown',
        'observation': {
            **dict.fromkeys(('session', 'parent', 'root', 'origin'), 'observed'),
            **dict.fromkeys(('command', 'paths'), 'not_applicable'),
        },
        'note': {'kind': 'prompt', 'text': text[:TEXT_CAP], 'truncated': len(text) > TEXT_CAP},
    }


def _record(note: dict, facts: dict) -> dict:
    """`record` as `kit note` calls it: a sound note, without `run_id` and `session`."""
    notes.check_note(note)
    got = RECORD(notes.record_argument(note), copy.deepcopy(facts))
    result, _ = checkers.read_record_return(got)
    assert result in ('facts', 'unchanged'), got
    return got


def _check(pair: tuple[dict, dict], facts: object) -> dict:
    act, observation = pair
    got = CHECK(act, observation, copy.deepcopy(facts))
    assert checkers.read_return(got)[0] == got['result'], got
    return got


def _facts_size(prompt: str) -> int:
    return len(state.json_bytes({'kit_facts': 1, 'facts': {'prompt': prompt}}))


# ------------------------------------------------- parity with the core's tests


def _core_decision(proc: object) -> str:
    if not proc.stdout:
        return 'allow'
    return json.loads(proc.stdout.decode('utf-8'))['hookSpecificOutput']['permissionDecision']


def classify(payload: object) -> str | None:
    """`skip` (skipped and counted), `prompt` or `pre` (replayed), or None (neither)."""
    if not isinstance(payload, dict):
        return 'skip'
    event = payload.get('hook_event_name')
    if not isinstance(payload.get('session_id'), str) or not isinstance(event, str):
        return 'skip'
    fields = (payload.get('tool_name'), payload.get('cwd'))
    if event in ('PreToolUse', 'PostToolUse') and not all(isinstance(f, str) for f in fields):
        return 'skip'
    if event == 'UserPromptSubmit':
        return 'prompt' if isinstance(payload.get('prompt'), str) else None
    if event == 'PreToolUse' and payload['tool_name'] in {**SHELL_TOOLS, **WRITE_TOOLS}:
        return 'pre'
    return None


class _Replay:
    """The calls the core's tests make, each run through the core and replayed through the pack."""

    def __init__(self) -> None:
        self.recorded = 0
        self.skipped = 0
        self.facts: dict[tuple[int, str], dict] = {}
        self.pre: list[tuple[object, str, str, str]] = []  # command, tool, core, pack

    def replay(self, box: object, raw: bytes, proc: object) -> None:
        try:
            payload = json.loads(raw.decode('utf-8'))
        except ValueError:
            payload = None
        kind = classify(payload)
        if kind == 'skip':
            self.skipped += 1
            return
        if kind is None:
            return
        key = (id(box), payload['session_id'])
        facts = self.facts.setdefault(key, {})
        if kind == 'prompt':
            got = _record(prompt_note(payload['prompt'], session=payload['session_id']), facts)
            if 'facts' in got:
                self.facts[key] = got['facts']
            return
        event = event_from_payload(raw)
        got = CHECK(event['act'], event['observation'], copy.deepcopy(facts))
        assert checkers.read_return(got)[0] == got['result'], got
        tool = payload['tool_name']
        self.pre.append((event['act']['command'], tool, _core_decision(proc), got['result']))


@contextlib.contextmanager
def _environment(env: dict):
    """This process's environment replaced by `env` for the block, then restored."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _replay_core_tests() -> _Replay:
    replay = _Replay()
    real = test_owner_acts_gate.Sandbox.run
    boxes: list[object] = []  # kept alive so that no two boxes share an id

    def run(box, payload, flag):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
        boxes.append(box)
        replay.recorded += 1
        with _environment(box.env()):
            proc = box._run_inproc(raw, [flag] if flag else [])
            replay.replay(box, raw, proc)
        return proc

    test_owner_acts_gate.Sandbox.run = run
    try:
        for name, fn in sorted(vars(test_owner_acts_gate).items()):
            if name.startswith('test_') and callable(fn):
                fn()
    finally:
        test_owner_acts_gate.Sandbox.run = real
    return replay


STATS: dict[str, int] = {}


def test_parity_with_the_core_over_its_own_tests():
    with _case():
        replay = _replay_core_tests()
    STATS.update(recorded=replay.recorded, skipped=replay.skipped)
    assert replay.pre, 'the core tests made no PreToolUse call'
    listed = {command for command, _, _ in LISTED_ROWS}
    unlisted = []
    for command, tool, core, pack in replay.pre:
        assert core in ('allow', 'deny'), (command, core)
        if core == 'deny':
            assert pack == 'match', ('a core deny the pack allows', command, tool, pack)
        elif pack == 'match' and command not in listed:
            unlisted.append((command, tool))
    assert unlisted == [], unlisted
    assert any(core == 'allow' for _, _, core, _ in replay.pre), replay.pre
    # Six unreadable payloads, one without session_id, one PreToolUse without cwd.
    assert replay.skipped == 8, replay.skipped


def test_listed_rows_have_their_shape_and_the_second_dialect_finds_the_act():
    assert isinstance(LISTED_ROWS, tuple)
    for row in LISTED_ROWS:
        assert isinstance(row, tuple) and len(row) == 3, row
        command, dialect, reason = row
        assert isinstance(command, str) and dialect in ('bash', 'powershell'), row
        assert isinstance(reason, str) and reason.strip() and reason.isascii(), row
        acts = owner_acts_gate.shell_acts(command, dialect, None)
        assert [a for a in acts if a.arm != 'shell-write'], row


def test_the_classification_of_recorded_calls():
    assert classify(None) == 'skip' and classify([1]) == 'skip'
    assert classify({'hook_event_name': 'PreToolUse', 'tool_name': 'Bash'}) == 'skip'
    assert classify({'session_id': 's', 'hook_event_name': 'PreToolUse', 'tool_name': 'Bash'}) == (
        'skip'
    )
    assert classify({'session_id': 's', 'hook_event_name': 'PostToolUse', 'cwd': '/'}) == 'skip'
    assert classify({'session_id': 's', 'hook_event_name': 'UserPromptSubmit'}) is None
    assert classify({'session_id': 's', 'hook_event_name': 'UserPromptSubmit', 'prompt': 'x'}) == (
        'prompt'
    )
    pre = {'session_id': 's', 'hook_event_name': 'PreToolUse', 'cwd': '/'}
    assert classify({**pre, 'tool_name': 'Edit'}) == 'pre'
    assert classify({**pre, 'tool_name': 'PowerShell'}) == 'pre'
    assert classify({**pre, 'tool_name': 'Read'}) is None
    post = {**pre, 'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'}
    assert classify(post) is None
    assert classify({'session_id': 's', 'hook_event_name': 'Stop'}) is None


# ------------------------------------------------------------- own corpus

GO_ON = 'pode seguir com as recomendações'
FAMILY_COMMANDS = (
    # (command, dialect of the tool, summary of the act, a prompt that names it)
    ('claude plugin update x@y', 'bash', 'claude plugin update x@y', 'pode atualizar o x@y'),
    ('claude.exe plugin install "a@b"', 'powershell', 'claude plugin install a@b', 'install a@b'),
    ('setx FOO 1', 'bash', 'setx FOO', 'defina a variavel de ambiente FOO'),
    (
        "[Environment]::SetEnvironmentVariable('FOO', '1', 'User')",
        'powershell',
        'SetEnvironmentVariable FOO',
        'set the env var FOO',
    ),
    (
        'git config --global user.name "A B"',
        'bash',
        'git config --global user.name',
        'pode alterar o git config global',
    ),
    (
        "git config --global core.autocrlf 'false'",
        'powershell',
        'git config --global core.autocrlf',
        'change the git config',
    ),
)


def test_each_shell_family_in_both_dialects_matches_until_a_sentence_names_it():
    with _case():
        for command, _dialect, summary, sentence in FAMILY_COMMANDS:
            for shell in ('bash', 'powershell'):
                assert owner_acts_gate.shell_acts(command, shell, None), (command, shell)
            got = _check(_shell(command), {})
            assert got == {
                'result': 'match',
                'detail': f'Owner-acts gate: denied ({summary}).',
            }, (command, got)
            assert _check(_shell(command), {'prompt': GO_ON})['result'] == 'match', command
            assert _check(_shell(command), {'prompt': sentence}) == {'result': 'no-match'}, command


def test_a_write_to_each_governed_file_matches_until_a_sentence_names_it():
    with _case() as home:
        for name in ('CLAUDE.md', 'settings.json', 'settings.local.json'):
            pair = _write([str(home / name)])
            assert _check(pair, {}) == {
                'result': 'match',
                'detail': f'Owner-acts gate: denied (write {name}).',
            }, name
            assert _check(pair, {'prompt': f'pode editar o {name}'}) == {'result': 'no-match'}
        relative = _write(['CLAUDE.md'], cwd=str(home))
        assert _check(relative, {})['result'] == 'match'
        twice = _write([str(home / 'CLAUDE.md'), str(home / 'CLAUDE.md')])
        assert _check(twice, {})['detail'] == 'Owner-acts gate: denied (write CLAUDE.md).'


def test_an_ordinary_file_or_command_is_no_match():
    with _case() as home:
        other = home.parent / 'repo'
        for pair in (
            _write([str(other / 'CLAUDE.md')]),
            _write([str(home / 'notes.md')]),
            _shell('git status'),
            _shell('git config --global --get user.name'),
            _shell('claude plugin marketplace list'),
            _shell('git commit -m "docs: explain git config --global"'),
        ):
            assert _check(pair, {}) == {'result': 'no-match'}, pair


def test_a_shell_write_to_a_governed_file_is_no_match():
    with _case() as home:
        target = (home / 'CLAUDE.md').as_posix()
        for command in (
            f'echo "- a rule" >> "{target}"',
            f"Set-Content -Path '{target}' -Value 'x'",
            f'cat notes.md > "{target}"',
        ):
            arms = {
                a.arm
                for s in ('bash', 'powershell')
                for a in owner_acts_gate.shell_acts(command, s, None)
            }
            assert 'shell-write' in arms, command
            assert _check(_shell(command), {}) == {'result': 'no-match'}, command


def test_none_facts_cannot_tell_for_an_act_and_no_match_without_one():
    with _case() as home:
        assert _check(_shell('setx FOO 1'), None) == {'result': 'cannot-tell'}
        assert _check(_write([str(home / 'CLAUDE.md')]), None) == {'result': 'cannot-tell'}
        assert _check(_shell('git status'), None) == {'result': 'no-match'}
        assert _check(_write([str(home / 'notes.md')]), None) == {'result': 'no-match'}


def test_malformed_facts_cannot_tell_and_facts_without_a_prompt_match():
    with _case():
        for facts in ([], 'x', 1, {'prompt': 1}, {'prompt': None}, {'prompt': ['a']}):
            assert _check(_shell('setx FOO 1'), facts) == {'result': 'cannot-tell'}, facts
        assert _check(_shell('setx FOO 1'), {'other': 1})['result'] == 'match'


def test_unobserved_acts_cannot_tell():
    with _case() as home:
        for observed in ('unavailable', 'not_applicable'):
            got = _check(_shell('setx FOO 1', observed=observed), {})
            assert got == {'result': 'cannot-tell'}, observed
            got = _check(_write([str(home / 'CLAUDE.md')], observed=observed), {})
            assert got == {'result': 'cannot-tell'}, observed


def test_an_act_of_another_kind_is_no_match():
    with _case():
        act, observation = _shell('setx FOO 1')
        act['kind'] = 'other'
        assert _check((act, observation), {}) == {'result': 'no-match'}


def test_only_the_denied_acts_are_named():
    with _case() as home:
        command = 'claude plugin update x@y && setx FOO 1 && git config --global user.name "A B"'
        got = _check(_shell(command), {})
        assert got['detail'] == (
            'Owner-acts gate: denied (claude plugin update x@y; setx FOO; '
            'git config --global user.name).'
        ), got
        got = _check(_shell(command), {'prompt': 'pode definir a variavel de ambiente FOO'})
        assert got['detail'] == (
            'Owner-acts gate: denied (claude plugin update x@y; git config --global user.name).'
        ), got
        pair = _write([str(home / 'CLAUDE.md'), str(home / 'settings.json')])
        got = _check(pair, {'prompt': 'pode editar o CLAUDE.md'})
        assert got['detail'] == 'Owner-acts gate: denied (write settings.json).', got


def test_an_act_either_reading_finds_counts():
    # The bash reading blanks the heredoc body; the PowerShell reading reads its lines.
    script = "cat > fix.ps1 <<'EOF'\nsetx FOO 1\nEOF"
    assert owner_acts_gate.shell_acts(script, 'bash', None) == []
    assert owner_acts_gate.shell_acts(script, 'powershell', None)
    with _case():
        assert _check(_shell(script), {})['result'] == 'match'


def _longest_fitting(text: str) -> str:
    """The longest prefix of the first 20000 code points whose facts file fits, char by char."""
    cut = text[:TEXT_CAP]
    size = _facts_size('')
    for k, char in enumerate(cut):
        size += len(json.dumps(char, ensure_ascii=True)) - 2  # the escaped form, quotes left out
        if size > FACTS_CAP:
            return cut[:k]
    return cut


def test_a_long_prompt_is_recorded_as_its_longest_prefix_that_fits():
    with _case():
        for char in ('é', '\U0001f600', '"', '\ud800'):
            text = char * TEXT_CAP
            got = _record(prompt_note(text), {})
            prompt = got['facts']['prompt']
            assert set(got) == {'facts'} and set(got['facts']) == {'prompt'}, got
            assert text.startswith(prompt), char
            assert _facts_size(prompt) <= FACTS_CAP, (char, _facts_size(prompt))
            assert prompt == _longest_fitting(text), (char, len(prompt))
            if len(prompt) < len(text):
                assert _facts_size(text[: len(prompt) + 1]) > FACTS_CAP, char
        short = 'pode editar o CLAUDE.md'
        assert _record(prompt_note(short), {}) == {'facts': {'prompt': short}}
        fits = 'a' * TEXT_CAP
        assert _record(prompt_note(fits), {}) == {'facts': {'prompt': fits}}


def test_a_recorded_prompt_replaces_the_facts_and_the_same_prompt_is_unchanged():
    with _case():
        got = _record(prompt_note('pode editar o CLAUDE.md'), {'prompt': GO_ON, 'other': 1})
        assert got == {'facts': {'prompt': 'pode editar o CLAUDE.md'}}, got
        same = {'prompt': 'pode editar o CLAUDE.md'}
        assert _record(prompt_note('pode editar o CLAUDE.md'), same) == {'result': 'unchanged'}


def test_prompts_the_rule_does_not_accept_leave_the_facts_unchanged():
    recorded = {'prompt': GO_ON}
    with _case():
        for note in (
            prompt_note('pode editar o CLAUDE.md', origin='child'),
            prompt_note('pode editar o CLAUDE.md', origin='synthetic'),
            opencode_prompt_note('"pode editar o CLAUDE.md"', parent='ses_root'),
            prompt_note(test_owner_acts_gate.TASK_NOTIFICATION),
            prompt_note(test_owner_acts_gate.HAND_BACK),
        ):
            assert _record(note, recorded) == {'result': 'unchanged'}, note['note']['text'][:40]
        assert not prompt_kind.is_owner_typed(test_owner_acts_gate.TASK_NOTIFICATION)
        assert not prompt_kind.is_owner_typed(test_owner_acts_gate.HAND_BACK)
        outcome = prompt_note('x')
        outcome['observation']['command'] = 'observed'
        act, _ = _shell('echo pode editar o CLAUDE.md')
        outcome['note'] = {
            'kind': 'outcome',
            'act': act,
            'status': 'completed',
            'output': 'pode editar o CLAUDE.md',
            'truncated': False,
        }
        assert _record(outcome, recorded) == {'result': 'unchanged'}


def test_the_switches():
    for mode in ('0', 'observe'):
        with _case(mode) as home:
            assert _check(_shell('setx FOO 1'), {}) == {'result': 'no-match'}, mode
            assert _check(_write([str(home / 'CLAUDE.md')]), None) == {'result': 'no-match'}
    with _case('0'):
        assert _record(prompt_note('pode editar o CLAUDE.md'), {}) == {'result': 'unchanged'}
    with _case('observe'):
        got = _record(prompt_note('pode editar o CLAUDE.md'), {})
        assert got == {'facts': {'prompt': 'pode editar o CLAUDE.md'}}, got
    for mode in ('1', 'on'):
        with _case(mode):
            assert _check(_shell('setx FOO 1'), {})['result'] == 'match', mode


def test_the_governed_home_is_the_cores():
    with _case() as home:
        other = home.parent / 'config-home'
        os.environ.pop(HOME_ENV)
        os.environ[CONFIG_ENV] = str(other)
        assert _check(_write([str(other / 'CLAUDE.md')]), {})['result'] == 'match'
        assert _check(_write([str(home / 'CLAUDE.md')]), {}) == {'result': 'no-match'}


def test_two_prompts_as_opencode_delivers_them():
    with _case() as home:
        write = _write([str(home / 'CLAUDE.md')])
        allowed = opencode_prompt_note('"Run the scripted tool call. Pode editar o CLAUDE.md."')
        assert allowed['note']['text'] == 'Run the scripted tool call. Pode editar o CLAUDE.md.'
        facts = _record(allowed, {})['facts']
        assert _check(write, facts) == {'result': 'no-match'}
        question = opencode_prompt_note('"pode editar o CLAUDE.md?"')
        assert question['note']['text'] == 'pode editar o CLAUDE.md?'
        facts = _record(question, facts)['facts']
        assert facts == {'prompt': 'pode editar o CLAUDE.md?'}
        got = _check(write, facts)
        assert got == {'result': 'match', 'detail': 'Owner-acts gate: denied (write CLAUDE.md).'}


# --------------------------------------------------------- reason and detail


def test_the_pack_file_and_its_reason():
    data = tomllib.loads((HERE / 'pack.toml').read_text(encoding='utf-8'))
    (rule,) = data['rule']
    (checker,) = data['checker']
    assert 'prevention' not in data
    assert data['pack'] == 1 and data['name'] == 'owner-acts'
    assert checker == {
        'id': CHECKER_ID,
        'file': 'owner_acts_rule.py',
        'budget_ms': 250,
        'records': ['prompt'],
    }, checker
    assert rule == {
        'id': RULE_ID,
        'effect': 'deny',
        'governed': True,
        'kinds': ['shell', 'file_write'],
        'check': CHECKER_ID,
        'reason': REASON,
    }, rule
    (built,) = [r for r in POLICY.rules if r.id == RULE_ID]
    assert built.reason == REASON and built.governed is True
    assert CHECKER.records == ('prompt',)


def test_the_reasons_last_four_sentences_are_the_cores():
    sentences = [s.rstrip('.') for s in REASON.split('. ')]
    assert len(sentences) == 5, sentences
    acts = [
        owner_acts_gate.Act(1, 'edit', 'CLAUDE.md', 'write CLAUDE.md'),
        owner_acts_gate.Act(2, 'shell', 'x@y', 'claude plugin update x@y'),
        owner_acts_gate.Act(3, 'shell', 'FOO', 'setx FOO'),
        owner_acts_gate.Act(4, 'shell', 'user.name', 'git config --global user.name'),
    ]
    for denied in [[a] for a in acts] + [acts]:
        text = owner_acts_gate.deny_reason(denied)
        for sentence in sentences[1:]:
            assert sentence in text, (sentence, text)
        # The first sentence is the core's with the list of families left out.
        assert sentences[0].replace('This is ', '', 1) in text, text


def test_the_detail_is_the_first_sentence_of_the_cores_deny_text():
    with _case() as home:
        cases = [
            (_shell('claude plugin update x@y; setx BAR 2'), 'shell'),
            (_write([str(home / 'settings.json')]), 'write'),
        ]
        for pair, kind in cases:
            got = _check(pair, {'prompt': GO_ON})
            if kind == 'shell':
                acts = owner_acts_gate._dedupe(
                    owner_acts_gate.shell_acts(pair[0]['command'], 'bash', None)
                    + owner_acts_gate.shell_acts(pair[0]['command'], 'powershell', None)
                )
            else:
                acts = [owner_acts_gate.Act(1, 'edit', 'settings.json', 'write settings.json')]
            text = owner_acts_gate.deny_reason(acts)
            assert got['detail'] == text[: text.index(' This is ')], (got, text)
        (rule,) = [r for r in POLICY.rules if r.id == RULE_ID]
        assert checkers.reduce_detail(got['detail']) == got['detail']
        assert rule.reason == REASON


# ----------------------------------------------------- the pack in a process

CORE_FILES = ('owner_acts_gate.py', 'prompt_kind.py', 'governed_home.py')


def _copy_tree(dest: Path, leave_out: str | None = None) -> Path:
    """A scratch copy of the pack and of the core's files, `leave_out` not copied."""
    pack = dest / 'harness-kit' / 'packs' / 'owner-acts'
    pack.mkdir(parents=True)
    for name in ('pack.toml', 'owner_acts_rule.py'):
        shutil.copyfile(HERE / name, pack / name)
    hooks = dest / 'plugins' / 'session-workflow' / 'hooks'
    hooks.mkdir(parents=True)
    for name in CORE_FILES:
        if name != leave_out:
            shutil.copyfile(HOOKS / name, hooks / name)
    return pack


def _kit_env(tree: Path, home: Path, run_id: str | None = None) -> dict:
    """The environment of a child run in `tree`: bytecode writing left on, its cache under `tree`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    for name in (GATE, STATE_DIR, CONFIG_ENV, DATA, 'PYTHONDONTWRITEBYTECODE'):
        env.pop(name, None)
    env[HOME_ENV] = str(home)
    env['PYTHONPATH'] = str(SRC)
    env['PYTHONPYCACHEPREFIX'] = str(tree / 'pycache')
    env['KIT_STATE_ROOT'] = str(tree / 'state')
    if run_id is not None:
        env['KIT_RUN_ID'] = run_id
    return env


def _kit(tree: Path, *args: str, stdin: bytes = b'', run_id: str | None = None):
    return subprocess.run(  # noqa: S603 - this interpreter, fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=stdin,
        capture_output=True,
        env=_kit_env(tree, tree / 'governed-home', run_id),
        timeout=60,
    )


def _build(tree: Path, pack: Path) -> tuple[subprocess.CompletedProcess, Path]:
    base = tree / 'base.toml'
    base.write_bytes(b'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n')
    out = tree / 'policy.toml'
    args = ('policy', 'build', '--base', str(base), '--pack', str(pack), '--out', str(out))
    return _kit(tree, *args), out


def _plugin_bytecode(tree: Path) -> list[Path]:
    found = [
        p for p in (tree / 'plugins').rglob('*') if p.name == '__pycache__' or p.suffix == '.pyc'
    ]
    for name in CORE_FILES:
        found += list((tree / 'pycache').rglob(name.replace('.py', '*.pyc')))
    return found


def test_a_built_policy_records_a_long_prompt_then_judges_a_write_and_writes_no_cache():
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    home = tree / 'governed-home'
    home.mkdir()
    pack = _copy_tree(tree)
    built, policy = _build(tree, pack)
    assert built.returncode == 0, built
    run_id, _ = state.mint_run(tree / 'state', 'claude-code')

    def note(text: str) -> dict:
        given = prompt_note(text)
        given['run_id'] = run_id
        noted = _kit(
            tree, 'note', '--policy', str(policy), stdin=json.dumps(given).encode(), run_id=run_id
        )
        assert noted.returncode == 0, noted
        return json.loads(noted.stdout.decode('ascii'))

    def judge() -> dict:
        act, observation = _write([str(home / 'CLAUDE.md')], cwd=str(tree))
        event = {
            'kit_event': 1,
            'run_id': run_id,
            'harness': {'name': 'claude-code', 'version': '2.1.316'},
            'session': {'id': 's1', 'parent_id': None, 'root_id': None},
            'origin': 'unknown',
            'observation': observation,
            'act': act,
        }
        judged = _kit(
            tree, 'judge', '--policy', str(policy), stdin=json.dumps(event).encode(), run_id=run_id
        )
        assert judged.returncode == 0, judged
        lines = judged.stdout.decode('ascii').splitlines()
        assert len(lines) == 1, judged
        return json.loads(lines[0])

    long_text = 'é' * TEXT_CAP
    receipt = note(long_text)
    assert receipt['outcome'] == 'recorded', receipt
    assert receipt['recorders'] == [{'id': CHECKER_ID, 'result': 'facts'}], receipt
    (stored,) = (tree / 'state' / 'runs' / run_id / 'facts').rglob(f'{CHECKER_ID}.json')
    assert stored.stat().st_size <= FACTS_CAP, stored.stat().st_size
    assert json.loads(stored.read_bytes())['facts']['prompt'] == _longest_fitting(long_text)
    verdict = judge()
    assert (verdict['verdict'], verdict['governed'], verdict['rule']) == ('deny', True, RULE_ID)
    assert verdict['reason'] == f'Owner-acts gate: denied (write CLAUDE.md). {REASON}', verdict
    receipt = note('Run the scripted tool call. Pode editar o CLAUDE.md.')
    assert receipt['recorders'] == [{'id': CHECKER_ID, 'result': 'facts'}], receipt
    verdict = judge()
    assert verdict['verdict'] == 'allow' and verdict['rule'] is None, verdict
    assert any((tree / 'pycache').rglob('*.pyc')), 'the child wrote no bytecode at all'
    assert _plugin_bytecode(tree) == [], _plugin_bytecode(tree)


def _does_not_execute(tree: Path, pack: Path, needle: bytes) -> None:
    alone = subprocess.run(  # noqa: S603 - this interpreter, fixed argv, no shell
        [sys.executable, str(pack / 'owner_acts_rule.py')],
        capture_output=True,
        env=_kit_env(tree, tree / 'governed-home'),
        timeout=60,
    )
    assert alone.returncode != 0, alone
    assert needle in alone.stderr, alone
    built, out = _build(tree, pack)
    assert built.returncode == 64, built
    assert not out.exists()
    assert not packs.sidecar_path(out).exists()


def test_with_governed_home_removed_the_checker_does_not_execute_and_the_build_refuses():
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    pack = _copy_tree(tree, leave_out='governed_home.py')
    _does_not_execute(tree, pack, b'GOVERNED_FILES')


def test_with_a_used_name_missing_the_checker_does_not_execute():
    for name in ('_dedupe', 'MAX_PROMPT_CHARS'):
        tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
        pack = _copy_tree(tree)
        core = tree / 'plugins' / 'session-workflow' / 'hooks' / 'owner_acts_gate.py'
        text = core.read_text(encoding='utf-8')
        assert name in text
        core.write_text(text.replace(name, name + '_moved'), encoding='utf-8')
        _does_not_execute(tree, pack, name.encode('ascii'))
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    pack = _copy_tree(tree)
    kind = tree / 'plugins' / 'session-workflow' / 'hooks' / 'prompt_kind.py'
    text = kind.read_text(encoding='utf-8')
    kind.write_text(text + '\ndel is_owner_typed\n', encoding='utf-8')
    _does_not_execute(tree, pack, b'is_owner_typed')


if __name__ == '__main__':
    names = sorted(n for n, f in list(globals().items()) if n.startswith('test_') and callable(f))
    for name in names:
        globals()[name]()
    print(
        f'ok: owner-acts rule pack ({len(names)} checks) recorded={STATS["recorded"]} '
        f'skipped={STATS["skipped"]} listed={len(LISTED_ROWS)}'
    )

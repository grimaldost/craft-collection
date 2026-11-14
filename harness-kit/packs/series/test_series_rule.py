#!/usr/bin/env python3
"""Checks of the series rule pack: its checker decides as session-workflow's series guard does.

Contract under test:
- parity with the live core over the core's own tests: every `test_*`
  function of the core's test module runs with its `Box.run` replaced by a
  recorder that runs the core's `main` in this process, under the
  environment `Box.run` would give its subprocess, and returns the real
  result; each recorded call is replayed through the pack inside that
  replaced `run`, with the pack's facts kept per `Box` instance and session
  id and starting at `{}`. Every pack `match` is a core deny, and every core
  deny the pack does not match is a row of `LISTED_ROWS`;
- the pack's own corpus in both dialects: the first create, the second, the
  `KEEL_SERIES` forms, a create in another repository, the statuses that
  record nothing, a URL printed by a command with no create, a Bash heredoc;
- `None` facts, unobserved commands, malformed facts and the two switch values;
- the rule's reason is the core's text between the two marks, and a match's
  detail starts with `why` and composes with the reason into the core's text;
- a built policy records a pull request through `kit note` and then denies
  the second create through `kit judge`, and no bytecode cache appears under
  `plugins/`;
- with the core renamed or missing a name the checker uses, the checker does
  not execute and the build exits 64.

Every case sets or clears `SESSION_WORKFLOW_SERIES_GUARD` and
`CLAUDE_PLUGIN_DATA`. The core runs in this process only; the only program
started is this interpreter.

Stdlib-runnable: `python test_series_rule.py`.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402 - bytecode writing is off before any other import
import copy  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
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

import series_guard  # noqa: E402
import test_series_guard  # noqa: E402
from harness_kit import checkers, notes, packs, state  # noqa: E402
from harness_kit.policy import load_policy  # noqa: E402

GATE = 'SESSION_WORKFLOW_SERIES_GUARD'
DATA = 'CLAUDE_PLUGIN_DATA'
RULE_ID = 'series-second-pr-declared'
CHECKER_ID = 'series-check'
SHELL_TOOLS = {'Bash': 'bash', 'PowerShell': 'powershell'}
FIRST_MARK = "The owner's rule:"
LAST_MARK = '(for example `none:hotfix`).'
OUTPUT_CAP = 65536
SCRATCH = tempfile.TemporaryDirectory()

# The core denies these and the pack lets them pass: each difference is on the allow side.
LISTED_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        'Set-Location ..\\or; gh pr create --fill',
        'powershell',
        'The bash reading takes the backslash as an escape, reads the folder as ..or, which holds'
        ' no repository, and so finds no create in a recorded repository.',
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
    """One case's switches: the series switch set to `mode` or cleared, and an empty data folder.

    The data folder is the core's own state folder; the pack must write nothing there.
    """
    saved = {name: os.environ.get(name) for name in (GATE, DATA)}
    data = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    if mode is None:
        os.environ.pop(GATE, None)
    else:
        os.environ[GATE] = mode
    os.environ[DATA] = str(data)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    assert list(data.iterdir()) == [], list(data.iterdir())


# ------------------------------------------------- events and notes, built here


def _observation(command: str = 'observed') -> dict:
    return {
        'session': 'observed',
        'parent': 'unavailable',
        'root': 'unavailable',
        'origin': 'unavailable',
        'command': command,
        'paths': 'not_applicable',
    }


def _act(command: object, cwd: object, digest: str = 'a' * 64) -> dict:
    return {
        'kind': 'shell',
        'command': command,
        'argv': None,
        'paths': [],
        'cwd': cwd,
        'payload_sha256': digest,
    }


def event_from_payload(raw: bytes) -> dict:
    """The event the first slice's Claude Code shell builds from a PreToolUse payload of a shell tool."""
    payload = json.loads(raw.decode('utf-8'))
    given = payload.get('tool_input')
    given = given if isinstance(given, dict) else {}
    command = given['command'] if isinstance(given.get('command'), str) else None
    return {
        'kit_event': 1,
        'run_id': None,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': payload['session_id'], 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': _observation(),
        'act': _act(command, payload['cwd'], hashlib.sha256(raw).hexdigest()),
    }


def note_from_payload(raw: bytes) -> dict:
    """The outcome note the Claude Code note mode builds from a result payload of a shell tool."""
    payload = json.loads(raw.decode('utf-8'))
    event = event_from_payload(raw)
    if payload['hook_event_name'] == 'PostToolUseFailure':
        status, output, truncated = 'failed', None, False
    else:
        response = payload.get('tool_response')
        response = response if isinstance(response, dict) else {}
        task = response.get('backgroundTaskId')
        status = 'background' if isinstance(task, str) and task else 'completed'
        stdout = response.get('stdout')
        output, truncated = None, False
        if status == 'completed' and isinstance(stdout, str):
            output, truncated = stdout[-OUTPUT_CAP:], len(stdout) > OUTPUT_CAP
    note = {k: event[k] for k in ('run_id', 'harness', 'session', 'origin', 'observation')}
    body = {'kind': 'outcome', 'act': event['act'], 'status': status}
    body.update(output=output, truncated=truncated)
    return {'kit_note': 1, **note, 'note': body}


def _note(command: str, cwd: str, status: str = 'completed', output: object = None) -> dict:
    return {
        'kit_note': 1,
        'run_id': None,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': 's1', 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': _observation(),
        'note': {
            'kind': 'outcome',
            'act': _act(command, cwd),
            'status': status,
            'output': output,
            'truncated': False,
        },
    }


def _record(note: dict, facts: dict) -> dict:
    """`record` as `kit note` calls it: a sound note, without `run_id` and `session`."""
    notes.check_note(note)
    got = RECORD(notes.record_argument(note), copy.deepcopy(facts))
    result, _ = checkers.read_record_return(got)
    assert result in ('facts', 'unchanged'), got
    return got


def _check(command: object, cwd: object, facts: dict | None, observed: str = 'observed') -> dict:
    got = CHECK(_act(command, cwd), _observation(observed), copy.deepcopy(facts))
    assert checkers.read_return(got)[0] == got['result'], got
    return got


# ------------------------------------------------- parity with the core's tests


class _Replay:
    """The calls the core's tests make, each run through the core and replayed through the pack."""

    def __init__(self) -> None:
        self.recorded = 0
        self.skipped = 0
        self.facts: dict[tuple[object, str], dict] = {}
        self.pre: list[tuple[str, str, str, str]] = []  # command, dialect, core, pack

    def _skipped(self, payload: object) -> bool | None:
        """True to skip and count, None to neither replay nor count, False to replay."""
        if not isinstance(payload, dict):
            return True
        if not isinstance(payload.get('session_id'), str):
            return True
        event = payload.get('hook_event_name')
        if not isinstance(event, str):
            return True
        if event not in ('PreToolUse', 'PostToolUse'):
            return None
        if not isinstance(payload.get('tool_name'), str) or not isinstance(payload.get('cwd'), str):
            return True
        if payload['tool_name'] not in SHELL_TOOLS:
            return None
        return False

    def replay(self, box: object, data: bytes, proc: object) -> None:
        try:
            payload = json.loads(data.decode('utf-8'))
        except ValueError:
            payload = None
        verdict = self._skipped(payload)
        if verdict:
            self.skipped += 1
            return
        if verdict is None:
            return
        facts = self.facts.setdefault((box, payload['session_id']), {})
        if payload['hook_event_name'] == 'PostToolUse':
            got = _record(note_from_payload(data), facts)
            if 'facts' in got:
                self.facts[(box, payload['session_id'])] = got['facts']
            return
        event = event_from_payload(data)
        got = CHECK(event['act'], event['observation'], copy.deepcopy(facts))
        assert checkers.read_return(got)[0] == got['result'], got
        core = test_series_guard.decision(proc)
        dialect = SHELL_TOOLS[payload['tool_name']]
        self.pre.append((event['act']['command'], dialect, core, got['result']))


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


def _core_main(flag: str, data: bytes, encoding: str) -> types.SimpleNamespace:
    """The core's `main` in this process on `data`, with the streams a subprocess would have."""
    out, err = io.BytesIO(), io.BytesIO()
    wrappers = (
        io.TextIOWrapper(io.BytesIO(data), encoding='utf-8'),
        io.TextIOWrapper(out, encoding=encoding, write_through=True),
        io.TextIOWrapper(err, encoding=encoding, write_through=True),
    )
    streams = (sys.stdin, sys.stdout, sys.stderr)
    sys.stdin, sys.stdout, sys.stderr = wrappers
    try:
        code = series_guard.main([flag])
        for wrapper in wrappers[1:]:
            wrapper.flush()
    finally:
        sys.stdin, sys.stdout, sys.stderr = streams
        for wrapper in wrappers:
            wrapper.detach()  # the byte buffers stay open to be read
    return types.SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())


def _replay_core_tests() -> _Replay:
    replay = _Replay()
    real = test_series_guard.Box.run

    def run(box, flag, payload, mode=None, raw=None):
        data = raw if raw is not None else json.dumps(payload).encode('utf-8')
        env = box.env(mode)
        replay.recorded += 1
        with _environment(env):
            proc = _core_main(flag, data, env.get('PYTHONIOENCODING') or 'utf-8')
            replay.replay(box, data, proc)
        return proc

    test_series_guard.Box.run = run
    try:
        for name, fn in sorted(vars(test_series_guard).items()):
            if name.startswith('test_') and callable(fn):
                fn()
    finally:
        test_series_guard.Box.run = real
    return replay


STATS: dict[str, int] = {}


def test_parity_with_the_core_over_its_own_tests():
    replay = _replay_core_tests()
    STATS.update(recorded=replay.recorded, skipped=replay.skipped)
    assert replay.pre, 'the core tests made no PreToolUse call'
    listed = {(command, dialect) for command, dialect, _ in LISTED_ROWS}
    unlisted = []
    for command, dialect, core, pack in replay.pre:
        assert core in ('allow', 'deny'), (command, core)
        if pack == 'match':
            assert core == 'deny', ('a pack match the core allows', command, dialect)
        elif core == 'deny' and (command, dialect) not in listed:
            unlisted.append((command, dialect, pack))
    assert unlisted == [], unlisted
    assert any(pack == 'match' for *_, pack in replay.pre), replay.pre
    assert replay.skipped == 10, replay.skipped


def test_listed_rows_have_their_shape():
    assert isinstance(LISTED_ROWS, tuple)
    for row in LISTED_ROWS:
        assert isinstance(row, tuple) and len(row) == 3, row
        command, dialect, reason = row
        assert isinstance(command, str) and dialect in ('bash', 'powershell'), row
        assert isinstance(reason, str) and reason.strip() and reason.isascii(), row


# ------------------------------------------------------------- own corpus


def _repo(name: str, origin: str | None) -> Path:
    path = Path(tempfile.mkdtemp(dir=SCRATCH.name)) / name
    (path / '.git').mkdir(parents=True)
    config = '[core]\n\trepositoryformatversion = 0\n'
    if origin is not None:
        config += f'[remote "origin"]\n\turl = {origin}\n'
    (path / '.git' / 'config').write_text(config, encoding='utf-8')
    return path


URL = 'https://github.com/o/r/pull/1'
RECORDED = {'repos': {'o/r': [URL]}}
REPO = _repo('or', 'https://github.com/o/r.git')


def _series_file() -> Path:
    path = REPO / 'docs' / 'series.toml'
    path.parent.mkdir(exist_ok=True)
    path.write_text('[series]\n', encoding='utf-8')
    return path


def test_a_first_create_is_no_match():
    for command in ('gh pr create -R o/r --fill', 'gh pr create --fill'):
        with _case():
            assert _check(command, str(REPO), {}) == {'result': 'no-match'}, command
            other = {'repos': {'x/y': ['https://github.com/x/y/pull/2']}}
            assert _check(command, str(REPO), other) == {'result': 'no-match'}, command


def test_a_plain_second_create_in_a_recorded_repository_is_a_match():
    for command in (
        'gh pr create -R o/r --fill',
        'gh pr create --fill',
        'cd x; gh pr create -R O/R',
    ):
        with _case():
            got = _check(command, str(REPO), RECORDED)
        assert got['result'] == 'match', (command, got)


def test_keel_series_forms_pass_in_both_dialects():
    series = _series_file()
    for command in (
        f'KEEL_SERIES={series.as_posix()} gh pr create -R o/r --fill',
        'KEEL_SERIES=docs/series.toml gh pr create -R o/r --fill',
        'KEEL_SERIES=none:hotfix gh pr create -R o/r --fill',
        f"$env:KEEL_SERIES='{series}'; gh pr create -R o/r --fill",
        "$env:KEEL_SERIES='none:hotfix'; gh pr create -R o/r --fill",
    ):
        with _case():
            assert _check(command, str(REPO), RECORDED) == {'result': 'no-match'}, command


def test_keel_series_without_a_reason_or_naming_a_missing_file_is_a_match():
    for command in (
        'KEEL_SERIES=none: gh pr create -R o/r',
        "$env:KEEL_SERIES='none:'; gh pr create -R o/r",
        'KEEL_SERIES=docs/missing.toml gh pr create -R o/r',
    ):
        with _case():
            got = _check(command, str(REPO), RECORDED)
        assert got['result'] == 'match', (command, got)


def test_a_create_in_another_repository_is_no_match():
    with _case():
        assert _check('gh pr create -R o/other', str(REPO), RECORDED) == {'result': 'no-match'}


def test_a_create_only_the_powershell_reading_finds_is_no_match():
    heredoc = "cat > notes.md <<'EOF'\ngh pr create -R o/r\nEOF\n"
    assert not series_guard.find_creates(heredoc, 'bash', REPO)
    assert series_guard.find_creates(heredoc, 'powershell', REPO)
    with _case():
        assert _check(heredoc, str(REPO), RECORDED) == {'result': 'no-match'}


def test_none_facts_cannot_tell_only_when_a_reading_finds_a_create():
    heredoc = "cat > notes.md <<'EOF'\ngh pr create -R o/r\nEOF\n"
    with _case():
        for command in ('gh pr create -R o/r', heredoc):
            assert _check(command, str(REPO), None) == {'result': 'cannot-tell'}, command
        for command in ('git status', 'echo pr create', 'git commit -m "gh pr create"'):
            assert _check(command, str(REPO), None) == {'result': 'no-match'}, command


def test_an_unobserved_command_cannot_tell():
    with _case():
        for observed in ('unavailable', 'not_applicable'):
            got = _check('gh pr create -R o/r', str(REPO), RECORDED, observed)
            assert got == {'result': 'cannot-tell'}, observed


def test_malformed_recorded_repositories_cannot_tell():
    with _case():
        for facts in ({'repos': []}, {'repos': {'o/r': 'x'}}, {'repos': {'o/r': [1]}}):
            got = _check('gh pr create -R o/r', str(REPO), facts)
            assert got == {'result': 'cannot-tell'}, facts
        assert _check('gh pr create -R o/r', str(REPO), {'other': 1}) == {'result': 'no-match'}


def test_the_switches():
    for mode in ('0', 'observe'):
        with _case(mode):
            got = _check('gh pr create -R o/r', str(REPO), RECORDED)
            assert got == {'result': 'no-match'}, (mode, got)
    with _case('0'):
        note = _note('gh pr create -R o/r', str(REPO), output=URL + '\n')
        assert _record(note, {}) == {'result': 'unchanged'}
    with _case('observe'):
        assert _record(note, {}) == {'facts': RECORDED}
    with _case('1'):
        assert _check('gh pr create -R o/r', str(REPO), RECORDED)['result'] == 'match'


def test_record_keeps_the_first_url_per_key_and_appends_new_ones():
    output = (
        'https://github.com/O/R/pull/1\nhttps://github.com/o/r/pull/9\n'
        'https://github.com/x/y/pull/2\r\n'
    )
    with _case():
        got = _record(_note('gh pr create -R o/r', str(REPO), output=output), {})
        assert got == {
            'facts': {
                'repos': {
                    'o/r': ['https://github.com/O/R/pull/1'],
                    'x/y': ['https://github.com/x/y/pull/2'],
                }
            }
        }, got
        later = _note('gh pr create -R o/r', '', output='https://github.com/o/r/pull/3\n')
        got = _record(later, RECORDED)
        assert got == {'facts': {'repos': {'o/r': [URL, 'https://github.com/o/r/pull/3']}}}, got
        again = _note('gh pr create -R o/r', str(REPO), output=URL)
        assert _record(again, RECORDED) == {'result': 'unchanged'}


def test_record_skips_what_did_not_create_a_pull_request():
    heredoc = "cat > notes.md <<'EOF'\ngh pr create -R o/r\nEOF\n"
    with _case():
        for note in (
            _note('gh pr create -R o/r', str(REPO), 'failed', None),
            _note('gh pr create -R o/r', str(REPO), 'background', None),
            _note('gh pr create -R o/r', str(REPO), 'unknown', None),
            _note('gh pr create -R o/r', str(REPO), 'completed', None),
            _note('gh pr create -R o/r', str(REPO), 'completed', 'no url here'),
            _note('gh pr view 1 --json url -q .url', str(REPO), 'completed', URL),
            _note(heredoc, str(REPO), 'completed', URL),
        ):
            assert _record(note, {}) == {'result': 'unchanged'}, note['note']


def test_record_ignores_a_note_that_is_not_an_observed_shell_outcome():
    with _case():
        prompt = _note('gh pr create -R o/r', str(REPO), output=URL)
        prompt['note'] = {'kind': 'prompt', 'text': URL, 'truncated': False}
        prompt['observation'] = {**_observation('not_applicable'), 'paths': 'not_applicable'}
        assert _record(prompt, {}) == {'result': 'unchanged'}


def test_a_second_create_after_a_recorded_one_matches_in_both_dialects():
    with _case():
        facts: dict = {}
        got = _record(_note('gh pr create -R o/r --fill', str(REPO), output=URL), facts)
        facts = got['facts']
        assert _check('gh pr create -R o/r --fill', str(REPO), facts)['result'] == 'match'
        got = _check('gh pr create -R o/r --fill', str(REPO), {})
        assert got == {'result': 'no-match'}


# --------------------------------------------------------- reason and detail


def _core_text(key: str, prs: list[str], why: str) -> str:
    return series_guard.deny_reason(key, prs, why)


def test_the_pack_reason_is_the_cores_text_between_the_marks():
    data = tomllib.loads((HERE / 'pack.toml').read_text(encoding='utf-8'))
    (rule,) = data['rule']
    (checker,) = data['checker']
    assert 'prevention' not in data
    assert data['pack'] == 1 and data['name'] == 'series'
    assert checker == {
        'id': CHECKER_ID,
        'file': 'series_rule.py',
        'budget_ms': 250,
        'records': ['outcome'],
    }, checker
    assert rule['id'] == RULE_ID and rule['check'] == CHECKER_ID
    assert rule['effect'] == 'deny' and rule['governed'] is False and rule['kinds'] == ['shell']
    for key, prs, why in (('o/r', [URL], 'W.'), ('a/b', [], 'The command carries no KEEL_SERIES.')):
        text = _core_text(key, prs, why)
        start = text.index(FIRST_MARK)
        end = text.index(LAST_MARK) + len(LAST_MARK)
        assert rule['reason'] == text[start:end], rule['reason']
    (built,) = [r for r in POLICY.rules if r.id == RULE_ID]
    assert built.reason == rule['reason']
    assert CHECKER.records == ('outcome',)


def test_the_detail_starts_with_why_and_composes_with_the_reason():
    (rule,) = [r for r in POLICY.rules if r.id == RULE_ID]
    with _case():
        for command, why in (
            ('gh pr create -R o/r', 'The command carries no KEEL_SERIES.'),
            (
                'KEEL_SERIES=none: gh pr create -R o/r',
                'KEEL_SERIES=none: needs a reason after the colon.',
            ),
        ):
            got = _check(command, str(REPO), RECORDED)
            assert got['result'] == 'match', got
            detail = got['detail']
            assert detail.startswith(why + ' '), detail
            head = detail[len(why) + 1 :]
            text = _core_text('o/r', [URL], why)
            assert f'{head} {why} {rule.reason}' == text[: text.rindex(' The value given')], detail
            cut = checkers.reduce_detail(detail)
            assert cut.startswith(why), cut


def test_the_detail_comes_from_the_bash_reading():
    with _case():
        missing = 'KEEL_SERIES=docs/missing.toml gh pr create -R o/r'
        got = _check(missing, str(REPO), RECORDED)
        assert got['detail'].startswith('KEEL_SERIES names '), got
        # Bash sees no KEEL_SERIES here; PowerShell sees `none:` without a reason.
        both = "$env:KEEL_SERIES='none:'; gh pr create -R o/r"
        got = _check(both, str(REPO), RECORDED)
        assert got['result'] == 'match', got
        assert got['detail'].startswith('The command carries no KEEL_SERIES. '), got


def test_a_command_without_the_words_create_and_pr_is_no_match():
    # The core's cheap exit: the bash reading of `cr\eate` is `create`, but the text lacks it.
    escaped = 'gh pr cr\\eate -R o/r'
    assert series_guard.find_creates(escaped, 'bash', REPO)
    with _case():
        for facts in (None, RECORDED):
            assert _check(escaped, str(REPO), facts) == {'result': 'no-match'}, facts


# ----------------------------------------------------- the pack in a process


def _copy_tree(dest: Path, core: str | None = 'series_guard.py') -> Path:
    """A scratch copy of the pack and of the core folder, the core saved as `core` (or left out)."""
    pack = dest / 'harness-kit' / 'packs' / 'series'
    pack.mkdir(parents=True)
    for name in ('pack.toml', 'series_rule.py'):
        shutil.copyfile(HERE / name, pack / name)
    hooks = dest / 'plugins' / 'session-workflow' / 'hooks'
    hooks.mkdir(parents=True)
    if core is not None:
        shutil.copyfile(HOOKS / 'series_guard.py', hooks / core)
    return pack


def _kit_env(tree: Path, run_id: str | None = None) -> dict:
    """The environment of a child run in `tree`: bytecode writing left on, its cache under `tree`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    for name in (GATE, DATA, 'PYTHONDONTWRITEBYTECODE'):
        env.pop(name, None)
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
        env=_kit_env(tree, run_id),
        timeout=60,
    )


def _build(tree: Path, pack: Path) -> tuple[subprocess.CompletedProcess, Path]:
    base = tree / 'base.toml'
    base.write_bytes(b'version = 1\n\n[launcher]\ntest_roots = []\nforbidden_roots = []\n')
    out = tree / 'policy.toml'
    args = ('policy', 'build', '--base', str(base), '--pack', str(pack), '--out', str(out))
    return _kit(tree, *args), out


def _plugin_bytecode(tree: Path) -> list[Path]:
    plugins = tree / 'plugins'
    found = [p for p in plugins.rglob('*') if p.name == '__pycache__' or p.suffix == '.pyc']
    found += list((tree / 'pycache').rglob('series_guard*.pyc'))
    return found


def test_a_built_policy_records_then_denies_and_writes_no_cache():
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    pack = _copy_tree(tree)
    built, policy = _build(tree, pack)
    assert built.returncode == 0, built
    run_id, _ = state.mint_run(tree / 'state', 'claude-code')
    note = _note('gh pr create -R o/r --fill', str(REPO), output=URL + '\n')
    note['run_id'] = run_id
    with _case():
        noted = _kit(
            tree, 'note', '--policy', str(policy), stdin=json.dumps(note).encode(), run_id=run_id
        )
    assert noted.returncode == 0, noted
    receipt = json.loads(noted.stdout.decode('ascii'))
    assert receipt['outcome'] == 'recorded', receipt
    assert receipt['recorders'] == [{'id': CHECKER_ID, 'result': 'facts'}], receipt
    event = {
        'kit_event': 1,
        'run_id': run_id,
        'harness': {'name': 'claude-code', 'version': '2.1.316'},
        'session': {'id': 's1', 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': _observation(),
        'act': _act('gh pr create -R o/r --fill', str(REPO)),
    }
    with _case():
        judged = _kit(
            tree, 'judge', '--policy', str(policy), stdin=json.dumps(event).encode(), run_id=run_id
        )
    assert judged.returncode == 0, judged
    lines = judged.stdout.decode('ascii').splitlines()
    assert len(lines) == 1, judged
    verdict = json.loads(lines[0])
    assert (verdict['verdict'], verdict['governed'], verdict['rule']) == ('deny', False, RULE_ID), (
        verdict
    )
    why = 'The command carries no KEEL_SERIES.'
    text = _core_text('o/r', [URL], why)
    detail = f'{why} ' + text[: text.index(f' {why} ')]
    reason = text[text.index(FIRST_MARK) : text.index(LAST_MARK) + len(LAST_MARK)]
    assert verdict['reason'] == f'{checkers.reduce_detail(detail)} {reason}', verdict
    assert any((tree / 'pycache').rglob('*.pyc')), 'the child wrote no bytecode at all'
    assert _plugin_bytecode(tree) == [], _plugin_bytecode(tree)


def _does_not_execute(tree: Path, pack: Path, needle: bytes) -> None:
    alone = subprocess.run(  # noqa: S603 - this interpreter, fixed argv, no shell
        [sys.executable, str(pack / 'series_rule.py')],
        capture_output=True,
        env=_kit_env(tree),
        timeout=60,
    )
    assert alone.returncode != 0, alone
    assert needle in alone.stderr, alone
    built, out = _build(tree, pack)
    assert built.returncode == 64, built
    assert not out.exists()
    assert not packs.sidecar_path(out).exists()


def test_with_the_core_renamed_the_checker_does_not_execute_and_the_build_refuses():
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    pack = _copy_tree(tree, core='series_guard_moved.py')
    _does_not_execute(tree, pack, b'series_guard')


def test_with_a_used_name_missing_the_checker_does_not_execute():
    tree = Path(tempfile.mkdtemp(dir=SCRATCH.name))
    pack = _copy_tree(tree)
    core = tree / 'plugins' / 'session-workflow' / 'hooks' / 'series_guard.py'
    text = core.read_text(encoding='utf-8')
    assert '_PULL_URL' in text
    core.write_text(text.replace('_PULL_URL', '_PULL_LINK'), encoding='utf-8')
    _does_not_execute(tree, pack, b'_PULL_URL')


if __name__ == '__main__':
    names = sorted(n for n, f in list(globals().items()) if n.startswith('test_') and callable(f))
    for name in names:
        globals()[name]()
    print(
        f'ok: series rule pack ({len(names)} checks) recorded={STATS["recorded"]} '
        f'skipped={STATS["skipped"]} listed={len(LISTED_ROWS)}'
    )

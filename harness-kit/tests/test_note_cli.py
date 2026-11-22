#!/usr/bin/env python3
"""Checks of `kit note [--policy PATH]` and the note journal, end to end.

Contract under test:
- one note as JSON on stdin, exactly one receipt line of ASCII JSON on stdout
  with the keys `kit_note_receipt`, `outcome`, `reason` and `recorders`, and
  exit 0 whenever the arguments parse; an unknown argument exits 2;
- the order of decisions: an invalid note is `invalid`; a refused state root is
  `failed` (for an invalid note too) and writes nothing; a note outside a minted
  run is `outside-run`; an unreadable policy is `dropped`, `policy-unreadable`;
  a launched, valid note under a readable policy is `dropped`, `no-recorder`,
  and no checker is loaded;
- one line per note in `notes.ndjson`: `runs/<run_id>/` when launched,
  `not-launched/invalid/` for an invalid note outside a run, else
  `not-launched/<16 hex or no-session>/`, with exactly the stated keys and no
  text, command, output or cwd; no line goes to any `journal.ndjson`;
- a journal that cannot be written turns the receipt into `failed`, with the
  reason `journal not written: ...`;
- `kit doctor --json` lists the same unlaunched sessions before and after notes
  outside a run.

Stdlib-runnable: `python test_note_cli.py`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import state
from kit_fixtures import SRC, event, run_module
from test_notes import OUTCOME, PROMPT

RECEIPT_KEYS = ['kit_note_receipt', 'outcome', 'reason', 'recorders']
LINE_KEYS = [
    'ts_utc',
    'run_id',
    'launched',
    'session_id',
    'harness',
    'note_kind',
    'status',
    'chars',
    'truncated',
    'content_sha256',
    'payload_sha256',
    'outcome',
    'reason',
    'recorders',
]


def _env(root: Path | str, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env['KIT_STATE_ROOT'] = str(root)
    env.update(extra)
    return env


def _kit(stdin: bytes, *args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=60,
    )


def _note(stdin: bytes, *args: str, env: dict) -> dict:
    proc = _kit(stdin, 'note', *args, env=env)
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    out = proc.stdout
    assert out.isascii(), out
    assert out.endswith(b'\n'), out
    lines = out.decode('ascii').splitlines()
    assert len(lines) == 1, out
    receipt = json.loads(lines[0])
    assert list(receipt) == RECEIPT_KEYS, receipt
    assert receipt['kit_note_receipt'] == 1, receipt
    assert receipt['recorders'] == [], receipt
    reason = receipt['reason']
    assert reason is None or (isinstance(reason, str) and reason.isascii()), receipt
    return receipt


def _bytes(note: dict) -> bytes:
    return json.dumps(note).encode('utf-8')


def _lines(path: Path) -> list[dict]:
    lines = [json.loads(x) for x in path.read_text(encoding='ascii').splitlines()]
    for line in lines:
        assert list(line) == LINE_KEYS, line
    return lines


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())


V2_POLICY = """\
version = 2

[[checker]]
id = "marker-check"
file = "marker_check.py"
sha256 = "{sha}"
budget_ms = 250

[[rule]]
id = "marked"
effect = "deny"
governed = false
kinds = ["shell"]
check = "marker-check"
reason = "a test rule"
"""


def _v2_policy(folder: Path) -> tuple[Path, Path]:
    """A readable version 2 policy whose checker writes a marker when it is loaded."""
    marker = folder / 'loaded.marker'
    source = (
        'from pathlib import Path\n'
        f'Path({str(marker)!r}).write_text("loaded")\n'
        'def check(act, observation):\n'
        '    return {"result": "no-match"}\n'
    ).encode()
    (folder / 'marker_check.py').write_bytes(source)
    policy = folder / 'policy.toml'
    text = V2_POLICY.format(sha=hashlib.sha256(source).hexdigest())
    policy.write_text(text, encoding='utf-8')
    return policy, marker


def _mint(root: Path) -> str:
    run_id, _ = state.mint_run(root, 'claude-code')
    return run_id


def test_a_note_in_a_minted_run_under_a_version_2_policy_is_dropped_with_no_recorder():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id = _mint(root)
        policy, marker = _v2_policy(base)
        env = _env(root, KIT_RUN_ID=run_id)
        receipt = _note(_bytes(PROMPT), '--policy', str(policy), env=env)
        assert (receipt['outcome'], receipt['reason']) == ('dropped', 'no-recorder'), receipt
        assert not marker.exists(), 'a checker was loaded'
        receipt = _note(_bytes(OUTCOME), env=dict(env, KIT_POLICY=str(policy)))
        assert (receipt['outcome'], receipt['reason']) == ('dropped', 'no-recorder'), receipt
        assert not marker.exists(), 'a checker was loaded'
        lines = _lines(root / 'runs' / run_id / 'notes.ndjson')
        assert len(lines) == 2, lines
        prompt, outcome = lines
        assert prompt['run_id'] == run_id and prompt['launched'] is True, prompt
        assert (prompt['outcome'], prompt['reason'], prompt['recorders']) == (
            'dropped',
            'no-recorder',
            [],
        )
        assert prompt['session_id'] == PROMPT['session']['id'], prompt
        assert prompt['harness'] == 'claude-code', prompt
        text = PROMPT['note']['text']
        assert (prompt['note_kind'], prompt['status'], prompt['payload_sha256']) == (
            'prompt',
            None,
            None,
        )
        assert prompt['chars'] == len(text) and prompt['truncated'] is False, prompt
        assert prompt['content_sha256'] == hashlib.sha256(text.encode('utf-8')).hexdigest()
        output = OUTCOME['note']['output']
        assert (outcome['note_kind'], outcome['status']) == ('outcome', 'completed'), outcome
        assert outcome['chars'] == len(output), outcome
        assert outcome['content_sha256'] == hashlib.sha256(output.encode('utf-8')).hexdigest()
        assert outcome['payload_sha256'] == '0' * 64, outcome
        assert outcome['harness'] == 'opencode' and outcome['session_id'] == 'ses_child'
        assert prompt['ts_utc'].endswith('Z'), prompt


def test_the_note_run_id_is_not_read_for_launch():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        run_id = _mint(root)
        note = copy.deepcopy(PROMPT)
        note['run_id'] = run_id
        receipt = _note(_bytes(note), env=_env(root))
        assert (receipt['outcome'], receipt['reason']) == ('outside-run', None), receipt
        assert not (root / 'runs' / run_id / 'notes.ndjson').exists()
        forged = _env(root, KIT_RUN_ID='20261113T120000Z-0123456789ab')
        assert _note(_bytes(PROMPT), env=forged)['outcome'] == 'outside-run'


def test_an_unreadable_policy_is_dropped_as_policy_unreadable():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id = _mint(root)
        bad = base / 'bad.toml'
        bad.write_text('this is not [ toml', encoding='utf-8')
        env = _env(root, KIT_RUN_ID=run_id)
        for args, extra in (
            (('--policy', str(bad)), {}),
            ((), {'KIT_POLICY': str(bad)}),
            ((), {}),
            (('--policy', str(base / 'absent.toml')), {}),
        ):
            receipt = _note(_bytes(PROMPT), *args, env=dict(env, **extra))
            assert (receipt['outcome'], receipt['reason']) == ('dropped', 'policy-unreadable')
        lines = _lines(root / 'runs' / run_id / 'notes.ndjson')
        assert [x['reason'] for x in lines] == ['policy-unreadable'] * 4, lines


def test_the_policy_flag_wins_over_kit_policy():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        run_id = _mint(root)
        good, _ = _v2_policy(base)
        bad = base / 'bad.toml'
        bad.write_text('version = 5\n', encoding='utf-8')
        env = _env(root, KIT_RUN_ID=run_id, KIT_POLICY=str(bad))
        assert _note(_bytes(PROMPT), '--policy', str(good), env=env)['reason'] == 'no-recorder'
        assert _note(_bytes(PROMPT), env=env)['reason'] == 'policy-unreadable'


def test_a_note_outside_a_run_is_journalled_by_its_session_folder():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        policy, marker = _v2_policy(Path(td))
        env = _env(root, KIT_POLICY=str(policy))
        receipt = _note(_bytes(PROMPT), env=env)
        assert (receipt['outcome'], receipt['reason']) == ('outside-run', None), receipt
        folder = state.session_folder(PROMPT['session']['id'])
        lines = _lines(root / 'not-launched' / folder / 'notes.ndjson')
        assert len(lines) == 1, lines
        line = lines[0]
        assert (line['run_id'], line['launched'], line['outcome'], line['reason']) == (
            None,
            False,
            'outside-run',
            None,
        )
        nobody = copy.deepcopy(PROMPT)
        nobody['session']['id'] = None
        assert _note(_bytes(nobody), env=env)['outcome'] == 'outside-run'
        lines = _lines(root / 'not-launched' / 'no-session' / 'notes.ndjson')
        assert lines[0]['session_id'] is None, lines
        assert not marker.exists()


def test_an_invalid_note_is_journalled_as_invalid_in_both_places():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        receipt = _note(b'{"kit_note": 2', env=_env(root))
        assert receipt['outcome'] == 'invalid', receipt
        assert isinstance(receipt['reason'], str) and receipt['reason'], receipt
        lines = _lines(root / 'not-launched' / 'invalid' / 'notes.ndjson')
        assert len(lines) == 1, lines
        line = lines[0]
        assert line['outcome'] == 'invalid' and line['reason'] is None, line
        for key in ('run_id', 'session_id', 'harness', 'note_kind', 'status', 'chars'):
            assert line[key] is None, (key, line)
        for key in ('truncated', 'content_sha256', 'payload_sha256'):
            assert line[key] is None, (key, line)
        assert line['launched'] is False and line['recorders'] == [], line
        run_id = _mint(root)
        bad = copy.deepcopy(PROMPT)
        bad['origin'] = 'owner'
        receipt = _note(_bytes(bad), env=_env(root, KIT_RUN_ID=run_id))
        assert receipt['outcome'] == 'invalid', receipt
        lines = _lines(root / 'runs' / run_id / 'notes.ndjson')
        assert [(x['outcome'], x['run_id'], x['launched']) for x in lines] == [
            ('invalid', run_id, True)
        ], lines


def test_an_invalid_reason_in_the_receipt_is_ascii():
    with tempfile.TemporaryDirectory() as td:
        bad = copy.deepcopy(PROMPT)
        bad['note']['\u00e9t\u00e9'] = 1
        receipt = _note(_bytes(bad), env=_env(Path(td) / 'state'))
        assert receipt['outcome'] == 'invalid', receipt


def test_a_refused_state_root_gives_failed_and_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / '.claude' / 'kit-state'
        env = _env(root, KIT_RUN_ID='20261113T120000Z-0123456789ab')
        for data in (_bytes(PROMPT), _bytes(OUTCOME), b'not json', b''):
            receipt = _note(data, env=env)
            assert receipt['outcome'] == 'failed', receipt
            assert isinstance(receipt['reason'], str) and receipt['reason'], receipt
        assert not root.exists(), _files(base)


def test_a_journal_that_cannot_be_written_gives_failed():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        folder = root / 'not-launched' / state.session_folder(PROMPT['session']['id'])
        (folder / 'notes.ndjson').mkdir(parents=True)
        receipt = _note(_bytes(PROMPT), env=_env(root))
        assert receipt['outcome'] == 'failed', receipt
        assert receipt['reason'].startswith('journal not written: '), receipt


def test_an_unknown_argument_exits_2():
    with tempfile.TemporaryDirectory() as td:
        proc = _kit(_bytes(PROMPT), 'note', '--bogus', env=_env(Path(td) / 'state'))
        assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
        assert proc.stdout == b'', proc.stdout


def test_no_text_command_output_or_cwd_lands_under_the_state_root():
    planted = {
        'text': 'planted-prompt-7f3a91',
        'command': 'echo planted-command-52bd0e',
        'output': 'planted-output-c81e44',
        'cwd': 'C:/scratch/planted-cwd-0d9b7a',
    }
    prompt = copy.deepcopy(PROMPT)
    prompt['note']['text'] = planted['text']
    outcome = copy.deepcopy(OUTCOME)
    outcome['note']['act']['command'] = planted['command']
    outcome['note']['act']['cwd'] = planted['cwd']
    outcome['note']['output'] = planted['output']
    bad = copy.deepcopy(outcome)
    bad['note']['extra'] = planted['text']
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        policy, _ = _v2_policy(base)
        run_id = _mint(root)
        for env in (_env(root, KIT_POLICY=str(policy), KIT_RUN_ID=run_id), _env(root)):
            for note in (prompt, outcome, bad):
                _note(_bytes(note), env=env)
        for rel in _files(root):
            data = (root / rel).read_bytes()
            for needle in planted.values():
                for form in (needle, needle.replace('/', '\\\\'), 'planted'):
                    assert form.encode('utf-8') not in data, (rel, form)


def test_no_note_adds_a_line_to_any_event_journal():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        policy, _ = _v2_policy(base)
        run_id = _mint(root)
        launched = _env(root, KIT_POLICY=str(policy), KIT_RUN_ID=run_id)
        for env in (launched, _env(root)):
            for data in (_bytes(PROMPT), _bytes(OUTCOME), b'{}'):
                _note(data, env=env)
        journals = [p for p in _files(root) if p.endswith('journal.ndjson')]
        assert journals == [], journals


def _doctor_sessions(env: dict) -> list:
    proc = _kit(b'', 'doctor', '--json', env=env)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)['not_launched']


def test_the_doctor_lists_the_same_unlaunched_sessions_after_notes():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        root = base / 'state'
        missing = json.dumps([str(base / 'no-such-harness.exe')])
        env = _env(
            root,
            KIT_HARNESS_ARGV_CLAUDE_CODE=missing,
            KIT_HARNESS_ARGV_OPENCODE=missing,
        )
        judged = _kit(json.dumps(event()).encode('utf-8'), 'judge', env=env)
        assert judged.returncode == 0, judged.stderr
        before = _doctor_sessions(env)
        assert len(before) == 1, before
        for n in range(20):
            note = copy.deepcopy(PROMPT if n % 2 else OUTCOME)
            note['session']['id'] = 'note-session-' + str(n % 3)
            if n == 7:
                note['session']['id'] = event()['session']['id']
            receipt = _note(_bytes(note), env=env)
            assert receipt['outcome'] == 'outside-run', receipt
        assert _doctor_sessions(env) == before


if __name__ == '__main__':
    run_module(globals(), 'kit note')

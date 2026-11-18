"""Command-line entry and subcommand dispatch for `kit`."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from harness_kit import __version__, checkers, facts, notes, packs, state
from harness_kit.event import InvalidEventError, check_event, parse_event
from harness_kit.policy import Policy, PolicyError, load_policy
from harness_kit.verdict import (
    CANARY_DENY_RULE,
    UNREADABLE_RUN,
    judge,
    judge_bytes,
    unknown_verdict,
)

POLICY_ENV = 'KIT_POLICY'
EXIT_REFUSED = 64
EXIT_INTERNAL = 70
MAX_ENVELOPE = 16 * 1024 * 1024
# How long a judgement retries a run record it meets while kit replaces it.
RUN_READ_S = 1.0
FROM_HELP = (
    'read one envelope of the shell of harness NAME instead, which its driver translates; '
    f'one over {MAX_ENVELOPE} bytes is invalid'
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='kit', description='harness-kit command line')
    parser.add_argument('--version', action='version', version=f'kit {__version__}')
    sub = parser.add_subparsers(dest='command', metavar='COMMAND')
    judge = sub.add_parser(
        'judge',
        help='judge one neutral event read from stdin; print one verdict line',
        description=(
            'Read one neutral event as JSON on stdin and print one verdict as one line '
            f'of JSON. The policy is --policy, else ${POLICY_ENV}.'
        ),
    )
    judge.add_argument('--policy', metavar='PATH', help=f'policy file (default: ${POLICY_ENV})')
    judge.add_argument('--from', dest='source', metavar='NAME', help=FROM_HELP)
    note = sub.add_parser(
        'note',
        help='take one session note read from stdin; print one receipt line; exit 0',
        description=(
            'Read one note (a submitted prompt or a finished shell call) as JSON on stdin '
            'and print one receipt as one line of JSON. Exits 0 once the arguments parse. '
            f'The policy is --policy, else ${POLICY_ENV}.'
        ),
    )
    note.add_argument('--policy', metavar='PATH', help=f'policy file (default: ${POLICY_ENV})')
    note.add_argument('--from', dest='source', metavar='NAME', help=FROM_HELP)
    st = sub.add_parser('state', help='the state root and run identity')
    st_sub = st.add_subparsers(dest='state_command', metavar='STATE_COMMAND', required=True)
    st_sub.add_parser('path', help='print the state root')
    new_run = st_sub.add_parser('new-run', help='mint a run; print its id and folder as JSON')
    new_run.add_argument('--harness', metavar='NAME', required=True, help='harness name')
    stub = sub.add_parser('stub', help='serve a scripted local model endpoint for tests')
    stub.add_argument('--log', required=True, help='file that receives one JSON line per request')
    stub.add_argument('--script', required=True, help='JSON array of tool-call and text steps')
    stub.add_argument(
        '--port', type=int, default=0, help='port on 127.0.0.1 (default: any free port)'
    )
    home = sub.add_parser('home', help='test homes a harness runs in')
    home_sub = home.add_subparsers(dest='home_command', metavar='HOME_COMMAND', required=True)
    render = home_sub.add_parser(
        'render', help='render a test home into an absent or empty folder; print home.json'
    )
    render.add_argument('--harness', metavar='NAME', required=True, help='claude-code or opencode')
    render.add_argument('--dir', metavar='DIR', required=True, help='absent or empty folder')
    render.add_argument(
        '--endpoint', metavar='URL', required=True, help='model endpoint, http://127.0.0.1:PORT'
    )
    render.add_argument(
        '--policy',
        metavar='FILE',
        help='policy whose recorded note kinds go into note_config.json; unreadable exits 64',
    )
    doctor = sub.add_parser(
        'doctor',
        help='report what was tested per objective and harness, the runs and unlaunched sessions',
    )
    doctor.add_argument('--json', action='store_true', help='print the report as one JSON line')
    doctor.add_argument(
        '--live',
        action='store_true',
        help='also run the presence canary per harness found (needs --live-root)',
    )
    doctor.add_argument(
        '--live-root',
        metavar='DIR',
        help='folder for the live scratch homes, under a test root of KIT_POLICY',
    )
    packs.add_parser(sub)
    sub.add_parser(
        'run',
        help='check a session, then start the harness: run --harness NAME --home DIR '
        '--workdir DIR --policy FILE -- HARNESS_ARGS...',
        add_help=False,
    )
    return parser


def _load(path: str | None):
    if not path:
        return PolicyError(f'no policy: pass --policy or set {POLICY_ENV}')
    try:
        return load_policy(path)
    except PolicyError as exc:
        return exc


def _valid_event(data: bytes) -> dict | None:
    try:
        return check_event(parse_event(data))
    except InvalidEventError:
        return None


def read_input(source: str | None) -> bytes | None:
    """Standard input whole; with `--from`, at most MAX_ENVELOPE bytes, None when longer."""
    if source is None:
        return sys.stdin.buffer.read()
    data = sys.stdin.buffer.read(MAX_ENVELOPE + 1)
    return data if len(data) <= MAX_ENVELOPE else None


def _driver(source: str, method: str, error: type[ValueError]):
    """The bound `method` of the driver of `source`; `error` when there is none."""
    from harness_kit import harnesses

    try:
        driver = harnesses.get(source)
    except KeyError as exc:
        raise error(str(exc.args[0])) from None
    found = getattr(driver, method, None)
    if found is None:
        raise error(f'harness {source!a} sends no envelope')
    return driver, found


def from_envelope(data: bytes | None, source: str) -> tuple[dict, tuple[str, str] | None]:
    """(neutral event, the driver's refused tool or None) of one envelope of `source`.

    The envelope goes whole to the driver of `source`; this module names no key
    of it and no tool. InvalidEventError for an envelope that is too long,
    unreadable or refused by the driver, a name no driver has, or a driver that
    translates no envelope.
    """
    if data is None:
        raise InvalidEventError(f'envelope is longer than {MAX_ENVELOPE} bytes')
    driver, translate = _driver(source, 'translate_event', InvalidEventError)
    envelope = parse_event(data)
    event = translate(envelope)
    return event, driver.refused_tool(envelope)


def read_run(root: Path, run_id: str) -> dict | str:
    """The run record of a launched event, or UNREADABLE_RUN when it is not one JSON object.

    kit replaces `run.json` only before and after a session, so a read that meets the
    replacement is retried for a short while.
    """
    path = Path(root) / 'runs' / run_id / 'run.json'
    end = time.monotonic() + RUN_READ_S
    while True:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except PermissionError:
            if time.monotonic() >= end:
                return UNREADABLE_RUN
            time.sleep(0.02)
            continue
        except (OSError, ValueError):
            return UNREADABLE_RUN
        return data if isinstance(data, dict) else UNREADABLE_RUN


def judge_and_journal(data: bytes | None, policy, env, source: str | None = None) -> dict:
    """Judge one event under the run identity the environment names, and journal it.

    A journal that cannot be written, a refused state root among its forms,
    turns the verdict into `unknown`, governed. Inside a canary run (its nonce
    in `KIT_CANARY_NONCE`) a refusal by `canary.deny` of a launched event is
    recorded by the refused marker in the run's canary folder. A valid,
    launched event with a root key hands its recording checkers their session
    facts, read without any lock; a judgement writes no facts. With `source`,
    `data` is an envelope of that harness's shell, judged as the neutral event
    its driver translates it into, with the driver's refused tool.
    """
    try:
        root = state.state_root(env)
    except state.StateRootError as exc:
        root, journal_error = None, str(exc)
    else:
        journal_error = None
    run_id = env.get(state.RUN_ID_ENV)
    launched = root is not None and state.is_launched(root, run_id)
    run_id = run_id if launched else None
    nonce = state.canary_nonce(env)

    doc, refused = None, None
    if source is None:
        event = _valid_event(data) if root is not None else None
    else:
        try:
            doc, refused = from_envelope(data, source)
            event = check_event(doc) if root is not None else None
        except InvalidEventError as exc:
            doc, event = exc, None
    reader = None
    if launched and event is not None:
        key = facts.root_key(event)
        if key is not None:
            reader = facts.judge_reader(root, run_id, key)
    run, run_dir = (
        (read_run(root, run_id), str(root / 'runs' / run_id)) if launched else (None, None)
    )
    if source is None:
        verdict = judge_bytes(data, policy, launched, nonce, facts=reader, run=run, run_dir=run_dir)
    elif isinstance(doc, InvalidEventError) and not isinstance(policy, PolicyError):
        verdict = unknown_verdict(f'invalid event: {doc}', policy.sha256)
    else:
        doc = None if isinstance(doc, InvalidEventError) else doc
        verdict = judge(
            doc, policy, launched, nonce, facts=reader, refused=refused, run=run, run_dir=run_dir
        )
    if root is not None:
        now = datetime.now(timezone.utc)
        record = state.journal_record(verdict, event, run_id, launched, now)
        try:
            state.append_journal(state.journal_path(root, run_id, event), record)
        except state.JournalError as exc:
            journal_error = str(exc)
    if journal_error is not None:
        verdict = unknown_verdict(f'journal not written: {journal_error}', verdict['policy_sha256'])
    if verdict['rule'] == CANARY_DENY_RULE and launched and nonce is not None:
        marker = state.refused_marker(root, run_id, nonce)
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(b'')
        except OSError:
            pass  # no marker: the canary fails, which is the closed side
    verdict['run_id'] = run_id
    verdict['launched'] = launched
    return verdict


def run_judge(policy_path: str | None, source: str | None = None) -> int:
    """Print exactly one verdict line; exit 0 whenever it was printed.

    A policy that declares checkers puts the output sink in place before any
    checker loads: descriptors 1 and 2 go to the null device and the verdict
    is written to a duplicate of descriptor 1. The process then ends through
    `os._exit` right after that line, since a checker thread still writing
    could otherwise abort the interpreter's shutdown.
    """
    verdict_fd = None
    try:
        policy = _load(policy_path or os.environ.get(POLICY_ENV))
        if isinstance(policy, Policy) and policy.checkers:
            verdict_fd = checkers.install_sink()
        verdict = judge_and_journal(read_input(source), policy, os.environ, source)
    except Exception as exc:  # a verdict is owed whatever failed; unknown denies
        verdict = unknown_verdict(f'judge failed: {type(exc).__name__}')
    line = json.dumps(verdict, ensure_ascii=True) + '\n'
    if verdict_fd is None:
        sys.stdout.write(line)
        sys.stdout.flush()
        return 0
    try:
        checkers.write_all(verdict_fd, line.encode('ascii'))
        os.close(verdict_fd)
    finally:
        os._exit(0)


def _receipt(outcome: str, reason: str | None, recorders: list | None = None) -> dict:
    if reason is not None:
        reason = reason.encode('ascii', 'backslashreplace').decode('ascii')
    return {
        'kit_note_receipt': 1,
        'outcome': outcome,
        'reason': reason,
        'recorders': list(recorders or []),
    }


def note_and_journal(
    data: bytes | None,
    policy_path: str | None,
    env,
    sink: list | None = None,
    source: str | None = None,
) -> dict:
    """Take one note under the run identity the environment names, journal it, return the receipt.

    In order: an invalid note is `invalid`; a refused state root is `failed` and
    writes nothing; a note outside a minted run is `outside-run`; an unreadable
    policy is `dropped`, `policy-unreadable`; a policy with no checker that
    records the note's kind is `dropped`, `no-recorder`; a note with no root
    key is `dropped`, `no-root`. Otherwise the output sink is put in place
    before the first checker loads, its duplicate of descriptor 1 is appended
    to `sink` when one is given, each recorder runs (`notes.record_note`) and
    the note is `recorded`. The journal line is appended after the last
    recorder, with no facts lock held; one that cannot be written turns the
    receipt into `failed`. With `source`, `data` is an envelope of that
    harness's shell, taken as the note its driver translates it into.
    """
    try:
        doc = notes.parse_note(data) if source is None else note_from_envelope(data, source)
        note = notes.check_note(doc)
        invalid = None
    except notes.InvalidNoteError as exc:
        note, invalid = None, str(exc)
    try:
        root = state.state_root(env)
    except state.StateRootError as exc:
        return _receipt('failed', f'journal not written: {exc}')
    run_id = env.get(state.RUN_ID_ENV)
    launched = state.is_launched(root, run_id)
    run_id = run_id if launched else None

    results: list[dict] = []
    if note is None:
        outcome, reason = 'invalid', None
    elif not launched:
        outcome, reason = 'outside-run', None
    else:
        outcome, reason = _drop_or_record(note, _load(policy_path), root, run_id, sink, results)

    now = datetime.now(timezone.utc)
    record = state.note_record(note, run_id, launched, outcome, reason, results, now)
    try:
        state.append_journal(state.notes_path(root, run_id, note), record)
    except state.JournalError as exc:
        return _receipt('failed', f'journal not written: {exc}', results)
    return _receipt(outcome, invalid if note is None else reason, results)


def note_from_envelope(data: bytes | None, source: str) -> dict:
    """The note one envelope of `source` stands for; InvalidNoteError as `from_envelope` refuses."""
    if data is None:
        raise notes.InvalidNoteError(f'envelope is longer than {MAX_ENVELOPE} bytes')
    _, translate = _driver(source, 'translate_note', notes.InvalidNoteError)
    return translate(notes.parse_note(data))


def _drop_or_record(note: dict, policy, root, run_id: str, sink, results: list):
    """(outcome, reason) of a valid, launched note; the recorders' results go to `results`."""
    if isinstance(policy, PolicyError):
        return 'dropped', 'policy-unreadable'
    recorders = notes.recorders_for(note, policy.checkers)
    if not recorders:
        return 'dropped', 'no-recorder'
    key = facts.root_key(note)
    if key is None:
        return 'dropped', 'no-root'
    out_fd = checkers.install_sink()
    if sink is not None:
        sink.append(out_fd)
    results.extend(notes.record_note(note, recorders, root, run_id, key))
    return 'recorded', None


def run_note(policy_path: str | None, source: str | None = None) -> int:
    """Print exactly one receipt line; exit 0 whatever the note and whatever failed.

    Once a recorder is about to load, the output sink is in place and the
    receipt goes to its duplicate of descriptor 1; the process then ends
    through `os._exit(0)` right after that line, as `kit judge` does, since a
    recorder thread still writing could otherwise abort the interpreter's
    shutdown.
    """
    sink: list[int] = []
    try:
        receipt = note_and_journal(
            read_input(source), policy_path or os.environ.get(POLICY_ENV), os.environ, sink, source
        )
    except Exception as exc:  # a receipt is owed whatever failed; a note never decides
        receipt = _receipt('failed', f'note failed: {type(exc).__name__}')
    line = json.dumps(receipt, ensure_ascii=True) + '\n'
    if not sink:
        sys.stdout.write(line)
        sys.stdout.flush()
        return 0
    try:
        checkers.write_all(sink[0], line.encode('ascii'))
        os.close(sink[0])
    finally:
        os._exit(0)


def _fail(code: int, message: str) -> int:
    sys.stderr.write(f'kit: {message}\n')
    sys.stderr.flush()
    return code


def run_state(args: argparse.Namespace) -> int:
    """`kit state path` and `kit state new-run`; a refused root exits 64 and creates nothing."""
    try:
        root = state.state_root()
    except state.StateRootError as exc:
        return _fail(EXIT_REFUSED, str(exc))
    if args.state_command == 'path':
        sys.stdout.write(state.ascii_path(root) + '\n')
        return 0
    if not args.harness:
        return _fail(EXIT_REFUSED, 'new-run refused: --harness is empty')
    try:
        run_id, run_dir = state.mint_run(root, args.harness)
    except OSError as exc:
        return _fail(EXIT_INTERNAL, f'run not minted under {state.ascii_path(root)}: {exc!a}')
    out = {'run_id': run_id, 'run_dir': str(run_dir)}
    sys.stdout.write(json.dumps(out, ensure_ascii=True) + '\n')
    return 0


def run_home(args: argparse.Namespace) -> int:
    """`kit home render`; a non-empty folder, an unknown harness or a foreign endpoint exits 64.

    With `--policy`, the policy must load, else the render exits 64 and writes
    nothing; the kinds of note its checkers record go to `note_config.json`.
    """
    from harness_kit import harnesses

    try:
        driver = harnesses.get(args.harness)
    except KeyError as exc:
        return _fail(EXIT_REFUSED, str(exc.args[0]))
    records: tuple[str, ...] = ()
    if args.policy is not None:
        try:
            records = harnesses.recorded_kinds(load_policy(args.policy).checkers)
        except PolicyError as exc:
            return _fail(EXIT_REFUSED, f'home not rendered: policy unreadable: {exc}')
    try:
        home = driver.render_home(Path(args.dir), args.endpoint, records)
    except harnesses.HomeError as exc:
        return _fail(EXIT_REFUSED, f'home not rendered: {exc}')
    except OSError as exc:
        return _fail(EXIT_INTERNAL, f'home not rendered: {exc!a}')
    sys.stdout.write(json.dumps(home, ensure_ascii=True) + '\n')
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['run']:
        from harness_kit import launcher

        return launcher.main(argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == 'judge':
        return run_judge(args.policy, args.source)
    if args.command == 'note':
        return run_note(args.policy, args.source)
    if args.command == 'state':
        return run_state(args)
    if args.command == 'home':
        return run_home(args)
    if args.command == 'doctor':
        from harness_kit import doctor

        return doctor.main(args.json, args.live, args.live_root)
    if args.command == 'policy':
        return packs.run_build(args)
    if args.command == 'stub':
        from harness_kit import stubmodel

        return stubmodel.run(args.log, args.script, args.port)
    parser.print_help()
    return 0

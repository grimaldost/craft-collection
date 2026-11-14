"""Command-line entry and subcommand dispatch for `kit`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness_kit import __version__, checkers, notes, packs, state
from harness_kit.event import InvalidEventError, check_event, parse_event
from harness_kit.policy import Policy, PolicyError, load_policy
from harness_kit.verdict import CANARY_DENY_RULE, judge_bytes, unknown_verdict

POLICY_ENV = 'KIT_POLICY'
EXIT_REFUSED = 64
EXIT_INTERNAL = 70


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


def judge_and_journal(data: bytes, policy, env) -> dict:
    """Judge one event under the run identity the environment names, and journal it.

    A journal that cannot be written, a refused state root among its forms,
    turns the verdict into `unknown`, governed. Inside a canary run (its nonce
    in `KIT_CANARY_NONCE`) a refusal by `canary.deny` of a launched event is
    recorded by the refused marker in the run's canary folder.
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

    verdict = judge_bytes(data, policy, launched, nonce)
    if root is not None:
        event = _valid_event(data)
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


def run_judge(policy_path: str | None) -> int:
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
        verdict = judge_and_journal(sys.stdin.buffer.read(), policy, os.environ)
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


def _receipt(outcome: str, reason: str | None) -> dict:
    if reason is not None:
        reason = reason.encode('ascii', 'backslashreplace').decode('ascii')
    return {'kit_note_receipt': 1, 'outcome': outcome, 'reason': reason, 'recorders': []}


def note_and_journal(data: bytes, policy_path: str | None, env) -> dict:
    """Take one note under the run identity the environment names, journal it, return the receipt.

    In order: an invalid note is `invalid`; a refused state root is `failed` and
    writes nothing; a note outside a minted run is `outside-run`; an unreadable
    policy is `dropped`, `policy-unreadable`; else `dropped`, `no-recorder`. No
    checker is loaded. A journal line that cannot be written turns the receipt
    into `failed`.
    """
    try:
        note = notes.check_note(notes.parse_note(data))
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

    if note is None:
        outcome, reason = 'invalid', None
    elif not launched:
        outcome, reason = 'outside-run', None
    elif isinstance(_load(policy_path), PolicyError):
        outcome, reason = 'dropped', 'policy-unreadable'
    else:
        outcome, reason = 'dropped', 'no-recorder'

    now = datetime.now(timezone.utc)
    record = state.note_record(note, run_id, launched, outcome, reason, [], now)
    try:
        state.append_journal(state.notes_path(root, run_id, note), record)
    except state.JournalError as exc:
        return _receipt('failed', f'journal not written: {exc}')
    return _receipt(outcome, invalid if note is None else reason)


def run_note(policy_path: str | None) -> int:
    """Print exactly one receipt line; exit 0 whatever the note and whatever failed."""
    try:
        receipt = note_and_journal(
            sys.stdin.buffer.read(), policy_path or os.environ.get(POLICY_ENV), os.environ
        )
    except Exception as exc:  # a receipt is owed whatever failed; a note never decides
        receipt = _receipt('failed', f'note failed: {type(exc).__name__}')
    sys.stdout.write(json.dumps(receipt, ensure_ascii=True) + '\n')
    sys.stdout.flush()
    return 0


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
        return run_judge(args.policy)
    if args.command == 'note':
        return run_note(args.policy)
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

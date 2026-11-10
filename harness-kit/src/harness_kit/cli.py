"""Command-line entry and subcommand dispatch for `kit`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from harness_kit import __version__, state
from harness_kit.event import InvalidEventError, check_event, parse_event
from harness_kit.policy import PolicyError, load_policy
from harness_kit.verdict import judge_bytes, unknown_verdict

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
    st = sub.add_parser('state', help='the state root and run identity')
    st_sub = st.add_subparsers(dest='state_command', metavar='STATE_COMMAND', required=True)
    st_sub.add_parser('path', help='print the state root')
    new_run = st_sub.add_parser('new-run', help='mint a run; print its id and folder as JSON')
    new_run.add_argument('--harness', metavar='NAME', required=True, help='harness name')
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
    turns the verdict into `unknown`, governed.
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

    verdict = judge_bytes(data, policy, launched)
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
    verdict['run_id'] = run_id
    verdict['launched'] = launched
    return verdict


def run_judge(policy_path: str | None) -> int:
    """Print exactly one verdict line; exit 0 whenever it was printed."""
    try:
        policy = _load(policy_path or os.environ.get(POLICY_ENV))
        verdict = judge_and_journal(sys.stdin.buffer.read(), policy, os.environ)
    except Exception as exc:  # a verdict is owed whatever failed; unknown denies
        verdict = unknown_verdict(f'judge failed: {type(exc).__name__}')
    sys.stdout.write(json.dumps(verdict, ensure_ascii=True) + '\n')
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == 'judge':
        return run_judge(args.policy)
    if args.command == 'state':
        return run_state(args)
    parser.print_help()
    return 0

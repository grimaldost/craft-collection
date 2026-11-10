"""Command-line entry and subcommand dispatch for `kit`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness_kit import __version__, state
from harness_kit.event import InvalidEventError, check_event, parse_event
from harness_kit.policy import PolicyError, load_policy
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


def run_home(args: argparse.Namespace) -> int:
    """`kit home render`; a non-empty folder, an unknown harness or a foreign endpoint exits 64."""
    from harness_kit import harnesses

    try:
        driver = harnesses.get(args.harness)
    except KeyError as exc:
        return _fail(EXIT_REFUSED, str(exc.args[0]))
    try:
        home = driver.render_home(Path(args.dir), args.endpoint)
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
    if args.command == 'state':
        return run_state(args)
    if args.command == 'home':
        return run_home(args)
    if args.command == 'stub':
        from harness_kit import stubmodel

        return stubmodel.run(args.log, args.script, args.port)
    parser.print_help()
    return 0

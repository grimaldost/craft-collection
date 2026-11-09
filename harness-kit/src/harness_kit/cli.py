"""Command-line entry and subcommand dispatch for `kit`."""

from __future__ import annotations

import argparse
import json
import os
import sys

from harness_kit import __version__
from harness_kit.policy import PolicyError, load_policy
from harness_kit.verdict import judge_bytes, unknown_verdict

POLICY_ENV = 'KIT_POLICY'


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
    return parser


def _load(path: str | None):
    if not path:
        return PolicyError(f'no policy: pass --policy or set {POLICY_ENV}')
    try:
        return load_policy(path)
    except PolicyError as exc:
        return exc


def run_judge(policy_path: str | None) -> int:
    """Print exactly one verdict line; exit 0 whenever it was printed."""
    try:
        policy = _load(policy_path or os.environ.get(POLICY_ENV))
        verdict = judge_bytes(sys.stdin.buffer.read(), policy)
    except Exception as exc:  # a verdict is owed whatever failed; unknown denies
        verdict = unknown_verdict(f'judge failed: {type(exc).__name__}')
    sys.stdout.write(json.dumps(verdict, ensure_ascii=True) + '\n')
    sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == 'judge':
        return run_judge(args.policy)
    parser.print_help()
    return 0

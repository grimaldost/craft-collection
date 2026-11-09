"""Command-line entry and subcommand dispatch for `kit`."""

from __future__ import annotations

import argparse
import sys

from harness_kit import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='kit', description='harness-kit command line')
    parser.add_argument('--version', action='version', version=f'kit {__version__}')
    commands = parser.add_subparsers(dest='command')
    stub = commands.add_parser('stub', help='serve a scripted local model endpoint for tests')
    stub.add_argument('--log', required=True, help='file that receives one JSON line per request')
    stub.add_argument('--script', required=True, help='JSON array of tool-call and text steps')
    stub.add_argument(
        '--port', type=int, default=0, help='port on 127.0.0.1 (default: any free port)'
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == 'stub':
        from harness_kit import stubmodel

        return stubmodel.run(args.log, args.script, args.port)
    parser.print_help()
    return 0

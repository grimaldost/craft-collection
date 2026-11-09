"""Command-line entry and subcommand dispatch for `kit`."""

from __future__ import annotations

import argparse
import sys

from harness_kit import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='kit', description='harness-kit command line')
    parser.add_argument('--version', action='version', version=f'kit {__version__}')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    parser.print_help()
    return 0

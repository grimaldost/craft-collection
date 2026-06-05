#!/usr/bin/env python3
"""Check latest PyPI versions against the python-engineering canonical stack.

Reads pinned versions from stack.toml (the single source of truth) and compares
them to the latest on PyPI, flagging any tool whose pinned floor is behind a
newer major/minor release. Exits non-zero when anything is behind, so CI can
detect drift.

Usage:
    python check_versions.py            # pretty table
    python check_versions.py --json     # machine-readable (for CI / refresh-stack)

Requires: Python 3.11+ (stdlib only: tomllib, urllib).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import tomllib

# stack.toml lives at the skill root, one level up from scripts/.
DEFAULT_STACK = Path(__file__).resolve().parent.parent / 'stack.toml'


def load_stack(path: Path = DEFAULT_STACK) -> dict:
    """Load and return the parsed stack.toml."""
    with Path(path).open('rb') as fh:
        return tomllib.load(fh)


def load_tools(path: Path = DEFAULT_STACK) -> dict[str, str]:
    """Return {pypi_name: pinned_min} from stack.toml's [tools.*] tables."""
    stack = load_stack(path)
    return {e['pypi']: str(e['pinned_min']) for e in stack.get('tools', {}).values()}


def load_precommit(path: Path = DEFAULT_STACK) -> dict[str, str]:
    """Return {hook_repo: pinned_rev} from stack.toml's [precommit] table."""
    return dict(load_stack(path).get('precommit', {}))


def _ver(s: str) -> tuple[int, int, int]:
    """Parse a version string into a (major, minor, patch) tuple; non-numeric
    parts -> 0 (so '1.2rc1' -> (1, 2, 0))."""
    parts = (s or '').split('.')

    def _int(i: int) -> int:
        return int(parts[i]) if len(parts) > i and parts[i].isdigit() else 0

    return (_int(0), _int(1), _int(2))


def is_behind(pinned_min: str, latest: str) -> bool:
    """True when `latest` is a newer release than the pinned floor.

    The skill pins a floor, not an exact version, so for a stable tool a patch
    bump (same major.minor) is NOT 'behind' — only a new minor/major warrants
    review. But for a true 0ver tool (major and minor both 0, e.g. ty 0.0.x) the
    patch axis is where every release lands, so 0.0.1 -> 0.0.43 DOES count.
    Comparing only (major, minor) made every 0.0.x release invisible to drift.
    """
    pin, late = _ver(pinned_min), _ver(latest)
    depth = 3 if pin[0] == 0 and pin[1] == 0 else 2  # 0.0.x -> compare patch too
    return late[:depth] > pin[:depth]


def fetch_pypi_version(package: str, pinned_min: str) -> dict:
    """Fetch latest version + upload date from the PyPI JSON API.

    Never raises: any failure is reported in the returned dict's 'status'.
    """
    url = f'https://pypi.org/pypi/{package}/json'
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})  # noqa: S310 - fixed https host
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https host
            data = json.loads(resp.read().decode())
        version = data['info']['version']
        files = data.get('releases', {}).get(version) or []
        upload_date = (files[-1].get('upload_time_iso_8601', '') or '')[:10] if files else ''
        return {
            'package': package,
            'latest': version,
            'pinned_min': pinned_min,
            'upload_date': upload_date or 'unknown',
            'behind': is_behind(pinned_min, version),
            'status': 'ok',
        }
    except urllib.error.HTTPError as e:
        return {
            'package': package,
            'latest': None,
            'pinned_min': pinned_min,
            'upload_date': None,
            'behind': False,
            'status': f'HTTP {e.code}',
        }
    except Exception as e:
        return {
            'package': package,
            'latest': None,
            'pinned_min': pinned_min,
            'upload_date': None,
            'behind': False,
            'status': str(e),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check canonical stack versions.')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--stack', type=Path, default=DEFAULT_STACK, help='Path to stack.toml')
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    tools = load_tools(args.stack)
    precommit = load_precommit(args.stack)
    results = [fetch_pypi_version(pkg, pinned) for pkg, pinned in tools.items()]
    behind = [r for r in results if r['behind']]

    if args.json:
        print(
            json.dumps(
                {
                    'checked_at': now,
                    'tools': results,
                    'precommit': precommit,
                    'behind_count': len(behind),
                },
                indent=2,
            )
        )
        return 1 if behind else 0

    print(f'\n  python-engineering stack - version check ({now})')
    print(f'  {"-" * 64}')
    print(f'  {"Package":<22} {"Pinned >=":<12} {"Latest":<14} {"Released":<12}')
    print(f'  {"-" * 64}')
    for r in results:
        if r['status'] != 'ok':
            flag = f'  ! {r["status"]}'
        elif r['behind']:
            flag = '  <- behind'
        else:
            flag = ''
        latest = r['latest'] or '(error)'
        date = r['upload_date'] or '?'
        print(f'  {r["package"]:<22} {r["pinned_min"]:<12} {latest:<14} {date:<12}{flag}')
    print(f'  {"-" * 64}')
    print('\n  Pre-commit hooks pinned in stack.toml:')
    for name, rev in precommit.items():
        print(f'    {name}: {rev}')
    if behind:
        print(
            f'\n  {len(behind)} tool(s) behind a newer minor/major. Run /refresh-stack '
            'to review changelogs and update.'
        )
    print()
    return 1 if behind else 0


if __name__ == '__main__':
    sys.exit(main())

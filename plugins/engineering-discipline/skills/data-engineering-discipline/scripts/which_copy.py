#!/usr/bin/env python3
"""Which copy of a module is actually running?

Reading a library end-to-end proves nothing when the venv imports a different
copy: an editable checkout and an installed release of the same name diverge
silently, and the read is then inference dressed as observation. This resolves
the imported module's `__file__` and the installed distribution's version and
fails when a checkout SHADOWS an installed distribution of the same name.

    python which_copy.py polars pandas

Exit 0 when every named module resolves to its installed copy (or has no
installed distribution at all), 1 when one shadows an installed distribution,
2 on a usage error (nothing named, or a module that does not import - which is
a failure to resolve, never a clean bill of health). Stdlib only.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import sys
import sysconfig


def site_paths() -> list[str]:
    """Directories the interpreter treats as installed-package roots. The stdlib
    roots are included, or every stdlib module reads as a local checkout."""
    keys = ('purelib', 'platlib', 'stdlib', 'platstdlib')
    return sorted({sysconfig.get_paths().get(k, '') for k in keys} - {''})


def _norm(path: str) -> str:
    return path.replace('\\', '/').lower()


def classify(name: str, module_file: str | None, version: str | None, sites: list[str]) -> dict:
    """Report where `name` resolved from. Pure -- feed it the three facts.

    `state` is one of: 'installed' (resolved inside an installed-package root),
    'shadowing' (resolved elsewhere while a distribution of that name IS
    installed -- the read copy is not the shipped one), 'local-only' (resolved
    elsewhere with no installed distribution, which is normal for a checkout),
    or 'no-file' (a builtin or namespace package, named rather than assumed).
    """
    if not module_file:
        state = 'no-file'
    elif any(_norm(module_file).startswith(_norm(s)) for s in sites):
        state = 'installed'
    else:
        state = 'shadowing' if version else 'local-only'
    return {
        'name': name,
        'file': module_file,
        'version': version,
        'state': state,
        'shadowed': state == 'shadowing',
    }


def resolve(name: str, sites: list[str] | None = None) -> dict:
    """Import `name` and classify it. Raises ImportError if it does not import."""
    module = importlib.import_module(name)
    try:
        version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        version = None
    return classify(name, getattr(module, '__file__', None), version, sites or site_paths())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Resolve which copy of a module runs.')
    parser.add_argument('modules', nargs='*', help='importable module names')
    args = parser.parse_args(argv)

    if not args.modules:
        print('error: name at least one module - resolving nothing is not a pass', file=sys.stderr)
        return 2

    shadowed = False
    for name in args.modules:
        try:
            report = resolve(name)
        except ImportError as e:
            print(f'error: {name} does not import: {e}', file=sys.stderr)
            return 2
        version = report['version'] or 'not installed as a distribution'
        print(f'{name}: {report["state"]}')
        print(f'  file    {report["file"]}')
        print(f'  version {version}')
        shadowed = shadowed or report['shadowed']
    if shadowed:
        print('SHADOWED: a checkout is being imported over an installed distribution')
        return 1
    print('WHICH-COPY OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())

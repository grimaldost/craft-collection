"""Sync gate: references/threats-catalog.md keys == schema.json threat_enum (spec section 4).

The threat catalog and the machine-readable enum are two surfaces of one closed
list; the validator (ER-THREAT) reads the enum, and a reader learns what each key
means from the catalog. If they drift, a key gets gated with no documentation or
documented with no gate. This extends the section-3 sync discipline to the section-4
reference. Stdlib only -- no PyYAML, so no skip path; it prints `ok:` on success and
raises on drift.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_JSON = HERE.parent / 'templates' / 'schema.json'
CATALOG = HERE.parent / 'references' / 'threats-catalog.md'

# Each core threat is a level-3 heading carrying its key as an inline code span:
#   ### `contamination_familiarity`
_HEADING = re.compile(r'^###\s+`([a-z_]+)`\s*$', re.MULTILINE)


def _catalog_keys() -> list[str]:
    return _HEADING.findall(CATALOG.read_text(encoding='utf-8'))


def _schema_enum() -> list[str]:
    return json.loads(SCHEMA_JSON.read_text(encoding='utf-8'))['threat_enum']


def test_catalog_keys_equal_schema_enum_exactly():
    catalog, enum = _catalog_keys(), _schema_enum()
    assert catalog == enum, (
        f'threats-catalog.md keys {catalog} != schema.json threat_enum {enum}; '
        'they are one closed list and must not drift'
    )


def test_no_duplicate_catalog_keys():
    catalog = _catalog_keys()
    assert len(catalog) == len(set(catalog)), f'duplicate threat heading in the catalog: {catalog}'


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
            except Exception as exc:  # report any failure; never emit the ok: sentinel
                failed += 1
                print(f'FAIL {name}: {exc!r}')
    if failed:
        print(f'{failed} test(s) failed')
        sys.exit(1)
    print('ok: threats-catalog.md is in sync with schema.json threat_enum')

"""Sync gates and template acceptance for the canonical schema (spec section 3).

templates/schema.json is THE machine-readable schema; two things must never drift
from it: validate.py's _EMBEDDED_SCHEMA (the pre-section-3 inline copy the gate falls
back to) and templates/SCHEMA.md (the generated human field guide). This module is the
sync gate for both, and it also proves the three tier skeletons validate as the spec
requires. PyYAML is a hard dependency (templates are YAML), so the module refuses to
run -- and never emits `skip:` -- when it is absent.
"""

from __future__ import annotations

try:
    import yaml  # noqa: F401 - imported for the hard-fail guard; used via validate/render
except ImportError:  # pragma: no cover - exercised only on a broken toolchain
    print('FAIL: PyYAML is required for the schema/template gates (mechanism spine must not skip)')
    raise SystemExit(1) from None

import json
import sys
from pathlib import Path

import render
import validate

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / 'templates'
SCHEMA_JSON = TEMPLATES / 'schema.json'
SCHEMA_MD = TEMPLATES / 'SCHEMA.md'

CONTEXT_CODES = {'ER-ANCHOR', 'ER-XCHECK', 'ER-PREREG', 'ER-COMPREHEND'}


def _schema_json() -> dict:
    return json.loads(SCHEMA_JSON.read_text(encoding='utf-8'))


def _fail_codes(report: validate.Report) -> set[str]:
    return {f.code for f in report.failures}


# --- schema.json <-> _EMBEDDED_SCHEMA (the section-2 flag) -------------------


def test_schema_json_agrees_with_embedded_schema():
    data = _schema_json()
    for key, value in validate._EMBEDDED_SCHEMA.items():
        assert key in data, f'schema.json is missing embedded key {key!r}'
        assert data[key] == value, f'schema.json[{key!r}] {data[key]!r} != embedded {value!r}'


def test_schema_json_loads_without_weakening_the_gate():
    # load_schema prefers schema.json; the completeness assertion must pass (no
    # SchemaError), and every embedded read-key must survive the merge equal.
    loaded = validate.load_schema(SCHEMA_JSON)
    for key, value in validate._EMBEDDED_SCHEMA.items():
        assert loaded[key] == value, key


def test_schema_json_is_the_loaded_default():
    # With schema.json on disk, the default load must come from it (not the embedded
    # fallback) -- proven by a key schema.json adds that the embedded copy lacks.
    loaded = validate.load_schema()
    assert 'field_shapes' in loaded, 'load_schema did not read templates/schema.json'


# --- schema.json <-> SCHEMA.md (the generated field guide) ------------------


def test_schema_md_is_in_sync_with_schema_json():
    generated = render.schema_markdown(_schema_json())
    on_disk = SCHEMA_MD.read_text(encoding='utf-8')  # universal newlines -> logical compare
    assert generated == on_disk, (
        'templates/SCHEMA.md is stale; regenerate with '
        '`python scripts/render.py --schema-md > templates/SCHEMA.md`'
    )


# --- template acceptance ----------------------------------------------------


def test_each_template_passes_schema_only_at_its_tier():
    for name in ('probe.yaml', 'measurement.yaml', 'decision.yaml'):
        path = TEMPLATES / name
        record = validate.load_record(path)
        report = validate.run_checks(record, path, schema_only=True)
        assert report.failures == [], (name, report.failures)


def test_decision_template_full_validate_fails_exactly_the_context_codes():
    path = TEMPLATES / 'decision.yaml'
    record = validate.load_record(path)
    report = validate.run_checks(record, path, schema_only=False)
    assert _fail_codes(report) == CONTEXT_CODES, _fail_codes(report)


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
    print('ok: all schema/template tests passed')

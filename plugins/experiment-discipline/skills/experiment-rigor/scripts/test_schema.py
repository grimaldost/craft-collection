"""Sync gates and template acceptance for the canonical schema (spec section 3).

templates/schema.json is THE machine-readable schema and now the only copy: the
validator's embedded fallback and the sync test that policed it are retired, so the
one thing that must never drift from schema.json is templates/SCHEMA.md (the
generated human field guide). This module is that sync gate, proves a missing or
degenerate schema file fails loudly rather than resolving to a second answer, and
proves the three tier skeletons validate as the spec requires. PyYAML is a hard dependency (templates are YAML), so the module refuses to
run -- and never emits `skip:` -- when it is absent.
"""

from __future__ import annotations

try:
    import yaml  # noqa: F401 - imported for the hard-fail guard; used via validate/render
except ImportError:  # pragma: no cover - exercised only on a broken toolchain
    print('FAIL: PyYAML is required for the schema/template gates (mechanism spine must not skip)')
    raise SystemExit(1) from None

import json
import pathlib
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


def test_known_versions_carries_both():
    # The v1.1 extension is additive, so known_versions carries BOTH: a v1.0 record
    # keeps validating and a v1.1 one is recognized.
    assert _schema_json()['known_versions'] == [1, 1.1]
    assert _schema_json()['schema_version'] == 1.1


def test_v11_contrast_keys_are_present_and_readable():
    data = _schema_json()
    assert data['contrast_estimators'] == ['paired_difference']
    assert data['contrast_interval_methods'] == ['paired_t']
    for shape in ('cluster_cell', 'contrast', 'contrast_interval', 'contrast_sign_test'):
        assert shape in data['field_shapes'], shape
    assert data['field_shapes']['contrast'] == [
        'name',
        'arms',
        'estimator',
        'estimate',
        'se',
        'n_clusters',
        'interval',
        'sign_test',
    ]
    assert data['field_shapes']['contrast_sign_test'] == ['p_value', 'effective_n', 'positive']
    # Both keys are in the completeness set, so a schema.json that emptied either
    # would raise rather than silently disable the gate that reads it.
    assert 'contrast_estimators' in validate._SCHEMA_LIST_KEYS
    assert 'contrast_interval_methods' in validate._SCHEMA_LIST_KEYS


def test_schema_json_is_the_only_source():
    loaded = validate.load_schema()
    assert 'field_shapes' in loaded, 'load_schema did not read templates/schema.json'
    assert not hasattr(validate, '_EMBEDDED_SCHEMA'), 'the embedded fallback came back'


def test_a_missing_schema_file_is_loud():
    # Retiring the fallback moves this from "resolve to a second answer" to a named
    # failure. Made to fail on purpose: a gate that silently substitutes a different
    # schema is exactly the vacuous-pass shape this plugin exists to prevent.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        missing = pathlib.Path(td) / 'nope.json'
        try:
            validate.load_schema(missing)
        except validate.SchemaError as exc:
            assert 'not found' in str(exc)
        else:
            raise AssertionError('a missing schema file resolved to something')


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

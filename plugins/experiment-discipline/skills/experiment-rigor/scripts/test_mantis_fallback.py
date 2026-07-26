"""Strict-fallback fixture for the mantis journal envelope (spec section 5, Q8; R2 fold).

The primary envelope carries the update's provenance as EXTRA header fields, which the
real mantis parsers tolerate (test_mantis_envelope.py). But the journaling contract warns
that a store MAY strict-parse and SILENTLY DROP an entry it does not like. So the emitter
defines a STRICT FALLBACK: the mantis-required keys plus a `record_ref` path and a
`record_sha256`, no provenance superset -- the provenance is not carried, it is LINKED,
hash-pinned to the typed record.

This module mocks a strict parser (one that rejects any unknown header key, i.e.
additionalProperties:false) and asserts:

  * the PRIMARY envelope is REJECTED (its provenance superset trips the strict parser);
  * the STRICT FALLBACK is ACCEPTED, well-formed (required keys present, valid origin),
    and RESOLVABLE (record_ref points at a real file whose canonical sha256 matches
    record_sha256).

That is the R2 requirement: the fallback shape is defined and tested, not left as prose.

PyYAML is a hard dependency; this module refuses to run -- and never emits `skip:` --
when it is absent, so the mechanism spine cannot go green-via-skip.
"""

from __future__ import annotations

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on a broken toolchain
    print(
        'FAIL: PyYAML is required for the mantis-fallback fixture (mechanism spine must not skip)'
    )
    raise SystemExit(1) from None

import re
import sys
import tempfile
from pathlib import Path

import render

HERE = Path(__file__).resolve().parent
EXAMPLE_DIR = HERE.parent / 'examples' / 'rg-2x2'

sys.path.insert(0, str(EXAMPLE_DIR))
import finalize  # noqa: E402 - path inserted just above

_HEADER_FIELD = re.compile(r'^([a-z_][a-z_0-9]*)\s*:\s*(.*?)$', re.MULTILINE)
_JOURNAL_ORIGINS = {'chat', 'code', 'meeting', 'reading'}


def _finalized_record() -> dict:
    frozen = yaml.safe_load((EXAMPLE_DIR / 'record.yaml').read_text(encoding='utf-8'))
    return finalize.finalize_record(frozen, 'a' * 40)


def _headers(envelope: str) -> dict[str, str]:
    header_text = envelope.split('--- CONTENT ---', 1)[0]
    return {m.group(1): m.group(2).strip() for m in _HEADER_FIELD.finditer(header_text)}


class _StrictParserRejectionError(Exception):
    """Raised by the mock strict parser when the envelope carries an unknown header key."""


def _strict_parse(envelope: str, allowed_keys: set[str]) -> dict[str, str]:
    """A MOCK parser that enforces additionalProperties:false over the header keys AND the
    mantis required-field / origin contract. Rejects (raises) on any unknown key, or on a
    malformed required set -- the silent-drop failure mode this fallback guards against,
    surfaced loudly here for the test."""
    headers = _headers(envelope)
    unknown = set(headers) - allowed_keys
    if unknown:
        raise _StrictParserRejectionError(f'unknown header keys: {sorted(unknown)}')
    missing = [k for k in render._MANTIS_REQUIRED if not headers.get(k)]
    if missing:
        raise _StrictParserRejectionError(f'missing required keys: {missing}')
    if headers['origin'] not in _JOURNAL_ORIGINS:
        raise _StrictParserRejectionError(f'bad origin: {headers["origin"]!r}')
    return headers


def _fallback_allowed_keys(record: dict) -> set[str]:
    """The strict fallback DEFINES the tolerance a strict parser must have: its own key
    set. A parser that accepts these keys accepts the fallback and rejects the superset."""
    strict = render.journal_envelope(record, strict=True, record_ref='record.yaml')
    return set(_headers(strict))


def test_strict_parser_rejects_the_primary_superset():
    record = _finalized_record()
    allowed = _fallback_allowed_keys(record)
    primary = render.journal_envelope(record, record_ref='record.yaml')
    try:
        _strict_parse(primary, allowed)
    except _StrictParserRejectionError as exc:
        # It rejects precisely because of the provenance superset (experiment/tier/...).
        assert 'experiment' in str(exc) or 'tier' in str(exc) or 'certainty' in str(exc), str(exc)
        return
    raise AssertionError(
        'the mock strict parser should have rejected the superset primary envelope'
    )


def test_strict_fallback_is_accepted_and_well_formed():
    record = _finalized_record()
    allowed = _fallback_allowed_keys(record)
    strict = render.journal_envelope(record, strict=True, record_ref='record.yaml')
    # Accepted by the same strict parser that rejected the primary.
    headers = _strict_parse(strict, allowed)
    # Well-formed: the required set present, a valid journal origin, and NO provenance superset.
    assert set(render._MANTIS_REQUIRED) <= set(headers)
    assert 'experiment' not in headers and 'certainty' not in headers, headers
    assert headers['record_ref'] and headers['record_sha256']


def test_strict_fallback_link_resolves_and_hash_matches():
    record = _finalized_record()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        record_path = d / 'record.yaml'
        record_path.write_text(yaml.safe_dump(record, sort_keys=False), encoding='utf-8')
        strict = render.journal_envelope(record, strict=True, record_ref='record.yaml')
        headers = _headers(strict)
        # RESOLVABLE: record_ref points at a real file beside the envelope.
        linked = d / headers['record_ref']
        assert linked.is_file(), linked
        # HASH-PINNED: record_sha256 is the canonical hash of the linked record.
        reloaded = yaml.safe_load(linked.read_text(encoding='utf-8'))
        assert headers['record_sha256'] == render.record_sha256(reloaded), headers['record_sha256']


def test_fallback_and_primary_differ_only_by_the_superset():
    # The fallback is the primary minus the provenance superset (plus nothing new but the
    # required set and the link) -- so the two agree on every required field.
    record = _finalized_record()
    primary = _headers(render.journal_envelope(record, record_ref='record.yaml'))
    strict = _headers(render.journal_envelope(record, strict=True, record_ref='record.yaml'))
    for key in render._MANTIS_REQUIRED:
        assert primary[key] == strict[key], (key, primary.get(key), strict.get(key))
    assert set(strict) < set(primary), 'the fallback must be a strict subset of the primary keys'


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
    print('ok: all mantis-fallback tests passed')

"""Parser-tolerance fixture for the mantis journal envelope (spec section 5, Q8).

render.py emits a record's belief-update as a journaling-sessions envelope carrying the
provenance as EXTRA header fields -- a SUPERSET of the required keys. This is only safe
if the mantis ingestion parser tolerates unknown keys (ignores them rather than dropping
the entry), because field / enum / required-key mismatches fail SILENTLY in that pipeline.

This module tests that tolerance two ways, and PRINTS which one ran:

  * REAL-PARSER mode -- if mantis.ingestion.journal_v2 is importable (set MANTIS_SRC to
    the mantis `src` dir and have its deps installed), the emitted superset envelope is
    parsed by the real JournalParserV2 and must yield exactly one fragment, zero skipped.
  * DOCUMENTED-CONTRACT mode (the portable default under `--with pyyaml`, where the
    mantis package and its structlog dependency are absent) -- the envelope is checked
    against the documented contract: the same header regex the real parser uses, the
    required-key set, the origin enum, and the type enum from the journaling-sessions
    `references/envelope-schema.json`. The extra provenance keys prove it is a superset.

PyYAML is a hard dependency; this module refuses to run -- and never emits `skip:` -- when
it is absent, so the mechanism spine cannot go green-via-skip. (The mode marker above is
NOT a skip: documented-contract mode runs real assertions and still prints `ok:`.)
"""

from __future__ import annotations

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on a broken toolchain
    print(
        'FAIL: PyYAML is required for the mantis-envelope fixture (mechanism spine must not skip)'
    )
    raise SystemExit(1) from None

import json
import os
import re
import sys
import tempfile
from pathlib import Path

import render

HERE = Path(__file__).resolve().parent
EXAMPLE_DIR = HERE.parent / 'examples' / 'rg-2x2'
PLUGINS_ROOT = HERE.parents[3]
ENVELOPE_SCHEMA = (
    PLUGINS_ROOT
    / 'session-workflow'
    / 'skills'
    / 'journaling-sessions'
    / 'references'
    / 'envelope-schema.json'
)

sys.path.insert(0, str(EXAMPLE_DIR))
import finalize  # noqa: E402 - path inserted just above

# The exact header-line regex both real mantis parsers use (journal.py / journal_v2.py).
_HEADER_FIELD = re.compile(r'^([a-z_][a-z_0-9]*)\s*:\s*(.*?)$', re.MULTILINE)
_JOURNAL_ORIGINS = {'chat', 'code', 'meeting', 'reading'}


def _finalized_record() -> dict:
    frozen = yaml.safe_load((EXAMPLE_DIR / 'record.yaml').read_text(encoding='utf-8'))
    return finalize.finalize_record(frozen, 'a' * 40)


def _split_headers(envelope: str) -> dict[str, str]:
    """Parse the header block (everything before --- CONTENT ---) exactly as the real
    parser does: collect every `key: value` line into a dict, keeping unknown keys."""
    header_text = envelope.split('--- CONTENT ---', 1)[0]
    return {m.group(1): m.group(2).strip() for m in _HEADER_FIELD.finditer(header_text)}


def _documented_enums() -> tuple[set[str], set[str]]:
    """(type enum, required set) from the documented envelope-schema.json."""
    schema = json.loads(ENVELOPE_SCHEMA.read_text(encoding='utf-8'))
    return set(schema['properties']['type']['enum']), set(schema['required'])


def _try_real_parser():
    src = os.environ.get('MANTIS_SRC')
    if src and Path(src).is_dir() and src not in sys.path:
        sys.path.insert(0, src)
    # Any import failure (mantis absent, structlog absent, ...) -> documented-contract mode.
    try:
        from mantis.ingestion.journal_v2 import JournalParserV2
    except Exception:
        return None
    return JournalParserV2


def test_primary_envelope_is_a_tolerated_superset():
    record = _finalized_record()
    envelope = render.journal_envelope(record, record_ref='record.yaml')
    headers = _split_headers(envelope)

    # The seven-field required set (v1 union) is present and non-blank -> a tolerant
    # parser has everything it needs.
    for key in render._MANTIS_REQUIRED:
        assert headers.get(key), (key, headers)
    assert headers['origin'] in _JOURNAL_ORIGINS, headers['origin']

    # It is a SUPERSET: it carries provenance keys beyond the required set. These are
    # exactly the keys a strict additionalProperties parser would reject (test_mantis_fallback).
    extras = set(headers) - set(render._MANTIS_REQUIRED)
    assert {'experiment', 'tier', 'record_ref', 'record_sha256'} <= extras, extras

    parser = _try_real_parser()
    if parser is not None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'entry.md'
            p.write_text(envelope, encoding='utf-8')
            result = parser().parse(p)
        assert len(result.fragments) == 1, (result.fragments, result.skipped)
        assert result.skipped == {}, result.skipped
        print('mode: REAL-PARSER (mantis.ingestion.journal_v2 imported)')
    else:
        type_enum, required = _documented_enums()
        assert headers['type'] in type_enum, headers['type']
        # The documented required set is a subset of what the envelope carries.
        assert required <= set(headers), (required, set(headers))
        print('mode: DOCUMENTED-CONTRACT (envelope-schema.json; mantis parser not importable)')


def test_envelope_is_deterministic():
    # No wall-clock: the same record re-emits byte-identically (timestamps come from the
    # record's own freeze / first-run fields), so a committed envelope is stable.
    record = _finalized_record()
    once = render.journal_envelope(record, record_ref='record.yaml')
    twice = render.journal_envelope(record, record_ref='record.yaml')
    assert once == twice
    assert '\r' not in once and once.endswith('--- ENTRY_END ---\n')


def test_envelope_timestamps_are_iso_t():
    record = _finalized_record()
    headers = _split_headers(render.journal_envelope(record, record_ref='record.yaml'))
    # 'T' separator, not a space (the envelope contract's example form).
    assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', headers['timestamp']), headers[
        'timestamp'
    ]


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
    print('ok: all mantis-envelope tests passed')

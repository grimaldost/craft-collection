#!/usr/bin/env python3
"""Report derivation and the drift gate for experiment-rigor (spec section 3).

The record.yaml is the single source of truth; report.md is derived and never
hand-edited. This module derives report.md, checks a committed report against its
record for drift, walks the cross-experiment update chain, and generates the
human field guide SCHEMA.md from the machine-readable templates/schema.json.

Canonical serialization policy (the E3 fold -- deterministic bytes so a re-render
of the same record is identical and the drift digest is stable across platforms):
  - keys sorted ascending at every level (sort_keys=True);
  - block style, never flow style;
  - floats emitted via repr() -- the shortest decimal that round-trips exactly
    (so 17.0 stays 17.0 and 0.1 stays 0.1, identically on every platform);
  - scalars never line-wrapped (a wrap is not semantic but changes bytes);
  - LF line endings, UTF-8, exactly one trailing newline.

The drift gate (--check) is SEMANTIC, not a byte diff: it re-parses the typed YAML
block embedded in the committed report.md, re-parses a fresh render, and compares a
sha256 over each parsed block re-serialized through the canonical policy. A cosmetic
edit to the report's prose is invisible; a changed value in the embedded block, or a
record that moved on without regenerating its report, is drift and exits 1.

Depends on PyYAML; stdlib otherwise. Python 3.13+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'templates' / 'schema.json'
_YAML_FENCE = re.compile(r'```ya?ml\n(.*?)```', re.DOTALL)
_RECORD_BLOCK_TITLE = 'Record (canonical, machine-checked)'


# --- canonical serialization ------------------------------------------------


class _CanonicalDumper(yaml.SafeDumper):
    """A SafeDumper with the pinned float representer registered (see policy)."""


def _represent_float(dumper: yaml.Dumper, value: float) -> yaml.ScalarNode:
    return dumper.represent_scalar('tag:yaml.org,2002:float', repr(float(value)))


_CanonicalDumper.add_representer(float, _represent_float)


def canonical_yaml(data: Any) -> str:
    """Serialize a Python value to canonical YAML per the module policy. The output
    ends with exactly one newline and carries no CR bytes."""
    text = yaml.dump(
        data,
        Dumper=_CanonicalDumper,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1_000_000,
        indent=2,
    )
    return text.replace('\r\n', '\n').rstrip('\n') + '\n'


# --- record loading ---------------------------------------------------------


def load_record(path: str | Path) -> dict[str, Any]:
    with open(path, encoding='utf-8') as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f'{path}: record must be a YAML mapping')
    return data


# --- report derivation ------------------------------------------------------


def _rate_line(oname: str, aname: str, arm: dict) -> str:
    num, den = arm.get('numerator'), arm.get('denominator')
    ci = arm.get('ci') if isinstance(arm.get('ci'), dict) else None
    frac = f'{num}/{den}' if num is not None and den is not None else '(no rate)'
    if ci and isinstance(ci.get('low'), (int, float)) and isinstance(ci.get('high'), (int, float)):
        method = ci.get('method', 'wilson')
        span = f'{method} CI [{ci["low"]}, {ci["high"]}]'
    else:
        span = 'no CI'
    return f'- {oname} / {aname}: {frac}, {span}'


def render_report(record: dict[str, Any]) -> str:
    """Derive the report.md text for a record. Exactly one fenced YAML block -- the
    canonical record -- is embedded; everything else is derived human prose the drift
    gate ignores."""
    experiment = record.get('experiment', '(unnamed)')
    tier = record.get('tier', '(no tier)')
    lines: list[str] = [f'# Experiment: {experiment} ({tier} tier)', '']
    lines.append('_Derived from record.yaml by render.py -- do not hand-edit._')
    lines.append('')

    design = record.get('design') or {}
    cells = design.get('cells') if isinstance(design, dict) else None
    if isinstance(cells, list) and cells:
        planned = ', '.join(
            f'{c.get("name")}={c.get("planned_n")}' for c in cells if isinstance(c, dict)
        )
        lines.append(
            f'- Design: {len(cells)} cell(s) ({planned}); shared_tasks={design.get("shared_tasks")}'
        )
    disp = record.get('disposition')
    if isinstance(disp, dict):
        lines.append(
            f'- Disposition: total={disp.get("total")}, completed={disp.get("completed")}, '
            f'excluded={disp.get("excluded")}'
        )

    outcomes = record.get('outcomes') or []
    if outcomes:
        lines.append('- Outcomes:')
        for o in outcomes:
            if isinstance(o, dict):
                lines.append(
                    f'  - {o.get("name")} (role={o.get("role")}): {o.get("operationalization")}'
                )

    results = record.get('results') or {}
    if isinstance(results, dict) and results:
        lines.append('- Results:')
        for oname, ores in results.items():
            if not isinstance(ores, dict):
                continue
            verdict = ores.get('verdict')
            if verdict is not None:
                lines.append(f'  - {oname}: verdict={verdict}, paired={ores.get("paired")}')
            for aname, arm in (ores.get('arms') or {}).items():
                if isinstance(arm, dict):
                    lines.append('  ' + _rate_line(oname, aname, arm))

    threats = record.get('threats')
    if isinstance(threats, dict):
        residual = sum(
            1 for r in threats.values() if isinstance(r, dict) and r.get('status') == 'residual'
        )
        lines.append(f'- Threats: {len(threats)} declared, {residual} residual')

    updates = record.get('updates')
    if isinstance(updates, dict):
        prior = updates.get('prior') if isinstance(updates.get('prior'), dict) else {}
        lines.append(
            f'- Update: certainty={updates.get("certainty")}, prior={prior.get("source_id")}'
        )

    lines.append('')
    lines.append(f'## {_RECORD_BLOCK_TITLE}')
    lines.append('')
    lines.append('```yaml')
    lines.append(canonical_yaml(record).rstrip('\n'))
    lines.append('```')
    return '\n'.join(lines) + '\n'


# --- the drift gate ---------------------------------------------------------


def _embedded_blocks(report_text: str) -> list[Any]:
    return [yaml.safe_load(block) for block in _YAML_FENCE.findall(report_text)]


def _digest(blocks: list[Any]) -> str:
    canon = ''.join(canonical_yaml(b) for b in blocks)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def resolve_pair(path: str | Path) -> tuple[Path, Path]:
    """Given either member of a travelling pair, return (record.yaml, report.md).
    A report.md path resolves to its sibling record.yaml; anything else is treated
    as the record and its sibling report.md is derived. This lets the drift gate fire
    on a staged report.md whose record.yaml was not restaged (F3)."""
    path = Path(path)
    if path.name == 'report.md':
        return path.parent / 'record.yaml', path
    return path, path.parent / 'report.md'


def check_drift(path: str | Path) -> str | None:
    """Return None when the report.md is in sync with its record.yaml, else a
    human-readable drift reason. Accepts either member of the pair (F3). A missing
    report or missing record is itself reported as drift (a travelling pair must carry
    both, and a report cannot be verified without its record)."""
    record_path, report = resolve_pair(path)
    if not record_path.exists():
        return f'no record.yaml beside {report.name} (a travelling report needs its record)'
    record = load_record(record_path)
    if not report.exists():
        return f'no report.md beside {record_path.name} (a travelling record carries its report)'
    committed = _embedded_blocks(report.read_text(encoding='utf-8'))
    if not committed:
        return 'committed report.md carries no embedded ```yaml block'
    fresh = _embedded_blocks(render_report(record))
    if _digest(committed) != _digest(fresh):
        return 'report.md embedded block drifted from record.yaml (regenerate with render.py)'
    return None


# --- the update chain -------------------------------------------------------


def walk_chain(record_path: str | Path) -> list[dict[str, Any]]:
    """Walk updates.prior.source_id links from a record back to the chain root,
    returned root-first. Each node is {path, record, resolved}; an unresolved link
    yields a final node with resolved=False and record=None."""
    chain: list[dict[str, Any]] = []
    seen: set[Path] = set()
    path = Path(record_path).resolve()
    while True:
        if path in seen:
            break  # cycle guard
        seen.add(path)
        if not path.exists():
            chain.append({'path': path, 'record': None, 'resolved': False})
            break
        record = load_record(path)
        chain.append({'path': path, 'record': record, 'resolved': True})
        prior = (record.get('updates') or {}).get('prior') or {}
        source_id = prior.get('source_id')
        if not source_id:
            break
        path = (path.parent / str(source_id)).resolve()
    chain.reverse()
    return chain


def render_chain(record_path: str | Path) -> str:
    chain = walk_chain(record_path)
    lines = ['# Update chain (root first)', '']
    for i, node in enumerate(chain):
        if not node['resolved']:
            lines.append(f'{i + 1}. UNRESOLVED: {node["path"]}')
            continue
        record = node['record']
        updates = record.get('updates') if isinstance(record.get('updates'), dict) else {}
        certainty = updates.get('certainty')
        reasons = updates.get('downgrade_reasons') or []
        suffix = f' -- certainty={certainty}, downgrades={list(reasons)}' if updates else ''
        lines.append(f'{i + 1}. {record.get("experiment")} ({record.get("tier")}){suffix}')
    return '\n'.join(lines) + '\n'


# --- the mantis journal envelope (Q8) ---------------------------------------
#
# render.py emits the record's belief-update as a journaling-sessions envelope so
# the mantis ingestion pipeline can compost it into the long-term store. Two shapes:
#
#   PRIMARY (default) -- the full journaling-sessions envelope carrying the update
#   and its provenance as EXTRA header fields (experiment, tier, certainty, ...): a
#   SUPERSET of the required keys. Both real mantis parsers collect header lines into
#   a dict and consume only the keys they know, ignoring the rest -- verified against
#   mantis-ai/src/mantis/ingestion/{journal.py, journal_v2.py}; neither enforces
#   additionalProperties. So the superset ingests without loss.
#
#   STRICT FALLBACK (--strict) -- for a hypothetical parser that DOES reject unknown
#   keys (an additionalProperties:false JSON-schema validator): the mantis-required
#   keys only, plus a record_ref path and a record_sha256, no rich-provenance
#   superset. The provenance is not dropped, it is LINKED: the envelope points at the
#   typed record, hash-pinned. test_mantis_fallback.py mocks a rejecting parser and
#   asserts the fallback is well-formed and resolvable (the R2 fold: the fallback
#   shape is defined and tested, not left as prose).
#
# The standing journal contract: field / enum / required-key mismatches fail SILENTLY
# in that pipeline, so the emitter matches the contract exactly -- ISO timestamps, a
# valid EntryType, one of the four journal origins, and the seven-field required set
# (the v1 union, so both JournalParser and JournalParserV2 accept the entry).

# The mantis journal-ingestion required header set: the union of the v1 and v2 parser
# contracts (v1 requires 'language', v2 does not -- emitting it satisfies both).
_MANTIS_REQUIRED: tuple[str, ...] = (
    'type',
    'author',
    'timestamp',
    'area',
    'language',
    'origin',
    'session',
)

# GRADE certainty -> journaling-sessions confidence band (evidence-calibrated,
# output-format.md section 9). A cross-experiment update is inference over small n,
# so it lands low.
_CERTAINTY_CONFIDENCE: dict[str, float] = {
    'very_low': 0.2,
    'low': 0.35,
    'moderate': 0.6,
    'high': 0.9,
}

_DEFAULT_AUTHOR = 'user:grimaldo-stanzani'
_DEFAULT_AREA = 'platform_engineering'


def _slug(text: str) -> str:
    """kebab-case slug for a session name (ASCII, lowercase, hyphen-joined)."""
    return '-'.join(re.findall(r'[a-z0-9]+', str(text).lower())) or 'experiment'


def _iso(value: Any) -> str:
    """Normalize a timestamp to ISO 8601 with a 'T' separator. PyYAML auto-parses an
    ISO string into a datetime, whose str() uses a space; the mantis parser tolerates
    both, but the T form matches the envelope contract's examples and stays stable."""
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def record_sha256(record: dict[str, Any]) -> str:
    """sha256 over the record's canonical serialization -- stable regardless of how
    record.yaml is formatted on disk (the canonical policy pins the bytes)."""
    return hashlib.sha256(canonical_yaml(record).encode('utf-8')).hexdigest()


def _envelope_content(record: dict[str, Any], *, strict: bool) -> str:
    """The CONTENT body: prose the embedder reads. Kept ASCII (ascii-runtime gate)."""
    experiment = record.get('experiment', '(unnamed)')
    tier = record.get('tier', '(no tier)')
    ref = record.get('_record_ref', 'record.yaml')
    if strict:
        return (
            f'Experiment-rigor belief update for {experiment} ({tier} tier). '
            f'The full typed record, results, and provenance are in the linked, '
            f'hash-pinned record at {ref} -- this strict envelope carries only the link.'
        )
    updates = record.get('updates') if isinstance(record.get('updates'), dict) else {}
    prior = updates.get('prior') if isinstance(updates.get('prior'), dict) else {}
    posterior = updates.get('posterior') if isinstance(updates.get('posterior'), dict) else {}
    parts: list[str] = [
        f'In dispatch / experiment-rigor work, the {experiment} experiment ({tier} tier) '
        f'updates a prior belief.'
    ]
    if prior.get('belief'):
        parts.append(f'Prior: {prior["belief"]} (grade {prior.get("grade", "unstated")}).')
    if posterior.get('belief'):
        parts.append(
            f'Posterior: {posterior["belief"]} '
            f'(grade {posterior.get("grade", "unstated")}, '
            f'method {posterior.get("method", "unstated")}).'
        )
    reasons = updates.get('downgrade_reasons') or []
    if reasons:
        parts.append(f'Certainty is downgraded for: {", ".join(str(r) for r in reasons)}.')
    parts.append(f'The full typed record is at {ref}, hash-pinned by record_sha256.')
    return ' '.join(parts)


def journal_envelope(
    record: dict[str, Any],
    *,
    strict: bool = False,
    record_ref: str = 'record.yaml',
    journaled_at: str | None = None,
    author: str = _DEFAULT_AUTHOR,
    area: str = _DEFAULT_AREA,
    entry_type: str = 'FINDING',
) -> str:
    """Render the record's belief-update as a journaling-sessions envelope.

    PRIMARY (strict=False): the required set plus the update's provenance as extra
    header fields (a superset the tolerant mantis parsers ingest without loss).
    STRICT (strict=True): the required set plus record_ref + record_sha256 only.

    `journaled_at` defaults to the record's own freeze timestamp (else its first-run
    time), so the envelope is DETERMINISTIC -- no wall-clock, re-emit is byte-stable.
    """
    frozen = record.get('plan_frozen_at') if isinstance(record.get('plan_frozen_at'), dict) else {}
    run = record.get('run') if isinstance(record.get('run'), dict) else {}
    occurred_at = _iso(run['first_run_at']) if run.get('first_run_at') else None
    timestamp = _iso(
        journaled_at or frozen.get('timestamp') or occurred_at or '2026-01-01T00:00:00Z'
    )
    sha = record_sha256(record)
    session = f'experiment-rigor-{_slug(record.get("experiment", "experiment"))}'

    # `_record_ref` is a transient hint for _envelope_content only; never a schema field.
    content = _envelope_content({**record, '_record_ref': record_ref}, strict=strict)

    headers: list[tuple[str, str]] = [
        ('type', entry_type),
        ('author', author),
        ('timestamp', str(timestamp)),
    ]
    if occurred_at and str(occurred_at) != str(timestamp):
        headers.append(('occurred_at', str(occurred_at)))
    headers.append(('area', area))
    headers.append(('language', 'en'))
    headers.append(('origin', 'code'))
    headers.append(('session', session))

    if strict:
        # Minimal: the required set (plus occurred_at above) and the hash-pinned link.
        headers.append(('record_ref', record_ref))
        headers.append(('record_sha256', sha))
    else:
        updates = record.get('updates') if isinstance(record.get('updates'), dict) else {}
        prior = updates.get('prior') if isinstance(updates.get('prior'), dict) else {}
        posterior = updates.get('posterior') if isinstance(updates.get('posterior'), dict) else {}
        certainty = updates.get('certainty')
        confidence = _CERTAINTY_CONFIDENCE.get(str(certainty), 0.35)
        headers.append(('visibility', 'private'))
        headers.append(('domains', 'experiment_rigor, dispatch, ab_testing'))
        headers.append(('confidence', f'{confidence}'))
        if prior.get('source'):
            headers.append(('refs', f'record:{record_ref}, prior:{prior["source"]}'))
        else:
            headers.append(('refs', f'record:{record_ref}'))
        # The provenance superset (extra header fields the tolerant parsers ignore).
        headers.append(('experiment', str(record.get('experiment', ''))))
        headers.append(('tier', str(record.get('tier', ''))))
        if certainty is not None:
            headers.append(('certainty', str(certainty)))
        if prior.get('source'):
            headers.append(('prior_source', str(prior['source'])))
        if posterior.get('method'):
            headers.append(('posterior_method', str(posterior['method'])))
        headers.append(('record_ref', record_ref))
        headers.append(('record_sha256', sha))

    lines = ['--- ENTRY_START ---']
    lines += [f'{k}: {v}' for k, v in headers]
    lines.append('--- CONTENT ---')
    lines.append(content)
    lines.append('--- ENTRY_END ---')
    return '\n'.join(lines) + '\n'


# --- the SCHEMA.md generator ------------------------------------------------


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ['| ' + ' | '.join(header) + ' |', '|' + '|'.join(['---'] * len(header)) + '|']
    out += ['| ' + ' | '.join(r) + ' |' for r in rows]
    return out


def schema_markdown(schema: dict[str, Any]) -> str:
    """Generate the human field guide SCHEMA.md from the machine-readable schema.
    Deterministic and ASCII: a sync gate compares this output to templates/SCHEMA.md."""
    tiers = schema['tiers']
    lines: list[str] = []
    lines.append(f'# experiment-rigor record schema (v{schema["schema_version"]})')
    lines.append('')
    lines.append(
        'Generated from templates/schema.json by render.py -- do not edit this file by hand.'
    )
    lines.append('Regenerate it with `python scripts/render.py --schema-md > templates/SCHEMA.md`;')
    lines.append('a sync gate under run_tests.py fails if this file drifts from the schema.')
    lines.append('')

    lines.append('## Tiers')
    lines.append('')
    lines.append(
        'The `tier` field selects the required-field set and which context gates apply: '
        'probe (cheap, refuses a confirmatory verdict or a posterior), measurement (a frozen '
        'pre-registration and a reported CI), and decision (adds the comprehension gate).'
    )
    lines.append('')

    lines.append('## Required and optional fields per tier')
    lines.append('')
    all_fields: list[str] = []
    for tier in tiers:
        for field in schema['required_fields'][tier] + schema.get('optional_fields', {}).get(
            tier, []
        ):
            if field not in all_fields:
                all_fields.append(field)
    rows = []
    for field in all_fields:
        cells = []
        for tier in tiers:
            if field in schema['required_fields'][tier]:
                cells.append('required')
            elif field in schema.get('optional_fields', {}).get(tier, []):
                cells.append('optional')
            else:
                cells.append('-')
        rows.append([f'`{field}`', *cells])
    lines += _table(['Field', *tiers], rows)
    lines.append('')

    lines.append('## Enums')
    lines.append('')
    enum_specs = [
        ('Threat coverage (Q1, closed)', 'threat_enum'),
        ('Threat status', 'threat_status_enum'),
        ('Outcome role', 'role_enum'),
        ('Verdict', 'verdict_enum'),
        ('Confirmatory verdicts (probe-refused)', 'confirmatory_verdicts'),
        ('CI method (no CLT/normal path)', 'ci_methods'),
        ('Certainty (cross-experiment GRADE)', 'certainty_enum'),
    ]
    for title, key in enum_specs:
        lines.append(f'### {title}')
        lines.append('')
        for value in schema[key]:
            lines.append(f'- `{value}`')
        lines.append('')

    lines.append('## Field shapes')
    lines.append('')
    for name in sorted(schema['field_shapes']):
        fields = ', '.join(f'`{f}`' for f in schema['field_shapes'][name])
        lines.append(f'- **{name}**: {fields}')
    lines.append('')

    lines.append('## Pre-registration content (Q4, measurement tier)')
    lines.append('')
    lines.append(
        'The frozen pre-registration maps the eight AsPredicted content questions to record '
        'fields; `decision_rule` is a structured object (`metric`, `comparison`, `threshold`, '
        '`direction`), not prose:'
    )
    lines.append('')
    for field in schema['prereg_fields']:
        lines.append(f'- `{field}`')
    lines.append('')

    lines.append('## Comprehension rubric (Q3, decision tier)')
    lines.append('')
    lines.append(
        'A decision-tier record carries a `comprehension` block: at least two fresh-context '
        'readers, each answering the four Methods-reconstruction questions verbatim with a '
        'resolving `transcript_path`. The block passes only on unanimous four-question '
        'reconstruction by every reader; genuineness of the reads is ceded to review.'
    )
    lines.append('')
    questions = schema['comprehension_questions']
    rows = [
        [f'`{k}`', questions[k]]
        for k in ['manipulated', 'placement', 'operationalization', 'execution_real']
    ]
    lines += _table(['Question key', 'What the reader must recover'], rows)
    lines.append('')

    lines.append('## Rounding and tolerance policy')
    lines.append('')
    lines.append(
        'Record CI bounds are stored rounded to 4 decimal places. The validator recomputes '
        'each interval with stats.py and asserts equality within ATOL = 1e-9 and RTOL = 1e-6 '
        'against those 4-decimal values. Integers and version strings cross-check exactly; '
        '`cost_usd_est` cross-checks within max(1%, $0.01). report.md is serialized under the '
        'canonical policy (sorted keys, LF, repr floats) so a re-render is byte-identical.'
    )
    lines.append('')

    lines.append('## Statistical prior')
    lines.append('')
    prior = schema['prior']
    lines.append(f'Prior: {prior["distribution"]}. {prior["note"]}')
    lines.append('')

    lines.append('## Cross-experiment GRADE update (two-node worked example)')
    lines.append('')
    lines.append(
        'The chain carries a qualitative GRADE update, never pooled counts. Node A (a '
        'measurement experiment) establishes a posterior; node B links back with '
        '`updates.prior.source_id: ../node-a/record.yaml` and records a `certainty` from the '
        'four-level enum plus `downgrade_reasons[]`. `render.py --chain` walks the links into a '
        'root-first lineage view:'
    )
    lines.append('')
    lines.append('```')
    lines.append('1. node-a (measurement)')
    lines.append('2. node-b (decision) -- certainty=moderate, downgrades=[nondeterminism]')
    lines.append('```')
    return '\n'.join(lines) + '\n'


def _load_schema_json() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Derive and drift-check experiment-rigor reports.')
    ap.add_argument('records', nargs='*', help='record.yaml path(s)')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        '--check', action='store_true', help='drift gate over committed report.md pairs'
    )
    mode.add_argument(
        '--chain', action='store_true', help='walk the update chain into a lineage view'
    )
    mode.add_argument(
        '--schema-md', action='store_true', help='print SCHEMA.md generated from schema.json'
    )
    mode.add_argument(
        '--emit-journal',
        action='store_true',
        help='print the record as a mantis journaling-sessions envelope',
    )
    ap.add_argument(
        '--strict',
        action='store_true',
        help='with --emit-journal: the strict linking fallback (no provenance superset)',
    )
    ap.add_argument(
        '--stdout', action='store_true', help='print the report instead of writing report.md'
    )
    args = ap.parse_args(argv)

    if args.schema_md:
        sys.stdout.write(schema_markdown(_load_schema_json()))
        return 0

    if args.emit_journal:
        if not args.records:
            ap.error('a record.yaml path is required for --emit-journal')
        for record_arg in args.records:
            record_path = Path(record_arg)
            record = load_record(record_path)
            sys.stdout.write(
                journal_envelope(record, strict=args.strict, record_ref=record_path.name)
            )
        return 0

    if not args.records:
        ap.error('a record.yaml path is required (unless --schema-md)')

    if args.check:
        # A staged pair passes both members (record.yaml AND report.md); resolve each
        # to its record and dedupe so the pair is checked -- and reported -- once (F3).
        failed = False
        seen: set[Path] = set()
        for check_arg in args.records:
            record_path, _report = resolve_pair(check_arg)
            key = record_path.resolve()
            if key in seen:
                continue
            seen.add(key)
            reason = check_drift(check_arg)
            if reason is None:
                print(f'OK {record_path}')
            else:
                print(f'DRIFT {record_path}: {reason}')
                failed = True
        return 1 if failed else 0

    if args.chain:
        for record_arg in args.records:
            sys.stdout.write(render_chain(record_arg))
        return 0

    for record_arg in args.records:
        record_path = Path(record_arg)
        text = render_report(load_record(record_path))
        if args.stdout:
            sys.stdout.write(text)
        else:
            report = record_path.parent / 'report.md'
            with open(report, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(text)
            print(f'wrote {report}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

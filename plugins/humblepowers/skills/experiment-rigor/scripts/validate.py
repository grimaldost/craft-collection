#!/usr/bin/env python3
"""The experiment-rigor central gate (§2): validate a typed record.yaml.

Every load-bearing rule is a gate that exits non-zero with a stable per-gate error
code and an itemised message (the offending field, and reconciling arithmetic where
one applies). This is the mechanism spine and the home of the standing deletion
rule: a gate that degrades into a section-presence tick is deleted, not tolerated.

Error-code catalog (ERROR_CODES):
  ER-SCHEMA      schema + tier well-formedness (a rate without both numerator and
                 denominator; a missing required field for the tier; an unknown
                 schema_version, the message naming the versions it knows; a bad enum)
  ER-RECON       declared-cells reconciliation: N_expected = sum(design.cells[].planned_n)
                 == disposition total == every outcome's sum of arm denominators
  ER-ANCHOR      temporal anchor: plan_frozen_at.commit exists in git history and
                 predates the earliest run (chronology, not proof of no backdating)
  ER-XCHECK      run cross-check vs the fathom ledger, with the Q5 per-tier hand policy
  ER-STATS       stats integrity: every stated CI recomputes via stats.py within
                 ATOL/RTOL; no CLT/normal below a cell denominator of 30; paired rules
  ER-PARITY      no typed field embedded in a committed report.md contradicts the record
  ER-LINK        updates.prior.source_id resolves to a record
  ER-THREAT      threat coverage over the closed enum (a silent core key fails)
  ER-PROBE       probe refusal: a confirmatory_* verdict or a posterior on a probe
  ER-PREREG      pre-registration consistency: the frozen prereg subset, reconstructed
                 via `git show <plan_frozen_at.commit>:<path>`, has not drifted
  ER-COMPREHEND  decision-tier comprehension block present, resolvable, unanimous
                 (R3-1: reserved and emitted here; §5 extends the fixture side)

Modes:
  validate.py <record.yaml> [more.yaml ...]   full gate, exit 1 on any failure
  validate.py <record.yaml> --schema-only     schema/tier shape only; the context
                                              gates (ER-ANCHOR, ER-XCHECK, ER-PREREG,
                                              ER-COMPREHEND) are skipped AND listed

Depends on PyYAML (the record is nested YAML) and on the sibling stats.py, whose
CI functions this module RECOMPUTES against — it never re-derives the interval math.
Stdlib + PyYAML only; Python 3.13+.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import from_fathom
import stats
import yaml

# --- the code catalog (R3-1 binds ER-COMPREHEND into §2's enumerated set) ----

ERROR_CODES: tuple[str, ...] = (
    'ER-SCHEMA',
    'ER-RECON',
    'ER-ANCHOR',
    'ER-XCHECK',
    'ER-STATS',
    'ER-PARITY',
    'ER-LINK',
    'ER-THREAT',
    'ER-PROBE',
    'ER-PREREG',
    'ER-COMPREHEND',
)

CONTEXT_CODES: tuple[str, ...] = ('ER-ANCHOR', 'ER-XCHECK', 'ER-PREREG', 'ER-COMPREHEND')

# --- the embedded schema --------------------------------------------------
#
# schema.json is a §3 deliverable and, per ADR-0007, the canonical machine-readable
# field list once it exists. §2 must be buildable and testable BEFORE §3, so this
# module carries the schema inline and `load_schema` prefers an on-disk
# templates/schema.json when present, falling back to this embedded copy otherwise.
# §3, when it authors schema.json, should shape it to expose these keys and add a
# sync test asserting the two agree (the same discipline as the schema.json<->SCHEMA.md
# sync gate). No rework to this module is required — it already reads schema.json first.

_EMBEDDED_SCHEMA: dict[str, Any] = {
    'known_versions': [1],
    'tiers': ['probe', 'measurement', 'decision'],
    'required_fields': {
        'probe': ['schema_version', 'tier', 'experiment', 'design', 'outcomes', 'threats'],
        'measurement': [
            'schema_version',
            'tier',
            'experiment',
            'design',
            'outcomes',
            'threats',
            'analysis_plan',
        ],
        'decision': [
            'schema_version',
            'tier',
            'experiment',
            'design',
            'outcomes',
            'threats',
            'analysis_plan',
        ],
    },
    'threat_enum': [
        'contamination_familiarity',
        'prompt_format_sensitivity',
        'judge_bias',
        'model_version_drift',
        'nondeterminism',
        'construct_validity_proxy',
        'token_length_confound',
        'selection_exclusion',
        'generalization',
    ],
    'threat_status_enum': ['controlled', 'residual'],
    'role_enum': ['confirmatory', 'exploratory'],
    'verdict_enum': [
        'confirmatory_supported',
        'confirmatory_null',
        'exploratory_signal',
        'inconclusive',
    ],
    'confirmatory_verdicts': ['confirmatory_supported', 'confirmatory_null'],
    'ci_methods': ['wilson', 'clopper_pearson', 'beta_binomial'],
    'certainty_enum': ['high', 'moderate', 'low', 'very_low'],
    'small_n_floor': 30,
}


class SchemaError(Exception):
    """A loaded schema is incomplete or degenerate — raised loudly rather than
    silently weakening a gate (a schema.json that dropped or emptied a key this
    module reads would otherwise disable the gate that reads it)."""


# Keys this module reads; every one must survive a schema.json merge (F8).
_SCHEMA_LIST_KEYS = (
    'known_versions',
    'tiers',
    'threat_enum',
    'threat_status_enum',
    'role_enum',
    'verdict_enum',
    'confirmatory_verdicts',
    'ci_methods',
)


def _assert_schema_complete(schema: dict[str, Any]) -> dict[str, Any]:
    """Loud completeness check: every key validate reads is present and non-degenerate,
    and required_fields covers all three tiers. A partial or hostile schema.json that
    empties a list (e.g. threat_enum: []) or drops a tier fails here, not silently."""
    for key in _SCHEMA_LIST_KEYS:
        value = schema.get(key)
        if not isinstance(value, list) or not value:
            raise SchemaError(
                f'schema key {key!r} must be a non-empty list (got {value!r}); a degenerate '
                'value would silently weaken the gate that reads it'
            )
    if 'small_n_floor' not in schema:
        raise SchemaError("schema is missing 'small_n_floor'")
    rf = schema.get('required_fields')
    if not isinstance(rf, dict):
        raise SchemaError('schema required_fields must be a mapping')
    for tier in schema['tiers']:
        if tier not in rf:
            raise SchemaError(f'schema required_fields is missing tier {tier!r}')
    return schema


def load_schema(override: str | Path | None = None) -> dict[str, Any]:
    """Return the schema. Prefers templates/schema.json (canonical once §3 ships it),
    else the embedded copy. `override` forces a specific path (mainly for tests).
    Whatever is loaded is asserted complete before use (F8)."""
    path: Path | None = None
    if override is not None:
        path = Path(override)
    else:
        candidate = Path(__file__).resolve().parent.parent / 'templates' / 'schema.json'
        if candidate.exists():
            path = candidate
    if path is not None and path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        # Merge over the embedded defaults so a partial schema.json still resolves
        # every key this module reads (forward-compatible with §3's richer file).
        merged = dict(_EMBEDDED_SCHEMA)
        merged.update(data)
        return _assert_schema_complete(merged)
    return _assert_schema_complete(dict(_EMBEDDED_SCHEMA))


# --- results ----------------------------------------------------------------


class Finding(NamedTuple):
    level: str  # 'FAIL' or 'WARN'
    code: str
    message: str


class Report(NamedTuple):
    findings: list[Finding]
    skips: list[tuple[str, str]]  # (code, reason) for gates skipped under --schema-only

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.level == 'FAIL']

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == 'WARN']


def _fail(code: str, message: str) -> Finding:
    return Finding('FAIL', code, message)


def _warn(code: str, message: str) -> Finding:
    return Finding('WARN', code, message)


# --- small helpers ----------------------------------------------------------


def load_record(path: str | Path) -> dict[str, Any]:
    with open(path, encoding='utf-8') as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f'{path}: record must be a YAML mapping')
    return data


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _arms(record: dict) -> list[tuple[str, str, dict]]:
    """Flatten results into (outcome_name, arm_name, arm_dict)."""
    out: list[tuple[str, str, dict]] = []
    results = record.get('results')
    if not isinstance(results, dict):
        return out
    for oname, ores in results.items():
        arms = ores.get('arms') if isinstance(ores, dict) else None
        if isinstance(arms, dict):
            for aname, arm in arms.items():
                if isinstance(arm, dict):
                    out.append((oname, aname, arm))
    return out


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --- git helpers ------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(cwd), *args],  # noqa: S607 - git resolved from PATH
        capture_output=True,
        text=True,
    )


def _commit_in_history(cwd: Path, commit: str) -> bool:
    return _git(cwd, 'rev-parse', '--verify', '--quiet', f'{commit}^{{commit}}').returncode == 0


def _commit_date(cwd: Path, commit: str) -> datetime | None:
    proc = _git(cwd, 'show', '-s', '--format=%cI', commit)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return _parse_dt(proc.stdout.strip())


def _repo_relpath(cwd: Path, path: Path) -> str | None:
    proc = _git(cwd, 'rev-parse', '--show-toplevel')
    if proc.returncode != 0:
        return None
    try:
        return path.resolve().relative_to(Path(proc.stdout.strip()).resolve()).as_posix()
    except ValueError:
        return None


def _show_at(cwd: Path, commit: str, relpath: str) -> dict | None:
    proc = _git(cwd, 'show', f'{commit}:{relpath}')
    if proc.returncode != 0:
        return None
    try:
        data = yaml.safe_load(proc.stdout)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


# --- ledger --------------------------------------------------------------


def _ledger_summary(path: Path) -> dict[str, Any]:
    """Fathom-ledger read for the ER-XCHECK cross-check: cost_usd_est summed over the
    run rows and n as the trial-row count. Delegated to from_fathom.summarize_ledger
    (the authoritative reader, §3) so the real ledger row-shape lives in exactly one
    place; this gate consumes only the two fields the cross-check compares."""
    summary = from_fathom.summarize_ledger(path)
    return {'cost_usd_est': summary.cost_usd_est, 'n': summary.n}


# --- schema-shape gates (run under --schema-only) ---------------------------


def check_schema(record: dict, schema: dict) -> list[Finding]:
    out: list[Finding] = []

    version = record.get('schema_version')
    known = schema['known_versions']
    if version not in known:
        out.append(
            _fail('ER-SCHEMA', f'schema_version {version!r} unknown; known versions: {known}')
        )

    tier = record.get('tier')
    if tier not in schema['tiers']:
        out.append(_fail('ER-SCHEMA', f'tier {tier!r} unknown; allowed: {schema["tiers"]}'))
    else:
        for field in schema['required_fields'][tier]:
            if field not in record:
                out.append(
                    _fail('ER-SCHEMA', f'missing required field {field!r} for tier {tier!r}')
                )

    # Enum well-formedness, plus the Q4 dv_operationalization requirement.
    require_op = record.get('tier') in ('measurement', 'decision')
    for outcome in record.get('outcomes') or []:
        if isinstance(outcome, dict):
            role = outcome.get('role')
            if role is not None and role not in schema['role_enum']:
                out.append(
                    _fail(
                        'ER-SCHEMA',
                        f'outcome {outcome.get("name")!r} role {role!r} not in {schema["role_enum"]}',
                    )
                )
            if require_op and not str(outcome.get('operationalization') or '').strip():
                out.append(
                    _fail(
                        'ER-SCHEMA',
                        f'outcome {outcome.get("name")!r} needs a non-empty operationalization '
                        f'(Q4 dv_operationalization) at the {record.get("tier")} tier',
                    )
                )
    ap = record.get('analysis_plan')
    if (
        isinstance(ap, dict)
        and (m := ap.get('ci_method')) is not None
        and m not in schema['ci_methods']
    ):
        out.append(
            _fail('ER-SCHEMA', f'analysis_plan.ci_method {m!r} not in {schema["ci_methods"]}')
        )
    for oname, ores in (record.get('results') or {}).items():
        if isinstance(ores, dict):
            v = ores.get('verdict')
            if v is not None and v not in schema['verdict_enum']:
                out.append(
                    _fail(
                        'ER-SCHEMA',
                        f'results.{oname}.verdict {v!r} not in {schema["verdict_enum"]}',
                    )
                )

    # A rate must carry both numerator and denominator (the founding-case defect).
    for oname, aname, arm in _arms(record):
        num, den = arm.get('numerator'), arm.get('denominator')
        if not (_is_int(num) and _is_int(den)):
            out.append(
                _fail(
                    'ER-SCHEMA',
                    f'results.{oname}.arms.{aname}: a rate without both a numerator and a '
                    f'denominator (got numerator={num!r}, denominator={den!r})',
                )
            )
        elif not 0 <= num <= den:
            out.append(
                _fail(
                    'ER-SCHEMA', f'results.{oname}.arms.{aname}: numerator {num} out of [0, {den}]'
                )
            )

    # A rate/count reported outside a well-formed arm (F9, N1): rates live under
    # results.<outcome>.arms.<arm> with a numerator and a denominator, never loose at
    # the outcome level — scanned even when arms exist, so a contradicting top-level
    # results.<outcome>.rate cannot hide beside well-formed arms.
    for oname, ores in (record.get('results') or {}).items():
        if not isinstance(ores, dict):
            continue
        stray = [k for k in ('rate', 'numerator', 'denominator') if k in ores]
        if stray:
            out.append(
                _fail(
                    'ER-SCHEMA',
                    f'results.{oname}: {stray} reported outside a well-formed arm; a rate lives '
                    f'under results.{oname}.arms.<arm> with a numerator and a denominator',
                )
            )

    return out


def check_recon(record: dict) -> list[Finding]:
    out: list[Finding] = []
    design = record.get('design')
    cells = design.get('cells') if isinstance(design, dict) else None
    if not isinstance(cells, list) or not cells:
        return out  # schema gate already flags a missing design/cells
    try:
        n_expected = sum(int(c['planned_n']) for c in cells)
    except (KeyError, TypeError, ValueError):
        return [_fail('ER-RECON', 'design.cells[] each need an integer planned_n to reconcile')]

    disp = record.get('disposition')
    if isinstance(disp, dict):
        total = disp.get('total')
        completed, excluded = disp.get('completed'), disp.get('excluded')
        if (
            _is_int(completed)
            and _is_int(excluded)
            and _is_int(total)
            and completed + excluded != total
        ):
            out.append(
                _fail(
                    'ER-RECON',
                    f'disposition.total {total} != completed {completed} + excluded {excluded}',
                )
            )
        if _is_int(total) and total != n_expected:
            out.append(
                _fail(
                    'ER-RECON',
                    f'N_expected = sum(design.cells.planned_n) = {n_expected} != disposition total {total}',
                )
            )

    for oname, ores in (record.get('results') or {}).items():
        arms = ores.get('arms') if isinstance(ores, dict) else None
        if isinstance(arms, dict):
            denoms = [a.get('denominator') for a in arms.values() if isinstance(a, dict)]
            if all(_is_int(d) for d in denoms) and denoms:
                s = sum(denoms)
                if s != n_expected:
                    out.append(
                        _fail(
                            'ER-RECON',
                            f'outcome {oname!r}: sum of arm denominators {s} != N_expected {n_expected}',
                        )
                    )
    return out


def check_stats(record: dict, schema: dict) -> list[Finding]:
    out: list[Finding] = []
    floor = schema['small_n_floor']
    shared = bool((record.get('design') or {}).get('shared_tasks'))
    require_ci = record.get('tier') in ('measurement', 'decision')

    for oname, aname, arm in _arms(record):
        num, den = arm.get('numerator'), arm.get('denominator')
        if not (_is_int(num) and _is_int(den)):
            continue  # malformed counts are the schema gate's concern (ER-SCHEMA)
        ci = arm.get('ci')
        if ci is None:
            # F1: at measurement/decision every reported rate carries a structured CI.
            if require_ci:
                out.append(
                    _fail(
                        'ER-STATS',
                        f'results.{oname}.arms.{aname}: reported {num}/{den} carries no confidence '
                        'interval (measurement/decision requires a structured ci: method, low, high)',
                    )
                )
            continue
        if not isinstance(ci, dict):
            # F5: a prose CI ("about 47% to 91%") is not machine-checkable.
            out.append(
                _fail(
                    'ER-STATS',
                    f'results.{oname}.arms.{aname}: ci must be a structured mapping with method, '
                    f'low, high (got {ci!r})',
                )
            )
            continue
        if require_ci and 'method' not in ci:
            out.append(
                _fail(
                    'ER-STATS',
                    f'results.{oname}.arms.{aname}: ci is missing method (method, low, high required)',
                )
            )
            continue
        method = ci.get('method', 'wilson')
        alpha = ci.get('alpha', 0.05)
        if method not in schema['ci_methods']:
            # F10: a refused method is refused at every denominator; the small-n rule
            # is named only when a denominator below the floor actually applies.
            small_n = (
                f' - and no small-n interval exists for it at denominator {den} < {floor}'
                if den < floor
                else ''
            )
            out.append(
                _fail(
                    'ER-STATS',
                    f'results.{oname}.arms.{aname}: CI method {method!r} is not an allowed method '
                    f'({schema["ci_methods"]}){small_n}',
                )
            )
            continue
        try:
            interval = stats.confidence_interval(num, den, method, alpha)
        except ValueError as exc:
            out.append(
                _fail('ER-STATS', f'results.{oname}.arms.{aname}: CI recompute failed: {exc}')
            )
            continue
        for bound, computed in (('low', interval.low), ('high', interval.high)):
            stated = ci.get(bound)
            if not isinstance(stated, (int, float)):
                out.append(_fail('ER-STATS', f'results.{oname}.arms.{aname}: CI {bound} missing'))
                continue
            recomputed = round(computed, 4)
            if not math.isclose(recomputed, float(stated), abs_tol=stats.ATOL, rel_tol=stats.RTOL):
                out.append(
                    _fail(
                        'ER-STATS',
                        f'results.{oname}.arms.{aname}: stated {method} CI {bound}={stated} != '
                        f'recomputed {recomputed} (from stats.py, {num}/{den})',
                    )
                )

    # Paired declaration (Q2): a between-arm comparison declares paired true/false;
    # when tasks are shared and paired is false, a clustered SE or an explicit reason.
    for oname, ores in (record.get('results') or {}).items():
        if not isinstance(ores, dict):
            continue
        arms = ores.get('arms')
        if not (isinstance(arms, dict) and len(arms) >= 2):
            continue
        paired = ores.get('paired')
        if not isinstance(paired, bool):
            out.append(
                _fail(
                    'ER-STATS',
                    f'outcome {oname!r}: a between-arm comparison must declare paired true/false',
                )
            )
        elif (
            paired is False
            and shared
            and ores.get('clustered_se') is None
            and not ores.get('unclustered_reason')
        ):
            out.append(
                _fail(
                    'ER-STATS',
                    f'outcome {oname!r}: paired:false on a shared-task design needs a '
                    'clustered_se or an explicit unclustered_reason',
                )
            )
    return out


def check_threats(record: dict, schema: dict) -> list[Finding]:
    out: list[Finding] = []
    threats = record.get('threats')
    if not isinstance(threats, dict):
        return out  # schema gate flags a missing threats block
    statuses = schema['threat_status_enum']
    for key in schema['threat_enum']:
        row = threats.get(key)
        if not isinstance(row, dict):
            out.append(_fail('ER-THREAT', f'core threat {key!r} has no row (silence fails)'))
            continue
        if row.get('status') not in statuses:
            out.append(
                _fail('ER-THREAT', f'threat {key!r} status {row.get("status")!r} not in {statuses}')
            )
        if not str(row.get('statement') or '').strip():
            out.append(_fail('ER-THREAT', f'threat {key!r} needs a non-empty statement'))
    for key, row in threats.items():
        if key in schema['threat_enum']:
            continue
        if not key.startswith('custom_'):
            out.append(
                _fail(
                    'ER-THREAT', f'threat key {key!r} is neither a core enum key nor custom_<slug>'
                )
            )
            continue
        if not isinstance(row, dict) or not str(row.get('statement') or '').strip():
            out.append(_fail('ER-THREAT', f'custom threat {key!r} needs a non-empty statement'))
        elif row.get('status') not in statuses:
            out.append(
                _fail(
                    'ER-THREAT',
                    f'custom threat {key!r} status {row.get("status")!r} not in {statuses}',
                )
            )
    return out


def _contains_posterior(node: object) -> bool:
    """True if a `posterior` key appears anywhere in the subtree (F3): a probe cannot
    smuggle a posterior in under updates.prior.posterior or results.<o>.updates.posterior."""
    if isinstance(node, dict):
        return 'posterior' in node or any(_contains_posterior(v) for v in node.values())
    if isinstance(node, list):
        return any(_contains_posterior(v) for v in node)
    return False


def check_probe(record: dict, schema: dict) -> list[Finding]:
    if record.get('tier') != 'probe':
        return []
    out: list[Finding] = []
    confirmatory = set(schema['confirmatory_verdicts'])
    for oname, ores in (record.get('results') or {}).items():
        if isinstance(ores, dict) and ores.get('verdict') in confirmatory:
            out.append(
                _fail(
                    'ER-PROBE',
                    f'probe carries a confirmatory verdict ({ores.get("verdict")!r}) on {oname!r}; '
                    'graduate to the measurement tier before making a confirmatory claim',
                )
            )
    # N2: a probe cannot carry a posterior ANYWHERE in the record — not only under
    # updates/results, but at the root or any other nesting.
    if _contains_posterior(record):
        out.append(
            _fail(
                'ER-PROBE',
                'probe carries a posterior somewhere in the record; graduate to the '
                'measurement tier for a posterior',
            )
        )
    return out


def check_links(record: dict, record_path: Path | None) -> list[Finding]:
    updates = record.get('updates')
    if not isinstance(updates, dict):
        return []
    prior = updates.get('prior')
    if not isinstance(prior, dict):
        return []
    source_id = prior.get('source_id')
    if not source_id:
        return []
    if record_path is None:
        return []
    target = record_path.parent / str(source_id)
    if not target.exists():
        return [
            _fail('ER-LINK', f'updates.prior.source_id {source_id!r} does not resolve to a record')
        ]
    return []


_YAML_FENCE = re.compile(r'```ya?ml\n(.*?)```', re.DOTALL)


def _parity_mismatches(embedded: dict, record: dict, idx: int, prefix: str = '') -> list[Finding]:
    """Report a finding for any embedded key/value that contradicts the record at that
    path. A committed report may embed a subset of the record; the gate only fails on
    an embedded field that disagrees, never on record fields the report omits."""
    out: list[Finding] = []
    for key, value in embedded.items():
        path = f'{prefix}{key}'
        rv = record.get(key) if isinstance(record, dict) else None
        if isinstance(value, dict) and isinstance(rv, dict):
            out += _parity_mismatches(value, rv, idx, prefix=path + '.')
        elif value != rv:
            out.append(
                _fail(
                    'ER-PARITY',
                    f'report.md block #{idx} field {path!r} = {value!r} contradicts record {rv!r}',
                )
            )
    return out


def check_parity(record: dict, record_path: Path | None) -> list[Finding]:
    """The byte-independent half of the drift gate (§2): no typed field embedded in a
    committed report.md contradicts the record it is derived from. Applies only to a
    committed pair — a bare record with no sibling report.md is fine, and a report that
    embeds only a subset of the record is fine. §3's render.py --check owns the
    semantic-digest half; §3 owns the canonical embedding this gate re-parses."""
    if record_path is None:
        return []
    report = record_path.parent / 'report.md'
    if not report.exists():
        return []
    blocks = _YAML_FENCE.findall(report.read_text(encoding='utf-8'))
    if not blocks:
        return [_fail('ER-PARITY', 'committed report.md carries no embedded ```yaml typed block')]
    out: list[Finding] = []
    for i, block in enumerate(blocks):
        try:
            parsed = yaml.safe_load(block)
        except yaml.YAMLError as exc:
            out.append(
                _fail('ER-PARITY', f'report.md embedded block #{i} is not valid YAML: {exc}')
            )
            continue
        if isinstance(parsed, dict):
            out += _parity_mismatches(parsed, record, i)
    return out


# --- context gates (skipped and listed under --schema-only) -----------------


def check_anchor(record: dict, record_path: Path | None) -> list[Finding]:
    if record.get('tier') not in ('measurement', 'decision') or record_path is None:
        return []
    cwd = record_path.parent
    commit = (record.get('plan_frozen_at') or {}).get('commit')
    if not commit or str(commit) in ('TBD', 'PENDING', 'tbd', 'pending'):
        return [
            _fail('ER-ANCHOR', 'plan_frozen_at.commit is absent; the freeze has no temporal anchor')
        ]
    if not _commit_in_history(cwd, str(commit)):
        return [_fail('ER-ANCHOR', f'plan_frozen_at.commit {commit} is absent from git history')]
    cdate = _commit_date(cwd, str(commit))
    first_run = (record.get('run') or {}).get('first_run_at')
    if cdate is not None and first_run and cdate > _parse_dt(first_run):
        return [
            _fail(
                'ER-ANCHOR',
                f'plan_frozen_at.commit ({cdate.date()}) postdates the earliest run ({first_run}); '
                'the goalpost moved after the run began',
            )
        ]
    return []


def check_xcheck(record: dict, record_path: Path | None) -> list[Finding]:
    tier = record.get('tier')
    run = record.get('run') if isinstance(record.get('run'), dict) else {}
    ledger_path = run.get('ledger_path')

    if ledger_path:
        if record_path is None:
            return []
        lpath = record_path.parent / str(ledger_path)
        if not lpath.exists():
            return [_fail('ER-XCHECK', f'run.ledger_path {ledger_path!r} does not resolve')]
        summary = _ledger_summary(lpath)
        out: list[Finding] = []
        stated_n = run.get('n')
        if _is_int(stated_n) and stated_n != summary['n']:
            out.append(
                _fail('ER-XCHECK', f'run.n {stated_n} != ledger trial-row count {summary["n"]}')
            )
        stated_cost, ledger_cost = run.get('cost_usd_est'), summary['cost_usd_est']
        if isinstance(stated_cost, (int, float)) and isinstance(ledger_cost, (int, float)):
            tol = max(0.01, 0.01 * abs(ledger_cost))
            if abs(stated_cost - ledger_cost) > tol:
                out.append(
                    _fail(
                        'ER-XCHECK',
                        f'run.cost_usd_est {stated_cost} diverges from ledger {ledger_cost} '
                        f'beyond max(1%, $0.01) = {tol:.4f}',
                    )
                )
        return out

    # No ledger: the Q5 per-tier source:hand policy.
    if tier == 'probe':
        return []
    if tier == 'measurement':
        reason = '' if run.get('hand_reason') else ' (declare run.hand_reason)'
        return [
            _warn(
                'ER-XCHECK',
                f'source:hand at measurement tier{reason}; the frozen plan must carry the task and '
                'verifier fixtures so the run is reconstructible',
            )
        ]
    if tier == 'decision':
        if run.get('attestation'):
            return []
        return [
            _fail(
                'ER-XCHECK',
                'decision-tier run has no ledger and no named second-party attestation (run.attestation)',
            )
        ]
    return []


_PREREG_SCALARS = ('name', 'role', 'operationalization')


def _outcomes_by_name(record: dict) -> dict[str, dict]:
    return {
        o['name']: o for o in (record.get('outcomes') or []) if isinstance(o, dict) and 'name' in o
    }


def _plan_without_amendments(plan: object) -> object:
    if isinstance(plan, dict):
        return {k: v for k, v in plan.items() if k != 'amendments'}
    return plan


def _check_amendments(record: dict, cwd: Path) -> list[Finding]:
    """Each analysis_plan.amendments[] entry must be frozen in history and predate the
    first run of the wave it governs (F6). The reference is the amendment's own
    governs_first_run_at when given, else the experiment's run.first_run_at."""
    out: list[Finding] = []
    amendments = (record.get('analysis_plan') or {}).get('amendments') or []
    experiment_first_run = (record.get('run') or {}).get('first_run_at')
    for i, amd in enumerate(amendments):
        if not isinstance(amd, dict):
            out.append(_fail('ER-PREREG', f'amendment[{i}] is malformed'))
            continue
        commit = amd.get('commit')
        if not commit or not _commit_in_history(cwd, str(commit)):
            out.append(
                _fail('ER-PREREG', f'amendment[{i}] commit {commit!r} is absent from git history')
            )
            continue
        reference = amd.get('governs_first_run_at') or experiment_first_run
        if not reference:
            continue
        ref_dt = _parse_dt(reference)
        cdate = _commit_date(cwd, str(commit))
        if cdate is not None and cdate > ref_dt:
            out.append(
                _fail(
                    'ER-PREREG',
                    f'amendment[{i}] commit ({cdate.date()}) postdates the first run of the wave '
                    f'it governs ({reference})',
                )
            )
        ts = amd.get('timestamp')
        if ts and _parse_dt(ts) > ref_dt:
            out.append(
                _fail(
                    'ER-PREREG',
                    f'amendment[{i}] timestamp ({ts}) postdates the first run of the wave it '
                    f'governs ({reference})',
                )
            )
    return out


def check_prereg(record: dict, record_path: Path | None) -> list[Finding]:
    tier = record.get('tier')
    if tier not in ('measurement', 'decision') or record_path is None:
        return []
    cwd = record_path.parent
    commit = (record.get('plan_frozen_at') or {}).get('commit')

    def downgrade(msg: str) -> list[Finding]:
        # Q5 hand ladder: measurement WARN + reason, decision FAIL.
        maker = _warn if tier == 'measurement' else _fail
        return [maker('ER-PREREG', msg)]

    if not commit or str(commit) in ('TBD', 'PENDING', 'tbd', 'pending'):
        return downgrade(
            'plan_frozen_at.commit is absent; cannot reconstruct the frozen pre-registration'
        )
    relpath = _repo_relpath(cwd, record_path)
    if relpath is None:
        return downgrade(
            'record is not under a git repo; cannot reconstruct the frozen pre-registration'
        )
    frozen = _show_at(cwd, str(commit), relpath)
    if frozen is None:
        return downgrade(
            f'record not in history at {commit}:{relpath}; cannot reconstruct pre-registration'
        )

    out: list[Finding] = []
    # design.cells compared as a whole subtree; analysis_plan compared WITHOUT its
    # amendments[] (F6) — amendments are legitimate post-freeze additions and get
    # their own per-amendment chronology check below, not a wholesale drift flag.
    if (record.get('design') or {}).get('cells') != (frozen.get('design') or {}).get('cells'):
        out.append(_fail('ER-PREREG', 'design.cells drifted from the frozen pre-registration'))
    if _plan_without_amendments(record.get('analysis_plan')) != _plan_without_amendments(
        frozen.get('analysis_plan')
    ):
        out.append(
            _fail('ER-PREREG', 'analysis_plan (excluding amendments) drifted from the frozen plan')
        )

    cur_out, frz_out = _outcomes_by_name(record), _outcomes_by_name(frozen)
    for name, frz in frz_out.items():
        cur = cur_out.get(name)
        if cur is None:
            out.append(
                _fail('ER-PREREG', f'frozen outcome {name!r} is missing from the analyzed record')
            )
            continue
        for field in _PREREG_SCALARS:
            if cur.get(field) != frz.get(field):
                out.append(
                    _fail(
                        'ER-PREREG',
                        f'outcome {name!r} field {field!r} drifted: frozen {frz.get(field)!r} -> {cur.get(field)!r}',
                    )
                )
        if (cur.get('verifier') or {}).get('hash') != (frz.get('verifier') or {}).get('hash'):
            out.append(
                _fail('ER-PREREG', f'outcome {name!r} verifier.hash drifted from the frozen plan')
            )

    # F7: any outcome added after the freeze must be quarantined — added_after_freeze:
    # true AND role: exploratory — regardless of what verdict it carries.
    for name, cur in cur_out.items():
        if name in frz_out:
            continue
        if cur.get('added_after_freeze') is not True or cur.get('role') != 'exploratory':
            out.append(
                _fail(
                    'ER-PREREG',
                    f'outcome {name!r} was added after the freeze; it must carry '
                    'added_after_freeze: true and role: exploratory (the post-hoc quarantine)',
                )
            )

    # A confirmatory_* verdict is legal only on an outcome frozen as role: confirmatory.
    for oname, ores in (record.get('results') or {}).items():
        if not (
            isinstance(ores, dict)
            and ores.get('verdict') in ('confirmatory_supported', 'confirmatory_null')
        ):
            continue
        frozen_role = (frz_out.get(oname) or {}).get('role')
        if frozen_role != 'confirmatory':
            out.append(
                _fail(
                    'ER-PREREG',
                    f'outcome {oname!r} carries a confirmatory verdict but its frozen role is '
                    f'{frozen_role!r}, not confirmatory',
                )
            )

    # F6: every declared amendment's commit is in history AND predates the first run of
    # the wave it governs (governs_first_run_at, else the experiment's first run).
    out += _check_amendments(record, cwd)
    return out


_COMPREHENSION_QUESTIONS = ('manipulated', 'placement', 'operationalization', 'execution_real')


def check_comprehend(record: dict, record_path: Path | None) -> list[Finding]:
    if record.get('tier') != 'decision':
        return []
    comp = record.get('comprehension')
    if not isinstance(comp, dict):
        return [_fail('ER-COMPREHEND', 'decision-tier record needs a comprehension block')]
    readers = comp.get('readers')
    if not isinstance(readers, list) or len(readers) < 2:
        return [_fail('ER-COMPREHEND', 'comprehension needs at least 2 fresh-context readers')]

    out: list[Finding] = []
    unanimous = True
    for i, reader in enumerate(readers):
        if not isinstance(reader, dict):
            out.append(_fail('ER-COMPREHEND', f'reader[{i}] is malformed'))
            unanimous = False
            continue
        tpath = reader.get('transcript_path')
        # F4: the transcript must be an actual file, not merely an existing path (a
        # directory named like a transcript is not a read).
        if not tpath or (
            record_path is not None and not (record_path.parent / str(tpath)).is_file()
        ):
            out.append(
                _fail(
                    'ER-COMPREHEND',
                    f'reader[{i}] transcript_path {tpath!r} does not resolve to a file',
                )
            )
        correct = reader.get('correct') or {}
        if not all(correct.get(q) is True for q in _COMPREHENSION_QUESTIONS):
            unanimous = False
    if not unanimous:
        out.append(
            _fail(
                'ER-COMPREHEND',
                'comprehension pass requires unanimous four-question reconstruction by every reader',
            )
        )
    if comp.get('pass') is not True:
        out.append(
            _fail('ER-COMPREHEND', 'comprehension.pass must hold for a decision-tier record')
        )
    return out


# --- orchestration ----------------------------------------------------------


def run_checks(
    record: dict,
    record_path: str | Path | None = None,
    *,
    schema_only: bool = False,
    schema: dict | None = None,
) -> Report:
    schema = schema or load_schema()
    path = Path(record_path) if record_path is not None else None
    findings: list[Finding] = []

    findings += check_schema(record, schema)
    findings += check_recon(record)
    findings += check_stats(record, schema)
    findings += check_threats(record, schema)
    findings += check_probe(record, schema)
    findings += check_links(record, path)
    findings += check_parity(record, path)

    skips: list[tuple[str, str]] = []
    if schema_only:
        skips = [(code, 'context gate skipped under --schema-only') for code in CONTEXT_CODES]
    else:
        findings += check_anchor(record, path)
        findings += check_xcheck(record, path)
        findings += check_prereg(record, path)
        findings += check_comprehend(record, path)

    return Report(findings, skips)


def _emit(path: Path, report: Report) -> None:
    print(f'== {path} ==')
    for f in report.findings:
        prefix = f.code if f.level == 'FAIL' else f'WARN [{f.code}]'
        print(f'{prefix}: {f.message}')
    for code, reason in report.skips:
        print(f'SKIP {code}: {reason}')
    if not report.failures:
        print('OK' if not report.warnings else f'OK ({len(report.warnings)} warning(s))')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Validate an experiment-rigor record.yaml.')
    ap.add_argument('records', nargs='+', help='record.yaml path(s)')
    ap.add_argument('--schema-only', action='store_true', help='schema/tier shape checks only')
    ap.add_argument('--schema', help='override the schema.json path (mainly for tests)')
    args = ap.parse_args(argv)

    schema = load_schema(args.schema)
    failed = False
    for record_arg in args.records:
        path = Path(record_arg)
        try:
            record = load_record(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f'== {path} ==')
            print(f'ER-SCHEMA: could not load record: {exc}')
            failed = True
            continue
        report = run_checks(record, path, schema_only=args.schema_only, schema=schema)
        _emit(path, report)
        failed = failed or bool(report.failures)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

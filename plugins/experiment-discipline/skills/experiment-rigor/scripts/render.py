#!/usr/bin/env python3
"""Report derivation and the drift gate for experiment-rigor (spec section 3).

The record.yaml is the single source of truth; report.md is derived and never
hand-edited. This module derives report.md, checks a committed report against its
record for drift, walks the cross-experiment update chain, generates the human
field guide SCHEMA.md from the machine-readable templates/schema.json, and emits
(and verifies) the activation line that opens a work product.

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

A derived report opens with the generated activation line (when the caller passes the
record's path) and carries, for every block the record actually has, the contrast table
with its achieved precision on the clustered scale, the 2x2 state breakdown including
the line-only rate, the descriptive turn/cost tax, and the pre-committed interpretation
the data selected with the precondition a rollout still owes. Each section is emitted
only when its block exists -- a record without contrasts gets no empty scaffolding --
because the drift gate digests the embedded YAML alone and would not notice prose that
went stale or prose that was never derived at all.

Depends on PyYAML; stdlib otherwise. Python 3.13+. Nothing here recomputes a
statistic: every number in a derived line is read from the record, and validate.py's
ER-STATS is what holds the record's numbers to the counts behind them.
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


def _rate_line(oname: str, aname: str, arm: dict, *, descriptive: bool = False) -> str:
    num, den = arm.get('numerator'), arm.get('denominator')
    ci = arm.get('ci') if isinstance(arm.get('ci'), dict) else None
    frac = f'{num}/{den}' if num is not None and den is not None else '(no rate)'
    if ci and isinstance(ci.get('low'), (int, float)) and isinstance(ci.get('high'), (int, float)):
        method = ci.get('method', 'wilson')
        span = f'{method} CI [{ci["low"]}, {ci["high"]}]'
        # Schema v1.1: once the outcome states a paired contrast, the per-arm interval
        # is an UPPER BOUND on precision (it prices independent trials on a design whose
        # unit is the prompt cluster) and the headline number is the contrast's. The
        # demotion is written into the derived line rather than left to the reader.
        if descriptive:
            span += ' (descriptive; headline precision is the contrast below)'
    else:
        span = 'no CI'
    return f'- {oname} / {aname}: {frac}, {span}'


def _contrast_line(oname: str, contrast: dict) -> str:
    """One derived line per stated contrast: the paired estimate, its t-interval, and
    the sign test that rides beside it as the distribution-free bound.

    Every number here is READ from the record, never recomputed. The record is the
    source and validate.py's ER-STATS is what holds each of these values to the
    clusters block; a second derivation in the renderer would be a second answer with
    nothing reconciling the two. It also keeps the prose and the embedded typed block
    quoting one number, so a hand-edit to either is drift the gates see.
    """
    name = contrast.get('name', '(unnamed)')
    arms = contrast.get('arms') if isinstance(contrast.get('arms'), list) else []
    pair = ' - '.join(str(a) for a in arms) if len(arms) == 2 else '(no arm pair)'
    parts = [f'- {oname} / {name} ({pair}): {contrast.get("estimator", "(no estimator)")}']
    parts.append(f'estimate={contrast.get("estimate")}, se={contrast.get("se")}')
    parts.append(f'{contrast.get("n_clusters")} cluster(s)')
    interval = contrast.get('interval')
    if isinstance(interval, dict):
        parts.append(
            f'{interval.get("method", "paired_t")} CI [{interval["low"]}, {interval["high"]}]'
        )
    signs = contrast.get('sign_test')
    if isinstance(signs, dict):
        parts.append(
            f'sign test p={signs.get("p_value")} on {signs.get("effective_n")} effective '
            f'cluster(s), {signs.get("positive")} positive'
        )
    return ', '.join(parts)


def _num(value: Any) -> str:
    """A number as the record spells it, or a placeholder. Never rounded here: the
    record's own value is the one the gates checked."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return '(none)'
    return f'{value}'


def _cell(text: Any) -> str:
    """One free-text table cell. A pipe or a newline inside a record value would break the
    row it lands in, so both are neutralized here rather than trusted not to appear."""
    return str(text).replace('|', '\\|').replace('\n', ' ').strip() or '-'


def _half_width(interval: Any) -> str:
    """The achieved precision of a stated interval: half its width, on the clustered
    scale. Arithmetic on the two bounds the record states -- not a re-derivation from
    the cluster block, which is ER-STATS's job."""
    if not isinstance(interval, dict):
        return '(none)'
    low, high = interval.get('low'), interval.get('high')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (low, high)):
        return '(none)'
    return f'+/- {round((float(high) - float(low)) / 2, 4)}'


def _block_outcome(key: str, block: dict[str, Any]) -> str:
    """Which declared outcome a results block speaks for. A block that scopes one contrast
    pair says so in `outcome`; a block that IS the outcome is named by its key."""
    declared = block.get('outcome')
    return str(declared) if isinstance(declared, str) and declared.strip() else str(key)


def _contrast_rows(record: dict[str, Any]) -> list[list[str]]:
    """One table row per stated contrast, across every result block, in record order.

    Every cell is QUOTED from the record (PR04's convention): the estimate, the SE, the
    interval and the sign test are the values validate.py's ER-STATS recomputed from the
    cluster block, so the table and the embedded block cannot say two different things.
    The trailing note column carries whatever label the record put on the row -- the A/A
    calibration names itself the noise floor there rather than the renderer knowing which
    contrast is one.
    """
    rows: list[list[str]] = []
    for oname, ores in (record.get('results') or {}).items():
        if not isinstance(ores, dict):
            continue
        contrasts = ores.get('contrasts')
        if not isinstance(contrasts, list):
            continue
        for contrast in contrasts:
            if not isinstance(contrast, dict):
                continue
            arms = contrast.get('arms') if isinstance(contrast.get('arms'), list) else []
            pair = ' - '.join(str(a) for a in arms) if len(arms) == 2 else '(no arm pair)'
            interval = (
                contrast.get('interval') if isinstance(contrast.get('interval'), dict) else {}
            )
            band = (
                f'[{_num(interval.get("low"))}, {_num(interval.get("high"))}]'
                if interval
                else '(none)'
            )
            signs = contrast.get('sign_test') if isinstance(contrast.get('sign_test'), dict) else {}
            sign_cell = (
                f'p={_num(signs.get("p_value"))}, {_num(signs.get("positive"))}/'
                f'{_num(signs.get("effective_n"))} positive'
                if signs
                else '(none)'
            )
            note = str(contrast.get('note') or '').strip()
            role = str(contrast.get('role') or '').strip()
            movement = contrast.get('moved')
            rows.append(
                [
                    _cell(_block_outcome(oname, ores)),
                    _cell(ores.get('class_scope') or 'all'),
                    _cell(contrast.get('name', '(unnamed)')),
                    _cell(pair),
                    _cell(role),
                    _num(contrast.get('estimate')),
                    _num(contrast.get('se')),
                    band,
                    _half_width(interval),
                    sign_cell,
                    _num(contrast.get('n_clusters')),
                    'yes' if movement is True else ('no' if movement is False else '-'),
                    _cell(note),
                ]
            )
    return rows


def _primary_precision(record: dict[str, Any]) -> str | None:
    """The achieved precision line for the contrast the frozen plan named primary.

    The plan names it (`analysis_plan.primary_contrast`), so the renderer does not have
    to know which row that is; a record without a named primary gets no line rather than
    an empty one."""
    plan = record.get('analysis_plan')
    named = plan.get('primary_contrast') if isinstance(plan, dict) else None
    if not isinstance(named, dict):
        return None
    want_name, want_outcome = named.get('name'), named.get('outcome')
    for oname, ores in (record.get('results') or {}).items():
        # Match on the DECLARED outcome: a pair-scoped block lives under its own key and
        # names the outcome it belongs to, so the plan's `outcome` still resolves.
        if not isinstance(ores, dict) or (
            want_outcome and _block_outcome(oname, ores) != want_outcome
        ):
            continue
        for contrast in ores.get('contrasts') or []:
            if not isinstance(contrast, dict) or contrast.get('name') != want_name:
                continue
            interval = (
                contrast.get('interval') if isinstance(contrast.get('interval'), dict) else {}
            )
            threshold = (plan.get('decision_rule') or {}).get('threshold')
            tail = f', declared MEWD {threshold}' if threshold is not None else ''
            return (
                f'- Achieved precision (clustered scale): '
                f'{_block_outcome(oname, ores)} / {want_name} '
                f'{_half_width(interval)} on {_num(contrast.get("n_clusters"))} cluster(s) at '
                f'alpha {_num(interval.get("alpha"))}{tail}'
            )
    return None


def _state_rows(record: dict[str, Any]) -> list[list[str]]:
    """The 2x2 state breakdown, arm by arm and class by class, with the line-only rate
    as its own column -- the first-class number the outcome exists to make visible."""
    block = record.get('state_breakdown')
    arms = block.get('arms') if isinstance(block, dict) else None
    if not isinstance(arms, dict):
        return []
    rows: list[list[str]] = []
    for aname, per_class in arms.items():
        if not isinstance(per_class, dict):
            continue
        for cname, counts in per_class.items():
            if not isinstance(counts, dict):
                continue
            rows.append(
                [
                    _cell(aname),
                    _cell(cname),
                    _num(counts.get('scored')),
                    _num(counts.get('both')),
                    _num(counts.get('line_only')),
                    _num(counts.get('skeleton_only')),
                    _num(counts.get('neither')),
                    _num(counts.get('line_only_rate')),
                ]
            )
    return rows


def _economy_rows(record: dict[str, Any]) -> list[list[str]]:
    """The descriptive turn and cost tax per arm. Descriptive: no interval is quoted on
    it and no contrast rests on it."""
    block = record.get('run_economy')
    per_arm = block.get('per_arm') if isinstance(block, dict) else None
    if not isinstance(per_arm, dict):
        return []
    return [
        [
            _cell(aname),
            _num(row.get('runs')),
            _num(row.get('mean_turns')),
            _num(row.get('total_cost_usd')),
            _num(row.get('mean_cost_usd')),
        ]
        for aname, row in per_arm.items()
        if isinstance(row, dict)
    ]


def _interpretation_lines(record: dict[str, Any]) -> list[str]:
    """The pre-committed interpretation the data selected, plus the precondition any
    production rollout of a row still owes. Both are RECORD fields -- finalize selects
    the leg mechanically and writes it down; the renderer quotes it."""
    conclusion = record.get('conclusion')
    if not isinstance(conclusion, dict) or not conclusion.get('interpretation'):
        return []
    lines = ['## Interpretation (pre-committed; selected mechanically)', '']
    lines.append(f'- Selected: `{conclusion.get("interpretation")}`')
    for label, key in (
        ('Condition', 'condition'),
        ('Read', 'read'),
        ('Basis', 'basis'),
    ):
        value = str(conclusion.get(key) or '').strip()
        if value:
            lines.append(f'- {label}: {value}')
    # The frozen word "alike" qualifies the second leg, and where it does not hold the
    # leg's own "the content is irrelevant" sentence is SUPPRESSED rather than quoted --
    # `read` above already carries the qualified text, so nothing here restates it.
    if conclusion.get('alike') is False and conclusion.get('frozen_read_suppressed'):
        lines.append(
            '- Alike: NO. The leg is still the pre-committed cell, but its own reading is '
            'suppressed on this data (Read above is the qualified one; the suppressed text '
            'stays in the record as `frozen_read_suppressed`).'
        )
    alike_basis = str(conclusion.get('alike_basis') or '').strip()
    if alike_basis and conclusion.get('interpretation') == 'preamble_only':
        lines.append(f'- Alike basis: {alike_basis}')
    # The frozen null leg's own text states the no-headroom rule conditionally, so a reader
    # meets the words "NO HEADROOM" whichever way the data fell. Resolve it here, both ways:
    # a null WITH room is the stronger finding and must not be left looking like the weaker one.
    if conclusion.get('no_headroom') is True:
        lines.append(
            '- Recorded as NO HEADROOM, not as no effect: control sits at or near ceiling '
            'on the genuine half, so the instrument had nowhere to move.'
        )
    elif conclusion.get('no_headroom') is False and conclusion.get('headroom') is not None:
        lines.append(
            f'- Headroom: the no-headroom qualifier does NOT apply. Control sits at '
            f'{_num(conclusion.get("control_genuine_rate"))} on the genuine half, leaving '
            f'{_num(conclusion.get("headroom"))} of room. The instrument had room to move '
            f'and did not, which is the stronger reading of a null, not the weaker one.'
        )
    if conclusion.get('instrument_noise') is True:
        lines.append(
            f'- INSTRUMENT NOISE: {conclusion.get("instrument_noise_note", "the A/A moved")}'
        )
    precondition = str(conclusion.get('rollout_precondition') or '').strip()
    if precondition:
        lines.append(f'- Precondition for any production rollout of a row: {precondition}')
    lines.append('')
    return lines


def _derived_sections(record: dict[str, Any]) -> list[str]:
    """The derived tables. Each one is emitted only when the record carries the block
    behind it -- a record with no contrasts gets no empty scaffolding, which is what
    keeps one shared renderer usable by every tier."""
    lines: list[str] = []
    rows = _contrast_rows(record)
    if rows:
        lines.append('## Contrasts (paired, on the clustered scale)')
        lines.append('')
        lines += _table(
            [
                'outcome',
                'scope',
                'contrast',
                'arms',
                'role',
                'estimate',
                'se',
                'interval',
                'half-width',
                'sign test',
                'clusters',
                'moved',
                'note',
            ],
            rows,
        )
        lines.append('')
        precision = _primary_precision(record)
        if precision is not None:
            lines.append(precision)
            lines.append('')
    states = _state_rows(record)
    if states:
        lines.append('## 2x2 states by arm (the line-only rate is first-class)')
        lines.append('')
        lines += _table(
            [
                'arm',
                'class',
                'scored',
                'both',
                'line_only',
                'skeleton_only',
                'neither',
                'line-only rate',
            ],
            states,
        )
        lines.append('')
    economy = _economy_rows(record)
    if economy:
        lines.append('## Turn and cost tax (descriptive)')
        lines.append('')
        lines += _table(['arm', 'runs', 'mean turns', 'total USD', 'mean USD'], economy)
        lines.append('')
    lines += _interpretation_lines(record)
    return lines


def _leading_activation_line(record: dict[str, Any], record_path: str | Path | None) -> list[str]:
    """The line that opens the work product, GENERATED from the record's own tier and
    path (section 3) rather than typed here, so the report cannot claim a coordinate the
    record does not have.

    Emitted at probe and above only: tier-0 `check` names no artifact, and a record whose
    file is not on disk (an in-memory render) has no path to name.
    """
    if record_path is None or str(record.get('tier') or '') in ('', 'check'):
        return []
    try:
        return [record_activation_line(record_path), '']
    except (OSError, ValueError):
        return []


def render_report(record: dict[str, Any], record_path: str | Path | None = None) -> str:
    """Derive the report.md text for a record. Exactly one fenced YAML block -- the
    canonical record -- is embedded; everything else is derived human prose the drift
    gate ignores.

    `record_path` is optional and only ever adds prose: with it the report opens with
    the generated activation line naming the record. The drift digest reads the embedded
    block alone, so the line is invisible to `--check` -- which is exactly why every
    caller that writes a report.md passes the path.
    """
    experiment = record.get('experiment', '(unnamed)')
    tier = record.get('tier', '(no tier)')
    lines: list[str] = _leading_activation_line(record, record_path)
    lines += [f'# Experiment: {experiment} ({tier} tier)', '']
    lines.append('_Derived from record.yaml by render.py -- do not hand-edit._')
    lines.append('')

    design = record.get('design') or {}
    cells = design.get('cells') if isinstance(design, dict) else None
    if isinstance(cells, list) and cells:
        amended = _amended_planned_n(design)
        parts = []
        for c in cells:
            if not isinstance(c, dict):
                continue
            name, frozen_n = c.get('name'), c.get('planned_n')
            now_n = amended.get(str(name), frozen_n)
            parts.append(
                f'{name}={frozen_n}'
                if now_n == frozen_n
                else f'{name}={frozen_n}->{now_n} (amended)'
            )
        planned = ', '.join(parts)
        lines.append(
            f'- Design: {len(cells)} cell(s) ({planned}); shared_tasks={design.get("shared_tasks")}'
        )
        for amd in design.get('amendments') or []:
            if isinstance(amd, dict):
                lines.append(
                    f'  - amended at {amd.get("commit", "?")[:12]} ({amd.get("timestamp", "?")}): '
                    f'{amd.get("scope", "")}'
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
            contrasts = ores.get('contrasts')
            has_contrasts = isinstance(contrasts, list) and bool(contrasts)
            for aname, arm in (ores.get('arms') or {}).items():
                if isinstance(arm, dict):
                    lines.append('  ' + _rate_line(oname, aname, arm, descriptive=has_contrasts))
            if has_contrasts:
                for contrast in contrasts:
                    if isinstance(contrast, dict):
                        lines.append('  ' + _contrast_line(oname, contrast))

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
    lines += _derived_sections(record)
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
    # No record_path here on purpose: the digest covers the embedded block alone, so the
    # leading activation line would only be built, thrown away, and -- for a record
    # outside a repository -- print a portability note the gate has no reason to emit.
    fresh = _embedded_blocks(render_report(record))
    if _digest(committed) != _digest(fresh):
        return 'report.md embedded block drifted from record.yaml (regenerate with render.py)'
    return None


# --- the activation line ----------------------------------------------------
#
# Whenever the frame engages, one austere line opens the work product. At probe and
# above it names the record behind the claim and is GENERATED here rather than typed:
# --activation-line prints the canonical line for a record, --check-activation-line
# verifies a pasted line against that record, and both build through activation_line()
# so the format string exists once. A line whose tier or path disagrees with the record
# is a drifted claim and exits 1.
#
# At tier-0 (`check`) the artifact reference is the literal `inline` -- nothing resolves
# it, so that rung's line is review-only and no generator emits it.
#
# The format is pure ASCII ('|' and '->'): these literals are runtime-reachable under
# the ASCII ratchet, which is why the generated form carries no glyph.

_ACTIVATION_RE = re.compile(r'^\[experiment-rigor \| (?P<tier>[^|\]]+?) -> (?P<artifact>[^\]]+)\]$')


def activation_line(tier: str, artifact: str) -> str:
    """Build the canonical activation line. The one place the format lives."""
    return f'[experiment-rigor | {tier} -> {artifact}]'


def _repo_root(start: Path) -> Path | None:
    """The nearest ancestor holding a `.git` entry (a directory in a clone, a file in
    a worktree), or None outside a repository."""
    for parent in [start, *start.parents]:
        if (parent / '.git').exists():
            return parent
    return None


def artifact_ref(record_path: str | Path) -> str:
    """How the line names a record. INSIDE a repository: the path relative to the
    repository root, POSIX separators -- so the same record yields the same line on
    every machine and checkout, from any working directory. OUTSIDE one there is no
    such anchor, so the RESOLVED ABSOLUTE path is used (CWD-independent, so the line
    still round-trips) and a note goes to stderr: an absolute path is machine-local,
    and a line naming one cannot be checked anywhere else."""
    resolved = Path(record_path).resolve()
    root = _repo_root(resolved.parent)
    if root is not None:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            pass
    print(
        f'{record_path}: outside a git repository; the line names an absolute path '
        'and is not portable',
        file=sys.stderr,
    )
    return resolved.as_posix()


def record_activation_line(record_path: str | Path) -> str:
    """The canonical activation line for a record: its own tier, its own path."""
    record = load_record(record_path)
    tier = record.get('tier')
    if not tier:
        raise ValueError(f'{record_path}: record declares no tier')
    if str(tier) == 'check':
        raise ValueError(
            f'{record_path}: tier-0 `check` names no artifact; its line is written by '
            'hand as `inline`'
        )
    return activation_line(str(tier), artifact_ref(record_path))


def check_activation_line(line: str, record_path: str | Path) -> str | None:
    """Return None when a pasted line agrees with the record, else the disagreement.
    The comparison is exact after strip(): tier and path must both match, so a line
    copied from another experiment -- or kept after the record moved or graduated a
    tier -- is caught rather than believed. A path spelled with Windows separators
    disagrees and is reported as one; the canonical form is POSIX."""
    expected = record_activation_line(record_path)
    pasted = line.strip()
    if pasted == expected:
        return None
    match = _ACTIVATION_RE.match(pasted)
    if match is None:
        return f'not an activation line: {pasted!r} (expected {expected})'
    want = _ACTIVATION_RE.match(expected)
    if want is None:  # a tier or a path carrying the format's own delimiters
        return f'{pasted!r} != {expected!r}'
    want_tier, want_artifact = want['tier'], want['artifact']
    got_tier = match['tier'].strip()
    got_artifact = match['artifact'].strip()
    problems: list[str] = []
    if got_tier != want_tier:
        problems.append(f'tier {got_tier!r} != record tier {want_tier!r}')
    if got_artifact != want_artifact:
        problems.append(f'artifact {got_artifact!r} != record path {want_artifact!r}')
    if not problems:
        problems.append(f'{pasted!r} != {expected!r}')
    return '; '.join(problems)


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


# --- the journal envelope (Q8) -----------------------------------------------
#
# render.py emits the record's belief-update as a journal envelope so the memory
# project's ingestion pipeline can compost it into the long-term store. That project
# is SEALORE: it owns the parser (sealore/src/sealore/ingestion/journal_v2.py) and the
# written contract (sealore/src/sealore/ingestion/ENVELOPE.md). It is not mantis, which
# held the role earlier in the chain cognitive-memory -> cogmem -> mantis -> sealore.
# Two shapes:
#
#   PRIMARY (default) -- the full envelope carrying the update and its provenance as
#   EXTRA header fields (experiment, tier, certainty, ...): a SUPERSET of the required
#   keys. The real parser collects header lines into a dict and consumes only the keys
#   it knows, ignoring the rest; it does not enforce additionalProperties. So the
#   superset ingests without loss.
#
#   STRICT FALLBACK (--strict) -- for a hypothetical parser that DOES reject unknown
#   keys (an additionalProperties:false JSON-schema validator): the required keys only,
#   plus a record_ref path and a record_sha256, no rich-provenance superset. The
#   provenance is not dropped, it is LINKED: the envelope points at the typed record,
#   hash-pinned. test_sealore_fallback.py mocks a rejecting parser and asserts the
#   fallback is well-formed and resolvable (the R2 fold: the fallback shape is defined
#   and tested, not left as prose).
#
# The standing journal contract: field / enum / required-key mismatches fail SILENTLY
# in that pipeline, so the emitter matches the contract exactly -- ISO timestamps, a
# valid entry type, one of the journal origins, and every required key present.

# The required header set. The current parser (v2) requires six: it dropped 'language',
# which the earlier v1 parser demanded. Emitting seven costs nothing and satisfies both,
# so a record rendered today still ingests into an older deployment.
_ENVELOPE_REQUIRED: tuple[str, ...] = (
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
    ISO string into a datetime, whose str() uses a space; the parser tolerates
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
    header fields (a superset sealore's tolerant parser ingests without loss).
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


def _amended_planned_n(design: dict) -> dict[str, int]:
    """Cell name -> planned_n after design.amendments[], latest winning (mirrors validate)."""
    out: dict[str, int] = {}
    for amd in design.get('amendments') or []:
        if not isinstance(amd, dict):
            continue
        for cell in amd.get('cells') or []:
            if isinstance(cell, dict) and 'name' in cell:
                try:
                    out[str(cell['name'])] = int(cell['planned_n'])
                except (KeyError, TypeError, ValueError):
                    continue
    return out


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
        ('Contrast estimator (v1.1, the clustered/paired scale)', 'contrast_estimators'),
        ('Contrast interval method (v1.1)', 'contrast_interval_methods'),
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

    lines.append('## The paired contrast (schema v1.1)')
    lines.append('')
    lines.append(
        'A per-arm interval prices independent trials. When the randomization unit is the '
        'prompt cluster -- the same prompts scored in every arm -- that is the wrong unit, '
        'and recomputing each arm from raw counts forces an independent-trials interval onto '
        'a clustered design. Two additive blocks fix it, and a v1.0 record that carries '
        'neither is unaffected.'
    )
    lines.append('')
    lines.append(
        '`results.<outcome>.clusters` holds, per prompt id and per arm, a `numerator` and a '
        '`denominator`. `results.<outcome>.contrasts[]` states the comparison on that scale: '
        'a `name`, the ORDERED `arms` pair `[minuend, subtrahend]`, an `estimator`, the '
        '`estimate`, its `se`, the `n_clusters` behind it, an `interval`, and a `sign_test`. '
        '`ER-STATS` recomputes every stated contrast from the clusters block -- estimate and '
        'SE through `stats.paired_difference`, the interval through `stats.paired_interval`, '
        'the sign test through `stats.sign_test` -- at the same tolerances the per-arm '
        'intervals answer to, and a contrast with no clusters block behind it fails rather '
        'than passing unchecked.'
    )
    lines.append('')
    lines.append(
        'The `paired_t` interval is `estimate +/- t(1 - alpha/2, n_clusters - 1) * se`, and '
        'the interval records the `t_quantile` it used so the arithmetic is checkable by '
        'hand. It is an APPROXIMATION -- it assumes roughly symmetric per-cluster deltas and '
        'a t reference distribution on few clusters -- so an exact, distribution-free sign '
        'test is REQUIRED beside it on every contrast: `p_value`, the `effective_n` left '
        'after the tie rule (a zero per-cluster delta is dropped), and the count of '
        '`positive` deltas. It is stated in the record rather than only printed, because a '
        'number that lives only in a report sentence is a number no gate reads -- the drift '
        'and parity gates re-parse the embedded typed block. `validate.py` recomputes the '
        'triple from the clusters block and also echoes it as an INFO line, which is '
        'confirmation of the arithmetic (and the values to write down while authoring), not '
        'the check. See `references/small-n-stats.md`.'
    )
    lines.append('')
    lines.append(
        'Scope is read from the `arms` block, not from a new field. An outcome carrying '
        '`arms` is scored over the FULL declared cell set: its arm denominators still have '
        'to reconcile to N_expected, and its per-arm Wilson interval stays -- DESCRIPTIVE, '
        'an upper bound on precision, with the headline precision quoted from the contrast. '
        'An outcome scored over a subset of the cells carries no `arms` block at all; it '
        'states its clusters and its contrasts, and no full-cell-set rule is applied to it.'
    )
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
    # A pasted activation line can carry any bytes (a hand-written glyph variant, a
    # path with accents); a cp1252 stdout would raise on the way out and lose the
    # designed message. Emit UTF-8 regardless of the platform default.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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
        help='print the record as a journal envelope for sealore ingestion',
    )
    mode.add_argument(
        '--activation-line',
        action='store_true',
        help="print the record's activation line (the generated form is the only one)",
    )
    mode.add_argument(
        '--check-activation-line',
        metavar='LINE',
        help='verify a pasted activation line against the record (tier and path must match)',
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

    if args.activation_line:
        if not args.records:
            ap.error('a record.yaml path is required for --activation-line')
        for record_arg in args.records:
            # An unreadable record or a tier-0 record is a reported failure, not a
            # traceback (the same shape as --check's DRIFT line).
            try:
                print(record_activation_line(record_arg))
            except (OSError, ValueError) as exc:
                print(f'ERROR {record_arg}: {exc}')
                return 1
        return 0

    if args.check_activation_line is not None:
        if len(args.records) != 1:
            ap.error('exactly one record.yaml path is required for --check-activation-line')
        try:
            reason = check_activation_line(args.check_activation_line, args.records[0])
        except (OSError, ValueError) as exc:
            print(f'ERROR {args.records[0]}: {exc}')
            return 1
        if reason is not None:
            print(f'MISMATCH {args.records[0]}: {reason}')
            return 1
        print(f'OK {args.check_activation_line.strip()}')
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
        text = render_report(load_record(record_path), record_path)
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

#!/usr/bin/env python3
"""Score the act-hint runs and fill the frozen record -- mechanically, after the spend.

The pre-registration was frozen before a cent moved (see FREEZE.md). This module is the
other end of that choreography: it reads what the run actually produced, scores it
through the frozen oracle, and writes the results into the record the plan is frozen in.
Every choice it could have made was made before the run and is READ from the record:

  * the exclusion rule, verbatim from `analysis_plan.exclusions.operationalization` --
    a run is excluded IFF the harness reported is_error or the response text is empty; a
    response that DECLINES for lack of an allowed tool is scored as written;
  * the fully-excluded-prompt drop-out, from `exclusions.fully_excluded_prompt`, and the
    stricter complete-prompt-pairs fallback from `analysis_plan.ceiling_halt_fallback`
    whenever a planned run never started;
  * the arms-block rule, from `exclusions.arms_block_rule` -- the confirmatory outcome
    states per-arm counts and their descriptive Wilson intervals ONLY when nothing was
    excluded, because ER-RECON holds arm denominators to N_expected;
  * which of the four pre-committed interpretations the data selected, from
    `analysis_plan.interpretations` -- the four legs partition the 2x2 of (the primary
    contrast moved, the inert-minus-control contrast moved), so the selection is a table
    lookup and no fifth leg can be invented after the fact.

It is DETERMINISTIC (no wall clock, no randomness; the observed first-run timestamp
comes from the run log) and IDEMPOTENT (it overwrites the finalized fields rather than
appending, so a second run yields byte-identical output). Before it writes anything it
RE-VERIFIES every frozen material SHA through `freeze_fill.material_hashes`: an edit to
bank, rules, table or oracle after the freeze fails loudly here rather than quietly
changing what was measured.

    python finalize.py [--record record.yaml] [--runs runs.jsonl] [--check]

Stdlib + PyYAML; the CLI additionally imports the sibling render.py / validate.py.
Python 3.13+.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / 'plugins' / 'experiment-discipline' / 'skills' / 'experiment-rigor' / 'scripts'


def load_module(name: str, path: Path):
    """Import a module from an EXACT PATH and register it under `name`.

    A bare `import stats` resolves through sys.path, and `evals/harness/stats.py` is a
    different module with the same name that the harness puts at the FRONT of the path --
    so the analysis would bind whichever import happened to run first, and the failure
    (an AttributeError deep in a contrast) would look like a bug in the statistics rather
    than a name collision. Loading by path removes the question, and registering the
    module under its plain name means a sibling's own `import stats` binds this one too.
    An already-loaded module from the same file is reused rather than duplicated.
    """
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, '__file__', None) == str(path):
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f'cannot load {name} from {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# freeze_fill: the one definition of what a material is and how it hashes.
freeze_fill = load_module('act_hint_freeze_fill', HERE / 'freeze_fill.py')
# stats before validate, and from_fathom too: validate imports both by bare name, so they
# are bound to the plugin's own copies before validate's module body runs.
stats = load_module('stats', SCRIPTS / 'stats.py')
load_module('from_fathom', SCRIPTS / 'from_fathom.py')
validate = load_module('validate', SCRIPTS / 'validate.py')
render = load_module('render', SCRIPTS / 'render.py')

RECORD_PATH = HERE / 'record.yaml'
RUNS_PATH = HERE / 'runs.jsonl'

ALPHA = 0.05
CONFIRMATORY_OUTCOME = 'rigor_disposition'
SECONDARY_OUTCOME = 'skeleton_wellformedness'

# The A/A calibration, named once. It is the instrument's own noise floor, so it stays out
# of every signal test: an A/A that moves is a diagnostic failure, not a finding, and it is
# recorded as one.
AA_CONTRAST = 'narrow_minus_wide_genuine'

# (primary contrast moved, inert - control moved) -> the pre-committed leg. The four
# frozen interpretations partition this 2x2 exactly, which is what makes the selection
# mechanical: there is no cell left over for a fifth reading. The `preamble_only` cell
# additionally carries the frozen word ALIKE, which the secondary contrast decides --
# see select_interpretation; the leg id is not changed by it, only qualified.
LEG_BY_MOVEMENT: dict[tuple[bool, bool], str] = {
    (True, False): 'content_carries',
    (True, True): 'preamble_only',
    (False, True): 'inert_moves_alone',
    (False, False): 'recorded_null',
}

# What each leg would move the belief to. Written here BEFORE the run selects one, so the
# posterior is a lookup rather than a sentence composed around the number that came back.
LEG_BELIEF: dict[str, str] = {
    'content_carries': (
        'the injected hint moves the evaluation-act disposition while the token-matched '
        'inert arm does not, so the effect travels with the hint CONTENT rather than with '
        'the preamble -- including the literal plugin-qualified skill id the router row '
        'ships, which is the correct reading of content here'
    ),
    'preamble_only': (
        'wide and inert both move, so the effect is preamble cost and the content is '
        'irrelevant; ship no row on this evidence'
    ),
    'inert_moves_alone': (
        'inert moves and wide does not, likewise a preamble effect with the content '
        'contributing nothing; ship no row on this evidence'
    ),
    'recorded_null': (
        'nothing moves beyond its interval on the clustered scale: a recorded null over a '
        'loaded, unhinted skill rather than over no treatment, read on the decoy side and '
        'on wide - inert'
    ),
}

# The chain prior: the founding RG-2x2 posterior, carried across as a QUALITATIVE GRADE
# link (never pooled counts), together with what the frozen baseline_expectation does to
# it. Static text, because a belief this record states about itself must not change when
# a file outside the frozen materials does.
PRIOR_BELIEF = (
    "from the founding RG-2x2 (this record's chain prior): register is null -- reg == ctrl "
    "in both tiers -- while the gate's forced deliberation raised the disciplinary "
    'footprint from 18/48 to 36/48 as an exploratory signal, with the skill never loaded in '
    'any arm. The frozen baseline_expectation carries that across as a WIDE genuine-side '
    'prior rather than a point estimate: every arm here loads the skill, so control measures '
    "the skill's own trigger surface with no hint, the hint effect is marginal over that, "
    "and the prior's upper tail is a ceiling risk rather than a compression risk."
)

# The relative link to that prior record. ER-LINK resolves it from this record's directory.
PRIOR_SOURCE_ID = (
    '../../../plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2/record.yaml'
)

ROLLOUT_PRECONDITION = (
    'whether the live UserPromptSubmit hook delivers this same text inside a production '
    'spawn is NOT measured here, and neither is candidate displacement under the live '
    'nine-row router_rules.json. Both are named preconditions for any production rollout of '
    'a row, not results of this run.'
)


# --- reading what the run produced -------------------------------------------


def load_runs(path: str | Path) -> list[dict[str, Any]]:
    """The run log as a list of records, in log order.

    A blank line is skipped; anything else that does not parse is a loud failure. The log
    is the reconstructible trace behind every number below, so a half-readable one is not
    something to work around.
    """
    rows: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding='utf-8')
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f'{path}:{i}: run log line is not JSON: {exc}') from exc
        if not isinstance(row, dict):
            raise SystemExit(f'{path}:{i}: run log line is not an object')
        rows.append(row)
    return rows


def load_oracle(record_dir: str | Path):
    """Import verify.py FROM THE RECORD'S OWN DIRECTORY -- the frozen material whose SHA
    this module just re-verified -- rather than by module name, so scoring a run set
    always uses the oracle that travels with it."""
    path = Path(record_dir) / 'verify.py'
    spec = importlib.util.spec_from_file_location('act_hint_oracle', path)
    if spec is None or spec.loader is None:
        raise SystemExit(f'cannot load the oracle at {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_materials(record: dict[str, Any], record_dir: str | Path) -> list[str]:
    """Re-hash every frozen material and compare it against the record's own `materials`
    block, plus the two places the oracle's hash is restated (both outcomes' verifier and
    the oracle-validation block). Returns the mismatches; empty means the results about to
    be written describe the materials the pre-registration froze."""
    computed = freeze_fill.material_hashes(record_dir)
    stated = record.get('materials') or {}
    problems: list[str] = []
    for key, want in computed.items():
        got = (stated.get(key) or {}).get('sha256')
        if got != want:
            rel = freeze_fill.MATERIALS[key][0]
            problems.append(f'{key} ({rel}): record states {got}, file hashes to {want}')
    for outcome in record.get('outcomes') or []:
        if not isinstance(outcome, dict):
            continue
        got = (outcome.get('verifier') or {}).get('hash')
        if got != computed['oracle']:
            problems.append(
                f'outcome {outcome.get("name")!r} verifier.hash: record states {got}, '
                f'verify.py hashes to {computed["oracle"]}'
            )
    got_labels = (record.get('oracle_validation') or {}).get('sha256')
    if got_labels != computed['oracle_labels']:
        problems.append(
            f'oracle_validation.sha256: record states {got_labels}, oracle_labels.json '
            f'hashes to {computed["oracle_labels"]}'
        )
    return problems


# --- the pre-registered exclusion rule ---------------------------------------


def exclusion_reason(run: dict[str, Any]) -> str | None:
    """The frozen rule, verbatim: excluded IFF the harness reported is_error or the
    response text is empty. Nothing else excludes a run -- in particular a response that
    declines for lack of an allowed tool is scored as written, which is what keeps the
    decoy half from being decided after the fact (10 of the 12 decoys ask for actions
    every arm is denied)."""
    if run.get('is_error'):
        return 'harness_error'
    if not str(run.get('response') or '').strip():
        return 'empty_response'
    return None


def score_runs(
    runs: list[dict[str, Any]],
    prompt_class: dict[str, str],
    score: Callable[[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """One scored row per logged run, in log order.

    The prompt CLASS comes from the frozen bank, not from the log's own copy of it, and
    the scorer never sees an arm label -- that is the oracle's blinding, preserved here.
    """
    out: list[dict[str, Any]] = []
    for run in runs:
        pid = str(run.get('prompt_id'))
        if pid not in prompt_class:
            raise SystemExit(f'run log names prompt {pid!r}, which is not in the frozen bank')
        reason = exclusion_reason(run)
        row: dict[str, Any] = {
            'arm': str(run.get('arm')),
            'prompt_id': pid,
            'prompt_class': prompt_class[pid],
            'repeat': run.get('repeat'),
            'excluded': reason,
            'num_turns': run.get('num_turns'),
            'cost_usd': run.get('cost_usd'),
            'ts': run.get('ts'),
        }
        if reason is None:
            scored = score(str(run.get('response') or ''), prompt_class[pid])
            row['state'] = scored['state']
            row['rigor_disposition'] = bool(scored['rigor_disposition'])
            row['skeleton_wellformedness'] = bool(scored['skeleton_wellformedness'])
        out.append(row)
    return out


# --- cluster blocks, contrasts, and the drop-out rule ------------------------


def cluster_block(
    rows: list[dict[str, Any]],
    pids: list[str],
    arms: tuple[str, ...],
    field: str,
    *,
    require_repeats: int | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """(clusters, dropped prompt ids) for one outcome over one prompt set.

    A cluster cell is (successes, scored runs) for that prompt in that arm. Two frozen
    rules decide what survives, and which one applies is not a choice made here:

      * always, the fully-excluded-prompt DROP-OUT -- a prompt with no scored run in some
        arm has no denominator there, so it leaves the block entirely and its id is
        reported. stats.paired_difference raises on a zero-size cluster rather than
        degrading, and one dead prompt must not take the analysis down with it.
      * when the CEILING HALTED the run, the stricter pre-registered fallback: complete
        prompt-pairs only, so a prompt is kept only where every arm carries both of its
        repeats (`require_repeats`). A partial pair is a cluster whose two arms were
        measured to different depths, and the fallback declines it rather than reporting
        a precision it does not have.
    """
    clusters: dict[str, Any] = {}
    dropped: list[str] = []
    for pid in sorted(pids):
        cells: dict[str, Any] = {}
        for arm in arms:
            scored = [
                r for r in rows if r['prompt_id'] == pid and r['arm'] == arm and not r['excluded']
            ]
            cells[arm] = {
                'numerator': sum(1 for r in scored if r[field]),
                'denominator': len(scored),
            }
        floor = 1 if require_repeats is None else require_repeats
        if any(cell['denominator'] < floor for cell in cells.values()):
            dropped.append(pid)
            continue
        clusters[pid] = cells
    return clusters, dropped


def contrast(
    name: str, clusters: dict[str, Any], arms: list[str], *, role: str, note: str = ''
) -> dict[str, Any]:
    """One `contrasts[]` entry, computed from the cluster block by stats.py alone.

    The estimate and SE come from `paired_difference`, the interval from `paired_interval`
    at the frozen alpha, and the exact sign test rides beside it under the frozen tie rule.
    validate.py's ER-STATS recomputes all three from the same block, so a value that drifts
    from its counts is a failure rather than a discrepancy nobody notices.
    """
    arrays, reason = validate.cluster_arrays(clusters, arms[0], arms[1])
    if arrays is None:
        raise SystemExit(f'contrast {name}: cannot build paired arrays: {reason}')
    _pids, a_num, a_den, b_num, b_den = arrays
    try:
        diff = stats.paired_difference(a_num, a_den, b_num, b_den)
        band = stats.paired_interval(diff.mean_diff, diff.se, diff.n_clusters, ALPHA)
        signs = stats.sign_test(stats.cluster_deltas(a_num, a_den, b_num, b_den))
    except ValueError as exc:
        # Too few clusters survived the drop-out rule to estimate anything. That is a
        # finding about the run, not something to paper over with a degraded number.
        raise SystemExit(
            f'contrast {name}: {exc} ({len(clusters)} surviving cluster(s) after the '
            'fully-excluded-prompt drop-out)'
        ) from exc
    entry: dict[str, Any] = {
        'name': name,
        'arms': list(arms),
        'estimator': 'paired_difference',
        'role': role,
        'estimate': round(diff.mean_diff, 4),
        'se': round(diff.se, 4),
        'n_clusters': diff.n_clusters,
        'interval': {
            'method': 'paired_t',
            'alpha': ALPHA,
            'low': round(band.low, 4),
            'high': round(band.high, 4),
            't_quantile': round(band.quantile, 4),
        },
        'sign_test': {
            'p_value': round(signs.p_value, 4),
            'effective_n': signs.effective_n,
            'positive': signs.positive,
        },
    }
    if note:
        entry['note'] = note
    return entry


def arms_block(clusters: dict[str, Any], arms: tuple[str, ...]) -> dict[str, Any]:
    """The per-arm counts with their DESCRIPTIVE Wilson intervals. Stated only when
    nothing was excluded (the frozen arms-block rule): ER-RECON holds these denominators
    to N_expected, and an exclusion is the first thing that makes them unable to."""
    out: dict[str, Any] = {}
    for arm in arms:
        num = sum(cell[arm]['numerator'] for cell in clusters.values())
        den = sum(cell[arm]['denominator'] for cell in clusters.values())
        interval = stats.confidence_interval(num, den, 'wilson', ALPHA)
        out[arm] = {
            'numerator': num,
            'denominator': den,
            'ci': {
                'method': 'wilson',
                'alpha': ALPHA,
                'low': round(interval.low, 4),
                'high': round(interval.high, 4),
            },
        }
    return out


# --- the mechanical reads ----------------------------------------------------


def moved(entry: dict[str, Any], threshold: float) -> bool:
    """Did this contrast MOVE, in the sense the frozen plan fixed?

    Two frozen conditions, both required, neither chosen here: the two-sided paired-t
    interval excludes 0 (`analysis_plan.interval`, the headline precision on the clustered
    scale), AND the estimate reaches the declared MEWD (`analysis_plan.decision_rule`:
    rate_difference, gte, two_sided). Reading only the interval would ignore a threshold
    the plan states; reading only the threshold would call an effect the interval cannot
    separate from zero a movement.
    """
    interval = entry.get('interval') or {}
    low, high = interval.get('low'), interval.get('high')
    excludes_zero = bool(low is not None and high is not None and (low > 0 or high < 0))
    return excludes_zero and abs(float(entry['estimate'])) >= threshold


def _frozen_leg(record: dict[str, Any], leg_id: str) -> dict[str, Any]:
    plan = record.get('analysis_plan') or {}
    for leg in plan.get('interpretations') or []:
        if isinstance(leg, dict) and leg.get('id') == leg_id:
            return leg
    raise SystemExit(
        f'the frozen plan names no interpretation {leg_id!r}; the four legs are the only '
        'readings this record may reach'
    )


def select_interpretation(
    record: dict[str, Any],
    contrasts: dict[str, dict[str, Any]],
    control_genuine_rate: float | None,
    *,
    instrument_noise: bool = False,
) -> dict[str, Any]:
    """The pre-committed leg the data selected, plus the arithmetic behind the selection.

    The lookup is over the pair (primary moved, inert - control moved) and the frozen legs
    partition it exactly. Two frozen qualifiers ride on top of it, and neither invents a
    fifth leg:

    ALIKE. The second leg's frozen condition is "wide and inert both move ALIKE", and the
    record's own secondary_contrast calls wide - inert the only pair in this design that
    isolates content from preamble. So the (moved, moved) cell is checked against that
    secondary: alike means the secondary did NOT move. When it did, the leg is still
    `preamble_only` -- there is no other cell to go to -- but it is recorded with
    alike: false, the frozen "the content is irrelevant" reading is SUPPRESSED rather than
    quoted, and what replaces it is the size of the content component the secondary
    separated.

    NO HEADROOM. The frozen text scopes this to the null: "A null with control at or near
    ceiling ... is recorded as NO HEADROOM". The magnitude is derived from frozen numbers
    rather than from a judgement about what "near ceiling" means -- the plan declares a
    MEWD, so control with less than one MEWD of room left on the genuine half leaves no
    headroom for any arm to move into. The rate and the headroom are reported whatever the
    leg; only the FLAG is scoped, because a primary that moved is proof there was room.
    """
    plan = record.get('analysis_plan') or {}
    threshold = float((plan.get('decision_rule') or {}).get('threshold'))
    primary_name = (plan.get('primary_contrast') or {}).get('name')
    secondary_name = (plan.get('secondary_contrast') or {}).get('name')
    primary = contrasts[str(primary_name)]
    inert_control = contrasts['inert_minus_control']
    secondary = contrasts[str(secondary_name)]

    movement = {
        str(primary_name): moved(primary, threshold),
        'inert_minus_control': moved(inert_control, threshold),
        str(secondary_name): moved(secondary, threshold),
    }
    leg_id = LEG_BY_MOVEMENT[(movement[str(primary_name)], movement['inert_minus_control'])]
    leg = _frozen_leg(record, leg_id)
    alike = not movement[str(secondary_name)]

    headroom = None if control_genuine_rate is None else round(1.0 - control_genuine_rate, 4)
    no_headroom = leg_id == 'recorded_null' and headroom is not None and headroom < threshold
    basis = (
        f'{primary_name} = {primary["estimate"]} '
        f'[{primary["interval"]["low"]}, {primary["interval"]["high"]}] over '
        f'{primary["n_clusters"]} cluster(s); inert_minus_control = '
        f'{inert_control["estimate"]} [{inert_control["interval"]["low"]}, '
        f'{inert_control["interval"]["high"]}]; {secondary_name} = {secondary["estimate"]} '
        f'[{secondary["interval"]["low"]}, {secondary["interval"]["high"]}]. A contrast '
        f'moves when its two-sided interval excludes 0 and its estimate reaches the '
        f'declared MEWD of {threshold}. Moved: '
        + ', '.join(f'{name}={value}' for name, value in movement.items())
        + '.'
    )
    alike_basis = (
        f'ALIKE is decided by the frozen secondary: {secondary_name} = '
        f'{secondary["estimate"]} [{secondary["interval"]["low"]}, '
        f'{secondary["interval"]["high"]}], which does '
        f'{"NOT clear" if alike else "clear"} the declared MEWD of {threshold} with an '
        f'interval {"covering" if alike else "excluding"} 0. It qualifies the '
        f'`preamble_only` leg only; the other three legs do not use the word.'
    )
    conclusion: dict[str, Any] = {
        'interpretation': leg_id,
        'condition': leg.get('condition'),
        'read': leg.get('read'),
        'basis': basis,
        'alike': alike,
        'alike_basis': alike_basis,
        'moved': movement,
        'instrument_noise': instrument_noise,
        'control_genuine_rate': control_genuine_rate,
        'headroom': headroom,
        'no_headroom': no_headroom,
        'headroom_rule': (
            "headroom = 1 - the control arm's rate on the genuine half; below one declared "
            f'MEWD ({threshold}) there is no room for any arm to move into. The flag is '
            'scoped to the RECORDED NULL, where the frozen text puts it: a null there is '
            'recorded as NO HEADROOM rather than as no effect, and the read rests on the '
            'decoy side and on wide - inert. Under any other leg something moved, which is '
            'itself proof there was room.'
        ),
        'rollout_precondition': ROLLOUT_PRECONDITION,
    }
    if leg_id == 'preamble_only' and not alike:
        conclusion['frozen_read_suppressed'] = leg.get('read')
        conclusion['read'] = (
            'wide and inert both moved, but NOT ALIKE. The confound-separation secondary '
            f'{secondary_name} = {secondary["estimate"]} '
            f'[{secondary["interval"]["low"]}, {secondary["interval"]["high"]}] clears the '
            'declared MEWD with an interval excluding 0, and it is the only pair in this '
            'design that isolates content from preamble -- so it separates a CONTENT '
            'component of that size. The leg is still the pre-committed `preamble_only` '
            'cell; its own frozen reading does not hold on this data and is recorded under '
            '`frozen_read_suppressed` rather than quoted here, and no fifth leg is '
            'invented for the difference.'
        )
    if instrument_noise:
        conclusion['instrument_noise_note'] = (
            'the A/A calibration MOVED. narrow and wide deliver byte-identical text on '
            'every genuine prompt, so its expected value is exactly 0 and whatever it '
            'shows is the instrument noise floor -- a diagnostic failure, not a signal. '
            'Read every contrast at or below that spread as unresolved by this design.'
        )
    return conclusion


def _verdict(is_confirmatory: bool, any_moved: bool) -> str:
    if is_confirmatory:
        return 'confirmatory_supported' if any_moved else 'confirmatory_null'
    return 'exploratory_signal' if any_moved else 'inconclusive'


# --- the descriptive blocks --------------------------------------------------


def state_breakdown(rows: list[dict[str, Any]], arms: tuple[str, ...]) -> dict[str, Any]:
    """The full 2x2 state per arm and per class, with the line-only rate as its own
    number. A line emitted without the substance scores zero on the genuine half, so how
    often that happened is the finding the founding case never made visible."""
    states = ('both', 'line_only', 'skeleton_only', 'neither')
    per_arm: dict[str, Any] = {}
    for arm in arms:
        per_class: dict[str, Any] = {}
        for cls in ('all', 'genuine', 'decoy'):
            scored = [
                r
                for r in rows
                if r['arm'] == arm
                and not r['excluded']
                and (cls == 'all' or r['prompt_class'] == cls)
            ]
            counts = {state: sum(1 for r in scored if r['state'] == state) for state in states}
            counts['scored'] = len(scored)
            counts['line_only_rate'] = (
                round(counts['line_only'] / len(scored), 4) if scored else None
            )
            per_class[cls] = counts
        per_arm[arm] = per_class
    return {
        'note': (
            'descriptive. The 2x2 state is recorded per run so the LINE-ONLY rate is a '
            'first-class number: on a genuine prompt only `both` counts correct, so a line '
            'emitted without the five elements scores zero here rather than being rewarded.'
        ),
        'arms': per_arm,
    }


def run_economy(rows: list[dict[str, Any]], arms: tuple[str, ...]) -> dict[str, Any]:
    """The turn and cost tax per arm, over every logged run including excluded ones -- an
    excluded run still cost what it cost. Descriptive: no interval is quoted on it and no
    contrast rests on it."""

    def _summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        turns = [r['num_turns'] for r in subset if isinstance(r['num_turns'], (int, float))]
        costs = [r['cost_usd'] for r in subset if isinstance(r['cost_usd'], (int, float))]
        return {
            'runs': len(subset),
            'mean_turns': round(sum(turns) / len(turns), 4) if turns else None,
            'total_cost_usd': round(sum(costs), 4) if costs else None,
            'mean_cost_usd': round(sum(costs) / len(costs), 4) if costs else None,
        }

    return {
        'note': (
            'descriptive, from the harness records. The harness reports turns and cost, not '
            'token counts, so the tax is priced in the units it actually measures.'
        ),
        'per_arm': {arm: _summary([r for r in rows if r['arm'] == arm]) for arm in arms},
        'total': _summary(rows),
    }


def _iso_utc(epoch: Any) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat().replace('+00:00', 'Z')


# --- the finalized record ----------------------------------------------------


def arms_of(record: dict[str, Any]) -> tuple[str, ...]:
    """The arm names, read off the frozen design cells (`<arm>_<class>`) in their declared
    order, so the record's own declaration is what fixes them."""
    seen: list[str] = []
    for cell in (record.get('design') or {}).get('cells') or []:
        name = str((cell or {}).get('name', ''))
        arm = name.rsplit('_', 1)[0]
        if arm and arm not in seen:
            seen.append(arm)
    return tuple(seen)


def finalize_record(
    record: dict[str, Any], rows: list[dict[str, Any]], prompt_class: dict[str, str]
) -> dict[str, Any]:
    """Return the finalized record: observed disposition, per-cluster results for both
    outcomes, the contrasts, the 2x2 breakdown, the descriptive tax, the selected
    interpretation and the prior -> posterior update.

    Pure and idempotent -- every field is overwritten rather than appended to, so
    re-running over the same rows yields byte-identical output whether the input is the
    frozen record or an already-finalized one.
    """
    out = copy.deepcopy(record)
    arms = arms_of(out)
    plan = out.get('analysis_plan') or {}
    threshold = float((plan.get('decision_rule') or {}).get('threshold'))
    # Name AND arm pair come from the frozen plan; restating either here would let this
    # module quietly compute a different contrast than the one that was pre-registered.
    primary_name = str((plan.get('primary_contrast') or {}).get('name'))
    primary_arms = [str(a) for a in (plan.get('primary_contrast') or {}).get('arms') or []]
    secondary_name = str((plan.get('secondary_contrast') or {}).get('name'))
    secondary_arms = [str(a) for a in (plan.get('secondary_contrast') or {}).get('arms') or []]
    if len(primary_arms) != 2 or len(secondary_arms) != 2:
        raise SystemExit(
            'the frozen plan must name an ordered arm pair for both the primary and the '
            'secondary contrast; finalize computes the pair it was given, never one it picks'
        )
    control_arm = primary_arms[1]

    keys = [(r['arm'], r['prompt_id'], r['repeat']) for r in rows]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise SystemExit(
            f'the run log carries {len(duplicates)} duplicate run key(s), e.g. {duplicates[:3]}; '
            'finalize refuses to guess which spawn is the measured one'
        )

    total = int((out.get('disposition') or {}).get('total'))
    excluded_rows = [r for r in rows if r['excluded']]
    completed = len(rows) - len(excluded_rows)
    not_run = total - len(rows)
    if not_run < 0:
        raise SystemExit(
            f'the run log holds {len(rows)} runs but the frozen plan declares {total}; '
            'finalize will not reconcile more runs than were planned'
        )
    reasons: dict[str, int] = {
        'harness_error': sum(1 for r in excluded_rows if r['excluded'] == 'harness_error'),
        'empty_response': sum(1 for r in excluded_rows if r['excluded'] == 'empty_response'),
        'not_run': not_run,
    }
    excluded_total = len(excluded_rows) + not_run
    out['disposition'] = {
        'total': total,
        'completed': completed,
        'excluded': excluded_total,
        'exclusion_reasons': reasons,
        'excluded_runs': sorted(
            (
                {
                    'arm': r['arm'],
                    'prompt_id': r['prompt_id'],
                    'repeat': r['repeat'],
                    'reason': r['excluded'],
                }
                for r in excluded_rows
            ),
            key=lambda r: (r['arm'], r['prompt_id'], str(r['repeat'])),
        ),
        'note': (
            'observed. `harness_error` and `empty_response` are the two arms of the frozen '
            'exclusion rule; `not_run` counts planned runs the ceiling halt never started, '
            'which the ceiling-halt fallback governs rather than the exclusion rule. Any '
            'non-zero total here puts BOTH outcomes in the contrasts-only shape.'
        ),
    }

    # The ceiling-halt fallback is triggered by the halt itself, not by a judgement about
    # how much of the run survived: any planned run that never started puts the analysis on
    # complete prompt-pairs only, at the reduced precision that implies.
    repeats = (out.get('run_config') or {}).get('repeats')
    if not_run > 0 and not isinstance(repeats, int):
        raise SystemExit(
            'the run halted before its plan finished, but run_config.repeats is missing, so '
            'the pre-registered complete-prompt-pairs fallback cannot be applied'
        )
    require_repeats = int(repeats) if not_run > 0 else None
    pairing_rule = (
        'every scored run counts; a prompt drops out only where an arm has none'
        if require_repeats is None
        else f'CEILING-HALT FALLBACK: complete prompt-pairs only -- a prompt is kept only '
        f'where every arm carries both of its {require_repeats} repeats, and the reduced '
        f'precision is what the intervals below report'
    )
    out['disposition']['pairing_rule'] = pairing_rule

    genuine_pids = sorted(p for p, cls in prompt_class.items() if cls == 'genuine')
    decoy_pids = sorted(p for p, cls in prompt_class.items() if cls == 'decoy')
    all_pids = sorted(prompt_class)

    # --- the contrasts, each scoped to ITS OWN arm pair (the frozen drop-out rule) ------
    #
    # The frozen drop-out is CONTRAST-scoped: "a prompt whose runs are ALL excluded in
    # either arm of a contrast drops out of THAT contrast", and the ceiling-halt fallback
    # keeps a prompt "only where every arm of THE CONTRAST carries both of its repeats".
    # One four-arm cluster block cannot express that -- a prompt dead in `narrow` would
    # cost the wide-control primary a cluster it does not use. ER-STATS recomputes every
    # contrast from the ONE clusters block of the results key it sits in, so the faithful
    # shape is one results key per contrast pair, each carrying only that pair's arms and
    # only the prompts that survive for that pair.
    #
    # The two DECLARED outcomes keep their own keys, carry the verdicts, and hold a
    # descriptive full-arm clusters block (which the arms block reconciles against when
    # nothing was excluded). They state no contrasts: a contrast there would be recomputed
    # against the all-arms block, which is the defect this layout removes.

    def _pair_key(outcome: str, contrast_name: str) -> str:
        return f'{outcome}__{contrast_name}'

    # (contrast name, ordered arm pair, prompt scope, scope label, outcome, field, note)
    pair_specs: list[tuple[str, list[str], list[str], str, str, str, str]] = [
        (
            primary_name,
            primary_arms,
            all_pids,
            'all',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'the pre-named PRIMARY: the deployable-package question, tokens included',
        ),
        (
            secondary_name,
            secondary_arms,
            all_pids,
            'all',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'pre-registered SECONDARY (the enum has no such value): confound separation on '
            'an identical row set with token-matched text, and the pair that decides ALIKE',
        ),
        (
            'narrow_minus_control',
            ['narrow', control_arm],
            all_pids,
            'all',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'exploratory package contrast; no arm is length-matched to narrow, so it '
            're-inherits the founding case confound intact',
        ),
        (
            'narrow_minus_inert',
            ['narrow', 'inert'],
            all_pids,
            'all',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'exploratory, named in the frozen exploratory_contrasts',
        ),
        (
            'inert_minus_control',
            ['inert', control_arm],
            all_pids,
            'all',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'the leg selector: whether the preamble alone moves the disposition',
        ),
        (
            f'{primary_name}_genuine',
            primary_arms,
            genuine_pids,
            'genuine',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'the pre-registered class decomposition, exploratory',
        ),
        (
            f'{secondary_name}_genuine',
            secondary_arms,
            genuine_pids,
            'genuine',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'the pre-registered class decomposition, exploratory',
        ),
        (
            AA_CONTRAST,
            ['narrow', 'wide'],
            genuine_pids,
            'genuine',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'A/A CALIBRATION -- the instrument noise floor. narrow and wide deliver '
            'byte-identical text on all 12 genuine prompts, so the expected value is '
            'exactly 0 and a contrast no larger than this spread is not an effect',
        ),
        (
            f'{primary_name}_decoy',
            primary_arms,
            decoy_pids,
            'decoy',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'the pre-registered class decomposition, exploratory -- the habituation cost',
        ),
        (
            f'{secondary_name}_decoy',
            secondary_arms,
            decoy_pids,
            'decoy',
            CONFIRMATORY_OUTCOME,
            CONFIRMATORY_OUTCOME,
            'the pre-registered class decomposition, exploratory',
        ),
        (
            f'{primary_name}_wellformed',
            primary_arms,
            genuine_pids,
            'genuine',
            SECONDARY_OUTCOME,
            SECONDARY_OUTCOME,
            'the scoped secondary outcome: does the denominator actually arrive',
        ),
        (
            f'{secondary_name}_wellformed',
            secondary_arms,
            genuine_pids,
            'genuine',
            SECONDARY_OUTCOME,
            SECONDARY_OUTCOME,
            'the scoped secondary outcome, confound-separated',
        ),
    ]

    # The two DECLARED outcomes are inserted first so the record reads outcome-first, with
    # the pair-scoped blocks that carry the contrasts after them. They are filled below.
    results: dict[str, Any] = {CONFIRMATORY_OUTCOME: {}, SECONDARY_OUTCOME: {}}
    by_name: dict[str, dict[str, Any]] = {}
    for name, pair, pids, class_scope, outcome, field, note in pair_specs:
        clusters, dropped = cluster_block(
            rows, pids, tuple(pair), field, require_repeats=require_repeats
        )
        role = 'confirmatory' if name == primary_name else 'exploratory'
        entry = contrast(name, clusters, pair, role=role, note=note)
        entry['moved'] = moved(entry, threshold)
        by_name[name] = entry
        block: dict[str, Any] = {
            'outcome': outcome,
            'class_scope': class_scope,
            'scope': (
                f'{" - ".join(pair)} over the {class_scope} prompt clusters; this block '
                "carries ONLY this pair's arms and only the prompts that survive for it"
            ),
            'paired': True,
            'clusters': clusters,
            'contrasts': [entry],
            'surviving_clusters': len(clusters),
            'dropped_prompts': dropped,
            'pairing_rule': pairing_rule,
        }
        # No `verdict` on a pair block: a verdict belongs to a DECLARED outcome (ER-PREREG
        # reads a results key as an outcome name), and each contrast already states
        # whether it moved.
        if name == AA_CONTRAST:
            block['instrument_noise'] = entry['moved']
        results[_pair_key(outcome, name)] = block

    instrument_noise = bool(by_name[AA_CONTRAST]['moved'])

    # The two declared outcomes: verdict, descriptive counts, no contrasts.
    full, full_dropped = cluster_block(
        rows, all_pids, arms, CONFIRMATORY_OUTCOME, require_repeats=require_repeats
    )
    well, well_dropped = cluster_block(
        rows, genuine_pids, arms, SECONDARY_OUTCOME, require_repeats=require_repeats
    )
    confirmatory_block: dict[str, Any] = {
        'verdict': _verdict(True, by_name[primary_name]['moved']),
        'paired': True,
        'scope': (
            'the confirmatory outcome over all declared cells. The verdict rests on the '
            f'pre-named primary contrast alone ({primary_name}); the counts here are '
            'descriptive and every contrast lives in its own pair-scoped block'
        ),
    }
    if excluded_total == 0:
        confirmatory_block['arms'] = arms_block(full, arms)
    confirmatory_block['clusters'] = full
    confirmatory_block['surviving_clusters'] = len(full)
    confirmatory_block['dropped_prompts'] = full_dropped
    confirmatory_block['pairing_rule'] = pairing_rule
    results[CONFIRMATORY_OUTCOME] = confirmatory_block
    results[SECONDARY_OUTCOME] = {
        'verdict': _verdict(
            False,
            any(
                by_name[n]['moved']
                for n in (f'{primary_name}_wellformed', f'{secondary_name}_wellformed')
            ),
        ),
        'paired': True,
        'scope': (
            'the scoped secondary, GENUINE cells only -- no arms block by construction, '
            'since ER-RECON holds an arm block to N_expected and a subset cannot reach it'
        ),
        'clusters': well,
        'surviving_clusters': len(well),
        'dropped_prompts': well_dropped,
        'pairing_rule': pairing_rule,
    }

    control_rate = None
    genuine_pair = results[_pair_key(CONFIRMATORY_OUTCOME, f'{primary_name}_genuine')]['clusters']
    if genuine_pair:
        num = sum(cell[control_arm]['numerator'] for cell in genuine_pair.values())
        den = sum(cell[control_arm]['denominator'] for cell in genuine_pair.values())
        control_rate = round(num / den, 4) if den else None
    conclusion = select_interpretation(
        out, by_name, control_rate, instrument_noise=instrument_noise
    )
    out['results'] = results

    out['state_breakdown'] = state_breakdown(rows, arms)
    out['run_economy'] = run_economy(rows, arms)
    out['conclusion'] = conclusion

    stamps = [r['ts'] for r in rows if isinstance(r['ts'], (int, float))]
    run_block = dict(out.get('run') or {})
    if stamps:
        run_block['first_run_at'] = _iso_utc(min(stamps))
        run_block['last_run_at'] = _iso_utc(max(stamps))
    run_block['n'] = len(rows)
    costs = [r['cost_usd'] for r in rows if isinstance(r['cost_usd'], (int, float))]
    if costs:
        run_block['cost_usd_est'] = round(sum(costs), 4)
    out['run'] = run_block

    threats = out.get('threats') or {}
    out['updates'] = {
        'certainty': 'low',
        'downgrade_reasons': [
            key
            for key, row in threats.items()
            if isinstance(row, dict) and row.get('status') == 'residual'
        ],
        'prior': {
            'belief': PRIOR_BELIEF,
            'grade': 'low',
            'source_id': PRIOR_SOURCE_ID,
        },
        'what_each_leg_would_move': dict(LEG_BELIEF),
        'posterior': {
            'belief': f'{LEG_BELIEF[conclusion["interpretation"]]}. {conclusion["basis"]}',
            'grade': 'low',
            'method': 'qualitative_grade_link',
            'selected_interpretation': conclusion['interpretation'],
        },
    }
    return out


# --- CLI ---------------------------------------------------------------------


HEADER = (
    '# Finalized by finalize.py -- the frozen pre-registration plus the observed results:\n'
    '# the disposition and its exclusions, the per-cluster counts and contrasts, the 2x2\n'
    '# state breakdown, the descriptive tax, the pre-committed interpretation the data\n'
    '# selected, and the prior -> posterior update. Do not hand-edit; re-run finalize.py\n'
    '# to regenerate. See FREEZE.md for the choreography.\n'
)


def render_finalized(record: dict[str, Any]) -> str:
    """The record's finalized text. One place, so --check and the write path cannot
    disagree about what would be written."""
    return HEADER + yaml.safe_dump(record, sort_keys=False, allow_unicode=False, width=100)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Finalize the act-hint record after its run.')
    ap.add_argument('--record', default=str(RECORD_PATH), help='path to record.yaml')
    ap.add_argument('--runs', default=None, help='the run log (default: runs.jsonl beside it)')
    ap.add_argument('--check', action='store_true', help='report what would change; write nothing')
    args = ap.parse_args(argv)

    record_path = Path(args.record).resolve()
    record_dir = record_path.parent
    runs_path = Path(args.runs) if args.runs else record_dir / RUNS_PATH.name
    record = yaml.safe_load(record_path.read_text(encoding='utf-8'))

    # Before anything is written: the materials must still be the ones that were frozen.
    problems = verify_materials(record, record_dir)
    for line in problems:
        print(f'FROZEN-MATERIAL MISMATCH: {line}')
    if problems:
        print(
            'refusing to finalize: a material changed after it was hashed into record.yaml, '
            'so these results would not describe what the pre-registration froze.'
        )
        return 2
    print('frozen materials re-verified against record.yaml')

    if not runs_path.exists():
        print(f'no run log at {runs_path}; finalize has nothing to score')
        return 2
    bank = json.loads((record_dir / 'bank.json').read_text(encoding='utf-8'))['prompts']
    prompt_class = {p['id']: p['class'] for p in bank}
    oracle = load_oracle(record_dir)
    patterns = oracle.load_patterns(record_dir / 'oracle_patterns.json')

    rows = score_runs(
        load_runs(runs_path),
        prompt_class,
        lambda text, cls: oracle.score(text, cls, patterns),
    )
    finalized = finalize_record(record, rows, prompt_class)
    text = render_finalized(finalized)

    import render
    import validate as validator

    report_text = render.render_report(finalized, record_path)
    if args.check:
        current = record_path.read_text(encoding='utf-8').replace('\r\n', '\n')
        report_path = record_dir / 'report.md'
        current_report = (
            report_path.read_text(encoding='utf-8').replace('\r\n', '\n')
            if report_path.exists()
            else ''
        )
        print(f'{"WOULD CHANGE" if text != current else "UP TO DATE"} {record_path}')
        print(f'{"WOULD CHANGE" if report_text != current_report else "UP TO DATE"} {report_path}')
        return 0

    record_path.write_text(text, encoding='utf-8', newline='\n')
    report_path = record_dir / 'report.md'
    report_path.write_text(report_text, encoding='utf-8', newline='\n')
    print(f'finalized {record_path} and {report_path}')

    report = validator.run_checks(finalized, record_path)
    for finding in report.findings:
        tag = finding.code if finding.level == 'FAIL' else f'{finding.level} [{finding.code}]'
        print(f'{tag}: {finding.message}')
    drift = render.check_drift(record_path)
    if drift is not None:
        print(f'DRIFT: {drift}')
    print(
        f'{len(report.failures)} failure(s), {len(report.warnings)} warning(s), '
        f'{"drift" if drift else "no drift"}; selected interpretation: '
        f'{finalized["conclusion"]["interpretation"]}'
    )
    if report.failures or drift is not None:
        print('finalize FAILED: the record did not reach a clean validate + render --check')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""The pre-spend shape gate: drive the COMPLETE record shape past the real validator
before a single paid run.

This gate exists because both of the previous round's `ER-RECON` collisions were found
by running a synthetic record past `validate.py`, not by reading the spec. A
reconciliation or stats-shape defect that surfaces here costs nothing; the same defect
found at finalize costs the whole 25-60 USD run.

Four records go through, all of them shapes this experiment will actually produce:

  1. the REAL frozen record as committed -- zero failures under the shape gates;
  2. a synthetic FINAL stage with zero exclusions: both outcomes populated, the
     confirmatory one with `arms` + `clusters` + `contrasts[]`, the genuine-scoped
     secondary with `clusters` + `contrasts[]` and NO `arms` block;
  3. a synthetic FINAL stage WITH exclusions, in the contrasts-only shape the record's
     `analysis_plan.exclusions.arms_block_rule` pre-registers;
  4. two deliberately broken variants, so the gate is demonstrably not vacuous.

Variant 4 is also the evidence behind the arms-block rule: a record that states per-arm
counts alongside a non-zero `disposition.excluded` CANNOT reconcile under `ER-RECON`,
which is why the rule was pre-registered instead of discovered.

Runnable with pytest or `python test_record_shape.py`; needs PyYAML.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / 'plugins' / 'experiment-discipline' / 'skills' / 'experiment-rigor' / 'scripts'

for extra in (str(HERE), str(SCRIPTS)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

try:
    import yaml
except ImportError:  # pragma: no cover - the runner supplies PyYAML
    print('skip: PyYAML not installed')
    sys.exit(0)

import freeze_fill  # noqa: E402 - after the path fix
import stats  # noqa: E402
import validate  # noqa: E402

# run_arms puts evals/harness at the FRONT of sys.path, and a different stats.py lives
# there (the eval harness's own). Import it only after the plugin modules above are
# bound, then put the path back, so nothing later resolves to the wrong module.
_PATH_BEFORE = list(sys.path)
import run_arms  # noqa: E402

sys.path[:] = _PATH_BEFORE

RECORD_PATH = HERE / 'record.yaml'
RECORD: dict[str, Any] = yaml.safe_load(RECORD_PATH.read_text(encoding='utf-8'))
BANK = run_arms.load_bank()
ARMS = ('control', 'narrow', 'wide', 'inert')


def _failures(record: dict[str, Any], *, schema_only: bool = True) -> list[str]:
    report = validate.run_checks(record, RECORD_PATH, schema_only=schema_only)
    return [f'{f.code}: {f.message}' for f in report.failures]


# --- 1. the frozen record as committed ---------------------------------------


def test_the_frozen_record_passes_every_shape_gate():
    """Only the git-context gates may be outstanding pre-freeze; nothing structural."""
    assert _failures(RECORD) == []


def test_the_freeze_stage_disposition_carries_total_alone():
    assert RECORD['disposition'] == {'total': 192}


def test_design_is_arm_by_class_and_reconciles():
    cells = RECORD['design']['cells']
    assert len(cells) == 8
    assert sum(c['planned_n'] for c in cells) == 192 == RECORD['disposition']['total']
    assert {c['name'] for c in cells} == {f'{a}_{c}' for a in ARMS for c in ('genuine', 'decoy')}
    assert RECORD['design']['shared_tasks'] is True
    assert RECORD['schema_version'] == 1.1
    assert RECORD['tier'] == 'measurement'


def test_outcomes_are_one_confirmatory_and_one_scoped_secondary():
    outcomes = {o['name']: o for o in RECORD['outcomes']}
    assert outcomes['rigor_disposition']['role'] == 'confirmatory'
    # The enum has no "secondary": the scoped secondary rides as `exploratory` and
    # says so in its own operationalization.
    assert outcomes['skeleton_wellformedness']['role'] == 'exploratory'
    for outcome in outcomes.values():
        assert outcome['verifier']['path'] == 'verify.py'
        assert len(outcome['verifier']['hash']) == 64, 'verifier hash must be filled before stage 1'


def test_the_analysis_plan_names_everything_the_freeze_owes():
    plan = RECORD['analysis_plan']
    assert plan['ci_method'] == 'wilson'
    assert plan['contrast_estimator'] == 'paired_difference'
    assert plan['interval']['method'] == 'paired_t'
    assert plan['interval']['status'] == 'approximation'
    assert plan['robustness_bound']['method'] == 'sign_test'
    assert 'DROPPED' in plan['robustness_bound']['tie_rule']
    assert 'effective cluster count' in plan['robustness_bound']['tie_rule']
    assert plan['primary_contrast']['arms'] == ['wide', 'control']
    assert plan['primary_contrast']['outcome'] == 'rigor_disposition'
    assert plan['primary_contrast']['role'] == 'confirmatory'
    assert plan['secondary_contrast']['arms'] == ['wide', 'inert']
    assert plan['secondary_contrast']['role'] == 'exploratory'
    assert plan['decision_rule']['direction'] == 'two_sided'
    ids = [i['id'] for i in plan['interpretations']]
    assert ids == ['content_carries', 'preamble_only', 'inert_moves_alone', 'recorded_null']
    null_leg = plan['interpretations'][-1]['read']
    assert 'NO HEADROOM' in null_leg and 'CEILING' in null_leg
    for key in ('rule', 'fully_excluded_prompt', 'arms_block_rule'):
        assert plan['exclusions'][key].strip()
    assert 'COMPLETE' in plan['ceiling_halt_fallback']
    assert 'PT-BR' in plan['language_fallback']


def test_threats_cover_the_enum_plus_the_two_named_residuals():
    threats = RECORD['threats']
    assert threats['custom_candidate_displacement']['status'] == 'residual'
    assert threats['custom_language_delivery']['status'] == 'residual'
    assert threats['token_length_confound']['status'] == 'residual'
    assert 'narrow - control' in threats['token_length_confound']['statement']
    assert threats['judge_bias']['status'] == 'controlled'


def test_run_config_matches_the_runner_it_describes():
    cfg = RECORD['run_config']
    assert cfg['model'] == run_arms.MODEL
    assert cfg['max_turns'] == run_arms.MAX_TURNS
    assert cfg['repeats'] == run_arms.REPEATS
    assert cfg['order_seed'] == run_arms.SEED
    assert cfg['per_run_budget_usd'] == run_arms.PER_RUN_BUDGET_USD
    assert cfg['ceiling_usd'] == run_arms.CEILING_USD
    assert cfg['insertion_point'] == run_arms.INSERTION_POINT
    assert cfg['allowed_tools'] == run_arms.ALLOWED_TOOLS
    assert cfg['disallowed_tools'] == run_arms.DISALLOWED_TOOLS
    assert cfg['skill_tool_in_allowlist'] is ('Skill' in run_arms.ALLOWED_TOOLS.split(','))
    assert cfg['allowlist_identical_across_arms'] is True
    assert cfg['timeout_seconds'] == run_arms.TIMEOUT_SECONDS
    assert cfg['sampling_mode'] == run_arms.SAMPLING
    assert cfg['plugin_dir'] == run_arms.PLUGIN_DIR.relative_to(REPO).as_posix()
    assert cfg['cwd_fixture'] == run_arms.CWD_FIXTURE.relative_to(REPO).as_posix()
    band = cfg['cost_projection_usd']
    assert (band['per_run_low'], band['per_run_high']) == run_arms.COST_BAND_USD
    assert (band['total_low'], band['total_high']) == run_arms.projected_cost(192)
    assert RECORD['run']['source'] == 'hand'
    assert RECORD['run']['hand_reason'].strip()


def test_first_run_at_cannot_be_outrun_by_the_freeze_commit():
    """ER-ANCHOR fails when the freeze commit postdates the first run, so a near-term
    placeholder is a fuse on a clock: it would redden a stage-1 commit made hours
    later, through no change to anything."""
    first_run = RECORD['run']['first_run_at']
    stamp = first_run if isinstance(first_run, str) else first_run.isoformat()
    assert stamp >= '2026-08-01', f'{stamp} leaves too little room before the freeze commit'


# --- the record cannot describe a reality it does not have -------------------


def test_the_record_firing_block_matches_the_frozen_table():
    """Recompute the summary the record quotes. Prose that has drifted from the table
    it was read off is the same defect as a report drifting from its record."""
    table = run_arms.load_table()
    stated = RECORD['firing']
    assert stated['rows'] == len(table['rows'])
    assert stated['below_floor_rows'] == sum(1 for r in table['rows'] if r['hook_skip'])
    for arm, summary in table['summary'].items():
        block = stated[arm]
        assert block['fired'] == summary['fired'], arm
        for key in ('genuine', 'decoy', 'en', 'pt'):
            want = f'{summary[key]["fired"]}/{summary[key]["rows"]}'
            assert block[key] == want, (arm, key, block[key], want)
    worst = max(d['deviation'] for d in table['wide_vs_inert'])
    assert f'{worst * 100:.2f} percent' in stated['wide_inert_token_match']


def test_the_record_oracle_validation_matches_the_oracle():
    import verify

    labels = json.loads((HERE / 'oracle_labels.json').read_text(encoding='utf-8'))
    summary = verify.check_labels(labels['labels'])
    stated = RECORD['oracle_validation']
    assert stated['n'] == summary['n'] == len(labels['labels'])
    assert stated['positive_class'] == labels['positive_class']
    assert stated['recall']['numerator'] == summary['recall_numerator']
    assert stated['recall']['denominator'] == summary['recall_denominator']
    assert stated['specificity']['numerator'] == summary['specificity_numerator']
    assert stated['specificity']['denominator'] == summary['specificity_denominator']
    assert set(stated['states_covered']) == {i['expected_state'] for i in labels['labels']}


def test_the_plan_carries_the_review_fixes():
    plan = RECORD['analysis_plan']
    excl = plan['exclusions']['operationalization']
    assert 'iff' in excl.lower(), 'the exclusion rule must be stated as a biconditional'
    assert 'is_error' in excl and 'empty' in excl
    assert 'NOT an exclusion' in excl, 'a tool-less decline is scored, not dropped'
    assert plan['robustness_bound']['sided'] == 'two_sided'
    assert 'pre-registered' in plan['secondary_contrast']['role_note'].lower()
    assert 'A/A' in plan['aa_calibration']
    assert 'narrow_minus_wide' in plan['aa_calibration']
    content = next(i for i in plan['interpretations'] if i['id'] == 'content_carries')
    assert 'experiment-discipline:experiment-rigor' in content['read']
    threats = RECORD['threats']
    assert threats['custom_oracle_primeability']['status'] == 'controlled'
    assert 'RESIDUAL' in threats['custom_oracle_primeability']['statement']
    assert 'FALSE NEGATIVE' in threats['construct_validity_proxy']['statement']
    assert 'arm-uniform' in threats['construct_validity_proxy']['statement']
    assert 'run set' in RECORD['run_config']['isolation']


# --- 2 and 3. the synthetic final stages --------------------------------------


def _counts(pid_index: int, arm_index: int, denominator: int = 2) -> int:
    """A deterministic synthetic numerator with real between-prompt variation, so the
    paired SE is non-degenerate and the sign test has both ties and non-ties."""
    return (pid_index * 5 + arm_index * 3) % (denominator + 1)


def _cluster_block(pids: list[str], arms: tuple[str, ...], denominator: int = 2) -> dict:
    return {
        pid: {
            arm: {'numerator': _counts(i, a, denominator), 'denominator': denominator}
            for a, arm in enumerate(arms)
        }
        for i, pid in enumerate(pids)
    }


def _contrast(name: str, clusters: dict, arms: list[str]) -> dict:
    pairs, reason = validate.cluster_arrays(clusters, arms[0], arms[1])
    assert pairs is not None, reason
    _pids, a_num, a_den, b_num, b_den = pairs
    diff = stats.paired_difference(a_num, a_den, b_num, b_den)
    band = stats.paired_interval(diff.mean_diff, diff.se, diff.n_clusters, 0.05)
    signs = stats.sign_test(stats.cluster_deltas(a_num, a_den, b_num, b_den))
    return {
        'name': name,
        'arms': arms,
        'estimator': 'paired_difference',
        'estimate': round(diff.mean_diff, 4),
        'se': round(diff.se, 4),
        'n_clusters': diff.n_clusters,
        'interval': {
            'method': 'paired_t',
            'alpha': 0.05,
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


def _arms_block(clusters: dict, arms: tuple[str, ...]) -> dict:
    out: dict[str, Any] = {}
    for arm in arms:
        num = sum(c[arm]['numerator'] for c in clusters.values())
        den = sum(c[arm]['denominator'] for c in clusters.values())
        interval = stats.confidence_interval(num, den, 'wilson', 0.05)
        out[arm] = {
            'numerator': num,
            'denominator': den,
            'ci': {
                'method': 'wilson',
                'alpha': 0.05,
                'low': round(interval.low, 4),
                'high': round(interval.high, 4),
            },
        }
    return out


def final_record_no_exclusions() -> dict[str, Any]:
    """The expected shape: everything completed, the confirmatory outcome carrying its
    descriptive per-arm block beside the clustered contrasts."""
    record = copy.deepcopy(RECORD)
    all_pids = [p['id'] for p in BANK]
    genuine = [p['id'] for p in BANK if p['class'] == 'genuine']
    full = _cluster_block(all_pids, ARMS)
    scoped = _cluster_block(genuine, ARMS)
    record['disposition'] = {'total': 192, 'completed': 192, 'excluded': 0}
    record['results'] = {
        'rigor_disposition': {
            'verdict': 'confirmatory_null',
            'paired': True,
            'arms': _arms_block(full, ARMS),
            'clusters': full,
            'contrasts': [
                _contrast('wide_minus_control', full, ['wide', 'control']),
                _contrast('wide_minus_inert', full, ['wide', 'inert']),
                _contrast('narrow_minus_control', full, ['narrow', 'control']),
            ],
        },
        'skeleton_wellformedness': {
            'verdict': 'exploratory_signal',
            'clusters': scoped,
            'contrasts': [_contrast('wide_minus_control_genuine', scoped, ['wide', 'control'])],
        },
    }
    return record


def final_record_with_exclusions() -> dict[str, Any]:
    """The pre-registered fallback shape: one prompt fully excluded and dropped from
    every contrast, some clusters at a single surviving repeat, and NO arms block on
    either outcome."""
    record = copy.deepcopy(RECORD)
    all_pids = [p['id'] for p in BANK][1:]  # the first prompt dropped out entirely
    genuine = [p['id'] for p in BANK if p['class'] == 'genuine'][1:]
    full = _cluster_block(all_pids, ARMS)
    scoped = _cluster_block(genuine, ARMS)
    for arm in ARMS:  # two surviving-single-repeat clusters
        cell = full[all_pids[0]][arm]
        cell['denominator'] = 1
        cell['numerator'] = min(cell['numerator'], 1)
    record['disposition'] = {'total': 192, 'completed': 186, 'excluded': 6}
    record['results'] = {
        'rigor_disposition': {
            'verdict': 'confirmatory_null',
            'clusters': full,
            'contrasts': [
                _contrast('wide_minus_control', full, ['wide', 'control']),
                _contrast('wide_minus_inert', full, ['wide', 'inert']),
            ],
        },
        'skeleton_wellformedness': {
            'verdict': 'inconclusive',
            'clusters': scoped,
            'contrasts': [_contrast('wide_minus_control_genuine', scoped, ['wide', 'control'])],
        },
    }
    return record


def test_the_complete_final_shape_validates():
    assert _failures(final_record_no_exclusions()) == []


def test_the_excluded_fallback_shape_validates():
    assert _failures(final_record_with_exclusions()) == []


def test_the_scoped_secondary_carries_no_arms_block():
    for builder in (final_record_no_exclusions, final_record_with_exclusions):
        secondary = builder()['results']['skeleton_wellformedness']
        assert 'arms' not in secondary
        assert secondary['contrasts'][0]['n_clusters'] in (11, 12)


# --- 4. the gate is not vacuous ----------------------------------------------


def test_a_contrast_that_disagrees_with_its_clusters_fails():
    broken = final_record_no_exclusions()
    broken['results']['rigor_disposition']['contrasts'][0]['estimate'] += 0.1
    failures = _failures(broken)
    assert any('ER-STATS' in f and 'wide_minus_control' in f for f in failures), failures


def test_per_arm_counts_beside_an_exclusion_cannot_reconcile():
    """The observed collision the arms-block rule is pre-registered against: ER-RECON
    holds arm denominators to N_expected, so per-arm counts and a non-zero
    disposition.excluded are mutually exclusive shapes."""
    broken = final_record_with_exclusions()
    outcome = broken['results']['rigor_disposition']
    outcome['arms'] = _arms_block(outcome['clusters'], ARMS)
    outcome['paired'] = True
    failures = _failures(broken)
    assert any('ER-RECON' in f for f in failures), failures
    assert RECORD['analysis_plan']['exclusions']['arms_block_rule'].strip()


# --- freeze_fill: the mechanical half of the choreography ---------------------


def test_every_stated_material_sha_matches_the_file_on_disk():
    computed = freeze_fill.material_hashes(HERE)
    for key, want in computed.items():
        assert RECORD['materials'][key]['sha256'] == want, key
    assert RECORD['oracle_validation']['sha256'] == computed['oracle_labels']
    for outcome in RECORD['outcomes']:
        assert outcome['verifier']['hash'] == computed['oracle']
    assert len(computed) == 9, sorted(computed)


def test_freeze_fill_is_a_no_op_once_the_materials_are_filled():
    text, failures = freeze_fill.fill(RECORD_PATH)
    assert failures == []
    assert text == RECORD_PATH.read_text(encoding='utf-8').replace('\r\n', '\n')


def test_an_edited_material_is_a_loud_failure_not_a_rewrite():
    record = copy.deepcopy(RECORD)
    record['materials']['bank']['sha256'] = '0' * 64
    _text, failures = freeze_fill.fill_materials(
        RECORD_PATH.read_text(encoding='utf-8'), record, freeze_fill.material_hashes(HERE)
    )
    assert any('bank' in f and 'post-freeze edit' in f for f in failures), failures


def test_filling_the_freeze_region_anchors_the_record():
    """End to end against a real commit in this repository: after the fill, the record
    carries a resolvable plan_frozen_at and ER-ANCHOR is clean. Nothing is written."""
    text, failures = freeze_fill.fill(RECORD_PATH, 'HEAD')
    assert failures == []
    filled = yaml.safe_load(text)
    pin = filled['plan_frozen_at']
    assert len(pin['commit']) == 40, pin
    assert pin['path'] == 'evals/experiments/act-hint/record.yaml'
    assert isinstance(pin['timestamp'], str) and pin['timestamp'].startswith('20'), pin
    assert validate.check_anchor(filled, RECORD_PATH) == []
    # idempotent: filling the already-filled text with the same SHA changes nothing
    again = freeze_fill.replace_region(
        text, freeze_fill.frozen_block(pin['commit'], pin['path'], pin['timestamp'])
    )
    assert again == text


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
    print('ok: freeze record, both final shapes, two broken variants and freeze_fill all hold')

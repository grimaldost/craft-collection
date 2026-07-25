"""Tests for validate.py — the experiment-rigor central gate (§2).

Runnable with pytest or `python test_validate.py` (the repo's run_tests.py runs the
latter from this dir and requires an `ok:` sentinel on success).

PyYAML is a HARD dependency of the mechanism spine (FM-2): the record gates parse
nested YAML, so this module refuses to run — and never emits the `skip:` sentinel —
when PyYAML is absent, so the suite cannot go green-via-skip.
"""

from __future__ import annotations

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on a broken toolchain
    print(
        'FAIL: PyYAML is required for the validate.py gate and its tests; '
        'run under `uv run --no-project --with pyyaml` (mechanism spine must not skip)'
    )
    raise SystemExit(1) from None

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import validate


def schema() -> dict:
    return validate.load_schema()


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
CLEAN_PROBE = FIXTURES / 'clean_probe.yaml'
# Schema v1.1: the clean paired-contrast record and its defect twin, whose stated
# contrast disagrees with the very clusters block it claims to summarize.
PAIRED_CONTRAST = FIXTURES / 'paired_contrast.yaml'
PAIRED_CONTRAST_MISMATCH = FIXTURES / 'paired_contrast_mismatch.yaml'

ALL_THREATS = {
    'contamination_familiarity',
    'prompt_format_sensitivity',
    'judge_bias',
    'model_version_drift',
    'nondeterminism',
    'construct_validity_proxy',
    'token_length_confound',
    'selection_exclusion',
    'generalization',
}


# --- helpers ----------------------------------------------------------------


def base_probe() -> dict:
    return yaml.safe_load(CLEAN_PROBE.read_text(encoding='utf-8'))


def fail_codes(report: validate.Report) -> set[str]:
    return {f.code for f in report.failures}


def warn_codes(report: validate.Report) -> set[str]:
    return {f.code for f in report.warnings}


def skip_codes(report: validate.Report) -> set[str]:
    return {code for code, _ in report.skips}


def write_record(directory: Path, record: dict, name: str = 'record.yaml') -> Path:
    path = directory / name
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding='utf-8')
    return path


def check(record: dict, path: Path | None = None, *, schema_only: bool = False) -> validate.Report:
    return validate.run_checks(record, path, schema_only=schema_only)


def _git(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env['GIT_CONFIG_GLOBAL'] = os.devnull
    full_env['GIT_CONFIG_SYSTEM'] = os.devnull
    if env:
        full_env.update(env)
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(cwd), *args],  # noqa: S607 - git resolved from PATH
        capture_output=True,
        text=True,
        env=full_env,
    )


def _git_init(d: Path) -> None:
    _git(d, 'init', '-q')


def _git_commit(d: Path, date: str, msg: str = 'freeze') -> str:
    _git(d, 'add', '-A')
    _git(
        d,
        '-c',
        'user.name=t',
        '-c',
        'user.email=t@e',
        'commit',
        '-q',
        '-m',
        msg,
        env={'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date},
    )
    return _git(d, 'rev-parse', 'HEAD').stdout.strip()


def _measurement_record(frozen_commit: str = 'PENDING') -> dict:
    return {
        'schema_version': 1,
        'tier': 'measurement',
        'experiment': 'rg-2x2-probe',
        'design': {
            'shared_tasks': True,
            'cells': [
                {'name': 'with_gate', 'planned_n': 48},
                {'name': 'without_gate', 'planned_n': 48},
            ],
        },
        'disposition': {'completed': 96, 'excluded': 0, 'total': 96},
        'outcomes': [
            {
                'name': 'footprint',
                'role': 'exploratory',
                'operationalization': 'regex presence of the footprint marker in the run output',
                'verifier': {'path': 'verify.py', 'hash': 'abc123'},
            }
        ],
        'analysis_plan': {
            'ci_method': 'wilson',
            'comparison': 'with_gate vs without_gate',
            'decision_rule': {
                'metric': 'rate',
                'comparison': 'gt',
                'threshold': 0.1,
                'direction': 'higher',
            },
        },
        'results': {
            'footprint': {
                'verdict': 'exploratory_signal',
                'paired': True,
                'arms': {
                    'with_gate': {
                        'numerator': 36,
                        'denominator': 48,
                        'ci': {'method': 'wilson', 'alpha': 0.05, 'low': 0.6122, 'high': 0.8508},
                    },
                    'without_gate': {
                        'numerator': 18,
                        'denominator': 48,
                        'ci': {'method': 'wilson', 'alpha': 0.05, 'low': 0.2522, 'high': 0.5164},
                    },
                },
            }
        },
        'threats': {t: {'status': 'residual', 'statement': f'{t} note'} for t in ALL_THREATS},
        'plan_frozen_at': {'commit': frozen_commit, 'timestamp': '2026-01-01T00:00:00'},
        'run': {'source': 'hand', 'first_run_at': '2026-02-01T00:00:00'},
    }


# --- the clean fixture passes every gate ------------------------------------


def test_clean_probe_passes_full_and_schema_only():
    rec = base_probe()
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        full = check(rec, path)
        assert full.failures == [], full.failures
        schema = check(rec, path, schema_only=True)
        assert schema.failures == [], schema.failures


def test_schema_only_lists_skipped_context_gates():
    rec = base_probe()
    report = check(rec, None, schema_only=True)
    assert skip_codes(report) == {'ER-ANCHOR', 'ER-XCHECK', 'ER-PREREG', 'ER-COMPREHEND'}, (
        report.skips
    )


def test_comprehend_code_in_catalog():
    # R3-1: ER-COMPREHEND belongs in §2's enumerated code catalog.
    assert 'ER-COMPREHEND' in validate.ERROR_CODES


# --- ER-SCHEMA --------------------------------------------------------------


def test_er_schema_rate_without_denominator():
    rec = base_probe()
    # A rate without both numerator and denominator fails (the founding-case defect).
    rec['results']['signal']['arms']['arm_a'] = {
        'rate': 0.75,
        'ci': {'method': 'wilson', 'alpha': 0.05, 'low': 0.4677, 'high': 0.9111},
    }
    assert 'ER-SCHEMA' in fail_codes(check(rec))


def test_er_schema_unknown_version_names_known():
    rec = base_probe()
    rec['schema_version'] = 2
    report = check(rec)
    assert 'ER-SCHEMA' in fail_codes(report)
    assert any('1' in f.message for f in report.failures if f.code == 'ER-SCHEMA')


def test_er_schema_missing_required_field():
    rec = base_probe()
    del rec['design']
    assert 'ER-SCHEMA' in fail_codes(check(rec))


def test_er_schema_unknown_tier():
    rec = base_probe()
    rec['tier'] = 'wishful'
    assert 'ER-SCHEMA' in fail_codes(check(rec))


# --- ER-RECON ---------------------------------------------------------------


def test_er_recon_cells_disagree_with_disposition():
    rec = base_probe()
    # cells sum to 24; break disposition to 48 (the two-waves-omitted shape).
    rec['disposition'] = {'completed': 48, 'excluded': 0, 'total': 48}
    report = check(rec)
    assert 'ER-RECON' in fail_codes(report)
    # The failure names the reconciling arithmetic.
    assert any(
        '24' in f.message and '48' in f.message for f in report.failures if f.code == 'ER-RECON'
    )


def test_er_recon_outcome_denominators_disagree():
    rec = base_probe()
    rec['results']['signal']['arms']['arm_b']['denominator'] = 6
    assert 'ER-RECON' in fail_codes(check(rec))


# --- ER-STATS ---------------------------------------------------------------


def test_er_stats_ci_mismatch():
    rec = base_probe()
    rec['results']['signal']['arms']['arm_a']['ci']['high'] = 0.9999
    assert 'ER-STATS' in fail_codes(check(rec))


def test_er_stats_refuses_normal_below_30():
    rec = base_probe()
    rec['results']['signal']['arms']['arm_a']['ci']['method'] = 'normal'
    report = check(rec)
    assert 'ER-STATS' in fail_codes(report)


def test_er_stats_undeclared_paired():
    rec = base_probe()
    del rec['results']['signal']['paired']
    assert 'ER-STATS' in fail_codes(check(rec))


def test_er_stats_unpaired_shared_tasks_needs_cluster():
    rec = base_probe()
    rec['design']['shared_tasks'] = True
    rec['results']['signal']['paired'] = False
    # no clustered_se and no unclustered_reason -> ER-STATS
    assert 'ER-STATS' in fail_codes(check(rec))
    rec['results']['signal']['unclustered_reason'] = 'arms drew disjoint task samples'
    assert 'ER-STATS' not in fail_codes(check(rec))


# --- ER-STATS: the schema v1.1 paired contrasts ------------------------------


def base_contrast() -> dict:
    return yaml.safe_load(PAIRED_CONTRAST.read_text(encoding='utf-8'))


def _contrast(rec: dict) -> dict:
    return rec['results']['signal']['contrasts'][0]


def test_v11_paired_contrast_fixture_passes_every_gate():
    rec = base_contrast()
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        report = check(rec, path)
        assert report.failures == [], report.failures
        assert report.warnings == [], report.warnings


def test_v10_record_still_validates_under_the_v11_schema():
    # The extension is ADDITIVE: known_versions carries both, and a record that
    # declares neither clusters nor contrasts is untouched by every new rule.
    rec = base_probe()
    assert rec['schema_version'] == 1
    assert 1 in schema()['known_versions'] and 1.1 in schema()['known_versions']
    assert check(rec).failures == []
    assert validate.check_contrasts(rec) == []
    assert validate.check_cluster_recon(rec) == []


def test_contrast_disagreeing_with_its_clusters_fails_naming_the_contrast():
    rec = yaml.safe_load(PAIRED_CONTRAST_MISMATCH.read_text(encoding='utf-8'))
    report = check(rec)
    assert 'ER-STATS' in fail_codes(report), fail_codes(report)
    messages = [f.message for f in report.failures if f.code == 'ER-STATS']
    # The offending contrast is NAMED (outcome, index and its own name), and the
    # message reconciles: the record's independent-trials SE against the paired one.
    assert all("contrasts[0] 'with_hint_minus_control'" in m for m in messages), messages
    assert any('stated se 0.1379' in m and '0.1193' in m for m in messages), messages


def test_cli_exits_one_on_the_mismatch_and_zero_on_the_corrected_twin():
    proc = _run_cli(PAIRED_CONTRAST_MISMATCH)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'ER-STATS' in proc.stdout, proc.stdout
    assert 'with_hint_minus_control' in proc.stdout, proc.stdout
    ok = _run_cli(PAIRED_CONTRAST)
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_stated_interval_disagreeing_with_paired_interval_fails():
    for field, bad in (('low', -0.2), ('high', 0.9), ('t_quantile', 1.96)):
        rec = base_contrast()
        _contrast(rec)['interval'][field] = bad
        messages = [f.message for f in check(rec).failures if f.code == 'ER-STATS']
        assert any(f'interval {field}' in m for m in messages), (field, messages)
    # And through the CLI, on a record whose only defect is the stated interval.
    rec = base_contrast()
    _contrast(rec)['interval']['high'] = 0.9
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        proc = _run_cli(path)
        assert proc.returncode == 1, proc.stdout
        assert 'ER-STATS' in proc.stdout and 'interval high' in proc.stdout, proc.stdout


def test_missing_interval_bound_or_quantile_fails():
    for field in ('low', 'high', 't_quantile'):
        rec = base_contrast()
        del _contrast(rec)['interval'][field]
        messages = [f.message for f in check(rec).failures if f.code == 'ER-STATS']
        assert any(f'interval {field} missing' in m for m in messages), (field, messages)


def test_contrast_without_a_clusters_block_fails_rather_than_passing():
    # A stated statistic the gate cannot recompute is the vacuous-gate case; it
    # fails loudly instead of being believed.
    rec = base_contrast()
    del rec['results']['signal']['clusters']
    messages = [f.message for f in check(rec).failures if f.code == 'ER-STATS']
    assert any('no clusters block' in m for m in messages), messages


def test_contrast_arm_missing_from_the_clusters_block_fails():
    rec = base_contrast()
    del rec['results']['signal']['clusters']['p4']['control']
    messages = [f.message for f in check(rec).failures if f.code == 'ER-STATS']
    assert any("'p4'" in m and "arm 'control'" in m for m in messages), messages


def test_stated_sign_test_is_required_on_every_contrast():
    # Fail-closed: the distribution-free bound is not optional decoration beside an
    # approximate interval. Dropping it, or any of its three fields, is ER-SCHEMA.
    rec = base_contrast()
    del _contrast(rec)['sign_test']
    assert 'ER-SCHEMA' in fail_codes(check(rec)), fail_codes(check(rec))
    for field in ('p_value', 'effective_n', 'positive'):
        rec = base_contrast()
        del _contrast(rec)['sign_test'][field]
        messages = [f.message for f in check(rec).failures if f.code == 'ER-SCHEMA']
        assert any('sign_test' in m for m in messages), (field, messages)
    for field, bad in (('p_value', 'about 0.4'), ('effective_n', -1), ('positive', '4')):
        rec = base_contrast()
        _contrast(rec)['sign_test'][field] = bad
        assert 'ER-SCHEMA' in fail_codes(check(rec)), (field, bad)


def test_stated_sign_test_is_recomputed_from_the_clusters_block():
    # The whole point of stating it: the number sits inside the typed block the gates
    # read, so a flattering p-value cannot survive. Each field fails on its own.
    for field, bad, phrase in (
        ('p_value', 0.01, 'sign_test p_value 0.01'),
        ('effective_n', 6, 'sign_test effective_n 6'),
        ('positive', 6, 'sign_test positive 6'),
    ):
        rec = base_contrast()
        _contrast(rec)['sign_test'][field] = bad
        messages = [f.message for f in check(rec).failures if f.code == 'ER-STATS']
        assert any(phrase in m for m in messages), (field, messages)
        assert all("contrasts[0] 'with_hint_minus_control'" in m for m in messages), messages


def test_a_fabricated_sign_test_cannot_hide_in_report_prose():
    # The hole this closes: the p-value used to live only in report.md prose, which
    # the drift gate ignores (it re-parses the embedded typed block only). Now it is
    # IN the block -- so a fabricated value fails the record gate, and a prose edit
    # that disagrees with the block is drift.
    import render

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        path = write_record(d, base_contrast())
        (d / 'report.md').write_text(render.render_report(base_contrast()), encoding='utf-8')
        assert render.check_drift(path) is None
        assert check(base_contrast(), path).failures == []
        tampered = (d / 'report.md').read_text(encoding='utf-8').replace('0.375', '0.01')
        (d / 'report.md').write_text(tampered, encoding='utf-8')
        assert render.check_drift(path) is not None
        assert 'ER-PARITY' in fail_codes(check(base_contrast(), path))


def test_sign_test_note_confirms_the_recomputation_beside_every_contrast():
    rec = base_contrast()
    report = check(rec)
    notes = [f for f in report.notes if 'sign test' in f.message]
    assert len(notes) == 1, report.notes
    # The note shows the arithmetic the gate did -- p-value, the effective count left
    # by the tie rule, the positives -- which is what an in-progress record writes down.
    assert 'p=0.3750' in notes[0].message, notes[0].message
    assert '5 effective cluster(s) of 6' in notes[0].message, notes[0].message
    assert '4 positive' in notes[0].message, notes[0].message
    assert report.failures == []
    # It rides beside a FAILING contrast too: when the stated triple is wrong, the
    # note is what tells the author the right one.
    broken = yaml.safe_load(PAIRED_CONTRAST_MISMATCH.read_text(encoding='utf-8'))
    broken_report = check(broken)
    assert any('sign test' in f.message for f in broken_report.notes)
    assert broken_report.failures != []


def test_cli_prints_the_sign_test_beside_the_contrast():
    proc = _run_cli(PAIRED_CONTRAST)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'INFO [ER-STATS]' in proc.stdout, proc.stdout
    assert 'sign test p=0.3750' in proc.stdout, proc.stdout
    assert '5 effective cluster(s)' in proc.stdout, proc.stdout


def test_subset_scoped_outcome_carries_no_arms_block_at_all():
    # The distinguisher between a full-cell-set outcome and a subset-scoped one is
    # the PRESENCE of `arms`: without it no full-cell-set rule applies, and the
    # outcome states only its clusters and its contrasts.
    rec = base_contrast()
    del rec['results']['signal']['arms']
    report = check(rec)
    assert report.failures == [], report.failures
    assert any('sign test' in f.message for f in report.notes)
    # ER-RECON's denominator sum is an arms rule; it must not fire on the subset.
    assert validate.check_recon(rec) == []


def test_clusters_disagreeing_with_the_arms_block_fails_er_recon():
    rec = base_contrast()
    rec['results']['signal']['clusters']['p1']['with_hint']['numerator'] = 3
    messages = [f.message for f in check(rec).failures if f.code == 'ER-RECON']
    assert any('clusters block sums to 16/24' in m and '17/24' in m for m in messages), messages


def test_cluster_cell_shape_is_gated():
    for mutate in (
        lambda r: r['results']['signal']['clusters']['p2'].__setitem__('control', {'numerator': 2}),
        lambda r: r['results']['signal']['clusters']['p2']['control'].__setitem__('numerator', 9),
        lambda r: r['results']['signal']['clusters']['p2']['control'].__setitem__('denominator', 0),
        lambda r: r['results']['signal']['clusters'].__setitem__('p2', 'not a mapping'),
        lambda r: r['results']['signal'].__setitem__('clusters', []),
    ):
        rec = base_contrast()
        mutate(rec)
        assert 'ER-SCHEMA' in fail_codes(check(rec)), mutate


def test_contrast_shape_is_gated():
    for field, bad in (
        ('name', ''),
        ('arms', ['with_hint']),
        ('arms', 'with_hint - control'),
        ('estimator', 'unpaired_difference'),
        ('estimate', 'about a fifth'),
        ('n_clusters', '6'),
        ('interval', 'roughly -0.10 to 0.52'),
    ):
        rec = base_contrast()
        _contrast(rec)[field] = bad
        assert 'ER-SCHEMA' in fail_codes(check(rec)), (field, bad)
    rec = base_contrast()
    _contrast(rec)['interval']['method'] = 'normal'
    assert 'ER-SCHEMA' in fail_codes(check(rec))
    rec = base_contrast()
    rec['results']['signal']['contrasts'] = []
    assert 'ER-SCHEMA' in fail_codes(check(rec))


def test_non_numeric_interval_alpha_is_a_sentence_not_a_python_error():
    # Without the shape gate a string alpha reaches stats.py and surfaces as
    # "'<' not supported between instances of 'float' and 'str'" -- a stack-shaped
    # message about Python, not a sentence about the record.
    rec = base_contrast()
    _contrast(rec)['interval']['alpha'] = 'ninety-five percent'
    report = check(rec)
    messages = [f.message for f in report.failures if f.code == 'ER-SCHEMA']
    assert any('interval alpha must be a number' in m for m in messages), messages
    assert not any("'<' not supported" in f.message for f in report.failures), report.failures


def test_an_estimator_without_a_recomputation_path_fails_loudly():
    # ER-SCHEMA rejects an estimator outside the enum. This is the other direction:
    # were a second estimator added to the enum without a path in check_contrasts,
    # the gate must refuse rather than check it as if it were a paired difference.
    rec = base_contrast()
    _contrast(rec)['estimator'] = 'ratio_of_rates'
    patched = dict(schema())
    patched['contrast_estimators'] = ['paired_difference', 'ratio_of_rates']
    report = validate.run_checks(rec, schema=patched)
    assert 'ER-SCHEMA' not in fail_codes(report), fail_codes(report)
    messages = [f.message for f in report.failures if f.code == 'ER-STATS']
    assert any('no recomputation path' in m for m in messages), messages


def test_per_arm_wilson_survives_and_stays_recomputed_beside_a_contrast():
    # The per-arm interval is DEMOTED to descriptive, not dropped: it is still
    # recomputed, so a wrong per-arm bound still fails even when the contrast is right.
    rec = base_contrast()
    rec['results']['signal']['arms']['with_hint']['ci']['high'] = 0.99
    messages = [f.message for f in check(rec).failures if f.code == 'ER-STATS']
    assert any('arms.with_hint' in m and 'CI high' in m for m in messages), messages


# --- ER-THREAT --------------------------------------------------------------


def test_er_threat_silent_core_key():
    rec = base_probe()
    del rec['threats']['judge_bias']
    report = check(rec)
    assert 'ER-THREAT' in fail_codes(report)
    assert any('judge_bias' in f.message for f in report.failures if f.code == 'ER-THREAT')


def test_er_threat_custom_requires_statement():
    rec = base_probe()
    rec['threats']['custom_ordering'] = {'status': 'residual'}  # no statement
    assert 'ER-THREAT' in fail_codes(check(rec))


# --- ER-PROBE ---------------------------------------------------------------


def test_er_probe_refuses_confirmatory_verdict():
    rec = base_probe()
    rec['results']['signal']['verdict'] = 'confirmatory_supported'
    report = check(rec)
    assert 'ER-PROBE' in fail_codes(report)
    assert any('measurement' in f.message.lower() for f in report.failures if f.code == 'ER-PROBE')


def test_er_probe_refuses_posterior():
    rec = base_probe()
    rec['updates'] = {'posterior': {'alpha_post': 10, 'beta_post': 4}}
    assert 'ER-PROBE' in fail_codes(check(rec))


# --- ER-LINK ----------------------------------------------------------------


def test_er_link_dangling_prior():
    rec = base_probe()
    rec['updates'] = {'prior': {'source_id': 'no-such-dir/record.yaml'}}
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        assert 'ER-LINK' in fail_codes(check(rec, path))


def test_er_link_resolves():
    rec = base_probe()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / 'prior').mkdir()
        write_record(d / 'prior', base_probe())
        rec['updates'] = {'prior': {'source_id': 'prior/record.yaml'}}
        path = write_record(d, rec)
        assert 'ER-LINK' not in fail_codes(check(rec, path))


# --- ER-PARITY (committed report.md re-parses equal to the record) ----------


def test_er_parity_report_block_disagrees():
    rec = base_probe()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        path = write_record(d, rec)
        # A committed report.md whose embedded typed block disagrees with the record.
        (d / 'report.md').write_text(
            '# report\n\n```yaml\ndisposition:\n  total: 999\n```\n', encoding='utf-8'
        )
        assert 'ER-PARITY' in fail_codes(check(rec, path))


def test_er_parity_report_block_matches():
    rec = base_probe()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        path = write_record(d, rec)
        (d / 'report.md').write_text(
            '# report\n\n```yaml\ndisposition:\n  total: 24\n  completed: 24\n  excluded: 0\n```\n',
            encoding='utf-8',
        )
        assert 'ER-PARITY' not in fail_codes(check(rec, path))


def test_er_parity_no_report_is_fine():
    rec = base_probe()
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        assert 'ER-PARITY' not in fail_codes(check(rec, path))


# --- ER-ANCHOR (temporal chronology via git) --------------------------------


def test_er_anchor_commit_absent_from_history():
    rec = _measurement_record(frozen_commit='0' * 40)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        path = write_record(d, rec)
        _git_commit(d, '2026-01-01T00:00:00')
        assert 'ER-ANCHOR' in fail_codes(check(rec, path))


def test_er_anchor_commit_postdates_run():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        # commit dated AFTER the declared first run -> goalpost moved.
        sha = _git_commit(d, '2026-03-01T00:00:00')
        rec['plan_frozen_at']['commit'] = sha
        write_record(d, rec)
        assert 'ER-ANCHOR' in fail_codes(check(rec, path))


def test_er_anchor_clean_commit_predates_run():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        rec['plan_frozen_at']['commit'] = sha
        write_record(d, rec)
        assert 'ER-ANCHOR' not in fail_codes(check(rec, path))


# --- ER-XCHECK (ledger cross-check + per-tier hand policy) -------------------


def _write_ledger(d: Path, cost: float, n_trials: int) -> Path:
    # Real fathom row shape: the discriminator is `kind`, run rows carry cost_usd_est,
    # trial rows carry verifier_results (a mapping) and status. The gate reads its
    # ledger through from_fathom.summarize_ledger, so the fixture is real-shaped.
    ledger = d / 'ledger'
    ledger.mkdir(exist_ok=True)
    path = ledger / 'rg-2x2.jsonl'
    lines = [json.dumps({'kind': 'run', 'cost_usd_est': cost})]
    for _ in range(n_trials):
        lines.append(
            json.dumps({'kind': 'trial', 'status': 'completed', 'verifier_results': {'ok': True}})
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def test_er_xcheck_cost_diverges():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _write_ledger(d, cost=17.00, n_trials=96)
        rec = _measurement_record()
        rec['run'] = {
            'source': 'ledger',
            'ledger_path': 'ledger/rg-2x2.jsonl',
            'n': 96,
            'cost_usd_est': 25.00,  # diverges beyond max(1%, $0.01)
            'first_run_at': '2026-02-01T00:00:00',
        }
        path = write_record(d, rec)
        assert 'ER-XCHECK' in fail_codes(check(rec, path))


def test_er_xcheck_matches_ledger():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _write_ledger(d, cost=17.00, n_trials=96)
        rec = _measurement_record()
        rec['run'] = {
            'source': 'ledger',
            'ledger_path': 'ledger/rg-2x2.jsonl',
            'n': 96,
            'cost_usd_est': 17.00,
            'first_run_at': '2026-02-01T00:00:00',
        }
        path = write_record(d, rec)
        assert 'ER-XCHECK' not in fail_codes(check(rec, path))


def test_er_xcheck_hand_probe_ok_measurement_warns_decision_fails():
    # probe: source hand is allowed (no finding at all).
    probe = base_probe()
    assert 'ER-XCHECK' not in fail_codes(check(probe))
    assert 'ER-XCHECK' not in warn_codes(check(probe))
    # measurement: source hand is a WARN, not a failure.
    meas = _measurement_record()
    assert 'ER-XCHECK' not in fail_codes(check(meas))
    assert 'ER-XCHECK' in warn_codes(check(meas))
    # decision: source hand without a ledger or attestation is a FAIL.
    dec = _measurement_record()
    dec['tier'] = 'decision'
    assert 'ER-XCHECK' in fail_codes(check(dec))
    dec['run']['attestation'] = 'second party X reviewed the raw transcripts'
    assert 'ER-XCHECK' not in fail_codes(check(dec))


# --- ER-PREREG (frozen-plan reconstruction via git show) --------------------


def test_er_prereg_design_drift():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        # working tree drifts a frozen prereg field after the freeze.
        rec['plan_frozen_at']['commit'] = sha
        rec['design']['cells'][0]['planned_n'] = 50
        write_record(d, rec)
        report = check(rec, path)
        assert 'ER-PREREG' in fail_codes(report)


def test_er_prereg_confirmatory_verdict_on_exploratory_role():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        rec['plan_frozen_at']['commit'] = sha
        rec['results']['footprint']['verdict'] = 'confirmatory_supported'
        write_record(d, rec)
        assert 'ER-PREREG' in fail_codes(check(rec, path))


def test_er_prereg_clean_no_drift():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        rec['plan_frozen_at']['commit'] = sha  # only plan_frozen_at (outside the subset) changes
        write_record(d, rec)
        assert 'ER-PREREG' not in fail_codes(check(rec, path))


def test_er_prereg_not_in_history_downgrades_by_tier():
    # measurement: WARN; decision: FAIL (Q5 hand ladder).
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record(frozen_commit='a' * 40)
        path = write_record(d, rec)
        _git_commit(d, '2026-01-01T00:00:00')
        report = check(rec, path)
        assert 'ER-PREREG' in warn_codes(report)
        assert 'ER-PREREG' not in fail_codes(report)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record(frozen_commit='a' * 40)
        rec['tier'] = 'decision'
        path = write_record(d, rec)
        _git_commit(d, '2026-01-01T00:00:00')
        assert 'ER-PREREG' in fail_codes(check(rec, path))


# --- the frozen COORDINATE: plan_frozen_at.path through a rename -------------


def _relocate(record: dict, old_path: Path, new_dir: Path) -> Path:
    """Move a record to a new directory the way a re-home does, leaving the old
    coordinate reachable only through history."""
    new_dir.mkdir(parents=True, exist_ok=True)
    old_path.unlink()
    return write_record(new_dir, record)


def test_er_prereg_pinned_path_reconstructs_after_a_rename():
    # `git show <commit>:<path>` does not follow renames, so a record relocated after its
    # freeze must pin the path it HAD at the freeze commit or the gate degrades to the
    # not-in-history WARN on the very record that dogfoods it.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        old_dir = d / 'plugins' / 'old-home' / 'skills' / 'sk' / 'examples' / 'rg'
        old_dir.mkdir(parents=True)
        rec = _measurement_record()
        old_path = write_record(old_dir, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        old_rel = 'plugins/old-home/skills/sk/examples/rg/record.yaml'

        rec['plan_frozen_at'] = {
            'commit': sha,
            'path': old_rel,
            'timestamp': '2026-01-01T00:00:00',
        }
        new_path = _relocate(rec, old_path, d / 'plugins' / 'new-home' / 'skills' / 'sk' / 'ex')
        report = check(rec, new_path)
        assert 'ER-PREREG' not in fail_codes(report), report.failures
        assert 'ER-PREREG' not in warn_codes(report), report.warnings

        # Without the pin the same relocated record cannot be reconstructed at all.
        unpinned = copy.deepcopy(rec)
        unpinned['plan_frozen_at'].pop('path')
        write_record(new_path.parent, unpinned)
        assert 'ER-PREREG' in warn_codes(check(unpinned, new_path))


def test_er_prereg_without_a_pin_reconstructs_from_the_current_path():
    # Every v1.0 record predates the field and must keep validating unchanged.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        rec['plan_frozen_at'] = {'commit': sha, 'timestamp': '2026-01-01T00:00:00'}
        write_record(d, rec)
        report = check(rec, path)
        assert 'path' not in rec['plan_frozen_at']
        assert 'ER-PREREG' not in fail_codes(report), report.failures
        assert 'ER-PREREG' not in warn_codes(report), report.warnings


def test_er_prereg_falls_back_when_the_pinned_lookup_fails():
    # The fallback fires on a FAILED lookup, not merely an absent field. A fixture that
    # relocates a pinned record -- the acceptance suite builds its temp repo at the root
    # while validating the delivered record, which carries the pin -- would otherwise go
    # red. The trade: a WRONG pin resolves silently through the current path rather than
    # failing loudly, so the pin is a durability aid, not a second integrity check.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        rec['plan_frozen_at'] = {
            'commit': sha,
            'path': 'plugins/never-existed/examples/rg/record.yaml',
            'timestamp': '2026-01-01T00:00:00',
        }
        write_record(d, rec)
        report = check(rec, path)
        assert 'ER-PREREG' not in fail_codes(report), report.failures
        assert 'ER-PREREG' not in warn_codes(report), report.warnings


def test_er_prereg_names_both_coordinates_when_neither_resolves():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record(frozen_commit='a' * 40)
        rec['plan_frozen_at']['path'] = 'plugins/old-home/examples/rg/record.yaml'
        path = write_record(d, rec)
        _git_commit(d, '2026-01-01T00:00:00')
        report = check(rec, path)
        msgs = [f.message for f in report.warnings if f.code == 'ER-PREREG']
        assert msgs, report.warnings
        assert 'plugins/old-home/examples/rg/record.yaml' in msgs[0], msgs
        assert msgs[0].rstrip().count('record.yaml') == 2, msgs


# --- ER-PREREG / ER-ANCHOR run git from the repo toplevel (Windows MAX_PATH) --------


def test_prereg_git_ops_run_from_repo_toplevel_not_nested_dir():
    # FIX-1 regression (shape test). The commit-reconstruction git ops must run with
    # -C <toplevel>, NOT the record's (deeply nested) dir: on Windows git disambiguates a
    # <sha>:<relpath> argument by stat-ing <cwd>/<sha>, a long nested cwd overflows
    # MAX_PATH, git fatals, and ER-PREREG silently downgrades to the not-in-history WARN.
    # A true long-path repro is impractical in a unit test, so this asserts the shape:
    # every rev/pathspec op targets the toplevel; only the --show-toplevel lookup itself
    # may run from the nested dir (it takes no rev/pathspec argument, so it cannot overflow).
    with tempfile.TemporaryDirectory() as td:
        top = Path(td)
        _git_init(top)
        nested = top / 'plugins' / 'humblepowers' / 'skills' / 'experiment-rigor' / 'examples' / 'z'
        nested.mkdir(parents=True)
        assert nested.resolve() != top.resolve()
        rec = _measurement_record()
        path = write_record(nested, rec)
        sha = _git_commit(top, '2026-01-01T00:00:00')  # commit staged from the repo root
        rec['plan_frozen_at']['commit'] = sha  # only plan_frozen_at (outside the subset) drifts
        write_record(nested, rec)

        calls: list[tuple[Path, tuple[str, ...]]] = []
        real_git = validate._git

        def spy(cwd, *args):
            calls.append((Path(cwd).resolve(), args))
            return real_git(cwd, *args)

        validate._git = spy
        try:
            report = validate.check_prereg(rec, path)
            anchor = validate.check_anchor(rec, path)
        finally:
            validate._git = real_git

        # The gate still verifies cleanly despite the nesting -- no silent downgrade.
        assert [f for f in report if f.level == 'FAIL'] == [], report
        assert anchor == [], anchor

        top_resolved = top.resolve()
        pathspec_ops = [
            (cwd, args)
            for cwd, args in calls
            if args and (args[0] == 'show' or args[:2] == ('rev-parse', '--verify'))
        ]
        assert pathspec_ops, calls  # reconstruction actually happened
        for cwd, args in pathspec_ops:
            assert cwd == top_resolved, (args, cwd, top_resolved)
        # The only op allowed to run from a non-toplevel cwd is the --show-toplevel lookup.
        for cwd, args in calls:
            if cwd != top_resolved:
                assert args[:2] == ('rev-parse', '--show-toplevel'), (cwd, args)


# --- ER-COMPREHEND (decision-tier comprehension block) ----------------------


def _decision_record() -> dict:
    rec = _measurement_record()
    rec['tier'] = 'decision'
    return rec


def _reader(transcript: str, all_correct: bool = True) -> dict:
    correct = dict.fromkeys(
        ('manipulated', 'placement', 'operationalization', 'execution_real'), True
    )
    if not all_correct:
        correct['execution_real'] = False
    return {
        'identity': 'reader-x',
        'family': 'frontier-a',
        'context': 'fresh',
        'answers': {k: f'{k} answer' for k in correct},
        'correct': correct,
        'transcript_path': transcript,
    }


def test_er_comprehend_missing_block():
    rec = _decision_record()
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        assert 'ER-COMPREHEND' in fail_codes(check(rec, path))


def test_er_comprehend_unresolvable_transcript():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rec = _decision_record()
        rec['comprehension'] = {
            'readers': [_reader('transcripts/a.md'), _reader('transcripts/missing.md')],
            'pass': True,
        }
        (d / 'transcripts').mkdir()
        (d / 'transcripts' / 'a.md').write_text('read', encoding='utf-8')
        path = write_record(d, rec)
        assert 'ER-COMPREHEND' in fail_codes(check(rec, path))


def test_er_comprehend_incomplete_reconstruction():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / 'transcripts').mkdir()
        (d / 'transcripts' / 'a.md').write_text('read', encoding='utf-8')
        (d / 'transcripts' / 'b.md').write_text('read', encoding='utf-8')
        rec = _decision_record()
        rec['comprehension'] = {
            'readers': [
                _reader('transcripts/a.md', all_correct=True),
                _reader('transcripts/b.md', all_correct=False),  # misses a question
            ],
            'pass': True,  # claims pass despite a miss
        }
        path = write_record(d, rec)
        assert 'ER-COMPREHEND' in fail_codes(check(rec, path))


def test_er_comprehend_clean():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / 'transcripts').mkdir()
        (d / 'transcripts' / 'a.md').write_text('read', encoding='utf-8')
        (d / 'transcripts' / 'b.md').write_text('read', encoding='utf-8')
        rec = _decision_record()
        rec['comprehension'] = {
            'readers': [_reader('transcripts/a.md'), _reader('transcripts/b.md')],
            'pass': True,
        }
        path = write_record(d, rec)
        assert 'ER-COMPREHEND' not in fail_codes(check(rec, path))


def test_er_comprehend_needs_two_readers():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / 'transcripts').mkdir()
        (d / 'transcripts' / 'a.md').write_text('read', encoding='utf-8')
        rec = _decision_record()
        rec['comprehension'] = {'readers': [_reader('transcripts/a.md')], 'pass': True}
        path = write_record(d, rec)
        assert 'ER-COMPREHEND' in fail_codes(check(rec, path))


# --- CLI exit contract ------------------------------------------------------


def _run_cli(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(HERE / 'validate.py'), str(path), *args],
        capture_output=True,
        text=True,
        cwd=str(path.parent),
    )


def test_cli_exit_zero_on_clean():
    rec = base_probe()
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        proc = _run_cli(path)
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_exit_one_names_code():
    rec = base_probe()
    del rec['threats']['judge_bias']
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        proc = _run_cli(path)
        assert proc.returncode == 1, proc.stdout
        assert 'ER-THREAT' in proc.stdout


def test_cli_schema_only_lists_skips():
    rec = base_probe()
    with tempfile.TemporaryDirectory() as td:
        path = write_record(Path(td), rec)
        proc = _run_cli(path, '--schema-only')
        assert proc.returncode == 0, proc.stdout + proc.stderr
        for code in ('ER-ANCHOR', 'ER-XCHECK', 'ER-PREREG', 'ER-COMPREHEND'):
            assert code in proc.stdout, (code, proc.stdout)


# --- the pre-commit hook shape (FM-6 / Q6) ----------------------------------


def _repo_root() -> Path:
    d = HERE
    while d != d.parent:
        if (d / '.pre-commit-config.yaml').exists():
            return d
        d = d.parent
    raise AssertionError('no .pre-commit-config.yaml found above the test')


def _record_hook() -> dict:
    cfg = yaml.safe_load((_repo_root() / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    for repo in cfg['repos']:
        for hook in repo.get('hooks', []):
            if 'validate.py' in hook.get('entry', '') and 'experiment-rigor' in hook.get(
                'entry', ''
            ):
                return hook
    raise AssertionError('experiment-rigor validate.py hook not found in .pre-commit-config.yaml')


def _hook_by_id(hook_id: str) -> dict:
    cfg = yaml.safe_load((_repo_root() / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    for repo in cfg['repos']:
        for hook in repo.get('hooks', []):
            if hook.get('id') == hook_id:
                return hook
    raise AssertionError(f'hook {hook_id!r} not found in .pre-commit-config.yaml')


TRAVELLING_BASE = 'plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2'
PRE_MOVE_RECORD = 'plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml'
# The evals alternative is what keeps a detector's own pre-registration inside the gate;
# dropping it while repointing the plugin half would silence the gate with no error.
EVALS_RECORD = 'evals/experiments/act-hint/record.yaml'
EVALS_REPORT = 'evals/experiments/act-hint/report.md'


def test_hook_uses_files_and_pass_filenames():
    import re

    hook = _record_hook()
    assert hook.get('pass_filenames') is True, hook
    assert hook.get('always_run') is not True, hook
    regex = hook['files']
    for travelling in (f'{TRAVELLING_BASE}/record.yaml', EVALS_RECORD):
        assert re.search(regex, travelling), (regex, travelling)
    assert not re.search(regex, 'docs/design/some-experiment/record.yaml'), regex
    # The pre-move coordinate must NOT still be selected: a regex matching both homes
    # would let the re-home read green while the gate points at a directory that is gone.
    assert not re.search(regex, PRE_MOVE_RECORD), regex


def test_both_record_hooks_run_the_moved_scripts():
    for hook_id, script in (
        ('experiment-rigor-validate', 'validate.py'),
        ('experiment-rigor-render-check', 'render.py'),
    ):
        entry = _hook_by_id(hook_id).get('entry', '')
        needle = f'plugins/experiment-discipline/skills/experiment-rigor/scripts/{script}'
        assert needle in entry, (hook_id, entry)


def test_run_tests_hook_carries_pyyaml():
    # F1: the record-parsing suites hard-fail (never skip) without PyYAML, so the
    # pre-push run-tests hook must run under --with pyyaml or the gate goes red.
    hook = _hook_by_id('run-tests')
    assert '--with pyyaml' in hook.get('entry', ''), hook.get('entry')


def test_render_check_hook_matches_both_pair_members():
    # F3: the render-check hook must reach a staged report.md whose record.yaml was
    # not restaged, so its files: regex matches BOTH members of the travelling pair.
    import re

    hook = _hook_by_id('experiment-rigor-render-check')
    assert hook.get('pass_filenames') is True, hook
    assert hook.get('always_run') is not True, hook
    regex = hook['files']
    for member in (
        f'{TRAVELLING_BASE}/record.yaml',
        f'{TRAVELLING_BASE}/report.md',
        EVALS_RECORD,
        EVALS_REPORT,
        'evals/some-exp/report.md',
    ):
        assert re.search(regex, member), (regex, member)
    assert not re.search(regex, 'docs/design/some-experiment/report.md'), regex
    assert not re.search(regex, PRE_MOVE_RECORD), regex


# --- review-round regression fixtures (F1-F10; reviewer's exact mutations) ---


def test_f1_measurement_arm_without_ci():
    # F1: at measurement/decision every reported rate carries a structured CI.
    rec = _measurement_record()
    del rec['results']['footprint']['arms']['with_gate']['ci']
    codes = {f.code for f in validate.check_stats(rec, schema())}
    assert 'ER-STATS' in codes


def test_f2_measurement_outcome_without_operationalization():
    rec = _measurement_record()
    del rec['outcomes'][0]['operationalization']
    codes = {f.code for f in validate.check_schema(rec, schema())}
    assert 'ER-SCHEMA' in codes


def test_f3_probe_refuses_nested_posterior_under_updates():
    rec = base_probe()
    rec['updates'] = {'prior': {'posterior': {'alpha_post': 10, 'beta_post': 4}}}
    assert 'ER-PROBE' in fail_codes(check(rec))


def test_f3_probe_refuses_posterior_under_results():
    rec = base_probe()
    rec['results']['signal']['updates'] = {'posterior': {'alpha_post': 10, 'beta_post': 4}}
    assert 'ER-PROBE' in fail_codes(check(rec))


def test_f4_directory_as_transcript_fails():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # a DIRECTORY named like a transcript is not a read.
        (d / 'transcripts').mkdir()
        (d / 'transcripts' / 'a.md').mkdir()  # directory, not a file
        (d / 'transcripts' / 'b.md').write_text('read', encoding='utf-8')
        rec = _decision_record()
        rec['comprehension'] = {
            'readers': [_reader('transcripts/a.md'), _reader('transcripts/b.md')],
            'pass': True,
        }
        path = write_record(d, rec)
        assert 'ER-COMPREHEND' in fail_codes(check(rec, path))


def test_f5_prose_ci_rejected():
    rec = base_probe()
    rec['results']['signal']['arms']['arm_a']['ci'] = 'about 47% to 91%'
    codes = {f.code for f in validate.check_stats(rec, schema())}
    assert 'ER-STATS' in codes


def test_f6_legit_amendment_passes():
    # The amendment references a SEPARATE real commit, identical frozen-vs-current, so
    # excluding amendments from the wholesale diff is the only thing keeping this clean —
    # the chronology check is what could still flag it, and here it must not.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        (d / 'amend.txt').write_text('wave-2 amendment', encoding='utf-8')
        amend_sha = _git_commit(d, '2026-01-10T00:00:00', msg='amend')
        rec = _measurement_record()
        rec['analysis_plan']['amendments'] = [
            {
                'commit': amend_sha,
                'timestamp': '2026-01-10T00:00:00',
                'scope': 'wave-2',
                'governs_first_run_at': '2026-02-15T00:00:00',
            }
        ]
        path = write_record(d, rec)
        freeze_sha = _git_commit(d, '2026-01-20T00:00:00', msg='freeze')
        rec['plan_frozen_at']['commit'] = freeze_sha
        write_record(d, rec)
        assert 'ER-PREREG' not in fail_codes(check(rec, path))


def test_f6_fabricated_amendment_timestamp_fails():
    # Amendment identical frozen-vs-current (so the wholesale diff sees nothing); only
    # the new per-amendment chronology check catches the 2099 timestamp.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        (d / 'amend.txt').write_text('amendment', encoding='utf-8')
        amend_sha = _git_commit(d, '2026-01-10T00:00:00', msg='amend')
        rec = _measurement_record()
        rec['analysis_plan']['amendments'] = [
            {'commit': amend_sha, 'timestamp': '2099-01-01T00:00:00', 'scope': 'wave-2'}
        ]
        path = write_record(d, rec)
        freeze_sha = _git_commit(d, '2026-01-20T00:00:00', msg='freeze')
        rec['plan_frozen_at']['commit'] = freeze_sha
        write_record(d, rec)
        assert 'ER-PREREG' in fail_codes(check(rec, path))


def test_f6_fabricated_amendment_commit_not_in_history_fails():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        rec['analysis_plan']['amendments'] = [
            {
                'commit': 'f' * 40,  # identical frozen-vs-current; simply not a real commit
                'timestamp': '2026-01-10T00:00:00',
                'scope': 'wave-2',
                'governs_first_run_at': '2026-02-15T00:00:00',
            }
        ]
        path = write_record(d, rec)
        freeze_sha = _git_commit(d, '2026-01-20T00:00:00', msg='freeze')
        rec['plan_frozen_at']['commit'] = freeze_sha
        write_record(d, rec)
        assert 'ER-PREREG' in fail_codes(check(rec, path))


def test_f7_post_freeze_outcome_needs_quarantine():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        _git_init(d)
        rec = _measurement_record()
        path = write_record(d, rec)
        sha = _git_commit(d, '2026-01-01T00:00:00')
        rec['plan_frozen_at']['commit'] = sha
        # an outcome absent from the frozen set, role confirmatory, no added_after_freeze,
        # carrying a NON-confirmatory verdict — F7 must still fire.
        rec['outcomes'].append(
            {'name': 'sneaky', 'role': 'confirmatory', 'operationalization': 'a post-hoc slice'}
        )
        rec['results']['sneaky'] = {
            'verdict': 'exploratory_signal',
            'paired': True,
            'arms': {
                'with_gate': {
                    'numerator': 30,
                    'denominator': 48,
                    'ci': {'method': 'wilson', 'alpha': 0.05, 'low': 0.4836, 'high': 0.7478},
                },
                'without_gate': {
                    'numerator': 20,
                    'denominator': 48,
                    'ci': {'method': 'wilson', 'alpha': 0.05, 'low': 0.2885, 'high': 0.5572},
                },
            },
        }
        write_record(d, rec)
        assert 'ER-PREREG' in fail_codes(check(rec, path))


def test_f8_partial_schema_empty_threat_enum_raises():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'schema.json'
        p.write_text(json.dumps({'threat_enum': []}), encoding='utf-8')
        try:
            validate.load_schema(override=p)
        except validate.SchemaError:
            return
        raise AssertionError('expected SchemaError on an emptied threat_enum')


def test_f8_partial_schema_missing_tier_raises():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'schema.json'
        # required_fields present but missing the decision tier.
        p.write_text(
            json.dumps({'required_fields': {'probe': ['tier'], 'measurement': ['tier']}}),
            encoding='utf-8',
        )
        try:
            validate.load_schema(override=p)
        except validate.SchemaError:
            return
        raise AssertionError('expected SchemaError on required_fields missing a tier')


def test_f9_rate_outside_a_well_formed_arm():
    rec = base_probe()
    rec['results']['loose'] = {'rate': 0.6, 'verdict': 'exploratory_signal'}
    codes = {f.code for f in validate.check_schema(rec, schema())}
    assert 'ER-SCHEMA' in codes


def test_f10_refused_method_message_scoping():
    # den < 30: the small-n rule is named.
    small = base_probe()
    small['results']['signal']['arms']['arm_a']['ci']['method'] = 'normal'  # den 12
    msgs = [f.message for f in validate.check_stats(small, schema()) if f.code == 'ER-STATS']
    assert any('small-n' in m and '< 30' in m for m in msgs), msgs
    # den >= 30: refused all the same, but the small-n rule is NOT named.
    big = _measurement_record()
    big['results']['footprint']['arms']['with_gate']['ci']['method'] = 'normal'  # den 48
    msgs = [f.message for f in validate.check_stats(big, schema()) if f.code == 'ER-STATS']
    assert msgs and all('small-n' not in m and '< 30' not in m for m in msgs), msgs


# --- re-verification residual gaps (N1, N2) ---------------------------------


def test_n1_top_level_rate_beside_valid_arms():
    # A contradicting top-level results.<o>.rate must not escape just because the
    # outcome also carries well-formed arms.
    rec = base_probe()
    rec['results']['signal']['rate'] = 0.99
    codes = {f.code for f in validate.check_schema(rec, schema())}
    assert 'ER-SCHEMA' in codes


def test_n2_probe_refuses_root_level_posterior():
    rec = base_probe()
    rec['posterior'] = {'alpha_post': 10, 'beta_post': 4}
    assert 'ER-PROBE' in fail_codes(check(rec))


# ---------------------------------------------------------------------------

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
    print('ok: all validate tests passed')

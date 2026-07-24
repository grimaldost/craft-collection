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
    ledger = d / 'ledger'
    ledger.mkdir(exist_ok=True)
    path = ledger / 'rg-2x2.jsonl'
    lines = [f'{{"type": "run", "cost_usd_est": {cost}}}']
    for _ in range(n_trials):
        lines.append('{"type": "trial", "verifier_results": [{"passed": true}]}')
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


def test_hook_uses_files_and_pass_filenames():
    import re

    hook = _record_hook()
    assert hook.get('pass_filenames') is True, hook
    assert hook.get('always_run') is not True, hook
    regex = hook['files']
    travelling = 'plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2/record.yaml'
    assert re.search(regex, travelling), (regex, travelling)
    assert not re.search(regex, 'docs/design/some-experiment/record.yaml'), regex


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

"""Acceptance test for the founding RG-2x2 dogfood fixture (spec section 5).

Two halves, both against a REAL freeze commit built in a temp git repo (the same
pattern test_validate.py uses for its ER-ANCHOR / ER-PREREG gates):

  1. The six-defect regression fixture. A seeded variant of the RG-2x2 record
     carrying EXACTLY the case's six known defects makes validate.py exit 1, naming
     all six by error code; the corrected record (the real fixture run through the
     real finalize step) exits 0 with render.py --check showing no drift.
  2. The decision-tier comprehension gate. A decision record missing the block, and
     one with a reader reconstructing fewer than four questions, each exit 1
     (ER-COMPREHEND); a complete decision record with resolving transcript files and a
     second-party attestation exits 0.

PyYAML is a HARD dependency (the record is nested YAML): this module refuses to run --
and never emits the `skip:` sentinel -- when PyYAML is absent, so the mechanism spine
cannot go green-via-skip.
"""

from __future__ import annotations

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on a broken toolchain
    print('FAIL: PyYAML is required for the RG-2x2 acceptance test (mechanism spine must not skip)')
    raise SystemExit(1) from None

import copy
import os
import re
import subprocess
import sys
from pathlib import Path

import render
import validate

HERE = Path(__file__).resolve().parent
EXAMPLE_DIR = HERE.parent / 'examples' / 'rg-2x2'
# The delivered record. Post-freeze-choreography this is the FINALIZED record; the frozen
# pre-registration lives at plan_frozen_at.commit and is reconstructed below.
DELIVERED_RECORD = EXAMPLE_DIR / 'record.yaml'
FROZEN_RECORD = DELIVERED_RECORD  # back-compat alias for the temp-repo helpers below

sys.path.insert(0, str(EXAMPLE_DIR))
import finalize  # noqa: E402 - path inserted just above

FREEZE_DATE = '2026-07-24T00:00:00Z'

# The six defects and the code each must fire (the section-5 map).
EXPECTED_DEFECT_CODES = {'ER-RECON', 'ER-SCHEMA', 'ER-STATS', 'ER-PREREG'}


# --- git helpers (mirroring test_validate.py) -------------------------------


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


def _freeze_commit(d: Path, record: dict, *, tier: str | None = None) -> tuple[Path, str]:
    """Init a temp repo, write the FROZEN pre-registration as record.yaml, commit it at
    the pinned freeze date, and return (record_path, freeze_sha). The frozen record is
    what `git show <sha>:record.yaml` reconstructs, so its prereg subset is the anchor."""
    _git(d, 'init', '-q')
    frozen = copy.deepcopy(record)
    frozen.pop('results', None)
    frozen.pop('updates', None)
    frozen.get('analysis_plan', {}).pop('amendments', None)
    frozen.setdefault('plan_frozen_at', {})['commit'] = 'PENDING'
    if tier is not None:
        frozen['tier'] = tier
    path = d / 'record.yaml'
    path.write_text(yaml.safe_dump(frozen, sort_keys=False), encoding='utf-8')
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
        'freeze',
        env={'GIT_AUTHOR_DATE': FREEZE_DATE, 'GIT_COMMITTER_DATE': FREEZE_DATE},
    )
    return path, _git(d, 'rev-parse', 'HEAD').stdout.strip()


def _load_frozen() -> dict:
    return yaml.safe_load(FROZEN_RECORD.read_text(encoding='utf-8'))


def _fail_codes(report: validate.Report) -> set[str]:
    return {f.code for f in report.failures}


def _warn_codes(report: validate.Report) -> set[str]:
    return {f.code for f in report.warnings}


def _run_cli(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(HERE / 'validate.py'), str(path), *args],
        capture_output=True,
        text=True,
        cwd=str(path.parent),
    )


def _tempdir():
    import tempfile

    return tempfile.TemporaryDirectory()


# --- the delivered fixture is a clean, frozen measurement record ------------


def test_delivered_record_is_finalized_with_reconstructible_freeze():
    # Post-choreography truth: the freeze happened for real (stage 1 -> plan_frozen_at.commit,
    # stage 2 -> the finalized pair on the branch), so the delivered record.yaml is FINALIZED.
    # The frozen pre-registration now lives at the freeze commit; this test reconstructs it via
    # the EXACT path ER-PREREG uses -- dogfooding that path -- and asserts the frozen invariants.
    record = _load_frozen()  # the delivered (now finalized) record

    # (a) a finalized measurement record with a REAL freeze SHA, not PENDING.
    assert record['tier'] == 'measurement', record['tier']  # R3-2: tier pinned to measurement
    commit = record['plan_frozen_at']['commit']
    assert re.fullmatch(r'[0-9a-f]{40}', str(commit)), f'expected a real freeze SHA, got {commit!r}'
    assert 'results' in record, 'delivered record is finalized (results present)'
    assert record['disposition']['total'] == 96
    assert sum(c['planned_n'] for c in record['design']['cells']) == 96  # 8 cells x 12

    # (b) reconstruct the FROZEN state exactly as ER-PREREG does: git show
    # <plan_frozen_at.commit>:<coordinate>, run from the repo toplevel, resolving the
    # coordinate through validate.frozen_coordinates so the fixture and the gate cannot
    # drift. `git show` does not follow renames, so the pinned path -- the path the record
    # HAD at the freeze commit -- is what survives the re-home; the current path is only
    # the fallback. Fail LOUD (never skip) if the history is unavailable (shallow/broken
    # clone), so a missing freeze is a hard failure, not a silent pass.
    toplevel = validate._repo_toplevel(DELIVERED_RECORD.parent)
    assert toplevel is not None, 'not under a git repo -- cannot reconstruct the frozen state'
    relpath = validate._repo_relpath(toplevel, DELIVERED_RECORD)
    assert relpath is not None, 'record is not under the repo toplevel'
    pinned = record['plan_frozen_at'].get('path')
    assert pinned, 'the delivered record must pin its freeze-time coordinate'
    coords = validate.frozen_coordinates(record, relpath)
    assert coords[0] == pinned, coords
    # Two different failures hide behind one lookup, so each gets its own message.
    # (i) the freeze OBJECT is absent -- a shallow clone. That is a checkout-depth
    # problem, not a bad pin. Expected to fail here, loudly: the fix is depth (CI pins
    # fetch-depth: 0 and the keep-ref tag holds the commit reachable), never a skip.
    assert validate._commit_in_history(toplevel, str(commit)), (
        f'freeze commit {commit} is absent from this checkout -- a shallow clone cannot '
        'reconstruct the freeze. The fix is depth (CI pins fetch-depth: 0; the keep-ref '
        'tag keeps the commit reachable across a squash-merge), never a skip'
    )
    # (ii) the pin itself is wrong. It must resolve ON ITS OWN, not via the gate's
    # lenient fallback: the gate tolerates a wrong pin, this fixture does not.
    assert validate._show_at(toplevel, str(commit), pinned) is not None, (
        f'plan_frozen_at.path {pinned!r} does not resolve at {commit} -- a wrong pin '
        'resolves silently through the current path in the gate, so it is checked here'
    )
    frozen, tried = validate._reconstruct_frozen(toplevel, str(commit), record, relpath)
    assert frozen is not None, (
        f'git show {commit}:{" / ".join(tried)} failed -- freeze history unavailable '
        '(fail loud, no skip)'
    )
    # The historical frozen version carries the pre-registration only.
    assert 'results' not in frozen, frozen.get('results')
    assert 'posterior' not in (frozen.get('updates') or {}), frozen.get('updates')
    assert frozen['disposition'] == {'total': 96}, frozen['disposition']

    # (c) full validate on the delivered (finalized) record exits 0 with exactly the one
    # source:hand WARN (the honest measurement-tier state), no failures.
    report = validate.run_checks(record, DELIVERED_RECORD)
    assert report.failures == [], report.failures
    assert _warn_codes(report) == {'ER-XCHECK'}, _warn_codes(report)

    # (d) the committed report.md is in sync with the delivered record.
    assert render.check_drift(DELIVERED_RECORD) is None


# --- the corrected record exits 0 against a real freeze ----------------------


def test_corrected_record_validates_and_has_no_drift():
    with _tempdir() as td:
        d = Path(td)
        _, sha = _freeze_commit(d, _load_frozen())
        finalized = finalize.finalize_record(_load_frozen(), sha)
        path = d / 'record.yaml'
        path.write_text(yaml.safe_dump(finalized, sort_keys=False), encoding='utf-8')
        (d / 'report.md').write_text(render.render_report(finalized), encoding='utf-8')

        report = validate.run_checks(finalized, path)
        assert report.failures == [], report.failures
        # source: hand at measurement is the honest state -- a WARN, not a failure.
        assert _warn_codes(report) == {'ER-XCHECK'}, _warn_codes(report)
        assert render.check_drift(path) is None
        # The activation outcome is the confirmatory one that FAILED (confirmatory_null);
        # the footprint is the quarantined exploratory one carrying the posterior.
        assert finalized['results']['activation']['verdict'] == 'confirmatory_null'
        assert finalized['results']['footprint']['verdict'] == 'exploratory_signal'
        assert finalized['outcomes'][1]['role'] == 'exploratory'
        # FIX-3: finalize adds the observed disposition; it reconciles (96 == 96).
        assert finalized['disposition'] == {'total': 96, 'completed': 96, 'excluded': 0}
        amd = finalized['analysis_plan']['amendments'][0]
        assert amd['commit'] == sha and amd['scope'] == 'wave-2'

        proc = _run_cli(path)
        assert proc.returncode == 0, proc.stdout + proc.stderr


# --- the six-defect regression fixture exits 1 naming all six ----------------


def _seed_six_defects(finalized: dict) -> dict:
    """Seed EXACTLY the case's six defects. #3 (missing denominators) and #6 (absent ci)
    live on DISTINCT footprint arms: a malformed-count arm short-circuits the CI check,
    so co-locating them would hide #6."""
    d = copy.deepcopy(finalized)
    d['disposition'] = {
        'completed': 48,
        'excluded': 0,
        'total': 48,
    }  # (1) wave omission -> ER-RECON
    del d['outcomes'][0]['operationalization']  # (2) un-operationalized outcome -> ER-SCHEMA
    del d['results']['footprint']['arms']['without_gate']['numerator']  # (3) missing
    del d['results']['footprint']['arms']['without_gate']['denominator']  # (3) denoms -> ER-SCHEMA
    del d['results']['footprint']['paired']  # (4) paired undeclared -> ER-STATS
    d['results']['footprint']['verdict'] = 'confirmatory_supported'  # (5) post-hoc -> ER-PREREG
    del d['results']['footprint']['arms']['with_gate'][
        'ci'
    ]  # (6) absent ci, distinct arm -> ER-STATS
    return d


def test_six_defect_fixture_exits_one_naming_all_six():
    with _tempdir() as td:
        d = Path(td)
        path, sha = _freeze_commit(d, _load_frozen())
        finalized = finalize.finalize_record(_load_frozen(), sha)
        defect = _seed_six_defects(finalized)
        # No report.md beside it -> the parity gate is silent; only the six seeded codes fire.
        path.write_text(yaml.safe_dump(defect, sort_keys=False), encoding='utf-8')

        report = validate.run_checks(defect, path)
        codes = _fail_codes(report)
        assert codes == EXPECTED_DEFECT_CODES, codes

        msgs = [f.message for f in report.failures]

        def named(pred) -> bool:
            return any(pred(m) for m in msgs)

        # (1) ER-RECON: declared cells (96) vs the wave-omitted disposition (48).
        assert named(lambda m: '96' in m and '48' in m)
        # (2) ER-SCHEMA: the un-operationalized outcome.
        assert named(lambda m: 'operationalization' in m and 'activation' in m)
        # (3) ER-SCHEMA: the missing footprint denominators on without_gate.
        assert named(lambda m: 'without_gate' in m and 'numerator' in m)
        # (4) ER-STATS: the undeclared paired comparison.
        assert named(lambda m: 'paired' in m and 'footprint' in m)
        # (5) ER-PREREG: confirmatory verdict on the exploratory-frozen footprint.
        assert named(lambda m: 'confirmatory verdict' in m and 'footprint' in m)
        # (6) ER-STATS: the absent ci on the OTHER arm (with_gate), distinct from #3.
        assert named(lambda m: 'with_gate' in m and 'confidence interval' in m)

        proc = _run_cli(path)
        assert proc.returncode == 1, proc.stdout
        for code in EXPECTED_DEFECT_CODES:
            assert code in proc.stdout, (code, proc.stdout)


# --- decision-tier comprehension fixtures (section 5, deliverable e) ---------


def _reader(name: str, transcript: str, *, all_correct: bool = True) -> dict:
    correct = dict.fromkeys(
        ('manipulated', 'placement', 'operationalization', 'execution_real'), True
    )
    if not all_correct:
        correct['execution_real'] = False
    return {
        'identity': name,
        'family': 'frontier',
        'context': 'fresh',
        'answers': {k: f'{name} recovered {k}' for k in correct},
        'correct': correct,
        'transcript_path': transcript,
    }


def _decision_finalized(d: Path) -> tuple[dict, Path, str]:
    """Freeze a decision-tier pre-registration and finalize it. The decision tier turns
    source:hand into an ER-XCHECK FAIL, so a second-party attestation is attached."""
    path, sha = _freeze_commit(d, _load_frozen(), tier='decision')
    finalized = finalize.finalize_record(_load_frozen(), sha)
    finalized['tier'] = 'decision'
    finalized['run']['attestation'] = (
        'a second party reviewed the raw transcripts and the workspace'
    )
    return finalized, path, sha


def test_decision_missing_comprehension_block_exits_one():
    with _tempdir() as td:
        d = Path(td)
        finalized, path, _ = _decision_finalized(d)
        path.write_text(yaml.safe_dump(finalized, sort_keys=False), encoding='utf-8')
        report = validate.run_checks(finalized, path)
        assert 'ER-COMPREHEND' in _fail_codes(report), _fail_codes(report)
        assert _run_cli(path).returncode == 1


def test_decision_reader_below_four_of_four_exits_one():
    with _tempdir() as td:
        d = Path(td)
        finalized, path, _ = _decision_finalized(d)
        (d / 'transcripts').mkdir()
        (d / 'transcripts' / 'a.md').write_text('reader a transcript', encoding='utf-8')
        (d / 'transcripts' / 'b.md').write_text('reader b transcript', encoding='utf-8')
        finalized['comprehension'] = {
            'readers': [
                _reader('reader-a', 'transcripts/a.md', all_correct=True),
                _reader('reader-b', 'transcripts/b.md', all_correct=False),  # misses a question
            ],
            'pass': True,  # claims pass despite a reader below 4/4
        }
        path.write_text(yaml.safe_dump(finalized, sort_keys=False), encoding='utf-8')
        report = validate.run_checks(finalized, path)
        assert 'ER-COMPREHEND' in _fail_codes(report), _fail_codes(report)
        assert _run_cli(path).returncode == 1


def test_decision_complete_record_exits_zero():
    with _tempdir() as td:
        d = Path(td)
        finalized, path, _ = _decision_finalized(d)
        (d / 'transcripts').mkdir()
        # Fabricated-but-labeled transcripts, written as real resolving files.
        for name in ('a', 'b'):
            (d / 'transcripts' / f'{name}.md').write_text(
                f'# Fresh-context reader {name} (fabricated fixture transcript)\n'
                'Reconstructed the manipulation, its placement, the operationalization, '
                'and confirmed execution was real.\n',
                encoding='utf-8',
            )
        finalized['comprehension'] = {
            'readers': [
                _reader('reader-a', 'transcripts/a.md'),
                _reader('reader-b', 'transcripts/b.md'),
            ],
            'pass': True,
        }
        path.write_text(yaml.safe_dump(finalized, sort_keys=False), encoding='utf-8')
        (d / 'report.md').write_text(render.render_report(finalized), encoding='utf-8')
        report = validate.run_checks(finalized, path)
        assert report.failures == [], report.failures
        assert render.check_drift(path) is None
        assert _run_cli(path).returncode == 0


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
    print('ok: all RG-2x2 acceptance tests passed')

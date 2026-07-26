"""Drive finalize.py end to end on SYNTHETIC runs, before a paid one exists.

The real record is never written to. The end-to-end cases stage a throwaway git repo that
mirrors the repo layout the gates read -- the record under `evals/experiments/act-hint/`
with its frozen materials beside it, the RG-2x2 chain prior where
`updates.prior.source_id` points -- commit the frozen pre-registration at a fixed date,
and finalize a COPY against that commit. So `ER-ANCHOR`, `ER-PREREG` and `ER-LINK` do
their real work here rather than being skipped, which is the only way this suite can
claim the finalize step reaches a clean validate. Cases that ask only what the pure core
computes go through `finalize_pure` instead: staging is the expensive part, and a case
that does not need the context gates should not pay for them.

The synthetic responses are the FROZEN hand-labeled texts (`oracle_labels.json`), so what
the oracle returns for each one is already pinned by `test_oracle.py` and no case has to
assume its own scoring.

The cases:

  1. a zero-exclusion run -- the arms branch, validate exit 0, every pre-registered
     contrast in its own pair-scoped block, and a report carrying the contrast table, the
     2x2 breakdown, the tax and the selected interpretation;
  2. a run WITH exclusions -- the contrasts-only branch, no descriptive Wilson anywhere,
     and the CONTRAST-scoped drop-out: a prompt dead in one arm leaves the contrasts that
     use that arm and stays in the ones that do not;
  3. a ceiling-halted run -- the stricter complete-prompt-pairs fallback, per contrast,
     with the per-pair survivor counts re-derived from the log rather than hardcoded;
  4. idempotence -- twice through finalize is byte-identical, in both members of the pair;
  5. a tampered material -- refused before anything is written;
  6. interpretation selection -- data built to land on each pre-committed leg, plus the two
     frozen qualifiers: ALIKE (both arms move, the secondary separates content anyway) and
     NO HEADROOM (scoped to the null, silent under a leg that moved);
  7. the A/A calibration moving -- recorded as instrument noise, never as a signal;
  8. the producer -> consumer interface -- run_arms' own row, scored by finalize;
  9. the exclusion rule's load-bearing half -- a decline for lack of a tool is scored;
 10. the refusals -- duplicate keys, an over-count, and too few surviving clusters;
 11. render degradation -- a record with no contrasts grows no empty scaffolding.

Runnable with pytest or `python test_finalize.py`; needs PyYAML.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / 'plugins' / 'experiment-discipline' / 'skills' / 'experiment-rigor' / 'scripts'
RG2X2 = SCRIPTS.parent / 'examples' / 'rg-2x2' / 'record.yaml'

for extra in (str(HERE), str(SCRIPTS)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

try:
    import yaml
except ImportError:  # pragma: no cover - the runner supplies PyYAML
    print('skip: PyYAML not installed')
    sys.exit(0)

import finalize  # noqa: E402 - after the path fix
import render  # noqa: E402
import validate  # noqa: E402

RECORD_PATH = HERE / 'record.yaml'
RECORD: dict[str, Any] = yaml.safe_load(RECORD_PATH.read_text(encoding='utf-8'))
BANK: list[dict[str, Any]] = json.loads((HERE / 'bank.json').read_text(encoding='utf-8'))['prompts']
LABELS: list[dict[str, Any]] = json.loads(
    (HERE / 'oracle_labels.json').read_text(encoding='utf-8')
)['labels']
ARMS = finalize.arms_of(RECORD)
RECORD_RELDIR = 'evals/experiments/act-hint'

# The staged freeze date and the synthetic run window. ER-ANCHOR fails when the freeze
# commit postdates the first run, so the runs sit after the freeze -- the real order.
FREEZE_DATE = '2026-08-01T00:00:00Z'
FIRST_RUN_AT = '2026-08-06T00:00:00Z'
FIRST_TS = int(datetime.fromisoformat(FIRST_RUN_AT.replace('Z', '+00:00')).timestamp())
ORDER_SEED = 20260725  # the frozen run's own seed, so the synthetic log interleaves like it

MATERIAL_FILES = (
    'bank.json',
    'firing_table.json',
    'verify.py',
    'oracle_patterns.json',
    'oracle_labels.json',
)
RULE_FILES = ('control.json', 'narrow.json', 'wide.json', 'inert.json')


def _labeled(state: str) -> str:
    """A frozen hand-labeled response in the given 2x2 state (English, first match)."""
    return next(
        item['text']
        for item in LABELS
        if item['expected_state'] == state and item['id'].startswith('en-')
    )


TEXT = {state: _labeled(state) for state in ('both', 'line_only', 'skeleton_only', 'neither')}


def _labeled_by_id(label_id: str) -> str:
    return next(item['text'] for item in LABELS if item['id'] == label_id)


# The DECLINE: a response that refuses the shape and answers anyway ("you asked me to run
# something, so here is what came back"). The frozen exclusion rule scores it as written --
# it is neither a harness error nor an empty response -- and 10 of the 12 decoys ask for
# actions every arm is denied, so this is the modal decoy response, not an edge case.
DECLINE_TEXT = _labeled_by_id('en-neither-02')


# --- staging a throwaway repo the context gates can actually read -------------


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


def _check(proc: subprocess.CompletedProcess) -> subprocess.CompletedProcess:
    """A git step that fails must say so here. Left unchecked it would surface much later
    as a gate complaining about the record, which is the wrong story about the wrong
    thing -- and, intermittently, as a flaky suite."""
    if proc.returncode != 0:
        raise AssertionError(f'staging git step failed: {proc.stderr.strip() or proc.stdout}')
    return proc


def stage(root: Path, runs: list[dict[str, Any]]) -> Path:
    """Lay out a temp repo mirroring the real one, commit the frozen record at
    FREEZE_DATE, and return the path of the working record to finalize."""
    record_dir = root / RECORD_RELDIR
    (record_dir / 'rules').mkdir(parents=True)
    for name in MATERIAL_FILES:
        shutil.copy2(HERE / name, record_dir / name)
    for name in RULE_FILES:
        shutil.copy2(HERE / 'rules' / name, record_dir / 'rules' / name)
    prior_dir = root / 'plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2'
    prior_dir.mkdir(parents=True)
    shutil.copy2(RG2X2, prior_dir / 'record.yaml')

    frozen = copy.deepcopy(RECORD)
    frozen['plan_frozen_at'] = {
        'commit': 'PENDING',
        'path': f'{RECORD_RELDIR}/record.yaml',
        'timestamp': FREEZE_DATE,
    }
    record_path = record_dir / 'record.yaml'
    record_path.write_text(
        yaml.safe_dump(frozen, sort_keys=False, allow_unicode=False, width=100),
        encoding='utf-8',
        newline='\n',
    )
    _check(_git(root, 'init', '-q'))
    _check(_git(root, 'add', '-A'))
    _check(
        _git(
            root,
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
    )
    sha = _check(_git(root, 'rev-parse', 'HEAD')).stdout.strip()
    # A staging step that half-worked would surface later as an ER-ANCHOR failure about
    # the record, which is the wrong story about the wrong thing.
    assert len(sha) == 40, f'the staged freeze commit is not a SHA: {sha!r}'

    # Stage 2 of the choreography, in miniature: the working record names the real commit.
    working = copy.deepcopy(frozen)
    working['plan_frozen_at']['commit'] = sha
    record_path.write_text(
        yaml.safe_dump(working, sort_keys=False, allow_unicode=False, width=100),
        encoding='utf-8',
        newline='\n',
    )
    (record_dir / 'report.md').write_text(
        render.render_report(working, record_path), encoding='utf-8', newline='\n'
    )
    with (record_dir / 'runs.jsonl').open('w', encoding='utf-8', newline='\n') as fh:
        for row in runs:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    return record_path


def run_finalize(record_path: Path, *argv: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = finalize.main(['--record', str(record_path), *argv])
    return code, buffer.getvalue()


def _tempdir():
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


# --- synthetic run logs -------------------------------------------------------

Spec = Callable[[str, int], int]  # (arm, prompt index) -> correct repeats, 0..2


def build_runs(
    spec: Spec,
    *,
    errors: set[tuple[str, str, int]] = frozenset(),
    empties: set[tuple[str, str, int]] = frozenset(),
    line_only: Callable[[str, dict[str, Any], int], bool] = lambda *_a: False,
    declines: Callable[[str, dict[str, Any], int], bool] = lambda *_a: False,
) -> list[dict[str, Any]]:
    """A run log in run_arms' on-disk shape. `spec` decides how many of a prompt's two
    repeats come back CORRECT in an arm; correctness is turned into a response by the
    prompt's class, since the oracle scores `both` on a genuine prompt and `neither` on a
    decoy."""
    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        for i, prompt in enumerate(BANK):
            for repeat in (0, 1):
                key = (arm, prompt['id'], repeat)
                correct = repeat < spec(arm, i)
                wants_both = correct == (prompt['class'] == 'genuine')
                row: dict[str, Any] = {
                    'arm': arm,
                    'prompt_id': prompt['id'],
                    'prompt_class': prompt['class'],
                    'language': prompt['language'],
                    'repeat': repeat,
                    'response': TEXT['both'] if wants_both else TEXT['neither'],
                    'is_error': False,
                    'cost_usd': 0.12,
                    'num_turns': 3,
                    'activated_skills': [],
                    'plugins_loaded': ['experiment-discipline'],
                }
                if key in errors:
                    row['is_error'] = True
                    row['response'] = ''
                elif key in empties:
                    row['response'] = '   '
                elif declines(arm, prompt, repeat):
                    row['response'] = DECLINE_TEXT
                elif not correct and line_only(arm, prompt, repeat):
                    # The declaration without the behaviour -- still incorrect in either
                    # class, but it lands in a different 2x2 cell, which is the whole
                    # point of recording the state rather than the pass.
                    row['response'] = TEXT['line_only']
                rows.append(row)
    # INTERLEAVED under a fixed seed, like the real plan: arm order is randomized so a
    # drifting snapshot cannot line up with an arm -- and so a truncated log (a ceiling
    # halt) thins every arm a little rather than wiping one arm's half of the bank, which
    # is what a tail-truncated arm-major log would do.
    random.Random(ORDER_SEED).shuffle(rows)  # noqa: S311 - run ordering, not cryptography
    for i, row in enumerate(rows):
        row['seq'] = i + 1
        row['ts'] = FIRST_TS + i * 30
    return rows


GENUINE_INDEXES = {i for i, prompt in enumerate(BANK) if prompt['class'] == 'genuine'}


def _spec(control: Spec, narrow: Spec, wide: Spec, inert: Spec) -> Spec:
    """Per-arm behaviour on the GENUINE half; every arm is near-perfect on the decoys,
    which is the baseline the frozen expectation describes (control near perfect there,
    treated arms able to lose ground). The pooled primary therefore carries the genuine
    signal diluted by twelve zero deltas, exactly as the real analysis will."""
    table = {'control': control, 'narrow': narrow, 'wide': wide, 'inert': inert}
    return lambda arm, i: table[arm](arm, i) if i in GENUINE_INDEXES else 2


# The four legs, built from the movement pair the frozen plan partitions:
# (the primary moved, inert - control moved). Each arm's lambda returns correct repeats.
LEG_SPECS: dict[str, Spec] = {
    # wide moves, inert does not
    'content_carries': _spec(
        lambda _a, _i: 0,
        lambda _a, i: 1 if i % 6 == 0 else 2,
        lambda _a, i: 1 if i % 6 == 0 else 2,
        lambda _a, i: 1 if i == 0 else 0,
    ),
    # wide and inert both move
    'preamble_only': _spec(
        lambda _a, _i: 0,
        lambda _a, i: 1 if i % 6 == 0 else 2,
        lambda _a, i: 1 if i % 6 == 0 else 2,
        lambda _a, i: 1 if i % 5 == 0 else 2,
    ),
    # inert moves, wide does not
    'inert_moves_alone': _spec(
        lambda _a, _i: 0,
        lambda _a, i: 1 if i == 0 else 0,
        lambda _a, i: 1 if i == 0 else 0,
        lambda _a, i: 1 if i % 5 == 0 else 2,
    ),
    # BOTH move, but not ALIKE: wide +0.50, inert +0.25 and wide - inert +0.25 with an
    # interval excluding zero -- the case where the frozen leg's "the content is
    # irrelevant" reading does not hold and must not be quoted.
    'preamble_not_alike': _spec(
        lambda _a, _i: 0,
        lambda _a, _i: 2,
        lambda _a, _i: 2,
        lambda _a, _i: 1,
    ),
    # control AT CEILING and wide COLLAPSING below it: the primary moves (two-sided), so
    # something plainly had room -- the no-headroom flag must not fire under this leg.
    'ceiling_collapse': _spec(
        lambda _a, _i: 2,
        lambda _a, _i: 0,
        lambda _a, _i: 0,
        lambda _a, _i: 2,
    ),
    # the A/A calibration moves: narrow and wide disagree on the genuine half, which is
    # impossible by construction and therefore a diagnostic failure rather than a signal.
    'aa_moves': _spec(
        lambda _a, _i: 0,
        lambda _a, _i: 2,
        lambda _a, _i: 0,
        lambda _a, _i: 0,
    ),
    # nothing moves, and control has room left on the genuine half
    'recorded_null': _spec(
        lambda _a, _i: 1,
        lambda _a, i: 2 if i == 2 else 1,
        lambda _a, i: 2 if i == 0 else 1,
        lambda _a, i: 2 if i == 1 else 1,
    ),
    # nothing moves because nothing could: every arm at ceiling on the genuine half
    'no_headroom': _spec(
        lambda _a, _i: 2,
        lambda _a, _i: 2,
        lambda _a, _i: 2,
        lambda _a, _i: 2,
    ),
}


def _finalized(record_path: Path) -> dict[str, Any]:
    return yaml.safe_load(record_path.read_text(encoding='utf-8'))


def pair(record: dict[str, Any], contrast_name: str, outcome: str = 'rigor_disposition') -> dict:
    """The pair-scoped results block a contrast lives in. Each contrast has its own block
    because the frozen drop-out rule is contrast-scoped and ER-STATS recomputes from the
    one clusters block of the key the contrast sits in."""
    return record['results'][f'{outcome}__{contrast_name}']


def only_contrast(record: dict[str, Any], name: str, outcome: str = 'rigor_disposition') -> dict:
    block = pair(record, name, outcome)
    assert len(block['contrasts']) == 1, name
    return block['contrasts'][0]


def _validate(record_path: Path) -> validate.Report:
    return validate.run_checks(_finalized(record_path), record_path)


PROMPT_CLASS = {p['id']: p['class'] for p in BANK}
_ORACLE = finalize.load_oracle(HERE)
_PATTERNS = _ORACLE.load_patterns(HERE / 'oracle_patterns.json')


def finalize_pure(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """The finalized record WITHOUT the CLI: same scoring, same pure core, no staged repo.

    Staging a git repo is what buys the context gates their real work, and the cases that
    need those gates pay for it. A case that only asks which leg the data selected does
    not, so it goes through the pure function -- the real record is copied, never written.
    """
    rows = finalize.score_runs(
        runs, PROMPT_CLASS, lambda text, cls: _ORACLE.score(text, cls, _PATTERNS)
    )
    return finalize.finalize_record(copy.deepcopy(RECORD), rows, PROMPT_CLASS)


# --- 1. the zero-exclusion run ------------------------------------------------
#
# One staging, then every assertion the zero-exclusion branch owes. Staging a repo is the
# expensive part of this suite (a git init, a commit, and a validate that shells out per
# gate), so the cases that need the SAME staged output share one.


def _zero_exclusion_runs() -> list[dict[str, Any]]:
    """content_carries, with half of control's genuine misses landing in the LINE-ONLY
    cell -- the founding failure, declared and unperformed, which the 2x2 breakdown has to
    make visible rather than fold into a pass rate."""
    return build_runs(
        LEG_SPECS['content_carries'],
        line_only=lambda arm, prompt, repeat: (
            arm == 'control' and prompt['class'] == 'genuine' and repeat == 0
        ),
    )


def test_a_zero_exclusion_run_finalizes_into_a_clean_measurement_record():
    with _tempdir() as td:
        record_path = stage(Path(td), _zero_exclusion_runs())
        code, out = run_finalize(record_path)
        assert code == 0, out
        assert 'frozen materials re-verified' in out, out
        assert 'no drift' in out, out
        record = _finalized(record_path)

        # (a) the observed disposition, with the exclusion reasons enumerated at zero.
        assert record['disposition']['completed'] == 192
        assert record['disposition']['excluded'] == 0
        assert record['disposition']['exclusion_reasons'] == {
            'harness_error': 0,
            'empty_response': 0,
            'not_run': 0,
        }
        assert 'CEILING-HALT' not in record['disposition']['pairing_rule']

        # (b) the arms branch: per-arm counts with their descriptive Wilson intervals, and
        # denominators that reconcile to N_expected (ER-RECON checks it; so does this).
        confirmatory = record['results']['rigor_disposition']
        assert set(confirmatory['arms']) == set(ARMS)
        assert sum(a['denominator'] for a in confirmatory['arms'].values()) == 192
        assert all(a['ci']['method'] == 'wilson' for a in confirmatory['arms'].values())
        assert confirmatory['surviving_clusters'] == 24
        assert confirmatory['dropped_prompts'] == []
        # The declared outcome states NO contrasts: a contrast there would be recomputed
        # against the all-arms block, which is what the pair-scoped keys exist to avoid.
        assert 'contrasts' not in confirmatory
        assert 'contrasts' not in record['results']['skeleton_wellformedness']
        # The scoped secondary never carries arms, exclusions or not.
        assert 'arms' not in record['results']['skeleton_wellformedness']
        assert record['results']['skeleton_wellformedness']['surviving_clusters'] == 12

        # (b2) every pre-registered contrast exists, in its own pair-scoped block whose
        # clusters carry exactly that pair's two arms.
        expected = {
            'wide_minus_control': (['wide', 'control'], 24),
            'wide_minus_inert': (['wide', 'inert'], 24),
            'narrow_minus_control': (['narrow', 'control'], 24),
            'narrow_minus_inert': (['narrow', 'inert'], 24),
            'inert_minus_control': (['inert', 'control'], 24),
            'wide_minus_control_genuine': (['wide', 'control'], 12),
            'wide_minus_inert_genuine': (['wide', 'inert'], 12),
            'narrow_minus_wide_genuine': (['narrow', 'wide'], 12),
            'wide_minus_control_decoy': (['wide', 'control'], 12),
            'wide_minus_inert_decoy': (['wide', 'inert'], 12),
        }
        for name, (arms_pair, n_clusters) in expected.items():
            block = pair(record, name)
            entry = only_contrast(record, name)
            assert entry['arms'] == arms_pair, name
            assert entry['n_clusters'] == n_clusters, name
            assert isinstance(entry['moved'], bool), name
            assert block['outcome'] == 'rigor_disposition', name
            for cells in block['clusters'].values():
                assert set(cells) == set(arms_pair), name
            # A pair block carries no verdict: a verdict belongs to a declared outcome.
            assert 'verdict' not in block, name
        for name in ('wide_minus_control_wellformed', 'wide_minus_inert_wellformed'):
            entry = only_contrast(record, name, 'skeleton_wellformedness')
            assert entry['n_clusters'] == 12, name
        assert only_contrast(record, 'wide_minus_control')['role'] == 'confirmatory'
        assert pair(record, 'narrow_minus_wide_genuine')['instrument_noise'] is False

        # (c) the 2x2 breakdown, with the line-only rate as a first-class number.
        states = record['state_breakdown']['arms']
        assert set(states) == set(ARMS)
        for arm in ARMS:
            assert states[arm]['all']['scored'] == 48
            assert states[arm]['genuine']['scored'] == 24
            counted = sum(
                states[arm]['all'][s] for s in ('both', 'line_only', 'skeleton_only', 'neither')
            )
            assert counted == 48, (arm, states[arm]['all'])
        assert states['control']['genuine']['line_only'] == 12
        assert states['control']['genuine']['line_only_rate'] == 0.5
        assert states['control']['genuine']['both'] == 0
        assert states['wide']['genuine']['line_only'] == 0

        # (d) the descriptive tax and the OBSERVED first run, in place of the placeholder.
        economy = record['run_economy']['per_arm']
        assert all(economy[arm]['runs'] == 48 for arm in ARMS)
        assert all(economy[arm]['mean_turns'] == 3.0 for arm in ARMS)
        assert record['run_economy']['total']['total_cost_usd'] == round(192 * 0.12, 4)
        assert record['run']['first_run_at'] == FIRST_RUN_AT
        assert record['run']['first_run_at'] != RECORD['run']['first_run_at']
        assert record['run']['n'] == 192

        # (e) the update, linking the founding experiment as this record's chain prior.
        updates = record['updates']
        assert updates['certainty'] in ('high', 'moderate', 'low', 'very_low')
        assert (record_path.parent / updates['prior']['source_id']).exists()
        assert '18/48 to 36/48' in updates['prior']['belief'], 'the RG-2x2 posterior is the prior'
        assert set(updates['what_each_leg_would_move']) == set(finalize.LEG_BELIEF)
        assert updates['posterior']['selected_interpretation'] == 'content_carries'
        assert 'generalization' in updates['downgrade_reasons']

        # (f) validate at measurement tier and the drift gate, both clean.
        report = _validate(record_path)
        assert report.failures == [], [f.message for f in report.failures]
        assert {f.code for f in report.warnings} == {'ER-XCHECK'}
        assert render.check_drift(record_path) is None

        # (g) the report carries every section the acceptance criterion names.
        text = (record_path.parent / 'report.md').read_text(encoding='utf-8')
        first = text.splitlines()[0]
        assert first == f'[experiment-rigor | measurement -> {RECORD_RELDIR}/record.yaml]', first
        for heading in (
            '## Contrasts (paired, on the clustered scale)',
            '## 2x2 states by arm',
            '## Turn and cost tax (descriptive)',
            '## Interpretation (pre-committed; selected mechanically)',
        ):
            assert heading in text, heading
        assert (
            '- Achieved precision (clustered scale): rigor_disposition / wide_minus_control' in text
        )
        assert 'A/A CALIBRATION -- the instrument noise floor' in text
        assert 'Selected: `content_carries`' in text
        assert 'live UserPromptSubmit hook' in text, 'the rollout precondition must be named'
        assert 'sign test' in text and 'p=' in text


# --- 2. the run with exclusions ----------------------------------------------


def _with_exclusions() -> list[dict[str, Any]]:
    """Both arms of the frozen exclusion rule, plus one prompt whose runs are ALL
    excluded in one arm -- the case the drop-out rule exists for."""
    dead = BANK[0]['id']  # g-en-01: every wide run of it errors
    return build_runs(
        LEG_SPECS['content_carries'],
        errors={('wide', dead, 0), ('wide', dead, 1)},
        empties={('control', BANK[12]['id'], 0)},
    )


def test_an_excluded_run_takes_the_contrasts_only_branch_and_drops_the_dead_prompt():
    with _tempdir() as td:
        record_path = stage(Path(td), _with_exclusions())
        code, out = run_finalize(record_path)
        assert code == 0, out
        record = _finalized(record_path)

        # (a) the disposition reconciles and names a reason per excluded run.
        assert record['disposition']['total'] == 192
        assert record['disposition']['completed'] == 189
        assert record['disposition']['excluded'] == 3
        assert record['disposition']['exclusion_reasons'] == {
            'harness_error': 2,
            'empty_response': 1,
            'not_run': 0,
        }
        assert len(record['disposition']['excluded_runs']) == 3
        assert {r['reason'] for r in record['disposition']['excluded_runs']} == {
            'harness_error',
            'empty_response',
        }

        # (b) the contrasts-only branch: no arms block anywhere, so no descriptive Wilson
        # rate is stated at all -- an exclusion is the first thing that invalidates one.
        for name, block in record['results'].items():
            assert 'arms' not in block, name
        assert 'wilson' not in yaml.safe_dump(record['results'])

        # (c) the drop-out is CONTRAST-scoped: g-en-01 is dead in `wide`, so it leaves the
        # contrasts that use wide and stays in the ones that do not.
        dead = BANK[0]['id']
        for name in ('wide_minus_control', 'wide_minus_inert'):
            assert pair(record, name)['dropped_prompts'] == [dead], name
            assert pair(record, name)['surviving_clusters'] == 23, name
            assert only_contrast(record, name)['n_clusters'] == 23, name
        for name in ('narrow_minus_control', 'inert_minus_control'):
            assert pair(record, name)['dropped_prompts'] == [], name
            assert only_contrast(record, name)['n_clusters'] == 24, name
        assert only_contrast(record, 'wide_minus_control_genuine')['n_clusters'] == 11
        assert only_contrast(record, 'narrow_minus_wide_genuine')['n_clusters'] == 11
        assert only_contrast(record, 'wide_minus_control_decoy')['n_clusters'] == 12

        # A single surviving repeat is kept, not dropped: a partial cluster is still a
        # cluster (denominator 1), which is what keeps that decoy prompt in the analysis.
        survivor = pair(record, 'wide_minus_control')['clusters'][BANK[12]['id']]
        assert survivor['control']['denominator'] == 1
        assert survivor['wide']['denominator'] == 2

        # (d) the gates stay clean, and the surviving count reaches the reader.
        report = _validate(record_path)
        assert report.failures == [], [f.message for f in report.failures]
        assert render.check_drift(record_path) is None
        assert '| 23 |' in (record_path.parent / 'report.md').read_text(encoding='utf-8')


def test_a_prompt_dead_in_one_arm_does_not_cost_a_contrast_that_never_uses_it():
    """The F2 case, measured: g-en-01 is dead in NARROW only. Under an all-arms cluster
    block the wide-control primary would lose a cluster to an arm it does not contrast;
    under the frozen contrast-scoped rule it keeps all 24."""
    dead = BANK[0]['id']
    runs = build_runs(
        LEG_SPECS['content_carries'],
        errors={('narrow', dead, 0), ('narrow', dead, 1)},
    )
    record = finalize_pure(runs)
    assert only_contrast(record, 'wide_minus_control')['n_clusters'] == 24
    assert pair(record, 'wide_minus_control')['dropped_prompts'] == []
    assert only_contrast(record, 'wide_minus_inert')['n_clusters'] == 24
    assert only_contrast(record, 'inert_minus_control')['n_clusters'] == 24
    assert only_contrast(record, 'wide_minus_control_genuine')['n_clusters'] == 12
    # Only the contrasts that actually use narrow pay for it.
    for name in ('narrow_minus_control', 'narrow_minus_inert'):
        assert pair(record, name)['dropped_prompts'] == [dead], name
        assert only_contrast(record, name)['n_clusters'] == 23, name
    assert only_contrast(record, 'narrow_minus_wide_genuine')['n_clusters'] == 11
    # The declared outcome's descriptive block is all-arms and DOES lose it -- that block
    # is a description of the run, not the estimand.
    assert record['results']['rigor_disposition']['dropped_prompts'] == [dead]


def _survivors(runs: list[dict[str, Any]], arms_subset: tuple[str, ...], pids: set[str]) -> int:
    """How many prompts survive for a given arm set under the frozen ceiling-halt rule --
    kept only where EVERY arm of that set carries both of its repeats. Re-derived here from
    the run log so the test pins the rule rather than the implementation's answer."""
    counts = Counter((r['arm'], r['prompt_id']) for r in runs if not r.get('is_error'))
    return sum(1 for pid in pids if all(counts.get((arm, pid), 0) == 2 for arm in arms_subset))


def test_a_ceiling_halt_falls_back_to_complete_prompt_pairs():
    """The frozen fallback is STRICTER than the drop-out rule and, like it, CONTRAST-scoped:
    "a prompt is kept only where every arm of THE CONTRAST carries both of its repeats".

    The log is interleaved, so a halt thins every arm -- and the point of the contrast
    scoping is that each pair loses only the prompts ITS OWN two arms lost. The expected
    survivor count per pair is re-derived from the log here; the all-arms count is derived
    too, and the primary must beat it, which is the defect this scoping removes.
    """
    runs = build_runs(LEG_SPECS['content_carries'])
    halted = runs[:-23]  # a ceiling halt 23 runs short of the plan
    all_pids = {b['id'] for b in BANK}
    genuine_pids = {b['id'] for b in BANK if b['class'] == 'genuine'}
    decoy_pids = {b['id'] for b in BANK if b['class'] == 'decoy'}
    all_arms_survivors = _survivors(halted, ARMS, all_pids)

    with _tempdir() as td:
        record_path = stage(Path(td), halted)
        code, out = run_finalize(record_path)
        assert code == 0, out
        record = _finalized(record_path)
        assert record['disposition']['exclusion_reasons']['not_run'] == 23
        assert record['disposition']['excluded'] == 23
        assert record['disposition']['completed'] == 169
        assert 'CEILING-HALT FALLBACK' in record['disposition']['pairing_rule']

        expected = {
            'wide_minus_control': (('wide', 'control'), all_pids),
            'wide_minus_inert': (('wide', 'inert'), all_pids),
            'narrow_minus_control': (('narrow', 'control'), all_pids),
            'narrow_minus_inert': (('narrow', 'inert'), all_pids),
            'inert_minus_control': (('inert', 'control'), all_pids),
            'wide_minus_control_genuine': (('wide', 'control'), genuine_pids),
            'narrow_minus_wide_genuine': (('narrow', 'wide'), genuine_pids),
            'wide_minus_control_decoy': (('wide', 'control'), decoy_pids),
        }
        for name, (pair_arms, pids) in expected.items():
            want = _survivors(halted, pair_arms, pids)
            assert pair(record, name)['surviving_clusters'] == want, name
            assert only_contrast(record, name)['n_clusters'] == want, name

        # The measured F2 defect: an all-arms block would have priced the primary at the
        # intersection of every arm's losses. Contrast-scoped, it keeps strictly more.
        primary_clusters = only_contrast(record, 'wide_minus_control')['n_clusters']
        assert primary_clusters > all_arms_survivors, (primary_clusters, all_arms_survivors)
        assert record['results']['rigor_disposition']['surviving_clusters'] == all_arms_survivors

        # No partial pair survived anywhere: every kept cluster carries both repeats.
        for key, block in record['results'].items():
            for pid, cells in (block.get('clusters') or {}).items():
                for arm, cell in cells.items():
                    assert cell['denominator'] == 2, (key, pid, arm, cell)
        assert 'CEILING-HALT FALLBACK' in pair(record, 'wide_minus_control')['pairing_rule']
        assert _validate(record_path).failures == []


def test_the_halt_rule_declines_a_prompt_left_on_a_single_repeat():
    """The single behaviour that separates the halt fallback from the ordinary drop-out:
    one repeat is enough for the drop-out rule and not enough for this one."""
    runs = build_runs(LEG_SPECS['content_carries'])
    victim = next(r for r in runs if r['arm'] == 'wide' and r['repeat'] == 1)
    halted = [r for r in runs if r is not victim]
    assert len(halted) == 191
    record = finalize_pure(halted)
    assert record['disposition']['exclusion_reasons']['not_run'] == 1
    block = pair(record, 'wide_minus_control')
    assert victim['prompt_id'] in block['dropped_prompts']
    assert block['surviving_clusters'] == 23
    # A contrast that does not use `wide` keeps it: the rule is per contrast, not per run.
    assert pair(record, 'inert_minus_control')['surviving_clusters'] == 24


# --- 3. idempotence -----------------------------------------------------------


def test_finalize_twice_is_byte_identical():
    with _tempdir() as td:
        record_path = stage(Path(td), build_runs(LEG_SPECS['recorded_null']))
        report_path = record_path.parent / 'report.md'
        assert run_finalize(record_path)[0] == 0
        once_record = record_path.read_bytes()
        once_report = report_path.read_bytes()
        assert run_finalize(record_path)[0] == 0
        assert record_path.read_bytes() == once_record, 'finalize appended instead of overwriting'
        assert report_path.read_bytes() == once_report
        # --check on an already-finalized pair reports no change and writes nothing.
        code, out = run_finalize(record_path, '--check')
        assert code == 0, out
        assert out.count('UP TO DATE') == 2, out
        assert record_path.read_bytes() == once_record


# --- 4. the material re-verification ------------------------------------------


def test_a_tampered_material_refuses_before_anything_is_written():
    with _tempdir() as td:
        record_path = stage(Path(td), build_runs(LEG_SPECS['content_carries']))
        before = record_path.read_bytes()
        report_before = (record_path.parent / 'report.md').read_bytes()
        bank_path = record_path.parent / 'bank.json'
        bank = json.loads(bank_path.read_text(encoding='utf-8'))
        bank['prompts'][0]['text'] += ' (edited after the freeze)'
        bank_path.write_text(json.dumps(bank), encoding='utf-8')

        code, out = run_finalize(record_path)
        assert code == 2, out
        assert 'FROZEN-MATERIAL MISMATCH' in out and 'bank' in out, out
        assert record_path.read_bytes() == before, 'a refusal must not have written results'
        assert (record_path.parent / 'report.md').read_bytes() == report_before


def test_the_oracle_hash_is_re_verified_in_all_three_places_it_is_stated():
    """materials.oracle, both outcomes' verifier.hash, and oracle_validation.sha256 are the
    same file's hash written three times; an edit to verify.py must fire on all of them."""
    record = copy.deepcopy(RECORD)
    assert finalize.verify_materials(record, HERE) == []
    record['outcomes'][0]['verifier']['hash'] = '0' * 64
    record['oracle_validation']['sha256'] = '0' * 64
    problems = finalize.verify_materials(record, HERE)
    assert any('verifier.hash' in p for p in problems), problems
    assert any('oracle_validation' in p for p in problems), problems


# --- 5. the interpretation the data selected ---------------------------------


def test_each_pre_committed_leg_is_selected_by_data_built_to_hit_it():
    """One scenario per leg, through the pure core. The staged end-to-end case above
    already carries a leg (content_carries) all the way to a written report; what is left
    to show here is that the OTHER data shapes select the other legs, and the leg is
    chosen in the pure function."""
    expected = {
        'content_carries': 'content_carries',
        'preamble_only': 'preamble_only',
        'inert_moves_alone': 'inert_moves_alone',
        'recorded_null': 'recorded_null',
        'no_headroom': 'recorded_null',
    }
    for scenario, leg in expected.items():
        record = finalize_pure(build_runs(LEG_SPECS[scenario]))
        conclusion = record['conclusion']
        assert conclusion['interpretation'] == leg, (scenario, conclusion['basis'])
        frozen = next(i for i in record['analysis_plan']['interpretations'] if i['id'] == leg)
        assert conclusion['read'] == frozen['read'], scenario
        assert conclusion['condition'] == frozen['condition'], scenario
        assert conclusion['no_headroom'] is (scenario == 'no_headroom'), scenario
        verdict = record['results']['rigor_disposition']['verdict']
        want = (
            'confirmatory_supported'
            if leg in ('content_carries', 'preamble_only')
            else 'confirmatory_null'
        )
        assert verdict == want, (scenario, verdict)
        assert f'Selected: `{leg}`' in render.render_report(record), scenario
        assert record['updates']['posterior']['selected_interpretation'] == leg, scenario


def test_the_no_headroom_null_is_recorded_as_no_headroom_not_as_no_effect():
    record = finalize_pure(build_runs(LEG_SPECS['no_headroom']))
    conclusion = record['conclusion']
    assert conclusion['interpretation'] == 'recorded_null'
    assert conclusion['control_genuine_rate'] == 1.0
    assert conclusion['headroom'] == 0.0
    assert conclusion['no_headroom'] is True
    assert 'Recorded as NO HEADROOM, not as no effect' in render.render_report(record)
    # The frozen leg's own text is what the report quotes -- no fifth reading.
    assert 'NO HEADROOM' in conclusion['read']


def test_no_headroom_is_scoped_to_the_null_and_not_to_a_leg_that_moved():
    """The frozen text scopes the qualifier to a NULL: "a null with control at or near
    ceiling ... is recorded as no headroom". With control at ceiling and wide collapsing
    below it the primary moved, which is itself proof there was room -- so the rate and the
    headroom are still reported, and the flag stays off."""
    record = finalize_pure(build_runs(LEG_SPECS['ceiling_collapse']))
    conclusion = record['conclusion']
    assert conclusion['interpretation'] == 'content_carries'
    assert conclusion['moved']['wide_minus_control'] is True
    assert only_contrast(record, 'wide_minus_control')['estimate'] < 0, 'a two-sided move down'
    assert conclusion['control_genuine_rate'] == 1.0
    assert conclusion['headroom'] == 0.0
    assert conclusion['no_headroom'] is False
    prose = render.render_report(record).split('## Record (canonical')[0]
    assert 'nowhere to move' not in prose, prose[-800:]
    # And the flag does fire where the frozen text puts it.
    null_record = finalize_pure(build_runs(LEG_SPECS['no_headroom']))
    assert null_record['conclusion']['no_headroom'] is True


def test_movement_needs_both_the_interval_and_the_declared_mewd():
    """The rule is a conjunction, and each half is load-bearing: an interval that excludes
    zero on an effect below the MEWD does not move, and neither does a large estimate
    whose interval covers zero."""
    threshold = RECORD['analysis_plan']['decision_rule']['threshold']
    tiny_but_certain = {'estimate': 0.05, 'interval': {'low': 0.04, 'high': 0.06}}
    large_but_uncertain = {'estimate': 0.4, 'interval': {'low': -0.1, 'high': 0.9}}
    both = {'estimate': 0.4, 'interval': {'low': 0.2, 'high': 0.6}}
    assert finalize.moved(tiny_but_certain, threshold) is False
    assert finalize.moved(large_but_uncertain, threshold) is False
    assert finalize.moved(both, threshold) is True
    # Two-sided: a move BELOW control counts as a move.
    assert finalize.moved({'estimate': -0.4, 'interval': {'low': -0.6, 'high': -0.2}}, threshold)


def test_the_four_legs_partition_the_movement_pair():
    """No fifth leg can be reached: the lookup is total over the 2x2, and every value it
    yields is an id the frozen plan declares."""
    frozen_ids = {i['id'] for i in RECORD['analysis_plan']['interpretations']}
    assert set(finalize.LEG_BY_MOVEMENT) == {(a, b) for a in (True, False) for b in (True, False)}
    assert set(finalize.LEG_BY_MOVEMENT.values()) == frozen_ids
    assert set(finalize.LEG_BELIEF) == frozen_ids


# --- 6. the renderer degrades rather than scaffolding ------------------------


def test_a_record_without_contrasts_grows_no_empty_sections():
    text = render.render_report(RECORD, RECORD_PATH)
    for heading in (
        '## Contrasts',
        '## 2x2 states by arm',
        '## Turn and cost tax',
        '## Interpretation (pre-committed',
    ):
        assert heading not in text, heading
    # The frozen pair on disk is untouched by this PR: the committed report is still in
    # sync with its record.
    assert render.check_drift(RECORD_PATH) is None


def test_the_run_log_is_read_strictly():
    """A duplicate run key and a run the bank does not know are both loud failures: one
    would silently double-count a cluster, the other would score a prompt that was never
    frozen."""
    prompt_class = {p['id']: p['class'] for p in BANK}
    rows = [
        {'arm': 'wide', 'prompt_id': BANK[0]['id'], 'repeat': 0, 'excluded': None},
        {'arm': 'wide', 'prompt_id': BANK[0]['id'], 'repeat': 0, 'excluded': None},
    ]
    try:
        finalize.finalize_record(copy.deepcopy(RECORD), rows, prompt_class)
    except SystemExit as exc:
        assert 'duplicate run key' in str(exc), exc
    else:
        raise AssertionError('a duplicated run key must not be silently collapsed')

    try:
        finalize.score_runs([{'prompt_id': 'not-in-the-bank'}], prompt_class, lambda t, c: {})
    except SystemExit as exc:
        assert 'not in the frozen bank' in str(exc), exc
    else:
        raise AssertionError('an unknown prompt id must not be scored')


def test_the_alike_qualifier_gates_the_preamble_leg_on_the_frozen_secondary():
    """The frozen condition is "wide and inert both move ALIKE", and wide - inert is the
    only pair in this design that isolates content from preamble. With wide +0.50, inert
    +0.25 and the secondary separating +0.25 at an interval excluding zero, the leg is
    still `preamble_only` -- no fifth leg exists -- but its "the content is irrelevant"
    reading is suppressed rather than quoted."""
    record = finalize_pure(build_runs(LEG_SPECS['preamble_not_alike']))
    conclusion = record['conclusion']
    frozen = next(
        i for i in record['analysis_plan']['interpretations'] if i['id'] == 'preamble_only'
    )
    assert conclusion['interpretation'] == 'preamble_only'
    assert conclusion['moved']['wide_minus_control'] is True
    assert conclusion['moved']['inert_minus_control'] is True
    assert conclusion['moved']['wide_minus_inert'] is True
    assert conclusion['alike'] is False
    assert conclusion['frozen_read_suppressed'] == frozen['read']
    assert conclusion['read'] != frozen['read']
    assert 'NOT ALIKE' in conclusion['read']
    assert 'CONTENT' in conclusion['read']
    # The suppressed sentence must not be asserted in the derived prose.
    text = render.render_report(record)
    prose = text.split('## Record (canonical')[0]
    assert 'the content is irrelevant' not in prose, prose[-1500:]
    assert 'Alike: NO' in prose
    assert 'Alike basis:' in prose


def test_alike_holds_when_the_secondary_does_not_move():
    """The other side of the same gate: wide and inert move together, the secondary does
    not separate them, and the frozen reading is quoted verbatim."""
    record = finalize_pure(build_runs(LEG_SPECS['preamble_only']))
    conclusion = record['conclusion']
    frozen = next(
        i for i in record['analysis_plan']['interpretations'] if i['id'] == 'preamble_only'
    )
    assert conclusion['interpretation'] == 'preamble_only'
    assert conclusion['alike'] is True
    assert conclusion['read'] == frozen['read']
    assert 'frozen_read_suppressed' not in conclusion
    assert 'the content is irrelevant' in render.render_report(record)


def test_an_aa_that_moves_is_recorded_as_instrument_noise_not_as_a_signal():
    """The A/A is the instrument's own noise floor: narrow and wide deliver byte-identical
    text on every genuine prompt. If it moves, that is a diagnostic failure -- it must not
    stamp a signal on anything, and it must be visible."""
    record = finalize_pure(build_runs(LEG_SPECS['aa_moves']))
    aa = only_contrast(record, 'narrow_minus_wide_genuine')
    assert aa['moved'] is True
    assert pair(record, 'narrow_minus_wide_genuine')['instrument_noise'] is True
    assert record['conclusion']['instrument_noise'] is True
    assert 'noise floor' in record['conclusion']['instrument_noise_note']
    # It changes no verdict: the confirmatory one rests on the primary, which did not move.
    assert record['results']['rigor_disposition']['verdict'] == 'confirmatory_null'
    assert record['conclusion']['interpretation'] == 'recorded_null'
    assert 'INSTRUMENT NOISE' in render.render_report(record)
    # And with an A/A that sits still, the flag is off.
    quiet = finalize_pure(build_runs(LEG_SPECS['content_carries']))
    assert quiet['conclusion']['instrument_noise'] is False
    assert 'INSTRUMENT NOISE' not in render.render_report(quiet)


def test_a_decline_for_lack_of_a_tool_is_scored_not_excluded():
    """The load-bearing half of the frozen exclusion rule. 10 of the 12 decoys ask for
    actions every arm is denied, so a decline is the modal decoy response: excluding it
    would decide after the fact whether the decoy half exists at all."""
    assert finalize.exclusion_reason({'is_error': False, 'response': DECLINE_TEXT}) is None
    # ... and it is neither of the two things that DO exclude.
    assert (
        finalize.exclusion_reason({'is_error': True, 'response': DECLINE_TEXT}) == 'harness_error'
    )
    assert finalize.exclusion_reason({'is_error': False, 'response': '  '}) == 'empty_response'

    runs = build_runs(
        LEG_SPECS['content_carries'],
        declines=lambda arm, prompt, repeat: prompt['class'] == 'decoy',
    )
    assert sum(1 for r in runs if r['response'] == DECLINE_TEXT) == 96
    record = finalize_pure(runs)
    assert record['disposition']['excluded'] == 0
    assert record['disposition']['completed'] == 192
    assert record['disposition']['exclusion_reasons'] == {
        'harness_error': 0,
        'empty_response': 0,
        'not_run': 0,
    }
    # Scored as written: every decline lands in a denominator, and on a decoy the shapeless
    # answer is the CORRECT one, so the decoy half is scored rather than emptied.
    decoy_clusters = pair(record, 'wide_minus_control_decoy')['clusters']
    assert len(decoy_clusters) == 12
    for pid, cells in decoy_clusters.items():
        for arm, cell in cells.items():
            assert cell['denominator'] == 2, (pid, arm)
            assert cell['numerator'] == 2, (pid, arm)
    for arm in ARMS:
        assert record['state_breakdown']['arms'][arm]['decoy']['scored'] == 24
        assert record['state_breakdown']['arms'][arm]['decoy']['neither'] == 24


def test_the_run_log_row_carries_every_field_finalize_reads():
    """The producer -> consumer interface, held by a test rather than by inspection: drive
    run_arms.execute through its DEFAULT spawn (run_one) with the harness stubbed, then
    score the row it wrote. A renamed or dropped field on either side reddens here."""
    path_before = list(sys.path)
    try:
        import run_arms
    finally:
        # run_arms puts evals/harness at the FRONT of sys.path; put it back so nothing
        # later in this module resolves `stats` to the harness copy.
        sys.path[:] = path_before

    class _FakeRun:
        """The AgentRun shape run_one reads. A field renamed on the harness side would
        surface here rather than as a silently empty response at finalize."""

        result_text = 'Method - checked it. Metric - 1/1. Results - 1/1. Conclusion - fine.'
        assistant_text = ''
        is_error = False
        cost_usd = 0.17
        num_turns = 4

        def __init__(self) -> None:
            self.activated_skills = {'experiment-rigor'}
            self.plugins_loaded = ['experiment-discipline']

    original = run_arms.run_agent
    run_arms.run_agent = lambda *args, **kwargs: _FakeRun()
    try:
        jobs = run_arms.build_plan(BANK, run_arms.load_table())[:1]
        prompts = {b['id']: b['text'] for b in BANK}
        with _tempdir() as td, contextlib.redirect_stdout(io.StringIO()):
            out = Path(td) / 'runs.jsonl'
            completed, _spent, halted = run_arms.execute(
                jobs, prompts, out=out, config_dir=None, cwd=None
            )
            written = [json.loads(line) for line in out.read_text(encoding='utf-8').splitlines()]
    finally:
        run_arms.run_agent = original

    assert completed == 1 and halted is False
    row = written[0]
    # Every field the consumer reads, by name and by type.
    for key, kind in (
        ('arm', str),
        ('prompt_id', str),
        ('prompt_class', str),
        ('repeat', int),
        ('response', str),
        ('is_error', bool),
        ('cost_usd', float),
        ('num_turns', int),
        ('ts', int),
    ):
        assert key in row, f'run_one dropped {key!r}, which finalize reads'
        assert isinstance(row[key], kind), (key, type(row[key]))
    assert row['response'] == _FakeRun.result_text
    # And the row survives the consumer end to end: not excluded, and fully scored.
    scored = finalize.score_runs(
        [row], PROMPT_CLASS, lambda text, cls: _ORACLE.score(text, cls, _PATTERNS)
    )[0]
    assert scored['excluded'] is None, 'a well-formed run must not read as an exclusion'
    assert scored['state'] in ('both', 'line_only', 'skeleton_only', 'neither')
    assert isinstance(scored['rigor_disposition'], bool)
    assert scored['num_turns'] == 4 and scored['cost_usd'] == 0.17


def test_more_runs_than_planned_is_a_refusal():
    """An over-count means the log is not the run the plan describes -- reconciling it
    would invent a disposition."""
    runs = build_runs(LEG_SPECS['content_carries'])
    extra = dict(runs[0])
    extra['repeat'] = 99  # a distinct key, so this is an over-count and not a duplicate
    try:
        finalize_pure([*runs, extra])
    except SystemExit as exc:
        assert 'more runs than were planned' in str(exc), exc
    else:
        raise AssertionError('193 runs against a 192-run plan must be refused')


def test_too_few_surviving_clusters_is_a_refusal_not_a_degraded_number():
    """When the drop-out rule leaves a contrast with fewer than two clusters there is
    nothing to estimate. stats.py raises; finalize turns that into a sentence about the
    run rather than a traceback -- and never into a number."""
    dead = {('wide', prompt['id'], repeat) for prompt in BANK[1:] for repeat in (0, 1)}
    runs = build_runs(LEG_SPECS['content_carries'], errors=dead)
    try:
        finalize_pure(runs)
    except SystemExit as exc:
        assert 'at least 2 shared clusters' in str(exc), exc
        assert 'surviving cluster(s)' in str(exc), exc
    else:
        raise AssertionError('a one-cluster contrast must be refused, not reported')


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
    print(
        'ok: both disposition branches, the drop-out rule, idempotence, the material '
        'refusal, all four interpretation legs and the renderer degradation'
    )

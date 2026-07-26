#!/usr/bin/env python3
"""Finalize the frozen RG-2x2 record after its pre-registration is committed.

The founding RG-2x2 record ships FROZEN (pre-results): design + outcomes + analysis
plan + threats, with `plan_frozen_at.commit: PENDING`. The freeze commit cannot name
its own SHA, so the SHA is filled AFTER the commit exists -- the standard
pre-registration freeze bootstrap (see FREEZE.md).

This step is a pure function of (frozen record, freeze SHA):

    finalize_record(record, freeze_sha) -> finalized record

It fills `plan_frozen_at.commit` and the wave-2 amendment's commit with the freeze SHA,
and adds the results (per-arm counts and Wilson CIs computed with stats.py), the observed
disposition (the frozen record carries only the planned total), the wave-2 amendment, and
the prior -> posterior update. It is DETERMINISTIC (no wall-clock) and
IDEMPOTENT (it overwrites, never appends -- re-running with the same SHA is a no-op),
so `validate.py` reaches exit 0 and `render.py --check` shows no drift.

The two decisions this fixture documents:
  - source: hand. The original was hand-orchestrated in fathom PR #15 before this
    discipline existed; reconstructed here as the chain root. ER-XCHECK is a
    measurement-tier WARN by design.
  - amendment.commit == the freeze commit. The +4/12 wave-2 confirmation bar for the
    exploratory footprint was fixed after the wave-1 post-hoc signal and before wave-2.
    In this reconstruction the whole pre-registration is frozen at one commit, so the
    amendment anchors to it; the validator's chronology check confirms the amendment
    commit predates the wave-2 run it governs (governs_first_run_at). A LIVE sequential
    design would carry a distinct between-waves amendment commit -- the fixture models
    the discipline's shape, not a live wave cadence.

Stdlib + PyYAML; the CLI additionally imports the sibling render.py / validate.py.
Python 3.13+.
"""

from __future__ import annotations

import argparse
import copy
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent / 'scripts'

# Per-arm results. Wilson 95% CIs (rounded to 4 dp) recomputed here match stats.py:
#   footprint with_gate    36/48 -> [0.6122, 0.8508]
#   footprint without_gate 18/48 -> [0.2522, 0.5164]
#   activation both arms    0/48 -> [0.0,    0.0741]
RESULTS: dict[str, Any] = {
    'activation': {
        # Primary, pre-registered, confirmatory. It FAILED: activation was ~0 in every
        # arm (the model never loaded the skill). The gate did not raise it.
        'verdict': 'confirmatory_null',
        'paired': True,
        'arms': {
            'with_gate': {
                'numerator': 0,
                'denominator': 48,
                'ci': {'method': 'wilson', 'alpha': 0.05, 'low': 0.0, 'high': 0.0741},
            },
            'without_gate': {
                'numerator': 0,
                'denominator': 48,
                'ci': {'method': 'wilson', 'alpha': 0.05, 'low': 0.0, 'high': 0.0741},
            },
        },
    },
    'footprint': {
        # Secondary, exploratory. The signal (gate raises the disciplinary footprint)
        # was noticed post-hoc in wave 1 and confirmed against a pre-fixed bar in wave 2.
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
    },
}

# The prior -> posterior belief update. This record is the chain ROOT, so
# updates.prior carries a `source` (a field memo), NOT a `source_id` (which the
# ER-LINK gate would require to resolve to a prior record.yaml -- there is none).
UPDATES: dict[str, Any] = {
    'certainty': 'low',
    'downgrade_reasons': ['token_length_confound', 'nondeterminism', 'generalization'],
    'prior': {
        'belief': 'imperative-register descriptions activate skills ~20x more '
        '(a field study on Claude Code skills)',
        'grade': 'low',
        'source': 'dispatch-field-memo',
    },
    'posterior': {
        'belief': "register (R) is null -- reg == ctrl in both tiers; the gate's forced "
        'deliberation raised the disciplinary footprint from 18/48 to 36/48 as an '
        'exploratory signal, even with a "none applies" verdict and no skill loaded',
        'grade': 'low',
        'method': 'beta_binomial_within',
    },
}


def _amendment(freeze_sha: str) -> dict[str, Any]:
    return {
        'commit': freeze_sha,
        'timestamp': '2026-07-24T00:00:00Z',
        'scope': 'wave-2',
        'governs_first_run_at': '2026-07-24T18:00:00Z',
        'note': 'wave-2 confirmation bar (+4/12) for the exploratory footprint, fixed '
        'after the wave-1 post-hoc signal and before wave-2. In this reconstruction the '
        'whole pre-registration is frozen at a single commit, so the amendment anchors '
        'to the freeze commit (documented choice; a live sequential design would carry a '
        'distinct between-waves commit).',
    }


# The OBSERVED disposition. The frozen record carries only the planned `total`; the
# completed / excluded counts are results, so finalize adds them (all 96 completed, none
# excluded). disposition is outside ER-PREREG's frozen-plan subset, so adding it here does
# not drift the freeze.
OBSERVED_DISPOSITION: dict[str, Any] = {'completed': 96, 'excluded': 0}


def finalize_record(record: dict[str, Any], freeze_sha: str) -> dict[str, Any]:
    """Return the finalized record: freeze SHA filled, results / amendment / update /
    observed disposition added.

    Pure and idempotent -- overwrites the finalized fields rather than appending, so
    re-running with the same SHA yields byte-identical output whether the input is the
    frozen stage-1 record or an already-finalized one."""
    out = copy.deepcopy(record)
    out.setdefault('plan_frozen_at', {})['commit'] = freeze_sha
    out.setdefault('analysis_plan', {})['amendments'] = [_amendment(freeze_sha)]
    out.setdefault('disposition', {}).update(copy.deepcopy(OBSERVED_DISPOSITION))
    out['results'] = copy.deepcopy(RESULTS)
    out['updates'] = copy.deepcopy(UPDATES)
    return out


def _git_env() -> dict[str, str]:
    """The environment minus every GIT_* variable, so `-C` is authoritative.

    Git exports the repository-location variables (GIT_DIR, GIT_WORK_TREE,
    GIT_INDEX_FILE, ...) into every hook it runs, and an ambient GIT_DIR takes
    PRECEDENCE over `git -C <dir>`. The record is located by `--record`, so it need
    not live in the repo a hook is running in: unscrubbed, finalizing from a hook
    (or any shell that inherited one) stamps the HOOK repo's HEAD into the record
    as the freeze commit -- a wrong SHA that ER-ANCHOR and ER-PREREG then verify
    against the wrong history. Found the hard way: the suite was green run directly
    and red inside `git push`."""
    return {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}


def _git_head(cwd: Path) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(cwd), 'rev-parse', 'HEAD'],  # noqa: S607 - git from PATH
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    if proc.returncode != 0:
        raise SystemExit(f'could not read HEAD in {cwd}: {proc.stderr.strip()}')
    return proc.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Finalize the frozen RG-2x2 record post-commit.')
    ap.add_argument('--record', default=str(HERE / 'record.yaml'), help='path to record.yaml')
    ap.add_argument(
        '--freeze-sha',
        default=None,
        help="the freeze commit SHA (default: HEAD of the record's repo)",
    )
    args = ap.parse_args(argv)

    record_path = Path(args.record).resolve()
    freeze_sha = args.freeze_sha or _git_head(record_path.parent)

    # Import the sibling scripts only in the CLI (the pure function above needs neither).
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import render
    import validate

    with open(record_path, encoding='utf-8') as fh:
        frozen = yaml.safe_load(fh)
    finalized = finalize_record(frozen, freeze_sha)

    with open(record_path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('# Finalized by finalize.py -- the frozen pre-registration plus results,\n')
        fh.write('# the wave-2 amendment, and the prior -> posterior update. Do not hand-edit;\n')
        fh.write('# re-run finalize.py to regenerate. See FREEZE.md for the choreography.\n')
        yaml.safe_dump(finalized, fh, sort_keys=False, allow_unicode=False, width=100)

    report_path = record_path.parent / 'report.md'
    # The record path goes in: it is what the leading activation line is generated from,
    # and the drift gate reads the embedded block alone -- so a re-render without it would
    # quietly drop the line while --check stayed green.
    report_path.write_text(
        render.render_report(finalized, record_path), encoding='utf-8', newline='\n'
    )

    report = validate.run_checks(finalized, record_path)
    for finding in report.findings:
        tag = finding.code if finding.level == 'FAIL' else f'WARN [{finding.code}]'
        print(f'{tag}: {finding.message}')
    drift = render.check_drift(record_path)
    if drift is not None:
        print(f'DRIFT: {drift}')
    if report.failures or drift is not None:
        print('finalize FAILED: the record did not reach a clean validate + render --check')
        return 1
    print(
        f'finalized {record_path} at freeze {freeze_sha[:12]} '
        f'({len(report.warnings)} warning(s), 0 failures, no drift)'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

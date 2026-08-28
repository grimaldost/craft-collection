#!/usr/bin/env python3
"""Held-out generalization check for a tuned skill description.

Evaluates the CURRENT (edited) skill description against NEW paraphrases the
editor did not see — proving the description captures the *intent category*
rather than overfitting the original eval prompts. Reads
`evals/trigger/holdout/<skill>.json` (same schema as trigger/) and reuses the
real triggering machinery from run_triggers.

    python evals/harness/holdout_check.py <skill> [--repeats R] [--concurrency K]
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_triggers
from claude_runner import cleanup_dir, make_isolated_config

REPO = Path(__file__).resolve().parents[2]


def dev_recall_pair(dev: dict) -> tuple[float | None, list | None, str]:
    """Pick the dev (point, CI, units) from ONE estimator family: query-level when
    the report carries both, else the pooled pair. Mixing families (the pooled
    point against the query-level interval) let the point sit outside its own CI
    and tripped false DROP/overfit verdicts."""
    if dev.get('recall_query') is not None and dev.get('recall_ci_query'):
        return dev['recall_query'], dev['recall_ci_query'], 'query'
    return dev.get('recall'), dev.get('recall_ci'), 'pooled'


def holdout_excl_point(score: dict, dev_units: str) -> float | None:
    """The error-excluded recall to feed the error-rescue, or None when it would cross
    units. `recall_excl_errors` is a POOLED rate; in the query-unit comparison path the
    strict point and dev bound are query-level and there is no query-level excl variant
    (an exclusion is ill-defined for a partially-errored query), so returning the pooled
    value would compare mismatched units. Return None there — the rescue is pooled-only,
    and the pooled excl recall is still printed to the reader regardless."""
    if dev_units == 'query' and score.get('recall_query') is not None:
        return None
    return score.get('recall_excl_errors')


def holdout_comparison(
    dev_recall, dev_ci, holdout_recall, holdout_recall_excl=None, n_err=0
) -> str:
    """One-line dev-vs-held-out recall verdict. Warns when held-out recall drops
    below the dev recall's lower Wilson bound — the overfit-to-the-dev-prompts
    signal the reader currently eyeballs by hand (#T2h).

    `n_err` errored-before-activation held-out positive runs carry no evidence the
    description failed (the mirror of N28a, which already credits fired-then-errored
    runs as activations), yet they depress the strict point this verdict reads. When
    they do — and the error-excluded point (`holdout_recall_excl`) would clear the
    dev bound while the strict point would not — the DROP is an infra artifact: name
    it and ask for a re-run rather than print a false 'overfit' verdict off a number
    the errors produced. (2026-07-14: a held-out run read 0.75/below-gate where 3
    identical `Prompt is too long` errors hit one query before it ever activated;
    excluding them recall was 1.00.)"""
    if holdout_recall is None:
        return 'held-out recall: n/a (no gated positives in the held-out set)'
    if dev_recall is None:
        return (
            f'held-out recall {holdout_recall:.2f} — dev recall n/a '
            '(no report/triggers.json entry to compare; run the dev trigger eval first)'
        )
    lo = dev_ci[0] if dev_ci else 0.0
    line = f'dev recall {dev_recall:.2f} (CI lo {lo:.2f})  vs  held-out {holdout_recall:.2f}'
    strict_drop = holdout_recall < lo
    error_rescued = (
        strict_drop and n_err and holdout_recall_excl is not None and holdout_recall_excl >= lo
    )
    if error_rescued:
        return (
            line + f'  -> DROP driven by {n_err} errored-before-activation run(s); '
            f'excl. errors {holdout_recall_excl:.2f} is within dev CI. Re-run the errored '
            'query before treating this DROP as real — infra noise, not a description verdict.'
        )
    if strict_drop:
        return line + '  -> DROP beyond dev CI: the description may be overfit to the dev prompts'
    return line + '  -> within dev CI: generalizes'


def strata_of(queries: list[dict]) -> dict[str, str]:
    """query text -> its declared `stratum`, for the entries that declare one.

    A holdout set whose cases are not all equally unseen has no single recall.
    The set says so in its own data rather than in a doc the reader must
    remember to apply: the 2026-08-11 data-engineering-discipline read scored
    0.75 on 6 genuinely unseen cases and 0.50 on 7 re-used spent-dev cases,
    while the harness printed the pooled 0.62 as its headline and BASELINES.md
    had to warn in prose that the printed number must not be read."""
    return {q['query']: q['stratum'] for q in queries if q.get('stratum')}


def stratify(per_query: list[dict], strata: dict[str, str]) -> list[dict]:
    """Per-stratum recall and specificity, or [] when there is nothing to split.

    Returns [] for an unstratified set and for a set whose entries all carry
    the SAME label: in both cases the pooled figure is the finding, and the
    extra apparatus would be noise a reader has to see past. Pure."""
    labels = {strata.get(pq['query']) for pq in per_query} - {None}
    if len(labels) < 2:
        return []
    rows = []
    for label in sorted(labels):
        pos_k = pos_n = neg_ok = neg_n = 0
        pos_q = neg_q = 0
        for pq in per_query:
            if strata.get(pq['query']) != label:
                continue
            if pq['should_trigger']:
                pos_k += pq['k']
                pos_n += pq['repeats']
                pos_q += 1
            else:
                neg_ok += pq['repeats'] - pq['k']
                neg_n += pq['repeats']
                neg_q += 1
        rows.append(
            {
                'stratum': label,
                'recall': (run_triggers.pass_rate(pos_k, pos_n) if pos_n else None),
                'recall_ci': (list(run_triggers.wilson_interval(pos_k, pos_n)) if pos_n else None),
                'specificity': (run_triggers.pass_rate(neg_ok, neg_n) if neg_n else None),
                'specificity_ci': (
                    list(run_triggers.wilson_interval(neg_ok, neg_n)) if neg_n else None
                ),
                'n_positive': pos_q,
                'n_negative': neg_q,
                'n_positive_runs': pos_n,
                'n_negative_runs': neg_n,
            }
        )
    return rows


def format_stratum(row: dict) -> str:
    """One stratum's line. ASCII only - this prints to a cp1252 console."""

    def fmt(point, ci, n_q, n_runs, kind):
        if point is None:
            return f'{kind} n/a (no {kind[:3]} cases in this stratum)'
        lo, hi = ci
        return f'{kind} {point:.2f} CI[{lo:.2f},{hi:.2f}] ({n_q} cases / {n_runs} runs)'

    recall = fmt(
        row['recall'], row['recall_ci'], row['n_positive'], row['n_positive_runs'], 'recall'
    )
    spec = fmt(
        row['specificity'],
        row['specificity_ci'],
        row['n_negative'],
        row['n_negative_runs'],
        'specificity',
    )
    return f'  [{row["stratum"]}] {recall}   {spec}'


def pooled_caveat(rows: list[dict]) -> str:
    """The label the pooled figure carries once the strata disagree, or ''.

    The harness used to print the pooled number as its headline and leave the
    caveat to a doc. A number a tool volunteers will be quoted, so the caveat
    travels with it."""
    if len(rows) < 2:
        return ''
    return (
        f'POOLED over {len(rows)} strata - not the finding. '
        'Read the per-stratum lines above; a pooled rate mixes seen with unseen.'
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    import argparse

    ap = argparse.ArgumentParser(
        description='Held-out generalization check for a tuned skill description '
        '(does it generalize to unseen paraphrases, or overfit the dev prompts?)'
    )
    ap.add_argument('skill', nargs='?', help='skill with an evals/trigger/holdout/<skill>.json set')
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--concurrency', type=int, default=6)
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])
    if not args.skill:
        ap.print_usage()
        return 2
    skill, repeats, concurrency = args.skill, args.repeats, args.concurrency

    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    holdout_path = REPO / 'evals' / 'trigger' / 'holdout' / f'{skill}.json'
    if not holdout_path.is_file():
        print(f'no held-out set at {holdout_path}')
        return 1
    queries = json.loads(holdout_path.read_text(encoding='utf-8'))
    plugin = cfg['plugin_of_skill'][skill]
    plugin_dir = str(REPO / 'plugins' / plugin)
    n_spawn = len(queries) * repeats
    print(
        f'HELD-OUT {skill} (plugin={plugin}) queries={len(queries)} '
        f'repeats={repeats} -> {n_spawn} spawns'
    )

    config_dir = make_isolated_config()
    cwd = tempfile.mkdtemp(prefix='holdout_')
    try:
        ok, detail = run_triggers.preflight_auth(cfg, config_dir, cwd)
        if not ok:
            print(
                f'\nPRE-FLIGHT FAILED: the auth/CLI probe errored ({detail}). '
                f'Re-login (claude /login) and retry — not spending the {n_spawn} held-out spawns.'
            )
            return 2
        score = run_triggers.run_skill(
            skill,
            queries,
            plugin_dir=plugin_dir,
            cfg=cfg,
            repeats=repeats,
            concurrency=concurrency,
            config_dir=config_dir,
            cwd=cwd,
        )
    finally:
        cleanup_dir(cwd)
        cleanup_dir(config_dir)

    if run_triggers.all_runs_errored(score):
        print(
            f'\nINVALID: all {score["total_runs"]} held-out runs errored '
            f'(cost=${score["cost_usd"]}). Infrastructure failure (auth/network/CLI), NOT a '
            f'measurement — re-run after fixing (a $0 cost points to auth: claude /login).'
        )
        for line in run_triggers.format_error_samples(score.get('error_samples') or []):
            print(line)
        return 2

    strata = stratify(score['per_query'], strata_of(queries))
    if strata:
        print('\nby stratum (the set declares more than one):')
        for row in strata:
            print(format_stratum(row))

    rlo, rhi = score['recall_ci']
    slo, shi = score['specificity_ci']
    if strata:
        print('\n' + pooled_caveat(strata))
    print(
        f'\nheld-out recall      = {score["recall"]:.2f}  CI[{rlo:.2f},{rhi:.2f}]  '
        f'(on {score["n_positive"]} unseen positives)'
    )
    if score.get('errors_no_activation_positive'):
        ree = score.get('recall_excl_errors')
        if ree is None:
            print(
                f'held-out recall excl. err = n/a (all '
                f'{score["errors_no_activation_positive"]} non-firing positive runs errored '
                'before activation — no valid trial)'
            )
        else:
            elo, ehi = score['recall_excl_errors_ci']
            print(
                f'held-out recall excl. err = {ree:.2f}  CI[{elo:.2f},{ehi:.2f}]  '
                f'({score["errors_no_activation_positive"]} errored-before-activation positive '
                'run(s) carry no description evidence)'
            )
    print(
        f'held-out specificity = {score["specificity"]:.2f}  CI[{slo:.2f},{shi:.2f}]  '
        f'(on {score["n_negative"]} unseen near-misses)'
    )
    print(
        f'cost=${score["cost_usd"]}  error_runs={score["error_runs"]}/{score["total_runs"]} '
        f'(no-activation errors={score["error_runs_no_activation"]})'
    )
    for line in run_triggers.format_error_samples(score.get('error_samples') or []):
        print(line)
    for pq in score['per_query']:
        sign = '+' if pq['should_trigger'] else '-'
        flag = (
            'MISS'
            if (pq['should_trigger'] and pq['rate'] < 1.0)
            or (not pq['should_trigger'] and pq['rate'] > 0.0)
            else 'ok'
        )
        print(f'  [{sign}] {flag:4} k={pq["k"]}/{pq["repeats"]}  {pq["query"][:72]}')

    triggers_path = REPO / 'evals' / 'report' / 'triggers.json'
    dev_recall = dev_ci = None
    dev_units = 'pooled'
    if triggers_path.exists():
        try:
            dev = json.loads(triggers_path.read_text(encoding='utf-8')).get(skill) or {}
            # Prefer the query-level pair: the pooled CI treats correlated repeats
            # as independent trials, so its lower bound is too high. Point and CI
            # must come from the SAME estimator (dev_recall_pair), and the held-out
            # point below is chosen in the same unit — a mixed pairing let a point
            # sit outside its own interval and tripped false "overfit" verdicts.
            dev_recall, dev_ci, dev_units = dev_recall_pair(dev)
        except (json.JSONDecodeError, ValueError):
            pass
    holdout_point = score['recall']
    if dev_units == 'query' and score.get('recall_query') is not None:
        holdout_point = score['recall_query']
    if strata:
        print(
            '\ndev-vs-held-out comparison withheld: it is defined on the pooled point, '
            'which this set does not have. Compare the dev number against the stratum '
            'you mean.'
        )
    else:
        print(
            '\n'
            + holdout_comparison(
                dev_recall,
                dev_ci,
                holdout_point,
                holdout_recall_excl=holdout_excl_point(score, dev_units),
                n_err=score.get('errors_no_activation_positive', 0),
            )
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Held-out generalization check for a tuned skill description.

Evaluates the CURRENT (edited) skill description against NEW paraphrases the
editor did not see — proving the description captures the *intent category*
rather than overfitting the original eval prompts. Reads
`evals/trigger/holdout/<skill>.json` (same schema as trigger/) and reuses the
real triggering machinery from run_triggers.

    python evals/harness/holdout_check.py <skill> [repeats] [concurrency]
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


def holdout_comparison(dev_recall, dev_ci, holdout_recall) -> str:
    """One-line dev-vs-held-out recall verdict. Warns when held-out recall drops
    below the dev recall's lower Wilson bound — the overfit-to-the-dev-prompts
    signal the reader currently eyeballs by hand (#T2h)."""
    if holdout_recall is None:
        return 'held-out recall: n/a (no gated positives in the held-out set)'
    if dev_recall is None:
        return (
            f'held-out recall {holdout_recall:.2f} — dev recall n/a '
            '(no report/triggers.json entry to compare; run the dev trigger eval first)'
        )
    lo = dev_ci[0] if dev_ci else 0.0
    line = f'dev recall {dev_recall:.2f} (CI lo {lo:.2f})  vs  held-out {holdout_recall:.2f}'
    if holdout_recall < lo:
        return line + '  -> DROP beyond dev CI: the description may be overfit to the dev prompts'
    return line + '  -> within dev CI: generalizes'


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

    rlo, rhi = score['recall_ci']
    slo, shi = score['specificity_ci']
    print(
        f'\nheld-out recall      = {score["recall"]:.2f}  CI[{rlo:.2f},{rhi:.2f}]  '
        f'(on {score["n_positive"]} unseen positives)'
    )
    print(
        f'held-out specificity = {score["specificity"]:.2f}  CI[{slo:.2f},{shi:.2f}]  '
        f'(on {score["n_negative"]} unseen near-misses)'
    )
    print(
        f'cost=${score["cost_usd"]}  error_runs={score["error_runs"]}/{score["total_runs"]} '
        f'(no-activation errors={score["error_runs_no_activation"]})'
    )
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
    if triggers_path.exists():
        try:
            dev = json.loads(triggers_path.read_text(encoding='utf-8')).get(skill) or {}
            dev_recall, dev_ci = dev.get('recall'), dev.get('recall_ci')
        except (json.JSONDecodeError, ValueError):
            pass
    print('\n' + holdout_comparison(dev_recall, dev_ci, score['recall']))
    return 0


if __name__ == '__main__':
    sys.exit(main())

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


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print('usage: holdout_check.py <skill> [repeats] [concurrency]')
        return 2
    skill = argv[0]
    repeats = int(argv[1]) if len(argv) > 1 else 3
    concurrency = int(argv[2]) if len(argv) > 2 else 6

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
    return 0


if __name__ == '__main__':
    sys.exit(main())

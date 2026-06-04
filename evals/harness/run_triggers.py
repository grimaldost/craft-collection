#!/usr/bin/env python3
"""Triggering eval (axes 1 & 3): does the right Skill auto-fire, and stay quiet
on near-misses?

`score_skill` is the pure, unit-tested scorer (pooled recall/specificity + Wilson
CIs). The CLI spawns `claude -p` with `--plugin-dir <plugin>` for every
(query x repeat), counts activations, and writes `report/triggers.json`.

    python evals/harness/run_triggers.py <skill> [--limit N] [--repeats R]
                                         [--concurrency K] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from claude_runner import cleanup_dir, make_isolated_config, map_concurrent, run_agent
from stats import pass_rate, wilson_interval

REPO = Path(__file__).resolve().parents[2]
TRIGGER_DIR = REPO / 'evals' / 'trigger'
REPORT_DIR = REPO / 'evals' / 'report'
MAX_TURNS_TRIGGER = 3  # enough for the skill to fire; keeps per-spawn cost low


def score_skill(queries: list[dict], repeats: int, trigger_counter) -> dict:
    """Pooled recall (over positives) and specificity (over negatives) with Wilson
    CIs. `trigger_counter(query_str, repeats) -> k` returns how many of `repeats`
    runs fired the skill. Pure: inject a fake counter in tests, the real one in the
    CLI."""
    pos_succ = pos_tri = neg_succ = neg_tri = 0
    per_query = []
    for q in queries:
        k = trigger_counter(q['query'], repeats)
        if q['should_trigger']:
            pos_succ += k
            pos_tri += repeats
        else:
            neg_succ += repeats - k  # a correct rejection = a NON-fire on a negative
            neg_tri += repeats
        per_query.append({'query': q['query'], 'should_trigger': q['should_trigger'],
                          'k': k, 'repeats': repeats,
                          'rate': (k / repeats if repeats else 0.0)})
    return {
        'recall': pass_rate(pos_succ, pos_tri),
        'specificity': pass_rate(neg_succ, neg_tri),
        'recall_ci': list(wilson_interval(pos_succ, pos_tri)),
        'specificity_ci': list(wilson_interval(neg_succ, neg_tri)),
        'n_positive': sum(1 for q in queries if q['should_trigger']),
        'n_negative': sum(1 for q in queries if not q['should_trigger']),
        'repeats': repeats,
        'per_query': per_query,
    }


def load_queries(skill: str, limit: int | None = None) -> list[dict]:
    data = json.loads((TRIGGER_DIR / f'{skill}.json').read_text(encoding='utf-8'))
    if limit:  # balanced slice: first `limit` positives + first `limit` negatives
        pos = [q for q in data if q['should_trigger']][:limit]
        neg = [q for q in data if not q['should_trigger']][:limit]
        return pos + neg
    return data


def run_skill(skill: str, queries: list[dict], *, plugin_dir: str, cfg: dict,
              repeats: int, concurrency: int, config_dir: str, cwd: str) -> dict:
    """Spawn every (query x repeat) run concurrently, tally activations, score."""
    jobs = [(i, q['query']) for i, q in enumerate(queries) for _ in range(repeats)]

    def worker(job):
        i, qstr = job
        run = run_agent(qstr, plugin_dir=plugin_dir,
                        allowed_tools=cfg['allowed_tools_trigger'],
                        model=cfg['agent_model'], max_turns=MAX_TURNS_TRIGGER,
                        max_budget_usd=cfg['max_budget_usd'],
                        timeout=cfg['timeout_seconds'], stream=True,
                        config_dir=config_dir, cwd=cwd)
        return (i, run.activated(skill), run.cost_usd or 0.0, run.is_error)

    results = map_concurrent(jobs, worker, concurrency=concurrency)
    counts = [0] * len(queries)
    cost = 0.0
    errors = errors_no_act = 0
    for i, fired, c, err in results:
        counts[i] += 1 if fired else 0
        cost += c
        if err:
            errors += 1
            if not fired:  # the only kind that can distort the score
                errors_no_act += 1
    by_str = {queries[i]['query']: counts[i] for i in range(len(queries))}
    score = score_skill(queries, repeats, lambda s, _r: by_str[s])
    score['cost_usd'] = round(cost, 4)
    score['error_runs'] = errors  # mostly benign: positives truncate at max_turns
    score['error_runs_no_activation'] = errors_no_act  # the diagnostic that matters
    score['total_runs'] = len(jobs)
    return score


def write_report(skill: str, score: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / 'triggers.json'
    blob: dict = {}
    if path.exists():
        try:
            blob = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, ValueError):
            blob = {}
    blob[skill] = score
    path.write_text(json.dumps(blob, indent=2), encoding='utf-8')
    return path


def main(argv: list[str] | None = None) -> int:
    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    ap = argparse.ArgumentParser(description='Skill triggering eval (axes 1 & 3)')
    ap.add_argument('skill', choices=sorted(cfg['plugin_of_skill']))
    ap.add_argument('--limit', type=int, default=None,
                    help='cap to first N positives + N negatives')
    ap.add_argument('--repeats', type=int, default=cfg['agent_repeats'])
    ap.add_argument('--concurrency', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)

    queries = load_queries(args.skill, args.limit)
    plugin = cfg['plugin_of_skill'][args.skill]
    plugin_dir = str(REPO / 'plugins' / plugin)
    n_spawn = len(queries) * args.repeats
    print(f'skill={args.skill} plugin={plugin} queries={len(queries)} '
          f'repeats={args.repeats} -> {n_spawn} spawns '
          f'(<= ${n_spawn * cfg["max_budget_usd"]:.2f} ceiling)')
    if args.dry_run:
        for q in queries:
            print(f'  [{"+" if q["should_trigger"] else "-"}] {q["query"][:80]}')
        return 0

    config_dir = make_isolated_config()
    cwd = tempfile.mkdtemp(prefix='eval_trig_')
    try:
        score = run_skill(args.skill, queries, plugin_dir=plugin_dir, cfg=cfg,
                          repeats=args.repeats, concurrency=args.concurrency,
                          config_dir=config_dir, cwd=cwd)
    finally:
        cleanup_dir(cwd)
        cleanup_dir(config_dir)

    write_report(args.skill, score)
    g = cfg['gates']
    rlo, rhi = score['recall_ci']
    slo, shi = score['specificity_ci']
    rec_ok = 'PASS' if score['recall'] >= g['trigger_recall'] else 'FAIL'
    spec_ok = 'PASS' if score['specificity'] >= g['trigger_specificity'] else 'FAIL'
    print(f'\nrecall      = {score["recall"]:.2f}  CI[{rlo:.2f},{rhi:.2f}]  '
          f'gate>={g["trigger_recall"]}  {rec_ok}')
    print(f'specificity = {score["specificity"]:.2f}  CI[{slo:.2f},{shi:.2f}]  '
          f'gate>={g["trigger_specificity"]}  {spec_ok}')
    print(f'cost=${score["cost_usd"]}  error_runs={score["error_runs"]}/{score["total_runs"]} '
          f'(no-activation errors={score["error_runs_no_activation"]})')
    for pq in score['per_query']:  # surface misses for description tuning
        miss = ((pq['should_trigger'] and pq['rate'] < 1.0)
                or (not pq['should_trigger'] and pq['rate'] > 0.0))
        if miss:
            sign = '+' if pq['should_trigger'] else '-'
            print(f'  miss [{sign}] k={pq["k"]}/{pq["repeats"]} {pq["query"][:70]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

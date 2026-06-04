#!/usr/bin/env python3
"""Grading eval (axes 2 & 4): correct usage and with/without quality.

For each task x agent-repeat, run a WITH arm (`--plugin-dir <plugin>`) and a
WITHOUT arm (same isolated authed config, no plugin), then:
  - axis 2: judge_pointwise(WITH output vs rubric)  -> correct-usage pass-rate
  - axis 4: judge_pairwise(WITH vs WITHOUT)          -> with/without win-rate

`grade_skill` is orchestration with injectable `run_arm`/judge fns (unit-tested
with fakes). The CLI does the real spawns. Output -> report/grading.json.

    python evals/harness/grade_tasks.py <skill> [--limit N] [--repeats R]
                                        [--concurrency K] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from claude_runner import cleanup_dir, make_isolated_config, map_concurrent, run_agent
from judge import judge_pairwise, judge_pointwise
from stats import pass_rate, wilson_interval

REPO = Path(__file__).resolve().parents[2]
TASKS_DIR = REPO / 'evals' / 'tasks'
REPORT_DIR = REPO / 'evals' / 'report'
SPAWNS_PER_UNIT = 5  # 2 arms + 1 pointwise (judge_repeats=1) + 2 pairwise orderings

# One holistic pairwise criterion per skill (axis 4 head-to-head).
PAIRWISE_CRITERION = {
    'journaling-sessions':
        'which response better captures the session as structured, separable, '
        'retrieval-ready memory entries — concrete reasoning inline, anti-patterns '
        'and dead-ends captured, one idea per entry — that a future session could '
        'find and reuse in isolation',
    'context-handoff':
        'which response is the better self-contained, paste-ready hand-off brief: '
        'states facts not references, inlines the concrete specifics an executor '
        'with zero prior context needs, and uses the correct mode framing',
    'data-engineering-discipline':
        'which response better applies data-engineering discipline — pins the '
        'contract/baseline, verifies the observable source over assumptions, '
        'proposes real-data parity checks, and keeps changes intentional and '
        'traceable rather than silently altering semantics',
}


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def build_task_prompt(skill: str, task: dict) -> str:
    parts = []
    fixture = task.get('fixture')
    if fixture:
        parts.append((TASKS_DIR / skill / fixture).read_text(encoding='utf-8'))
    parts.append(task['prompt'])
    return '\n\n-----\n\n'.join(parts)


def _read_created_files(cwd: str, cap: int = 20000) -> str:
    """Concatenate text files the agent wrote in its temp cwd (journaling writes
    its entries to a file rather than the final message). Capped, best-effort."""
    chunks = []
    for p in sorted(Path(cwd).rglob('*')):
        if p.is_file():
            try:
                chunks.append(f'--- file: {p.name} ---\n{p.read_text(encoding="utf-8", errors="replace")}')
            except OSError:
                continue
    return '\n\n'.join(chunks)[:cap]


def _run_arm_real(prompt: str, *, plugin_dir: str | None, cfg: dict, config_dir: str):
    """One agent arm in a fresh cwd; output = final message + any files it wrote."""
    cwd = tempfile.mkdtemp(prefix='eval_task_')
    try:
        run = run_agent(prompt, plugin_dir=plugin_dir,
                        allowed_tools=cfg['allowed_tools_task'], model=cfg['agent_model'],
                        max_turns=cfg['max_turns'], max_budget_usd=cfg['max_budget_usd'],
                        timeout=cfg['timeout_seconds'], stream=True,
                        config_dir=config_dir, cwd=cwd)
        files = _read_created_files(cwd)
    finally:
        cleanup_dir(cwd)
    output = run.result_text + (f'\n\n[FILES WRITTEN]\n{files}' if files else '')
    return run, output


def grade_skill(skill: str, tasks: list[dict], rubric: list[dict], cfg: dict, *,
                plugin_dir: str | None, config_with: str | None,
                config_without: str | None, pairwise_criterion: str,
                concurrency: int = 4, run_arm=_run_arm_real,
                judge_point=judge_pointwise, judge_pair=judge_pairwise) -> dict:
    """Run every (task x repeat) unit concurrently; each unit does WITH + WITHOUT
    arms then pointwise + pairwise judging. Returns the per-skill grading blob.

    The two arms MUST use SEPARATE config dirs: a `--plugin-dir` run caches the
    plugin into its CLAUDE_CONFIG_DIR, so a WITHOUT arm sharing that dir would
    silently inherit the skill (contaminating the baseline). `config_without` is
    never touched by `--plugin-dir`, so it stays genuinely skill-free."""
    repeats = cfg['agent_repeats']
    units = [(t, r) for t in tasks for r in range(repeats)]

    def do_unit(unit):
        task, r = unit
        prompt = build_task_prompt(skill, task)
        with_run, with_out = run_arm(prompt, plugin_dir=plugin_dir, cfg=cfg,
                                     config_dir=config_with)
        without_run, without_out = run_arm(prompt, plugin_dir=None, cfg=cfg,
                                            config_dir=config_without)
        pw = judge_point(prompt, with_out, rubric, model=cfg['judge_model'],
                         repeats=cfg['judge_repeats'])
        pair = judge_pair(prompt, with_out, without_out, pairwise_criterion,
                          model=cfg['judge_model'])
        return {
            'task_id': task['id'], 'repeat': r,
            'with_pass': bool(pw['pass']), 'with_score': pw['score'],
            'with_agreement': pw['agreement'], 'pairwise_winner': pair['winner'],
            'pairwise_orders': [pair.get('order1'), pair.get('order2')],
            'with_activated': with_run.activated(skill),
            'with_cost': with_run.cost_usd or 0.0, 'without_cost': without_run.cost_usd or 0.0,
            'with_error': with_run.is_error, 'without_error': without_run.is_error,
            'criteria': (pw.get('verdicts') or [{}])[0].get('criteria'),  # per-criterion met+evidence
        }

    records = map_concurrent(units, do_unit, concurrency=concurrency)
    return _summarize(skill, records)


def _summarize(skill: str, records: list[dict]) -> dict:
    by_task: dict[str, list] = {}
    for rec in records:
        by_task.setdefault(rec['task_id'], []).append(rec)

    tasks_out = []
    for tid, recs in by_task.items():
        n = len(recs)
        passes = sum(1 for x in recs if x['with_pass'])
        tasks_out.append({
            'task_id': tid, 'n': n,
            'with_pass_rate': pass_rate(passes, n),
            'with_pass_ci': list(wilson_interval(passes, n)),
            'mean_score': _mean(x['with_score'] for x in recs),
            'mean_agreement': _mean(x['with_agreement'] for x in recs),
            'with_activation_rate': pass_rate(sum(1 for x in recs if x['with_activated']), n),
            'pairwise': {
                'with_wins': sum(1 for x in recs if x['pairwise_winner'] == 'A'),
                'without_wins': sum(1 for x in recs if x['pairwise_winner'] == 'B'),
                'ties': sum(1 for x in recs if x['pairwise_winner'] == 'tie'),
            },
            'records': recs,
        })

    n = len(records)
    passes = sum(1 for x in records if x['with_pass'])
    a = sum(1 for x in records if x['pairwise_winner'] == 'A')
    b = sum(1 for x in records if x['pairwise_winner'] == 'B')
    ties = sum(1 for x in records if x['pairwise_winner'] == 'tie')
    cost = sum((x['with_cost'] + x['without_cost']) for x in records)
    summary = {
        'n_records': n,
        'correct_usage_rate': pass_rate(passes, n),
        'correct_usage_ci': list(wilson_interval(passes, n)),
        'mean_score': _mean(x['with_score'] for x in records),
        'mean_agreement': _mean(x['with_agreement'] for x in records),
        'with_activation_rate': pass_rate(sum(1 for x in records if x['with_activated']), n),
        'with_win_rate': pass_rate(a, n), 'without_win_rate': pass_rate(b, n),
        'tie_rate': pass_rate(ties, n),
        'error_runs': sum(1 for x in records if x['with_error'] or x['without_error']),
        'cost_usd': round(cost, 4),
    }
    return {'skill': skill, 'tasks': tasks_out, 'summary': summary}


def write_report(skill: str, blob: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / 'grading.json'
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, ValueError):
            data = {}
    data[skill] = blob
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return path


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # task text is unicode
    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    ap = argparse.ArgumentParser(description='Skill grading eval (axes 2 & 4)')
    ap.add_argument('skill', choices=sorted(cfg['plugin_of_skill']))
    ap.add_argument('--limit', type=int, default=None, help='cap to first N tasks')
    ap.add_argument('--repeats', type=int, default=None, help='override agent_repeats')
    ap.add_argument('--concurrency', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)
    if args.repeats:
        cfg['agent_repeats'] = args.repeats

    skill = args.skill
    tasks = json.loads((TASKS_DIR / skill / 'tasks.json').read_text(encoding='utf-8'))
    rubric = json.loads((TASKS_DIR / skill / 'rubric.json').read_text(encoding='utf-8'))
    if args.limit:
        tasks = tasks[:args.limit]
    n_units = len(tasks) * cfg['agent_repeats']
    n_spawn = n_units * SPAWNS_PER_UNIT
    plugin = cfg['plugin_of_skill'][skill]
    print(f'skill={skill} plugin={plugin} tasks={len(tasks)} repeats={cfg["agent_repeats"]} '
          f'-> {n_units} units x {SPAWNS_PER_UNIT} = {n_spawn} spawns '
          f'(<= ${n_spawn * cfg["max_budget_usd"]:.2f} ceiling)')
    if args.dry_run:
        for t in tasks:
            print(f'  task {t["id"]}: {t["prompt"][:70]}')
        return 0

    plugin_dir = str(REPO / 'plugins' / plugin)
    config_with = make_isolated_config()       # --plugin-dir runs cache the plugin here
    config_without = make_isolated_config()    # never sees --plugin-dir -> stays skill-free
    try:
        blob = grade_skill(skill, tasks, rubric, cfg, plugin_dir=plugin_dir,
                           config_with=config_with, config_without=config_without,
                           pairwise_criterion=PAIRWISE_CRITERION[skill],
                           concurrency=args.concurrency)
    finally:
        cleanup_dir(config_with)
        cleanup_dir(config_without)

    write_report(skill, blob)
    s = blob['summary']
    gate = cfg['gates']['correct_usage']
    clo, chi = s['correct_usage_ci']
    usage_ok = 'PASS' if s['correct_usage_rate'] >= gate else 'FAIL'
    print(f'\ncorrect_usage = {s["correct_usage_rate"]:.2f}  CI[{clo:.2f},{chi:.2f}]  '
          f'gate>={gate}  {usage_ok}   (mean_score={s["mean_score"]:.2f}, '
          f'judge_agreement={s["mean_agreement"]:.2f})')
    print(f'with/without  = WITH wins {s["with_win_rate"]:.2f} | '
          f'WITHOUT wins {s["without_win_rate"]:.2f} | tie {s["tie_rate"]:.2f}')
    print(f'activation    = {s["with_activation_rate"]:.2f} (WITH arm fired the skill)')
    print(f'cost=${s["cost_usd"]}  error_runs={s["error_runs"]}/{s["n_records"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

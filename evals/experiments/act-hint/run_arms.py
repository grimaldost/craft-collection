#!/usr/bin/env python3
"""Spend the act-hint detector's 192 runs -- or, with --dry-run, spend nothing.

Firing was decided offline and frozen in `firing_table.json`. This module is only
the effect half: it takes each arm's already-frozen injected text and delivers it
DIRECTLY, prepended to the prompt the measured spawn reads on stdin, at a single
insertion point that never moves. No plugin hook is involved, nothing is
recomputed at run time, and no harness change is needed -- `claude_runner.run_agent`
already feeds the prompt on stdin.

What is held identical across arms, by construction rather than by intent: the
prompt text, the model string, the sampling settings, the turn cap, the tool
allowlist, the cwd fixture, the repeat count, the insertion point, and the EN/PT-BR
balance. What differs is exactly one thing -- which prompts receive an injection
and what text they receive.

Every arm loads `plugins/experiment-discipline` with the `Skill` tool available, so
the control arm is NOT a no-treatment baseline: it already carries, in its own
loaded plugin, a skill that instructs the behavior the oracle scores. Control
measures that skill's own trigger surface with no hint; `wide - control` is the
hint's marginal effect over a loaded, unhinted skill.

Isolation per run: a fresh spawn (`--no-session-persistence`), an isolated
credentials-only CLAUDE_CONFIG_DIR (no CLAUDE.md, no settings, no history), a
restricted tool allowlist, and a neutral cwd fixture holding no expected answer.
Arm order is randomized and interleaved under a seeded RNG so a drifting model
snapshot cannot line up with an arm.

Before either mode does anything, every frozen material is re-hashed and checked
against the record's own `materials` block. A run against edited materials would
measure something the pre-registration does not describe, so that is a refusal, not
a warning -- and it is checked in `--dry-run` too, because it is free.

    uv run --no-project --with pyyaml -- python run_arms.py --dry-run   # plan + cost, $0
    uv run --no-project --with pyyaml -- python run_arms.py             # the paid run

Stdlib for everything except the material check, which reads record.yaml and
therefore needs PyYAML. That import is local to the check and RAISES when PyYAML is
missing: a material check that skips itself is worse than none.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
HARNESS = REPO / 'evals' / 'harness'

if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from claude_runner import (  # noqa: E402 - the in-repo harness, imported after the path fix
    cleanup_dir,
    make_isolated_config,
    run_agent,
)

BANK_PATH = HERE / 'bank.json'
TABLE_PATH = HERE / 'firing_table.json'
CWD_FIXTURE = HERE / 'cwd_fixture'
PLUGIN_DIR = REPO / 'plugins' / 'experiment-discipline'
RUNS_PATH = HERE / 'runs.jsonl'
RECORD_PATH = HERE / 'record.yaml'

# --- the frozen run configuration -------------------------------------------
#
# Every value here is restated in record.yaml under `run_config` and a test asserts
# the two agree, so the record cannot describe a run this module would not perform.

# The repo's standard agent model (evals/config.json `agent_model` at freeze time).
# The only in-repo cost anchor is a trigger-arm run at about $0.099 per read-only
# 3-turn spawn on this same model; the detector's spawns are task-shaped at a turn
# cap of 6, which is why the per-run band below is quoted well above that anchor
# rather than derived from it.
MODEL = 'claude-sonnet-4-6'
MAX_TURNS = 6
REPEATS = 2
SEED = 20260725
PER_RUN_BUDGET_USD = 0.40  # the per-spawn --max-budget-usd cap
CEILING_USD = 75.0  # the run halts BEFORE a spawn that could cross this
TIMEOUT_SECONDS = 300
# No --temperature or --top-p flag is passed; the CLI default applies. Named as a
# constant so the record can state it and a test can compare the two.
SAMPLING = 'cli_default'

# Identical across arms, stated explicitly. `Skill` IS in the allowlist: that one
# entry decides whether the control arm can load the skill it ships with, and
# therefore which experiment this is. Writing tools are denied on every arm -- the
# outcomes are properties of the response text, so nothing needs to be written.
ALLOWED_TOOLS = 'Skill,Read,Glob,Grep'
DISALLOWED_TOOLS = 'Write,Edit,NotebookEdit,Bash,WebFetch,WebSearch,Task'

# The single frozen insertion point: the injected text, one blank line, the prompt.
INSERTION_POINT = 'prefix_blank_line'

# The per-run cost band the projection is quoted over. A band, not a point: the
# in-repo anchor is a lower bound on a different profile, so an honest projection
# reports a range and lets the ceiling do the enforcing.
COST_BAND_USD = (0.13, 0.31)


def compose(injected: str, prompt: str) -> str:
    """The one place the insertion point lives. An empty injection returns the
    prompt untouched -- the control arm's spawn must not carry a stray blank line
    the other arms do not."""
    return f'{injected}\n\n{prompt}' if injected else prompt


def load_bank(path: str | Path = BANK_PATH) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding='utf-8'))['prompts']


def load_table(path: str | Path = TABLE_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build_plan(
    bank: list[dict[str, Any]], table: dict[str, Any], repeats: int = REPEATS, seed: int = SEED
) -> list[dict[str, Any]]:
    """The full run plan: arms x prompts x repeats, interleaved under a seeded RNG.

    Pure and deterministic -- the same seed yields the same order on every machine,
    which is what makes 'randomized and interleaved' a frozen property rather than a
    description of what happened.
    """
    by_key = {(r['arm'], r['prompt_id']): r for r in table['rows']}
    prompts = {p['id']: p for p in bank}
    jobs: list[dict[str, Any]] = []
    for arm in table['arms']:
        for pid in prompts:
            row = by_key[(arm, pid)]
            for rep in range(repeats):
                jobs.append(
                    {
                        'arm': arm,
                        'prompt_id': pid,
                        'prompt_class': prompts[pid]['class'],
                        'language': prompts[pid]['language'],
                        'repeat': rep,
                        'injected': row['text'],
                        'injected_chars': row['chars'],
                        'fires': row['fires'],
                    }
                )
    random.Random(seed).shuffle(jobs)  # noqa: S311 - run ordering, not cryptography
    return jobs


def projected_cost(n_runs: int) -> tuple[float, float]:
    low, high = COST_BAND_USD
    return round(n_runs * low, 2), round(n_runs * high, 2)


def print_plan(jobs: list[dict[str, Any]], table: dict[str, Any]) -> None:
    low, high = projected_cost(len(jobs))
    print(
        f'act-hint detector: {len(jobs)} runs ({len(table["arms"])} arms x 24 prompts x {REPEATS} repeats)'
    )
    print(f'  model            {MODEL}, max_turns {MAX_TURNS}, sampling: CLI default (unset)')
    print(f'  allowed tools    {ALLOWED_TOOLS}  (identical across arms; Skill IS included)')
    print(f'  disallowed       {DISALLOWED_TOOLS}')
    print(f'  plugin dir       {PLUGIN_DIR.relative_to(REPO).as_posix()}')
    print(f'  cwd fixture      {CWD_FIXTURE.relative_to(REPO).as_posix()}')
    print(f'  insertion point  {INSERTION_POINT}')
    print(f'  order seed       {SEED} (randomized, interleaved)')
    print(f'  per-run cap      ${PER_RUN_BUDGET_USD:.2f}   ceiling ${CEILING_USD:.2f}')
    print(
        f'  projected cost   ${low:.2f} - ${high:.2f} at ${COST_BAND_USD[0]:.2f}-${COST_BAND_USD[1]:.2f}/run'
    )
    print('  per arm:')
    for arm in table['arms']:
        arm_jobs = [j for j in jobs if j['arm'] == arm]
        fired = sum(1 for j in arm_jobs if j['fires'])
        print(f'    {arm:<8} {len(arm_jobs):>3} runs, {fired:>3} carry an injection')
    print(
        f'  first 5 in seeded order: {[(j["arm"], j["prompt_id"], j["repeat"]) for j in jobs[:5]]}'
    )


def verify_materials(record_path: str | Path = RECORD_PATH) -> list[str]:
    """Re-hash every frozen material and compare it against the record's `materials`
    block. Returns the mismatches, empty when the run is measuring what the
    pre-registration describes.

    PyYAML is imported HERE rather than at module scope so the module stays
    stdlib-importable, and its absence RAISES: a material check that quietly skips
    itself would leave the loudest integrity guarantee in this design as decoration.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - the runner supplies PyYAML
        raise SystemExit(
            'run_arms: the frozen-material check needs PyYAML to read record.yaml. '
            'Run under `uv run --no-project --with pyyaml --`; it is not skippable.'
        ) from exc
    sys.path.insert(0, str(HERE))
    import freeze_fill  # the one definition of what a material is and how it hashes

    record = yaml.safe_load(Path(record_path).read_text(encoding='utf-8'))
    stated = record.get('materials') or {}
    problems: list[str] = []
    for key, want in freeze_fill.material_hashes(Path(record_path).parent).items():
        got = (stated.get(key) or {}).get('sha256')
        if got != want:
            rel = freeze_fill.MATERIALS[key][0]
            problems.append(f'{key} ({rel}): record states {got}, file hashes to {want}')
    return problems


def run_one(
    job: dict[str, Any], prompt_text: str, *, config_dir: str | None, cwd: str | None
) -> dict[str, Any]:
    """One measured spawn. The response text is stored; the oracle scores it later,
    so no arm label ever reaches the scoring step."""
    run = run_agent(
        compose(job['injected'], prompt_text),
        plugin_dir=str(PLUGIN_DIR),
        allowed_tools=ALLOWED_TOOLS,
        disallowed_tools=DISALLOWED_TOOLS,
        model=MODEL,
        max_turns=MAX_TURNS,
        max_budget_usd=PER_RUN_BUDGET_USD,
        timeout=TIMEOUT_SECONDS,
        stream=True,
        config_dir=config_dir,
        cwd=cwd,
    )
    return {
        **{k: job[k] for k in ('arm', 'prompt_id', 'prompt_class', 'language', 'repeat')},
        'response': run.result_text or run.assistant_text,
        'is_error': run.is_error,
        'cost_usd': run.cost_usd,
        'num_turns': run.num_turns,
        'activated_skills': sorted(run.activated_skills),
        'plugins_loaded': run.plugins_loaded,
    }


def execute(
    jobs: list[dict[str, Any]],
    prompts: dict[str, str],
    *,
    out: Path,
    config_dir: str | None,
    cwd: str | None,
    spawn=run_one,
) -> tuple[int, float, bool]:
    """Run the plan, appending one JSON line per completed run. Returns
    (completed, spent, halted). `spawn` is the seam a test stubs.

    THE CEILING IS CHECKED BEFORE A RUN, NOT AFTER ONE. Halting once `spent` has
    already passed the ceiling means the ceiling was crossed and then noticed;
    refusing to start a run that its own `--max-budget-usd` cap could take past the
    ceiling means it never is. The margin costs at most one run's cap.

    That margin is also what absorbs a known UNDER-COUNT: `run_agent` retries a
    transient failure internally and returns only the last attempt's AgentRun, so
    earlier attempts' cost is not visible here and `spent` can read low by up to
    (max_attempts - 1) x cap per retried job. The harness exposes no per-attempt
    cost to sum, so the two are stated together deliberately -- read the margin as
    protection against the under-count, not as spare budget.
    """
    spent = 0.0
    completed = 0
    halted = False
    with out.open('a', encoding='utf-8', newline='\n') as fh:
        for i, job in enumerate(jobs, 1):
            if spent + PER_RUN_BUDGET_USD > CEILING_USD:
                halted = True
                print(
                    f'\nHALT before run {i}: ${spent:.2f} spent and one more capped run could '
                    f'cross the ${CEILING_USD:.2f} ceiling. {completed} run(s) complete; the '
                    'pre-registered fallback analyzes complete prompt-pairs only.'
                )
                break
            record = spawn(job, prompts[job['prompt_id']], config_dir=config_dir, cwd=cwd)
            record['seq'] = i
            record['ts'] = round(time.time())
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')
            fh.flush()
            spent += record['cost_usd'] or 0.0
            completed += 1
            if i % 16 == 0:
                print(f'  {i}/{len(jobs)} runs, ${spent:.2f} spent')
    return completed, spent, halted


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # PT-BR prompt text
    ap = argparse.ArgumentParser(description='Run the act-hint detector arms.')
    ap.add_argument('--dry-run', action='store_true', help='print the plan and cost; spend nothing')
    ap.add_argument('--limit', type=int, default=None, help='cap the run to the first N jobs')
    ap.add_argument('--out', default=str(RUNS_PATH), help='append-only run log')
    args = ap.parse_args(argv)

    # Before anything else, and in --dry-run too because it is free: the run must be
    # measuring the materials the pre-registration froze.
    problems = verify_materials()
    for line in problems:
        print(f'FROZEN-MATERIAL MISMATCH: {line}')
    if problems:
        print(
            'refusing to run: a material changed after it was hashed into record.yaml, so '
            'these runs would not measure what the pre-registration describes.'
        )
        return 2
    print('frozen materials verified against record.yaml')

    bank = load_bank()
    table = load_table()
    jobs = build_plan(bank, table)
    print_plan(jobs, table)
    if args.dry_run:
        print('\ndry run: nothing spawned, nothing spent.')
        return 0

    if args.limit:
        jobs = jobs[: args.limit]
        print(
            f'\nNOTE: --limit {args.limit} -- a partial run; the record is not analyzable from it.'
        )
    prompts = {p['id']: p['text'] for p in bank}
    config_dir = make_isolated_config()
    out = Path(args.out)
    try:
        completed, spent, _halted = execute(
            jobs, prompts, out=out, config_dir=config_dir, cwd=str(CWD_FIXTURE)
        )
    finally:
        cleanup_dir(config_dir)
    print(f'\n{completed}/{len(jobs)} runs complete, ${spent:.2f} spent -> {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

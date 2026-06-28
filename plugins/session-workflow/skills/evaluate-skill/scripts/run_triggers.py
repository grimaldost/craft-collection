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


def score_skill(queries: list[dict], repeats: int, trigger_counter, error_counter=None) -> dict:
    """Pooled recall (over positives) and specificity (over negatives) with Wilson
    CIs. `trigger_counter(query_str, repeats) -> k` returns how many of `repeats`
    runs fired the skill; `error_counter(query_str, repeats) -> e` returns how many
    of the NON-firing runs errored (timeout/budget) — those runs carry no evidence
    that the description failed, so recall is also reported with them excluded.
    The strict `recall` (errors count as misses) stays the gated number. An
    `expected_hard` positive — its miss is an accepted model-behavior boundary,
    not a description gap — is scored into `recall_hard` and EXCLUDED from the
    gated `recall`, so tuning stops re-spending on immovable queries while a
    regression stays visible. Pure: inject fake counters in tests, the real ones
    in the CLI."""
    pos_succ = pos_tri = pos_err = 0  # gated recall: non-hard positives
    hard_succ = hard_tri = 0  # reported separately: expected-hard positives
    neg_succ = neg_tri = 0
    per_query = []
    for q in queries:
        k = trigger_counter(q['query'], repeats)
        e = error_counter(q['query'], repeats) if error_counter else 0
        hard = bool(q.get('expected_hard'))
        if q['should_trigger']:
            if hard:
                hard_succ += k
                hard_tri += repeats
            else:
                pos_succ += k
                pos_tri += repeats
                pos_err += e
        else:
            neg_succ += repeats - k  # a correct rejection = a NON-fire on a negative
            neg_tri += repeats
        per_query.append(
            {
                'query': q['query'],
                'should_trigger': q['should_trigger'],
                'expected_hard': hard,
                'k': k,
                'repeats': repeats,
                'rate': (k / repeats if repeats else 0.0),
                'errors_no_activation': e,
            }
        )
    pos_valid = pos_tri - pos_err
    return {
        'recall': (pass_rate(pos_succ, pos_tri) if pos_tri else None),
        'specificity': pass_rate(neg_succ, neg_tri),
        'recall_ci': (list(wilson_interval(pos_succ, pos_tri)) if pos_tri else None),
        'specificity_ci': list(wilson_interval(neg_succ, neg_tri)),
        'recall_excl_errors': (pass_rate(pos_succ, pos_valid) if pos_valid > 0 else None),
        'recall_excl_errors_ci': (
            list(wilson_interval(pos_succ, pos_valid)) if pos_valid > 0 else None
        ),
        'errors_no_activation_positive': pos_err,
        'recall_hard': (pass_rate(hard_succ, hard_tri) if hard_tri else None),
        'recall_hard_ci': (list(wilson_interval(hard_succ, hard_tri)) if hard_tri else None),
        'n_positive': sum(1 for q in queries if q['should_trigger']),
        'n_positive_hard': sum(
            1 for q in queries if q['should_trigger'] and q.get('expected_hard')
        ),
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


def validate_queries(queries: list[dict]) -> list[str]:
    """Structural pre-run check on a trigger dataset: return a list of problems
    (empty == valid). The mechanical spec-MUST — every entry well-formed,
    `expected_hard` only on a documented positive, no duplicate queries — is
    validated BEFORE a run so a malformed dataset fails fast instead of after
    spending spawns. Pure."""
    problems: list[str] = []
    seen: set[str] = set()
    for i, q in enumerate(queries):
        if not isinstance(q, dict):
            problems.append(f'entry {i}: not an object')
            continue
        query = q.get('query')
        tag = repr(str(query)[:40])
        if not isinstance(query, str) or not query.strip():
            problems.append(f'entry {i}: missing or empty "query"')
        if not isinstance(q.get('should_trigger'), bool):
            problems.append(f'entry {i} ({tag}): "should_trigger" must be a bool')
        if 'expected_hard' in q:
            if not isinstance(q['expected_hard'], bool):
                problems.append(f'entry {i} ({tag}): "expected_hard" must be a bool')
            elif q['expected_hard']:
                if not q.get('should_trigger'):
                    problems.append(
                        f'entry {i} ({tag}): "expected_hard" is only valid on a positive '
                        '(should_trigger=true)'
                    )
                if not (isinstance(q.get('note'), str) and q['note'].strip()):
                    problems.append(
                        f'entry {i} ({tag}): "expected_hard" requires a "note" documenting '
                        'why the miss is immovable'
                    )
        if isinstance(query, str):
            if query in seen:
                problems.append(f'entry {i}: duplicate query {tag}')
            seen.add(query)
    return problems


def merge_report(blob: dict, skill: str, score: dict) -> tuple[dict, bool]:
    """Pure merge of one skill's `score` into the report blob. Returns
    (new_blob, clobbered_fuller): `clobbered_fuller` is True when an existing
    entry for `skill` had MORE total_runs than `score` — i.e. a partial
    (--limit/--repeats) run is about to overwrite a fuller one. Does not mutate
    the input blob."""
    prior = blob.get(skill) or {}
    clobbered = prior.get('total_runs', 0) > score.get('total_runs', 0)
    new_blob = dict(blob)
    new_blob[skill] = score
    return new_blob, clobbered


def run_skill(
    skill: str,
    queries: list[dict],
    *,
    plugin_dir: str,
    cfg: dict,
    repeats: int,
    concurrency: int,
    config_dir: str,
    cwd: str,
) -> dict:
    """Spawn every (query x repeat) run concurrently, tally activations, score."""
    jobs = [(i, q['query']) for i, q in enumerate(queries) for _ in range(repeats)]

    def worker(job):
        i, qstr = job
        run = run_agent(
            qstr,
            plugin_dir=plugin_dir,
            allowed_tools=cfg['allowed_tools_trigger'],
            disallowed_tools=cfg.get('disallowed_tools_trigger', ''),
            append_system_prompt=cfg.get('trigger_routing_frame', ''),
            model=cfg['agent_model'],
            max_turns=cfg.get('trigger_max_turns', MAX_TURNS_TRIGGER),
            max_budget_usd=cfg['max_budget_usd'],
            timeout=cfg['timeout_seconds'],
            stream=True,
            config_dir=config_dir,
            cwd=cwd,
        )
        text = (run.result_text or '') if run.is_error else ''  # carry cause only on error
        return (i, run.activated(skill), run.cost_usd or 0.0, run.is_error, text)

    results = map_concurrent(jobs, worker, concurrency=concurrency)
    counts = [0] * len(queries)
    err_counts = [0] * len(queries)  # errored runs that did NOT fire, per query
    err_texts: list[str] = []  # raw cause text from errored runs, for a sample
    cost = 0.0
    errors = errors_no_act = 0
    for i, fired, c, err, text in results:
        counts[i] += 1 if fired else 0
        cost += c
        if err:
            errors += 1
            if text:
                err_texts.append(text)
            if not fired:  # the only kind that can distort the score
                errors_no_act += 1
                err_counts[i] += 1
    by_str = {queries[i]['query']: counts[i] for i in range(len(queries))}
    err_by_str = {queries[i]['query']: err_counts[i] for i in range(len(queries))}
    score = score_skill(
        queries, repeats, lambda s, _r: by_str[s], error_counter=lambda s, _r: err_by_str[s]
    )
    score['cost_usd'] = round(cost, 4)
    score['error_runs'] = errors  # mostly benign: positives truncate at max_turns
    score['error_runs_no_activation'] = errors_no_act  # the diagnostic that matters
    score['total_runs'] = len(jobs)
    score['error_samples'] = distinct_error_samples(err_texts)  # WHY they errored, sampled
    return score


def write_report(skill: str, score: dict) -> bool:
    """Merge `score` into report/triggers.json atomically (temp + replace, so a
    crash mid-write can't corrupt the blob). Returns `clobbered_fuller` — True when
    a smaller (partial) run overwrote a fuller existing entry for the same skill,
    so the CLI can warn loudly rather than only printing the pre-run NOTE."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / 'triggers.json'
    blob: dict = {}
    if path.exists():
        try:
            blob = json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, ValueError):
            blob = {}
    new_blob, clobbered = merge_report(blob, skill, score)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(new_blob, indent=2), encoding='utf-8')
    tmp.replace(path)  # atomic rename on the same filesystem
    return clobbered


def distinct_error_samples(texts: list[str], limit: int = 3, width: int = 200) -> list[dict]:
    """Group raw per-run error strings into up to `limit` DISTINCT samples, most
    frequent first, each truncated to `width` chars with an occurrence count. This
    surfaces *why* runs errored (401 vs timeout vs network) — the diagnostic
    `run_skill` otherwise discards, since it keeps each run's `is_error` bool but not
    its `result_text` (2026-06-19-eval-harness-auth-race#3, when a 401 had to be
    recovered by hand via a separate `claude -p` probe). Blank/whitespace-only
    strings are dropped (a non-errored run carries no text). The stable sort keeps
    first-seen order on count ties, so a single dominant cause reads as 'the first
    non-empty result_text' (the original ask). Pure: feed it the collected error
    texts; no truncation/dedup is done upstream."""
    counts: dict[str, int] = {}
    for t in texts:
        if not t or not t.strip():
            continue
        key = t.strip()[:width]
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts, key=lambda k: -counts[k])  # stable -> ties keep first-seen
    return [{'text': k, 'count': counts[k]} for k in ranked[:limit]]


def format_error_samples(samples: list[dict]) -> list[str]:
    """Render `distinct_error_samples()` output as printable lines (empty list when
    there are no samples, so a clean run prints nothing). Kept separate from the
    extractor so the all-errored INVALID branch and the normal partial-error path
    print identically."""
    if not samples:
        return []
    lines = ['error sample(s) — distinct run.result_text, most frequent first:']
    lines += [f'  ({s["count"]}x) {s["text"]}' for s in samples]
    return lines


def all_runs_errored(score: dict) -> bool:
    """True when every spawn errored — an infrastructure failure (auth / network /
    CLI), not a measurement. Such a run is the harness's own fail-open trap: a
    did-not-run counts as a non-fire, so recall reads 0.00 (looks like the skill
    never triggers) and specificity reads 1.00 (every negative 'correctly' silent)
    — both artifacts of nothing running, not signal. Callers must refuse to report
    or persist it as a result. (Observed 2026-06-19: a concurrent run 401'd at $0
    after the OAuth token aged mid-burst and every spawn errored.)"""
    return score.get('total_runs', 0) > 0 and score.get('error_runs', 0) == score['total_runs']


def preflight_auth(cfg: dict, config_dir: str, cwd: str) -> tuple[bool, str]:
    """One cheap spawn before the fan-out: fail fast if auth is dead (don't burn N
    real spawns to discover a 401), and warm/refresh the token ONCE so the
    concurrent fan-out doesn't have many spawns racing to refresh a single-use
    token simultaneously (the race that invalidated auth on 2026-06-19). Returns
    (ok, detail)."""
    probe = run_agent(
        'Reply with the single word: ok',
        allowed_tools='',
        model=cfg['agent_model'],
        max_turns=1,
        max_budget_usd=cfg['max_budget_usd'],
        timeout=cfg['timeout_seconds'],
        config_dir=config_dir,
        cwd=cwd,
    )
    return (not probe.is_error), (probe.result_text or 'unknown error')[:200]


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # query text is unicode
    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    ap = argparse.ArgumentParser(description='Skill triggering eval (axes 1 & 3)')
    ap.add_argument('skill', choices=sorted(cfg['plugin_of_skill']))
    ap.add_argument(
        '--limit', type=int, default=None, help='cap to first N positives + N negatives'
    )
    ap.add_argument('--repeats', type=int, default=cfg['agent_repeats'])
    ap.add_argument('--concurrency', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)

    queries = load_queries(args.skill, args.limit)
    problems = validate_queries(queries)
    if problems:
        print(f'dataset {args.skill}.json has {len(problems)} problem(s) — fix before running:')
        for p in problems:
            print(f'  - {p}')
        return 1
    plugin = cfg['plugin_of_skill'][args.skill]
    plugin_dir = str(REPO / 'plugins' / plugin)
    n_spawn = len(queries) * args.repeats
    print(
        f'skill={args.skill} plugin={plugin} queries={len(queries)} '
        f'repeats={args.repeats} -> {n_spawn} spawns '
        f'(<= ${n_spawn * cfg["max_budget_usd"]:.2f} ceiling)'
    )
    if args.dry_run:
        for q in queries:
            print(f'  [{"+" if q["should_trigger"] else "-"}] {q["query"][:80]}')
        return 0
    if args.limit or args.repeats != cfg['agent_repeats']:
        print(
            f'NOTE: partial run — overwrites any full "{args.skill}" entry in '
            f'report/triggers.json; re-run full (or restore a backup) before aggregating'
        )

    config_dir = make_isolated_config()
    cwd = tempfile.mkdtemp(prefix='eval_trig_')
    try:
        ok, detail = preflight_auth(cfg, config_dir, cwd)
        if not ok:
            print(
                f'\nPRE-FLIGHT FAILED: the auth/CLI probe errored ({detail}). '
                f'Re-login (claude /login) and retry — not spending the {n_spawn} run spawns.'
            )
            return 2
        score = run_skill(
            args.skill,
            queries,
            plugin_dir=plugin_dir,
            cfg=cfg,
            repeats=args.repeats,
            concurrency=args.concurrency,
            config_dir=config_dir,
            cwd=cwd,
        )
    finally:
        cleanup_dir(cwd)
        cleanup_dir(config_dir)

    if all_runs_errored(score):
        hint = (
            '$0 cost points to auth — re-login (claude /login) and re-run.'
            if not score['cost_usd']
            else 'Likely network/CLI — re-run.'
        )
        print(
            f'\nINVALID: all {score["total_runs"]} runs errored (cost=${score["cost_usd"]}). '
            f'Infrastructure failure, NOT a measurement — the recall/specificity it would print '
            f'are artifacts of nothing running, so the result is discarded (not written to '
            f'report/triggers.json). {hint}'
        )
        for line in format_error_samples(score.get('error_samples') or []):
            print(line)
        return 2

    clobbered = write_report(args.skill, score)
    if clobbered:
        print(
            f'WARNING: this run overwrote a FULLER existing "{args.skill}" entry in '
            'report/triggers.json (a partial --limit/--repeats run). Re-run full or '
            'restore a backup before aggregating.'
        )
    g = cfg['gates']
    action = args.skill in set(cfg.get('action_discipline_skills', []))
    slo, shi = score['specificity_ci']
    if score['recall'] is None:
        rec_ok = 'INFO (no gated positives — all expected_hard, or none in the slice)'
    elif action:
        rec_ok = 'INFO (action-discipline: not gated on trigger-arm recall)'
    else:
        rec_ok = 'PASS' if score['recall'] >= g['trigger_recall'] else 'FAIL'
    spec_ok = 'PASS' if score['specificity'] >= g['trigger_specificity'] else 'FAIL'
    if score['recall'] is None:
        print(f'\nrecall      = n/a    gate>={g["trigger_recall"]}  {rec_ok}')
    else:
        rlo, rhi = score['recall_ci']
        print(
            f'\nrecall      = {score["recall"]:.2f}  CI[{rlo:.2f},{rhi:.2f}]  '
            f'gate>={g["trigger_recall"]}  {rec_ok}'
        )
    if action:
        print(
            '              this skill activates during real work; the gated recall '
            "proxy is the grading arm's activation rate (grade_tasks / scorecard)"
        )
    if score['errors_no_activation_positive'] > 0:
        ree = score['recall_excl_errors']
        if ree is None:
            print(
                f'recall excl. errored runs = n/a (all '
                f'{score["errors_no_activation_positive"]} non-firing positive runs errored)'
            )
        else:
            elo, ehi = score['recall_excl_errors_ci']
            print(
                f'recall excl. errored runs = {ree:.2f}  CI[{elo:.2f},{ehi:.2f}]  '
                f'({score["errors_no_activation_positive"]} errored positive runs '
                f'carry no description evidence)'
            )
    print(
        f'specificity = {score["specificity"]:.2f}  CI[{slo:.2f},{shi:.2f}]  '
        f'gate>={g["trigger_specificity"]}  {spec_ok}'
    )
    if score.get('n_positive_hard'):
        hlo, hhi = score['recall_hard_ci']
        print(
            f'recall (expected-hard) = {score["recall_hard"]:.2f}  CI[{hlo:.2f},{hhi:.2f}]  '
            f'({score["n_positive_hard"]} immovable positive(s): reported, NOT gated)'
        )
    print(
        f'cost=${score["cost_usd"]}  error_runs={score["error_runs"]}/{score["total_runs"]} '
        f'(no-activation errors={score["error_runs_no_activation"]})'
    )
    for line in format_error_samples(score.get('error_samples') or []):
        print(line)
    for pq in score['per_query']:  # surface misses for description tuning
        miss = (pq['should_trigger'] and pq['rate'] < 1.0) or (
            not pq['should_trigger'] and pq['rate'] > 0.0
        )
        if miss:
            sign = '+' if pq['should_trigger'] else '-'
            err = pq.get('errors_no_activation', 0)
            err_note = f' err={err}/{pq["repeats"]}' if err else ''
            hard_note = ' [expected-hard: not gated]' if pq.get('expected_hard') else ''
            print(
                f'  miss [{sign}] k={pq["k"]}/{pq["repeats"]}{err_note}{hard_note} '
                f'{pq["query"][:70]}'
            )
    return 0


if __name__ == '__main__':
    sys.exit(main())

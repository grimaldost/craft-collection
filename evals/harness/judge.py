"""LLM-as-judge for the eval harness, via `claude -p` (no plugin, isolated config).

Layers:
- `extract_verdict` — pure: pull a JSON verdict out of messy judge text.
- `aggregate_pointwise` / `decide_pairwise` — pure: combine repeated verdicts and
  decide a swap-order pairwise winner. Unit-tested.
- `judge_pointwise` / `judge_pairwise` — spawn the judge agent(s). `runner` is
  injectable so the orchestration can be exercised without real spawns.

The judge runs at the CLI's default sampling (no temp-0); mitigations are a strict
JSON rubric, deterministic score recomputation from rubric weights, K-repeat
majority with a reported agreement number, and swap-order on pairwise.
"""

from __future__ import annotations

import json
import re

from claude_runner import run_agent

JUDGE_THRESHOLD = 0.7  # score at/above which a pointwise verdict counts as a pass


def extract_verdict(text: str) -> dict | None:
    """Pull a JSON verdict object out of a judge's (messy) text reply.

    Tries a fenced ```json block first, then the first balanced {...} substring.
    Returns the parsed dict, or None if no JSON object is found.
    """
    if not text:
        return None
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    start = text.find('{')
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break  # not valid JSON; advance to the next '{'
        start = text.find('{', start + 1)
    return None


def score_from_criteria(verdict: dict, rubric: list[dict],
                        threshold: float = JUDGE_THRESHOLD) -> dict:
    """Recompute score/pass from rubric weights x the judge's per-criterion `met`
    flags, so the number doesn't depend on the model's arithmetic. Falls back to
    the model's own score if no usable criteria list is present."""
    crits = verdict.get('criteria')
    if not isinstance(crits, list) or not crits:
        return verdict
    weight = {c['id']: c.get('weight', 1) for c in rubric}
    total = sum(weight.values()) or 1
    got = sum(weight.get(c.get('id'), 0) for c in crits if c.get('met'))
    out = dict(verdict)
    out['score'] = got / total
    out['pass'] = out['score'] >= threshold
    return out


def aggregate_pointwise(verdicts: list[dict]) -> dict:
    """Combine K pointwise verdicts on one output: mean score, majority pass, and
    the agreement fraction (how many concur with the majority pass decision)."""
    scored = [v for v in verdicts if v]
    if not scored:
        return {'score': 0.0, 'pass': False, 'agreement': 0.0, 'n': 0}
    scores = [float(v.get('score', 0.0)) for v in scored]
    passes = [bool(v.get('pass', False)) for v in scored]
    n_pass = sum(passes)
    return {
        'score': sum(scores) / len(scores),
        'pass': n_pass * 2 > len(passes),
        'agreement': max(n_pass, len(passes) - n_pass) / len(passes),
        'n': len(scored),
    }


def decide_pairwise(winner_order1: str, winner_order2: str) -> dict:
    """Swap-order pairwise decision. Each arg is the ACTUAL winner ('A'|'B'|'tie')
    in one presentation order. A response wins only if BOTH orders name it — this
    controls for position bias, which matters because the CLI can't pin temp-0.
    Disagreement (incl. any 'tie') collapses to 'tie'."""
    if winner_order1 == winner_order2 and winner_order1 in ('A', 'B'):
        return {'winner': winner_order1, 'agreement': True}
    return {'winner': 'tie', 'agreement': winner_order1 == winner_order2}


def _render_pointwise(task: str, output: str, rubric: list[dict]) -> str:
    lines = [f'- [id={c["id"]} weight={c.get("weight", 1)}] {c["text"]}' for c in rubric]
    crit_block = '\n'.join(lines)
    return (
        'You are a strict, fair grader. Judge how well the RESPONSE satisfies each '
        'rubric criterion for the TASK. Judge ONLY what the RESPONSE actually '
        'contains — do not give credit for what it could have done.\n\n'
        f'TASK:\n{task}\n\n'
        f'RESPONSE:\n{output}\n\n'
        f'RUBRIC:\n{crit_block}\n\n'
        'For each criterion decide met=true or met=false. Reply with ONLY this '
        'JSON object and nothing else:\n'
        '{"criteria":[{"id":"<id>","met":true,"evidence":"<short quote or reason>"}],'
        '"reason":"<one sentence overall>"}'
    )


def judge_pointwise(task: str, output: str, rubric: list[dict], *, model: str,
                    repeats: int = 1, runner=run_agent, max_budget_usd: float = 0.25,
                    timeout: int = 180, threshold: float = JUDGE_THRESHOLD) -> dict:
    """Grade one output against the rubric `repeats` times; recompute each score
    from weights, then aggregate (mean score, majority pass, agreement)."""
    prompt = _render_pointwise(task, output, rubric)
    verdicts = []
    for _ in range(repeats):
        r = runner(prompt, plugin_dir=None, allowed_tools='', model=model,
                   max_turns=1, max_budget_usd=max_budget_usd, timeout=timeout,
                   stream=False)
        v = extract_verdict(r.result_text)
        if v:
            verdicts.append(score_from_criteria(v, rubric, threshold))
    agg = aggregate_pointwise(verdicts)
    agg['verdicts'] = verdicts
    return agg


def _render_pairwise(task: str, first: str, second: str, criterion: str) -> str:
    return (
        'You are a strict, fair judge. For the TASK, decide which response better '
        f'satisfies this CRITERION.\n\nCRITERION: {criterion}\n\n'
        f'TASK:\n{task}\n\n--- RESPONSE 1 ---\n{first}\n\n--- RESPONSE 2 ---\n{second}\n\n'
        'Reply with ONLY this JSON object and nothing else:\n'
        '{"winner":"first","reason":"<one sentence>"}\n'
        '(winner must be "first", "second", or "tie".)'
    )


def _ask_pairwise(task, first, second, criterion, *, model, runner,
                  max_budget_usd, timeout) -> str:
    prompt = _render_pairwise(task, first, second, criterion)
    r = runner(prompt, plugin_dir=None, allowed_tools='', model=model, max_turns=1,
               max_budget_usd=max_budget_usd, timeout=timeout, stream=False)
    v = extract_verdict(r.result_text) or {}
    w = str(v.get('winner', 'tie')).strip().lower()
    return w if w in ('first', 'second', 'tie') else 'tie'


def judge_pairwise(task: str, out_a: str, out_b: str, criterion: str, *, model: str,
                   runner=run_agent, max_budget_usd: float = 0.25,
                   timeout: int = 180) -> dict:
    """Ask the judge twice with A/B swapped; A is the WITH-skill output, B WITHOUT.
    Returns a winner only if both orderings agree (else 'tie')."""
    v1 = _ask_pairwise(task, out_a, out_b, criterion, model=model, runner=runner,
                       max_budget_usd=max_budget_usd, timeout=timeout)
    w1 = {'first': 'A', 'second': 'B', 'tie': 'tie'}[v1]
    v2 = _ask_pairwise(task, out_b, out_a, criterion, model=model, runner=runner,
                       max_budget_usd=max_budget_usd, timeout=timeout)
    w2 = {'first': 'B', 'second': 'A', 'tie': 'tie'}[v2]
    decision = decide_pairwise(w1, w2)
    decision['order1'], decision['order2'] = w1, w2
    return decision

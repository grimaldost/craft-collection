#!/usr/bin/env python3
"""Assumption smoke checks (plan Task 2.2 — the go/no-go gate).

Runs three real `claude -p` agents and reports PASS/FAIL for the three
assumptions the rest of the harness depends on. Run from the repo root:

    python evals/harness/smoke.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from claude_runner import run_agent
from judge import extract_verdict

REPO = Path(__file__).resolve().parents[2]
CFG = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
SESSION_WORKFLOW = str(REPO / 'plugins' / 'session-workflow')


def _check(name: str, ok: bool, detail: str = '') -> bool:
    print(f'[{"PASS" if ok else "FAIL"}] {name}\n        {detail}')
    return ok


def main() -> int:
    results: list[bool] = []

    # 1. Does --bare + --plugin-dir load the plugin without error?
    r1 = run_agent('Reply with the single word: hi.', plugin_dir=SESSION_WORKFLOW,
                   allowed_tools='Read', model=CFG['agent_model'], max_turns=2,
                   max_budget_usd=CFG['max_budget_usd'], timeout=CFG['timeout_seconds'])
    results.append(_check(
        '1. plugin loads under --bare + --plugin-dir',
        r1.plugin_loaded('session-workflow') and not r1.plugin_errors,
        f'plugins_loaded={r1.plugins_loaded} plugin_errors={r1.plugin_errors} '
        f'is_error={r1.is_error} result={r1.result_text[:80]!r}'))

    # 2. Does a skill auto-activate, and is it detectable in stream-json?
    prompt2 = (
        'We just finished a working session. Decisions: (a) chose Qdrant over LanceDB '
        'for in-traversal filtering; (b) set HNSW m=16. Dead end: tried a three-tier '
        'store hierarchy and abandoned it because the middle tier had no backend. '
        'Now: journal this session.')
    r2 = run_agent(prompt2, plugin_dir=SESSION_WORKFLOW, allowed_tools='Skill,Read,Glob,Grep',
                   model=CFG['agent_model'], max_turns=CFG['max_turns'],
                   max_budget_usd=CFG['max_budget_usd'], timeout=CFG['timeout_seconds'])
    results.append(_check(
        '2. journaling-sessions auto-activates & is detected',
        r2.activated('journaling-sessions'),
        f'activated_skills={sorted(r2.activated_skills)} '
        f'output_has_ENTRY_START={"ENTRY_START" in r2.result_text}'))

    # 3. Does a CLI judge return parseable JSON?
    judge_prompt = (
        'You are a strict grader. Reply with ONLY a JSON object '
        '{"score": <0..1 float>, "pass": <true|false>, "reason": "<short>"} and nothing '
        'else. Task: does the text "the cat sat on the mat" contain the word "cat"? '
        'pass=true if it does.')
    r3 = run_agent(judge_prompt, plugin_dir=None, allowed_tools='', model=CFG['judge_model'],
                   max_turns=1, max_budget_usd=CFG['max_budget_usd'],
                   timeout=CFG['timeout_seconds'], stream=False)
    verdict = extract_verdict(r3.result_text)
    results.append(_check(
        '3. CLI judge returns parseable JSON',
        verdict is not None,
        f'verdict={verdict} raw={r3.result_text[:120]!r}'))

    print()
    print('SMOKE RESULT:', 'ALL PASS' if all(results) else 'SOME FAILED')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())

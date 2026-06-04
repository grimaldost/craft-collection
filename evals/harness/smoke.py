#!/usr/bin/env python3
"""Assumption smoke checks (plan Task 2.2 — the go/no-go gate).

Runs three real `claude -p` agents in an isolated, authenticated-but-skill-free
config (copied credentials, no plugins) and reports PASS/FAIL for the three
assumptions the rest of the harness depends on. Run from the repo root:

    python evals/harness/smoke.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from claude_runner import cleanup_dir, make_isolated_config, run_agent
from judge import extract_verdict

REPO = Path(__file__).resolve().parents[2]
CFG = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
SESSION_WORKFLOW = str(REPO / 'plugins' / 'session-workflow')


def _check(name: str, ok: bool, detail: str = '') -> bool:
    print(f'[{"PASS" if ok else "FAIL"}] {name}\n        {detail}')
    return ok


def main() -> int:
    cfg_dir = make_isolated_config()
    work = tempfile.mkdtemp(prefix='eval_work_')
    common = dict(config_dir=cfg_dir, cwd=work, model=CFG['agent_model'],
                  max_budget_usd=CFG['max_budget_usd'], timeout=CFG['timeout_seconds'])
    results: list[bool] = []
    try:
        # 1. clean config is authenticated, and --plugin-dir loads the plugin cleanly.
        r1 = run_agent('Reply with the single word: hi.', plugin_dir=SESSION_WORKFLOW,
                       allowed_tools='Read', max_turns=2, **common)
        results.append(_check(
            '1. authed clean config + plugin loads',
            (not r1.is_error) and r1.plugin_loaded('session-workflow') and not r1.plugin_errors,
            f'is_error={r1.is_error} plugins={r1.plugins_loaded} errors={r1.plugin_errors}'))

        # 2. the skill auto-activates and is detectable in stream-json.
        prompt2 = (
            'We just finished a working session. Decisions: (a) chose Qdrant over LanceDB '
            'for in-traversal filtering; (b) set HNSW m=16. Dead end: tried a three-tier '
            'store hierarchy and abandoned it because the middle tier had no backend. '
            'Now: journal this session.')
        r2 = run_agent(prompt2, plugin_dir=SESSION_WORKFLOW, allowed_tools='Skill,Read,Glob,Grep',
                       max_turns=CFG['max_turns'], **common)
        results.append(_check(
            '2. journaling-sessions auto-activates & is detected',
            r2.activated('journaling-sessions'),
            f'activated={sorted(r2.activated_skills)} '
            f'ENTRY_START_in_output={"ENTRY_START" in r2.result_text}'))

        # 3. a CLI judge (no plugin) returns parseable JSON.
        judge_prompt = (
            'You are a strict grader. Reply with ONLY a JSON object '
            '{"score": <0..1 float>, "pass": <true|false>, "reason": "<short>"} and nothing '
            'else. Task: does "the cat sat on the mat" contain the word "cat"? pass=true if so.')
        r3 = run_agent(judge_prompt, allowed_tools='', max_turns=1, stream=False,
                       model=CFG['judge_model'], config_dir=cfg_dir, cwd=work,
                       max_budget_usd=CFG['max_budget_usd'], timeout=CFG['timeout_seconds'])
        verdict = extract_verdict(r3.result_text)
        results.append(_check('3. CLI judge returns parseable JSON', verdict is not None,
                              f'verdict={verdict} raw={r3.result_text[:120]!r}'))
    finally:
        cleanup_dir(work)
        cleanup_dir(cfg_dir)

    print()
    print('SMOKE RESULT:', 'ALL PASS' if all(results) else 'SOME FAILED')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())

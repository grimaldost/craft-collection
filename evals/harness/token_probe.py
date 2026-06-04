#!/usr/bin/env python3
"""Measure the token cost of journaling a session — to decide whether proactive
(autonomous) journaling is affordable enough to enable by default.

Per realistic session fixture, runs three arms and reports input/output tokens +
cost:
  - WITHOUT  : no skill, "we're wrapping up, thanks" -> baseline closing cost.
  - WITH-auto: skill loaded, SAME closing prompt -> does it auto-fire, and at what
               token cost? (this is the autonomous scenario)
  - WITH-expl: skill loaded, "journal this session" -> explicit-invocation cost.

The autonomous overhead = WITH-auto minus WITHOUT. Arms run sequentially (clean
measurement). WITH and WITHOUT use SEPARATE config dirs (no plugin-cache leak).

    python evals/harness/token_probe.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from claude_runner import cleanup_dir, make_isolated_config, run_agent

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / 'evals' / 'tasks' / 'journaling-sessions' / 'fixtures'
CLOSE = "\n\n-----\n\nThat's everything for today — we're wrapping up here. Thanks."
EXPLICIT = "\n\n-----\n\nJournal this session."


def _in_tokens(u: dict) -> int:
    return (u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0)
            + u.get('cache_creation_input_tokens', 0))


def probe(label, prompt, plugin_dir, cfg, cfgdir) -> dict:
    cwd = tempfile.mkdtemp(prefix='tok_')
    try:
        run = run_agent(prompt, plugin_dir=plugin_dir,
                        allowed_tools=cfg['allowed_tools_task'], model=cfg['agent_model'],
                        max_turns=cfg['max_turns'], max_budget_usd=cfg['max_budget_usd'],
                        timeout=cfg['timeout_seconds'], stream=True,
                        config_dir=cfgdir, cwd=cwd)
    finally:
        cleanup_dir(cwd)
    return {'label': label, 'activated': run.activated('journaling-sessions'),
            'in': _in_tokens(run.usage), 'out': run.usage.get('output_tokens', 0),
            'cost': round(run.cost_usd or 0.0, 4), 'turns': run.num_turns,
            'is_error': run.is_error, 'usage': run.usage}


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    plugin = str(REPO / 'plugins' / 'session-workflow')
    cfg_with = make_isolated_config()
    cfg_without = make_isolated_config()
    rows = []
    try:
        for fx in ('decision-session.md', 'reference-reading.md'):
            base = (FIX / fx).read_text(encoding='utf-8')
            short = fx.replace('.md', '')
            rows.append(probe(f'{short} | WITHOUT (just close)', base + CLOSE, None, cfg, cfg_without))
            rows.append(probe(f'{short} | WITH  (auto-journal)', base + CLOSE, plugin, cfg, cfg_with))
            rows.append(probe(f'{short} | WITH  (explicit)', base + EXPLICIT, plugin, cfg, cfg_with))
    finally:
        cleanup_dir(cfg_with)
        cleanup_dir(cfg_without)

    print(f'\n{"arm":34s} {"act":5s} {"in_tok":>8s} {"out_tok":>8s} {"cost$":>8s} {"turns":>5s}')
    print('-' * 72)
    for r in rows:
        print(f'{r["label"]:34s} {str(r["activated"]):5s} {r["in"]:>8d} {r["out"]:>8d} '
              f'{r["cost"]:>8} {r["turns"]:>5d}')

    print('\nAUTONOMOUS OVERHEAD  (WITH-auto  -  WITHOUT), per fixture:')
    for i in range(0, len(rows), 3):
        wo, wa = rows[i], rows[i + 1]
        fxname = wo['label'].split('|')[0].strip()
        print(f'  {fxname:20s}  +{wa["in"] - wo["in"]:>6d} in   '
              f'+{wa["out"] - wo["out"]:>6d} out   +${round(wa["cost"] - wo["cost"], 4):<7}  '
              f'(auto-fired={wa["activated"]})')

    rpt = REPO / 'evals' / 'report'
    rpt.mkdir(parents=True, exist_ok=True)
    (rpt / 'token_probe.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(f'\nwrote {rpt / "token_probe.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

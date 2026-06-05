#!/usr/bin/env python3
"""Behavioral test for journaling-sessions' write-vs-offer routing.

The contract (in the skill body): when the skill activates PROACTIVELY on a bare
session-end (the user did not ask to journal), it must emit a one-line OFFER, not
silently write the full journal. When the user asks EXPLICITLY, it writes.

Per fixture, two WITH-skill arms:
  - proactive : bare "wrapping up, thanks"  -> expect an OFFER (short message), or
                the skill staying silent (selectivity). Writing = FAIL (regressed).
  - explicit  : "journal this session"      -> expect a WRITTEN journal (envelope).

RED baseline (report/token_probe.json, pre-edit): the proactive arm wrote the full
~8.5k-token journal. GREEN: the proactive arm now offers (out tokens collapse).

    python evals/harness/offer_probe.py
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
EXPLICIT = '\n\n-----\n\nJournal this session.'
# Soft, session-ending preserve-request — the regression risk: the new routing must
# read this as "the user asked" (write), NOT as a bare wind-down (offer).
IMPLICIT = "\n\n-----\n\nBefore I move on, make sure we don't lose what we worked out here."

_OFFER_CUES = (
    'want me to',
    'would you like',
    'let me know',
    'shall i',
    'i can ',
    'happy to',
    'if you',
    'should i',
)


def _files_text(cwd: str, cap: int = 20000) -> str:
    chunks = []
    for p in sorted(Path(cwd).rglob('*')):
        if p.is_file():
            try:
                chunks.append(p.read_text(encoding='utf-8', errors='replace'))
            except OSError:
                continue
    return '\n\n'.join(chunks)[:cap]


def _classify(message: str, files_text: str, out_tokens: int) -> tuple[str, str]:
    """Label the arm's behavior: 'wrote' a journal, 'offered' to, or 'other'.

    Output-token volume is the primary, robust discriminator: generating a journal
    (whether to a file, an envelope, or mid-stream prose) costs thousands of output
    tokens; an offer costs a few hundred — here 885 vs 8500/10305, a clean ~10x
    gap. Envelope and file checks corroborate. This is deliberately blind to WHERE
    the journal landed, so it is unaffected by the known mid-stream capture gap (a
    written journal still shows in the token count even when its text is neither the
    final message nor an on-disk file — only a short "10 entries written" report is)."""
    combined = f'{message}\n{files_text}'
    entries = combined.count('ENTRY_START')
    if entries:
        return 'wrote', f'{entries} envelope entr{"ies" if entries > 1 else "y"}'
    if len(files_text.strip()) > 800:
        return 'wrote', f'{len(files_text.strip())}-char journal file (no envelope)'
    if out_tokens >= 2500:
        return 'wrote', f'{out_tokens} output tokens — full journal generated'
    low = message.lower()
    names_journal = any(w in low for w in ('journal', 'capture', 'log'))
    if names_journal and ('?' in message or any(p in low for p in _OFFER_CUES)):
        return 'offered', f'short ({out_tokens} out-tok) message proposing to journal'
    return 'other', f'{out_tokens} out-tok, neither journal nor offer'


def _in(u: dict) -> int:
    return (
        u.get('input_tokens', 0)
        + u.get('cache_read_input_tokens', 0)
        + u.get('cache_creation_input_tokens', 0)
    )


def arm(label, prompt, plugin, cfg, cfgdir, expect) -> dict:
    cwd = tempfile.mkdtemp(prefix='offer_')
    try:
        run = run_agent(
            prompt,
            plugin_dir=plugin,
            allowed_tools=cfg['allowed_tools_task'],
            model=cfg['agent_model'],
            max_turns=cfg['max_turns'],
            max_budget_usd=cfg['max_budget_usd'],
            timeout=cfg['timeout_seconds'],
            stream=True,
            config_dir=cfgdir,
            cwd=cwd,
        )
        files = _files_text(cwd)
    finally:
        cleanup_dir(cwd)
    activated = run.activated('journaling-sessions')
    behavior, why = _classify(run.result_text or '', files, run.usage.get('output_tokens', 0))
    # Verdict. Explicit must write. Proactive must offer IF it activated; staying
    # silent (not activated) is acceptable selectivity, reported as SKIP.
    if expect == 'wrote':
        verdict = 'PASS' if behavior == 'wrote' else 'FAIL'
    elif not activated:
        verdict = 'SKIP'  # skill stayed silent — selective, not a regression
    else:
        verdict = 'PASS' if behavior == 'offered' else 'FAIL'
    return {
        'label': label,
        'expect': expect,
        'activated': activated,
        'behavior': behavior,
        'why': why,
        'verdict': verdict,
        'out': run.usage.get('output_tokens', 0),
        'in': _in(run.usage),
        'cost': round(run.cost_usd or 0.0, 4),
        'message': (run.result_text or '').strip(),
    }


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    plugin = str(REPO / 'plugins' / 'session-workflow')
    cfgdir = make_isolated_config()  # all arms are WITH-plugin -> one config is fine
    rows = []
    try:
        for fx in ('decision-session.md', 'reference-reading.md'):
            base = (FIX / fx).read_text(encoding='utf-8')
            short = fx.replace('.md', '')
            rows.append(arm(f'{short} | proactive', base + CLOSE, plugin, cfg, cfgdir, 'offer'))
            rows.append(arm(f'{short} | explicit', base + EXPLICIT, plugin, cfg, cfgdir, 'wrote'))
            if short == 'decision-session':  # the soft-ask regression guard
                rows.append(
                    arm(f'{short} | soft-ask', base + IMPLICIT, plugin, cfg, cfgdir, 'wrote')
                )
    finally:
        cleanup_dir(cfgdir)

    print(f'\n{"arm":32s} {"fired":5s} {"behavior":9s} {"out":>7s} {"verdict":7s}  why')
    print('-' * 94)
    for r in rows:
        print(
            f'{r["label"]:32s} {r["activated"]!s:5s} {r["behavior"]:9s} '
            f'{r["out"]:>7d} {r["verdict"]:7s}  {r["why"]}'
        )

    print('\nProactive-arm messages (the offer, verbatim, truncated):')
    for r in rows:
        if r['expect'] == 'offer':
            print(f'  [{r["label"].strip()}] {r["message"][:400] or "(empty)"}')

    fails = [r for r in rows if r['verdict'] == 'FAIL']
    print(f'\nOVERALL: {"PASS" if not fails else f"FAIL ({len(fails)} arm(s))"}')

    rpt = REPO / 'evals' / 'report'
    rpt.mkdir(parents=True, exist_ok=True)
    (rpt / 'offer_probe.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(f'wrote {rpt / "offer_probe.json"}')
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Compute the detector's frozen firing table -- offline, free, and auditable.

Firing is decomposed from effect. This generator answers "which prompts would
receive an injection under which arm, and what exactly would they receive" WITHOUT
spending a cent, and freezes the answer so review happens before the run rather
than after it.

It drives the REAL router read-only: it imports
`plugins/humblepowers/skills/choosing-tools/scripts/router.py`, calls
`load_rules(<arm rules file>)` (the path parameter that function already accepts),
`route`, and `hint_line`, and applies the dispatch hook's own pre-filter constants
and skips by importing them from `inject_dispatch.py` rather than restating them.
Importing is not editing: no humblepowers file is written, and the shipped
`router_rules.json` is out of frame entirely (a test asserts it byte-unchanged).

Fidelity therefore comes by construction rather than from a checklist an
implementer could under-copy -- the format-category strip, the 4000-character
truncation, the lowercasing, the order-preserving dedup and three-word cap on the
echoed matches, the ASCII collapse that only bites the PT-BR half, and the join
across candidates are the router's own behavior.

Per arm x per prompt the table records whether an injection fires, which candidate
ids that arm produces (so displacement would be visible rather than silent), the
injected text VERBATIM, its character count, and an estimated token count under a
declared approximation: characters / 4. A prompt too short for the hook's floor
appears as a visible no-injection row in EVERY arm -- never a silent hole.

Three arms take their text from the router itself; `inert` does not. Inert fires on
wide's rows by construction (identical patterns) and carries a per-prompt neutral
house-style text that names no experiment, no evaluation, no rigor and no tier,
length-matched to THAT prompt's wide text within 5 percent on estimated tokens. The
match is therefore a per-row property this table carries and a test checks, not a
global average.

    python firing_table.py            # regenerate firing_table.json
    python firing_table.py --check    # fail if the committed table is stale

Stdlib only. Deterministic: no clock, no randomness, no network, no model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROUTER_DIR = REPO / 'plugins' / 'humblepowers' / 'skills' / 'choosing-tools' / 'scripts'

if str(ROUTER_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTER_DIR))

import inject_dispatch  # noqa: E402 - the hook's own floor constants and skips
import router  # noqa: E402 - the real router, driven read-only

BANK_PATH = HERE / 'bank.json'
RULES_DIR = HERE / 'rules'
TABLE_PATH = HERE / 'firing_table.json'

# The arms, in the order the table lists them. `inert` is derived from `wide`, so it
# is generated last and named here in that order.
ARMS: tuple[str, ...] = ('control', 'narrow', 'wide', 'inert')
ROUTER_ARMS: tuple[str, ...] = ('control', 'narrow', 'wide')

# The declared token approximation. Stated once, recorded per row, and never
# silently swapped for a tokenizer: an estimate whose rule is written down is
# checkable by hand; a tokenizer's answer is not.
CHARS_PER_TOKEN = 4

# The wide/inert length match, as a fraction of wide's estimated token count.
TOKEN_MATCH_TOLERANCE = 0.05


# --- the hook's pre-filter, reproduced by importing it ----------------------


def hook_skip(prompt: str) -> str | None:
    """Why the dispatch hook would decline this prompt, or None if it would run.

    Reproduces `inject_dispatch._prompt_submit`'s pre-filter using that module's
    own constants (MIN_WORDS, MIN_CHARS, SYNTHETIC_PREFIXES), so a change to the
    hook's floor moves this table rather than leaving it quietly wrong.
    """
    text = prompt.strip()
    if text.startswith(inject_dispatch.SYNTHETIC_PREFIXES):
        return 'synthetic_prefix'
    if text.startswith('/'):
        return 'slash_command'
    if len(text) < inject_dispatch.MIN_CHARS or len(text.split()) < inject_dispatch.MIN_WORDS:
        return 'below_hook_floor'
    return None


# --- the inert arm's neutral text -------------------------------------------
#
# Plain house-style sentences: no experiment, no evaluation, no rigor, no tier, and
# none of the oracle's element labels (a test asserts the last part mechanically).
# The text is assembled to land as close as the pool allows to the character count
# of THAT prompt's wide text, which is what makes the length match a per-row
# property rather than an average.
#
# ORTHOGONALITY, which is this arm's whole job. Every clause is a statement about
# FILES AND SCOPE, never about how to answer. An earlier pool carried lines like
# "Reply in plain prose and keep the wording steady" and "A short answer is fine when
# it covers the ask"; read as instructions those point straight at the scored
# behavior -- the first discourages the labelled shape the oracle detects (it landed
# on 6 of the 12 genuine rows), the second licenses brevity on 4 of the 6 firing
# decoy rows, where brevity is what scores correct. Either would have biased
# wide - inert toward the content leg by SUPPRESSING inert rather than by wide adding
# anything. A confound control has to be inert about the outcome, not just about the
# topic.

_INERT_BASE = 'Session note: keep the working files where they are and name each file you open.'

_INERT_CLAUSES: tuple[str, ...] = (
    ' The working copy sits where it was left this morning.',
    ' Nothing outside the current folder is in scope today.',
    ' The folder layout stays exactly as it stands today.',
    ' Name the files you touch along the way.',
    ' The same paths as before apply.',
    ' The usual file names hold.',
    ' Paths stay as they are.',
    ' Same folder as before.',
    ' Files stay put.',
    ' As before.',
)


def inert_text(target_chars: int) -> str:
    """The neutral text whose length lands closest to `target_chars`.

    Exhaustive over the clause pool (2**10 subsets), so the result is the closest
    length the pool can reach rather than whatever a greedy pass happened to hit.
    Ties break toward fewer clauses and then toward the pool's own order, so the
    output is a pure function of the target.
    """
    n = len(_INERT_CLAUSES)
    base = len(_INERT_BASE)
    best: tuple[int, int, tuple[int, ...]] | None = None
    for mask in range(1 << n):
        picks = tuple(i for i in range(n) if mask >> i & 1)
        total = base + sum(len(_INERT_CLAUSES[i]) for i in picks)
        key = (abs(total - target_chars), len(picks), picks)
        if best is None or key < best:
            best = key
    assert best is not None  # noqa: S101 - the loop always runs (mask 0 exists)
    return _INERT_BASE + ''.join(_INERT_CLAUSES[i] for i in best[2])


# --- the table ---------------------------------------------------------------


def est_tokens(text: str) -> float:
    """The declared approximation: characters / 4, rounded to 2 dp."""
    return round(len(text) / CHARS_PER_TOKEN, 2)


def load_bank(path: str | Path = BANK_PATH) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding='utf-8'))['prompts']


def load_arm_rules(arm: str, rules_dir: str | Path = RULES_DIR) -> dict:
    """The arm's rules through the router's own loader -- the same call the hook
    makes, with the path parameter `load_rules` already accepts."""
    return router.load_rules(Path(rules_dir) / f'{arm}.json')


def router_row(arm: str, prompt: dict[str, Any], rules: dict) -> dict[str, Any]:
    """One router-derived row: the real route() candidates and the real hint_line()
    text for this prompt under this arm's rules."""
    skip = hook_skip(prompt['text'])
    if skip is not None:
        return _row(arm, prompt, skip_reason=skip)
    # The hook routes the STRIPPED prompt; reproduce that rather than the raw one. A
    # test asserts every bank prompt is already stripped, so what the runner delivers
    # and what was routed here cannot come apart.
    matches = router.route(prompt['text'].strip(), rules)
    text = router.hint_line(matches)
    return _row(
        arm,
        prompt,
        candidates=[m['id'] for m in matches],
        matched=[m['matched'] for m in matches],
        text=text,
        text_source='router.hint_line' if text else 'none',
    )


def _row(
    arm: str,
    prompt: dict[str, Any],
    *,
    skip_reason: str | None = None,
    candidates: list[str] | None = None,
    matched: list[list[str]] | None = None,
    text: str = '',
    text_source: str = 'none',
) -> dict[str, Any]:
    return {
        'arm': arm,
        'prompt_id': prompt['id'],
        'prompt_class': prompt['class'],
        'language': prompt['language'],
        'hook_skip': skip_reason,
        'fires': bool(text),
        'candidates': candidates or [],
        'matched': matched or [],
        'text': text,
        'text_source': text_source,
        'chars': len(text),
        'est_tokens': est_tokens(text),
    }


def build_rows(bank: list[dict[str, Any]], rules_by_arm: dict[str, dict]) -> list[dict[str, Any]]:
    """Every arm x prompt row, arms in ARMS order, prompts in bank order.

    `inert` is built from wide's rows: same firing decision, authored neutral text
    length-matched to wide's own text for that prompt.
    """
    rows: list[dict[str, Any]] = []
    wide_by_prompt: dict[str, dict[str, Any]] = {}
    for arm in ROUTER_ARMS:
        for prompt in bank:
            row = router_row(arm, prompt, rules_by_arm[arm])
            rows.append(row)
            if arm == 'wide':
                wide_by_prompt[prompt['id']] = row
    for prompt in bank:
        wide = wide_by_prompt[prompt['id']]
        if not wide['fires']:
            rows.append(_row('inert', prompt, skip_reason=wide['hook_skip']))
            continue
        text = inert_text(wide['chars'])
        rows.append(
            _row(
                'inert',
                prompt,
                candidates=list(wide['candidates']),
                matched=[],
                text=text,
                text_source='authored_neutral',
            )
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-arm firing counts and the EN/PT-BR firing rates the pre-registered
    language fallback is decided from. Contains no outcome data -- reading it
    before the run is a design decision, not a peek at a result."""
    out: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [r for r in rows if r['arm'] == arm]
        fired = [r for r in arm_rows if r['fires']]

        def rate(subset: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
            total = [r for r in subset if r[key] == value]
            hit = [r for r in total if r['fires']]
            return {
                'fired': len(hit),
                'rows': len(total),
                'rate': round(len(hit) / len(total), 4) if total else None,
            }

        out[arm] = {
            'rows': len(arm_rows),
            'fired': len(fired),
            'genuine': rate(arm_rows, 'prompt_class', 'genuine'),
            'decoy': rate(arm_rows, 'prompt_class', 'decoy'),
            'en': rate(arm_rows, 'language', 'en'),
            'pt': rate(arm_rows, 'language', 'pt'),
        }
    return out


def token_match(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The per-row wide-vs-inert estimated-token comparison, worst row first."""
    wide = {r['prompt_id']: r for r in rows if r['arm'] == 'wide' and r['fires']}
    inert = {r['prompt_id']: r for r in rows if r['arm'] == 'inert' and r['fires']}
    out: list[dict[str, Any]] = []
    for pid, w in wide.items():
        i = inert.get(pid)
        if i is None:
            out.append({'prompt_id': pid, 'wide_est_tokens': w['est_tokens'], 'deviation': None})
            continue
        deviation = abs(i['est_tokens'] - w['est_tokens']) / w['est_tokens']
        out.append(
            {
                'prompt_id': pid,
                'wide_est_tokens': w['est_tokens'],
                'inert_est_tokens': i['est_tokens'],
                'deviation': round(deviation, 6),
            }
        )
    return sorted(out, key=lambda d: -(d['deviation'] or 0.0))


def build_table(bank_path: str | Path = BANK_PATH, rules_dir: str | Path = RULES_DIR) -> dict:
    bank = load_bank(bank_path)
    rules_by_arm = {arm: load_arm_rules(arm, rules_dir) for arm in ARMS}
    rows = build_rows(bank, rules_by_arm)
    return {
        'generator': 'firing_table.py',
        'comment': (
            'Frozen firing table: per arm x per prompt, whether an injection fires, the '
            'candidate ids the arm produces, and the injected text VERBATIM. The paid run '
            'delivers this text; it is never regenerated at run time. Regenerate with '
            '`python firing_table.py`; `--check` fails when the committed table is stale.'
        ),
        'hook_floor': {
            'min_words': inject_dispatch.MIN_WORDS,
            'min_chars': inject_dispatch.MIN_CHARS,
            'synthetic_prefixes': list(inject_dispatch.SYNTHETIC_PREFIXES),
            'slash_command_skip': True,
            'source': 'plugins/humblepowers/skills/choosing-tools/scripts/inject_dispatch.py',
        },
        'router_source': 'plugins/humblepowers/skills/choosing-tools/scripts/router.py',
        'token_estimate': {
            'rule': 'characters / 4',
            'declared_approximation': True,
            'tolerance_wide_vs_inert': TOKEN_MATCH_TOLERANCE,
        },
        'arms': list(ARMS),
        'summary': summarize(rows),
        'wide_vs_inert': token_match(rows),
        'rows': rows,
    }


def render(table: dict) -> str:
    return json.dumps(table, indent=2, ensure_ascii=False) + '\n'


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # PT-BR prompt text
    ap = argparse.ArgumentParser(description='Generate the frozen act-hint firing table.')
    ap.add_argument('--check', action='store_true', help='fail if the committed table is stale')
    ap.add_argument('--out', default=str(TABLE_PATH), help='table path')
    args = ap.parse_args(argv)

    table = build_table()
    text = render(table)
    out = Path(args.out)
    if args.check:
        if not out.exists():
            print(f'STALE {out}: the committed firing table is missing')
            return 1
        if out.read_text(encoding='utf-8').replace('\r\n', '\n') != text:
            print(f'STALE {out}: regenerate with `python firing_table.py`')
            return 1
        print(f'OK {out}')
        return 0
    out.write_text(text, encoding='utf-8', newline='\n')
    summary = table['summary']
    print(f'wrote {out} ({len(table["rows"])} rows)')
    for arm in ARMS:
        s = summary[arm]
        print(
            f'  {arm:<8} fires {s["fired"]:>2}/{s["rows"]:<2} '
            f'genuine {s["genuine"]["fired"]}/{s["genuine"]["rows"]} '
            f'decoy {s["decoy"]["fired"]}/{s["decoy"]["rows"]} '
            f'en {s["en"]["fired"]}/{s["en"]["rows"]} pt {s["pt"]["fired"]}/{s["pt"]["rows"]}'
        )
    worst = next((d for d in table['wide_vs_inert'] if d['deviation'] is not None), None)
    if worst:
        print(
            f'  worst wide-vs-inert row: {worst["prompt_id"]} '
            f'{worst["deviation"] * 100:.2f}% (tolerance {TOKEN_MATCH_TOLERANCE * 100:.0f}%)'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Deterministic lexical dispatch router for the choosing-tools prompt hook.

Matches a user prompt against per-skill word-boundary regex rules
(router_rules.json) and names at most two candidate skills. Silence on zero
hits is the contract: no "no skills matched" noise, ever.

Honest scope: this router lives under the same lexical ceiling as native
skill-description triggering — pure-intent paraphrases will not match here
either. Its wins are determinism, offline calibration against the labeled
trigger datasets, and per-prompt presence. The generic micro-reminder tier of
inject_dispatch covers the paraphrase gap.

Stdlib only (Python 3.10+). ASCII-only output strings.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

RULES_PATH = Path(__file__).parent / 'router_rules.json'
MAX_PROMPT_CHARS = 4000


def _ascii(text: str) -> str:
    """Collapse to ASCII for output. The hook's stdout may be a codepage-limited
    console, so any prompt-derived text placed into a hint must be ASCII-safe."""
    return text.encode('ascii', 'replace').decode('ascii')


def load_rules(path: str | Path = RULES_PATH) -> dict:
    rules = json.loads(Path(path).read_text(encoding='utf-8'))
    for skill in rules['skills']:
        skill['_compiled'] = [re.compile(p) for p in skill['patterns']]
        skill['_compiled_neg'] = [re.compile(p) for p in skill.get('negative_patterns', [])]
    return rules


def route(prompt: str, rules: dict) -> list[dict]:
    """Return up to max_candidates matches: [{'id', 'matched', 'hits'}], best first."""
    # Strip zero-width / format-category chars so an invisible character cannot
    # selectively defeat a negative_pattern (e.g. a ZWSP inside "ci pipeline").
    text = ''.join(c for c in prompt[:MAX_PROMPT_CHARS] if unicodedata.category(c) != 'Cf').lower()
    matches = []
    for skill in rules['skills']:
        if any(neg.search(text) for neg in skill['_compiled_neg']):
            continue
        matched = []
        for pattern in skill['_compiled']:
            hit = pattern.search(text)
            if hit:
                matched.append(hit.group(0).strip())
        if len(matched) >= skill.get('min_hits', 1):
            matches.append({'id': skill['id'], 'matched': matched, 'hits': len(matched)})
    matches.sort(key=lambda m: -m['hits'])
    return matches[: rules.get('max_candidates', 2)]


def hint_line(matches: list[dict]) -> str:
    """Render the advisory hint for a non-empty match list ('' when empty)."""
    if not matches:
        return ''
    parts = []
    for m in matches:
        words = ', '.join(_ascii(w) for w in list(dict.fromkeys(m['matched']))[:3])
        parts.append(f'{m["id"]} (matched: {words})')
    return (
        'Prompt wording matches triggers for: '
        + '; '.join(parts)
        + ". Check fit before starting; 'nothing fits' remains a valid outcome."
    )


def _eval(trigger_dir: Path, rules: dict) -> int:
    """Print the per-skill dev-set recall/specificity table (informational)."""
    print(f'{"skill":<55} {"recall":>7} {"spec":>7}')
    for skill in rules['skills']:
        dataset = trigger_dir / (skill['id'].split(':', 1)[1] + '.json')
        if not dataset.exists():
            print(f'{skill["id"]:<55} {"n/a":>7} {"n/a":>7}')
            continue
        data = json.loads(dataset.read_text(encoding='utf-8'))
        pos = [d['query'] for d in data if d['should_trigger']]
        neg = [d['query'] for d in data if not d['should_trigger']]
        hits = sum(1 for q in pos if skill['id'] in {m['id'] for m in route(q, rules)})
        false_fires = sum(1 for q in neg if skill['id'] in {m['id'] for m in route(q, rules)})
        recall = hits / len(pos) if pos else 1.0
        spec = 1 - false_fires / len(neg) if neg else 1.0
        print(f'{skill["id"]:<55} {recall:>7.2f} {spec:>7.2f}')
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description='Dispatch lexical router (debug CLI).')
    parser.add_argument('--prompt', help='route one prompt and print matches')
    parser.add_argument(
        '--eval', metavar='TRIGGER_DIR', help='print recall/specificity vs a trigger dataset dir'
    )
    args = parser.parse_args(argv)
    rules = load_rules()
    if args.prompt:
        for m in route(args.prompt, rules):
            print(f'{m["id"]}  hits={m["hits"]}  matched={m["matched"]}')
        return 0
    if args.eval:
        return _eval(Path(args.eval), rules)
    parser.print_help()
    return 0


if __name__ == '__main__':
    import sys

    sys.exit(main())

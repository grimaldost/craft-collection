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
# scripts/ -> choosing-tools -> skills -> humblepowers -> the directory holding
# every sibling plugin. Both shipped install shapes put them there: a marketplace
# install and `--plugin-dir ./plugins/<name>` from a checkout.
_PLUGINS_DIR = Path(__file__).resolve().parents[3].parent
_USER_SKILLS = Path.home() / '.claude' / 'skills'


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


def is_installed(skill_id: str, plugins_dir: Path | None = None) -> bool:
    """True when `plugin:skill` resolves to a SKILL.md on disk. Five of the nine
    routed rows name skills in SIBLING plugins, and the hint used to emit the raw
    id with no check -- so a single-plugin install recommended skills that were
    not there, failing the pack's own degradation test. Pure stat calls: this runs
    on the prompt path and must not shell out."""
    plugin, _, skill = skill_id.partition(':')
    if not plugin or not skill:
        return False
    if plugins_dir is not None:
        # An explicit base is the ONLY place searched -- otherwise a test cannot
        # express "this skill is absent" on a machine that has it installed.
        return (plugins_dir / plugin / 'skills' / skill / 'SKILL.md').is_file()
    candidates = [
        _PLUGINS_DIR / plugin / 'skills' / skill / 'SKILL.md',
        _USER_SKILLS / skill / 'SKILL.md',
    ]
    try:
        candidates.extend(
            (Path.home() / '.claude' / 'plugins' / 'marketplaces').glob(
                f'*/plugins/{plugin}/skills/{skill}/SKILL.md'
            )
        )
    except OSError:
        pass
    return any(c.is_file() for c in candidates)


def cwd_noise_tokens(cwd: str | Path | None = None) -> tuple[str, ...]:
    """Directory names that must not be read as trigger vocabulary. A project
    called `treasury-fin-pipeline` otherwise fires the data rule on every prompt
    that names it, for the life of that project -- a permanent false-fire class,
    not a one-off. Only the whole directory name is removed, so a standalone
    'pipeline' in the same prompt still matches."""
    p = Path(cwd) if cwd else Path.cwd()
    names = [p.name, p.parent.name]
    return tuple(n.lower() for n in names if len(n) > 3)


def route(prompt: str, rules: dict, noise_tokens: tuple[str, ...] = ()) -> list[dict]:
    """Return up to max_candidates matches: [{'id', 'matched', 'hits'}], best first."""
    # Strip zero-width / format-category chars so an invisible character cannot
    # selectively defeat a negative_pattern (e.g. a ZWSP inside "ci pipeline").
    text = ''.join(c for c in prompt[:MAX_PROMPT_CHARS] if unicodedata.category(c) != 'Cf').lower()
    for token in noise_tokens:
        text = text.replace(token, ' ')
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
            matches.append(
                {
                    'id': skill['id'],
                    'matched': matched,
                    'hits': len(matched),
                    'activation_test': skill.get('activation_test', ''),
                }
            )
    matches.sort(key=lambda m: -m['hits'])
    return matches[: rules.get('max_candidates', 2)]


def hint_line(matches: list[dict]) -> str:
    """Render the advisory hint for a non-empty match list ('' when empty).

    Each candidate is rendered as its one-line ACTIVATION TEST, not as the words
    that matched. A bare lexical token is not a reason -- the matched skill's own
    description explicitly does not rest on it -- so a reader had nothing to
    decide against; a question they can answer no to is a decidable check."""
    if not matches:
        return ''
    parts = []
    for m in matches:
        test = _ascii(str(m.get('activation_test') or '')).strip()
        parts.append(f'- {m["id"]}: {test}' if test else f'- {m["id"]}')
    return (
        'Prompt wording matches triggers for these skills. Answer each test; '
        'a no is a complete answer, and "nothing fits" remains a valid outcome.\n'
        + '\n'.join(parts)
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

#!/usr/bin/env python3
"""The act-hint detector's oracle: score one response, deterministically.

A completed run is not a pass. This module reads a response's TEXT and nothing
else -- no arm label reaches it, so it cannot know which arm produced what -- and
reports the full 2x2 state:

    line      the format-(a) activation line is present, verbatim in shape
    skeleton  all five tier-0 elements are present (method, metric, results,
              conclusion, and the one-line "what this updates")

    state = both | line_only | skeleton_only | neither

The scoring is pre-registered, not chosen afterwards:

  * on a GENUINE evaluation act only `both` counts correct, so a line emitted
    without substance scores zero -- the founding RG-2x2 case reported its
    ritual declaration in nearly every run while the confirmatory outcome sat at
    0/48, and that pattern is measured here rather than rewarded;
  * on a DECOY (an execution or lookup ask) only `neither` counts correct, which
    is what prices the cheapest way to game the genuine half: declaring the
    shape on everything.

`skeleton_wellformedness` is the separate, weaker secondary: at least one
numerator-over-denominator figure is present AND every such figure in the
response is numerically consistent (numerator <= denominator, denominator >= 1).
A response can carry all five element labels and still fail it, which is the
point -- the element most often dropped is the denominator.

Language-specific patterns live beside this file in `oracle_patterns.json`, not
in literals here, so the module stays ASCII under scripts/ascii_runtime_lint.py.
Those same patterns are the primeability ban list: a test asserts no injected
text and no bank prompt matches any of them.

Stdlib only. Deterministic: no clock, no randomness, no network, no model.

    python verify.py --response out.txt --class genuine
    python verify.py --labels oracle_labels.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

HERE = Path(__file__).resolve().parent
PATTERNS_PATH = HERE / 'oracle_patterns.json'

# The five elements of the tier-0 check, in the reference's order. `updates` is the
# one-line "what this updates".
ELEMENTS: tuple[str, ...] = ('method', 'metric', 'results', 'conclusion', 'updates')

CLASSES: tuple[str, ...] = ('genuine', 'decoy')

STATES: tuple[str, ...] = ('both', 'line_only', 'skeleton_only', 'neither')

# The correct 2x2 state per prompt class. Frozen here, and frozen again in the
# record's analysis plan, before any run.
CORRECT_STATE: dict[str, str] = {'genuine': 'both', 'decoy': 'neither'}


class Patterns(NamedTuple):
    activation: re.Pattern[str]
    elements: dict[str, list[re.Pattern[str]]]
    fraction: re.Pattern[str]
    fenced_code: re.Pattern[str]


def load_patterns(path: str | Path = PATTERNS_PATH) -> Patterns:
    """Compile the oracle's patterns from JSON data. Raises on a missing element
    key: a silently absent element would make the skeleton check easier to pass,
    which is a gate degrading rather than failing."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    raw_elements = data.get('elements')
    if not isinstance(raw_elements, dict):
        raise ValueError(f'{path}: "elements" must be a mapping of element -> pattern list')
    elements: dict[str, list[re.Pattern[str]]] = {}
    for name in ELEMENTS:
        patterns = raw_elements.get(name)
        if not isinstance(patterns, list) or not patterns:
            raise ValueError(f'{path}: element {name!r} needs a non-empty pattern list')
        elements[name] = [re.compile(p, re.IGNORECASE) for p in patterns]
    extra = sorted(set(raw_elements) - set(ELEMENTS))
    if extra:
        raise ValueError(f'{path}: unknown element key(s) {extra}; the five elements are fixed')
    return Patterns(
        activation=re.compile(data['activation_line'], re.IGNORECASE | re.MULTILINE),
        elements=elements,
        fraction=re.compile(data['fraction']),
        fenced_code=re.compile(data['fenced_code'], re.DOTALL),
    )


def strip_fenced_code(text: str, pats: Patterns) -> str:
    """The response with fenced code blocks removed, one newline per block so line
    boundaries survive the removal. An unclosed fence runs to the end, which is what
    an unclosed fence means to a reader."""
    return pats.fenced_code.sub('\n', text)


def has_activation_line(text: str, pats: Patterns) -> bool:
    """True when some line of the response IS the format-(a) activation line.

    Checked explicitly and structurally: the bracketed
    `[<plugin>:experiment-rigor | <tier> -> <artifact>]` shape on a line of its own,
    with the PLUGIN PREFIX OPTIONAL -- the injected hint hands the model the
    qualified id, so both spellings must count or the scoring gap would fall on the
    treated arms only. A leading quote or emphasis marker is tolerated, trailing
    prose is not. Any tier and any artifact reference count: the outcome measures
    that the convention was emitted, not that the responder guessed the tier this
    bank's prompts sit at.

    FENCED CODE IS STRIPPED FIRST, and only here: a response that declines the shape
    and then QUOTES the convention inside a fence is showing it, not doing it, and
    counting that as a line is a false positive on the decoy half. Inline backticks
    still count -- a real response may format its own line that way.
    """
    return pats.activation.search(strip_fenced_code(text, pats)) is not None


def elements_present(text: str, pats: Patterns) -> dict[str, bool]:
    """Which of the five elements the response carries, one bool each."""
    return {name: any(p.search(text) for p in patterns) for name, patterns in pats.elements.items()}


def fractions(text: str, pats: Patterns) -> list[tuple[int, int]]:
    """Every numerator-over-denominator figure in the response, in order."""
    return [(int(m.group(1)), int(m.group(2))) for m in pats.fraction.finditer(text)]


def skeleton_wellformed(text: str, pats: Patterns) -> bool:
    """The secondary: a denominator is present AND every stated figure is
    numerically consistent with itself. One `9/3` anywhere fails the whole
    response -- an inconsistent number is worse than an absent one."""
    found = fractions(text, pats)
    if not found:
        return False
    return all(den >= 1 and 0 <= num <= den for num, den in found)


def state_of(line: bool, skeleton: bool) -> str:
    if line and skeleton:
        return 'both'
    if line:
        return 'line_only'
    if skeleton:
        return 'skeleton_only'
    return 'neither'


def score(text: str, prompt_class: str, pats: Patterns | None = None) -> dict[str, Any]:
    """Score one response. `prompt_class` is the bank's own label ('genuine' or
    'decoy'); no arm label is an input to this function, by design."""
    if prompt_class not in CLASSES:
        raise ValueError(f'prompt_class must be one of {CLASSES}, got {prompt_class!r}')
    pats = pats or load_patterns()
    present = elements_present(text, pats)
    line = has_activation_line(text, pats)
    skeleton = all(present.values())
    st = state_of(line, skeleton)
    return {
        'class': prompt_class,
        'line': line,
        'skeleton': skeleton,
        'elements': present,
        'state': st,
        'fractions': fractions(text, pats),
        'rigor_disposition': st == CORRECT_STATE[prompt_class],
        'skeleton_wellformedness': skeleton_wellformed(text, pats),
    }


# --- oracle validation against the hand-labeled set -------------------------


def check_labels(labels: list[dict[str, Any]], pats: Patterns | None = None) -> dict[str, Any]:
    """Score every hand-labeled response and report the disagreements plus the
    oracle's recall and specificity.

    The positive class is the 2x2 state `both` -- the only state that counts a
    genuine prompt correct, and therefore the call the confirmatory outcome rests
    on. Recall is over the labeled `both` items, specificity over the rest.
    """
    pats = pats or load_patterns()
    mismatches: list[str] = []
    tp = fn = tn = fp = 0
    for item in labels:
        text = item['text']
        got_line = has_activation_line(text, pats)
        present = elements_present(text, pats)
        got_skeleton = all(present.values())
        got_state = state_of(got_line, got_skeleton)
        got_well = skeleton_wellformed(text, pats)
        for field, got, want in (
            ('line', got_line, item['expected_line']),
            ('skeleton', got_skeleton, item['expected_skeleton']),
            ('state', got_state, item['expected_state']),
            ('wellformed', got_well, item['expected_wellformed']),
        ):
            if got != want:
                missing = sorted(k for k, v in present.items() if not v)
                mismatches.append(
                    f'{item["id"]}: {field} = {got!r}, label says {want!r} '
                    f'(elements missing: {missing or "none"})'
                )
        if item['expected_state'] == 'both':
            tp += 1 if got_state == 'both' else 0
            fn += 0 if got_state == 'both' else 1
        else:
            tn += 1 if got_state != 'both' else 0
            fp += 0 if got_state != 'both' else 1
    return {
        'n': len(labels),
        'mismatches': mismatches,
        'recall_numerator': tp,
        'recall_denominator': tp + fn,
        'recall': (tp / (tp + fn)) if (tp + fn) else None,
        'specificity_numerator': tn,
        'specificity_denominator': tn + fp,
        'specificity': (tn / (tn + fp)) if (tn + fp) else None,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='The act-hint detector oracle (deterministic).')
    ap.add_argument('--response', help='path to a response text file to score')
    ap.add_argument('--class', dest='prompt_class', choices=list(CLASSES), help='the bank class')
    ap.add_argument('--labels', help='path to oracle_labels.json; report recall and specificity')
    ap.add_argument('--patterns', default=str(PATTERNS_PATH), help='override the pattern file')
    args = ap.parse_args(argv)

    pats = load_patterns(args.patterns)
    if args.labels:
        data = json.loads(Path(args.labels).read_text(encoding='utf-8'))
        summary = check_labels(data['labels'], pats)
        for line in summary['mismatches']:
            print(f'MISMATCH {line}')
        print(
            f'oracle vs {summary["n"]} hand-labeled response(s): '
            f'recall {summary["recall_numerator"]}/{summary["recall_denominator"]}, '
            f'specificity {summary["specificity_numerator"]}/{summary["specificity_denominator"]}'
        )
        return 1 if summary['mismatches'] else 0

    if not args.response or not args.prompt_class:
        ap.error('--response and --class are required unless --labels is given')
    text = Path(args.response).read_text(encoding='utf-8')
    json.dump(score(text, args.prompt_class, pats), sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""The oracle must reproduce every hand label before it scores anything paid.

`verify.py` is the only scorer in this design -- there is no LLM judge -- so the
confirmatory outcome means exactly what these patterns mean. That makes the
hand-labeled set the gate: twelve synthetic responses spanning both languages and
all four 2x2 states, each pinning four independent calls (the activation line, the
five-element skeleton, the resulting state, and wellformedness), so a pattern edit
that quietly loosens one of them reddens here rather than changing what the record's
confirmatory number means.

The set's recall and specificity are recomputed here and checked against the numbers
the record states, so the record cannot claim a validation it did not get.

Runnable with pytest or `python test_oracle.py`. Stdlib only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import verify  # noqa: E402 - after the path fix

LABELS = json.loads((HERE / 'oracle_labels.json').read_text(encoding='utf-8'))
PATS = verify.load_patterns()


def test_the_labeled_set_spans_both_languages_and_all_four_states():
    items = LABELS['labels']
    assert len(items) >= 12, len(items)
    assert {i['language'] for i in items} == {'en', 'pt'}
    assert {i['expected_state'] for i in items} == set(verify.STATES)
    for state in verify.STATES:
        same = [i for i in items if i['expected_state'] == state]
        assert len(same) >= 2, (state, len(same))
        assert {i['language'] for i in same} == {'en', 'pt'} or len(same) >= 3, state
    assert len({i['id'] for i in items}) == len(items), 'duplicate label id'


def test_the_oracle_reproduces_every_label():
    summary = verify.check_labels(LABELS['labels'], PATS)
    assert not summary['mismatches'], summary['mismatches']


def test_recall_and_specificity_are_perfect_on_the_set():
    """The record quotes these numbers; test_record_shape.py checks the record against
    this same recomputation, so the prose and the numbers cannot drift apart."""
    summary = verify.check_labels(LABELS['labels'], PATS)
    assert summary['recall'] == 1.0, summary
    assert summary['specificity'] == 1.0, summary
    assert summary['recall_denominator'] >= 3, summary
    assert summary['specificity_denominator'] >= 9, summary


def test_the_review_defects_stay_fixed():
    """One assertion per defect found at review, so a pattern edit that reopens any of
    them reddens by name rather than as an arithmetic shift somewhere downstream."""
    # the injection hands the model the PLUGIN-QUALIFIED id; both spellings must count,
    # or the scoring gap falls on the treated arms only
    assert verify.has_activation_line('[experiment-rigor | check -> inline]', PATS)
    assert verify.has_activation_line(
        '[experiment-discipline:experiment-rigor | check -> inline]', PATS
    )
    # quoting the convention inside a fence is showing it, not emitting it
    fenced = 'Not using the shape. It looks like:\n```\n[experiment-rigor | check -> inline]\n```\n'
    assert not verify.has_activation_line(fenced, PATS)
    assert verify.has_activation_line('`[experiment-rigor | check -> inline]`', PATS)
    # a sentence-final figure counts, a decimal does not, and a date is not a rate
    assert verify.fractions('prompt B 35/40.', PATS) == [(35, 40)]
    assert verify.fractions('we saw 9/3.', PATS) == [(9, 3)]
    assert verify.fractions('ratio 3/4.5 here', PATS) == []
    assert verify.fractions('1.5/3 of it', PATS) == []
    assert verify.fractions('on 2026/07/25 we ran it', PATS) == []
    assert verify.skeleton_wellformed('A 31/40, B 45/40.', PATS) is False
    assert verify.skeleton_wellformed('on 2026/07/25 we ran it', PATS) is False


def test_scoring_is_pre_registered_per_class():
    """A genuine prompt is correct only on `both`; a decoy only on `neither`."""
    assert verify.CORRECT_STATE == {'genuine': 'both', 'decoy': 'neither'}
    line_only = next(i for i in LABELS['labels'] if i['expected_state'] == 'line_only')
    scored = verify.score(line_only['text'], 'genuine', PATS)
    assert scored['rigor_disposition'] is False, 'a line without substance must score zero'
    neither = next(i for i in LABELS['labels'] if i['expected_state'] == 'neither')
    assert verify.score(neither['text'], 'decoy', PATS)['rigor_disposition'] is True
    assert verify.score(neither['text'], 'genuine', PATS)['rigor_disposition'] is False


def test_wellformedness_is_independent_of_the_skeleton():
    """The secondary asks a different question and must be able to disagree."""
    both_ways = {(i['expected_skeleton'], i['expected_wellformed']) for i in LABELS['labels']}
    assert (True, False) in both_ways, 'need a five-element response with a bad denominator'
    assert (False, True) in both_ways, 'need a shapeless response that still carries one'
    assert verify.skeleton_wellformed('we got 9/3 of them', PATS) is False
    assert verify.skeleton_wellformed('we got 3/9 of them', PATS) is True
    assert verify.skeleton_wellformed('we got most of them', PATS) is False


def test_the_oracle_takes_no_arm_label():
    """Blinding, asserted rather than asserted-about: `score` accepts the response and
    the bank's own class, and refuses anything else as a class."""
    assert verify.score.__code__.co_varnames[: verify.score.__code__.co_argcount] == (
        'text',
        'prompt_class',
        'pats',
    )
    for bad in ('control', 'narrow', 'wide', 'inert', ''):
        try:
            verify.score('x', bad, PATS)
        except ValueError:
            continue
        raise AssertionError(f'score accepted {bad!r} as a prompt class')


def test_pattern_data_is_complete():
    """A silently missing element key would make the skeleton easier to pass."""
    assert set(PATS.elements) == set(verify.ELEMENTS)
    for name, patterns in PATS.elements.items():
        assert patterns, name


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
            except Exception as exc:  # report any failure; never emit the ok: sentinel
                failed += 1
                print(f'FAIL {name}: {exc!r}')
    if failed:
        print(f'{failed} test(s) failed')
        sys.exit(1)
    summary = verify.check_labels(LABELS['labels'], PATS)
    print(
        f'ok: the oracle reproduces all {summary["n"]} hand labels '
        f'(recall {summary["recall_numerator"]}/{summary["recall_denominator"]}, '
        f'specificity {summary["specificity_numerator"]}/{summary["specificity_denominator"]})'
    )

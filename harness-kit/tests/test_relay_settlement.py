#!/usr/bin/env python3
"""Checks of the relay's settlement of one answer, `relay.settlement(usage, model, reserved)`.

Contract under test:
- a valid amount is a finite, non-negative int or float, not a bool, whose conversion to float
  does not overflow; a token count whose priced term (the count times the model's price per
  million tokens) is not a finite float counts as absent; `cost_details` counts as absent unless
  it is a JSON object;
- an answer whose `usage.is_byok` is the JSON boolean true and whose
  `cost_details.upstream_inference_cost` is a valid amount settles at that cost plus the fee
  (`usage.cost` when it is a valid amount, else 0), source `reported`, with no priced floor and
  no cap at the reservation;
- failing that, such an answer whose `upstream_inference_prompt_cost` and
  `upstream_inference_completions_cost` are both valid amounts settles at the fee plus the two;
- every other answer, and one whose sum above is not finite, settles by the earlier rule: the
  larger of the reported cost and the priced usage, else the reservation, its result unchanged
  wherever that rule did not raise; a non-BYOK answer's upstream cost is never added to its cost;
- no input makes `settlement` raise, every amount is a finite float and every source is one of
  `reported`, `priced` and `reservation`.

Nothing here starts a process or opens a socket.

Stdlib-runnable: `python test_relay_settlement.py`.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import daily, relay
from kit_fixtures import run_module

# The prices below are an example: 1000 prompt and 100 completion tokens price at 0.003 USD.
MODEL = daily.Model(
    id='anthropic/claude-sonnet-5.5',
    input_usd_per_mtok=2.0,
    output_usd_per_mtok=10.0,
    max_output_tokens=1000,
)
# The model of the relay's own tests, whose prices are 2.0 and 8.0.
VENDOR = daily.Model(
    id='vendor/model-a', input_usd_per_mtok=2.0, output_usd_per_mtok=8.0, max_output_tokens=1000
)
RESERVED = 0.02
TOKENS = {'prompt_tokens': 1000, 'completion_tokens': 100}
PRICED = 0.003
SOURCES = ('reported', 'priced', 'reservation')
HUGE = 10**400


def byok(cost: object = 0, **details: object) -> dict:
    """A BYOK usage with the example tokens, `cost` and these `cost_details`."""
    return {**TOKENS, 'cost': cost, 'is_byok': True, 'cost_details': details}


def settle(usage: object, model: daily.Model = MODEL, reserved: object = RESERVED):
    amount, source = relay.settlement(usage, model, reserved)
    assert type(amount) is float and math.isfinite(amount), (usage, amount)
    assert source in SOURCES, (usage, source)
    return amount, source


def check(usage: object, want: float, source: str, **over: object) -> None:
    amount, got = settle(usage, **over)
    assert got == source, (usage, amount, got, source)
    assert math.isclose(amount, want, rel_tol=1e-12, abs_tol=1e-18), (usage, amount, want)


def test_a_byok_answer_settles_at_its_upstream_cost_below_and_above_the_priced_usage():
    check(byok(upstream_inference_cost=0.0005), 0.0005, 'reported')
    check(byok(upstream_inference_cost=0.0036), 0.0036, 'reported')


def test_a_byok_answer_adds_its_fee():
    check(byok(0.0001, upstream_inference_cost=0.0005), 0.0006, 'reported')


def test_a_byok_amount_is_not_capped_at_the_reservation():
    check(byok(upstream_inference_cost=0.05), 0.05, 'reported', reserved=0.02)
    check({'is_byok': True, 'cost_details': {'upstream_inference_cost': 0.05}}, 0.05, 'reported')


def test_a_byok_answer_settles_at_its_split_upstream_costs_when_the_total_is_unread():
    split = {
        'upstream_inference_prompt_cost': 0.0002,
        'upstream_inference_completions_cost': 0.0003,
    }
    check(byok(upstream_inference_cost=None, **split), 0.0005, 'reported')
    check(byok(**split), 0.0005, 'reported')
    above = {'upstream_inference_prompt_cost': 0.002, 'upstream_inference_completions_cost': 0.0025}
    check(byok(0.0001, **above), 0.0046, 'reported')


def test_a_byok_flag_other_than_the_json_true_is_not_byok():
    for flag in (1, 'true', 1.0, 'True', [True], None, False):
        usage = {**byok(upstream_inference_cost=0.0005), 'is_byok': flag}
        check(usage, PRICED, 'priced')


def test_cost_details_that_are_not_an_object_count_as_absent():
    for details in (..., None, [], [{'upstream_inference_cost': 0.0005}], 'x', 0.0005, True):
        usage = {**TOKENS, 'cost': 0, 'is_byok': True}
        if details is not ...:
            usage['cost_details'] = details
        check(usage, PRICED, 'priced')


def test_only_one_valid_split_cost_falls_to_the_earlier_rule():
    for bad in (None, 'x', -0.1, True, float('nan'), HUGE):
        check(
            byok(upstream_inference_prompt_cost=0.0002, upstream_inference_completions_cost=bad),
            PRICED,
            'priced',
        )
        check(
            byok(upstream_inference_prompt_cost=bad, upstream_inference_completions_cost=0.0003),
            PRICED,
            'priced',
        )


def test_an_invalid_upstream_cost_falls_to_the_split_costs_or_the_earlier_rule():
    split = {
        'upstream_inference_prompt_cost': 0.0002,
        'upstream_inference_completions_cost': 0.0003,
    }
    for bad in (True, False, -0.0005, float('nan'), float('inf'), '0.0005', HUGE):
        check(byok(upstream_inference_cost=bad, **split), 0.0005, 'reported')
        check(byok(upstream_inference_cost=bad), PRICED, 'priced')


def test_an_invalid_cost_under_byok_is_a_fee_of_zero():
    for bad in (-0.0001, float('nan'), float('inf'), True, '0.0001', None, HUGE, {}):
        check(byok(bad, upstream_inference_cost=0.0005), 0.0005, 'reported')
    usage = byok(upstream_inference_cost=0.0005)
    del usage['cost']
    check(usage, 0.0005, 'reported')


def test_a_non_byok_upstream_cost_is_never_added_to_the_cost():
    for flag in (False, ...):
        usage = {**TOKENS, 'cost': 0.002, 'cost_details': {'upstream_inference_cost': 0.002}}
        if flag is not ...:
            usage['is_byok'] = flag
        check(usage, PRICED, 'priced')
        usage['cost'] = usage['cost_details']['upstream_inference_cost'] = 0.004
        check(usage, 0.004, 'reported')


def test_a_huge_amount_or_token_count_counts_as_absent():
    check({**TOKENS, 'cost': HUGE}, PRICED, 'priced')
    check({'cost': HUGE}, RESERVED, 'reservation')
    check(byok(HUGE, upstream_inference_cost=0.0005), 0.0005, 'reported')
    check(byok(upstream_inference_cost=HUGE), PRICED, 'priced')
    check({'prompt_tokens': HUGE, 'completion_tokens': 100}, 0.001, 'priced')
    check({'prompt_tokens': HUGE}, RESERVED, 'reservation')
    check({'prompt_tokens': HUGE, 'cost': 0.0001}, 0.0001, 'reported')
    check({'prompt_tokens': 1000, 'completion_tokens': HUGE}, 0.002, 'priced')


def test_a_token_count_whose_priced_term_overflows_counts_as_absent():
    for price in (2.0, 2):
        model = daily.Model(
            id=MODEL.id, input_usd_per_mtok=price, output_usd_per_mtok=10.0, max_output_tokens=1
        )
        big = 10**308
        check({'prompt_tokens': big, 'completion_tokens': 100}, 0.001, 'priced', model=model)
        check({'prompt_tokens': big}, RESERVED, 'reservation', model=model)
        check({'prompt_tokens': big, 'cost': 0.0001}, 0.0001, 'reported', model=model)


def test_a_byok_sum_that_is_not_finite_falls_to_the_earlier_rule():
    check(byok(1e308, upstream_inference_cost=1e308), 1e308, 'reported')
    huge = {'upstream_inference_prompt_cost': 1e308, 'upstream_inference_completions_cost': 1e308}
    check(byok(**huge), PRICED, 'priced')


def test_the_earlier_rows_keep_their_results():
    reserved = 0.0081
    rows = (
        ({'prompt_tokens': 100, 'completion_tokens': 50, 'cost': 0.5}, 'reported', 0.5),
        ({'cost': 0.25}, 'reported', 0.25),
        ({'prompt_tokens': 1000, 'completion_tokens': 0}, 'priced', 0.002),
        ({'prompt_tokens': 1000}, 'priced', 0.002),
        ({'prompt_tokens': 'n/a', 'completion_tokens': 250, 'cost': 0.001}, 'priced', 0.002),
        ({}, 'reservation', reserved),
        (None, 'reservation', reserved),
    )
    for usage, source, usd in rows:
        check(usage, usd, source, model=VENDOR, reserved=reserved)


def test_a_reservation_given_as_an_integer_settles_as_a_float():
    check({}, 1.0, 'reservation', reserved=1)


def test_no_usage_makes_settlement_raise():
    odd = (None, True, 1, -1, 1.5, float('nan'), 'x', b'x', [], [1], {}, set(), HUGE, -HUGE)
    for value in odd:
        settle(value)
        for key in ('cost', 'prompt_tokens', 'completion_tokens', 'is_byok', 'cost_details'):
            settle({**TOKENS, 'cost': 0.001, key: value})
            settle({**byok(upstream_inference_cost=0.0005), key: value})
        for key in (
            'upstream_inference_cost',
            'upstream_inference_prompt_cost',
            'upstream_inference_completions_cost',
        ):
            settle(byok(**{key: value}))
            settle({**TOKENS, 'cost': 0.001, 'cost_details': {key: value}})


if __name__ == '__main__':
    run_module(globals(), 'the settlement of one answer')

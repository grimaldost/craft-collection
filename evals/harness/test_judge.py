"""Tests for judge pure logic. Runnable with pytest or `python test_judge.py`."""

from __future__ import annotations

from claude_runner import AgentRun
from judge import (aggregate_pointwise, decide_pairwise, extract_verdict,
                   judge_pairwise, score_from_criteria)


def test_extracts_fenced_json():
    txt = 'Here is my assessment:\n```json\n{"score":0.8,"pass":true,"reason":"ok"}\n```\n'
    v = extract_verdict(txt)
    assert v['score'] == 0.8 and v['pass'] is True


def test_extracts_bare_json_object():
    v = extract_verdict('prose {"score": 0.4, "pass": false, "reason": "x"} more')
    assert v['pass'] is False


def test_returns_none_on_no_json():
    assert extract_verdict('no json here') is None


def test_score_from_criteria_uses_weights():
    rubric = [{'id': 'a', 'weight': 2}, {'id': 'b', 'weight': 1}, {'id': 'c', 'weight': 1}]
    verdict = {'criteria': [{'id': 'a', 'met': True}, {'id': 'b', 'met': False},
                            {'id': 'c', 'met': True}]}
    out = score_from_criteria(verdict, rubric, threshold=0.7)
    assert abs(out['score'] - 0.75) < 1e-9  # (2+1)/4
    assert out['pass'] is True


def test_aggregate_pointwise_majority_and_agreement():
    verdicts = [{'score': 0.8, 'pass': True}, {'score': 0.9, 'pass': True},
                {'score': 0.2, 'pass': False}]
    agg = aggregate_pointwise(verdicts)
    assert agg['pass'] is True
    assert abs(agg['score'] - 0.6333) < 0.01
    assert abs(agg['agreement'] - 0.6667) < 0.01


def test_aggregate_pointwise_empty():
    agg = aggregate_pointwise([])
    assert agg['pass'] is False and agg['n'] == 0


def test_decide_pairwise_requires_order_agreement():
    assert decide_pairwise('A', 'A')['winner'] == 'A'   # both orders pick A
    assert decide_pairwise('B', 'B')['winner'] == 'B'
    assert decide_pairwise('A', 'B')['winner'] == 'tie'  # position disagreement
    assert decide_pairwise('A', 'tie')['winner'] == 'tie'


def test_judge_pairwise_maps_positions_and_agrees():
    # Fake judge ALWAYS prefers whichever response is the WITH-skill output (A),
    # regardless of position -> both orders should name A -> winner A.
    def fake_runner(prompt, **kw):
        first_block = prompt.split('--- RESPONSE 1 ---')[1].split('--- RESPONSE 2 ---')[0]
        winner = 'first' if 'WITH-OUTPUT' in first_block else 'second'
        return AgentRun(result_text=f'{{"winner":"{winner}","reason":"x"}}')

    d = judge_pairwise('task', 'WITH-OUTPUT', 'without-output', 'better?',
                       model='m', runner=fake_runner)
    assert d['winner'] == 'A' and d['order1'] == 'A' and d['order2'] == 'A'


def test_judge_pairwise_position_biased_judge_yields_tie():
    # Fake judge ALWAYS picks "first" no matter what -> orders disagree -> tie.
    def fake_runner(prompt, **kw):
        return AgentRun(result_text='{"winner":"first"}')

    d = judge_pairwise('task', 'A-out', 'B-out', 'better?', model='m', runner=fake_runner)
    assert d['winner'] == 'tie'


if __name__ == '__main__':
    test_extracts_fenced_json()
    test_extracts_bare_json_object()
    test_returns_none_on_no_json()
    test_score_from_criteria_uses_weights()
    test_aggregate_pointwise_majority_and_agreement()
    test_aggregate_pointwise_empty()
    test_decide_pairwise_requires_order_agreement()
    test_judge_pairwise_maps_positions_and_agrees()
    test_judge_pairwise_position_biased_judge_yields_tie()
    print('ok: all judge tests passed')

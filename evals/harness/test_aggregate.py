"""Tests for aggregate.build_scorecard (pure merge). Runnable with pytest or
`python test_aggregate.py`."""

from __future__ import annotations

from aggregate import build_scorecard, render_scorecard

GATES = {'trigger_recall': 0.8, 'trigger_specificity': 0.9, 'correct_usage': 0.7}
TRIG = {
    'journaling-sessions': {
        'recall': 0.75,
        'recall_ci': [0.47, 0.91],
        'specificity': 1.0,
        'specificity_ci': [0.76, 1.0],
        'per_query': [
            {'query': 'record this', 'should_trigger': True, 'k': 0, 'repeats': 3, 'rate': 0.0}
        ],
    }
}
GRAD = {
    'journaling-sessions': {
        'summary': {
            'correct_usage_rate': 0.8,
            'correct_usage_ci': [0.5, 0.94],
            'mean_agreement': 1.0,
            'with_win_rate': 0.6,
            'without_win_rate': 0.1,
            'tie_rate': 0.3,
            'with_activation_rate': 1.0,
        },
        'tasks': [
            {
                'task_id': 'journal-explicit',
                'with_pass_rate': 0.8,
                'with_activation_rate': 1.0,
                'pairwise': {'with_wins': 2, 'without_wins': 0, 'ties': 1},
            }
        ],
    }
}


def test_build_scorecard_rows():
    rows = build_scorecard(TRIG, GRAD, GATES)
    r = rows[0]
    assert r['recall'] == 0.75 and r['recall_ci'] == [0.47, 0.91]
    assert r['recall_gate'] == 'FAIL'  # 0.75 < 0.8
    assert r['specificity_gate'] == 'PASS'  # 1.0 >= 0.9
    assert r['correct_usage'] == 0.8 and r['correct_usage_gate'] == 'PASS'
    assert r['judge_agreement'] == 1.0
    assert r['with_win_rate'] == 0.6 and r['without_win_rate'] == 0.1


def test_build_scorecard_handles_missing_grading():
    rows = build_scorecard({'a': {'recall': 1.0, 'specificity': 1.0}}, {}, GATES)
    assert rows[0]['correct_usage'] is None
    assert rows[0]['correct_usage_gate'] == 'n/a'


def test_command_first_skill_recall_is_informational():
    # A command-first skill below the recall gate is reported, not failed.
    rows = build_scorecard(TRIG, GRAD, GATES, command_first=['journaling-sessions'])
    assert rows[0]['recall'] == 0.75  # still reported
    assert rows[0]['recall_gate'] == 'info'  # not 'FAIL', though 0.75 < 0.8


def test_render_includes_misses_and_tables():
    md = render_scorecard(build_scorecard(TRIG, GRAD, GATES), TRIG, GRAD)
    assert 'Skill eval scorecard' in md
    assert 'MISSED positive' in md and 'record this' in md  # the trigger miss surfaces
    assert 'journal-explicit' in md  # per-task row present


def test_action_discipline_recall_info_and_task_arm_gate():
    # An action-discipline skill: trigger-arm recall is informational; the
    # grading-arm activation rate is surfaced and gated as the recall proxy.
    rows = build_scorecard(TRIG, GRAD, GATES, action_disciplines=['journaling-sessions'])
    r = rows[0]
    assert r['recall'] == 0.75  # still reported
    assert r['recall_gate'] == 'info'
    assert r['task_arm_recall'] == 1.0  # == grading summary with_activation_rate
    assert r['task_arm_recall_gate'] == 'PASS'  # gated on trigger_recall threshold


def test_action_discipline_without_grading_is_na():
    rows = build_scorecard(
        {'a': {'recall': 0.0, 'specificity': 1.0}}, {}, GATES, action_disciplines=['a']
    )
    assert rows[0]['recall_gate'] == 'info'
    assert rows[0]['task_arm_recall'] is None
    assert rows[0]['task_arm_recall_gate'] == 'n/a'


def test_non_action_rows_have_no_task_arm_gate():
    rows = build_scorecard(TRIG, GRAD, GATES)
    assert rows[0]['task_arm_recall'] is None
    assert rows[0]['task_arm_recall_gate'] is None


def test_render_marks_action_discipline_activation():
    rows = build_scorecard(TRIG, GRAD, GATES, action_disciplines=['journaling-sessions'])
    md = render_scorecard(rows, TRIG, GRAD)
    assert '1.00 (PASS)' in md  # activation cell carries the task-arm gate
    assert 'action-discipline' in md  # legend explains the marker


def test_render_marks_expected_hard_miss_not_as_failure():
    # An expected-hard positive that fires 0/3 is surfaced but labelled as
    # reported-not-gated, NOT counted as a "MISSED positive" gate failure.
    trig = {
        's': {
            'recall': 1.0,
            'recall_ci': [0.4, 1.0],
            'recall_hard': 0.0,
            'specificity': 1.0,
            'specificity_ci': [0.4, 1.0],
            'per_query': [
                {
                    'query': 'immovable imperative',
                    'should_trigger': True,
                    'expected_hard': True,
                    'k': 0,
                    'repeats': 3,
                    'rate': 0.0,
                }
            ],
        }
    }
    md = render_scorecard(build_scorecard(trig, {}, GATES), trig, {})
    assert 'expected-hard' in md
    assert 'MISSED positive' not in md  # the hard miss is not a gate failure


if __name__ == '__main__':
    test_build_scorecard_rows()
    test_build_scorecard_handles_missing_grading()
    test_command_first_skill_recall_is_informational()
    test_render_includes_misses_and_tables()
    test_action_discipline_recall_info_and_task_arm_gate()
    test_action_discipline_without_grading_is_na()
    test_non_action_rows_have_no_task_arm_gate()
    test_render_marks_action_discipline_activation()
    test_render_marks_expected_hard_miss_not_as_failure()
    print('ok: all aggregate tests passed')

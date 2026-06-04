"""Tests for grade_tasks.grade_skill orchestration with injected fakes (no real
agents). Runnable with pytest or `python test_grade_tasks.py`."""

from __future__ import annotations

from claude_runner import AgentRun
from grade_tasks import grade_skill

CFG = {'agent_repeats': 3, 'judge_repeats': 1, 'agent_model': 'm', 'judge_model': 'm',
       'allowed_tools_task': 'Skill,Read', 'max_turns': 8, 'max_budget_usd': 0.5,
       'timeout_seconds': 300}


def fake_arm(prompt, *, plugin_dir, cfg, config_dir):
    with_arm = plugin_dir is not None
    run = AgentRun(
        activated_skills={'session-workflow:journaling-sessions'} if with_arm else set(),
        result_text='WITH out' if with_arm else 'WITHOUT out',
        cost_usd=0.02 if with_arm else 0.01)
    return run, run.result_text


def fake_point(task, output, rubric, *, model, repeats):
    return {'pass': True, 'score': 0.85, 'agreement': 1.0, 'n': repeats, 'verdicts': []}


def fake_pair(task, a, b, criterion, *, model):
    return {'winner': 'A', 'order1': 'A', 'order2': 'A', 'agreement': True}


def test_grade_skill_shape_over_repeats():
    tasks = [{'id': 't1', 'prompt': 'do x', 'fixture': None}]
    rubric = [{'id': 'r1', 'weight': 1, 'text': '...'}]
    blob = grade_skill('journaling-sessions', tasks, rubric, CFG, plugin_dir='p',
                       config_with=None, config_without=None,
                       pairwise_criterion='better?', concurrency=1,
                       run_arm=fake_arm, judge_point=fake_point, judge_pair=fake_pair)
    task = blob['tasks'][0]
    assert task['n'] == 3                       # one record per agent-repeat
    assert task['with_pass_rate'] == 1.0
    assert task['pairwise']['with_wins'] == 3   # fake judge always picks WITH (A)
    rec = task['records'][0]
    assert 'with_pass' in rec and 'pairwise_winner' in rec
    assert rec['with_cost'] == 0.02 and rec['without_cost'] == 0.01  # per-arm cost
    s = blob['summary']
    assert s['n_records'] == 3 and s['with_win_rate'] == 1.0
    assert s['with_activation_rate'] == 1.0     # WITH arm always "fired"


def test_grade_skill_counts_without_wins_and_ties():
    tasks = [{'id': 't1', 'prompt': 'p', 'fixture': None}]
    rubric = [{'id': 'r1', 'weight': 1, 'text': '...'}]

    def mixed_pair(task, a, b, criterion, *, model):
        mixed_pair.calls += 1
        return {'winner': ['A', 'B', 'tie'][mixed_pair.calls % 3]}
    mixed_pair.calls = 0

    blob = grade_skill('context-handoff', tasks, rubric, CFG, plugin_dir='p',
                       config_with=None, config_without=None,
                       pairwise_criterion='c', concurrency=1,
                       run_arm=fake_arm, judge_point=fake_point, judge_pair=mixed_pair)
    pw = blob['tasks'][0]['pairwise']
    assert pw['with_wins'] + pw['without_wins'] + pw['ties'] == 3


if __name__ == '__main__':
    test_grade_skill_shape_over_repeats()
    test_grade_skill_counts_without_wins_and_ties()
    print('ok: all grade_tasks tests passed')

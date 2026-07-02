"""Tests for grade_tasks.grade_skill orchestration with injected fakes (no real
agents). Runnable with pytest or `python test_grade_tasks.py`."""

from __future__ import annotations

from claude_runner import AgentRun
from grade_tasks import grade_skill, resolve_plugin_dir, resolve_task_rubric

CFG = {
    'agent_repeats': 3,
    'judge_repeats': 1,
    'agent_model': 'm',
    'judge_model': 'm',
    'allowed_tools_task': 'Skill,Read',
    'max_turns': 8,
    'max_budget_usd': 0.5,
    'timeout_seconds': 300,
}


def fake_arm(prompt, *, plugin_dir, cfg, config_dir):
    with_arm = plugin_dir is not None
    run = AgentRun(
        activated_skills={'session-workflow:journaling-sessions'} if with_arm else set(),
        result_text='WITH out' if with_arm else 'WITHOUT out',
        cost_usd=0.02 if with_arm else 0.01,
    )
    return run, run.result_text


def fake_point(task, output, rubric, *, model, repeats, config_dir=None):
    return {'pass': True, 'score': 0.85, 'agreement': 1.0, 'n': repeats, 'verdicts': []}


def fake_pair(task, a, b, criterion, *, model, config_dir=None):
    return {'winner': 'A', 'order1': 'A', 'order2': 'A', 'agreement': True}


def test_grade_skill_shape_over_repeats():
    tasks = [{'id': 't1', 'prompt': 'do x', 'fixture': None}]
    rubric = [{'id': 'r1', 'weight': 1, 'text': '...'}]
    blob = grade_skill(
        'journaling-sessions',
        tasks,
        rubric,
        CFG,
        plugin_dir='p',
        config_with=None,
        config_without=None,
        pairwise_criterion='better?',
        concurrency=1,
        run_arm=fake_arm,
        judge_point=fake_point,
        judge_pair=fake_pair,
    )
    task = blob['tasks'][0]
    assert task['n'] == 3  # one record per agent-repeat
    assert task['with_pass_rate'] == 1.0
    assert task['pairwise']['with_wins'] == 3  # fake judge always picks WITH (A)
    rec = task['records'][0]
    assert 'with_pass' in rec and 'pairwise_winner' in rec
    assert rec['with_cost'] == 0.02 and rec['without_cost'] == 0.01  # per-arm cost
    s = blob['summary']
    assert s['n_records'] == 3 and s['with_win_rate'] == 1.0
    assert s['with_activation_rate'] == 1.0  # WITH arm always "fired"


def test_grade_skill_counts_without_wins_and_ties():
    tasks = [{'id': 't1', 'prompt': 'p', 'fixture': None}]
    rubric = [{'id': 'r1', 'weight': 1, 'text': '...'}]

    def mixed_pair(task, a, b, criterion, *, model, config_dir=None):
        mixed_pair.calls += 1
        return {'winner': ['A', 'B', 'tie'][mixed_pair.calls % 3]}

    mixed_pair.calls = 0

    blob = grade_skill(
        'context-handoff',
        tasks,
        rubric,
        CFG,
        plugin_dir='p',
        config_with=None,
        config_without=None,
        pairwise_criterion='c',
        concurrency=1,
        run_arm=fake_arm,
        judge_point=fake_point,
        judge_pair=mixed_pair,
    )
    pw = blob['tasks'][0]['pairwise']
    assert pw['with_wins'] + pw['without_wins'] + pw['ties'] == 3


def test_resolve_task_rubric_inline_wins():
    default = [{'id': 'd', 'weight': 1, 'text': 'shared'}]
    task = {'id': 't1', 'rubric': [{'id': 'x', 'weight': 2, 'text': 'task-specific'}]}
    out = resolve_task_rubric('any-skill', task, default)
    assert out[0]['id'] == 'x'  # the task's own rubric, not the shared one


def test_resolve_task_rubric_falls_back_to_default():
    default = [{'id': 'd', 'weight': 1, 'text': 'shared'}]
    # No inline rubric and no rubric.<id>.json on disk -> the shared rubric (back-compat).
    assert resolve_task_rubric('any-skill', {'id': 'no-such-task-xyz'}, default) == default


def test_resolve_plugin_dir_default_and_override():
    cfg = {'plugin_of_skill': {'test-driven-development': 'humblepowers'}}
    default = resolve_plugin_dir(cfg, 'test-driven-development', None)
    assert default.endswith('humblepowers'), default  # repo plugins/<plugin>
    # An ablation arm points the WITH arm at a different plugin shipping a
    # same-named skill (e.g. the superpowers cache); the override wins verbatim.
    override = resolve_plugin_dir(cfg, 'test-driven-development', r'C:\cache\superpowers\5.1.0')
    assert override == r'C:\cache\superpowers\5.1.0'


def test_errored_with_arm_excluded_from_scoring():
    # A WITH arm that errored produced no output; grading it would score a spurious 0
    # (a discipline "failure" that is really an infra failure). It must be excluded
    # from correct_usage, and an all-errored run leaves nothing valid to score.
    def erroring_arm(prompt, *, plugin_dir, cfg, config_dir):
        is_err = plugin_dir is not None  # WITH arm errors; WITHOUT arm is fine
        run = AgentRun(activated_skills=set(), result_text='', is_error=is_err, cost_usd=0.0)
        return run, ''

    tasks = [{'id': 't1', 'prompt': 'p', 'fixture': None}]
    rubric = [{'id': 'r1', 'weight': 1, 'text': '...'}]
    blob = grade_skill(
        'journaling-sessions',
        tasks,
        rubric,
        CFG,
        plugin_dir='p',
        config_with=None,
        config_without=None,
        pairwise_criterion='c',
        concurrency=1,
        run_arm=erroring_arm,
        judge_point=fake_point,
        judge_pair=fake_pair,
    )
    s = blob['summary']
    assert s['n_records'] == 3 and s['error_runs'] == 3
    assert s['n_usage_valid'] == 0  # every WITH arm errored -> nothing valid to score


def test_main_skips_skill_without_tasks_suite():
    import json

    import grade_tasks

    # A configured skill with no evals/tasks/ suite (e.g. brainstorming) must skip
    # cleanly (return 0), not crash the whole run_all grading loop. Pick one
    # dynamically so the test never hits the real-spawn path if the premise changes.
    cfg = json.loads((grade_tasks.REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    skill = next(
        s
        for s in sorted(cfg['plugin_of_skill'])
        if not (grade_tasks.TASKS_DIR / s / 'tasks.json').exists()
    )
    assert grade_tasks.main([skill]) == 0


if __name__ == '__main__':
    test_grade_skill_shape_over_repeats()
    test_grade_skill_counts_without_wins_and_ties()
    test_resolve_task_rubric_inline_wins()
    test_resolve_task_rubric_falls_back_to_default()
    test_resolve_plugin_dir_default_and_override()
    test_errored_with_arm_excluded_from_scoring()
    test_main_skips_skill_without_tasks_suite()
    print('ok: all grade_tasks tests passed')

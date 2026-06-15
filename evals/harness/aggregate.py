#!/usr/bin/env python3
"""Aggregate report/triggers.json + report/grading.json into a scorecard.

`build_scorecard` is the pure merge (unit-tested); the CLI renders Markdown to
report/scorecard.md.

    python evals/harness/aggregate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO / 'evals' / 'report'


def _gate(value, threshold) -> str:
    if value is None:
        return 'n/a'
    return 'PASS' if value >= threshold else 'FAIL'


def build_scorecard(
    triggers: dict, grading: dict, gates: dict, command_first=(), action_disciplines=()
) -> list[dict]:
    """Merge the two report blobs into one row per skill, with gate flags. Pure.

    `command_first` skills (invoked mainly via their slash command, like a panel
    you deliberately convene) report recall for information but are not gated on
    it — auto-firing is a bonus, not the contract.

    `action_disciplines` skills activate during real work (TDD, debugging,
    verification): the Write-less trigger arm cannot exercise them, so trigger-arm
    recall is informational and the grading arm's activation rate is surfaced as
    `task_arm_recall`, gated on the same `trigger_recall` threshold."""
    command_first = set(command_first)
    action_disciplines = set(action_disciplines)
    rows = []
    for skill in sorted(set(triggers) | set(grading)):
        t = triggers.get(skill) or {}
        g = (grading.get(skill) or {}).get('summary') or {}
        ungated = skill in command_first or skill in action_disciplines
        recall_gate = 'info' if ungated else _gate(t.get('recall'), gates['trigger_recall'])
        is_action = skill in action_disciplines
        task_arm_recall = g.get('with_activation_rate') if is_action else None
        rows.append(
            {
                'skill': skill,
                'recall': t.get('recall'),
                'recall_ci': t.get('recall_ci'),
                'recall_gate': recall_gate,
                'recall_hard': t.get('recall_hard'),
                'task_arm_recall': task_arm_recall,
                'task_arm_recall_gate': (
                    _gate(task_arm_recall, gates['trigger_recall']) if is_action else None
                ),
                'specificity': t.get('specificity'),
                'specificity_ci': t.get('specificity_ci'),
                'specificity_gate': _gate(t.get('specificity'), gates['trigger_specificity']),
                'correct_usage': g.get('correct_usage_rate'),
                'correct_usage_ci': g.get('correct_usage_ci'),
                'correct_usage_gate': _gate(g.get('correct_usage_rate'), gates['correct_usage']),
                'judge_agreement': g.get('mean_agreement'),
                'with_win_rate': g.get('with_win_rate'),
                'without_win_rate': g.get('without_win_rate'),
                'tie_rate': g.get('tie_rate'),
                'with_activation_rate': g.get('with_activation_rate'),
            }
        )
    return rows


def _pct(v) -> str:
    return 'n/a' if v is None else f'{v:.2f}'


def _ci(ci) -> str:
    return '' if not ci else f' [{ci[0]:.2f},{ci[1]:.2f}]'


def render_scorecard(rows: list[dict], triggers: dict, grading: dict) -> str:
    out = ['# Skill eval scorecard', '']
    out += [
        'Each cell is a rate in [0,1] with a Wilson 95% CI; gate verdicts in '
        'parentheses. Trigger axis = does the right skill auto-fire (recall) and '
        'stay quiet on near-misses (specificity). Usage axis = does the WITH-skill '
        "output satisfy the skill's discipline rubric. With/without = swap-order "
        'pairwise win-rate of the skill vs no-skill. A recall verdict of (info) '
        'marks a command-first skill (e.g. review-panel) whose auto-fire rate is '
        'reported but not gated — it is invoked deliberately via its slash command — '
        'or an action-discipline skill (TDD, debugging, verification), which the '
        'Write-less trigger arm cannot exercise: for those, the Activation column '
        'carries the gated task-arm recall proxy in parentheses.',
        '',
    ]

    # main table
    out += [
        '## Per-skill summary',
        '',
        '| Skill | Recall | Specificity | Correct-usage | Judge agr | WITH win | WITHOUT win | Tie | Activation |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for r in rows:
        out.append(
            f'| `{r["skill"]}` '
            f'| {_pct(r["recall"])}{_ci(r["recall_ci"])} ({r["recall_gate"]}) '
            f'| {_pct(r["specificity"])}{_ci(r["specificity_ci"])} ({r["specificity_gate"]}) '
            f'| {_pct(r["correct_usage"])}{_ci(r["correct_usage_ci"])} ({r["correct_usage_gate"]}) '
            f'| {_pct(r["judge_agreement"])} '
            f'| {_pct(r["with_win_rate"])} | {_pct(r["without_win_rate"])} | {_pct(r["tie_rate"])} '
            f'| {_pct(r["with_activation_rate"])}'
            + (
                f' ({r["task_arm_recall_gate"]})'
                if r.get('task_arm_recall_gate') is not None
                else ''
            )
            + ' |'
        )
    out.append('')

    # trigger misses (description-tuning signal)
    out += ['## Trigger misses (tuning signal)', '']
    any_miss = False
    for skill in sorted(triggers):
        for pq in triggers[skill].get('per_query', []):
            miss = (pq['should_trigger'] and pq['rate'] < 1.0) or (
                not pq['should_trigger'] and pq['rate'] > 0.0
            )
            if miss:
                any_miss = True
                if pq.get('expected_hard'):
                    kind = 'expected-hard (reported, not gated)'
                elif pq['should_trigger']:
                    kind = 'MISSED positive'
                else:
                    kind = 'FALSE FIRE on negative'
                out.append(
                    f'- `{skill}` — {kind} (fired {pq["k"]}/{pq["repeats"]}): "{pq["query"]}"'
                )
    if not any_miss:
        out.append('- none — every positive fired and every negative stayed quiet.')
    out.append('')

    # per-task with/without detail
    out += [
        '## With/without per task',
        '',
        '| Skill | Task | Usage pass-rate | WITH/WITHOUT/tie | Activation |',
        '|---|---|---|---|---|',
    ]
    for skill in sorted(grading):
        for t in grading[skill].get('tasks', []):
            pw = t.get('pairwise', {})
            out.append(
                f'| `{skill}` | {t["task_id"]} | {_pct(t.get("with_pass_rate"))} '
                f'| {pw.get("with_wins", 0)}/{pw.get("without_wins", 0)}/{pw.get("ties", 0)} '
                f'| {_pct(t.get("with_activation_rate"))} |'
            )
    out.append('')
    return '\n'.join(out)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; agent/query text can carry unicode.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cfg = json.loads((REPO / 'evals' / 'config.json').read_text(encoding='utf-8'))
    triggers_path = REPORT_DIR / 'triggers.json'
    grading_path = REPORT_DIR / 'grading.json'
    triggers = (
        json.loads(triggers_path.read_text(encoding='utf-8')) if triggers_path.exists() else {}
    )
    grading = json.loads(grading_path.read_text(encoding='utf-8')) if grading_path.exists() else {}
    if not triggers and not grading:
        print('no report/triggers.json or report/grading.json found — run the eval first')
        return 1

    rows = build_scorecard(
        triggers,
        grading,
        cfg['gates'],
        cfg.get('command_first_skills', []),
        cfg.get('action_discipline_skills', []),
    )
    md = render_scorecard(rows, triggers, grading)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / 'scorecard.md'
    out_path.write_text(md, encoding='utf-8')
    print(f'wrote {out_path}')
    print()
    print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())

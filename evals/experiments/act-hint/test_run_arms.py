"""The runner's pre-spend guards: the plan, the insertion point, and a dry run that
provably spends nothing.

`--dry-run` is the last thing between the design and the money, so it is tested like a
gate rather than trusted like a flag: the spawner is rebound to something that raises,
and the dry run has to complete anyway.

Runnable with pytest or `python test_run_arms.py`. Stdlib only.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
from itertools import pairwise
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    import yaml as _yaml  # noqa: F401 - run_arms' material check reads record.yaml
except ImportError:  # pragma: no cover - the runner supplies PyYAML
    print('skip: PyYAML not installed')
    sys.exit(0)

import run_arms  # noqa: E402 - after the path fix

BANK = run_arms.load_bank()
TABLE = run_arms.load_table()
PLAN = run_arms.build_plan(BANK, TABLE)


def test_the_plan_is_192_runs_across_the_declared_cells():
    assert len(PLAN) == 192
    for arm in TABLE['arms']:
        arm_jobs = [j for j in PLAN if j['arm'] == arm]
        assert len(arm_jobs) == 48, arm
        for cls in ('genuine', 'decoy'):
            assert len([j for j in arm_jobs if j['prompt_class'] == cls]) == 24, (arm, cls)
    for job in PLAN:
        assert job['repeat'] in (0, 1)
    assert len({(j['arm'], j['prompt_id'], j['repeat']) for j in PLAN}) == 192


def test_the_order_is_seeded_and_interleaved():
    """Deterministic under the frozen seed, and genuinely mixed -- a plan that ran one
    arm to completion before the next would confound arm with model drift."""
    assert run_arms.build_plan(BANK, TABLE) == PLAN
    assert run_arms.build_plan(BANK, TABLE, seed=run_arms.SEED + 1) != PLAN
    first_arms = [j['arm'] for j in PLAN[:16]]
    assert len(set(first_arms)) > 1, first_arms
    switches = sum(1 for a, b in pairwise(PLAN) if a['arm'] != b['arm'])
    assert switches > len(PLAN) / 2, switches


def test_the_injected_text_is_read_from_the_frozen_table():
    """Never regenerated at run time: every job carries the table's own bytes."""
    frozen = {(r['arm'], r['prompt_id']): r for r in TABLE['rows']}
    for job in PLAN:
        row = frozen[(job['arm'], job['prompt_id'])]
        assert job['injected'] == row['text']
        assert job['fires'] is row['fires']
    assert sum(1 for j in PLAN if j['arm'] == 'control' and j['fires']) == 0
    assert sum(1 for j in PLAN if j['arm'] == 'wide' and j['fires']) == 36
    assert sum(1 for j in PLAN if j['arm'] == 'inert' and j['fires']) == 36
    assert sum(1 for j in PLAN if j['arm'] == 'narrow' and j['fires']) == 24


def test_the_insertion_point_is_one_place_and_never_moves():
    composed = run_arms.compose('HINT', 'the prompt')
    assert composed == 'HINT\n\nthe prompt'
    assert composed.startswith('HINT')
    # an un-injected arm must not carry a stray blank line the others do not
    assert run_arms.compose('', 'the prompt') == 'the prompt'
    assert run_arms.INSERTION_POINT == 'prefix_blank_line'


def test_the_allowlist_is_one_constant_shared_by_every_arm():
    """Identical across arms by construction: there is only one value. `Skill` is IN
    it, which is what makes control a loaded-skill baseline rather than a no-treatment
    one; the writing tools are out, because the outcomes are properties of the text."""
    assert 'Skill' in run_arms.ALLOWED_TOOLS.split(',')
    for tool in ('Write', 'Edit', 'Bash', 'Task'):
        assert tool in run_arms.DISALLOWED_TOOLS.split(',')
        assert tool not in run_arms.ALLOWED_TOOLS.split(',')
    assert run_arms.MAX_TURNS == 6
    assert run_arms.REPEATS == 2


def test_the_projection_sits_inside_the_declared_band_and_under_the_ceiling():
    low, high = run_arms.projected_cost(len(PLAN))
    assert 25 <= high <= 60, (low, high)
    assert 24 <= low <= 30, (low, high)
    assert high < run_arms.CEILING_USD
    assert run_arms.COST_BAND_USD[1] < run_arms.PER_RUN_BUDGET_USD


def test_dry_run_prints_the_plan_and_spends_nothing():
    def explode(*_args, **_kwargs):
        raise AssertionError('--dry-run spawned a run')

    original = run_arms.run_agent
    run_arms.run_agent = explode
    try:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run_arms.main(['--dry-run'])
    finally:
        run_arms.run_agent = original
    out = buffer.getvalue()
    assert code == 0
    assert '192 runs' in out
    assert 'projected cost' in out
    assert f'${run_arms.CEILING_USD:.2f}' in out
    assert run_arms.MODEL in out
    assert 'nothing spawned, nothing spent' in out
    assert 'frozen materials verified' in out, 'the dry run must check materials too; it is free'
    for arm in TABLE['arms']:
        assert arm in out
    assert not (HERE / 'runs.jsonl').exists(), 'a dry run must not open the run log'


def test_the_frozen_materials_match_the_record_before_any_spend():
    assert run_arms.verify_materials() == []


def test_a_changed_material_refuses_the_run():
    """The refusal is the point: runs against edited materials would measure something
    the pre-registration does not describe. Checked against a tampered copy of the
    record, so the real one is never written to."""
    record = (HERE / 'record.yaml').read_text(encoding='utf-8')
    real = run_arms.load_table()  # any material; the bank's SHA is the one we corrupt
    assert real  # the table loaded, so the materials are on disk where the check looks
    with tempfile.TemporaryDirectory() as tmp:
        for name in ('bank.json', 'oracle_patterns.json', 'oracle_labels.json', 'verify.py'):
            shutil.copy2(HERE / name, Path(tmp) / name)
        for name in ('control.json', 'narrow.json', 'wide.json', 'inert.json'):
            (Path(tmp) / 'rules').mkdir(exist_ok=True)
            shutil.copy2(HERE / 'rules' / name, Path(tmp) / 'rules' / name)
        shutil.copy2(HERE / 'firing_table.json', Path(tmp) / 'firing_table.json')
        (Path(tmp) / 'bank.json').write_text('{"prompts": []}', encoding='utf-8')
        (Path(tmp) / 'record.yaml').write_text(record, encoding='utf-8', newline='\n')
        problems = run_arms.verify_materials(Path(tmp) / 'record.yaml')
    assert any('bank' in p for p in problems), problems


def test_the_ceiling_halts_before_it_is_crossed():
    """The halt fires BEFORE a spawn that could take the total past the ceiling, not
    after one already has. The stub charges more than the per-run cap on purpose --
    that is the shape that used to overshoot."""
    charged = 0.45

    def stub(job, _prompt, *, config_dir=None, cwd=None):
        return {
            **{k: job[k] for k in ('arm', 'prompt_id', 'prompt_class', 'language', 'repeat')},
            'response': '',
            'is_error': False,
            'cost_usd': charged,
            'num_turns': 1,
            'activated_skills': [],
            'plugins_loaded': [],
        }

    prompts = {p['id']: p['text'] for p in BANK}
    buffer = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(buffer):
        completed, spent, halted = run_arms.execute(
            PLAN,
            prompts,
            out=Path(tmp) / 'runs.jsonl',
            config_dir=None,
            cwd=None,
            spawn=stub,
        )
        written = len((Path(tmp) / 'runs.jsonl').read_text(encoding='utf-8').splitlines())
    assert halted is True
    assert completed < len(PLAN), 'the stub is too cheap to reach the ceiling'
    assert spent < run_arms.CEILING_USD, f'crossed the ceiling at ${spent:.2f}'
    assert spent + run_arms.PER_RUN_BUDGET_USD > run_arms.CEILING_USD, spent
    assert written == completed, 'every completed run is on disk when the halt fires'
    out = buffer.getvalue()
    assert 'HALT before run' in out
    assert 'complete prompt-pairs only' in out, 'the halt must name the pre-registered fallback'


def test_a_run_that_fits_under_the_ceiling_is_not_halted():
    """The margin must not cost runs that were always affordable."""

    def stub(job, _prompt, *, config_dir=None, cwd=None):
        return {
            **{k: job[k] for k in ('arm', 'prompt_id', 'prompt_class', 'language', 'repeat')},
            'response': '',
            'is_error': False,
            'cost_usd': 0.2,
            'num_turns': 1,
            'activated_skills': [],
            'plugins_loaded': [],
        }

    prompts = {p['id']: p['text'] for p in BANK}
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        completed, spent, halted = run_arms.execute(
            PLAN, prompts, out=Path(tmp) / 'runs.jsonl', config_dir=None, cwd=None, spawn=stub
        )
    assert halted is False
    assert completed == len(PLAN) == 192
    assert spent < run_arms.CEILING_USD


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
    print(
        'ok: 192-run plan, frozen insertion point, material check, ceiling halt before '
        'crossing, and a dry run that spends nothing'
    )

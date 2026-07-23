"""Tests for the dispatch lexical router. Runnable with pytest or `python test_router.py`.

Calibration bars (dev-set numbers — the trigger datasets are spent holdouts and
are DEV data for the router; seal a fresh holdout before publishing
generalization claims):
  - per routed skill: recall >= 0.60 on its should_trigger positives
  - per routed skill: specificity >= 0.90 on its own should_trigger=false negatives
  - cross-sweep: firing on another dataset's negative that is NOBODY's positive
    counts against a <= 0.15 cross-fire budget per skill
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import router

SCRIPTS_DIR = Path(__file__).parent
RULES_PATH = SCRIPTS_DIR / 'router_rules.json'
# scripts/ -> choosing-tools -> skills -> humblepowers -> plugins -> repo root
REPO_ROOT = SCRIPTS_DIR.parents[4]
TRIGGER_DIR = REPO_ROOT / 'evals' / 'trigger'

RECALL_BAR = 0.60
SPECIFICITY_BAR = 0.90
CROSS_FIRE_BAR = 0.15


def _rules():
    return router.load_rules(RULES_PATH)


def _dataset(skill_file: str) -> list[dict]:
    return json.loads((TRIGGER_DIR / skill_file).read_text(encoding='utf-8'))


def _routed_ids(rules) -> list[str]:
    return [s['id'] for s in rules['skills']]


def _dataset_file_for(skill_id: str) -> str:
    return skill_id.split(':', 1)[1] + '.json'


def _fired_ids(prompt: str, rules) -> set[str]:
    return {m['id'] for m in router.route(prompt, rules)}


# --- structural properties -------------------------------------------------


def test_rules_load_and_compile():
    rules = _rules()
    assert rules['skills'], 'rules must route at least one skill'
    for skill in rules['skills']:
        assert ':' in skill['id'], f'{skill["id"]}: id must be plugin:skill'
        for pat in skill['patterns'] + skill.get('negative_patterns', []):
            re.compile(pat)  # must be valid regex
            assert '(?P' not in pat and '(?:(?:(?:' not in pat, 'keep patterns simple'


def test_max_two_candidates():
    rules = _rules()
    # A prompt stuffed with trigger vocabulary across many skills still names <= 2.
    prompt = (
        'Migrate the pipeline, backfill the dataset for the dashboard, '
        "let's build a new project, red team this design with fresh eyes, "
        'journal this session, hand this off into its own session, '
        "tests pass locally but fail in CI and the previous fix didn't stick"
    )
    assert len(router.route(prompt, rules)) <= 2


def test_silence_on_no_match():
    rules = _rules()
    for prompt in ('hello', 'what time is it', 'thanks, looks good', 'continue'):
        assert router.route(prompt, rules) == []


def test_matched_words_reported():
    rules = _rules()
    matches = router.route('Backfill six months into the sessions table and replay it', rules)
    assert matches, 'expected a data-engineering hit'
    assert all(m['matched'] for m in matches), 'matches must carry matched words'


def test_payload_is_ascii():
    rules = _rules()
    for skill in rules['skills']:
        skill['id'].encode('ascii')
    line = router.hint_line(router.route('backfill the pipeline and replay history', rules))
    line.encode('ascii')


def test_latency_bound():
    rules = _rules()
    prompt = 'Refactor the transform that builds the orders fact table dashboards read. ' * 10
    start = time.perf_counter()
    for _ in range(1000):
        router.route(prompt, rules)
    assert time.perf_counter() - start < 2.0, 'router too slow for a prompt-path hook'


# --- calibration against the trigger datasets ------------------------------


def test_recall_and_specificity_per_skill():
    rules = _rules()
    failures = []
    for skill_id in _routed_ids(rules):
        data = _dataset(_dataset_file_for(skill_id))
        pos = [d['query'] for d in data if d['should_trigger']]
        neg = [d['query'] for d in data if not d['should_trigger']]
        hits = sum(1 for q in pos if skill_id in _fired_ids(q, rules))
        false_fires = sum(1 for q in neg if skill_id in _fired_ids(q, rules))
        recall = hits / len(pos) if pos else 1.0
        specificity = 1 - (false_fires / len(neg)) if neg else 1.0
        if recall < RECALL_BAR:
            failures.append(f'{skill_id}: recall {recall:.2f} < {RECALL_BAR}')
        if specificity < SPECIFICITY_BAR:
            failures.append(f'{skill_id}: specificity {specificity:.2f} < {SPECIFICITY_BAR}')
    assert not failures, '; '.join(failures)


def test_cross_sweep_budget():
    """A skill firing on another dataset's negative is a violation unless that
    query is a positive somewhere in the routed corpus."""
    rules = _rules()
    routed = _routed_ids(rules)
    all_positives = set()
    for skill_id in routed:
        for d in _dataset(_dataset_file_for(skill_id)):
            if d['should_trigger']:
                all_positives.add(d['query'])
    violations = dict.fromkeys(routed, 0)
    totals = dict.fromkeys(routed, 0)
    for owner_id in routed:
        for d in _dataset(_dataset_file_for(owner_id)):
            if d['should_trigger']:
                continue
            fired = _fired_ids(d['query'], rules)
            for sid in routed:
                if sid == owner_id:
                    continue  # own-negative behavior is the specificity test
                totals[sid] += 1
                if sid in fired and d['query'] not in all_positives:
                    violations[sid] += 1
    failures = [
        f'{sid}: cross-fire {violations[sid]}/{totals[sid]}'
        for sid in routed
        if totals[sid] and violations[sid] / totals[sid] > CROSS_FIRE_BAR
    ]
    assert not failures, '; '.join(failures)


def test_adversarial_holdout_false_fire_budget():
    """The 2026-07-22 blind adversarial holdout's near-miss negatives must stay
    within a documented false-fire budget. This is a SEALED regression set —
    never tune the rules against it beyond the two accepted borderline fires
    (a genuinely-failing UI test → debugging; adding a column to a fact table a
    report reads → a schema change with consumers). Both are defensible, so the
    budget is 2/20; any third false-fire is a regression to investigate."""
    adversarial = TRIGGER_DIR / 'holdout' / 'dispatch-router-adversarial.json'
    if not adversarial.exists():
        return  # dataset optional in a partial checkout
    rules = _rules()
    cases = json.loads(adversarial.read_text(encoding='utf-8'))
    negatives = [c for c in cases if not c['should_trigger']]
    fired = [c['query'] for c in negatives if router.route(c['query'], rules)]
    assert len(fired) <= 2, f'false-fire budget exceeded ({len(fired)}/{len(negatives)}): {fired}'


def test_recall_holdout_floors():
    """The 2026-07-23 blind recall holdout (sealed with baseline in
    holdout/BASELINES.md) gates against regression, never against fitting:
    floors sit under the sealed numbers (overall 0.50, direct 0.94, 2/28 null
    false-fires). Tuning against individual cases spends the seal — the
    register gradient (direct 0.94 / embedded 0.44 / paraphrase 0.12) is the
    lexical ceiling and is closed by a semantic layer, not more patterns."""
    holdout = TRIGGER_DIR / 'holdout' / 'dispatch-router-recall.json'
    if not holdout.exists():
        return  # dataset optional in a partial checkout
    rules = _rules()
    cases = json.loads(holdout.read_text(encoding='utf-8'))
    pos = [c for c in cases if c.get('expected')]
    direct = [c for c in pos if c.get('register') == 'direct']
    nulls = [c for c in cases if not c.get('expected')]
    hits = sum(1 for c in pos if c['expected'] in _fired_ids(c['query'], rules))
    direct_hits = sum(1 for c in direct if c['expected'] in _fired_ids(c['query'], rules))
    null_fires = sum(1 for c in nulls if _fired_ids(c['query'], rules))
    assert hits / len(pos) >= 0.45, f'overall recall regressed: {hits}/{len(pos)}'
    assert direct_hits / len(direct) >= 0.85, (
        f'direct recall regressed: {direct_hits}/{len(direct)}'
    )
    assert null_fires <= 3, f'null false-fires regressed: {null_fires}/{len(nulls)}'


def test_multilingual_is_silent_not_wrong():
    """Portuguese-intent prompts (no English trigger vocab) must not mis-fire —
    the router is monolingual-English and degrades to silence, the safe default,
    not to a confident wrong route."""
    rules = _rules()
    pt_no_loanword = [
        'me ajuda a pensar o desenho antes de codar',
        'o bug voltou depois do meu fix, ja e a terceira tentativa',
        'vamos separar isso numa sessao propria antes de perder o contexto',
    ]
    for p in pt_no_loanword:
        # silence is acceptable; a wrong confident route is not. We assert no
        # route here because none of these carry a loanword the rules key on.
        assert router.route(p, rules) == [], (
            f'PT prompt mis-fired: {p!r} -> {router.route(p, rules)}'
        )


if __name__ == '__main__':
    import sys

    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
            except AssertionError as exc:
                failed += 1
                print(f'FAIL {name}: {exc}')
    if failed:
        sys.exit(1)
    print('ok: all router tests passed')

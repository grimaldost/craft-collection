"""Guards over the act-hint detector's frozen firing table.

These are the checks that make "router-realistic" a property something verified
rather than a claim someone made. They run for free, before any spend, and every
one of them is a thing that would otherwise be discovered after the money is gone:

  * PARITY (condition C2) -- every frozen row for the ROUTER-DERIVED arms (narrow,
    wide) equals what the real router produces for that prompt under that arm's
    rules, candidate list and injected text alike. `inert` is asserted against
    wide's row set and its own authored neutral text, and `control` against an
    empty candidate list.
  * the wide/inert length match, per row, on estimated tokens.
  * PRIMEABILITY -- no injected text and no bank prompt carries the activation-line
    format or any of the oracle's five element labels, in either language. The
    constraint binds the bank because the router echoes literal spans of the prompt
    into the treatment.
  * the hook floor over every bank prompt, and the visible no-injection row a
    below-floor prompt would produce.
  * the shipped humblepowers router_rules.json, byte-unchanged.
  * the committed table matching what the generator produces today.

Runnable with pytest or `python test_firing_table.py`. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROUTER_DIR = REPO / 'plugins' / 'humblepowers' / 'skills' / 'choosing-tools' / 'scripts'

for extra in (str(HERE), str(ROUTER_DIR)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import firing_table  # noqa: E402 - after the path fix
import router  # noqa: E402 - the real router, to reproduce the frozen rows
import verify  # noqa: E402 - the oracle's patterns are the primeability ban list

TABLE = json.loads((HERE / 'firing_table.json').read_text(encoding='utf-8'))
BANK = json.loads((HERE / 'bank.json').read_text(encoding='utf-8'))['prompts']
ROWS = TABLE['rows']

# The shipped router rules, pinned. The detector's candidate rows exist only as
# offline inputs under rules/; nothing in this wave may add them to the file the
# hook actually loads, and the sealed router budgets in test_router.py depend on
# that file not moving underneath them. A DELIBERATE router change updates this
# pin in the same diff that changes the file -- after confirming the change is a
# router change and not a detector row leaking into production.
SHIPPED_RULES = ROUTER_DIR / 'router_rules.json'
SHIPPED_RULES_SHA256 = 'd6721cfe2bdcde1124d8f0ca0576d045b3898e6a610bd8491236d6f47f42c2c8'


def _rows(arm: str) -> dict[str, dict]:
    return {r['prompt_id']: r for r in ROWS if r['arm'] == arm}


def _prompt(pid: str) -> dict:
    return next(p for p in BANK if p['id'] == pid)


# --- the table covers the whole grid ----------------------------------------


def test_every_arm_covers_every_prompt():
    assert len(BANK) == 24, len(BANK)
    assert len(ROWS) == len(firing_table.ARMS) * len(BANK) == 96
    for arm in firing_table.ARMS:
        assert set(_rows(arm)) == {p['id'] for p in BANK}, arm


def test_bank_is_balanced_by_class_and_language():
    for cls in ('genuine', 'decoy'):
        same = [p for p in BANK if p['class'] == cls]
        assert len(same) == 12, (cls, len(same))
        for lang in ('en', 'pt'):
            assert len([p for p in same if p['language'] == lang]) == 6, (cls, lang)


# --- parity with the real router (C2) ---------------------------------------


def test_router_derived_arms_match_the_real_router():
    """narrow and wide: the frozen candidate list and the frozen injected text are
    exactly what the real router returns for that prompt under that arm's rules."""
    for arm in ('narrow', 'wide'):
        rules = router.load_rules(HERE / 'rules' / f'{arm}.json')
        for pid, row in _rows(arm).items():
            text = _prompt(pid)['text']
            matches = router.route(text.strip(), rules)
            assert row['candidates'] == [m['id'] for m in matches], (arm, pid)
            assert row['matched'] == [m['matched'] for m in matches], (arm, pid)
            assert row['text'] == router.hint_line(matches), (arm, pid)
            assert row['fires'] is bool(row['text']), (arm, pid)
            if row['fires']:
                assert row['text_source'] == 'router.hint_line', (arm, pid)


def test_control_produces_no_candidates_anywhere():
    for pid, row in _rows('control').items():
        assert row['candidates'] == [], pid
        assert row['fires'] is False, pid
        assert row['text'] == '', pid


def test_inert_is_wide_rows_with_authored_text():
    """inert fires exactly where wide fires, and says something else entirely."""
    wide, inert = _rows('wide'), _rows('inert')
    assert {p for p, r in wide.items() if r['fires']} == {p for p, r in inert.items() if r['fires']}
    for pid, row in inert.items():
        if not row['fires']:
            continue
        assert row['text_source'] == 'authored_neutral', pid
        assert row['text'] == firing_table.inert_text(wide[pid]['chars']), pid
        assert row['text'] != wide[pid]['text'], pid
        # the neutral text names none of the four things it must not name
        low = row['text'].lower()
        for banned in ('experiment', 'evaluat', 'rigor', 'tier'):
            assert banned not in low, (pid, banned)


def test_wide_and_inert_are_token_matched_per_row():
    wide, inert = _rows('wide'), _rows('inert')
    worst = 0.0
    for pid, w in wide.items():
        if not w['fires']:
            continue
        i = inert[pid]
        deviation = abs(i['est_tokens'] - w['est_tokens']) / w['est_tokens']
        worst = max(worst, deviation)
        assert deviation <= firing_table.TOKEN_MATCH_TOLERANCE, (pid, deviation)
    assert worst <= firing_table.TOKEN_MATCH_TOLERANCE, worst


def test_the_arms_actually_differ_in_exposure():
    """A table where every arm fires identically would pass every check above and
    measure nothing. narrow must be a strict subset of wide, and control empty."""
    fired = {arm: {p for p, r in _rows(arm).items() if r['fires']} for arm in firing_table.ARMS}
    assert fired['control'] == set()
    assert fired['narrow'] < fired['wide'], (len(fired['narrow']), len(fired['wide']))
    assert fired['wide'] == fired['inert']
    genuine = {p['id'] for p in BANK if p['class'] == 'genuine'}
    assert fired['narrow'] == genuine, (
        'narrow must reach every genuine prompt to be distinguishable'
    )
    assert fired['wide'] & {p['id'] for p in BANK if p['class'] == 'decoy'}, (
        'wide exists to price habituation; it must reach some decoys'
    )


# --- primeability ------------------------------------------------------------


def _primeability_offenders(label: str, text: str, pats: verify.Patterns) -> list[str]:
    out: list[str] = []
    if pats.activation.search(text):
        out.append(f'{label}: carries the activation-line format')
    for name, patterns in pats.elements.items():
        for pat in patterns:
            hit = pat.search(text)
            if hit:
                out.append(f'{label}: carries element {name!r} via {hit.group(0)!r}')
    return out


def test_no_bank_prompt_or_injected_text_primes_the_oracle():
    """The oracle keys on the activation-line format and the five element labels, so
    neither may reach the model through the prompt or through the injection. Because
    the router echoes literal spans of the prompt, a violation is repaired by editing
    the bank or narrowing the pattern -- before the freeze."""
    pats = verify.load_patterns()
    offenders: list[str] = []
    for prompt in BANK:
        offenders += _primeability_offenders(f'bank/{prompt["id"]}', prompt['text'], pats)
    for row in ROWS:
        if row['text']:
            offenders += _primeability_offenders(
                f'{row["arm"]}/{row["prompt_id"]}', row['text'], pats
            )
    assert not offenders, offenders


# --- the hook's floor --------------------------------------------------------


def test_every_bank_prompt_clears_the_hook_floor():
    for prompt in BANK:
        # already stripped, so the text the runner delivers is the text that was routed
        assert prompt['text'] == prompt['text'].strip(), prompt['id']
        assert firing_table.hook_skip(prompt['text']) is None, prompt['id']
    assert all(r['hook_skip'] is None for r in ROWS)
    assert TABLE['hook_floor']['min_words'] == 4
    assert TABLE['hook_floor']['min_chars'] == 15


def test_a_below_floor_prompt_is_a_visible_row_in_every_arm():
    """Not a silent hole: the generator emits the row with its reason, in each arm."""
    assert firing_table.hook_skip('too short') == 'below_hook_floor'
    assert firing_table.hook_skip('/compact and continue please') == 'slash_command'
    assert firing_table.hook_skip('[SYSTEM NOTIFICATION] a subagent finished') == 'synthetic_prefix'
    short = {'id': 'x-short', 'class': 'genuine', 'language': 'en', 'text': 'too short'}
    rules = {arm: firing_table.load_arm_rules(arm) for arm in firing_table.ARMS}
    rows = firing_table.build_rows([short], rules)
    assert len(rows) == len(firing_table.ARMS)
    for row in rows:
        assert row['prompt_id'] == 'x-short'
        assert row['fires'] is False
        assert row['hook_skip'] == 'below_hook_floor'
        assert row['text'] == ''


# --- the shipped rules stay out of the blast radius --------------------------


def test_shipped_router_rules_are_byte_unchanged():
    data = SHIPPED_RULES.read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha256(data).hexdigest() == SHIPPED_RULES_SHA256, (
        'plugins/humblepowers/skills/choosing-tools/scripts/router_rules.json changed. The '
        'detector drives the router READ-ONLY and its arm rows live only under '
        'evals/experiments/act-hint/rules/; if this is a deliberate router change, update '
        'SHIPPED_RULES_SHA256 in the same diff.'
    )


def test_arm_patterns_are_not_in_the_shipped_rules():
    """The pin above catches any edit; this says WHICH edit would be the bad one, so
    a leak of a detector row into the file the hook loads reads as itself."""
    shipped = SHIPPED_RULES.read_text(encoding='utf-8')
    for arm in ('narrow', 'wide', 'inert'):
        rules = json.loads((HERE / 'rules' / f'{arm}.json').read_text(encoding='utf-8'))
        for skill in rules['skills']:
            for pattern in skill['patterns']:
                assert pattern not in shipped, (
                    f'{arm} arm pattern {pattern!r} appears in the shipped router rules; the '
                    'detector rows are offline inputs only'
                )


# --- the committed table is what the generator produces today ----------------


def test_the_committed_table_is_fresh():
    assert firing_table.main(['--check']) == 0


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
    print('ok: firing table parity, token match, primeability and hook floor all hold')

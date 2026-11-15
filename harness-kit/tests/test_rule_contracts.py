#!/usr/bin/env python3
"""Checks of the `[rules]` table of the two harness contracts.

Contract under test:
- each contract holds a `[rules]` table whose first entry is
  `uv-project-uses-uv`, the rule of the uv pack, and whose other entries are
  among the series and owner-acts packs' rules, present where their guard cells
  held;
- each entry has exactly the keys `state`, `mark` and `evidence`, as the
  contract's other entries do: `state = "tested"`, `mark = "measured"`, and an
  ASCII `evidence` that names the rule's cells (`uv-deny`, `uv-allow-outside`
  and `uv-allow-mention` for the uv rule; `series-guard` for the series rule;
  `owner-acts-deny` and `owner-acts-allow` for the owner-acts rule), the
  contract's harness version and a date;
- `harness`, `objective`, `loss`, `rules` and `notes` are the contract's only
  top-level keys.

Stdlib-runnable: `python test_rule_contracts.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import tomllib
from harness_kit import doctor
from kit_fixtures import run_module

PACKS = Path(__file__).resolve().parents[1] / 'packs'
PACK = PACKS / 'uv' / 'pack.toml'
RULE_ID = 'uv-project-uses-uv'
CELLS = ('uv-deny', 'uv-allow-outside', 'uv-allow-mention')
# The guard rules, their packs and the guard cells that measure each.
GUARD_RULES = {
    'series-second-pr-declared': ('series', ('series-guard',)),
    'owner-acts-named-by-owner': ('owner-acts', ('owner-acts-deny', 'owner-acts-allow')),
}
PINNED = {'claude-code': '2.1.316', 'opencode': '2.2.5'}
STATES = ('tested', 'degraded', 'absent', 'unknown')
MARKS = ('measured', 'read', 'inferred')


def test_each_contract_holds_the_uv_rule_as_tested_and_measured():
    for harness in PINNED:
        contract = doctor.load_contract(harness)
        rules = contract.get('rules')
        assert isinstance(rules, dict), (harness, rules)
        assert list(rules)[:1] == [RULE_ID], (harness, list(rules))
        assert set(list(rules)[1:]) <= set(GUARD_RULES), (harness, list(rules))
        for entry in rules.values():
            assert set(entry) == {'state', 'mark', 'evidence'}, (harness, entry)
            assert entry['state'] == 'tested' and entry['state'] in STATES, (harness, entry)
            assert entry['mark'] == 'measured' and entry['mark'] in MARKS, (harness, entry)


def test_a_guard_rule_entry_names_its_cells_the_version_and_a_date():
    for harness, version in PINNED.items():
        rules = doctor.load_contract(harness)['rules']
        for rule_id, (_, cells) in GUARD_RULES.items():
            if rule_id not in rules:
                continue
            evidence = rules[rule_id]['evidence']
            assert evidence.isascii(), (harness, evidence)
            for cell in cells:
                assert re.search(rf'(?<![\w-]){cell}(?![\w-])', evidence), (harness, cell)
            assert version in evidence, (harness, evidence)
            assert re.search(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', evidence), (harness, evidence)


def test_a_guard_rule_is_its_packs_rule():
    for rule_id, (pack, _) in GUARD_RULES.items():
        data = tomllib.loads((PACKS / pack / 'pack.toml').read_text(encoding='utf-8'))
        assert rule_id in [rule['id'] for rule in data['rule']], (pack, data['rule'])


def test_the_evidence_names_the_cells_the_version_and_a_date():
    for harness, version in PINNED.items():
        evidence = doctor.load_contract(harness)['rules'][RULE_ID]['evidence']
        assert evidence.isascii(), (harness, evidence)
        for cell in CELLS:
            assert re.search(rf'(?<![\w-]){cell}(?![\w-])', evidence), (harness, cell, evidence)
        assert version in evidence, (harness, evidence)
        assert re.search(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', evidence), (harness, evidence)


def test_the_rule_is_the_uv_packs_rule():
    pack = tomllib.loads(PACK.read_text(encoding='utf-8'))
    assert RULE_ID in [rule['id'] for rule in pack['rule']], pack['rule']


def test_the_contracts_keep_their_shape():
    for harness in PINNED:
        contract = doctor.load_contract(harness)
        keys = {'harness', 'objective', 'loss', 'rules', 'notes'}
        assert set(contract) == keys, (harness, set(contract))
        assert contract['harness']['version'] == PINNED[harness], contract['harness']


if __name__ == '__main__':
    run_module(globals(), 'rule entries of the contracts')

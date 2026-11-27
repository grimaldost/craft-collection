#!/usr/bin/env python3
"""Checks of the `[notes]` table and the note losses of the two harness contracts.

Contract under test:
- each contract holds a `[notes]` table with exactly the entries `prompt` and
  `outcome`, each with exactly the keys `state`, `mark` and `evidence`;
  `state` is `tested` or `absent`; a `tested` entry has `mark = "measured"`
  and an ASCII `evidence` that names the guard cells needing that kind
  (`owner-acts-allow` for prompt notes, `series-guard` for outcome notes), the
  contract's harness version and a date;
- each contract lists the losses `prompt-origin-unproved` (objective
  `run_identity`, mark `measured`) and `prompt-note-lost-keeps-earlier`
  (objective `prevention`, mark `inferred`); each has exactly the keys `id`,
  `objective`, `mark`, `evidence` and `text`, and an `evidence` that names the
  harness version and a date.

Stdlib-runnable: `python test_note_contracts.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import doctor
from kit_fixtures import run_module

PINNED = {'claude-code': '2.1.316', 'opencode': '2.2.5'}
KIND_CELLS = {'prompt': ('owner-acts-allow',), 'outcome': ('series-guard',)}
NOTE_LOSSES = {
    'claude-code': {
        'prompt-origin-unproved': ('run_identity', 'measured'),
        'prompt-note-lost-keeps-earlier': ('prevention', 'inferred'),
    },
    'opencode': {
        'prompt-origin-unproved': ('run_identity', 'measured'),
        'prompt-note-lost-keeps-earlier': ('prevention', 'inferred'),
    },
}
DATE = re.compile(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}')


def test_each_contract_holds_a_notes_entry_per_kind():
    for harness, version in PINNED.items():
        notes = doctor.load_contract(harness).get('notes')
        assert isinstance(notes, dict) and set(notes) == set(KIND_CELLS), (harness, notes)
        for kind, entry in notes.items():
            assert set(entry) == {'state', 'mark', 'evidence'}, (harness, kind, entry)
            assert entry['state'] in ('tested', 'absent'), (harness, kind, entry)
            assert entry['mark'] in ('measured', 'read', 'inferred'), (harness, kind, entry)
            assert entry['evidence'].isascii() and entry['evidence'].strip(), (harness, entry)
            if entry['state'] != 'tested':
                continue
            assert entry['mark'] == 'measured', (harness, kind, entry)
            for cell in KIND_CELLS[kind]:
                assert re.search(rf'(?<![\w-]){cell}(?![\w-])', entry['evidence']), (harness, cell)
            assert version in entry['evidence'] and DATE.search(entry['evidence']), entry


def test_each_contract_lists_the_note_losses():
    for harness, version in PINNED.items():
        losses = {loss['id']: loss for loss in doctor.load_contract(harness)['loss']}
        for loss_id, (objective, mark) in NOTE_LOSSES[harness].items():
            loss = losses.get(loss_id)
            assert loss is not None, (harness, loss_id)
            assert set(loss) == {'id', 'objective', 'mark', 'evidence', 'text'}, loss
            assert (loss['objective'], loss['mark']) == (objective, mark), loss
            assert version in loss['evidence'] and DATE.search(loss['evidence']), loss
            assert loss['text'].strip() and loss['text'].isascii(), loss
    claude = {loss['id'] for loss in doctor.load_contract('claude-code')['loss']}
    assert 'patch-refused-under-owner-acts' not in claude, claude


if __name__ == '__main__':
    run_module(globals(), 'note entries of the contracts')

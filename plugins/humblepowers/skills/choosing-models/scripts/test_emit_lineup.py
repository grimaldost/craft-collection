#!/usr/bin/env python3
"""Self-contained checks for emit_lineup.py (no pytest required)."""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import emit_lineup as el

MODELS_TOML = Path(__file__).resolve().parent.parent / 'models.toml'


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = el.main(argv)
    return rc, buf.getvalue()


def _shipped_pairs() -> dict[str, tuple[str, str]]:
    """tier -> (api_string, harness_alias), parsed straight out of the shipped file.

    Deliberately a SECOND reader of models.toml. If the emitter ever grows its own
    copy of the lineup it becomes the fifth mirror, which is the failure this file
    exists to prevent -- so the expectation is re-derived from the source here,
    never written down as a literal.
    """
    text = MODELS_TOML.read_text(encoding='utf-8')
    pairs: dict[str, tuple[str, str]] = {}
    for block in text.split('[[models]]')[1:]:
        tier = re.search(r"^tier\s*=\s*'([^']+)'", block, re.MULTILINE)
        api = re.search(r"^api_string\s*=\s*'([^']+)'", block, re.MULTILINE)
        alias = re.search(r"^harness_alias\s*=\s*'([^']+)'", block, re.MULTILINE)
        if tier and api and alias:
            pairs[tier.group(1)] = (api.group(1), alias.group(1))
    return pairs


def test_every_shipped_tier_emits_its_own_api_string():
    for tier, (api, _) in _shipped_pairs().items():
        rc, out = _run(['--format', 'model', '--tier', tier, '--resolved-on', '2026-01-01'])
        assert rc == 0, out
        assert f'model = "{api}"' in out, f'{tier}: {out}'


def test_every_shipped_tier_emits_its_own_harness_alias():
    """The Agent tool and workflow agent() take the alias, never the api string."""
    for tier, (_, alias) in _shipped_pairs().items():
        rc, out = _run(['--format', 'alias', '--tier', tier, '--resolved-on', '2026-01-01'])
        assert rc == 0, out
        assert out.strip().splitlines()[-1] == alias, f'{tier}: {out}'


def test_the_table_carries_every_tier_and_nothing_else():
    rc, out = _run(['--format', 'table', '--resolved-on', '2026-01-01'])
    assert rc == 0, out
    assert '[governance.tier_models]' in out
    for tier, (api, _) in _shipped_pairs().items():
        assert f'{tier} = "{api}"' in out, f'{tier} missing: {out}'


def test_thresholds_are_never_emitted():
    """Thresholds are calibratable policy, not lineup: emitting them into an
    artefact would let a run carry a routing cut nobody calibrated for it."""
    for fmt in ('model', 'alias', 'table'):
        argv = ['--format', fmt, '--resolved-on', '2026-01-01']
        if fmt != 'table':
            argv += ['--tier', 'strong']
        _, out = _run(argv)
        assert 'threshold' not in out.lower(), out
        for band in ('0-25', '26-55', '56-100'):
            assert band not in out, out


def test_the_stamp_is_the_one_mirror_check_looks_for():
    """The emitter writes the stamp the walk verifies. If these two phrasings
    drift apart, every emitted artefact reads as a stale mirror."""
    rc, out = _run(['--format', 'table', '--resolved-on', '2026-01-01'])
    assert rc == 0, out
    reviewed = re.search(
        r'^last_reviewed\s*=\s*"([^"]+)"', MODELS_TOML.read_text(encoding='utf-8'), re.MULTILINE
    )
    assert reviewed, 'the canonical file has no [meta].last_reviewed'
    assert f'lineup synced {reviewed.group(1)}' in out, out


def test_both_dates_are_carried_so_the_older_one_can_age_the_artefact():
    """resolved_on is when the block was emitted; policy_reviewed_on is how old
    the SOURCE was at that moment. A fresh emission off a stale table must not
    read as fresh."""
    _, out = _run(['--format', 'table', '--resolved-on', '2026-01-01'])
    assert 'resolved 2026-01-01' in out, out
    assert 'last_reviewed' in out, out


def test_an_unknown_tier_names_the_known_ones_and_exits_one():
    rc, out = _run(['--format', 'model', '--tier', 'titanium'])
    assert rc == 1, out
    assert 'titanium' in out and 'strong' in out, out


def test_output_is_ascii_and_paste_ready():
    for fmt, extra in (('model', ['--tier', 'weak']), ('table', [])):
        _, out = _run(['--format', fmt, '--resolved-on', '2026-01-01', *extra])
        out.encode('ascii')
        assert not out.startswith('\n'), out


def main() -> int:
    test_every_shipped_tier_emits_its_own_api_string()
    test_every_shipped_tier_emits_its_own_harness_alias()
    test_the_table_carries_every_tier_and_nothing_else()
    test_thresholds_are_never_emitted()
    test_the_stamp_is_the_one_mirror_check_looks_for()
    test_both_dates_are_carried_so_the_older_one_can_age_the_artefact()
    test_an_unknown_tier_names_the_known_ones_and_exits_one()
    test_output_is_ascii_and_paste_ready()
    print('ok: emit_lineup')
    return 0


if __name__ == '__main__':
    sys.exit(main())

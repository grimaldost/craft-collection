#!/usr/bin/env python3
"""Self-contained checks for lineup_check.py (no pytest required)."""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lineup_check as lc


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = lc.main(argv)
    return rc, buf.getvalue()


def test_reads_the_real_tier_data():
    api, alias = lc.known_ids()
    assert api, 'no api_strings parsed from the shipped models.toml'
    assert 'opus' in alias and 'haiku' in alias


def test_every_shipped_api_string_and_alias_passes():
    api, alias = lc.known_ids()
    for m in api | alias:
        assert _run([m]) == (0, ''), m


def test_dated_snapshot_and_context_variant_pass():
    """A harness id is not always an API string. If those fired, the check would
    go off on every session and get muted -- the exact failure it prevents."""
    api, _ = lc.known_ids()
    base = sorted(api)[0]
    for variant in (f'{base}-20260115', f'{base}[1m]'):
        assert _run([variant]) == (0, ''), variant


def test_a_dotted_successor_is_not_a_variant_of_its_predecessor():
    """`claude-fable-5-1` is a new model, not a snapshot of `claude-fable-5`. The
    bare-prefix rule swallowed it, so the tripwire stayed green through a lineup
    change (2026-09-05). Only a dated snapshot (-YYYYMMDD) or a bracketed
    context-window variant ([1m]) is the same model as its api_string."""
    api = {'claude-fable-5', 'claude-opus-5'}
    alias = {'fable', 'opus'}
    for same in ('claude-opus-5-20260115', 'claude-opus-5[1m]', 'claude-opus-5-20260115[1m]'):
        assert lc.is_known(same, api, alias), same
    for other in (
        'claude-fable-5-1',
        'claude-opus-5-1',
        'claude-opus-5-1-20261001',
        'claude-opus-50',
        'claude-opus-5-turbo',
    ):
        assert not lc.is_known(other, api, alias), f'{other} passed as a variant'


def test_absent_model_reddens_and_names_the_refresh_command():
    """The tripwire, made to fire on purpose. It was prose the reader had to
    perform by hand, so it fired by luck; this is the same rule as a command."""
    rc, out = _run(['claude-opus-4-8'])
    assert rc == 1, 'a retired model passed the lineup check'
    assert 'claude-opus-4-8' in out
    assert '/refresh-models' in out
    out.encode('ascii')  # hook/console safe


def test_nothing_to_check_is_not_a_finding():
    import os

    saved = os.environ.pop(lc.MODEL_ENV, None)
    try:
        assert _run([])[0] == 0
    finally:
        if saved is not None:
            os.environ[lc.MODEL_ENV] = saved


def test_env_fallback():
    import os

    saved = os.environ.get(lc.MODEL_ENV)
    os.environ[lc.MODEL_ENV] = 'not-a-real-model'
    try:
        rc, out = _run([])
        assert rc == 1 and 'not-a-real-model' in out
    finally:
        if saved is None:
            os.environ.pop(lc.MODEL_ENV, None)
        else:
            os.environ[lc.MODEL_ENV] = saved


def main() -> int:
    test_reads_the_real_tier_data()
    test_every_shipped_api_string_and_alias_passes()
    test_dated_snapshot_and_context_variant_pass()
    test_a_dotted_successor_is_not_a_variant_of_its_predecessor()
    test_absent_model_reddens_and_names_the_refresh_command()
    test_nothing_to_check_is_not_a_finding()
    test_env_fallback()
    print('ok: lineup_check')
    return 0


if __name__ == '__main__':
    sys.exit(main())

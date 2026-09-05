#!/usr/bin/env python3
"""Is the model this session is running on present in the tier data?

    lineup_check.py <model-id> [...]      # explicit ids
    lineup_check.py                       # falls back to $ANTHROPIC_MODEL

The environment tripwire the choosing-models freshness loop already described --
"when the session's lineup names a model the tier table does not, refresh before
trusting it" -- was prose the reader had to perform by hand, so it fired by luck.
Four recurrences cost nothing only because dispatch emits family aliases, which
insulated it; that is exactly why nobody fixed it. This is the same rule as a
command: exit 1 and print one line naming the absent model and the refresh
command.

A harness id is not always an API string: a dated snapshot
(`claude-opus-5-20260115`) and a context-window variant (`claude-opus-5[1m]`) are
the same model. An id matches when it equals an api_string, equals a
harness_alias, or is an api_string plus exactly those suffixes. Nothing looser:
the bare-prefix rule this replaced read `claude-fable-5-1` as a variant of
`claude-fable-5` and returned 0 across a lineup change (2026-09-05).

Stdlib only, no TOML parser needed (the file is flat enough to read with a
regex, and this has to run wherever the skill is installed). ASCII output.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

MODELS_TOML = Path(__file__).resolve().parent.parent / 'models.toml'
MODEL_ENV = 'ANTHROPIC_MODEL'
_FIELD = re.compile(r"^(api_string|harness_alias)\s*=\s*'([^']+)'", re.MULTILINE)
_VARIANT = re.compile(r'\[[^\]]+\]$')  # context-window variant: `[1m]`
_SNAPSHOT = re.compile(r'-\d{8}$')  # dated snapshot: `-YYYYMMDD`


def known_ids(models_toml: Path = MODELS_TOML) -> tuple[set[str], set[str]]:
    """(api_strings, harness_aliases) declared in the tier data."""
    try:
        text = models_toml.read_text(encoding='utf-8')
    except OSError:
        return set(), set()
    api = {v for k, v in _FIELD.findall(text) if k == 'api_string'}
    alias = {v for k, v in _FIELD.findall(text) if k == 'harness_alias'}
    return api, alias


def is_known(model_id: str, api: set[str], alias: set[str]) -> bool:
    """A dated snapshot (`-YYYYMMDD`) or a context-window variant (`[1m]`) of an
    api_string is the same model -- otherwise the check fires on every snapshot
    and gets muted, which is the failure mode it exists to prevent. Only those
    two suffixes count: a dotted successor (`claude-fable-5-1` next to
    `claude-fable-5`) is a new model, and a bare prefix match let it through."""
    mid = model_id.strip().lower()
    if not mid:
        return True  # nothing to check is not a finding
    known = {a.lower() for a in api}
    if mid in known or mid in {a.lower() for a in alias}:
        return True
    base = _SNAPSHOT.sub('', _VARIANT.sub('', mid, count=1), count=1)
    return base != mid and base in known


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ids = [a for a in argv if a and not a.startswith('-')]
    if not ids:
        env = os.environ.get(MODEL_ENV, '').strip()
        ids = [env] if env else []
    if not ids:
        print(f'lineup check: no model id given and {MODEL_ENV} is unset; nothing to check')
        return 0
    api, alias = known_ids()
    if not api:
        print(f'lineup check: could not read the tier data at {MODELS_TOML}')
        return 1
    missing = [m for m in ids if not is_known(m, api, alias)]
    if not missing:
        return 0
    for m in missing:
        print(
            f'lineup drift: {m} is not in the choosing-models tier data '
            f'({MODELS_TOML}). Run /refresh-models before trusting a tier '
            f'assignment. Known: {", ".join(sorted(api))}'
        )
    return 1


if __name__ == '__main__':
    sys.exit(main())

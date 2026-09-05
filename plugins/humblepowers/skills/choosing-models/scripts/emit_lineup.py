#!/usr/bin/env python3
"""Emit the resolved lineup for pasting into an execution artefact.

    emit_lineup.py --format model --tier strong    # a [governance] line
    emit_lineup.py --format alias --tier weak      # the Agent / agent() word
    emit_lineup.py --format table                  # a [governance.tier_models] block

The tier data lives here and the engines that run the work live in other
repositories, which cannot import it and should not: an engine has to install
and run for a stranger who never heard of this collection. So the coupling goes
through the only object that already crosses the boundary -- the artefact of the
run. Authoring resolves the tier against this file and writes the ANSWER into
the series file; the engine reads its own artefact and consults no mirror.

That is why a lineup change stops being a synchronisation problem: the copy
inside an engine is a dated floor that announces itself when consulted, not the
thing that decides a run.

Two dates travel with every emission. ``resolved`` is when this block was made;
``last_reviewed`` is how old the SOURCE was at that moment. A consumer ages the
artefact by the OLDER of the two -- a fresh emission off a stale table is stale,
and reporting only the first would hide exactly that.

Thresholds are never emitted. They are calibratable routing policy, not lineup:
a run carrying a cut nobody calibrated for it would be worse than a run that
carries none.

Stdlib only, ASCII out, no default date baked in beyond today -- so a test can
pin one and the output stays reproducible.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

MODELS_TOML = Path(__file__).resolve().parent.parent / 'models.toml'
STAMP = 'lineup synced'
FORMATS = ('model', 'alias', 'table')

_BLOCK = re.compile(r"^(tier|api_string|harness_alias|available)\s*=\s*(?:'([^']*)'|(\S+))", re.M)
_REVIEWED = re.compile(r'^last_reviewed\s*=\s*"([^"]+)"', re.M)


def read_lineup(models_toml: Path = MODELS_TOML) -> tuple[dict[str, tuple[str, str]], str]:
    """``({tier: (api_string, harness_alias)}, last_reviewed)`` from the tier data.

    Regex rather than ``tomllib``, matching the sibling ``lineup_check.py``: the
    rows are flat, and this has to run wherever the skill is installed.
    """
    text = models_toml.read_text(encoding='utf-8')
    lineup: dict[str, tuple[str, str]] = {}
    for chunk in text.split('[[models]]')[1:]:
        fields = {k: (q or bare) for k, q, bare in _BLOCK.findall(chunk)}
        if fields.get('available') == 'false':
            continue
        tier, api, alias = fields.get('tier'), fields.get('api_string'), fields.get('harness_alias')
        if tier and api and alias:
            lineup[tier] = (api, alias)
    reviewed = _REVIEWED.search(text)
    return lineup, reviewed.group(1) if reviewed else 'unknown'


def provenance(reviewed: str, resolved_on: str) -> str:
    """The one comment line every emission carries, in both directions."""
    return (
        f'# choosing-models: {STAMP} {reviewed} '
        f'(resolved {resolved_on} from models.toml last_reviewed {reviewed}). '
        'Age this by the older date.'
    )


def render(
    fmt: str, tier: str | None, lineup: dict[str, tuple[str, str]], reviewed: str, resolved_on: str
) -> list[str]:
    """The lines to print, provenance first."""
    head = provenance(reviewed, resolved_on)
    if fmt == 'table':
        rows = [f'{t} = "{api}"' for t, (api, _) in lineup.items()]
        return [head, '[governance.tier_models]', *rows]
    api, alias = lineup[str(tier)]
    if fmt == 'alias':
        return [head, alias]
    return [head, f'model = "{api}"']


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Emit the resolved lineup for an artefact')
    ap.add_argument('--format', default='model', choices=FORMATS)
    ap.add_argument('--tier', default=None, help='required for --format model and alias')
    ap.add_argument('--resolved-on', default=None, help='emission date (default: today)')
    ap.add_argument('--models-toml', default=None, help='override the tier data path')
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    path = Path(args.models_toml) if args.models_toml else MODELS_TOML
    try:
        lineup, reviewed = read_lineup(path)
    except OSError:
        print(f'emit-lineup: could not read the tier data at {path}')
        return 1
    if not lineup:
        print(f'emit-lineup: no available models parsed from {path}')
        return 1

    if args.format != 'table':
        if not args.tier:
            print(f'emit-lineup: --format {args.format} needs --tier; known: {", ".join(lineup)}')
            return 1
        if args.tier not in lineup:
            print(f'emit-lineup: unknown tier {args.tier!r}; known tiers: {", ".join(lineup)}')
            return 1

    resolved_on = args.resolved_on or datetime.date.today().isoformat()
    for line in render(args.format, args.tier, lineup, reviewed, resolved_on):
        print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())

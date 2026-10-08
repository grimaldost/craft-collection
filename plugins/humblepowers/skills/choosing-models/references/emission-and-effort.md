# Effort defaults, emission surfaces, and the staleness tripwires

Lookup material, not decision material. The body owns the procedure, the context
modifiers and the boundaries; this file is what you read once while writing the
tier out, or when a table stops being trustworthy.

## Effort defaults

Defaults, not calibrated thresholds: **`high`** unless a row below applies.

| Work | Effort |
|---|---|
| mechanical, tightly scoped | `low`-`medium` |
| hard agentic or coding work | `xhigh` |
| correctness dominates cost | `max` |

Whether effort changes a weak-tier run is unmeasured on Haiku 5.5. Its predecessor
Haiku 4.5 accepted the flag and ignored it (measured 2026-09-13 on the CLI and on
governed spawns); emit the level anyway, and do not lean on it until a measurement
of the current model says what it does.

The "mechanical, tightly scoped" row does not cover work whose correctness is agreement
between two independent statements of one rule: two readers of one domain rule, a pin
and its vocabulary, a docstring promise and its binding, a mirror and its source. That
work keeps the `high` default at any tier and any diff size. Six tasks in two lots of
one programme took 2-3 fix rounds at `medium` on both tiers where the obligation
applied, and 1 at `high` (the table is in `models.toml`, `[meta].effort_observations`).

Since Claude Code 2.1.292 (2026-10-06) the Agent tool takes an `effort` parameter;
pass it with `model`. A spawn that omits it, or runs on an older harness, inherits the
session's setting. Say so rather than pretending a value was set, and count the effort
of such a spawn as inherited, not chosen: in one 2026-09-26 measure, before the
parameter existed, 110 of 127 Agent spawns inherited `xhigh` or `max`, 46 of them
sonnet. Where a request goes to the platform directly (a series file, direct API
tooling), an omitted `effort` takes the MODEL's default, and the strong tier's model (Opus 5.5) defaults to
`medium`, one level below its predecessor and below this table's default - emit the
level. A workflow `agent()` that omits it inherits the session's effort instead.

## Emission surfaces

Tier names are not shared across surfaces — emit each surface's own words:

| Surface | Emits | Vocabulary |
|---|---|---|
| series-file governance (e.g. convoy) | `tier` or `model`, plus `effort` | `weak/mid/strong/frontier` or API string |
| Agent-tool spawn | `model` + `effort` | family alias (`haiku/sonnet/opus/fable`) + effort level |
| workflow `agent()` | `model` + `effort` | family alias + effort level |
| planning-tool per-PR tier (e.g. keel) | tier per task | family names — translate, don't assume |
| direct API tooling | model id | undated API string |

A workflow `agent()` with no `model` inherits the session model, possibly the
frontier one; no engine-level cap exists, so under a tier cap every call carries
an explicit `model`.

While an engine is series-global (no per-task keys): score every task anyway, set
the series tier to the modal tier, and consider splitting at a tier boundary when
the spread is two or more tiers. Splitting buys tier fit at coordination cost;
sometimes accepting the overpay is right.

## Staleness tripwires

- **Age (always fires).** `models.toml` carries `review_by`. Past that date,
  offer `/refresh-models` before trusting the table.
- **Environment (partial).** `scripts/lineup_check.py <model id>` exits 1 when
  the session's own model is not in `models.toml` — run it rather than checking
  by hand. It cannot see a model the session is not running on; the age check is
  what covers that gap.

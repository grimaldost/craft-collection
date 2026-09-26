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

The lower and upper rows both apply from mid up — the weak tier has no effort
knob at all.

A surface with no effort knob (the Agent tool today) inherits the session's
setting. Say so rather than pretending a value was set. An omitted `effort` is not
`high` everywhere: the strong tier's model (Opus 5.5) defaults to `medium`, one level
below its predecessor, so an `agent()` call that leaves effort out now runs lower than
this table's default - emit the level.

## Emission surfaces

Tier names are not shared across surfaces — emit each surface's own words:

| Surface | Emits | Vocabulary |
|---|---|---|
| series-file governance (e.g. convoy) | `tier` or `model`, plus `effort` | `weak/mid/strong/frontier` or API string |
| Agent-tool spawn | `model` | family alias (`haiku/sonnet/opus/fable`) |
| workflow `agent()` | `model` + `effort` | family alias + effort level |
| planning-tool per-PR tier (e.g. keel) | tier per task | family names — translate, don't assume |
| direct API tooling | model id | undated API string |

A workflow `agent()` with no `model` inherits the session model, possibly the
frontier one; no engine-level cap exists, so under a tier cap every call carries
an explicit `model`. The PreToolUse spawn hint fires on exactly that shape — a
spawn with no `model` — and says nothing once one is passed: directly, through a
const, or through a spread of a call that builds the options (`{ ...route(id) }`,
the shape a scored batch emits).

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

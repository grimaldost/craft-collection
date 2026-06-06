# Binding to a target store (optional)

This skill is **store-agnostic by default**: it emits a generic envelope with a
placeholder `author` and example `area` values, and any structured store can ingest
it. But `area` and `author` are not cosmetic — in a typical structured store they are
**scope and partition keys**: retrieval filters by `author`, and consolidation runs
**author + area-scoped**. So when you journal *into a specific existing store*, those
values must match that store's **existing vocabulary**, or the entry ingests without
error and is then **silently orphaned** — filed under a scope no consolidation pass
over the real corpus will ever see, or hidden in the wrong author partition. Both
failures are silent: nothing errors, the entry just never clusters with the corpus it
belongs to.

The fix is an optional **`target_store` profile** the host or user supplies. It is the
*only* thing that turns on store-aware behavior; absent it, output is exactly the
generic default. You are **given** the profile — stated inline in the conversation, or
by being pointed at a file that holds it. Do not hunt for it at a hardcoded path and
do not invent one; that would couple this skill to a single store's conventions, which
it must never do.

## Profile shape

```yaml
target_store:                       # optional; absent ⇒ generic behavior, unchanged
  author: user:grimaldo-stanzani    # canonical author id for this store — use verbatim
  areas: [mantis_engineering, treasuryutils_development]   # existing area vocabulary to REUSE
  allowed_types:   [decision, finding, observation, tradeoff, hypothesis, contradiction, connection, pattern, anti_pattern]  # optional — the enum the store strict-parses
  allowed_origins: [chat, code, meeting, reading]          # optional
  required_fields: [type, author, timestamp, area, language, origin, session]  # optional
```

Only `author` and `areas` are load-bearing — they are what prevent silent orphaning.
The rest are optional validators that catch a value a strict-parsing store would drop.

## Behavior when a profile IS present

- **`author`** — set every entry's `author` from the profile, verbatim. Do not invent
  or placeholder one.
- **`area`** — constrain to `areas`. Pick the **closest existing value**. The match is
  exact, not fuzzy, so a near-miss area is as orphaned as a wrong one — when nothing
  fits, that is a real signal. Only mint a new area when the work genuinely belongs to
  no existing scope, and when you do, **flag it explicitly** in your closing summary
  ("created a new area `X` — confirm it belongs") so the operator can confirm it rather
  than discover an orphan later.
- **`allowed_types` / `allowed_origins`** (if given) — keep every emitted `type` /
  `origin` within them. A store that strict-parses enums **silently drops** an entry
  with an out-of-set value, so this is a hard constraint, not a preference. Match
  **case** too (see the enum subset rule in `output-format.md` §1).
- **`required_fields`** (if given) — never omit one; a store typically **silently
  skips** an entry missing a required field. The skill already always emits the
  standard seven (`type, author, timestamp, area, language, origin, session`), so this
  is a backstop, not new work.
- **The envelope is mandatory** — a profile means there is a store downstream, so never
  take the prose-only branch (see SKILL.md "Output").

## Behavior when a profile is ABSENT

Exactly today's generic behavior: placeholder `author`, example `area` values, no
constraint beyond the documented field set. Nothing about store binding applies. This
is the default and must stay byte-for-byte unchanged.

## Example — an entry written *with* the profile above

Note the bound `author` (`user:grimaldo-stanzani`, not a placeholder), an `area` drawn
from the profile's vocabulary (`mantis_engineering`, not the generic
`platform_engineering` example), and `validated: true` alongside the in-prose
VALIDATED marker:

```
--- ENTRY_START ---
type: DECISION
author: user:grimaldo-stanzani
timestamp: 2026-06-06T18:20:00Z
area: mantis_engineering
language: en
origin: chat
visibility: private
session: journal-envelope-store-binding
domains: memory_systems, ingestion, schema_design
entities: mantis, journaling-sessions
confidence: 0.85
validated: true
summary: Bind the journal envelope's author/area to the target store's existing vocabulary, because consolidation is author+area-scoped and a novel area silently orphans the entry.
--- CONTENT ---
Decided that when journaling into mantis, `area` must be drawn from mantis's existing
area vocabulary (here `mantis_engineering`) rather than the skill's generic
`platform_engineering` example. The reason is concrete: mantis runs consolidation
author+area-scoped, so an entry filed under a novel area ingests cleanly but is never
seen by a consolidation pass over the real corpus — it is silently orphaned from the
cluster it belongs to. Rejected letting the skill mint a fresh area per session, which
maximises orphaning. VALIDATED: survived questioning on whether a generic area is
"close enough" — it is not, because the join key is exact-match, not fuzzy, so a
near-miss area is as orphaned as a wrong one.
--- ENTRY_END ---
```

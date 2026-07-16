# series.toml skeleton (with wave budget)

The full `series.toml` schema is owned by the series orchestrator — see your
orchestrator's schema reference; this skeleton does not restate it. The minimal
contract the method reads is what the skeleton shows: each `[[pr]]` carries
`id`, `prompt`, `section` (the spec section it implements), and `tier`, plus the
**`[budget]` block** (Upgrade 4): a wave-level forecast and a drift gate,
extending per-PR scoring to the whole wave. Without an orchestrator, the
skeleton still serves as the series' manual checklist.

```toml
[series]
id = "<series-name>"
integration_branch = "refactor/<topic>-consolidation"

# Per-PR definitions: each cites exactly one spec section (see the PR↔section
# manifest in the spec). Model tier comes from the complexity score — unless a
# capacity-dispatch policy is bound (method-bindings.md), whose tier rule wins.
[[pr]]
id = "PR01"
prompt = "PR01_task.md"
section = "§1"          # traceability: spec section this PR implements
tier = "haiku"          # model-family name — see "Tier vocabulary" below

[[pr]]
id = "PR02"
prompt = "PR02_task.md"
section = "§2"
tier = "sonnet"

# --- Upgrade 4: wave budget + drift gate -------------------------------------
[budget]
estimate_usd = 26.00          # Σ per-PR tier cost estimates
all_opus_baseline_usd = 41.00 # same series if every PR ran on Opus (cost framing)
drift_threshold = 0.25        # flag if cumulative actual exceeds estimate by >25%
on_breach = "warn"            # "warn" (log + continue) | "block" (stop the wave)
```

## Tier vocabulary

Tiers here are **model-family names** (`haiku`, `sonnet`, ...) — the method's own words,
deliberately not any one orchestrator's. An orchestrator may use a different tier vocabulary,
and may take a tier per PR or only one per series; translating these names to it, and deciding
where the tier is set, belongs to the orchestrator binding in `method-bindings.md` — not to this
skeleton, which does not restate an orchestrator's schema. Keep the family names literal: a bound
capacity-dispatch policy greps them when its model lineup changes.

## Drift-check convention

A post-PR hook sums actual cost so far and compares to `estimate_usd`. If
`actual > estimate * (1 + drift_threshold)`, it fires `on_breach`. This catches a
wave quietly blowing past its forecast — the wave-level analogue of a PR that
won't score.

*(The hook itself is wired during "apply"; this skeleton defines the contract it
reads.)*

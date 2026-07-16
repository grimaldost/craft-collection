# Method toolkit

The portable kit that operationalizes the method (see the keel doctrine). Copy these
into a new project and fill `method-bindings.md`. The kit embodies the method
*and* its upgrade set.

## Portability slots → files

The method (§7) needs five slots filled in any project. Each maps to a template:

| Slot | Template | Notes |
|---|---|---|
| ADR home | `adr-template.md` | one numbered file per decision |
| Spec format | `spec-template.md` | numbered sections; DoR-ready by construction |
| Guardrails + gate commands | `definition-of-done.md` | the exit-of-review gate |
| Review checklist | `review-checklist.md` | also the promotion target for reflection triage |
| Reflection sink | `reflection-triage.md` | closes the loop (Upgrade 3) |

## Upgrade artifacts (the upgrade set)

| Upgrade | Template |
|---|---|
| DoR gate | `definition-of-ready.md` |
| Pre-mortem | `pre-mortem-prompt.md` |
| Close the loop | `reflection-triage.md` |
| Wave budget | `series-toml-skeleton.md` (`[budget]` block) |
| Portability | `method-bindings.md` |

## Using the kit in a new project

1. Copy `adr-template.md`, `spec-template.md`, the two gate checklists, and
   `review-checklist.md` into the project's docs.
2. Fill `method-bindings.md` — bind each slot to a concrete mechanism (CI command,
   script, agent).
3. Wire the gates: DoR before decomposition, DoD before merge.
4. The `apply-method` skill (in the keel plugin) walks an agent through this.

Source of truth for orchestration (`series.toml`, hooks, scoring) stays with
your series orchestrator (e.g. pr-pilot) — these templates link to it, they
don't restate it. Without an orchestrator, the templates still work as manual
checklists.

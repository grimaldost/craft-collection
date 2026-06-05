---
name: consolidate-knowledge
description: Use when a body of captured journal entries from many sessions should be distilled into durable, higher-level guidance — cluster related entries, synthesize the one generalization each cluster supports, promote only the reinforced and specific ones into long-lived guidance, and reconcile supersession when newer evidence overrides older. Triggers on "consolidate my journals", "what patterns emerged across these sessions", "distill these notes into guidance", "what have we learned over time", "promote the durable insights", "synthesize my entries into wisdom", or running "/consolidate-knowledge". This is the downstream pass that journaling-sessions feeds — journaling captures raw entries one session at a time, this consolidates many of them across sessions. Not for capturing a single session (use journaling-sessions), not for a one-off summary, and distinct from consolidating your agent memory files.
user-invocable: true
---

# Consolidate Knowledge

Distill a corpus of raw journal entries into **durable, higher-level guidance** — the
pass that turns many specific captures into a few reinforced generalizations.
`journaling-sessions` produces the raw input (one idea per entry, reasoning inline,
anti-patterns hunted); this clusters those entries and promotes the patterns that have
earned it. The bar is not "summarize the journals" but: *a future session, retrieving
this cold, gets a generalization it can act on that no single entry stated — and that
the base model would not have volunteered.*

## The pipeline — run in order

1. **Gather** the entries in scope — by area, by date range, or the whole corpus. Read
   them; do not work from titles.
2. **Cluster** related entries. Entries about the same mechanism, decision, or failure
   mode across different sessions belong together. The cluster is the unit of
   consolidation; a singleton is usually not yet promotable (see the gate).
3. **Synthesize one generalization per cluster.** What durable pattern do these entries
   jointly support that none states alone? Name it concretely, cite the entries it
   rests on, and keep the specificity that made them valuable — a generalization that
   drops the names and numbers is a platitude.
4. **Apply the promotion gate** (below). Promote only what has earned it; leave the
   rest as raw entries to revisit when more evidence arrives.
5. **Reconcile supersession.** If a cluster contradicts already-promoted guidance, the
   newer evidence wins: write the updated guidance, mark it as superseding the prior,
   and state what changed and why. Never leave two equally-confident contradictory
   claims in the store.
6. **Emit** the promoted guidance entries (format below), each linking back to the
   source entries it generalizes — so the chain from raw capture to durable guidance
   stays traceable.

## The promotion gate — what earns "durable"

Promote a generalization only if ALL of these hold; otherwise leave the entries raw:

- **Reinforced** — supported by multiple entries, ideally across more than one session.
  A pattern seen once is a hypothesis, not guidance.
- **Specific** — carries a concrete anchor (a named mechanism, a number, a condition, a
  tool or version) that makes it checkable. Strip the anchor and you have a fortune
  cookie; do not promote it.
- **Non-reconstructable** — a fresh expert model would not already volunteer it. If it
  is generic best practice, the corpus does not need to remember it.
- **Actionable** — it changes what a future session would *do*, not just what it knows.

Most clusters do not pass on the first pass. **Under-promoting is safe; over-promoting
pollutes the durable layer** with noise that every later consolidation must then fight.

## Anti-patterns — hunt these

- **Over-generalizing from one entry** — a single observation promoted as a law.
- **Platitude promotion** — "test your code", "communicate clearly": true, useless,
  already known. The specificity and non-reconstructable checks exist to kill these.
- **Losing the scar** — the source entries are vivid because they carry the specific
  failure; a consolidation that abstracts away the `69,449 → 31,032` keeps the shape
  and loses the teeth. Generalize the lesson, keep the evidence.
- **Silent contradiction** — promoting an insight that conflicts with a prior one
  without marking the supersession.

## Output format

Emit each promoted insight as a durable-guidance entry — broader scope and higher
confidence than a journal entry, and explicitly derived:

```
--- GUIDANCE_START ---
scope: <the area / domain it governs>
confidence: <0.0-1.0 — promoted insights start higher than a single journal entry, but
  a generalization is only as strong as its weakest supporting cluster>
derived_from: <the source entry ids / sessions this generalizes over>
supersedes: <optional — a prior guidance id this replaces, and what changed>
--- CONTENT ---
<the generalization, stated concretely with its anchors and the condition under which
it applies. One durable idea.>
--- GUIDANCE_END ---
```

No downstream store? Emit the CONTENT prose and skip the envelope — keep the discipline
(one anchored, derived generalization per entry, supersession marked); drop only the
ceremony.

## Relationship to journaling-sessions

`journaling-sessions` = capture: raw, per-session, tuned for recall. This = consolidate:
distilled, cross-session, tuned for precision. Run journaling often; run this
periodically, once a corpus has accumulated. Do **not** consolidate a single session's
entries — there is nothing to generalize across yet; just journal it.

# Running a panel — mechanism and harness

## Why one reviewer is the default

Level 1, one reviewer subagent that did not see the session and is briefed to refute, is the default rung; the panel machinery (several lenses, a Workflow script, a barrier and a verify stage) is for stakes that justify its cost. The evidence: arXiv:2603.12123 v2 (2026-10-01), "Cross-Context Review: Improving LLM Output Quality by Separating Production and Review Sessions", reports that cross-context review is not significantly ahead of context-aware subagent review (p = 0.057), and that the advantages v1 reported over subagent review and over single same-session review came from its first run alone. So the cheap rung is one subagent reviewer; more lenses and a fully separate session are a cost to justify, not a default.

## Reasoning effort and lens routing

Level 3: drive the lenses through the Workflow tool — `agent(prompt, {effort, schema})` per lens — which buys schema-forced, mechanically comparable output and the whole panel in one script. Per-lens effort no longer needs it: since Claude Code 2.1.292 the Agent tool takes an `effort` parameter, so concurrent Agent calls (the Levels 1–2 mechanism) can pass model and effort per lens. If the Workflow tool is not available in the session, fall back to concurrent Agent calls, accepting the loss of schema-forced output.

**Selection and capping.** Sort serious findings by severity, then round-robin across lenses, then cap; log() the dropped finding ids with their lens.

## Barrier and verify flow

When a verify stage follows the lenses, collect the findings in a barrier before it — a pipeline that drops a finding on a verifier's error loses a real finding to a coarse failure, not to a refutation. The barrier also dedupes before the verify stage, by (file, line ±5) or (file, first four title words).

## Persisting raw output (step 6)

**When the panel is a script, persisting raw output before synthesis is a stage in the harness, not a step for its operator** — write inside the stage that produces the output. Read as an operator's step it gets implemented as nothing: one panel script persisted no verdicts, and a dead synthesis would have taken a seven-agent corpus with it.

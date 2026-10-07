# Running a panel — mechanism and harness

## Reasoning effort and lens routing

Level 3, or any panel that needs per-lens reasoning-effort control: drive the lenses through the Workflow tool — `agent(prompt, {effort, schema})` per lens — which buys what the Agent tool does not expose: reasoning-effort control and schema-forced, mechanically comparable output. If the Workflow tool is not available in the session, fall back to the Levels 1–2 mechanism (concurrent Agent calls), accepting the loss of per-lens effort control.

**Selection and capping.** Sort serious findings by severity, then round-robin across lenses, then cap; log() the dropped finding ids with their lens.

## Barrier and verify flow

When a verify stage follows the lenses, collect the findings in a barrier before it — a pipeline that drops a finding on a verifier's error loses a real finding to a coarse failure, not to a refutation. The barrier also dedupes before the verify stage, by (file, line ±5) or (file, first four title words).

## Persisting raw output (step 6)

**When the panel is a script, persisting raw output before synthesis is a stage in the harness, not a step for its operator** — write inside the stage that produces the output. Read as an operator's step it gets implemented as nothing: one panel script persisted no verdicts, and a dead synthesis would have taken a seven-agent corpus with it.

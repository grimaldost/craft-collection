---
name: data-engineering-discipline
description: >
  Discipline guardrails for data-engineering work with downstream consumers —
  activate at the START of the task, before writing code, because silent
  semantic drift is the dominant risk. Activate on: migrating or porting a
  pipeline (e.g. "migrate this Spark pipeline to the new warehouse"),
  refactoring a transform, backfilling or replaying history, evolving a schema
  (add / rename / retype / drop a column), creating a new dataset that has
  consumers, designing or reviewing a data contract, writing tests for a
  pipeline, generating pipeline code with an LLM, and investigating a consumed
  dataset that misbehaves — "the numbers changed / look different", or a
  table/extract that "ran but didn't update / is stale / isn't refreshing / the
  watermark didn't advance". The test for activation:
  could this change the columns, dtypes, row or group cardinality, null
  behavior, semantics, or freshness of a dataset that something or someone
  else reads? If so, this skill applies — pin the contract, verify the
  observable source, and check parity on real data. Do NOT activate for pure
  exploratory analysis with no downstream consumer, throwaway notebooks, or
  non-data software work.
---

# Data Engineering Discipline

The output of a data pipeline is a contract. Columns, dtypes, row
cardinality, null behavior, group cardinality, and semantics are all part
of that contract, whether anyone wrote it down or not. This skill defends
against **silent breakage** — output that compiles, runs, and looks
plausible, but no longer means what consumers think it means. Every
principle in this skill exists because one of those guarantees has
historically been broken in a way that cost real money or real trust.

This skill is scenario-agnostic. The same discipline applies to migrating
a pipeline, creating a new one, refactoring an existing one, evolving a
schema, backfilling history, designing incremental loads, and
investigating downstream regressions. The specifics change; the
non-negotiables do not.

## When to invoke

Activate on any task where downstream consumers might be affected:

- Creating a new dataset that will have at least one consumer beyond
  yourself.
- Migrating a pipeline between frameworks, stacks, or warehouses.
- Refactoring transforms while preserving the produced dataset.
- Evolving the schema of an existing dataset (add, remove, rename,
  retype, re-semanticize a column).
- Backfilling history or designing replay logic.
- Designing incremental or streaming loads (watermarks, late-arriving
  data).
- Writing tests for a data pipeline.
- Investigating "the numbers look different" reports — or a consumed dataset
  that ran but didn't update / is stale / isn't refreshing / the watermark
  didn't advance.
- Generating data-pipeline code with an LLM where semantics matter.
- Designing or reviewing a data contract.

Do **not** activate for one-off exploratory analysis with no downstream
consumer, throwaway notebooks, or software-engineering tasks unrelated to
data outputs.

## The four non-negotiables

These four beliefs are the source from which every principle in this
skill derives. They are scenario-agnostic by design: the specifics of
how each one applies differ between migration, refactor, new dataset,
schema evolution, and other scenarios, but the axiom itself does not.
If a recommendation in any other file conflicts with these, these win.

### 1. The output is the contract

What downstream depends on — schema, dtypes, row cardinality, group
cardinality, null behavior, semantics — is the producer's commitment to
consumers, named or not. Changes to any of these are breaking changes by
default.

The contract exists whether or not it's written down. For a brand-new
dataset, the contract is what you commit to when the first consumer
integrates. For an existing dataset, the contract is what consumers
have observed and depend on. The producer's job is to identify,
declare, and protect the contract.

### 2. The source of truth is observable, not inferred

Verify against code, materialized data, library signatures, and
registries — not against priors, plans, conversation summaries, or
intuitions about how things "should" work. The world is full of
exceptions to "should."

Concretely, this means:

- For an existing pipeline: read the source code end-to-end and inspect
  the materialized output. Don't trust your summary of either — and
  confirm the source you read is the code that *runs*: resolve the
  imported module's `__file__` and installed version first, because an
  editable checkout and an installed release of the same library diverge
  silently (reading a non-executing copy is inference, not observation).
  `systematic-debugging` owns the debug-time form of this check.
- For an unfamiliar library: run `inspect.signature(fn)` or read the
  docstring. Don't trust your memory of the signature.
- For a string identifier (calendar name, source name, schema name):
  enumerate the registry. Don't trust your guess at what it's called.
- For source data feeding a new pipeline: sample and inspect it.
  Don't trust the upstream documentation.
- For a long session: re-read the primary sources at each phase.
  Don't trust the session summary.

**A producer can look verified and still mislead** — four sharper sub-cases,
consolidated here so other files point to this set rather than re-stating it:

| The trap | The check |
|----------|-----------|
| A reused producer is public, tested, and correctly called — yet reads the **wrong layer/version** of state (a pre-overlay config where the merged one was meant). | Verify *which* layer/version it returns, not just that it exists and is called. |
| You build on a producer **behavior the code doesn't deliver** — a read path bypasses the layer you assume. | Run it and observe the behavior; don't infer it from the call site. |
| A classifier/heuristic's **verdict** is wrong while its **reasons** are diagnostic. | Read the reasons, not the boolean. |
| A design is frozen on a **paper-defined subgroup/corpus** whose real size or purity was never measured. | Measure it on the real data before committing the design to it. |

If this set recurs *after* this consolidation, it is judgment-bound with no
mechanical reach — sharpen an example or decline it; do not add a sixth row.

This axiom replaces the migration-specific framing of "legacy is the
source of truth" with the universal observation that an LLM (or a
hurried human) will reach for inference when verification is available
at low cost. The defense is mechanical: make verification the default
first step, not an optional one.

### 3. Real data finds what synthetic fixtures cannot

Unit tests with synthetic fixtures are necessary but never sufficient.
The first staging run on production-shaped data is where reality
lives. Every declared constraint — nullability, value ranges, enum
membership, uniqueness — must survive that contact.

This applies symmetrically across scenarios:

- For a new pipeline: validate constraints against real source data
  before declaring them.
- For a migration or refactor: run end-to-end on production-shaped
  data before declaring parity.
- For schema evolution: confirm new constraints hold against the last
  90 days of production.
- For a framework: smoke-test each backend the framework claims to
  support against a real but small dataset.

The trap is the same in every case: the LLM (or the developer)
generates both the code and the fixtures that satisfy it. Real data
has edge cases neither party anticipated.

### 4. All change is intentional and traceable

Silent drift is the failure mode. Every divergence is documented;
every breaking change is announced; every "improvement" has a named
scope and approval. The discipline is the same whether you're
preserving an existing contract or evolving it — the difference is
just what's being protected.

By scenario:

- For migration: bug-for-bug parity is the cutover criterion;
  divergences are explicit in `MIGRATION_NOTES.md` with sign-off.
- For refactor: no semantic changes during the refactor; any
  legitimately-needed semantic change is a separate PR.
- For new dataset: the declared contract is the spec; output matches
  contract; contract evolves only through versioning.
- For schema evolution: deprecation cycles with named end dates;
  consumer notifications recorded; never silent rename or drop.
- For backfill: replay produces the same output as a fresh
  full-recompute; divergence is a bug to fix, not a feature to ship.
- For investigation: fix the producer and replay; never "fix forward"
  the data, which leaves the producer broken and history
  inconsistent.

The corrective in every case is the same: make the change scope
explicit, document it, and verify the result. The mechanical defenses
that enforce this — parity diffs, schema-diff in CI, contract
enforcement, `MIGRATION_NOTES.md` artifacts — are detailed in the
references.

## Make the discipline visible in your output

Apply the discipline *visibly* — silent correctness is indistinguishable from a
plausible guess, and a reviewer can only trust what they can see. As you work:

1. **Pin the contract first** — state the schema / dtypes / grain / cardinality /
   null behavior and known quirks you're protecting, and that changes to them are
   breaking by default for the named consumers — before writing code.
2. **Name the non-negotiable you're invoking** as you apply it, so a reader can
   audit which principle each step serves.
3. **Insist on reading the observable source** even when handed a diff, summary, or
   description; never diagnose or migrate from the diff text alone.
4. **Propose the verification gates** that must pass before "done"; for any fix,
   **repair the producer and replay** rather than patching the data forward.

## LLM failure modes — quick warning

This skill is consumed by an LLM workflow. LLMs introduce specific
failure modes that mechanical discipline must defend against. The
dominant pattern is **plausible-but-wrong code**: output that compiles,
runs, and produces believable numbers while silently changing meaning.
Other recurring modes:

- **Inference instead of verification** — the agent reasons about what
  the code/signature/identifier should be rather than reading it — or
  reads the *wrong copy* (an editable checkout while the venv runs the
  installed release), so the read isn't the code that ran.
- **Plan drift** — the conversational summary becomes the spec;
  subsequent work drifts from the actual source.
- **Improving while executing** — reflexive renames, refactors, and
  simplifications during what should be a scope-bounded task.
- **Synthetic-fixtures-only validation** — the agent generates both
  the tests and the code that satisfies them.
- **"Looks reasonable" as done-gate** — the weakest test pyramid
  layer used as the only gate.
- **Fabricated inference presented as observation** — an async status
  event, a cited anchor, or a "verified" claim *invented* rather than
  read (the sharpest Axiom-2 violation); the defense is disk truth over
  narration — confirm the thing exists before citing it.
- **Absence read as a state** — silence on an unattended run taken as
  "finished/stopped," or an empty check-result taken as "clean" when the
  check may not have run; the defense is to probe before acting — confirm
  the process is dead (not just quiet) and the tool ran (not just silent).

For full taxonomy, detection patterns, and mechanical defenses, read
**`references/llm-failure-modes.md`**. Consult this file before any
non-trivial LLM-assisted data work.

## Pre-shipping checklist

Run this checklist before declaring any data-engineering work done.
None of these items are optional. If you find yourself wanting to skip
one, that's the one you most need to run.

**Scale to the change.** A breaking or semantic change runs the whole list. A
purely additive change (e.g. a new nullable column nothing depends on yet) runs
the contract and real-data checks and may skip the parity/replay items. When you
can't tell whether a change is additive or breaking, treat it as breaking.

**Contract checks.**

- [ ] Output schema (columns + dtypes) matches the declared contract /
      baseline exactly.
- [ ] Row count is within tolerance of the expected baseline.
- [ ] Group cardinality (distinct combinations of key columns) matches.
- [ ] Per-column null rate is consistent with the contract.
- [ ] Aggregate sums on numeric columns match within float tolerance.

**Source-of-truth checks.**

- [ ] Every input read by the spec / existing code is read by the new
      code.
- [ ] Every output column has a documented source.
- [ ] Library signatures and string identifiers (calendar names,
      source names, schema names) verified, not assumed.

**Real-data checks.**

- [ ] Pipeline has been run end-to-end on a production-shaped sample.
- [ ] If the load is incremental, the cursor/watermark advanced this run
      (`freshness_check.py`) — a self-reported `success` is not freshness.
- [ ] Every constraint declared in the schema is satisfied by the
      sample.
- [ ] If the framework supports multiple backends, each backend has
      been exercised in a smoke test.

**Replayability checks.**

- [ ] Re-running the same partition produces the same output.
- [ ] No `now()` / random / non-deterministic side effects in the
      transform.

**Process checks (apply the ones relevant to the scenario).**

- [ ] If this is a migration: bug-for-bug parity confirmed;
      improvements deferred to a separate PR.
- [ ] If this is a refactor: no semantic changes; any change to
      contract is a separate, intentional PR.
- [ ] If this is a new dataset: the contract is declared first;
      output matches contract.
- [ ] If this is a schema change: compatibility direction declared;
      additive / dual-write / versioned path chosen explicitly.
- [ ] All consumers identified; breaking changes communicated.
- [ ] Every deliberate divergence from the baseline is documented and
      signed off.

**Observability checks.**

- [ ] Tests at every applicable pyramid layer (unit, contract,
      generic, singular, parity where relevant).
- [ ] Production monitors (freshness, volume, drift) configured
      before consumers depend on the output.

For concrete recipes implementing each check (SQL EXCEPT queries,
Polars `assert_frame_equal`, dbt-utils macros, custom comparison
scripts), read **`references/parity-recipes.md`**.

**Runnable checks (`scripts/`).** Four of those recipes ship as runnable,
stdlib-first tools: `schema_diff.py` (column/dtype diff), `parity_check.py`
(row-count, group-cardinality, null-rate, and aggregate-sum diff within
tolerance), `contract_check.py` (validate rows against a contract spec), and
`freshness_check.py` (assert an incremental cursor advanced — Recipe 14).
Wire them into CI or run by hand before declaring done.

> **last-reviewed: 2026-06-04.** The four non-negotiables and the 21 principles
> are stable; only the tool survey in `community-practices.md` drifts over time,
> so re-check that file's tool versions periodically.

## Additional resources

| File | Read when |
|------|-----------|
| `references/principles.md` | Drafting a design decision, code review, or stuck on which principle applies. The 21 principles in full, each with anti-pattern, corrective, verification, and the LLM-specific gotcha. Principles are universal; per-scenario applications are noted inline. |
| `references/scenarios.md` | Starting a specific kind of task. Step-by-step playbooks for new dataset, migration, refactor, schema evolution, backfill, incremental/streaming, and investigating downstream breakage. |
| `references/llm-failure-modes.md` | About to generate non-trivial data code with an LLM, or debugging output that "looks right but feels wrong." Fourteen documented failure modes (incl. the fabrication family: telemetry, anchors, verifier-inherited traps; the absence-read-as-state pair: unattended-run silence, fail-open tooling; and traced-the-wrong-copy: editable-vs-installed divergence) with detection patterns and mechanical defenses. |
| `references/parity-recipes.md` | Implementing a parity check, row-level diff, schema diff, or any verification step. Concrete code/SQL/CLI recipes for SQL warehouses, Polars, PySpark, dbt, and Python. |
| `references/contract-templates.md` | Designing or reviewing a data contract. Worked templates for the same dataset expressed as a dbt `schema.yml`, an ODCS YAML, a Pydantic model, and a JSON Schema. |
| `references/glossary.md` | When precision matters: schema vs. contract vs. interface, parity vs. equivalence, partition vs. snapshot, replay vs. backfill. |
| `references/community-practices.md` | Grounding a recommendation in published practice or choosing between competing approaches. Detailed summaries of dbt contracts/tests, ODCS, Schema Registry, GX, Soda, Beauchemin's paradigm, OpenLineage, Hamilton, Kedro, medallion, data mesh, Kimball SCDs. |

### How to use this skill in practice

For each new task, do these three things before writing any code:

1. **Identify the scenario.** New dataset? Migration? Schema evolution?
   Refactor? Backfill? Investigation? Open `references/scenarios.md`
   and find the matching playbook. Follow it in order; do not skip
   steps.
2. **Pin the baseline.** What is the contract being protected (for
   migration/refactor/schema-evolution) or declared (for new
   dataset)? Capture it — schema, dtypes, row count if relevant,
   group cardinality, aggregate sums. The pre-shipping checklist
   runs against this baseline.
3. **Decide on verification gates.** Which checks from
   `references/parity-recipes.md` apply to this task? Wire them into
   CI or run them by hand before declaring done.

When the work is complete, the pre-shipping checklist above is the
gate. If you cannot answer every item with "yes," the work is not done
— regardless of what the data "looks like."

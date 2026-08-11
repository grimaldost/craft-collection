---
name: data-engineering-discipline
description: >
  Discipline guardrails for data-engineering work with downstream consumers —
  activate at the START of the task, before writing code, because silent
  semantic drift is the dominant risk. Activate on: migrating or porting a
  pipeline, refactoring a transform, backfilling or replaying history,
  evolving a schema (add / rename / retype / drop a column), creating a new
  dataset — or a metadata / catalog / lineage emitter whose output a separate
  tool loads — that has consumers, designing or reviewing a data contract,
  reshaping a tool / API response payload a client depends on, writing or
  changing the tests, fixtures, or expected values that gate a pipeline,
  generating pipeline code with an LLM, and investigating a consumed
  dataset that misbehaves — "the numbers changed / look different", or a
  table/extract that "ran but didn't update / is stale / isn't refreshing / the
  watermark didn't advance". A hand-authored schema-as-data document counts
  when code is generated from or validated against it; not when its
  only consumers render it. The test for activation:
  could this change the columns, dtypes, row or group cardinality, null
  behavior, semantics, or freshness of a dataset — or the fields, types, or
  closed vocabularies of a tool/API payload — that something or someone
  else reads? Do NOT activate for pure
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

## Scoped-change lane

A bounded change to one transform or seam — a single tz-cursor fix, one emitter
field, a localized incremental load — does not need the full-migration
apparatus. Pin the contract for *that* seam (its schema / dtypes / semantics and
the consumers of the changed field), run only the parity and real-data checks
that touch it, and leave the rest of the pipeline alone — a wide scope is what
invites the "improving while executing" failure mode. The four non-negotiables
below still hold for the seam; what shrinks is the blast radius you verify, not
the rigor. Follow the project's own conventions over greenfield defaults
(python-engineering's edit lane owns that code-style half). A column written by
more than one producer is the documented exception — see below, it belongs to no
seam.

## The four non-negotiables

These four are the source of every principle here, and they win over any
recommendation in another file. Rank what follows by three properties: a
defense is deterministic, is out-of-band and not editable by the change it
judges, and bounds the blast radius. This skill is prompt-level guidance with
none of the three — its job is to make you build and demand the out-of-band
checks, not to be one.

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
  confirm the source you read is the code that *runs* (`which_copy.py`):
  an editable checkout and an installed release of the same library
  diverge silently. `systematic-debugging` owns the debug-time form.
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
- For a metadata/catalog or tool/API-payload emitter: the emitted contract
  loads and validates in the real consumer (or a producer-owned encoding of
  that consumer's expectation) — not only in the producer's own tests.
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

## Cross-producer contract

A contract column written by more than one producer belongs to no single seam,
so a correctly scoped change never covers it and both producer-local suites
stay green while the two writers disagree. Count the writers of every column
you touch (`producer_census.py`); two or more that were never run together is
unverified, not fine. Then run both and assert the join on the shared key
*before* asserting any value (`parity_check.py --two-producer`) — a dtype or
rendering mismatch drops rows, and a value comparison over the survivors reads
perfectly clean. A `Date` and a `Datetime` written by two emitters of one
column survived a 7,500-test suite, a full-model review and a multi-agent
audit exactly this way.

## Grain, fanout and time

Declare the grain before writing code — one row per what? A diff tool that is
not told the grain compares nothing. Then compare `COUNT(*)` against
`COUNT(DISTINCT <declared key>)` on both sides at every join and every
materialization stage, not only at the output. A `DISTINCT` introduced in a
diff that also changes a join is a fanout repair until proven otherwise: it
restores the row count while the measure stays double-counted, which is worse
than the failure it hid.

For each side of a filtered or joined transform, name: event time or ingestion
time; bounds inclusive or exclusive; timezone and DST; fiscal, ISO or calendar
week; `CURRENT_DATE` versus the pipeline's execution date. Every table in a
join is filtered on the same time semantics, or the join is wrong. One internal
audit of *time-based analyses* found 73% carried inconsistent time filters
across joined tables — a prevalence among analyses, not an agent capability
score — and what fixed it was metadata plus a deterministic cross-join
consistency check.

Re-running old logic against a source that has since changed produces a clean
compare and corrupt history: both sides read the same mutated input. Pin the
source snapshot, or an as-of timestamp, for both sides — or state plainly that
the replay proves determinism and not historical correctness. Whether history
*should* change at all is a contract decision, not a technical one.

## Oracle integrity

The verifier, fixtures, expected values, baselines and tolerance settings are
not edited in the change they judge. A diff that touches both the transform
and its expected output has produced no evidence. If a baseline is genuinely
wrong, repair it in its own change, with the reason.

## Irreversible operations

`DROP`, `TRUNCATE`, table replace, full refresh, production backfill,
partition delete, a primary-key or grain change, a metric-definition change:
propose these, do not execute them. This skill's force is advisory — a prompt
rule is not a gate, and in-context prohibitions have been violated on record.
The gate you rely on is the one outside the session.

## LLM failure modes

The dominant pattern is plausible-but-wrong output: it compiles, runs, and
produces believable numbers while silently changing meaning. SQL is the
sharpest case because the failures do not throw. Two modes specific to
producing a dataset are in **`references/llm-failure-modes.md`** — a fresh
verifier that inherits none of the design's documented traps, and a source
traced from the wrong copy. The tool-general evidence modes belong to
`verification-before-completion`.

## Pre-shipping checklist

Run this checklist before declaring any data-engineering work done.
None of these items are optional. If you find yourself wanting to skip
one, that's the one you most need to run.

**Scale to the change.** A breaking or semantic change runs the whole list. A
purely additive change (a new nullable column — or, in a non-tabular contract,
a new event type, enum value, or default-preserving API symbol — nothing
depends on yet) runs the contract and real-data checks and may skip the
parity/replay items. When you can't tell whether a change is additive or
breaking, treat it as breaking.

**Contract checks — run them, don't tick them.** `schema_diff.py base cand`;
`parity_check.py base cand --keys id,as_of --tol 1e-9` (add `--tol-col
name=atol` per noisy column, `--residual-zero name` for a column read as
`> 0`); `contract_check.py cand contract.json`; `freshness_check.py --prev
--curr`; `producer_census.py inventory.json`; `mutate_check.py cand --check
parity --column amount`. Each fails loudly on what it could not assess rather
than passing quietly — a dtype match never checked, an unassessable cursor,
null placement without unique keys, a contract shape it cannot read. PARITY OK
is necessary, not sufficient: the gaps each check leaves are enumerated in
`parity-recipes.md`.

**Source-of-truth checks.**

- [ ] Every input read by the spec / existing code is read by the new
      code.
- [ ] Every output column has a documented source, and every column has
      exactly one producer or a two-producer join that passed.
- [ ] Library signatures and string identifiers (calendar names,
      source names, schema names) verified, not assumed.

**Real-data checks.**

- [ ] Pipeline has been run end-to-end on a production-shaped sample.
- [ ] If the load is incremental, the cursor/watermark advanced this run
      — a self-reported `success` is not freshness.
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

> **last-reviewed: 2026-08-11.** The references carry no tool survey and no
> version-pinned recommendations, so nothing here goes stale on a vendor's
> release schedule. What drifts is the corpus: re-read this body against the
> feedback reports, not against the calendar.

## Additional resources

| File | Read when |
|------|-----------|
| `references/principles.md` | Drafting a design decision, code review, or stuck on which principle applies. Each principle with its anti-pattern, corrective, verification, and LLM-specific gotcha. |
| `references/scenarios.md` | Starting a specific kind of task. Step-by-step playbooks for migration, refactor, schema evolution (columns — and equally event types, enum values, API fields, tool/API payload contracts), backfill, incremental/streaming, and investigating downstream breakage. |
| `references/parity-recipes.md` | Implementing a parity check, row-level diff, schema diff, two-producer join, or any verification step. Concrete code/SQL/CLI recipes, and an honest list of what they do not catch. |
| `references/llm-failure-modes.md` | About to generate non-trivial data code with an LLM, or debugging output that "looks right but feels wrong." A verifier that inherits none of the design's documented traps, and a source traced from the wrong copy. |
| `references/contract-templates.md` | Designing or reviewing a data contract. A worked ODCS contract, the field vocabulary, the completeness checklist, the compatibility-mode table, and the contract-design anti-patterns. |

# Glossary

Precise terminology for data engineering. Terms are deliberately kept
narrow — when the field uses a word loosely, this glossary picks one
meaning and sticks with it. The point is to enable clear conversations
about what's actually being changed or guaranteed.

Organized into five sections:

1. **Contract and shape** — schema, contract, interface, dataset
2. **Equivalence and parity** — parity, equivalence, idempotency
3. **Time and recompute** — partition, snapshot, replay, backfill, watermark
4. **Pipeline shape** — transform, materialization, lineage, layer
5. **Quality and observability** — drift, freshness, SLO, quality

---

## 1. Contract and shape

**Schema.** The set of columns, their data types, and their order if
positional. A *strict* notion. A dataset's schema is observable directly
from the materialized output. Two datasets share a schema if their
column names + dtypes match.

**Constraints.** Restrictions on column values beyond their dtype:
nullability, uniqueness, foreign-key references, value ranges, regex
patterns, enum membership. Constraints are *declarative* — they assert
what must be true; they don't compute values.

**Contract.** The schema *plus* the constraints *plus* the semantics
(what each column means, what each row represents, what null means)
*plus* the SLAs (freshness, completeness, accuracy) *plus* the
deprecation policy. A contract is broader than a schema and broader
than a set of tests. Two datasets can share a schema but have
different contracts (e.g., different freshness SLOs, different null
semantics).

**Interface (or API).** The portion of the contract that consumers
depend on. For a public dataset, the interface is the entire contract.
For an internal staging dataset, the interface may be just the schema
that downstream models read.

**Dataset.** A named, materialized collection of rows with a contract.
A dataset has a producer, at least one consumer, and a lifecycle
(creation, updates, eventual deprecation). Tables, views, and files
are *physical realizations* of a dataset. A dataset can have multiple
physical realizations (e.g., `dim_customer__v1` and `dim_customer__v2`
during a deprecation window) that share a logical identity.

**Schema-as-code.** The practice of declaring a dataset's contract in
a versioned file (dbt `schema.yml`, ODCS YAML, Pydantic class, JSON
Schema) that's checked into the same repository as the producing code,
reviewed in PRs, and enforced in CI. The alternative — schema implicit
in the producing code — is the source of most silent contract drift.

**Schema-on-read vs. schema-on-write.** Schema-on-write enforces the
contract at the producer's boundary (e.g., a database with declared
column types rejects mismatched inserts). Schema-on-read enforces it
at the consumer's boundary (e.g., a Parquet file lets you write
anything; the contract is asserted by the reader). Modern data
engineering favors schema-on-write where possible — it catches
violations closer to the source.

---

## 2. Equivalence and parity

**Parity.** Output equivalence between two pipeline implementations.
"Parity-preserving" means the new pipeline produces output that
matches the legacy pipeline within a declared tolerance. Parity is the
success criterion for migrations and refactors. Parity is *measurable*
— see `parity-recipes.md`.

**Equivalence.** A broader notion than parity. Two pipelines are
equivalent if they would produce identical outputs for any input,
not just for the input sampled during parity testing. Equivalence
implies parity but not vice versa: parity-on-sampled-data does not
prove equivalence. (This is why the seven-day shadow run in the
migration playbook exists — to sample more inputs.)

**Tolerance.** The numerical bound within which two values are
considered "the same." Used for float comparisons (relative tolerance,
absolute tolerance) and for aggregate checks (within ±0.01%). Pick a
tolerance numerically; "should be close" is not a tolerance.

**Idempotency.** A pipeline is idempotent if re-running it on the
same inputs produces the same outputs. "Same partition twice → same
result." Idempotency is a property of the *write* operation: `INSERT
OVERWRITE` is idempotent, `INSERT INTO ... SELECT` is not.
Idempotency is the foundation of replay (see §3).

**Determinism.** A stronger notion than idempotency. A deterministic
pipeline produces the same output every time given the same inputs,
including no dependence on `now()`, random seeds, or input row order.
All deterministic pipelines are idempotent; not all idempotent
pipelines are deterministic.

**Pure function.** A transform with no side effects, no hidden state,
and deterministic output. Maxime Beauchemin's *Functional Data
Engineering* argues every batch transform should be a pure function;
this is the substrate that makes idempotency and replay possible.

---

## 3. Time and recompute

**Partition.** A subset of a dataset identified by a key (typically a
date or hour). Pipelines compute outputs partition-by-partition.
Partitioning enables: (a) parallel computation, (b) idempotent
overwrite, (c) replay of specific partitions without affecting others.

**Partition key.** The column(s) that identify a partition. Most often
a date column (`partition_date`) or composite (date + region).

**Snapshot.** A point-in-time view of a dataset's full state. Distinct
from a partition: a partition is *part of* the dataset; a snapshot is
*all of* the dataset as of a specific moment. Iceberg, Delta Lake, and
Snowflake support snapshot isolation natively. Time-travel queries
read historical snapshots.

**Replay.** Re-running a pipeline on a partition (or set of partitions)
to regenerate output. Replay is the primary recovery mechanism for
batch data: when a producer ships a bug, you fix the producer and
replay the affected partitions. Replay requires idempotency.

**Backfill.** Replay of historical partitions, typically to populate a
new dataset or to apply a producer change retroactively. Backfill is
*planned* and *bounded* — distinct from a casual rerun. See
`scenarios.md` → Backfilling.

**Watermark.** In incremental or streaming loads, the timestamp up to
which the pipeline has processed data. The watermark advances as new
data arrives. Watermark management is the discipline of tracking
which data has been seen, deciding how late "late-arriving" data is
allowed to be, and what happens to data that arrives outside the
late-arriving window.

**Late-arriving data.** Data that arrives after its partition's
watermark has advanced. Common in event-based pipelines where producer
timestamps differ from arrival timestamps. Policy for late-arriving
data is part of the contract: reject? reconcile? backfill?

**Time travel.** A warehouse feature (Snowflake, BigQuery, Delta,
Iceberg) that lets you query historical versions of a table. Useful
for debugging ("what did this look like yesterday?") and short-window
replay. Not a substitute for explicit SCD2 (see §4) when business
semantics demand entity-level history.

---

## 4. Pipeline shape

**Transform.** A function that produces a dataset from one or more
input datasets. Transforms are the unit of composition in pipelines.

**Pipeline.** A directed graph of transforms with a single execution
trigger (a schedule, an event, a manual run). One pipeline can
produce multiple datasets (each transform's output is a dataset).

**Materialization.** How a dataset is physically stored: table, view,
incremental, ephemeral (dbt), or file (Parquet, ORC). Materialization
choice is part of the dataset's operational contract. Switching from
a view to a table is observable to consumers (different query cost,
different freshness).

**Lineage.** The directed graph of which datasets feed which. Used
for impact analysis ("if I change column X, who breaks?") and post-
incident debugging ("where did this NULL come from?"). See
`references/community-practices.md` → OpenLineage.

**Layer.** A logical grouping of datasets by purpose in a multi-tier
architecture. Common scheme: bronze (raw), silver (validated), gold
(business-ready). Each layer has different discipline — see
`scenarios.md` → Creating a new dataset.

**SCD (Slowly Changing Dimension).** Patterns for tracking changes to
dimensional attributes over time. Kimball's seven SCD types (0, 1, 2,
3, 4, 6, 7) describe different tradeoffs. SCD2 — "new row per change
with surrogate key and effective dates" — is the workhorse pattern.
See `references/community-practices.md` → Kimball SCD patterns.

**Surrogate key.** An integer (or UUID) primary key assigned by the
producer, distinct from any natural key. Surrogate keys enable SCD2:
the natural key (e.g., customer_id) cannot uniquely identify a row
when multiple versions of the customer's data coexist in the table.

**Natural key.** A primary key derived from business attributes (e.g.,
an email address, an ISBN, a transaction reference). Natural keys are
human-readable and stable in source systems; they make poor primary
keys in SCD2 tables.

---

## 5. Quality and observability

**Drift.** A change in the shape or distribution of a dataset over
time. Three flavors:

- *Schema drift* — columns added/dropped/renamed, dtypes changed.
- *Distributional drift* — null rates change, value distributions
  shift, aggregates trend up or down.
- *Semantic drift* — same name, different meaning (the worst case).

**Freshness.** How recent the dataset's data is. A freshness SLO
declares "data is available by X minutes/hours after the source
event." Freshness is monitored separately from correctness.

**SLO (Service Level Objective).** A measurable target the producer
commits to. Common SLOs:

- Freshness: data available by 06:00 UTC daily.
- Completeness: row count within ±5% of expected.
- Accuracy: aggregates within ±0.01% of source.

SLOs are part of the contract. Missed SLOs are operational events with
escalation paths.

**Quality.** A loose umbrella term covering completeness, accuracy,
consistency, validity, uniqueness, and timeliness. The "data quality"
literature (Great Expectations, Soda, Anomalo, Monte Carlo) breaks
quality into measurable dimensions per assertion.

**Observability (data).** The platform's ability to detect and
diagnose quality problems in production. Production observability is
the *rightmost* layer of the test pyramid (`scenarios.md`) — it
catches drift after it's happening, not before. Necessary but not
sufficient.

**Test pyramid (for data).** Seven layers, narrowest at the bottom:

1. Unit tests (transform logic with mocked inputs).
2. Contract tests (structural shape).
3. Generic data tests (`not_null`, `unique`, `relationships`).
4. Singular tests (business-rule SQL).
5. Integration tests (end-to-end pipeline).
6. Parity tests (during migration / refactor).
7. Observability (production drift).

See `references/community-practices.md` for the full taxonomy.

---

## Cross-references

**Schema vs. contract.** A schema is what columns/dtypes you have. A
contract is schema plus constraints plus semantics plus SLAs plus
deprecation policy. Use "schema" when you mean shape; use "contract"
when you mean the full agreement with consumers.

**Idempotency vs. determinism.** Idempotency: same inputs → same
*persisted* state. Determinism: same inputs → same *computed* output,
every time, no randomness. Determinism implies idempotency. All pure
functions are deterministic.

**Partition vs. snapshot.** Partition is part of the dataset.
Snapshot is the whole dataset at a point in time. Iceberg/Delta give
you snapshots cheaply (via the transaction log); explicit
partitioning gives you replay granularity.

**Replay vs. backfill.** Replay re-runs a recent partition (typical
recovery). Backfill re-runs many historical partitions (planned
event). Both require idempotency.

**Drift vs. breaking change.** A drift is observable change in a
dataset. A breaking change is a drift that violates the contract.
Schema drift is *always* a breaking change. Distributional drift may
or may not be — depends on the contract's SLOs.

**Test vs. monitor.** A test runs at build time and gates the deploy.
A monitor runs in production and alerts on detected problems.
Mature stacks have both; tests prevent known classes of bugs,
monitors detect the unknown ones.

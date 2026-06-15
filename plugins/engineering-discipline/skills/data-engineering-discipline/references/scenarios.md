# Scenarios — Step-by-Step Playbooks

Discipline applied to specific situations. Each playbook is a sequence,
not a menu — execute steps in order. Each step has four parts:

- **What to do** — the action.
- **Why** — what failure this protects against.
- **How** — concrete commands, queries, or recipes.
- **Watch for** — failure modes specific to this step, and when to
  escalate.

The playbooks are ordered roughly by frequency: most data work is
either creating a new dataset, evolving an existing one, or refactoring
internals while preserving the interface. Migration and backfill are
less frequent but higher-risk per occurrence. Investigation is the
fire-drill scenario.

For the parity recipes referenced throughout (row-level diff, schema
diff, aggregate checks), see `parity-recipes.md`. For contract template
examples, see `contract-templates.md`.

---

## 1. Creating a new dataset

The most common starting point for new data work. The discipline here
sets the contract that future scenarios (evolution, refactor, migration)
will protect.

### Step 1.1 — Find at least one named consumer

**What.** Identify who will read this dataset, what they'll do with it,
what their freshness / accuracy needs are.

**Why.** Datasets without consumers are speculative. Speculative
datasets become abandoned datasets become production confusion.

**Watch for.** "Someone might find this useful" is not a consumer. A
named team with a named use case is a consumer. If you can't name one,
the work is exploratory — close this skill and proceed without these
guardrails.

### Step 1.2 — Inventory the source data

**What.** Read the source data's schema and a representative sample of
values. Understand what's actually in the data, not what the upstream
team's documentation says is in it.

**Why.** Principle 2 (source of truth is observable, not inferred).
Source-side documentation lies more often than not — either it's
outdated, or it describes the intent rather than the reality.

**How.**

```sql
-- Schema inspection
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'raw' AND table_name = 'source_events'
ORDER BY ordinal_position;

-- Sample inspection
SELECT * FROM raw.source_events
ORDER BY ingestion_timestamp DESC
LIMIT 100;

-- Distributional check
SELECT
    COUNT(*) AS n_rows,
    COUNT(DISTINCT primary_key) AS n_distinct_keys,
    SUM(CASE WHEN nullable_col IS NULL THEN 1 ELSE 0 END) AS null_count,
    MIN(numeric_col), MAX(numeric_col), AVG(numeric_col)
FROM raw.source_events
WHERE partition_date >= CURRENT_DATE - INTERVAL '7 days';
```

**Watch for.** Surprises in the sample. "There shouldn't be nulls here"
that have nulls. "This should be unique" that has duplicates. "This is
an enum" that has unexpected values. Every surprise is a constraint
you'd otherwise declare incorrectly (Principle 10).

### Step 1.3 — Define the contract first

**What.** Columns, dtypes, primary key, freshness SLO, deprecation
policy, owner. Write it down before writing the producer.

**Why.** Contract-first prevents the producer from drifting toward
"what the source happens to provide" instead of "what the consumer
needs." It also forces explicit decisions about nullability, ranges,
and enums — decisions that surface assumptions early.

**How.** See `contract-templates.md` for worked templates in dbt
`schema.yml`, ODCS, Pydantic, and JSON Schema. Pick the form that
matches where you're enforcing the contract:

- dbt `schema.yml` for in-warehouse models managed by dbt.
- ODCS YAML when the contract crosses team boundaries.
- Pydantic at Python-side ingestion or service boundaries.
- JSON Schema when contracts cross language boundaries.

**Watch for.** Schema-only contracts (just columns and dtypes) are
incomplete. The contract must include nullability, value constraints
(enum, ranges, regex), uniqueness, freshness SLO, and ownership.

### Step 1.4 — Read 2–3 existing similar datasets

**What.** Find datasets in the same domain or layer. Read their YAML,
their transforms, their tests.

**Why.** Convention drift is the #1 source of LLM-assisted errors.
Reading existing datasets is the cheapest way to absorb conventions.

**Watch for.** Don't reinvent conventions. If the project uses
`stg_<source>__<entity>` naming, follow it. If it materializes
silver-layer models as incremental tables, follow suit. Deviation from
convention is a conscious choice with a documented reason, not an
oversight.

### Step 1.5 — Choose materialization and layer explicitly

**What.** Bronze, silver, gold (medallion) or staging, intermediate,
mart (dbt convention). Each layer has different discipline.

**Why.** Materialization is part of the operational contract. A
bronze-layer dataset is append-only and source-fidelity; a gold-layer
dataset is read-optimized for a specific use case.

**How.**

- *Bronze / staging*: raw, immutable, source-fidelity. Minimal
  transformation. Wide nullability tolerance. Type casting limited
  to obvious safe casts.
- *Silver / intermediate*: validated, conformed enterprise entities.
  Deduplication, type casting, data-quality gating. The "single
  source of truth" for an entity.
- *Gold / mart*: business-ready aggregates, star schemas,
  denormalized read-optimized models per consumption use case.

**Watch for.** Cross-layer shortcuts. Writing to silver directly from
ingestion (skipping bronze) is the canonical mistake — schema drift in
sources will break silver. Reading from bronze in a BI dashboard skips
the validation silver provides.

### Step 1.6 — Validate proposed constraints against source data

**What.** Run each declared constraint as a pre-flight query against
the actual source data.

**Why.** Principle 10. Constraints lie when they reflect what you
wish were true. Falsify them before declaring them.

**How.**

```sql
-- Run before declaring `nullable: false` on a column
SELECT SUM(CASE WHEN col IS NULL THEN 1 ELSE 0 END) AS null_count
FROM source_data
WHERE partition_date >= CURRENT_DATE - INTERVAL '90 days';
-- If null_count > 0, the constraint will fail.

-- Run before declaring `accepted_values: [a, b, c]`
SELECT DISTINCT col_value FROM source_data
WHERE partition_date >= CURRENT_DATE - INTERVAL '90 days';
-- The declared enum must include every observed value.
```

**Watch for.** "Recent" data may not cover the full distribution. Edge
cases (month-end, year-end, holidays, special promotions) may produce
values outside the typical range. Either widen the constraint or
exclude those days from production and document why.

### Step 1.7 — Build the producer to satisfy the contract

**What.** Write transforms that produce exactly what the contract
declares. No more, no less.

**Why.** Output drift from declared contract is silent breakage in
slow motion. Consumers will read the contract and depend on it.

**Watch for.** The temptation to ship "useful extras" — columns the
producer happens to compute that aren't in the contract. Either add
them to the contract (with version bump) or remove them. Don't ship
undocumented columns; consumers will start using them and you'll have
created an undeclared contract.

### Step 1.8 — Build the test pyramid at creation, not retrofitted

**What.** Unit tests for any non-trivial transform; contract
enforcement on output; generic data tests on PKs and FKs; freshness
check.

**Why.** Tests added later cover only what someone remembers to test.
Tests at creation cover what the original designer intended.

**How.** At minimum:

- *Unit*: every transform with non-trivial logic. dbt unit tests
  (v1.8+) or pytest for Python transforms.
- *Contract*: `contract: enforced: true` on the dbt model (or
  equivalent).
- *Generic*: `not_null`, `unique` on PKs; `relationships` on FKs;
  `accepted_values` for enums.
- *Source freshness*: declared and monitored.
- *Singular*: business-rule SQL for the specific invariants of this
  dataset.

See `references/community-practices.md` for the 7-layer test pyramid.

### Step 1.9 — Document and announce before any consumer integrates

**What.** Owner, freshness SLO, schema, sample queries, deprecation
policy, contact for issues. Discoverability in the catalog.

**Why.** Documentation written after consumers depend on the dataset
reflects what the producer wishes were true, not what actually is.

### Step 1.10 — Wire production observability

**What.** Freshness monitor, volume monitor, schema-drift monitor.

**Why.** Build-time tests catch what you knew to test. Production
monitors catch what you didn't. Principle 21.

**Watch for.** Don't ship observability after consumers depend on the
dataset. The first incident your consumers will tell you about is the
one that observability would have caught first.

---

## 2. Evolving a schema

The most common ongoing scenario for an existing dataset. The
discipline determines whether consumers experience smooth evolution or
abrupt breakage.

### Step 2.1 — Classify the change

**What.** Categorize the change: additive, subtractive, renaming,
retyping, or semantic-shift.

**Why.** Each category has a different playbook.

**How.**

- *Additive (new column, new enum value)*: goes straight in under
  BACKWARD or FULL compatibility. Make the column nullable or
  defaulted.
- *Subtractive (drop column, drop enum value)*: requires deprecation
  cycle.
- *Renaming*: requires dual-write + deprecation.
- *Retyping*: requires version bump. `int64 → string` is a breaking
  change no matter what.
- *Semantic shift (same name, different meaning)*: this is the worst
  case. Requires explicit rename to a new column with new semantics;
  old column deprecated. Never reuse a name with new meaning.

### Step 2.2 — Determine compatibility direction

**What.** BACKWARD, FORWARD, FULL, or NONE — pick one per producer.

**Why.** Compatibility mode determines whether you can add fields,
remove fields, or both, and in what order producers and consumers
must upgrade.

**How.**

- *BACKWARD* (Confluent default): new consumers can read old data.
  Safe: delete fields, add fields-with-defaults. Upgrade consumers
  first.
- *FORWARD*: old consumers can read new data. Safe: add fields,
  delete fields-with-defaults. Upgrade producers first.
- *FULL*: both BACKWARD and FORWARD.
- *NONE*: no checks. Avoid in production.

See `references/community-practices.md` → Schema Registry for the
detailed taxonomy.

### Step 2.3 — Lineage walk to identify consumers

**What.** Trace every downstream model, exposure, and known consumer
of the columns being changed.

**Why.** Consumer impact analysis is non-optional for subtractive or
renaming changes. Principle 14.

**How.**

- OpenLineage / DataHub / dbt-docs for in-platform lineage.
- Grep across known notebook / BI repos for the table and column names.
- Ask the SME about off-platform consumers (Excel exports, vendor
  tools).

**Watch for.** Off-platform consumers are the silent killer. They
don't appear in lineage graphs.

### Step 2.4 — Additive changes: ship the schema-as-code first

**What.** Update the contract YAML / dbt `schema.yml` before the
transform.

**Why.** Contract-first makes the change reviewable in isolation.
Reviewers see the new column declared before the code that produces
it.

**How.**

```yaml
# Add the column to schema.yml first
- name: new_column
  data_type: numeric(18, 2)
  description: "..."
  constraints:
    - type: check
      expression: 'new_column >= 0'
```

Then implement the transform that populates it.

### Step 2.5 — Subtractive / renaming changes: dual-write + deprecation

**What.** Add the new shape alongside the old. Announce the
deprecation window with a named end date. Remove only after the
window closes and consumers have acknowledged.

**How.**

```yaml
# dbt model with deprecation
version: 2
models:
  - name: dim_user
    deprecation_date: '2026-09-01'  # if removing the whole model
    columns:
      - name: last_login_date  # to be removed
        deprecation_date: '2026-09-01'
        description: "DEPRECATED — use last_activity_ts. Removal 2026-09-01."
      - name: last_activity_ts
        description: "Replaces last_login_date. Includes API activity."
```

Notify consumers via the established channel (Slack, email, dataset
catalog). Track acknowledgments. Don't merge the removal PR until the
acknowledgment threshold is met.

### Step 2.6 — Breaking changes: version bump

**What.** `dim_x_v1` and `dim_x_v2` coexist; consumers migrate
explicitly.

**How.**

```yaml
models:
  - name: dim_user
    latest_version: 2
    versions:
      - v: 1
        deprecation_date: '2026-12-01'
      - v: 2
        # current
```

### Step 2.7 — CI gate on breaking changes

**What.** Wire `state:modified` (dbt) or schema-registry compatibility
check (streaming) into CI to fail the PR if a breaking change is
unannounced.

**Why.** Mechanical enforcement beats social discipline. Make it
impossible to ship a breaking change without explicit acknowledgment.

### Step 2.8 — Document the change in the contract changelog

**What.** Every contract change has an entry in the
`CONTRACT_CHANGELOG.md` (or equivalent) with rationale, consumer
notification, and effective date.

**Why.** Principle 18. Changes traceable through git alone are
discoverable; changes documented in a changelog are *findable*.

---

## 3. Refactoring a pipeline (no functional change)

A refactor's success criterion is that the output is unchanged. The
gate is the same as a migration; refactors fail the gate for exactly
the same reasons.

### Step 3.1 — Define the parity contract first

**What.** Same columns, dtypes, row count, group cardinality,
aggregate sums. Pin a baseline from the current output.

**How.** See `parity-recipes.md` for the baseline capture pattern.
Save the baseline as a versioned artifact in the repo.

### Step 3.2 — Row-level diff at every step

**What.** Don't trust your own (or the LLM's) claim of "equivalent
logic." Run the data through both versions and diff.

**How.** Simplest pattern:

```python
import polars as pl
old = run_old_pipeline(sample_input)
new = run_new_pipeline(sample_input)
pl.testing.assert_frame_equal(
    new.sort(key_cols), old.sort(key_cols),
    check_exact=False,
    rel_tol=1e-9,
)
```

### Step 3.3 — Read the consumers, not just the producer

**What.** Refactor scope is determined by what consumers read, not by
what the code looks like.

**Why.** A "purely internal" refactor that changes an intermediate
column's dtype can still surface to consumers via a downstream model.

### Step 3.4 — No renames or semantic changes during refactor

**What.** Renames and semantic changes are schema-evolution changes,
not refactors. Handle them separately.

**Why.** Bundling renames into refactors is the canonical
"improvement smuggled into a scope-bounded task" pattern. Principle 17.

### Step 3.5 — Schema-diff in CI as the non-negotiable gate

**What.** Wire schema diff into CI to fail the PR if columns,
dtypes, or group cardinality changed.

**Why.** Mechanical enforcement; the refactor's PR description claims
no functional change. The diff proves it.

---

## 4. Migrating an existing pipeline

A scenario-heavy preservation task: the new pipeline must reproduce
the existing pipeline's output. The discipline overlaps significantly
with refactor, but the larger scope (often a framework change) and
the longer timeline make some additional steps necessary.

**Estimated time budget.** A "small" migration (one dataset, ≤10
downstream consumers) is 2–4 weeks of *real* discipline. The
shadow-run phase alone is 7–14 days. Pad accordingly.

### Step 4.1 — Inventory the existing output completely

**What.** Capture the existing output's full signature as a parity
baseline.

**Why.** Without a baseline, "parity" is unmeasurable. Without
measurement, you cannot prove the migration is invisible to
consumers.

**How.**

```sql
-- Schema baseline
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'existing_output'
ORDER BY ordinal_position;

-- Row count and group cardinality
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT key_a) AS distinct_a,
       COUNT(DISTINCT (key_a, key_b)) AS distinct_ab
FROM existing_output WHERE partition_date = '2026-05-26';

-- Per-column null rate and aggregate sums
SELECT
    AVG(CASE WHEN col_x IS NULL THEN 1.0 ELSE 0.0 END) AS null_rate_x,
    SUM(amount) AS total_amount
FROM existing_output WHERE partition_date = '2026-05-26';
```

Save the results as `migration/baseline.json` or equivalent.

**Watch for.** Skipping "obvious" columns. Capture every column,
every aggregate. The column you don't measure is the one that will
silently change.

### Step 4.2 — Inventory every existing input

**What.** Enumerate every source table, every join, every read in the
existing code path.

**Why.** Principle 5. Missing an input drops every column derived
from it.

**How.**

```bash
# Find every read in the existing code path
grep -rE "(pd\.read_|pl\.read_|bigquery\.Client|spark\.read|FROM |JOIN )" \
    existing/etl/path/ | sort -u
```

For each output column, write down which source input(s) it comes
from. This becomes the column-source map.

**Watch for.** Hidden inputs — config files read at runtime, calendar
data fetched from a registry, exchange rates pulled from an external
API. These don't appear in obvious read patterns but contribute to
the output.

### Step 4.3 — Identify all consumers

**What.** Enumerate every notebook, dashboard, downstream pipeline,
export, or report that reads the existing output.

**Why.** Bug-for-bug parity is measured against what consumers
actually consume.

**How.** Same as schema-evolution Step 2.3 — lineage walk + grep +
SME query.

### Step 4.4 — Define the parity gate

**What.** Declare the exact criteria for "the migration matches
existing."

**Why.** Without a written gate, "parity" drifts to "looks
reasonable."

**How.** A parity gate has at least:

- Row count exact (or within documented tolerance, e.g., ±0.01%).
- Every column present with matching dtype.
- Every numeric aggregate within float tolerance (e.g., relative
  tolerance 1e-9).
- Every group cardinality reproduced.
- Per-column null rate within tolerance.
- For a sample of natural keys: row-level value match.

Write this as a runnable script. See `parity-recipes.md`.

### Step 4.5 — Build the new pipeline to satisfy the parity gate

**What.** Produce a new pipeline that passes the gate — only the
gate, nothing more.

**Why.** Bundled improvements are silent regressions. Principle 17.

**How.**

- Open an `IMPROVEMENTS.md` file in the migration branch. Anything
  improvable goes there, not into the in-flight code.
- For each output column, implement the transform that produces it.
  Match dtypes explicitly. Match group keys exactly.
- Run the parity gate after each major component lands.

**Watch for.** The agent (or you) will be tempted to rename a "weird"
column, drop a "redundant" group key, "simplify" a transform. Resist.
Note it in `IMPROVEMENTS.md` and move on.

### Step 4.6 — Run shadow for 7–14 days minimum

**What.** Both pipelines write; only the existing one is read by
consumers. Diff outputs daily.

**Why.** A week-over-week cycle exposes weekend, month-end, and other
calendar-sensitive edge cases that a single-partition test cannot.

**How.**

- Schedule the new pipeline alongside the existing one, writing to a
  separate location (e.g., `prod__shadow.dataset_name`).
- Daily diff job compares outputs; alerts on any mismatch.
- Triage every mismatch: is it a documented divergence, a bug in the
  new pipeline, or a bug in the diff itself?

**Watch for.** The temptation to declare "parity achieved" after 2–3
good days. Don't. The seven-day minimum exists because the failures
it catches happen at specific calendar moments. Month-end is the
canonical landmine.

### Step 4.7 — Get explicit sign-off on every divergence

**What.** For every documented divergence from the existing output,
get sign-off from a consumer representative.

**Why.** Divergences that consumers haven't approved become
post-cutover surprises. Principle 18.

**How.** A `MIGRATION_NOTES.md` file lists each divergence:

```markdown
## Divergence D1: Decimal precision change on `amount` (Decimal(18,4) → Decimal(18,6))
- Rationale: new framework's default precision is 6; original was 4.
- Impact: trailing-digit changes in aggregates; no row-count change.
- Consumer notification: finance team notified 2026-05-15; ack 2026-05-17.
- Sign-off: Jane Doe (Finance Lead), 2026-05-17.
```

### Step 4.8 — Cutover, keep the original intact for a rollback window

**What.** Switch consumers to the new pipeline. Keep the original
running and materialized for a defined window (typically 30 days).

**Why.** If a problem surfaces post-cutover, you need to be able to
roll back without losing data or context.

### Step 4.9 — Improvements PR (post-cutover)

**What.** After cutover and rollback window closes, work through
`IMPROVEMENTS.md` as separate PRs.

**Why.** Improvements deserve their own scrutiny, separate from the
migration's parity gate.

---

## 5. Backfilling

### Step 5.1 — Backfill is a planned event, not a casual rerun

**What.** Treat a backfill the same way you treat a deploy: planned,
announced, monitored.

**Why.** A backfill writes a lot of partitions, changes a lot of
history, can blow your storage and cost budgets, and can surface
bugs that haven't been seen in months.

**How.**

- Declare the partitions to be backfilled.
- Estimate cost and time. If you can't, do a single-partition trial
  first.
- Announce: which consumers will see changed data, when.
- Schedule during low-traffic hours.

### Step 5.2 — Idempotent partition writes only

**What.** Re-running the same partition key must produce the same
result in the destination.

**Why.** A non-idempotent backfill leaves the destination in a state
that depends on whether the backfill is partial, complete, or has
been re-run. Replay becomes impossible. Principle 13.

**How.** `INSERT OVERWRITE` keyed on partition, or `MERGE` with a
complete match condition.

### Step 5.3 — Parity check against full-recompute

**What.** On a representative window, backfill, then do a
full-recompute, then diff.

**Why.** The backfill's output must equal what a fresh full-recompute
would produce. Any divergence is a bug in the backfill logic.

### Step 5.4 — Late-arriving data policy is documented

**What.** Define the late-arriving window. Define the reconciliation
strategy. Both are part of the contract.

**Why.** "We'll figure it out when it happens" is how late-arriving
data silently corrupts history.

---

## 6. Incremental / streaming loads

### Step 6.1 — Watermark management is explicit

**What.** Declare the high-water-mark column. Declare the
late-arriving allowance.

**How.**

```sql
-- dbt incremental model
{{ config(
    materialized='incremental',
    unique_key=['event_id', 'event_date'],
    incremental_strategy='merge',
    on_schema_change='fail'
) }}

{% if is_incremental() %}
WHERE event_timestamp > (SELECT MAX(event_timestamp) FROM {{ this }})
                       - INTERVAL '24 hours'  -- late-arriving window
{% endif %}
```

### Step 6.2 — Idempotent overwrites or MERGEs

Match conditions cover the full natural-key set. Principle 13.

### Step 6.3 — Replay-safe by partition

**What.** You can re-process any partition without side effects on
other partitions.

**Why.** Replay is your primary recovery mechanism. A pipeline that
can't be replayed is unsupportable in production.

### Step 6.4 — Schema-registry compatibility check (for event streams)

**What.** At minimum BACKWARD_TRANSITIVE on the producer's contract.

**Why.** Event streams have asynchronous producer/consumer upgrade
cycles. Transitive compatibility ensures every prior schema version
remains readable.

---

## 7. Investigating downstream breakage

The "numbers look off" report. This playbook turns the vague
complaint into a bounded investigation.

### Step 7.1 — Don't speculate from the report

**What.** Resist the urge to immediately propose a hypothesis. Get
the specifics first.

**How.** Ask the reporter:

- Which specific dataset, column, or aggregate is off?
- Off compared to what — yesterday's number, last week, a known
  truth?
- When did the symptom first appear?
- What does the reporter think changed?

### Step 7.2 — Bound the change window

**What.** Identify a "last known good" timestamp and a "first known
bad" timestamp.

**Why.** A bounded window narrows the search dramatically. Without
it, you're searching the entire history of every producer.

**How.**

```sql
-- Find when the metric changed
SELECT partition_date, SUM(amount) AS daily_total
FROM downstream_dataset
WHERE partition_date BETWEEN '2026-05-01' AND CURRENT_DATE
ORDER BY partition_date;
-- Eyeball the series for a step change
```

### Step 7.3 — Lineage walk

**What.** Trace upstream from the broken output through every
producer that touches the affected columns.

**Why.** The change is somewhere in this upstream tree. Walking it
systematically beats randomly checking producers.

**How.**

- OpenLineage / DataHub / dbt-docs: find every upstream node
  touching the affected columns.
- For each upstream node, what changed in the change window? Code
  changes (git log), data-source changes (source freshness or
  volume anomalies), backfills or replays.

### Step 7.4 — Schema diff between last-good and first-bad

**What.** Compare the upstream schemas at the last-good timestamp
and the first-bad timestamp.

**Why.** Many "numbers are off" reports trace to an unannounced
schema change upstream — a column rename, a dtype change, a new
enum value bucketed into the wrong category.

**How.** If you have time-travel data (Iceberg, Delta, Snowflake),
diff the schema directly. Otherwise, diff git history of the
upstream producer's contract.

### Step 7.5 — Row-level diff on a partition spanning the change window

**What.** Pull rows from before and after the change window, diff
them.

**Why.** Even with the same schema, value distributions can shift
silently — a dtype change, a different rounding mode, a new business
rule applied retroactively.

**How.** See `parity-recipes.md`.

### Step 7.6 — Once you find the change, do not "fix forward"

**What.** Fix the producer, then replay the affected partitions.

**Why.** "Fixing forward" — patching the data in place — leaves the
producer broken and the history inconsistent. Future replays will
produce wrong results.

**How.**

1. Identify the producer change that caused the issue.
2. Fix the producer.
3. Replay the affected partitions using the fixed producer.
4. Validate the replay against the parity baseline.
5. Document the incident.

**Watch for.** "We just need this dashboard right by 9am" is the
sentence that justifies fix-forward. Resist it. A wrong producer
running for one extra day is recoverable; a permanently-divergent
history is not.

---

## 8. Building an enforcement gate (the data product is a verdict function)

Some waves don't ship a dataset — they ship a *checker*: a lint rule, a
CI gate, a validation function, a contract-enforcement plant whose output
is a pass/fail verdict over a tree, not rows in a table. The four
non-negotiables still apply, but they translate: the "schema" is the
verdict function's contract (what it must catch and must pass); the
"parity baseline" is the set of cases it must classify correctly; "real
data finds what synthetic can't" becomes "run the gate against the real
tree, not only planted fixtures." The dominant failure is a *vacuous
gate* — green because it checks nothing, not because the tree is clean.

### Step 8.1 — Write the dataset→verdict translation table

**What.** Before building the checker, write down what each non-negotiable
becomes for this gate: the contract = the exact conditions that must FAIL
and must PASS; the baseline = the current tree's verdict (green-on-arrival
is the contract — the gate must pass on the tree as it exists the moment
it lands); the real-data check = running against the whole real tree, not
only fixtures.

**Why.** A verdict function has a contract just as a dataset does. Leaving
it implicit is how a gate ships that passes everything.

**Watch for.** A gate whose only test is "passes on the current tree."
That proves it isn't a false positive; it does not prove it can fail.

### Step 8.2 — Prove the gate can fail (the non-vacuity matrix)

**What.** Three planted checks, each a test fixture:

- *plant-fires* — a deliberately bad case the gate MUST flag.
- *empty-allow-list* — when the allow-list / exclusion set is emptied, the
  gate fails loudly (proves it actually reads the list).
- *real-tree negative-pin* — pin a known-good real entity so a future
  regression that breaks it is caught.

**Why.** A gate that cannot demonstrate a failure is indistinguishable
from `return PASS`. The plant-fires fixture is the single most important
test of an enforcement gate.

**How.** Encode each as a CI unit test: plant-fires asserts a non-empty
violation list; empty-allow-list asserts failure when the list is cleared;
the negative-pin asserts the real entity stays correctly classified.

**Watch for.** Plant fixtures too easy to count — a syntactically broken
file the parser rejects *before* the gate's logic runs. The plant must be
valid input that the gate's logic must catch.

### Step 8.3 — Green-on-arrival is the contract

**What.** The gate must pass on the tree exactly as it exists when it
lands. If it would fail on existing code, either fix the existing code in
the same wave (in scope) or scope the gate to new code only — explicitly,
with the boundary recorded.

**Why.** A gate that lands red trains everyone to ignore it. A gate that
lands green on a clean tree is enforceable from day one.

**Watch for.** Shipping the gate and the fixes it requires in different
waves with no ordering — the gate is either vacuous (silently scoped
around the existing failures) or broken (red on arrival).

---

## 9. Repairing a contract to match shipped reality

The schema-evolution playbook (Scenario 2) assumes the contract moves
*forward* — you change the declaration and migrate consumers. This is the
inverse: the declared schema and the shipped producer disagree, and the
*declaration* is the thing that's wrong — consumers have only ever
observed the emitted shape. Repairing the contract *backward* to match
shipped reality is legitimate, but it is still a contract change and gets
the same discipline. The trap is treating "fix the obviously-wrong
declaration" as a no-op.

### Step 9.1 — Establish which side consumers actually depend on

**What.** Before changing either the declaration or the producer,
enumerate consumers and determine what each reads — the declared shape or
the emitted shape.

**Why.** The repair direction depends entirely on this. If consumers
observed only the emitted shape, the declaration is an aspiration and the
emission is the de-facto contract — repair the declaration. If any
consumer depends on the declaration, you have a real breaking change, not
a repair — go to Scenario 2.

**Watch for.** Assuming "the declaration is the contract" by definition.
The contract is what consumers depend on (non-negotiable #1); a
declaration no consumer reads is documentation, not a commitment.

### Step 9.2 — Record the retired aspiration durably

**What.** The declaration you're removing represented an intent. Record
why it never became real and why it's being retired — in an ADR or the
contract changelog, not just the diff.

**Why.** Non-negotiable #4: all change is traceable. A silently-deleted
aspiration is exactly the kind of thing a future session re-introduces.

### Step 9.3 — Land the repair with a parity pin

**What.** Pin the now-agreed shape (a frozen contract token / golden over
the full surface) in the same change that lands the repair, so the
declaration and the emission can't silently diverge again.

**Why.** The divergence happened once because nothing held the two in
sync. Repairing without a pin invites the same drift straight back.

**How.** A byte-stable contract fingerprint over the full surface,
asserted in CI (see `parity-recipes.md` for the fingerprint pattern).
Recompute it at the repair commit and pin it.

**Watch for.** Pinning only the repaired field. Pin the whole surface —
the next divergence won't announce which field it touches.

---

## 10. Cutting a release across independently-merged waves

Several waves merged independently, each green on its own gates. The cut
validates that they still *compose* into one coherent contract surface — a
property no per-wave gate can check, because each wave was reviewed
against the tree as it stood then, not the assembled whole. This is the
shape that catches added-surface drift (a CHANGELOG / migration entry each
wave skipped) and cross-wave contract divergence.

### Step 10.1 — Re-seal the freeze over the assembled surface

**What.** Recompute the public-surface and data-contract freeze (the
byte-stable fingerprints / goldens) over the assembled tree at the cut
commit, and diff against the last sealed point.

**Why.** A per-wave fingerprint proves that wave didn't drift; only an
assembled re-seal proves the waves didn't drift *each other*.

**How.** Recompute the contract token over the full dataset set in a clean
base worktree; a byte-identical diff is the no-silent-drift evidence.

### Step 10.2 — Real-data sweep, clean-room and strict

**What.** Rebuild every buildable dataset through the *current* contracts
— fresh cache, fresh state, strict mode — not from stale cache.

**Why.** Non-negotiable #3. A green synthetic-fixture suite cannot prove
the assembled contracts hold against real data; only a from-scratch
real-data rebuild can. Stale cache masks exactly the drift the cut is
meant to catch.

**Watch for.** A sweep that reads cached outputs. Clean-room means the
cache and any incremental state are discarded; every dataset rebuilds from
source through the new contracts.

### Step 10.3 — Cross-wave docs / release-notes completeness pass

**What.** Audit that every wave's new public surface or behavior change
has a CHANGELOG entry and, if consumer-facing, a migration note.

**Why.** The most common release-cut miss is not a broken dataset — it's a
real behavior change that shipped with no consumer-facing record. Per-wave
gates miss it because added-surface drift is invisible to a wave reviewed
in isolation.

**How.** A blind multi-agent audit panel suits this well: independent
readers for boundaries, public-surface/freeze, cross-wave contract
composition, and release-docs completeness, each blind to the others (see
`review-panel`). It catches release-notes drift per-wave gates structurally
cannot.

**Watch for.** Trusting that "each wave had a pre-mortem" covers the
assembly. Per-wave pre-mortems are blind to the composed surface by
construction.

---

## Cross-scenario notes

**When in doubt about which playbook applies**, ask: what is the
consumer's expected experience after this change ships?

- "Indistinguishable from before" → migration or refactor playbook.
- "They will see new data or new columns they need to know about" →
  new dataset or schema evolution playbook.
- "They're seeing something wrong right now" → investigation
  playbook.
- "They will see history changing under them" → backfill playbook.

**Every playbook ends with the pre-shipping checklist** in `SKILL.md`.
If the checklist's items cannot all be answered "yes," the work is
not done, regardless of which playbook you followed.

**Multiple scenarios at once.** Real work often combines scenarios.
A "new dataset + backfill historical data + wire incremental
forward" task touches three playbooks. Run all the relevant steps
from each; the playbooks overlap (e.g., the contract is defined once
in the new dataset playbook and reused), but the non-overlapping
discipline of each scenario still applies.

**The lint/format toolchain is a consumer.** When a task constrains the
*shape* of a diff or output literal — a migration preserving a
line-for-line form, a refactor pinning a diff shape, an enforcement gate
asserting on formatting — the repo's own formatter and linter are
consumers of that shape. Apply the planned transform to one representative
file and run the full lint+format gate on it *before* locking any
diff-shape constraint. If the tools rewrite the literal form (strip
imports, reflow, reorder), restate the constraint in content terms (a
pattern that must hold, a line that must be pure) rather than position
terms (column, exact line). A constraint the repo's own ruff rejects is a
defect you shipped to yourself.

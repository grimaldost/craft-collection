# Principles — Full Catalog

The 21 principles, organized by what each one protects. Each principle is
**universal** — it applies regardless of whether you're creating a new
dataset, migrating an existing one, refactoring transforms, evolving a
schema, backfilling, or investigating a regression. The *specifics* of
how it applies differ by scenario; those differences are noted inline.

Each principle has five parts:

1. **Statement** — the principle itself, crisp and scenario-agnostic.
2. **Per-scenario application** — what the principle looks like in each
   scenario it most directly affects.
3. **Anti-pattern** — the concrete way it gets violated.
4. **Corrective and verification** — what to do, and how to prove
   compliance, with concrete code/CLI where useful.
5. **LLM gotcha** — the specific way an LLM workflow tends to violate
   this principle, and the mechanical defense.

For the four non-negotiables from which these derive, see `SKILL.md`.

---

## Group 1 — Contract preservation (the output is the API)

The output of a data pipeline is the producer's commitment to consumers.
These five principles protect every axis of that commitment: column
names, column count, group cardinality, data types, and input
completeness.

### Principle 1 — Treat the output schema as a versioned API

**Statement.** The set of columns, their order if positional, and their
types are a public contract. Renaming a column is a breaking change in
the same way renaming a public function is.

**Per-scenario application.**

- New dataset: declare every column in the contract before shipping.
  Treat each name and type as a commitment.
- Migration / refactor: column names in the new output match the
  existing output exactly. Renames are out of scope.
- Schema evolution: rename only through dual-write + deprecation, never
  in place.
- Investigation: a column-rename in the producer's last PR is the first
  thing to suspect.

**Anti-pattern.** Renaming `unit_cost → uc`, `base_fee →
base_fee_amt`, `margin_raw → margin` "for clarity." Downstream
Excel workbooks, notebooks, and dashboards keyed on the original names
break the next morning.

**Corrective and verification.**

```python
# Polars: schema diff against a baseline
import polars as pl
new = pl.read_parquet("new_output.parquet")
baseline = pl.read_parquet("baseline_output.parquet")
assert set(new.columns) == set(baseline.columns), (
    f"missing: {set(baseline.columns) - set(new.columns)}; "
    f"extra: {set(new.columns) - set(baseline.columns)}"
)
```

For dbt, `contract: enforced: true` in `schema.yml` makes this an
automatic build-time gate.

**LLM gotcha.** LLMs reflexively rename for clarity in any task —
not just migrations. They treat naming as a code-style concern, not a
contract concern. Mechanical defense: column-name diff against the
baseline is a CI gate on every PR that touches a contracted model.

---

### Principle 2 — Columns are part of the contract

**Statement.** Every output column is part of what consumers depend on,
including columns that don't appear in the producing transform's "main"
logic. Derived columns, audit columns, metadata columns — all part of
the contract.

**Per-scenario application.**

- New dataset: enumerate every column you commit to producing. Don't
  rely on "whatever falls out of the SELECT."
- Migration / refactor: every column the existing output produces must
  appear in the new output. A column the new transform "doesn't need"
  is still a contract obligation.
- Schema evolution: dropping a column requires a deprecation cycle.

**Anti-pattern.** A position dataset includes weighted-average metrics
(`metric_a`, `metric_b`, `avg_rate`, `avg_uc`). The new transform
"doesn't need" them and silently drops them. Output is "complete" by
the producer's lens; consumers find their charts missing values.

**Corrective and verification.**

```python
# Required column presence check
required = set(baseline.columns)  # or from the declared contract
present = set(new.columns)
missing = required - present
assert not missing, f"missing required columns: {missing}"
```

dbt-utils' `equal_column_subset` for SQL. dbt contracts declare every
column in YAML; the build fails if any is missing.

**LLM gotcha.** LLMs work from the producing transform's perspective
and miss that some columns are derived elsewhere (computed in a
downstream SELECT, computed in a notebook, included in an export, used
in a join condition). Mechanical defense: the column inventory is a
*required output* of the planning phase — the plan must list every
output column with its source before any code is written.

---

### Principle 3 — Group cardinality is part of the contract

**Statement.** A `GROUP BY a, b, c` that silently becomes `GROUP BY a,
b` changes the meaning of every aggregate, even if column names stay
the same. Row count is the loudest signal that something changed.

**Per-scenario application.**

- New dataset: declare the grain explicitly (one row per what?). The
  group keys are the grain.
- Migration / refactor: reproduce the legacy group keys exactly. If a
  key feels redundant, prove its redundancy with a query before
  dropping it.
- Investigation: row-count anomalies in downstream aggregates often
  trace to a producer's group-cardinality change.

**Anti-pattern.** Legacy aggregate groups by 4 keys producing 69,449
rows. The new pipeline drops one key because it "felt redundant."
Output has 31,032 rows. The aggregates' totals match (sums are
associative), but the per-row meaning has silently changed — each row
in the new output represents a coarser grouping than before.

**Corrective and verification.**

```sql
-- Group cardinality check
SELECT COUNT(*) FROM (
    SELECT DISTINCT key_a, key_b, key_c, key_d FROM baseline_output
);
SELECT COUNT(*) FROM (
    SELECT DISTINCT key_a, key_b, key_c, key_d FROM new_output
);
-- counts must match exactly
```

```python
# Polars equivalent
baseline_groups = baseline.select(keys).unique().height
new_groups = new.select(keys).unique().height
assert baseline_groups == new_groups, (
    f"group cardinality changed: {baseline_groups} → {new_groups}"
)
```

**LLM gotcha.** LLMs read group-by clauses without internalizing that
each key materially affects what's being aggregated. They drop keys
when "simplifying." Mechanical defense: group keys are part of the
schema contract. Schema diff includes the group-key set, not just
columns.

---

### Principle 4 — Match data types exactly

**Statement.** `Date` and `Datetime[ns]` are not interchangeable.
`Decimal(18,4)` and `Decimal(18,6)` differ. `int64` and `int32` differ
at scale. Implicit casts at the consumer's side fail in the worst
possible way: silently, until they don't.

**Per-scenario application.**

- New dataset: declare dtypes explicitly in the contract. Cast at the
  producer's output boundary.
- Migration / refactor: every column's dtype matches the existing
  output's dtype. Don't let the new source's natural type leak through.
- Schema evolution: dtype changes (`int32 → int64`, `Date →
  Datetime`) are breaking; they require a version bump.

**Anti-pattern.** Legacy `trade_date` is `Date` (i32). New pipeline's
`trade_date` is `Datetime[ns]` (i64) because that's what BigQuery's
extract returned and no cast was added. Downstream `asof-join` fails at
runtime with a dtype-mismatch error after consumers have already
adopted the new output.

**Corrective and verification.**

```python
# Per-column dtype assertion
expected_schema = {
    "trade_date": pl.Date,
    "amount": pl.Float64,
    "client_id": pl.Utf8,
}
for col, expected_dtype in expected_schema.items():
    actual = new.schema[col]
    assert actual == expected_dtype, (
        f"{col}: expected {expected_dtype}, got {actual}"
    )
```

dbt contracts with `data_type:` enforce this in CI before
materialization.

**LLM gotcha.** LLMs accept whatever type a source returns and
propagate it downstream. They rarely insert explicit casts unless
told to. Mechanical defense: schema-as-code declaration with enforced
dtypes; contracts that fail the build on dtype mismatch.

---

### Principle 5 — Every input source is part of the producer's responsibility

**Statement.** A transform's contract includes every dataset it
ingests. A script that pulls two tables and produces one output has
two inputs, not one. Missing an input silently drops every column
derived from it.

**Per-scenario application.**

- New dataset: enumerate every source before writing the producer.
  Trace every output column back to its source input(s).
- Migration / refactor: every input read by the existing code must be
  read by the new code.
- Schema evolution: adding columns from a new input may require the
  new input to become a permanent dependency — declare it.
- Investigation: a "missing column" report often means a missing input,
  not a missing transform.

**Anti-pattern.** A legacy script extracts TWO tables and writes TWO
parquets. The migration plan captures "orders + revenue data" as one
line; the second extraction is deferred indefinitely and never
lands. The `revenue` column silently disappears from the downstream
output. The producer doesn't see it because the column lives in an
output the new producer doesn't materialize.

**Corrective and verification.** Produce a written inventory:
`[(output_column, [source_inputs])]` for every output column. Compare
the resulting input set against `grep`-found `read_*` / `from` clauses
in the source code. Any mismatch is a missing input.

**LLM gotcha.** LLMs read the first few inputs in a file and stop when
they think they've understood the pattern. Mechanical defense: enforce
the inventory step before code generation. The plan must list every
input with its corresponding output columns.

---

## Group 2 — Source-of-truth discipline (verify, don't infer)

These principles defend against the LLM-dominant failure mode of
inferring instead of verifying. The discipline applies to existing code
(read it, don't summarize), materialized data (inspect it, don't trust
the code), library signatures (run `inspect.signature`, don't recall),
and registries (enumerate them, don't guess identifiers).

### Principle 6 — Read primary sources end-to-end, not summaries

**Statement.** Whatever you're working from — existing source code,
upstream data, a spec document, a library — read it primary, not via
summaries or interpretations. Summaries are lossy; the lost details
are usually load-bearing.

**Per-scenario application.**

- New dataset: read the source data's schema and a sample of values
  end-to-end. Don't rely on the upstream team's documentation.
- Migration / refactor: open and read each existing source file
  end-to-end. Don't build from a plan that paraphrased the code.
- Schema evolution: read the current contract YAML and the actual
  materialized schema. They may differ; the materialized form is
  what consumers depend on.
- Investigation: read the producer's code at the change window. Don't
  rely on the developer's recollection of what changed.

**Anti-pattern.** The agent does a quick read of a source file, writes
a plan listing major components, then builds against the plan as if
it were the spec. When the plan misses a corner-case branch, a derived
column, or a secondary join, the build inherits the gap. Read the file
end-to-end at the start of each phase.

**Corrective and verification.** Before writing any new code, produce
a per-file checklist: every input source, every output, every
grouping, every derived column, every join key, every conditional
branch. If you cannot fill the checklist from memory after reading,
re-read.

**LLM gotcha.** This is the *defining* LLM failure mode. The plan
becomes the source of truth and code drifts from the actual source.
A real migration like this can take dozens of commits to get right.
Mechanical defense: re-read the primary source at the start of
each phase, regardless of how confident the agent feels.

---

### Principle 7 — Materialized data outranks code as the truth

**Statement.** Code can lie. Comments can lie. The materialized output
cannot. When the code and the output disagree, the output is what
consumers rely on.

**Per-scenario application.**

- New dataset: validate the producer's output against the declared
  contract by inspecting materialized data, not by reading the code.
- Migration / refactor: compare new output to existing output, not new
  code to existing code, as the parity gate.
- Schema evolution: the materialized schema is what consumers will
  see. Diff materialized schemas before and after, not just YAML
  before and after.
- Investigation: the data is the evidence. The code is a hypothesis
  about the data. Always check the evidence.

**Anti-pattern.** The agent implements the existing code "as written"
and ships, only to discover the existing output reflects a bug-fix or
hotfix applied directly to the materialized data that the code never
received. The new pipeline is "correct" by the code but breaks
consumers because their expectation was set by the materialized
output.

**Corrective and verification.** Row-level diff against the
materialized output on a real partition. See `parity-recipes.md` for
concrete recipes.

**LLM gotcha.** LLMs prefer reasoning over data inspection. They will
declare "the code matches" without ever loading the actual output to
compare. Mechanical defense: data inspection at the materialized
output is a non-negotiable done-gate, not an optional check.

---

### Principle 8 — Verify library signatures and identifiers before relying on them

**Statement.** The signature you remember is the signature you saw in
a different version, a different library, or a hallucination.

**Per-scenario application.** Universal — applies to every scenario
where you call code you didn't just write.

**Anti-pattern.** Eight library-signature errors caught at runtime in
a single phase because parameter names were inferred, not verified:

- `polars.testing.assert_frame_equal(rtol=...)` — actual: `rel_tol`
- `weighted_average(keys=...)` — actual: `group_cols`
- `business_date_range(...)` returns `Datetime[μs]`, not `Date` as assumed
- `WindowSpec(as_of_date=Series)` — actual type: `Sequence[date]`
- `apply_adjustment` is semantically wrong; correct primitive is
  `resample_bulk`
- `resample_bulk` is `@singledispatch`-decorated; positional args
  required
- The output column is literally named `'interpolated'`, not the
  input column name
- Calendar identifier `'calendar_c'` doesn't exist; registry has
  `'calendar_a'`

Each cost a debug round.

**Corrective and verification.**

```python
# 10-line smoke script per unfamiliar primitive
import inspect
from mylib.compute import weighted_average
print(inspect.signature(weighted_average))
# (df, value_col, weight_col, group_cols, **kwargs) -> DataFrame
# Now you know it's group_cols, not keys.

# For string identifiers, list before referencing
from mylib.calendars import list_calendars
print(list_calendars())
# ['calendar_a', 'calendar_b', ...]
```

**LLM gotcha.** Second-most-common LLM failure mode (after plan
drift). LLMs generate plausible parameter names from training-data
priors. Mechanical defense: for any unfamiliar primitive, a 10-line
smoke script is a required first step. Treat all signatures and
identifiers as suspect until verified.

---

## Group 3 — Real-data discipline (staging is where reality lives)

### Principle 9 — Synthetic fixtures are necessary but never sufficient

**Statement.** Synthetic fixtures test what you remembered to test.
Real data tests what actually happens.

**Per-scenario application.**

- New dataset: unit-test the transforms with synthetic fixtures, but
  also smoke-test on real source data before declaring the producer
  ready.
- Migration / refactor: real-data parity is the gate. Synthetic-only
  parity is no parity.
- Schema evolution: validate that real production data still satisfies
  the new contract.
- Backfill: re-test the producer on a historical partition's real
  inputs, not on synthetic fixtures.

**Anti-pattern.** Every unit test passes; the first staging run fails
on a null value in a column declared `nullable: false`, or a negative
amount in a column declared `ge: 0`. The fixtures were generated
alongside the code; they have the same blind spots.

**Corrective and verification.** A staging run with at least the last
30 days of production-shaped data is a required gate before declaring
work done.

**LLM gotcha.** LLM-generated test suites have very high test counts
and very low real-world coverage. The LLM both wrote the code and
generated fixtures that satisfy it. Mechanical defense: pair every
unit test suite with a real-data integration test that uses fixtures
the LLM *did not generate* — sampled directly from production.

---

### Principle 10 — Validate constraints against production data before declaring them

**Statement.** Constraints lie when they reflect what you wish were
true instead of what the data is. `nullable: false`, `ge: 0`, `unique`,
`enum [...]` are all falsifiable claims — check them against real data
before declaring.

**Per-scenario application.**

- New dataset: every declared constraint requires a pre-flight query
  against the source data.
- Schema evolution: tightening a constraint requires confirming
  production data already satisfies the tighter form.
- Migration / refactor: a constraint that the existing pipeline
  satisfies must be satisfied by the new pipeline too.
- Investigation: constraint violations in production are evidence
  that the constraint was declared without evidence.

**Anti-pattern.** Schema declares `nullable: false` on `uc` and
`margin`. But legitimate edge cases produce nulls: adjustment coverage
gaps produce null `uc`; same-day operations have `tenure_days=0` →
division by zero → null. Every unit test passes; the first staging
run fails on a null. Second run, after loosening that constraint,
fails on a negative amount because the contract said `ge: 0` but
reversals are legitimately negative.

**Corrective and verification.**

```sql
-- Constraint pre-flight check
SELECT
    SUM(CASE WHEN uc IS NULL THEN 1 ELSE 0 END) AS null_count_uc,
    SUM(CASE WHEN future_amount < 0 THEN 1 ELSE 0 END) AS neg_count_amount
FROM production_table
WHERE trade_date >= CURRENT_DATE - INTERVAL '90 days';
-- If null_count > 0, you cannot declare nullable: false
-- If neg_count > 0, you cannot declare ge: 0
```

**LLM gotcha.** LLMs draft constraints based on "what makes sense" —
a column called `amount` "should be positive." This is conviction
without evidence. Mechanical defense: every new constraint requires
a pre-flight query against production data.

---

### Principle 11 — Test frameworks against real backends, not just synthetic ones

**Statement.** A framework that works on file-based sources may fail
on warehouse sources because of execution-model differences (DLT
generators, lazy evaluation, streaming vs. batch).

**Per-scenario application.** Most relevant when building or adopting
a new framework that abstracts over multiple backends. Applies
symmetrically across scenarios — a new pipeline using a multi-backend
framework, a migration to such a framework, a refactor that
introduces one.

**Anti-pattern.** A driver tested with synthetic file sources passes
every unit test. The first BigQuery call fails because BigQuery
returns a `@dlt.transformer` (not a `@dlt.resource`); iterating one
outside DLT's pipe machinery raises `RuntimeError: generator already
executing`. The bug was latent for the entire build.

**Corrective and verification.** Every backend the framework claims
to support gets at least one end-to-end live test against a real but
small dataset.

**LLM gotcha.** LLMs treat framework abstractions as if they were
real — the test passes on the synthetic case, so the framework
works. Mechanical defense: live-backend smoke test is mandatory in
the framework's CI matrix.

---

## Group 4 — Replayability & idempotency (recompute as recovery)

### Principle 12 — Pipelines are pure functions of inputs and partition keys

**Statement.** Same inputs + same partition + same code = same output.
Always. This is the foundation Maxime Beauchemin laid in *Functional
Data Engineering* and remains the design philosophy behind Airflow,
Dagster, and Prefect.

**Per-scenario application.** Universal — applies to every batch
pipeline.

**Anti-pattern.** Transforms that read `now()` or random seeds without
recording them; transforms that mutate a partition in place;
transforms where the order of input rows affects output. Replay
produces different results than the original run.

**Corrective and verification.**

```python
# Pure-function check: same input → same output
out1 = run_pipeline(inputs, partition_key="2026-05-26")
out2 = run_pipeline(inputs, partition_key="2026-05-26")
pl.testing.assert_frame_equal(out1, out2, check_exact=True)
```

**LLM gotcha.** LLMs reach for `datetime.now()` and `pd.Timestamp.now()`
when they need a date. They use random sampling without recording
seeds. Mechanical defense: pre-commit hook that flags `now()` /
`today()` / `random.*` in transform code; CI gate that enforces
partition-keyed outputs.

---

### Principle 13 — Idempotent writes only

**Statement.** `INSERT INTO ... SELECT` is not idempotent. `INSERT
OVERWRITE`, `DELETE WHERE partition_key = X; INSERT`, and `MERGE` with
a complete match condition are idempotent.

**Per-scenario application.**

- New dataset: declare idempotency at design time. Choose a
  partition-overwrite or MERGE strategy.
- Migration / refactor: the new write pattern must be at least as
  idempotent as the existing one.
- Backfill: idempotency is the *enabling* property. Without it,
  backfill is not safe.
- Incremental loads: MERGE match conditions must cover the full
  natural-key set.

**Anti-pattern.** A MERGE statement matches on `(customer_id)` when
uniqueness requires `(customer_id, effective_date)`. Each rerun
creates silent duplicates that look like new rows. Documented in
Monte Carlo's analysis of LLM-generated SQL.

**Corrective and verification.**

```sql
-- Replay row-count check
SELECT COUNT(*) FROM target_table WHERE partition_date = '2026-05-26';
-- run the MERGE again
SELECT COUNT(*) FROM target_table WHERE partition_date = '2026-05-26';
-- counts must match exactly
```

For dbt incremental models: declare `unique_key` explicitly with all
key columns; use `merge` strategy; test replay.

**LLM gotcha.** LLMs write MERGE statements with the most obvious key
column but miss compound keys. Mechanical defense: replay test as a
required step before declaring an incremental model done.

---

## Group 5 — Schema evolution (change with a calendar)

### Principle 14 — Schema changes go through dual-write and deprecation, not in-place mutation

**Statement.** A column rename is two changes: add the new column,
then later remove the old one — separated by a deprecation window
with a named end date. The same applies to drops, retypes, and
semantic changes.

**Per-scenario application.**

- Schema evolution: dual-write is the default for any non-additive
  change.
- Migration / refactor: schema changes are out of scope. Smuggling
  them into a migration is the anti-pattern (see Principle 17).
- New dataset: design with future evolution in mind — versioned
  contract, owner, deprecation policy.

**Anti-pattern.** Rename a column in one PR. Downstream notebooks,
dashboards, and exports break the next morning. The producer team
blames "downstream's brittle code."

**Corrective and verification.** Add the new column alongside the
old; populate both; announce the deprecation window; remove the old
column only after the window expires and consumers have
acknowledged. dbt's `deprecation_date` or equivalent metadata makes
the calendar discoverable.

**LLM gotcha.** LLMs do not have a sense of consumer impact. They
will rename or delete columns without considering who reads them.
Mechanical defense: consumer-impact analysis (via lineage walk) is a
required step before any subtractive or renaming schema change.

---

### Principle 15 — Choose a compatibility direction and enforce it

**Statement.** BACKWARD-compatible changes: add nullable/defaulted
fields, delete fields. FORWARD-compatible changes: add fields, delete
fields-with-defaults. Pick one mode per producer and apply it across
all changes.

**Per-scenario application.** Most directly relevant to schema
evolution and to event-stream design (Schema Registry). The choice
also informs migration / refactor decisions when the producer's
output is consumed by multiple downstream teams.

**Anti-pattern.** Mixing compatibility modes within a single producer;
one PR breaks readers, the next breaks writers. Consumers never know
what to expect.

**Corrective and verification.** Declare the compatibility mode in
the producer's contract. Validate in CI before merge. For event
streams, use Schema Registry's `_TRANSITIVE` variants — they check
against all prior versions, not just the immediate predecessor. See
`references/community-practices.md` for the compatibility-mode
taxonomy.

**LLM gotcha.** LLMs handle each schema change in isolation, without
maintaining a global stance on compatibility direction. Mechanical
defense: compatibility mode is declared in the producer's contract
file; CI enforces it on every PR.

---

### Principle 16 — Versioned models for breaking changes

**Statement.** When a change cannot be made compatible, version the
model. `dim_user_v1` and `dim_user_v2` coexist for the deprecation
window; `latest_version` points consumers at the current one.

**Per-scenario application.** Schema evolution where the change is
genuinely breaking and dual-write is insufficient.

**Anti-pattern.** In-place breaking changes labeled as "v2" in a
comment but materialized to the same table. Consumers cannot opt in
to the new version.

**Corrective and verification.** Two physical artifacts during the
migration window. Discoverable, documented, dated. Use dbt's
`versions:` block or equivalent metadata.

**LLM gotcha.** LLMs may suggest "just update the model" when
versioning is the right choice. Mechanical defense: breaking-change
detection in CI (dbt `state:modified` with `--fail-fast`) forces the
versioning conversation before merge.

---

## Group 6 — Scope and traceability (intentional change)

These principles defend against the failure mode where change scope is
unclear, multiple changes are bundled together, or divergences happen
silently. They apply universally — bundling improvements is the
anti-pattern regardless of which task is "officially" in scope.

### Principle 17 — Change scope is explicit and bounded

**Statement.** Every change has a declared scope. Changes that fall
outside that scope are either deferred to a separate PR or explicitly
re-scoped with sign-off. The trap is the opposite: bundling unrelated
"improvements" into a scope-limited task.

**Per-scenario application.**

- Migration: bug-for-bug compatibility is the migration's scope.
  Renames, refactors, schema simplifications are out of scope. Each
  is a separate PR after parity is signed off.
- Refactor: parity-preserving code changes are in scope. Schema
  changes or semantic changes are out of scope.
- New dataset: declared contract is the scope. Output matches
  contract; deviations require contract update with sign-off.
- Schema evolution: a deprecation is one change; a rename is another.
  Each gets its own PR with its own deprecation calendar.
- Backfill: idempotent reproduction of historical state is the scope.
  "Fixing" past data is out of scope.
- Investigation / hotfix: the scope is the bug, not adjacent code
  that "could also use cleanup."

**Anti-pattern (migration form).** A migration ships with three
"improvements" bundled in: column renames, schema simplifications,
transform splits. Each is a legitimate engineering choice. Together,
in a migration, they are a silent regression.

**Anti-pattern (refactor form).** A "pure refactor" PR renames a
column and tightens a constraint while restructuring the code. The
refactor's parity gate now has to discriminate between the
restructure and the semantic change, which it cannot.

**Anti-pattern (new dataset form).** The contract says `tier` is one
of `bronze`, `silver`, `gold`, `platinum`. The producer also writes
`diamond` because "the data has that value." The contract drifted
from the implementation; downstream consumers crash on the new value.

**Corrective and verification.** Maintain an `IMPROVEMENTS.md` in the
working branch. Anything that feels improvable goes there, not into
the in-flight code. Improvements are consulted post-cutover (for
migrations) or post-merge (for refactors). For new datasets and
schema evolutions, contract changes go through their own PR with
their own approval.

**LLM gotcha.** LLMs *love* to improve. Renaming, refactoring,
simplifying — it's a reflex. Mechanical defense: an explicit
"improvement freeze" rule in the agent's instructions for the
duration of the scoped task. Improvements go in a backlog file, not
in-flight commits.

---

### Principle 18 — Every divergence from the baseline is explicit, approved, and documented

**Statement.** When you must diverge from the baseline — whatever the
baseline is for the scenario — write the divergence down, get
sign-off, log it in the dataset's change history.

**Per-scenario application.**

- Migration: divergences from legacy output (because the legacy was
  buggy, because regulation changed, because the new framework
  physically cannot reproduce something) are documented in
  `MIGRATION_NOTES.md`.
- Refactor: divergences from existing semantics (which shouldn't
  happen in a refactor, but sometimes the existing code was buggy)
  are explicit.
- New dataset: divergences from the declared contract require
  contract update with version bump.
- Schema evolution: deviations from the announced deprecation
  schedule are explicit.
- Backfill: divergences between backfilled output and what a fresh
  full-recompute would produce are bugs to fix, not features to
  ship.
- Investigation: any change to historical data is documented with
  rationale.

**Anti-pattern.** Silent divergences buried in commit messages.
Three months later, consumers ask "why does this number disagree
with the old report?" and nobody remembers.

**Corrective and verification.** The artifact differs by scenario:

```markdown
# MIGRATION_NOTES.md (migration)
## Divergence D1: Decimal precision change on `amount` (4 → 6)
- Rationale: new framework's default precision is 6; legacy was 4.
- Impact: trailing-digit changes in aggregates; no row-count change.
- Consumer notification: finance team notified 2026-05-15.
- Sign-off: Jane Doe (Finance Lead), 2026-05-17.

# CONTRACT_CHANGELOG.md (new dataset / schema evolution)
## v2.1.0 (2026-05-20)
- Added column: `last_activity_ts` (timestamp, nullable).
- Deprecated column: `last_login_date` (removal 2026-09-01).
- Sign-off: Data Platform Team, 2026-05-18.
```

**LLM gotcha.** LLMs introduce divergences silently because they
don't distinguish "I improved this" from "I deviated from spec."
Mechanical defense: every code change in a scope-limited PR must map
to either (a) a baseline-preserving translation, (b) a documented
divergence in the appropriate artifact, or (c) an item on a
post-cutover/post-merge backlog.

---

### Principle 19 — Test pyramid, all layers, in order

**Statement.** Unit → contract → generic data tests → singular tests
→ integration → parity (where relevant) → observability. Skipping
layers is the LLM-assisted trap: "the data looks right" is the
production-observability layer; it cannot substitute for contract or
unit tests.

**Per-scenario application.**

- New dataset: every layer applies; build the pyramid at creation,
  not later.
- Migration / refactor: parity tests sit between integration and
  observability. They are the migration / refactor success
  criterion.
- Schema evolution: contract tests catch breaking changes pre-merge.
- Incremental loads: integration tests cover the watermark and
  replay logic.
- Investigation: tests added during investigation prevent the same
  bug from recurring.

**Anti-pattern.** Relying on a single layer (most often "I ran the
pipeline and the rows look reasonable").

**Corrective and verification.** Test coverage matrix per artifact.
See `references/community-practices.md` for the 7-layer pyramid
taxonomy.

**LLM gotcha.** LLMs default to "the data looks right" as the only
check when no explicit test framework is set up. Mechanical defense:
the pre-shipping checklist in `SKILL.md` enumerates the pyramid
layers as required items.

---

## Group 7 — Lineage & observability (see drift before consumers do)

### Principle 20 — Every transformation is traceable from output back to inputs

**Statement.** Lineage is operational infrastructure, not after-the-
fact documentation. Impact analysis ("if I change column X, who
breaks?") and post-incident debugging ("where did this NULL come
from?") both need it.

**Per-scenario application.** Universal — applies to every
consumer-facing dataset.

**Anti-pattern.** Lineage extracted only from dbt manifests, missing
Spark jobs, ad-hoc backfills, and MERGE side effects. The pipeline
that's *actually running* in production isn't in the lineage graph.

**Corrective and verification.** Emit OpenLineage events from every
runtime (Airflow, Spark, dbt, custom Python jobs). Aggregate in
DataHub, OpenMetadata, Atlan, or Marquez.

**LLM gotcha.** LLMs cannot infer lineage that isn't in the code
they're reading. They will declare downstream impact "low" without
ever consulting a lineage graph. Mechanical defense: lineage walk is
a required step before any subtractive or renaming schema change.

---

### Principle 21 — Production drift is monitored, not assumed away

**Statement.** Build-time tests catch what you knew to test.
Production monitors catch distributional shifts, freshness misses,
schema drift in source data, and volume anomalies.

**Per-scenario application.** Universal — applies to any
consumer-facing dataset.

**Anti-pattern.** Treating dbt tests as the only quality layer.
Production incidents discovered by consumers, not by the platform.

**Corrective and verification.** Layered observability: dbt / GX /
Soda tests at build; statistical anomaly detection (Soda anomaly
checks, Anomalo, Monte Carlo, Bigeye) in production.

**LLM gotcha.** LLMs over-rely on build-time checks because that's
what they can write themselves. Production observability is
operational infrastructure, not test code. Mechanical defense:
production monitors are part of the definition-of-done for any
consumer-facing dataset.

---

## How the principles relate

| Principle group | Protects against | Most relevant scenarios |
|-----------------|------------------|------------------------|
| Contract preservation (1–5) | Silent schema / cardinality / dtype breakage | All scenarios touching a consumer-facing dataset |
| Source-of-truth (6–8) | Inference instead of verification | All scenarios where existing code, data, or libraries are involved |
| Real-data (9–11) | Synthetic-fixtures-pass-real-fails | New dataset, constraint design, framework testing, any "I tested it locally" claim |
| Replayability (12–13) | Non-idempotent runs, duplicate rows | Incremental loads, backfill, streaming, any partition-based pipeline |
| Schema evolution (14–16) | Silent consumer breakage | Schema changes, deprecations, versioning |
| Scope & traceability (17–19) | Bundled change, silent divergence | All scenarios — the highest-leverage discipline group |
| Lineage & observability (20–21) | Drift invisible until consumers complain | Any consumer-facing dataset |

When multiple principles apply, the contract-preservation group (1–5)
takes priority. They guard the consumer interface, which is the most
expensive thing to break.

These rules come from a real migration where
contract preservation (1–5), source-of-truth (6–8), and scope &
traceability (17–19) were all violated. That's why the migration
examples appear most frequently in the anti-patterns. The principles
themselves apply identically to other scenarios; only the *specifics*
of what counts as "the baseline" or "the contract" differ.

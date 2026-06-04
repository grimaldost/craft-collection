# Community Practices — Reference Appendix

Detailed summaries of the practice bodies referenced from `SKILL.md`. Read
this when a recommendation needs grounding in published practice, when
choosing between competing approaches, or when a discussion turns to a
specific framework or standard.

Organized into four sections:

1. **Contracts & testing** — dbt, ODCS, Schema Registry, Great Expectations, Soda
2. **Functional & lineage** — Beauchemin's paradigm, idempotency, OpenLineage, Hamilton, Kedro
3. **Architectural** — medallion, Data Mesh, Kimball SCDs, data product thinking
4. **LLM-assisted data engineering** — failure modes, CLAUDE.md patterns, MCP boundaries, parity gates

---

## 1. Contracts & Testing

### dbt model contracts (v1.5+)

Setting `contract: enforced: true` on a dbt model causes dbt to validate the
model's returned columns, dtypes, and declared constraints (`not_null`,
`unique`, `primary_key`, `foreign_key`, `check`) **before materialization**.
If the model's output diverges from the declared shape, the build fails and
the new shape never lands. Most warehouse adapters natively enforce only
`not_null`; other constraints are "definable but not enforced" depending on
the backend, though dbt validates them in the build step regardless.

Use contracts on every model consumed across team or project boundaries
("public" models, dbt Mesh exposure). Pair with `state:modified` selection
in CI to catch breaking changes before merge.

The discipline a contract enforces is **structural promise**: column names,
dtypes, and constraints are part of the API. The classic anti-pattern is
silent decimal-precision drift — a tweak to a numeric column's precision
causes downstream aggregates to disagree by a percent or two, undetected
for weeks. An enforced contract fails the first build.

### dbt model versioning + breaking-change detection

The `versions:` block lets producers ship `dim_x_v1` and `dim_x_v2` side
by side, with `latest_version` and `deprecation_date` controlling consumer
visibility. dbt Cloud's `state:modified` selector in CI detects breaking
changes (removed columns, type changes, constraint removals) and forces
version bumps before merge.

Use whenever a contracted model needs an incompatible change. The discipline
is **producer accountability**: silent breakage is impossible; deprecation
is a dated, named event.

### dbt tests: generic, singular, source freshness, snapshots

Generic tests (`not_null`, `unique`, `accepted_values`, `relationships`)
are SQL-templated assertions on columns or column groups. Singular tests
are arbitrary SQL returning failures. Source freshness asserts upstream
timeliness within declared bounds. Snapshots capture SCD2 history of a
source's slowly-changing dimensions.

Companion packages: `dbt_expectations` ports many Great Expectations
assertions into dbt; `dbt_utils` provides utility tests (`equal_rowcount`,
`expression_is_true`, `unique_combination_of_columns`).

The discipline tests enforce is **behavioral promise** on actual data
values. They complement, not replace, contracts. A renamed column passes
all column-level tests if the test YAML is renamed in the same PR;
contracts catch the rename, tests catch the value drift.

### dbt unit tests (v1.8+, May 2024)

Mocked-input / expected-output assertions on a model's SQL logic, run
before materialization. Tests live in YAML with `given:` (inputs as dict,
csv, or sql) and `expect:` (expected rows). The `--empty` flag enables
cheap CI compilation against incremental models without materializing
fixture data.

Use for complex transformations: regex parsing, sessionization, attribution
logic, MERGE branches, edge cases (nulls, empty inputs, zero-count groups).
The discipline is **logical correctness** of transform code — the kind of
bug data tests cannot deterministically catch.

The trap: the synthetic fixtures problem. LLM-generated unit tests often
test the same logic the LLM wrote against fixtures the LLM also generated.
High test counts, low real-world coverage. Mitigation: pair unit tests
with real-data integration or parity tests.

### Open Data Contract Standard (ODCS)

ODCS, currently v3.1.0 (December 2025), is a vendor-neutral YAML standard
under the Linux Foundation's Bitol project. It specifies a data contract's
schema, semantics, SLAs, quality rules, and relationships in a single
producer-owned file. Strict JSON Schema validation; executable SLAs;
companion specification ODPS (Open Data Product Standard) for the broader
"data as product" concept.

Use when a dataset crosses team or service boundaries, especially in event
streams or data-mesh adoption. The discipline is **portable, machine-
validatable contracts** — escapes vendor lock-in while standardizing the
producer/consumer agreement.

Andrew Jones' *Driving Data Quality with Data Contracts* (O'Reilly, 2023)
is the canonical reference. Chad Sanderson's "Shift Left Data Manifesto"
(Substack, 2025) frames the cultural reorganization: producers own quality,
enforced in CI/CD as integration tests.

### Schema Registry (Avro / Protobuf / JSON Schema)

Centralized registry (Confluent Schema Registry, AWS Glue, Apicurio)
storing versioned schemas with enforced compatibility rules:

- **BACKWARD** (Confluent default): new consumers can read old data. Safe
  changes: delete fields, add fields-with-defaults. Upgrade consumers first.
- **FORWARD**: old consumers can read new data. Safe changes: add fields,
  delete fields-with-defaults. Upgrade producers first.
- **FULL**: both BACKWARD and FORWARD simultaneously.
- **NONE**: no checks (avoid in production).
- **`_TRANSITIVE`** variants check against all previous versions, not just
  the immediate predecessor — strictly safer.

Use for any pub/sub source where producer/consumer upgrade ordering
matters (Kafka, Pulsar, gRPC). The discipline is **streaming schema
evolution** with explicit rollout ordering. The classic anti-pattern is
adding a required field with no default, which breaks all old consumers
and is rejected under BACKWARD.

### Pact-style contract testing for data

Consumer-driven contract testing ported from microservices to data: the
consumer publishes its expectations as a versioned contract; the producer's
CI runs the contract against test data on every change. Tools like Gable
instrument this in producer codebases, often by parsing application code
to detect what data is emitted.

Use especially where upstream service teams emit events consumed by
analytics. The discipline is **catching contract violations in the
producer's PR**, before deploy — the leftmost shift available.

### Great Expectations (v1.0, August 2024)

Python-based data-validation framework. Core concepts: Expectations
(individual assertions like `ExpectColumnValuesToNotBeNull`), Expectation
Suites (collections), Checkpoints (runnable bundles of suites against
data batches), Data Docs (auto-generated validation result documentation).

GX 1.0 (Aug 2024) was a breaking redesign: Fluent Datasources API,
drastically simplified Checkpoint constructor (legacy took ~15 named
parameters; v1.0 takes `validation_definitions` and `actions`), legacy
YAML/CLI workflow deprecated. **Pre-1.0 blog posts and Stack Overflow
answers do not apply.**

Use for validation outside the dbt model lifecycle — pre-warehouse
file landing, Spark/Pandas DataFrames, ML feature pipelines. dbt tests
are best when transformations live in the warehouse; GX shines for
cross-system validation.

The discipline boundary: Expectations validate **values**; they do not
guarantee **structural commitments**. Treat GX as a complement to
contracts, not a substitute.

### Soda Core / Soda Cloud / SodaCL

YAML-based check language (SodaCL), a Python library (Soda Core), and a
hosted product (Soda Cloud) with anomaly detection. Compares to Great
Expectations operationally but with a leaner check syntax and stronger
built-in statistical anomaly detection. The classic anomaly check used
Prophet under the hood; a 2025 rebuild was announced at Databricks AI
Summit. The classic check is marked deprecated; the rebuild is the
current production recommendation per Soda's docs.

Use for production-time quality monitoring with statistical drift detection
alongside rule-based checks. The discipline is **continuous observability**.

The trap: treating production observability as the contract. Drift
detection is the rightmost layer of the test pyramid — necessary, but it
detects drift after it's happening, not before. Contracts and build-time
tests are still required upstream.

### How dbt, GX, Soda, and ODCS fit together

These overlap but are not substitutes. A defensible production posture
typically uses **all** of them, each at the layer where it's strongest:

- **ODCS** for the producer/consumer contract itself (the spec).
- **dbt contracts** for in-warehouse structural enforcement.
- **dbt tests + dbt unit tests** for in-warehouse logical and value
  enforcement.
- **GX** for pre-warehouse validation (file landing, DataFrames, cross-
  system).
- **Soda Cloud / Monte Carlo / Anomalo** for production drift detection.

---

## 2. Functional & Lineage

### Maxime Beauchemin — Functional Data Engineering (January 2018)

Beauchemin's foundational essay ported functional programming principles
to batch ETL: tasks should be **pure functions** (same inputs → same
outputs), **idempotent** (re-running produces the same result), with
**immutable, time-partitioned outputs**. No in-place mutation. The paradigm
is the design philosophy behind Airflow itself; Dagster and Prefect's
data-aware scheduling models echo it.

Use this as the foundational frame for every batch pipeline. The
discipline is **reproducibility and recomputability**: bugs become
fixable by recompute, not by manual data surgery.

The classic anti-pattern: UPDATE statements that modify history; "fix it
forward" patches that leave a partition in an unreconstructible state. The
modern restatement (Ananth Packkildurai, *Data Engineering Weekly*) frames
this as the necessary precondition for any reliable replay or backfill.

### Idempotency, replay, and time-travel

Practical implementation of the functional paradigm:

- **Partition overwrites.** `INSERT OVERWRITE`, or `DELETE WHERE
  partition_key = X; INSERT`, replace a partition wholesale.
- **MERGE with complete match conditions.** All natural-key columns appear
  in the match clause; missing one column produces silent near-duplicates
  on each rerun.
- **Watermarks for late-arriving data.** High-water-mark column tracks the
  furthest-processed timestamp; the late-arriving allowance window is
  declared and bounded.
- **Snapshot isolation** at the table level (Iceberg, Delta Lake) for
  point-in-time reads.
- **Time-travel** (Snowflake, BigQuery, Delta) for short-window replay and
  debugging.

The discipline: **recompute as recovery**. Late-arriving data is
reconciled by rewriting affected partitions, not by patching live state.

### SCD in Iceberg / Delta — when time-travel is not enough

Delta and Iceberg time-travel preserves **table** versions, not
**business-entity** versions. Per Databricks' documentation: "Databricks
doesn't recommend using table history as a long-term backup solution for
data archival. Use only the past 7 days for time travel operations unless
you have set both data and log retention configurations to a larger value."
Defaults: `delta.deletedFileRetentionDuration` is 7 days;
`delta.logRetentionDuration` is 30 days.

Explicit SCD2 (with `effective_at`, `end_at`, `current_flag`, surrogate
keys) is still the right pattern when:

1. Consumers query "what did this dimension look like on date X" with
   arbitrary lookback;
2. Fact tables must join historically-correct dimension versions via
   surrogate keys;
3. Audit or regulatory requirements demand explicit version history.

Time-travel is the right tool for short-window debugging and ML
reproducibility. SCD2 is the right tool for business-meaningful versioning.

### OpenLineage + Marquez

OpenLineage is the de-facto open standard (LF AI & Data graduate project)
for run/job/dataset lineage. Three event types (RunEvent, DatasetEvent,
JobEvent), three core entities (Run, Job, Dataset) identified by
`namespace + name + runId`. Extensible via **facets** — atomic JSON
payloads carrying metadata (`SchemaDatasetFacet` for column schemas,
`DataQualityMetricsInputDatasetFacet` for row counts and null rates,
`SqlJobFacet` for the executed query text).

Native runtime integrations: Airflow, Spark, Flink, dbt. Marquez is the
reference backend; DataHub, OpenMetadata, and Atlan all consume OL events.

Use OpenLineage when lineage matters operationally — for impact analysis,
post-incident root-cause, and compliance audit. The discipline is
**runtime lineage as engineering infrastructure**, not after-the-fact
catalog inference. The anti-pattern is extracting lineage from dbt
manifests only, which misses Spark transformations, ad-hoc backfills, and
MERGE side effects.

### Lineage backends — DataHub, OpenMetadata, Atlan

- **DataHub** (LinkedIn-origin, open-source, push-based metadata):
  developer-leaning, strong API; the open default in tech-leaning shops.
- **OpenMetadata** (open-source, opinionated UX): batteries-included; better
  out-of-box governance UX.
- **Atlan** (SaaS, paid): governance / workflow leader; integrates with
  business stakeholders better than the open contenders.

All three ingest OpenLineage events. Selection is mostly about org maturity
and budget. For small teams, dbt-docs + manual cataloging is sufficient.

### Hamilton (Stitch Fix → DAGWorks)

Python microframework where every function is a node in a DAG, parameter
names declare dependencies, and type annotations document contracts. Built
at Stitch Fix to manage feature-engineering pipelines with thousands of
columns. Now under DAGWorks. Supports pandera-based per-node validation
and scales to Spark, Dask, Ray via adapters.

Use for feature engineering with hundreds-to-thousands of derived columns,
or ML pipelines where lineage must be code-level, not just table-level.
The discipline at the framework level: every transform is **named,
type-annotated, dependency-declared, and unit-testable in isolation**.
Code review becomes traceable because change diffs are localized.

The anti-pattern Hamilton addresses: "procedural notebook with 200 cells
of side-effecting code."

### Kedro (McKinsey → Linux Foundation)

Python framework with three primitives:

- **Nodes**: functions with named inputs and outputs;
- **Pipelines**: DAGs of nodes;
- **Data Catalog**: `catalog.yml` maps logical dataset names to physical
  I/O (file path, table name, format).

Enforces an eight-layer data-engineering convention:
`01_raw` → `02_intermediate` → `03_primary` → `04_feature` →
`05_model_input` → `06_models` → `07_model_output` → `08_reporting`.

Use for production-ready data science pipelines, especially where ML and
analytics share infrastructure. The discipline: **separation of I/O from
logic**, environment-based configuration, per-dataset versioning. The
anti-pattern: hardcoded filesystem paths in transformation code —
`catalog.yml` is the only place paths live.

---

## 3. Architectural Patterns

### Medallion architecture (bronze / silver / gold)

Earliest public reference: a Databricks blog post on June 2, 2020 (per
Daniel Beach's research on *Data Engineering Central* Substack).

- **Bronze**: raw, immutable, append-only. Preserves source fidelity.
  Includes metadata columns (`ingestion_timestamp`, `_metadata.file_name`).
  Databricks explicitly recommends storing many fields as string,
  VARIANT, or binary at bronze to survive upstream schema drift.
- **Silver**: validated, cleaned, conformed enterprise entities.
  Deduplication. Type casting. Data-quality gating. "Single source of
  truth" for an entity.
- **Gold**: business-ready aggregates, star schemas, denormalized read-
  optimized models per consumption use case.

The discipline by layer: bronze keeps raw fidelity with no transformation;
silver applies validation and conformance; gold builds business semantics
and aggregates.

Recent critiques (2024–2026): Lak Lakshmanan (ex-Google) argues gold is
under-specified and chaotic in practice; he proposes a four-layer model
with an explicit "platinum" layer between silver and gold for enterprise-
conformed entities, leaving gold for project-specific marts. Ananth
Packkildurai makes a related argument: platinum as the operational /
serving layer combining real-time and batch. The broader critique: medallion
is a **mnemonic**, not an architecture — apply it as a guideline, not a
rulebook.

Common anti-patterns: writing to silver directly from ingestion (Databricks
explicitly warns: schema drift in sources will break silver); treating
bronze and silver as physical layers rather than logical roles.

### Data Mesh (Zhamak Dehghani, May 2019)

Sociotechnical architecture introduced by Dehghani at ThoughtWorks. Four
principles:

1. **Domain-oriented data ownership** — data lives with the team that
   produces and understands it.
2. **Data as a product** — each domain's data is treated as a product with
   owner, SLAs, documentation, discoverability.
3. **Self-serve data platform** — shared infrastructure that domain teams
   use.
4. **Federated computational governance** — global policies enforced as
   code, locally implemented.

Use as the conceptual frame when an organization is large enough that a
central data team is a bottleneck (typically 100+ engineers, multiple
business domains). The discipline: **decentralized ownership** with
producer accountability and explicit consumer interfaces (the data
product).

Critique 2024–2026: Adoption has moderated from peak hype. The four
principles remain influential, but full data-mesh re-orgs are now seen as
overkill for many organizations. The **patterns** (data as product,
contracts, federated governance) are widely adopted without the full org
redesign. The Open Data Product Standard (ODPS v1.0.0, 2025) codifies the
data-product specification.

Anti-pattern: calling a centrally-owned analytics dataset a "data product"
without ownership, SLA, contract, or deprecation policy — "data mesh-
washing."

### Kimball SCD patterns

The Kimball Group's seven slowly-changing-dimension types:

- **Type 0** — retain original (no change ever recorded).
- **Type 1** — overwrite, no history. Use when history is not needed.
- **Type 2** — new row per change, with surrogate key, effective dates,
  current flag. The workhorse for historically-correct dimensions.
- **Type 3** — add a column for the previous value. Limited history (one
  prior version), useful when consumers want a side-by-side compare.
- **Type 4** — mini-dimension for rapidly-changing attributes (e.g.,
  customer-status flags) split off from the main dimension.
- **Type 6** — combination of types 1 + 2 + 3.
- **Type 7** — dual foreign keys in the fact table: surrogate for the
  historically-correct version, durable supernatural key for the current
  version.

Surrogate keys (integer, sequentially assigned, not natural) are essential
for Type 2 because the natural key cannot uniquely identify a row when
multiple versions exist.

Use as the decision frame for every dimension attribute: should this
change be tracked, overwritten, or both? The discipline: **explicit
per-attribute choice**, not "we'll figure it out later." Even in Iceberg /
Delta lakehouses, SCD2 remains necessary when business questions require
"what did this look like at point-in-time X."

Anti-pattern: using natural keys as primary keys in dimensions undergoing
Type 2 — breaks fact-to-dimension referential integrity the first time a
version changes.

### Data product thinking

Treating each consumable dataset as a product with:

- Named owner;
- Documented schema (the contract);
- Declared SLOs (freshness, completeness, accuracy);
- Discoverability in the catalog;
- Explicit consumer interface;
- Deprecation policy.

ODPS v1.0.0 (Bitol / Linux Foundation, 2025) codifies the spec.

Use as soon as a dataset has consumers beyond its creator. The discipline:
**every consumable dataset has an accountable owner; deprecation is a
planned event**.

Anti-pattern: anonymous tables in `prod.analytics.*` with no documented
owner, freshness SLA, or contract — discoverable only by searching git
blame.

---

## 4. LLM-Assisted Data Engineering

This area is the newest and most consequential for the discipline skill,
because the skill is consumed by an LLM-driven workflow. The core empirical
insight from 2024–2026 writeups: **LLMs do not produce correct code; they
produce plausible code**. The failure mode is silent semantic drift, not
loud syntactic error.

### Documented failure modes

**"Plausible but wrong" code.** Compiles, runs, looks right on the happy
path. Silently returns wrong row counts, drops rows, coarsens groupings
under specific data conditions. SQL is especially dangerous because failures
don't throw — they return believable numbers.

**Schema / semantic drift across migrations.** Tian Pan (April 2026)
documents a representative case: a column renamed `last_login_date →
last_activity_ts` with expanded semantics (to include API calls) silently
breaks downstream LLM-generated queries that have no awareness of the
change. Pan's taxonomy: renames, semantic shifts (units changed but name
unchanged), enum expansions (new values bucketed wrong), type changes.

**"Improving while migrating."** LLMs default to "improving" code during
migration — renaming for clarity, refactoring for elegance, simplifying
logic — without consumer alignment. Datafold's Migration Agent
documentation explicitly calls out the mitigation: bug-for-bug parity is
the migration success criterion; "code that compiles" is not equivalent
to "code that produces the same data."

**Synthetic fixtures pass, real data fails.** LLM-generated unit tests
test the same logic the LLM wrote against fixtures the LLM also generated.
High test counts; low real-world coverage.

**Context truncation / plan drift.** In multi-turn migrations, the
conversational summary becomes the source of truth instead of the code.
The agent loses track of which columns were in the original contract and
confidently produces code aligned with the summary.

**Confabulated signatures and identifiers.** Function signatures, parameter
names, calendar identifiers, schema names — guessed from training-data
priors rather than looked up. Caught at runtime, not at integration
boundary.

Monte Carlo's "Data Quality Statistics & Insights From Monitoring +11
Million Tables In 2025" reports the platform resolves more than 1,000 data
quality incidents per day. Dominant root causes: pipeline execution faults
(26.2%), real-world variation (20%), intentional changes such as
backfilling (14.2%).

### CLAUDE.md / AGENTS.md as the discipline layer

A repository-root markdown file encoding project-specific conventions,
constraints, and "sharp edges" the agent must respect. The agent reads it
before any work in the repo. Pádraic Slattery (Xebia, April 2026) frames
it as "onboarding documentation for your AI pair programmer — similar in
spirit to dbt-bouncer's conventions, written in natural language."

Typical contents:

- Naming conventions (`stg_<source>__<entity>`, `int_<entity>`, `dim_`,
  `fct_`);
- SQL style (snake_case, one column per line, CTEs over subqueries,
  `source → renamed → select` staging pattern);
- Materialization rules per layer;
- Required test packages and conventions;
- "Never target production" guardrails (Weld's pattern: explicit dev target
  in `profiles.yml`, note in CLAUDE.md).

Glen Rhodes' refinement (via Bharuka Shraddha): place **local CLAUDE.md
files near risky modules** (auth, billing, contracted models, migrations)
so the model receives the right constraint information at the moment it
needs it. Global CLAUDE.md for project-wide rules; local CLAUDE.md for
high-risk subdirectories.

### The "Read → Write → Build → Verify" loop

Altimate AI's open-source data engineering skills (January 2026) codify
the workflow:

1. **Read existing similar models first.** Convention discovery is
   non-optional. The number-one source of agent errors is mismatched
   conventions; reading 2–3 existing models first eliminates most of
   them.
2. **Run `dbt build` after creating models — `dbt compile` is not enough.**
   Compile catches syntax; build catches contract violations, test
   failures, materialization errors.
3. **Verify output after build using `dbt show`.** Actually inspect the
   produced rows.
4. **If build fails 3+ times, stop and reassess.** Loop-thrashing is a
   signal that the approach is wrong, not that the next iteration will
   succeed.

### MCP servers as tool-bounded execution

**dbt-mcp (dbt Labs, April 2025).** Official MCP server exposing `build`,
`compile`, `list`, `parse`, `get_lineage_dev`, `get_node_details_dev`,
`get_column_lineage` (with dbt-lsp), `generate_model_yaml`,
`generate_staging_model`, `query_metrics`, `text_to_sql`. dbt Labs
explicitly cautions: freeform SQL "bypasses dbt's semantic safeguards.
Uncontrolled use can lead to incorrect results and costly warehouse
queries. dbt Labs recommends limiting SQL tools to sandbox environments."

**Snowflake Cortex Code + hooks.** Snowflake's Cortex AI Guardrails detect
prompt injection and jailbreak attempts. Cortex Code Hooks enforce
SQL-shape concerns (no `SELECT *` without filter), time-window rules (no
DDL outside change windows), and PII boundaries. As Saurabh Kumar's writeup
frames it: "RBAC answers 'is this principal allowed?' Hooks answer 'is
this the right action right now, given the context?'"

**Databricks Genie Code.** Built-in approval gating before table-modifying
code; Unity Catalog as governance foundation; native revision-history
rollback.

### Verification as a non-negotiable done-gate

Bauplan Labs (March 2026) describes the canonical pattern for LLM-driven
migrations: **two verification loops** that gate "done":

1. **Inner loop:** row-by-row comparison between the agent's working-branch
   tables and source-warehouse tables.
2. **Outer loop:** extract query plans from both engines (e.g., SQL and
   Polars), then ask a **separate** LLM to verify plan equivalence — "this
   reduces the risk that the tables match for the wrong reasons."

Bauplan's framing: "The migration succeeded because the agent could fail
freely. For ~200 turns, it wrote broken pipelines, produced mismatched
schemas, and generated incorrect transformations. Every one of those
failures was safe. Every one of them made the next attempt better."
Git-for-data (branchable, revertible lake state) makes safe iteration
possible.

**Datafold Migration Agent** productizes the same pattern: legacy code is
translated to the new dialect, tested for accuracy, and the agent
fine-tunes itself until parity matches.

### The "LLM as junior engineer" framing — and where it breaks

Transferable patterns: code review, conventions docs, pre-commit hooks,
CI gates, pair programming.

Where the analogy breaks:

- A junior engineer has **shame** about silent breakage; an LLM has none.
- A junior engineer **escalates** when uncertain; an LLM confabulates with
  the same fluent confidence.
- A junior engineer **remembers** yesterday's conversation; an LLM's
  context window forgets.

The corrective: **make the discipline mechanical, not social**. Schema-
diff in CI, row-level parity gates, contract enforcement, hooks. Do not
rely on the agent to "know better."

### Continue.dev and `.continue/rules/*.md`

Continue.dev supports project-specific rules in `.continue/rules/*.md`
with YAML frontmatter (`name`, `globs`, `alwaysApply`, `description`).
Glob-based rules let you inject dbt-specific conventions only when editing
`models/**/*.sql`, preventing prompt-context pollution.

Use when working in Continue.dev specifically; the pattern (layer-specific
instruction injection, team-level config sharing) is portable to other
agents via similar mechanisms (Cursor rules, Claude Code per-directory
CLAUDE.md).

---

## Sources and recency notes

- dbt contracts and tests: current as of dbt-core 1.9+ (early 2026).
- dbt unit tests: dbt-core 1.8+, May 2024.
- ODCS: v3.1.0, December 2025, under Linux Foundation Bitol project.
- Great Expectations: v1.0+, August 2024 (pre-1.0 patterns do not apply).
- Soda: classic anomaly check deprecated; 2025 rebuild announced at
  Databricks AI Summit is current.
- Beauchemin's *Functional Data Engineering*: January 8, 2018. Still the
  foundational frame; restated by Packkildurai (*Data Engineering Weekly*).
- OpenLineage: LF AI & Data graduate project, 1.x stable, broadly adopted.
- Medallion: earliest public reference June 2, 2020 (Databricks blog).
  Critiques (Lakshmanan, Packkildurai) from 2024–2026.
- Data Mesh: Dehghani's original blog post, May 2019. Adoption moderated
  2024–2026; patterns persist without full org redesign.
- LLM-assisted patterns: rapidly evolving; the patterns documented here
  reflect Q1–Q2 2026 and will consolidate further.

Vendor-published patterns (Bauplan, Datafold Migration Agent, Altimate
Skills, dbt Labs MCP, Monte Carlo's documented incident analysis)
describe replicable engineering patterns but contain marketing framing —
quoted benchmarks should be treated as vendor claims, not independent
measurements.

# Parity Recipes — Concrete Diff Implementations

Reusable patterns for proving that two datasets match. Use these when
implementing the parity gate for a migration, refactor, or backfill;
when investigating downstream breakage; or when wiring a CI check that
detects schema or value drift.

Each recipe is independently usable. Pick the recipe that matches your
stack and the level of strictness your scenario requires.

The recipes are organized in roughly the order you'd run them: cheapest
checks first (schema), then row count and group cardinality, then
aggregates, then row-level value matching.

---

## Strictness ladder

When in doubt, run all of them in order. Each catches a different class
of regression.

| Layer | What it catches | Cost |
|-------|----------------|------|
| Schema diff | Column adds/drops/renames, dtype changes | Microseconds |
| Row count | Group cardinality changes, dropped/added rows in bulk | Seconds |
| Group cardinality | Coarsened or refined groupings | Seconds |
| Per-column null rate | Constraint violations, branch logic changes | Seconds |
| Aggregate sums | Numeric drift, off-by-one row, dtype precision shifts | Seconds |
| Distributional checks | Subtle systematic shifts in distributions | Minutes |
| Row-level value match (sampled) | Single-row computation errors, value transformations | Minutes |
| Row-level value match (exhaustive) | The strictest gate; catches anything | Minutes-to-hours |
| Contract fingerprint (identity pin) | Any drift in a sealed surface, across commits / waves | Microseconds |

Two checks below the ladder govern whether any rung above can be trusted —
they are not strictness levels but preconditions for believing a green
result: **Recipe 12 (cover every unit, not a sample)** ensures the gate's
*coverage* is complete, and **Recipe 13 (prove the check can fail)** ensures
the gate is *non-vacuous*. A check that is strict but covers a sample, or
strict but never proven red, is still a green light over an unverified
surface.

---

## Recipe 1 — Schema diff

### 1a. Polars

```python
import polars as pl
from typing import NamedTuple

class SchemaDiff(NamedTuple):
    missing_in_new: set[str]
    extra_in_new: set[str]
    dtype_changes: dict[str, tuple[pl.DataType, pl.DataType]]

def schema_diff(baseline: pl.DataFrame, new: pl.DataFrame) -> SchemaDiff:
    baseline_cols = set(baseline.columns)
    new_cols = set(new.columns)
    common = baseline_cols & new_cols
    return SchemaDiff(
        missing_in_new=baseline_cols - new_cols,
        extra_in_new=new_cols - baseline_cols,
        dtype_changes={
            c: (baseline.schema[c], new.schema[c])
            for c in common
            if baseline.schema[c] != new.schema[c]
        },
    )

diff = schema_diff(baseline, new)
assert not diff.missing_in_new, f"missing columns: {diff.missing_in_new}"
assert not diff.extra_in_new, f"unexpected columns: {diff.extra_in_new}"
assert not diff.dtype_changes, f"dtype changes: {diff.dtype_changes}"
```

### 1b. SQL (Snowflake / BigQuery / Postgres / DuckDB)

```sql
-- Drop any rows that match exactly; whatever remains is divergent
WITH baseline_schema AS (
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'prod' AND table_name = 'baseline_output'
),
new_schema AS (
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'prod' AND table_name = 'new_output'
)
SELECT 'missing in new' AS diff_type, column_name FROM baseline_schema
EXCEPT
SELECT 'missing in new', column_name FROM new_schema
UNION ALL
SELECT 'extra in new', column_name FROM new_schema
EXCEPT
SELECT 'extra in new', column_name FROM baseline_schema
UNION ALL
SELECT 'dtype changed', l.column_name
FROM baseline_schema l JOIN new_schema n USING (column_name)
WHERE l.data_type <> n.data_type;
```

### 1c. dbt (using contracts)

Declare the contract in `schema.yml`:

```yaml
models:
  - name: new_output
    config:
      contract:
        enforced: true
    columns:
      - name: trade_date
        data_type: date
        constraints: [{type: not_null}]
      - name: amount
        data_type: numeric(18, 4)
```

The build fails before materialization if the model's output doesn't
match.

---

## Recipe 2 — Row count and group cardinality

```python
# Polars
def cardinality_check(
    baseline: pl.DataFrame,
    new: pl.DataFrame,
    group_keys: list[str],
    tolerance: float = 0.0,
) -> None:
    """Raises AssertionError on cardinality mismatch."""
    n_baseline = baseline.height
    n_new = new.height
    delta = abs(n_baseline - n_new) / max(n_baseline, 1)
    assert delta <= tolerance, (
        f"row count delta {delta:.4%} exceeds tolerance {tolerance:.4%}: "
        f"baseline={n_baseline}, new={n_new}"
    )

    g_baseline = baseline.select(group_keys).unique().height
    g_new = new.select(group_keys).unique().height
    assert g_baseline == g_new, (
        f"group cardinality mismatch on {group_keys}: "
        f"baseline={g_baseline}, new={g_new}"
    )
```

```sql
-- SQL
WITH counts AS (
    SELECT 'baseline' AS src, COUNT(*) AS n_rows,
           COUNT(DISTINCT (key_a, key_b, key_c)) AS n_groups
    FROM baseline_output WHERE partition_date = '2026-05-26'
    UNION ALL
    SELECT 'new', COUNT(*),
           COUNT(DISTINCT (key_a, key_b, key_c))
    FROM new_output WHERE partition_date = '2026-05-26'
)
SELECT * FROM counts;
-- Compare n_rows and n_groups across the two sources.
```

> **Dialect note.** `COUNT(DISTINCT (a, b, c))` over a tuple is **not portable** —
> BigQuery and PostgreSQL reject it. On those engines, hash the keys first, e.g.
> `COUNT(DISTINCT a || '|' || b || '|' || c)` using a separator that cannot appear
> in the values (or `COUNT(DISTINCT FARM_FINGERPRINT(...))` on BigQuery).

---

## Recipe 3 — Per-column null rate

```python
def null_rate_diff(
    baseline: pl.DataFrame,
    new: pl.DataFrame,
    tolerance: float = 1e-6,
) -> dict[str, tuple[float, float]]:
    common = set(baseline.columns) & set(new.columns)
    drift = {}
    for col in common:
        l_rate = baseline[col].null_count() / baseline.height
        n_rate = new[col].null_count() / new.height
        if abs(l_rate - n_rate) > tolerance:
            drift[col] = (l_rate, n_rate)
    return drift

drift = null_rate_diff(baseline, new)
assert not drift, f"null-rate drift: {drift}"
```

---

## Recipe 4 — Aggregate sums

```python
def aggregate_diff(
    baseline: pl.DataFrame,
    new: pl.DataFrame,
    numeric_cols: list[str],
    rel_tol: float = 1e-9,
) -> dict[str, tuple[float, float, float]]:
    """Returns {col: (baseline_sum, new_sum, relative_delta)} for any drift."""
    drift = {}
    for col in numeric_cols:
        baseline_sum = float(baseline[col].sum())
        n_sum = float(new[col].sum())
        if baseline_sum == 0 and n_sum == 0:
            continue
        rel_delta = abs(baseline_sum - n_sum) / max(abs(baseline_sum), abs(n_sum), 1e-12)
        if rel_delta > rel_tol:
            drift[col] = (baseline_sum, n_sum, rel_delta)
    return drift
```

For SQL:

```sql
SELECT
    'baseline' AS src,
    SUM(amount) AS total_amount,
    SUM(revenue) AS total_revenue,
    COUNT(*) AS n_rows
FROM baseline_output WHERE partition_date = '2026-05-26'
UNION ALL
SELECT 'new', SUM(amount), SUM(revenue), COUNT(*)
FROM new_output WHERE partition_date = '2026-05-26';
```

For dbt: `dbt-utils.equal_rowcount` and `dbt-audit-helper` provide
production-ready macros for these checks.

---

## Recipe 5 — Row-level value match (sampled)

When exhaustive row-level comparison is too expensive, sample.

```python
import polars as pl

def sampled_row_diff(
    baseline: pl.DataFrame,
    new: pl.DataFrame,
    key_cols: list[str],
    value_cols: list[str],
    sample_n: int = 10_000,
    rel_tol: float = 1e-9,
    seed: int = 42,  # Pin the seed for reproducibility
) -> pl.DataFrame:
    """Return rows where baseline and new disagree."""
    # Join on keys
    joined = (
        baseline.select(key_cols + value_cols)
        .rename({c: f"{c}__baseline" for c in value_cols})
        .join(
            new.select(key_cols + value_cols)
            .rename({c: f"{c}__new" for c in value_cols}),
            on=key_cols,
            how="full",
        )
    )
    # Sample
    sampled = joined.sample(n=min(sample_n, joined.height), seed=seed)

    # Find disagreements
    diffs = []
    for col in value_cols:
        l_col = f"{col}__baseline"
        n_col = f"{col}__new"
        delta = (sampled[l_col] - sampled[n_col]).abs()
        rel_delta = delta / sampled[l_col].abs().clip(lower_bound=1e-12)
        bad = sampled.filter(rel_delta > rel_tol)
        if bad.height > 0:
            diffs.append((col, bad))

    return diffs
```

---

## Recipe 6 — Row-level value match (exhaustive)

The strictest gate. Use for small enough datasets that full comparison is
feasible.

```python
import polars as pl

def exhaustive_row_diff(
    baseline: pl.DataFrame,
    new: pl.DataFrame,
    key_cols: list[str],
    rel_tol: float = 1e-9,
) -> None:
    """Assert that baseline and new are equal row-by-row."""
    # Sort both by keys to ensure consistent ordering
    baseline_sorted = baseline.sort(key_cols)
    new_sorted = new.sort(key_cols)
    # Polars has a built-in assertion with float tolerance
    pl.testing.assert_frame_equal(
        new_sorted,
        baseline_sorted,
        check_exact=False,
        rel_tol=rel_tol,
        check_dtypes=True,  # renamed from check_dtype in Polars 0.20.31
        check_column_order=False,
    )
    # Polars has renamed these kwargs across versions: rtol -> rel_tol (1.32.3) and
    # check_dtype -> check_dtypes (0.20.31). This IS Principle 8 in action — verify
    # the real signature against your installed Polars with
    # inspect.signature(pl.testing.assert_frame_equal); don't trust a remembered name.
```

For SQL warehouses:

```sql
-- EXCEPT-based exhaustive check
-- Returns rows in baseline that aren't in new (with any column difference)
SELECT * FROM baseline_output
EXCEPT
SELECT * FROM new_output
LIMIT 100;  -- Cap for review

-- And the reverse: rows in new that aren't in baseline
SELECT * FROM new_output
EXCEPT
SELECT * FROM baseline_output
LIMIT 100;
```

dbt-audit-helper provides `compare_relations` and `compare_column_values`
macros that bundle these patterns with reporting.

---

## Recipe 7 — Multi-partition parity check

For migrations, run the parity gate across multiple partitions to catch
calendar-sensitive bugs (month-end, year-end, leap days).

```python
def multi_partition_parity(
    baseline_table: str,
    new_table: str,
    partition_dates: list[str],
    conn,  # warehouse connection
    key_cols: list[str],
    numeric_cols: list[str],
) -> dict[str, dict]:
    """Run parity checks across a list of partition dates."""
    results = {}
    for date in partition_dates:
        baseline_df = pl.read_database(
            f"SELECT * FROM {baseline_table} WHERE partition_date = '{date}'",
            conn,
        )
        new_df = pl.read_database(
            f"SELECT * FROM {new_table} WHERE partition_date = '{date}'",
            conn,
        )
        results[date] = {
            "schema_diff": schema_diff(baseline_df, new_df),
            "cardinality": cardinality_check(baseline_df, new_df, key_cols),
            "aggregates": aggregate_diff(baseline_df, new_df, numeric_cols),
        }
    return results

# Recommended partition set for migration parity:
# - Most recent week (typical case)
# - Last month-end (calendar edge)
# - Last year-end (calendar + dtype edge)
# - One partition with known historical anomalies (regression coverage)
```

---

## Recipe 8 — Replay idempotency check

Tests that re-running a partition produces the same output (Principle 12).

```python
def replay_idempotency(
    pipeline_fn,
    inputs: dict,
    partition_key: str,
    n_runs: int = 2,
) -> None:
    """Run the pipeline n times; assert outputs are identical."""
    outputs = [pipeline_fn(inputs, partition_key=partition_key)
               for _ in range(n_runs)]
    for i in range(1, n_runs):
        pl.testing.assert_frame_equal(
            outputs[0], outputs[i],
            check_exact=True,  # idempotency means exact match
        )
```

For SQL incremental models, the equivalent is:

```sql
-- Run the incremental merge twice; row count must not change
SELECT COUNT(*) FROM target_table WHERE partition_date = '2026-05-26';
-- (run the merge)
SELECT COUNT(*) FROM target_table WHERE partition_date = '2026-05-26';
-- counts must match
```

---

## Recipe 9 — Constraint pre-flight against production data

Tests that a proposed schema constraint is actually satisfiable by
production data (Principle 10).

```sql
-- Run before declaring `nullable: false`
SELECT
    SUM(CASE WHEN uc IS NULL THEN 1 ELSE 0 END) AS null_count_uc,
    SUM(CASE WHEN margin IS NULL THEN 1 ELSE 0 END) AS null_count_margin
FROM production_table
WHERE partition_date >= CURRENT_DATE - INTERVAL '90 days';
-- If null_count > 0, you cannot declare nullable: false on that column.

-- Run before declaring `ge: 0`
SELECT
    SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) AS neg_count_amount,
    SUM(CASE WHEN amount = 0 THEN 1 ELSE 0 END) AS zero_count_amount
FROM production_table
WHERE partition_date >= CURRENT_DATE - INTERVAL '90 days';
-- If neg_count > 0, ge: 0 is too strict.

-- Run before declaring an enum constraint
SELECT DISTINCT status FROM production_table
WHERE partition_date >= CURRENT_DATE - INTERVAL '90 days';
-- The declared enum must include every value seen.
```

---

## Recipe 10 — CI wiring

A typical CI gate runs schema diff + sampled row-level diff on every PR.

```yaml
# .github/workflows/parity.yml
name: parity-check
on: [pull_request]
jobs:
  parity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install polars dbt-core pyarrow
      - name: dbt build (CI target)
        run: |
          dbt run --target ci --select state:modified+ \
              --state ./prod-manifest
      - name: Schema diff
        run: python ci/schema_diff.py --baseline ./baseline.json
      - name: Sampled row-level diff
        run: |
          python ci/sampled_row_diff.py \
              --baseline prod__baseline.output \
              --new ci__new.output \
              --sample-n 10000 \
              --rel-tol 1e-9
```

For dbt-specific projects, `dbt-checkpoint` and `dbt-audit-helper`
provide turnkey alternatives.

---

## Recipe 11 — Contract fingerprint (byte-stable surface token)

A fingerprint reduces an entire contract surface — the schema, the declared
constraints, the set of participating datasets, or the full output of a
deterministic build — to a single hash. Two builds that should be identical
produce the same token; any drift, however small, changes it. Unlike the
row-level recipes, a fingerprint is cheap to store and compare across commits,
which makes it the right tool for a *parity pin* (freeze the agreed shape so it
can't silently change — Scenario 9) and a *release re-seal* (prove
independently-merged waves still compose to the same surface — Scenario 10).

```python
import hashlib
import json
import polars as pl

def contract_fingerprint(df: pl.DataFrame) -> str:
    """A byte-stable token over a dataset's contract surface: columns, dtypes,
    and the canonically-ordered data. Deterministic across runs."""
    schema = sorted((name, str(dtype)) for name, dtype in df.schema.items())
    # Canonical ordering so row/column order can't change the token.
    body = df.select(sorted(df.columns)).sort(sorted(df.columns)).write_csv()
    payload = json.dumps({"schema": schema, "rows": df.height}, sort_keys=True) + body
    return hashlib.sha256(payload.encode()).hexdigest()

# Pin: store the token at the agreed / sealed commit, checked into the repo.
SEALED = "a1b2c3..."
assert contract_fingerprint(build_output()) == SEALED, "contract surface drifted"
```

For a *set* of datasets (a multi-wave surface), fingerprint each and hash the
sorted `(name, token)` pairs into one surface token:

```python
def surface_token(outputs: dict[str, pl.DataFrame]) -> str:
    parts = sorted((name, contract_fingerprint(df)) for name, df in outputs.items())
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
```

For SQL warehouses, the equivalent is a deterministic digest over the ordered
output:

```sql
-- DuckDB / Snowflake: a digest over the sorted result rows
SELECT md5(string_agg(row_text, '\n' ORDER BY row_text)) AS surface_token
FROM (
    SELECT concat_ws('|', key_a, key_b, cast(amount AS varchar)) AS row_text
    FROM new_output WHERE partition_date = '2026-05-26'
);
```

**Usage notes.**

- A fingerprint proves *identity*, not *correctness* — it says the surface is
  byte-for-byte what you sealed, not that the sealed value was right. Seal only
  after a value-level gate (Recipe 4 or 6) has passed once.
- Make the input canonical (sort rows and columns; pin float formatting) or the
  token churns on benign reorderings and loses its signal. A token that flaps is
  a token everyone ignores.
- Recompute in a clean room — a fresh build from source, not from cache — when
  using the token to prove no silent drift across a release (Scenario 10). A
  token recomputed from stale cache only proves the cache didn't change.

---

## Recipe 12 — Cover every unit, not a sample

A parity gate can be non-vacuous in *method* — it really diffs, it really
fails on a mismatch — and still hollow in *coverage*: it pins a
representative handful of the migrated columns, rerouted operations, or
swapped inputs and leaves the rest unchecked. The one unit you don't diff
is the one that drifted. "Preserve behavior" carries an unstated quantifier:
*every* unit, enumerated against the source-of-truth registry, not a
plausible sample.

The defense is to derive the complete set mechanically — from the registry,
the dispatch table, the column list, the set of rerouted ops — and assert
the gate covers all of it, rather than hand-picking cases the author
happened to think of.

```python
# The gate's coverage is itself a checkable claim. Enumerate the complete
# set from the source of truth, then assert the parity gate touches each one.
from mylib.dispatch import REGISTERED_OPS  # the source-of-truth registry

covered = set(parity_cases.keys())          # what the gate actually checks
expected = set(REGISTERED_OPS)              # what it must check
missing = expected - covered
assert not missing, f'parity gate omits {len(missing)} units: {sorted(missing)}'
```

The same shape applies to a mechanism swap (the CONSUMER-SWAP framing):
when a wave replaces one data-access mechanism with another, enumerate
exactly which inputs the OLD mechanism reads / refreshes and which the NEW
one does, and diff the *sets*. A superset on the new path (it reads an input
the old one never did) is a behavior change, not parity — and a coverage
check over a sample will not see it, because the extra input simply isn't in
the sample.

```python
old_inputs = inputs_read_by(old_mechanism)   # enumerate, don't assume
new_inputs = inputs_read_by(new_mechanism)
assert old_inputs == new_inputs, (
    f'input set changed: only-old={old_inputs - new_inputs}, '
    f'only-new={new_inputs - old_inputs}'
)
```

**Usage notes.**

- "We checked the tricky ones" is sampling by another name. The registry,
  not intuition about which units are risky, defines the complete set.
- Make the completeness assertion fail loudly when a *new* unit is added
  upstream but not wired into the gate — that turns a silent coverage gap
  into a red build the day the unit appears.

---

## Recipe 13 — Prove the check can fail before trusting it green

A parity check that has only ever been seen green proves nothing: green can
mean "the outputs match" or "the check never actually compared anything." A
typo in a join key, a filter that drops both sides to empty, a tolerance set
so wide nothing trips it, a fixture that exercises a fallback path instead of
the unit under test — each yields a passing check that verifies nothing. The
discipline that separates a real gate from a green light is the same one
Scenario 8 applies to enforcement gates: **prove it red first.** Plant a
known divergence, watch the check catch it, then remove the plant and trust
the green.

```python
def test_parity_check_is_not_vacuous():
    """The parity gate must fail on a planted divergence — else green is meaningless."""
    baseline = load_baseline()
    perturbed = baseline.with_columns(
        (pl.col('amount') + 0.01).alias('amount')  # one cell, deliberately wrong
    )
    try:
        run_parity_gate(baseline, perturbed)
    except AssertionError:
        return  # good: the gate caught the planted divergence
    raise AssertionError('parity gate passed on a planted divergence — it is vacuous')
```

**Usage notes.**

- The plant must be a divergence the gate *should* catch — a value off by
  more than the tolerance, a missing row, a renamed column — not noise below
  the tolerance floor (that would prove the opposite of what you want).
- Watch especially for the fixture that satisfies the check via the wrong
  path: when a change adds an eligibility / participation guard, the headline
  fixture must be a *participating* instance, or the check passes through the
  fallback and never exercises the new logic. The red-first plant surfaces
  this — a vacuous fixture stays green even when you perturb the value the
  gate claims to protect.
- For a "verbatim move" refactor, the red-first analog is to diff the
  *actual* relocated body against `HEAD` (e.g. `git show HEAD:path | ...`),
  not a mental model of what moved. The deltas a mental model forgets — a log
  line that now needs a local, a module-level import the moved block relied
  on — are exactly what the byte diff surfaces.

---

## Recipe 14 — Freshness / watermark advance (incremental loads)

Schema, parity, and contract checks are all invariant under *staleness*: a run
that re-writes structurally identical, aggregate-identical rows with a frozen
cursor passes every recipe above. Freshness is an orthogonal axis. The failure
this catches: a cache builds once under a default `if_missing` and never
re-pulls, so `max(cursor)` is frozen while the run self-reports `success: true`.

Assert the watermark moved — never trust the pipeline's self-reported success:

```bash
# stuck cursor (built once, never re-pulled) -> STALE, exit 1
python freshness_check.py --prev "$PREV_MAX" --curr "$CURR_MAX" --source "$SOURCE_MAX"
```

```python
from freshness_check import check_freshness, check_freshness_groups

# Single global watermark — the floor check (ok=False if frozen or behind source).
rep = check_freshness(prev_max, curr_max, source_max)
assert rep['ok'] is True, rep['reason']
```

A global `max(cursor)` is **necessary, not sufficient** — it is blind to
per-partition staleness (one tenant frozen while the global max advances) and to
a watermark that advances while rows below it were skipped. Two companions:

```python
# Per-partition freshness: one frozen partition fails the aggregate.
groups = [{'group': k, 'prev': prev[k], 'curr': curr[k]} for k in partitions]
rep = check_freshness_groups(groups)
assert rep['ok'] is True, f'stale partitions: {rep["stale"]}'
```

```sql
-- Row-count-per-watermark-bucket: catches "watermark advanced but rows skipped".
-- Any nonzero delta between source and output counts per bucket is a gap.
SELECT bucket, src_n, out_n, coalesce(src_n, 0) - coalesce(out_n, 0) AS missing
FROM (SELECT date_trunc('hour', cursor) AS bucket, count(*) src_n FROM source GROUP BY 1) s
FULL JOIN (SELECT date_trunc('hour', cursor) AS bucket, count(*) out_n FROM output GROUP BY 1) o
  USING (bucket)
WHERE coalesce(src_n, 0) <> coalesce(out_n, 0);
```

Cursors must be a comparable type (int / date / datetime). `freshness_check`
rejects a string cursor (`'9' > '10'` mis-orders; unpadded ISO dates mis-order)
and a tz-aware-vs-naive mix as `uncomparable` rather than comparing them wrongly,
and returns `ok=None` ("unknown") when it has neither a prior snapshot nor a
source max — never a silent pass.

---

## Choosing the right strictness

| Scenario | Recommended recipes |
|----------|---------------------|
| Migration cutover | 1, 2, 3, 4, 6 (exhaustive), 7, 8 |
| Refactor (no functional change) | 1, 2, 4, 6 (exhaustive) |
| New dataset (first ship) | 1, 9, 3 (against expected nulls) |
| Schema evolution (additive) | 1 only |
| Schema evolution (breaking) | 1 + version-bump validation |
| Backfill | 2, 4, 8 against full-recompute |
| Incremental load smoke test | 1, 8, 14 |
| Investigating downstream breakage | 1, 4, 5 across the change window |
| Contract repair to shipped reality (Scenario 9) | 1, 4, 11 (pin the repaired surface) |
| Release cut / multi-wave assembly (Scenario 10) | 1, 4, 6, 11 (re-seal in a clean room) |

---

## What these recipes do not catch

Be honest about the gaps. Parity recipes are powerful but not omniscient.

- **Subtle distributional shifts** within tolerance (e.g., a small change
  in float precision that doesn't trigger the rel_tol gate but produces
  a different result downstream when chained through many transforms).
- **Semantic shifts under the same name** — if `last_login_date` is
  renamed to `last_activity_ts` AND its meaning is broadened to include
  API calls, parity against the *renamed* column will hide the semantic
  change. Detection requires consumer-impact analysis, not just diff.
- **Issues outside the sampled partitions.** Sample-based recipes can
  miss regressions that only happen on specific dates or specific data
  conditions. Multi-partition checks (Recipe 7) help; exhaustive checks
  are the only guarantee.
- **Performance regressions** — these recipes verify correctness, not
  cost or speed. A pipeline that's correct but 10× slower is still a
  regression.
- **Upstream source drift** — these recipes compare two pipelines against
  their respective inputs. If the upstream source has drifted, both
  pipelines may agree on the (wrong) new shape.
- **Staleness beyond the global watermark** — Recipe 14's `max(cursor)` check
  confirms the watermark moved, not that every partition advanced or that no
  rows below the mark were skipped (use per-group + row-count-per-bucket).
  Soft-deletes and late-arriving data below the watermark are invisible to a
  max-cursor check.

The pre-shipping checklist in `SKILL.md` covers more than parity. Parity
is necessary; the checklist asserts it's sufficient.

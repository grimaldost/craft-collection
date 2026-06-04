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
        check_dtype=True,
        check_column_order=False,  # but check_dtype catches col-level dtype shifts
    )
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
    SUM(CASE WHEN cof IS NULL THEN 1 ELSE 0 END) AS null_count_cof,
    SUM(CASE WHEN take_rate IS NULL THEN 1 ELSE 0 END) AS null_count_take_rate
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

## Choosing the right strictness

| Scenario | Recommended recipes |
|----------|---------------------|
| Migration cutover | 1, 2, 3, 4, 6 (exhaustive), 7, 8 |
| Refactor (no functional change) | 1, 2, 4, 6 (exhaustive) |
| New dataset (first ship) | 1, 9, 3 (against expected nulls) |
| Schema evolution (additive) | 1 only |
| Schema evolution (breaking) | 1 + version-bump validation |
| Backfill | 2, 4, 8 against full-recompute |
| Incremental load smoke test | 1, 8 |
| Investigating downstream breakage | 1, 4, 5 across the change window |

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

The pre-shipping checklist in `SKILL.md` covers more than parity. Parity
is necessary; the checklist asserts it's sufficient.

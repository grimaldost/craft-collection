# Contract Templates

Worked templates for declaring a data contract. The same dataset
expressed four ways:

1. **dbt `schema.yml`** — for in-warehouse models managed by dbt.
2. **ODCS YAML** — for portable, vendor-neutral contracts (Open Data
   Contract Standard v3.1.0).
3. **Pydantic** — for Python-side schema validation, especially at
   ingestion boundaries.
4. **JSON Schema** — for cross-language schema interchange, often used
   in event streams alongside Avro / Protobuf.

The same example dataset (`dim_customer`) is used across all four, so
you can see how the same semantic shape is expressed in each form. Pick
the form that matches where in the stack you're enforcing the contract.

A complete contract has more than schema. It includes ownership,
freshness SLO, deprecation policy, and quality rules. Each template
below shows the minimum complete shape, not just the column list.

---

## The example dataset: `dim_customer`

Single source of truth for customer dimensional data. Used by the finance
team for reporting and by the analytics team for cohort analysis.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| customer_id | string | no | Surrogate key, format `CUST{10 digits}` |
| customer_natural_id | string | no | Source-system natural key |
| email | string | no | Lower-cased, validated email address |
| company_name | string | no | Trimmed; max 255 chars |
| tier | enum | no | One of `bronze`, `silver`, `gold`, `platinum` |
| signup_date | date | no | Calendar date of account creation |
| last_activity_ts | timestamp | yes | Timestamp of most recent activity (any kind) |
| lifetime_value | numeric(18,2) | no | USD; >= 0 |
| is_active | boolean | no | Currently active (not churned) |
| etl_batch_id | string | no | Provenance: ETL run that produced this row |
| created_at | timestamp | no | Row creation timestamp |
| updated_at | timestamp | no | Row last-modified timestamp |

Primary key: `customer_id`.
Freshness SLO: data available by 06:00 UTC daily.
Owner: data-platform-team.

---

## Template 1 — dbt `schema.yml`

```yaml
version: 2

models:
  - name: dim_customer
    description: >
      Single source of truth for customer dimensional data.
      Used by finance for reporting and by analytics for cohort analysis.
    meta:
      owner: data-platform-team
      slack_channel: '#data-platform'
      freshness_sla: '06:00 UTC daily'
      pii: true
      contract_version: '2.1.0'
    config:
      contract:
        enforced: true
      materialized: table
      tags: ['silver', 'dimensional', 'pii']
    columns:
      - name: customer_id
        data_type: string
        description: 'Surrogate key; format CUST{10 digits}'
        constraints:
          - type: not_null
          - type: primary_key
          - type: unique
        tests:
          - dbt_expectations.expect_column_values_to_match_regex:
              regex: '^CUST[0-9]{10}$'
      - name: customer_natural_id
        data_type: string
        description: 'Source-system natural key'
        constraints:
          - type: not_null
        tests:
          - unique
      - name: email
        data_type: string
        description: 'Lower-cased, validated email address'
        constraints:
          - type: not_null
        tests:
          - dbt_expectations.expect_column_values_to_match_regex:
              regex: '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
      - name: company_name
        data_type: string
        constraints:
          - type: not_null
      - name: tier
        data_type: string
        constraints:
          - type: not_null
        tests:
          - accepted_values:
              values: ['bronze', 'silver', 'gold', 'platinum']
      - name: signup_date
        data_type: date
        constraints:
          - type: not_null
      - name: last_activity_ts
        data_type: timestamp
        description: 'Timestamp of most recent activity (any kind)'
      - name: lifetime_value
        data_type: numeric(18, 2)
        description: 'USD; >= 0'
        constraints:
          - type: not_null
          - type: check
            expression: 'lifetime_value >= 0'
      - name: is_active
        data_type: boolean
        constraints:
          - type: not_null
      - name: etl_batch_id
        data_type: string
        description: 'Provenance: ETL run that produced this row'
        constraints:
          - type: not_null
      - name: created_at
        data_type: timestamp
        constraints:
          - type: not_null
      - name: updated_at
        data_type: timestamp
        constraints:
          - type: not_null

    # Freshness check on the source feeding this model
    # (declared on the upstream source, not the model itself)

    # Versioning block for breaking changes
    latest_version: 2
    versions:
      - v: 1
        deprecation_date: '2026-12-01'
        config:
          alias: dim_customer__v1
      - v: 2
        # current

sources:
  - name: raw_customer
    freshness:
      warn_after: { count: 6, period: hour }
      error_after: { count: 24, period: hour }
    loaded_at_field: ingested_at
    tables:
      - name: customer_events
```

**Key dbt patterns shown.**

- `contract: enforced: true` — fails the build if output doesn't match
  the declared columns and dtypes.
- `meta:` — non-functional metadata (owner, SLA, PII flag, contract version).
  Surfaces in dbt-docs and downstream catalog tools.
- `constraints:` — `not_null`, `primary_key`, `unique`, `check`. dbt's contract
  validates only column names and data types at build; the constraints are pushed
  into the DDL and enforcement is delegated to the warehouse — and most warehouses
  enforce only `not_null` (`check` is warned-and-skipped, `primary_key`/`unique`
  are emitted but not enforced). dbt does NOT validate them at build, so pair the
  contract with a `not_null`/`unique` data test to actually guarantee them.
- `tests:` — runtime data tests run after materialization.
- `versions:` — coexisting model versions during deprecation cycles.
- `dbt_expectations` package — adds regex matching and many other
  Great-Expectations-style assertions.

---

## Template 2 — ODCS YAML (v3.1.0)

```yaml
apiVersion: v3.1.0
kind: DataContract
id: ddb78a82-c8a4-4d49-9c5a-9b76ea0aaca0
name: dim_customer
version: 2.1.0
status: active
domain: customer-data
tenant: data-platform
description:
  purpose: >
    Single source of truth for customer dimensional data.
  usage: >
    Used by finance for reporting and by analytics for cohort analysis.
  limitations: >
    PII; access requires the customer-data-read role.

contractCreatedTs: '2025-11-15T10:00:00Z'

# Schema
schema:
  - name: dim_customer
    physicalName: dim_customer
    physicalType: table
    properties:
      - name: customer_id
        physicalType: string
        logicalType: string
        required: true
        unique: true
        primaryKey: true
        primaryKeyPosition: 1
        examples: ['CUST0000000001']
        pattern: '^CUST[0-9]{10}$'
        description: 'Surrogate key'
      - name: customer_natural_id
        physicalType: string
        logicalType: string
        required: true
        unique: true
      - name: email
        physicalType: string
        logicalType: string
        required: true
        pattern: '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        classification: pii
      - name: company_name
        physicalType: string
        logicalType: string
        required: true
      - name: tier
        physicalType: string
        logicalType: string
        required: true
        validValues: ['bronze', 'silver', 'gold', 'platinum']
      - name: signup_date
        physicalType: date
        logicalType: date
        required: true
      - name: last_activity_ts
        physicalType: timestamp
        logicalType: timestamp
        required: false
      - name: lifetime_value
        physicalType: numeric(18, 2)
        logicalType: number
        required: true
        minimum: 0
      - name: is_active
        physicalType: boolean
        logicalType: boolean
        required: true
      - name: etl_batch_id
        physicalType: string
        logicalType: string
        required: true
        description: 'Provenance: ETL run that produced this row'
      - name: created_at
        physicalType: timestamp
        logicalType: timestamp
        required: true
      - name: updated_at
        physicalType: timestamp
        logicalType: timestamp
        required: true

# Quality rules (executable)
quality:
  - rule: row_count_within_range
    description: 'Daily row count between 100K and 10M'
    dimension: completeness
    severity: error
    businessImpact: operational
    schedule: '0 7 * * *'
    expression: 'COUNT(*) BETWEEN 100000 AND 10000000'
  - rule: pk_unique
    description: 'customer_id must be unique'
    dimension: uniqueness
    severity: error
    expression: 'COUNT(*) = COUNT(DISTINCT customer_id)'
  - rule: ltv_non_negative
    dimension: validity
    severity: error
    expression: 'MIN(lifetime_value) >= 0'

# Service level objectives
slaProperties:
  - property: latency
    value: 6
    unit: hours
    element: dim_customer.updated_at
  - property: retention
    value: 7
    unit: years
  - property: frequency
    value: 1
    unit: day

# Team
team:
  - username: data-platform-team
    role: owner
    name: 'Data Platform Team'
  - username: finance-analytics
    role: consumer

# Roles for access
roles:
  - role: customer-data-read
    access: read
  - role: customer-data-write
    access: write

# Lifecycle
support:
  - channel: '#data-platform'
    tool: slack
    url: 'https://example.slack.com/archives/CXXX'
```

**Key ODCS patterns shown.**

- Portable across vendors — no dbt, Snowflake, or warehouse coupling.
- Quality rules are executable SQL, evaluable by any validator.
- SLA properties are first-class — latency, retention, frequency are
  contract elements, not metadata.
- Team and role declarations are part of the contract.
- Versioning via SemVer (`2.1.0` in this example).

Use ODCS when the contract crosses team or service boundaries, when
multiple consumers need a vendor-neutral spec, or when compliance/audit
needs a portable artifact.

---

## Template 3 — Pydantic

```python
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Optional
from pydantic import BaseModel, Field, EmailStr, ConfigDict


class CustomerTier(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class DimCustomer(BaseModel):
    """Single source of truth for customer dimensional data.

    Contract version: 2.1.0
    Owner: data-platform-team
    Freshness SLO: 06:00 UTC daily
    """

    model_config = ConfigDict(
        frozen=True,        # immutable; protects against accidental mutation
        strict=True,        # no implicit coercion
        extra="forbid",     # reject unexpected fields
    )

    customer_id: Annotated[
        str,
        Field(pattern=r"^CUST[0-9]{10}$", description="Surrogate key"),
    ]
    customer_natural_id: str
    email: EmailStr
    company_name: Annotated[str, Field(min_length=1, max_length=255)]
    tier: CustomerTier
    signup_date: date
    last_activity_ts: Optional[datetime] = None
    lifetime_value: Annotated[Decimal, Field(ge=Decimal(0), decimal_places=2)]
    is_active: bool
    etl_batch_id: Annotated[
        str,
        Field(description="Provenance: ETL run that produced this row"),
    ]
    created_at: datetime
    updated_at: datetime


# Usage at the ingestion boundary
def ingest_customer_row(raw: dict) -> DimCustomer:
    """Parse and validate a raw row. Raises ValidationError on contract drift."""
    return DimCustomer.model_validate(raw)

# Bulk-validate a polars DataFrame
def validate_dataframe(df: pl.DataFrame) -> list[DimCustomer]:
    """Validate every row of a DataFrame against the contract."""
    return [DimCustomer.model_validate(row) for row in df.iter_rows(named=True)]
```

**Key Pydantic patterns shown.**

- `model_config` enforces immutability, strict typing, no-extra-fields.
  These three together prevent the most common silent-drift modes.
- `Annotated` + `Field` for declarative constraints
  (pattern, min/max, decimal_places).
- `EmailStr` and `StrEnum` for stricter typing than raw `str`.
- `Decimal` not `float` for money — float precision is a classic source
  of silent aggregate drift.
- `Optional` is explicit; `None` is not the default.

Use Pydantic when validating data at Python boundaries — ingestion,
inter-service calls, file-loading. It complements rather than replaces
warehouse-side contracts.

---

## Template 4 — JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://contracts.example.com/dim_customer/v2.1.0.json",
  "title": "dim_customer",
  "description": "Single source of truth for customer dimensional data",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "customer_id", "customer_natural_id", "email", "company_name",
    "tier", "signup_date", "lifetime_value", "is_active",
    "etl_batch_id", "created_at", "updated_at"
  ],
  "properties": {
    "customer_id": {
      "type": "string",
      "pattern": "^CUST[0-9]{10}$",
      "description": "Surrogate key"
    },
    "customer_natural_id": {
      "type": "string"
    },
    "email": {
      "type": "string",
      "format": "email"
    },
    "company_name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 255
    },
    "tier": {
      "type": "string",
      "enum": ["bronze", "silver", "gold", "platinum"]
    },
    "signup_date": {
      "type": "string",
      "format": "date"
    },
    "last_activity_ts": {
      "type": ["string", "null"],
      "format": "date-time"
    },
    "lifetime_value": {
      "type": "number",
      "minimum": 0,
      "multipleOf": 0.01
    },
    "is_active": {
      "type": "boolean"
    },
    "etl_batch_id": {
      "type": "string"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

**Key JSON Schema patterns shown.**

- `additionalProperties: false` — reject unexpected fields (the JSON-
  Schema equivalent of Pydantic's `extra: forbid`).
- `required` array — declares which properties are non-null. This is
  the JSON Schema equivalent of Pydantic's `Optional` or ODCS's
  `required: true`.
- `format: email` / `format: date` / `format: date-time` — semantic
  type hints (most validators enforce them).
- `pattern` — regex constraint for strings.
- `multipleOf: 0.01` — coarse decimal-precision constraint.

Use JSON Schema when contracts cross language boundaries (e.g., Python
producer, Java consumer; or REST APIs with multiple language clients).
Pair with Avro or Protobuf for binary-format event streams.

---

## Combining contracts across layers

A common production stack uses several of these together, each at the
layer where it's strongest:

| Layer | Format | Validates |
|-------|--------|-----------|
| Producer service (Python) | Pydantic | Application-side schema before emit |
| Event stream | Avro / Protobuf + Schema Registry | Wire-format schema; BACKWARD compatibility |
| Warehouse landing | dbt `contract: enforced: true` | Materialized output schema |
| Cross-team contract | ODCS YAML | Portable, vendor-neutral spec; SLAs |
| Public API | JSON Schema | Cross-language contract for external consumers |

The same conceptual contract is expressed in different forms at each
layer. The agent should use the form matching the layer where the
enforcement happens — not pick one form to declare across all layers.

---

## Anti-patterns in contract design

**1. Schema-only contracts.**
A contract that declares only columns and dtypes is not enough. It must
include nullability, value constraints (enum, ranges, regex), uniqueness,
freshness SLO, and ownership. Each of these is a separate axis of
silent breakage.

**2. Contracts that drift from code.**
The contract file in git and the actual materialized output diverge.
Defense: enforce the contract in CI (`dbt build` with `contract:
enforced`, ODCS validator, JSON Schema validator).

**3. Implicit semantics.**
A column named `amount` is in cents, not dollars. The contract doesn't
say. Defense: declare semantic units (USD, cents, hours, %, bytes) in
the description. Use type aliases (`MoneyUSD` in Pydantic) to make
units type-level.

**4. Optional everything.**
Every column declared nullable "just in case." Defense: nullability is
a contract assertion. Declare nullable only when production data has
nulls (Principle 10).

**5. No versioning.**
The contract evolves without version bumps; consumers can't tell which
shape they're working against. Defense: SemVer the contract; track
changes in a changelog; use `latest_version` patterns to coexist
versions during transitions.

**6. Quality rules buried in tests.**
The contract YAML declares only structure; quality rules live elsewhere
(dbt tests, custom scripts). Consumers see structure but not quality
expectations. Defense: ODCS's `quality:` block bundles structure and
quality in one artifact.

# Contract Templates

A worked contract for one dataset, plus the field vocabulary and the
completeness checklist that make a contract more than a column list.

The template is **ODCS YAML** (Open Data Contract Standard v3.1.0) because it
is the portable, vendor-neutral form: it crosses team and service boundaries,
carries SLAs and executable quality rules as first-class contract elements,
and needs no warehouse or transformation tool to read. The dbt `schema.yml`,
Pydantic and JSON Schema renderings of the same shape were retired in 2026-08:
a current model writes all three correctly from the field list below, and a
second definition site for the same contract is a drift liability, not a
reference.

A complete contract has more than schema. It includes ownership, freshness
SLO, deprecation policy, and quality rules. The template shows the minimum
complete shape.

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

## The contract: ODCS YAML (v3.1.0)

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

## Which form belongs at which layer

The same conceptual contract is expressed differently depending on where it is
enforced. Use the form matching the layer that enforces it, rather than one
form declared everywhere.

| Layer | Format | Validates |
|-------|--------|-----------|
| Producer service (Python) | Pydantic model | Application-side schema before emit |
| Event stream | Avro / Protobuf + a schema registry | Wire-format schema and its compatibility mode |
| Warehouse landing | dbt `contract: enforced: true` | Materialized output schema |
| Cross-team contract | ODCS YAML | Portable, vendor-neutral spec; SLAs |
| Public API | JSON Schema | Cross-language contract for external consumers |

---

## Compatibility-mode vocabulary

The words a compatibility decision is argued in, stated once so a discussion
does not invent its own. These are the registry modes; a warehouse or catalog
tool renames them but the semantics carry.

| Mode | A new schema may | Who upgrades first |
|---|---|---|
| `BACKWARD` | delete a field, add an OPTIONAL field | consumers |
| `BACKWARD_TRANSITIVE` | same, against EVERY earlier version, not only the last | consumers |
| `FORWARD` | add a field, delete an OPTIONAL field | producers |
| `FORWARD_TRANSITIVE` | same, against every earlier version | producers |
| `FULL` | add or delete an OPTIONAL field only | either |
| `FULL_TRANSITIVE` | same, against every earlier version | either |
| `NONE` | anything - the registry checks nothing | nobody, and that is the point |

Two traps live in this table. The plain (non-transitive) modes check only
against the **immediately preceding** version, so a field deleted in v2 and
re-added with a different meaning in v3 passes `BACKWARD` while breaking a
consumer pinned to v1 - the transitive variants exist for exactly that.
And `NONE` is a real configured mode, not an absence: a registry set to `NONE`
reports success on every change, which is a fail-open gate with a compatibility
label (see `llm-failure-modes.md`, Mode 13).

Transformation tools express the same idea as breaking-change policy levels
rather than modes: a contract-enforced model typically classifies a removed
column, a retype, or a narrowed nullability as breaking, and an added nullable
column as non-breaking, with the enforcement level chosen per model (warn,
error, or the check skipped entirely - the third being the same fail-open shape).

**On adoption.** No independent survey of contract-standard adoption exists.
Treat any claim about "what most teams use" as unsourced, including this file's
choice of ODCS as the worked example: that choice is argued on portability
above, not on a measured install base.

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

# Migration context

The legacy pipeline `revenue_daily` (PySpark, on the old cluster) produces a table
consumed by the **finance dashboard** and a **downstream forecasting model**.

Current output:

- Columns: `date` (date), `region` (string), `gross_revenue_cents` (bigint),
  `net_revenue_cents` (bigint), `order_count` (bigint), `refund_count` (bigint).
- Grain: one row per `(date, region)`. ~18 regions, daily.
- Known convention/quirk: refunds are attributed to the **original order date**,
  not the refund date (a deliberate finance rule). So
  `net_revenue_cents = gross_revenue_cents - (refunds booked against that order date)`.

The ask: move `revenue_daily` to the new warehouse (SQL / dbt) **without changing
what consumers see**.

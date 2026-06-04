# "The numbers changed" report

After yesterday's deploy, the finance dashboard's `net_revenue_cents` for the last
30 days dropped ~6% versus the prior run. Nothing else was supposed to change.

The deploy's diff touched only the `revenue_daily` transform:

```diff
- FROM orders o
- LEFT JOIN refunds r ON r.order_id = o.id
+ FROM orders o
+ INNER JOIN refunds r ON r.order_id = o.id
+ WHERE r.refund_status = 'completed'
```

The `GROUP BY (date, region)` was unchanged. No schema change was announced.

Consumers of this table: the finance dashboard and a forecasting model.

---
name: sql-review
description: Use when reviewing a SQL query before it runs in production — catches accidental fan-out joins, non-idempotent MERGE on an incomplete key, missing partition filters on large tables, and NULL-in-aggregate bugs that silently change the result. Triggers on "review this query", "is this SQL safe to run", "check my MERGE statement", "why is this join returning too many rows".
---

# SQL Review

Before a query ships, check it against the four silent-wrong-answer traps and, for
each, name the specific risk in THIS query and the fix:

1. **Fan-out join** — a join key that is not unique on the right side multiplies rows.
2. **Non-idempotent MERGE** — a MERGE keyed on an incomplete grain double-applies on
   re-run.
3. **Missing partition filter** — a scan over an unpartitioned date range is slow and
   expensive.
4. **NULL in aggregate** — COUNT/SUM silently skip NULLs, changing the result vs intent.

# Ledger service

A small internal service that records account balances and posts transactions.
This fixture is a **populated working directory** for the trigger eval — a
cwd-dependent skill like `corpus-review` fires when it can see a repo's files to
audit, and reads a false 0.00 recall in an empty temp cwd. It is not a real
project; the docs below only need to look like a repo worth reviewing.

## Layout

- `CONTRIBUTING.md` — how to propose a change.
- `architecture.md` — components and data flow.
- `api-reference.md` — the public endpoints.

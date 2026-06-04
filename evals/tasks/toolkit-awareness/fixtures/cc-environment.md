# This Claude Code environment (from the toolkit scan)

Installed and available to a Claude Code session in this repo:

- `/code-review` — reviews the current diff; returns APPROVE or REQUEST_CHANGES.
- `/gate` — runs lint + type-check + tests and reports any blocking failures.
- `/security-review` — scans the pending change for vulnerabilities.
- skill `project-conventions` — owns this repo's coding standards, naming, and
  error-handling rules (the authoritative source).
- skill `api-schema` — resolves the canonical request/response schemas by name.

The work to spec: add a `POST /payments/refund` endpoint that issues a partial
refund and records it, following the repo's conventions.

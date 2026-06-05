# Journal corpus — entries captured across several past sessions

--- ENTRY_START ---
type: FINDING
session: payments-incident-feb
domains: idempotency, retries
--- CONTENT ---
A retry on a non-idempotent POST double-charged a customer: the first request
actually succeeded but its response timed out, so the client retried and the charge
applied twice. The endpoint had no idempotency key, so the server could not tell the
retry from a new request.
--- ENTRY_END ---

--- ENTRY_START ---
type: ANTI_PATTERN
session: webhooks-mar
domains: idempotency, messaging
--- CONTENT ---
Added retries to the webhook sender without idempotency keys. On every transient 503
the downstream consumer received duplicate events — the retry looked reasonable in
isolation but multiplied delivery because nothing de-duplicated on the receiving side.
--- ENTRY_END ---

--- ENTRY_START ---
type: DECISION
session: api-hardening-apr
domains: idempotency, api_design
--- CONTENT ---
Adopted client-supplied idempotency keys on all mutating endpoints after the third
duplicate-write incident this quarter. The server now stores the key and returns the
original result on a repeat, so retries are safe by construction.
--- ENTRY_END ---

--- ENTRY_START ---
type: OBSERVATION
session: onboarding-apr
domains: team
--- CONTENT ---
The new hire preferred reading the runbook to asking in chat. Might be worth keeping
runbooks first-class for onboarding. Only noticed once so far.
--- ENTRY_END ---

--- ENTRY_START ---
type: DECISION
session: module-x-apr
domains: testing
--- CONTENT ---
Decided to write unit tests for the new module before merging.
--- ENTRY_END ---

--- ENTRY_START ---
type: DECISION
session: reporting-db-mar
domains: time, reporting
--- CONTENT ---
Chose to store timestamps as local time in the reporting DB so they match what the BI
tool displays without conversion.
--- ENTRY_END ---

--- ENTRY_START ---
type: DECISION
session: reporting-db-may
domains: time, reporting
--- CONTENT ---
Reversed the local-time storage decision: store all timestamps in UTC and convert at
display time. The local-time choice caused a DST double-count in the October report
(the 2am hour repeated), which silently inflated that day's totals.
--- ENTRY_END ---

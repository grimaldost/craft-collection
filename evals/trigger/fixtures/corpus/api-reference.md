# API reference

- `POST /accounts` — open an account; returns its id.
- `GET /accounts/{id}` — the current balance and last-updated timestamp.
- `POST /transactions` — post a transaction (a debit and a matching credit).
- `GET /transactions/{id}` — the recorded legs and their status.

All amounts are integer minor units. Errors return a problem-detail body.

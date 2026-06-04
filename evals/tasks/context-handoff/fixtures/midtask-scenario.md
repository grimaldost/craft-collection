# Current session state (mid-task)

We're building a **payments service in Python 3.12**. Over the last hour:

- Designed the schedule-generation path. It produces `ScheduledPayment` rows with
  fields: `id: UUID`, `account_id: UUID`, `amount_cents: int`, `currency: str`
  (ISO-4217), `due_date: date`, `status: Literal["pending","sent","failed"]`.
- Decided due dates must be moved to the next business day when they land on a
  weekend or holiday. There is an existing calendar utility at
  `app.calendars.business` exposing `is_business_day(d: date) -> bool` and
  `next_business_day(d: date) -> date`.
- Settled a convention: all monetary amounts are integer minor units (cents),
  never floats. PEP 8, line length 100, type hints required.

Two open threads:

- **Thread A** — we want a checker that validates the generated due dates don't
  fall on non-business days.
- **Thread B** (independent) — the retry/backoff policy for failed payment
  dispatch is still undecided: fixed 5-minute intervals vs exponential backoff
  capped at 1 hour.

Constraints: no new third-party dependencies; `from datetime import date`; import
the calendar from `app.calendars.business`.

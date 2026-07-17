# ADR-NNNN — <short decision title>

- **Status:** Proposed | Accepted | Superseded by ADR-MMMM
- **Date:** YYYY-MM-DD

## Context

What forces are at play? What problem or constraint requires a decision now?
Keep it to the facts that bear on the choice.

## Decision

The decision, stated as a present-tense directive ("We use X", "Curves are
immutable"). One decision per ADR.

## Alternatives considered

- **Option A** — why it was rejected.
- **Option B** — why it was rejected.

(If there were no real alternatives, the decision probably doesn't need an ADR.)

## Consequences

What becomes easier, what becomes harder, what new invariant this creates that
later code must respect. Name the invariant explicitly if one is created — it
will become a guardrail and a review-checklist item.

---
*Number ADRs sequentially. Never edit an Accepted ADR's decision; supersede it
with a new ADR and set this one's status to "Superseded by ADR-MMMM". Keeping the
ADR log current is what lets stateless workers share one set of global invariants
(method principle: keep the coordinate system current).*

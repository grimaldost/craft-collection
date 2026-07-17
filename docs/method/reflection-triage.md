# Reflection triage (closing the loop)

The exit gate of **Reflect** (phase 8). Reflections are worthless if nothing
consumes them; this step turns them into new external checks so the learning
compounds. A series is not "done reflecting" until recurring traps are promoted.

## Inputs

- `reflections.jsonl` (or wherever the project's reflection sink writes), plus the
  review/fix logs from the series.

## Procedure

1. **Read** all reflections from the series — and **sweep the sink**: every open
   (`proposed` / `watch`) promotion row of every prior triage or handoff doc in the same
   directory is also input to this pass. Reconcile each — carry it, supersede it, or close
   it with a reason. The directory is authoritative; an open row no later pass lists is an
   orphan. (A promotion row carries a status: `proposed` — or `watch` for a parked
   singleton — while open; `shipped(<version>)`, `accepted`, or `declined` closes it.)
2. **Cluster** them — group by underlying cause, not by symptom.
3. **Ground each candidate promotion against current source before writing it** — verify the
   mechanism it names is actually absent (or present) and cite the check. A promotion naming a
   mechanism that already exists collapses to already-shipped or a docs gap; catching it here
   keeps a no-op out of the backlog (a CHANGELOG window cannot see work shipped releases ago —
   only the source can).
4. For each grounded cluster that is **recurring or high-cost**, **promote** it to exactly
   one external destination:
   - a new **review-checklist item** (`review-checklist.md`) — for "a reviewer
     should have caught this";
   - a new **guardrail script / gate** — for "a machine should catch this
     deterministically";
   - a **spec-template change** (`spec-template.md`) — for "the spec should have
     required this up front" (often a new DoR check).
5. **Land** each promotion where the method can consume it, then record it in the triage
   document (one line per promotion, citing the motivating round/PR) — emitted with an H1
   beginning `# Triage —`: the feedback-loop tooling that indexes such directories detects
   a triage doc by that heading (the filename is not a signal there). Landing has two branches:
   - **Targets editable in-context** — the method repo itself, or this project's own bound
     copies of the kit for a project-scoped lesson: apply the edit directly.
   - **Targets out of reach** — the method runs from an installed plugin and its files are
     not yours to edit: emit a `<date>-<source>-method-promotions.md` handoff (the
     digest-for-handoff form; its H1 must NOT begin `# Triage —`, or the intake re-orphans
     its rows — open it e.g. `# Method promotions — <project>, <date> → INPUT to the method's
     triage`) into the method's registered feedback intake — the same channel this session's
     feedback report travels — and record project-side only the pointer to it. Recording the
     promotions project-side and stopping is the write-only half-state.

   A CHANGELOG entry is not this step's job: it is written in the method repo at build time,
   when a promotion ships — never in the consuming project. A promotion row **closes** only
   when a later triage or backlog document lists its doc as input; until then it stays
   `proposed` / `watch` for the next pass's sweep.

## What to promote vs. decline (feedback flows up)

Reflections flow **up** into the method; the method never reaches back down into the
reporting project. Promote only the **project-agnostic** lesson. Decline, with a one-line
reason, the residue that belongs to someone else — and do not track its fate:

- **Engine / execution-resilience** faults (orchestrator stalls, runner bugs, the salvage
  workflow) → the orchestrator's ledger, not a method gate. Keep method-correctness and
  engine-resilience as **separate ledgers**, so a healthy method is not blamed for an engine
  fault, nor an executor fix smuggled into a method gate.
- **Project-specific** knowledge (one codebase's typing/dispatch rule) → that project's own
  review checklist. keel stays project-agnostic; it does not file into or track a consumer.

## Exit gate

- [ ] Every recurring/high-cost cluster has been promoted to a checklist item, a
      guardrail, or a spec-template/DoR change — or explicitly logged as "accepted,
      no action" with a reason.
- [ ] Every promotion either landed in an editable target or rode a handoff into the
      method's feedback intake — none is recorded only where the method cannot read it.
- [ ] Every open (`proposed` / `watch`) row of every prior triage doc in the sink is
      reconciled — carried, superseded, or closed with a reason.

*A reflection that is read but never promoted is the write-only failure mode this step
exists to prevent — and a promotion recorded where the method cannot read it is the same
failure, one step later.*

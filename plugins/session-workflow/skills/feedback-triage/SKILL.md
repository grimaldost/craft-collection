---
name: feedback-triage
description: >
  Triage a tool's accumulated dogfooding feedback reports into a leverage-ordered
  improvement backlog — reconcile what already shipped, cluster findings by
  underlying cause rather than symptom, assign each cluster a disposition (attack
  this tool, route out to the tool that owns it, or decline), apply a promotion
  gate (reinforced across reports, specific, actionable), and emit a triage
  document with a status-tracked promotion table. Use on "triage the feedback
  backlog", "cluster the feedback reports", "what should this tool fix next",
  "promote the recurring feedback", or "/feedback-triage". Explicitly invoked
  maintenance — never run proactively; it reads a whole corpus. If the tool's
  binding registers its own triage template (e.g. keel's reflection-triage),
  follow that template. Not for consolidating journal entries into guidance (that
  is consolidate-knowledge), not for a single report (nothing to cluster yet), and
  not for triaging GitHub issues or a PR queue.
user-invocable: true
---

# Feedback Triage

The downstream half of the tool-feedback loop. `tool-feedback` captures one report
per session; this pass reads the accumulated corpus and turns it into the tool's
improvement backlog. Capture is tuned for recall; triage is tuned for precision —
the bar is *a maintainer can pick the top item and build it without re-reading the
reports*. It ends at the backlog document: building promotions, bumping versions,
and writing CHANGELOGs belong to the tool's own release process.

## The pipeline — run in order

1. **Scope.** Resolve the tool from the `feedback-targets` table in loaded context
   (ask once if absent; never hunt). Un-triaged reports = reports in its feedback
   dir not listed in the **Inputs** section of any existing `*-triage-*.md` doc
   there — detection is by input lists, not dates.
2. **Reconcile shipped first.** Read the tool's CHANGELOG since the last triage.
   Open the doc with **"Already shipped — NOT re-proposed"**; a cluster that goes
   further than a shipped change is marked as *extending* it. Each triage sharpens
   the backlog; it never repeats it.
3. **Cluster by underlying cause, not symptom.** Three reports saying "the cited
   file didn't exist", "the helper didn't handle our shape", and "the precedent
   was counterfactual" are one cluster: *ungrounded referents*. Cite every
   cluster's evidence as `<file-stem>#<n>` IDs (or stem + section for narrative
   findings), with counts.
4. **Assign a disposition per cluster:**
   - **ATTACK** — a real increment to this tool; name the home (template / gate /
     skill / doc / ADR).
   - **ROUTE OUT** — it belongs to another registered tool; record the target.
   - **DECLINE** — project-specific or out of charter; record why.
5. **Apply the promotion gate.** Promote only clusters that are **reinforced**
   (≥2 reports, ideally across arcs — a single-report **BLOCKER** is exempt),
   **specific** (a concrete change with a home), and **actionable**.
   Under-promote rather than pollute; unpromoted clusters stay listed as raw.
6. **Emit the triage doc** (template below) into the tool's feedback dir as
   `<YYYY-MM-DD>-triage-<scope>.md`, clusters leverage-ordered.
7. **Defer to a tool-owned template.** If the binding's `extras` registers a
   triage template (keel's `reflection-triage`), follow *its* structure and homes;
   the template below is the fallback for tools without one.

## Triage doc template

```markdown
# Triage — <tool> feedback backlog (<N> reports, <date-range>)

## Already shipped — NOT re-proposed
<changelog reconciliation; clusters below that extend shipped work say so>

## Inputs
<the explicit list of report files this triage covers>

## Headline
<2–4 sentences: what this round establishes about the tool>

## Clusters
### T1 — <underlying cause> (<disposition>; <recurrence count>)
<evidence: cited finding IDs / report stems>

| # | proposed promotion | home | status |
|---|--------------------|------|--------|
| T1a | <the concrete change> | <template/gate/skill/doc/ADR> | proposed |

### T2 — …

## Routed out
<cluster → target tool, what was routed>

## Declined
<cluster → reason>
```

Status vocabulary: `proposed` / `accepted` / `shipped(<version>)` / `declined`.
A fresh triage emits everything as `proposed`; later passes update statuses.

## Anti-patterns — hunt these

- **Re-proposing shipped work** — the reconciliation step exists to kill this.
- **Symptom clusters** — grouping by where it hurt instead of why it happened
  produces ten shallow clusters where two deep ones exist.
- **Over-promotion** — a singleton observation promoted as if reinforced; the
  gate (≥2 reports, BLOCKER exempt) exists to kill this.
- **Absorbing what should be routed** — an engine defect "fixed" with a method
  doc; honor each tool's ledger and route out.

## Relationship to neighbors

`tool-feedback` captures (per session, recall); this consolidates (per corpus,
precision) — the same shape as `journaling-sessions` → `consolidate-knowledge`,
specialized to tool dogfooding. For a keel *series'* reflections, keel's own
triage flow owns the job; this skill defers to registered templates when triaging
keel's feedback dir.

## What this skill does NOT do

- Build promotions, edit the tool, bump versions, or write CHANGELOG entries.
- Run proactively or on a single report.
- Triage GitHub issues, PR queues, or task backlogs.

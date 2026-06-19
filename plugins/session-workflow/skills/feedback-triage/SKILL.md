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
  is consolidate-knowledge), not for a single report (nothing to cluster yet), not
  for triaging GitHub issues or a PR queue, and not for triaging a governed
  series' own reflections into durable checks — the owning method tool's triage
  skill (e.g. keel's keel-triage) does that, not this generic feedback pass.
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
   (ask once if absent; never hunt). List the feedback dir directly — a plain
   directory listing, not a glob, which a non-cwd path or a house naming
   convention can silently miss. Un-triaged reports = reports in its feedback dir
   not listed in the **Inputs** section of any existing triage doc there —
   detection is by input lists, not dates. A doc counts as a triage doc if its
   first heading is `# Triage —` or its filename contains `triage`; this catches
   house variants like keel's `<date>-backlog-triage.md` that a bare
   `*-triage-*.md` glob skips. First run (no triage doc exists yet): the whole
   corpus is un-triaged. If the invocation names a different count or set than the
   directory holds, the directory is authoritative — triage what is on disk and
   note the discrepancy under **Inputs**. If another session may be triaging the
   same corpus, note any triage doc already dated today before you start, and
   re-check at emit (step 6) so two sessions don't write competing docs. Rebuild the
   dir's `INDEX.md` at scope (run `uv run --no-project python scripts/build_feedback_index.py <dir>`) so the
   `extends`-lookup in steps 2–3 is one Read of a current index, not N
   phrasing-fragile greps.
2. **Reconcile shipped first.** Read the tool's CHANGELOG since the last triage —
   on a first run, the window is the whole CHANGELOG to date. For a component that
   ships without its own CHANGELOG (an eval harness, a scripts dir, a doc set),
   also read `git log` over that window and check the current source: its
   increments land as commits, so a CHANGELOG-only reconciliation reads
   already-shipped work as still-open. Map each finding to the version or commit
   that resolved it. Open the doc with **"Already shipped — NOT re-proposed"**; a
   cluster that goes further than a shipped change is marked as *extending* it.
   Each triage sharpens the backlog; it never repeats it.
3. **Cluster by underlying cause, not symptom.** Three reports saying "the cited
   file didn't exist", "the helper didn't handle our shape", and "the precedent
   was counterfactual" are one cluster: *ungrounded referents*. Collapsing has a
   dual — **split** one super-cause into separate clusters when its corollaries
   have distinct homes *and* distinct concrete fixes; each piece must be
   promotable on its own. Follow `extends` chains while clustering: a finding
   marked "extends `<stem>#<n>`" belongs with its ancestors, and the chain's
   length is recurrence evidence. Cite every cluster's evidence as
   `<file-stem>#<n>` finding IDs (or stem + section for narrative findings),
   with counts. For a same-wave `-execution`/`-authoring` report pair, read the
   `-execution` report first — it holds the evidence; the `-authoring` report
   explains the causes and the folds.
4. **Assign a disposition per cluster:**
   - **ATTACK** — a real increment to this tool; name the home (template / gate /
     skill / doc / ADR). **Escalate the layer on a recurrence:** when a finding
     recurred *after* a fix already shipped at the same enforcement layer (≥2
     post-fix reports) and its cause is **mechanically reachable** at the next
     layer, attack one rung down — advisory prose → required structure →
     script/gate → hook → linter/CI — instead of re-prosing the same advice. A
     judgment-bound recurrence no mechanism can reach (a dispatch-timing nudge, a
     naming call) takes sharper prose or DECLINE, not a forced rung. This is the
     loop-side of the rule `skill-authoring` states for a skill: a constraint that
     needs caps to hold needs a gate, not louder prose.
   - **ROUTE OUT** — it belongs to another registered tool; record the target.
   - **DECLINE** — project-specific or out of charter; record why.

   Tie-breaker when this tool's artifact participates in behavior another tool
   owns: route by **where the fix lands**, not where the artifact lives. When you
   fan out per-tool digest subagents over a multi-tool corpus, enumerate **each
   registered tool's own skills/components** in the brief's owner taxonomy — a
   finding about tool X's own skill is otherwise misrouted to whichever tool the
   brief described in most detail (e.g. a pr-pilot skill mistagged as craft's).
5. **Apply the promotion gate.** Promote only clusters that are **reinforced**
   (≥2 reports, ideally across arcs — a single-report **BLOCKER** is exempt),
   **specific** (a concrete change with a home), and **actionable**. The
   exemption's scope is the BLOCKER's own row: sibling rows from the same
   report need their own explicit justification in the ledger, or take `watch`.
   `watch` is also the middle disposition for an anchored singleton — keep the
   row, hold the build, wait for a second report. Under-promote rather than
   pollute; unpromoted clusters stay listed as raw, and the **Promotion-gate
   ledger** section shows the gate's work either way.
6. **Emit the triage doc** (template below) into the tool's feedback dir as
   `<YYYY-MM-DD>-triage-<scope>.md` — a name a later `triage`-detecting scope step
   will find — clusters leverage-ordered. Before writing, re-list the dir: if a
   triage doc covering this same corpus appeared since step 1 (a concurrent
   session), reconcile with it instead of emitting a duplicate.
7. **Defer to a tool-owned template.** If the binding's `extras` registers a
   triage template (keel's `reflection-triage`), follow *its* structure and homes;
   if `extras` is empty or registers none, the template below is authoritative —
   don't hunt for one. When the ask is to triage "everything" across tools and one
   of them owns its triage flow, that tool's slice is a **digest-for-handoff** —
   extracted, clustered, and owner-tagged (per step 4) findings written as INPUT to
   its flow (a `<date>-new-findings-digest.md`), not a competing generic triage and
   not skipped.

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

## Promotion-gate ledger
<the gate's work, auditable per cluster: which cleared on reinforcement, which
promoted via the BLOCKER exemption (name the exempting finding), which sit at
`watch`, which stayed raw — and why. Close with the assertion that no singleton
non-BLOCKER was promoted.>
```

Status vocabulary: `proposed` / `watch` / `accepted` / `shipped(<version>)` /
`declined` — `watch` parks an anchored-but-singleton row until a second report
corroborates it. A fresh triage emits rows as `proposed` (or `watch`); later
passes update statuses.

Two ID namespaces are in play; don't conflate them. **Report finding IDs**
(`<file-stem>#<n>`, minted by `tool-feedback`) are what evidence and CHANGELOG
credits cite; **promotion IDs** (`T1a` — cluster number + row letter, minted
here) are what statuses track across triage passes.

## Anti-patterns — hunt these

- **Re-proposing shipped work** — the reconciliation step exists to kill this.
- **Symptom clusters** — grouping by where it hurt instead of why it happened
  produces ten shallow clusters where two deep ones exist.
- **Over-promotion** — a singleton observation promoted as if reinforced; the
  gate (≥2 reports, BLOCKER exempt) exists to kill this, and `watch` exists so
  the anchored singleton isn't lost instead.
- **Absorbing what should be routed** — an engine defect "fixed" with a method
  doc; honor each tool's ledger and route out.
- **Re-prosing a recurrence** — a finding that recurred past a shipped prose fix
  needs a stronger enforcement layer (a structure, script, gate, hook, or linter),
  not a fourth sentence of the same advice; more prose symptom-patches the cause
  the prose layer already failed to bind.

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

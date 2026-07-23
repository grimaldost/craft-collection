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
  is consolidate-knowledge), not for a corpus of one report with no prior triage
  (nothing to cluster yet — a 1-report delta over an existing baseline IS a valid
  later pass), not for triaging GitHub issues or a PR queue, and not for triaging
  a governed series' own reflections into durable checks — the owning method
  tool's triage skill (e.g. keel's keel-triage) does that, not this generic
  feedback pass.
user-invocable: true
---

# Feedback Triage

The downstream half of the tool-feedback loop. `tool-feedback` captures one report
per session; this pass reads the accumulated corpus and turns it into the tool's
improvement backlog. Capture is tuned for recall; triage is tuned for precision —
the bar is *a maintainer can pick the top item and build it without re-reading the
reports*. It ends at the backlog document: building promotions, version bumps,
and CHANGELOGs belong to the tool's release process.

## The pipeline — run in order

1. **Scope.** Resolve the tool from the `feedback-targets` table in loaded context
   (ask once if absent; never hunt). Rebuild the dir's `INDEX.md` first (run
   `uv run --no-project python "${CLAUDE_PLUGIN_ROOT}/skills/feedback-triage/scripts/build_feedback_index.py" <dir>`):
   its `### Untriaged` section is the input list — reports in no triage doc's
   **Inputs**, detection by input lists, not dates — and the `extends`-lookup in
   steps 2–3 is one Read. A triage doc is detected by its `# Triage` H1 — the
   rule the index builder stamps into its header; the filename is deliberately
   NOT a signal (`references/mechanics.md` has the misclassification cases).
   State the count: `N un-triaged
   reports`. N of 1 with no prior triage doc is too thin — stop with a note
   (nothing to cluster); 1 new report over an existing baseline is a valid delta
   pass (step 7). When the invocation names a different count or set, the
   directory is authoritative — note the discrepancy under **Inputs**. Note any triage doc already dated today and re-check at emit
   (step 7).
2. **Reconcile shipped first.** Read the tool's CHANGELOG since the last triage —
   on a first run, the whole CHANGELOG to date. For a component without its own
   CHANGELOG (a harness, a scripts dir, a doc set), also read `git log` over
   the window — increments land as commits, invisible to CHANGELOG-only
   reconciliation. Map each finding to the version or commit that resolved it. Open the doc with **"Already shipped — NOT re-proposed"**; a
   cluster that goes further than a shipped change is marked as *extending* it.
   Reconcile OPEN rows too,
   not only shipped ones: the INDEX's `## Triage coverage` lists every triage doc
   in the dir, so carry or re-disposition each one's open `proposed`/`watch` rows
   into this pass — a row is not closed until a later doc lists it. An
   off-main-chain cycle-scoped triage otherwise orphans its rows (keel's
   `reflection-triage` P3a is the twin; co-land).
3. **Cluster by underlying cause, not symptom.** Three reports saying "the cited
   file didn't exist", "the helper didn't handle our shape", and "the precedent
   was counterfactual" are one cluster: *ungrounded referents*. Collapsing has a
   dual — **split** one super-cause into separate clusters when its corollaries
   have distinct homes *and* distinct concrete fixes; each piece must be
   promotable on its own. Follow `extends` chains while clustering: a finding
   belongs with its ancestors, and chain length is recurrence evidence. Cite each
   cluster's evidence as finding IDs (or stem + section for narrative findings),
   with counts. For a same-wave `-execution`/`-authoring` pair, read `-execution`
   first — it holds the evidence.
4. **Assign a disposition per cluster:**
   - **ATTACK** — a real increment to this tool; name the home (template / gate /
     skill / doc / ADR) **and the fix shape, derived from the cause, not the
     symptom**. Prefer shapes in this order: **remove/simplify** what produces the
     failure; **restructure** the section or mechanism so the class can't recur;
     **mechanize** (test / script / gate / hook); **append prose** — last, and
     only naming what it displaces (a clause folded, tightened, or retired) —
     loop bodies measurably grow one clause per promoted finding until a cold
     reader drops load-bearing ones. **Escalate the layer on a recurrence:** when
     a finding recurred *after* a fix already shipped at the same enforcement
     layer (≥2 post-fix reports) and its cause is **mechanically reachable** at
     the next layer, attack one rung down — advisory prose → required structure →
     script/gate → hook → linter/CI — instead of re-prosing the same advice. A
     judgment-bound recurrence no mechanism can reach (a dispatch-timing nudge, a
     naming call) takes sharper prose or DECLINE, not a forced rung —
     `skill-authoring`'s rule, loop-side: what needs caps to hold needs a
     gate, not louder prose.
   - **ROUTE OUT** — it belongs to another registered tool; record the target.
   - **DECLINE** — project-specific or out of charter; record why.

   Tie-breaker when this tool's artifact participates in behavior another tool
   owns: route by **where the fix lands**, not where the artifact lives.
   Fan-out digest briefs must enumerate each tool's own components in the
   owner taxonomy — misrouting case in `references/mechanics.md`.
5. **Ground, then apply the promotion gate.** Before writing a row, ground it
   against the tool's **current source**: verify the mechanism it names is
   actually absent (or present, for an extension), implementable as stated (the
   API allows it), and truthfully named for the shape it will carry — cite the
   check in the ledger. A CHANGELOG window cannot see work shipped releases ago;
   only the source can — ungrounded rows have re-proposed the shipped and
   proposed the impossible. Then promote only clusters that are **reinforced**
   (≥2 reports, ideally across arcs — a single-report **BLOCKER** is exempt),
   **specific** (a concrete change with a home), and **actionable**. The
   exemption's scope is the BLOCKER's own row — siblings from the same report
   justify themselves in the ledger or take `watch` (the middle disposition:
   keep the row, hold the build, wait for a second report). Under-promote rather
   than pollute; unpromoted clusters stay listed as raw, and the **Promotion-gate
   ledger** shows the gate's work either way.
6. **Consolidate before you grow.** A standing debt check on every pass: a home
   that takes an appending promotion this round, carries clauses no report has
   exercised across recent rounds, or nears the validator's size cap gets a
   consolidation row of its own — fold accumulated sub-cases into a reference
   file, merge overlapping clauses, retire dead ones. Shrink rows ride the same
   table and statuses as any other promotion; a loop that can only add converges
   on bodies too dense to execute.
7. **Emit the triage doc** (template below) into the tool's feedback dir as
   `<YYYY-MM-DD>-triage-<scope>.md`, clusters leverage-ordered. A later pass
   over a corpus with a baseline emits a NEW doc in the delta form — Inputs
   list only the new reports, the new table supersedes the baseline as status
   of record, a consolidated backlog table carries every open row, cluster IDs
   continue the baseline's namespace (`references/mechanics.md`). Before
   emitting, assert **input coverage**: every finding `<stem>#<n>` in the Inputs'
   INDEX entries appears in the doc under a disposition — a cluster's evidence,
   Routed out, Declined, or an explicit "no action: <reason>" — so a finding
   leaves the loop only with a disposition, never by omission (a dropped
   extends-chain surfaced two passes late). Then re-list the dir: a same-corpus
   triage doc that appeared since step 1 is reconciled with, not duplicated.
   Close by re-running the index builder: just-triaged stems still under
   `### Untriaged` mean the Inputs did not parse (fragmented stems) — fix
   before ending.
8. **Defer to a tool-owned template.** If the binding's `extras` registers a
   triage template (keel's `reflection-triage`), follow *its* structure and homes;
   otherwise the template below is authoritative — don't hunt for one. Triaging
   "everything" when one tool owns its own flow? That tool's slice is a
   **digest-for-handoff**: extracted, clustered, owner-tagged (per step 4)
   findings written as INPUT to its flow (a `<date>-new-findings-digest.md`) —
   not a competing triage, not skipped.

## Triage doc template

```markdown
# Triage — <tool> feedback backlog (<N> reports, <date-range>)

## Already shipped — NOT re-proposed
<changelog reconciliation; clusters below that extend shipped work say so>

## Inputs
<full report stems, one per line; the coverage parser matches whole stems —
a factored-out date prefix reads as zero coverage>

## Headline
<2–4 sentences: what this round establishes about the tool>

## Clusters
### T1 — <underlying cause> (<disposition>; <recurrence count>)
<evidence: cited finding IDs / report stems>

| # | proposed promotion | fix shape | home | status |
|---|--------------------|-----------|------|--------|
| T1a | <the concrete change> | <remove / restructure / mechanize / prose (displaces: …) / new artifact> | <template/gate/skill/doc/ADR> | proposed |

### T2 — …

## Routed out
<cluster → target tool, what was routed>

## Declined
<cluster → reason>

## Promotion-gate ledger
<the gate's work, auditable per cluster: which cleared on reinforcement, which
promoted via the BLOCKER exemption (name the exempting finding), which sit at
`watch`, which stayed raw — and why. Close with three assertions: no singleton
non-BLOCKER was promoted, no prose append shipped without a named displacement,
and every Inputs finding is dispositioned (input coverage).>
```

Status vocabulary: `proposed` / `watch` / `accepted` / `shipped(<version>)` /
`declined` — `watch` parks an anchored-but-singleton row until a second report
corroborates it; later passes update statuses. (Report finding IDs `<stem>#<n>`
are minted by `tool-feedback`; promotion IDs `T1a` are minted here — two
namespaces, don't conflate them.)

## Anti-patterns — hunt these

- **Re-proposing shipped work** — the reconciliation step exists to kill this.
- **Symptom clusters** — grouping by where it hurt instead of why it happened
  produces ten shallow clusters where two deep ones exist.
- **Over-promotion** — a singleton observation promoted as if reinforced; the
  gate exists to kill this, and `watch` keeps the anchored singleton.
- **Absorbing what should be routed** — an engine defect "fixed" with a method
  doc; honor each tool's ledger and route out.
- **Re-prosing a recurrence** — a finding that recurred past a shipped prose fix
  needs a stronger enforcement layer, not a fourth sentence of the same advice.

## Relationship to neighbors

`tool-feedback` captures (per session, recall); this consolidates (per corpus,
precision) — the same shape as `journaling-sessions` → `consolidate-knowledge`,
specialized to tool dogfooding. (A governed series' own reflections belong to the
owning tool's triage flow — see step 8.)

## What this skill does NOT do

- Build promotions, edit the tool, bump versions, or write CHANGELOG entries.
- Run proactively, or on a corpus of one report with no baseline (a 1-report
  delta over an existing baseline is a valid later pass).
- Triage GitHub issues, PR queues, or task backlogs.

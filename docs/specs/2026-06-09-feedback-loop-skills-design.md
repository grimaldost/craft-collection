# Feedback-loop skills — design (approved 2026-06-09)

Two new skills in **session-workflow** that turn the hand-maintained tool-feedback standing
practice (global CLAUDE.md prose) into a versioned, evaluable, self-improving frame:

- **`tool-feedback`** — capture: one per-session dogfooding report per registered tool used.
- **`feedback-triage`** — downstream: cluster a tool's report backlog into a leverage-ordered,
  status-tracked improvement backlog.

The pair mirrors the plugin's existing `journaling-sessions` → `consolidate-knowledge` idiom:
capture tuned for recall, downstream pass tuned for precision.

## Motivation (evidence, 2026-06-09 review)

Three live feedback loops exist; each independently evolved a different third of the frame:

| | capture format | triage/dedup | closure accounting |
|---|---|---|---|
| keel | formalized (`docs/feedback/README.md`, 6 sections) | `reflection-triage` template + skill (cause-clusters, ATTACK/ROUTE-OUT/DECLINE, status) | partial ("already shipped — not re-proposed" in triage) |
| pr-pilot | de-facto consistent + richer (severity tags, cost tables, phase attribution, cross-wave refs) | none — same ask recurred in 4 reports (heartbeat) | strongest (CHANGELOG credits specific reports; fix ships 1–3 days after report) |
| craft-collection | inherited keel's 6 sections via CLAUDE.md prose | none — 21 reports, ~39 unclustered proposals | none |

Closed loops demonstrably pay (pr-pilot 0.2.4→0.5.0 in a week off report findings; keel 0.4.0
built from its backlog triage). The frame unifies the best fragment of each loop and makes the
frame itself versioned and improvable — feedback about these skills flows into craft-collection's
own feedback dir, closing the meta-loop.

## Scope

**v1 (this spec):** capture + triage skills, bindings contract, unified report format,
triage-doc format, evals (with sealed holdouts), packaging (session-workflow 0.2.0), migration.

**v2 (deferred, recorded not designed):** closure conventions — CHANGELOG-crediting rules,
`shipped(version)` back-references written into prior triage docs, status-index automation.

## Decisions log

1. **Approach A** — a new two-skill pair (not one dual-mode skill; not extensions of
   journaling/consolidate). Rationale: the halves fire at different moments (session end vs.
   explicit maintenance) with opposing activation postures — mode-mixed descriptions are the
   hardest to tune (python-engineering evidence); grafting onto eval-tuned descriptions risks
   trigger regression.
2. **Bindings live in user context (global CLAUDE.md), discipline lives in the skills** — the
   `target_store` pattern from journaling's store-binding: the profile is *given*, never hunted.
3. **Unified report format = keel's six sections (superset) + pr-pilot enrichments** (severity
   tags, phase attribution, recurrence refs, optional cost table, stable finding IDs). keel's
   `docs/feedback/README.md` stays authoritative for keel's dir; the unified format must remain
   a strict superset of it.
4. **Finding IDs on proposed promotions only** (`<file-stem>#<n>`); friction/misses are cited by
   slug + section. Rationale: proposals are the triage input units; numbering everything adds
   ceremony without a consumer.
5. **Severity scale: BLOCKER / HIGH / MED / LOW** (pr-pilot's, proven in 37 reports).
6. **Triage defers to a tool-owned template when the binding registers one** (keel's
   `reflection-triage`) — ownership resolution per toolkit-awareness; the generic pipeline is
   the fallback.
7. **Triage emits a backlog, never builds** — keel's separation ("cluster and record" vs
   "promote/build + CHANGELOG + SemVer") is kept; building is the tool's own release process.
8. **Sealed holdout trigger sets are authored together with the main datasets, before any
   tuning** — applying the python-engineering overfitting lesson from day one.
9. Both skills are `user-invocable: true`; neither is `disable-model-invocation` (both have
   genuine NL trigger surfaces). Frontmatter descriptions use `description: >` folded blocks to
   dodge the colon-space silent-kill trap.
10. **Dataset deviation (2026-06-09, during implementation):** the tool-feedback boundary
    negative "Update the CHANGELOG for the release." listed below was traded — on
    eval-methodology review advice — for a second journaling-boundary near-miss ("Capture what
    we learned this session into my long-term notes."), because the journaling boundary is the
    hardest and was single-guarded, while the changelog boundary is explicitly disclaimed in
    the skill body and low-risk. The final whole-branch review flagged the unrecorded
    substitution; recorded here so the "MUST be present" list reflects reality.

## Component 1 — the bindings contract (`feedback-targets`)

A markdown table the user keeps in always-loaded context (global CLAUDE.md). Shape:

```markdown
## Feedback targets

Run tool-feedback at session close for every registered tool the session exercised
(skills, agents, engine/CLI runs, templates/doctrine — design-only use counts).

| tool | repo | feedback dir | extras |
|------|------|--------------|--------|
| keel | C:\Users\grima\Documents\keel | docs/feedback | format: that dir's README.md; triage template: src/keel/templates/reflection-triage.md |
| pr-pilot | C:\Users\grima\Documents\pr-pilot-main | docs/feedback | include cost table for engine runs |
| craft-collection | C:\Users\grima\Documents\craft-collection | docs/feedback | — |
```

Rules (stated in both skills):

- A tool is **registered** iff such a table is in loaded context or the user points at one.
- No table in context → ask once for it (or for an inline binding); **never hunt the
  filesystem** for candidate repos.
- `extras` is free text the skills read for per-tool obligations (format authority, triage
  template, cost-table requirement).
- "The session **used** a tool" means: invoked any of its skills/agents/commands, ran its
  engine or CLI, or substantively applied its templates/doctrine — including design-only and
  authoring-only use.

## Component 2 — `tool-feedback` (capture)

`plugins/session-workflow/skills/tool-feedback/SKILL.md`. No scripts, no references dir in v1
(single-file skill; the report template lives in the body).

### Frontmatter description (draft — the trigger surface)

> Write a per-session dogfooding feedback report for each registered in-development tool the
> session exercised — what worked, friction, misses with the phase that should have caught
> them, vacuous gates, and severity-tagged proposed changes with stable finding IDs — saved
> into that tool's own feedback directory. Use when the user asks for feedback on their tools
> ("write the feedback reports", "tooling feedback", "dogfood report", "capture the friction
> with keel / pr-pilot"), and offer once, unprompted, when a session that exercised a
> registered tool is winding down. Registered tools come from a feedback-targets table the
> user supplies (e.g. in CLAUDE.md) — never hunt the filesystem for targets. Design-only or
> authoring-only use of a tool still counts as use. Not for feedback on code or PRs (that is
> code review), not for capturing general session knowledge into a memory store (that is
> journaling-sessions), and not for product feedback to a third-party vendor.

### Body — load-bearing content

1. **Asked vs. noticed** (reuse journaling-sessions' offer-first protocol verbatim in shape):
   asked → write now, no confirmation; self-activated at session end → a single one-line offer
   naming the tools and what's capturable ("This session exercised keel and pr-pilot — want
   the two feedback reports?"); one offer, not a nag; can't tell → offer.
2. **Resolve targets**: read the bindings table; enumerate which registered tools the session
   used (the "used" definition above); one report per tool.
3. **Recurrence check before drafting**: grep the tool's feedback dir for each candidate
   finding's key terms; a repeat is written as **"extends `<prior-stem>#<n>`"** (or
   "extends `<prior-stem>` §Misses" for narrative findings) with only the new evidence — not
   restated fresh.
4. **Route by ownership**: engine/execution findings → the engine tool's report; method/gate
   findings → the method tool's; skill findings → the skill collection's. When ownership is
   ambiguous, put it in the report of the tool where it surfaced and say so — triage's
   ROUTE OUT is the backstop.
5. **Report template** (the unified format):

```markdown
# <tool> feedback — <short title>

- **Date:** YYYY-MM-DD
- **Tool/version:** <name> <version — read from plugin.json / pyproject / __version__; never guessed>
- **Context:** <what the tool was applied to; which skills/components were exercised>
- **Outcome:** <one-line headline of how the session went>

## What worked
<where the tool earned its keep — explicit positive validation, named features>

## Friction
<each item severity-tagged [BLOCKER|HIGH|MED|LOW]; cost or confusion, with the concrete moment>

## Misses
<defects the tool failed to prevent — each with severity AND the phase that should have
caught it ("phase: DoR", "phase: pre-mortem", "phase: gate", "phase: review")>

## Vacuous gates
<anything that passed while hollow; "none observed" is a valid entry>

## Proposed promotions / changes
1. **[SEVERITY]** <proposal — candidate template / gate / doc / skill change, with its home>
2. ...
<numbered: these are the stable IDs (<file-stem>#1, #2, …) that triage and changelogs cite;
a repeat of a prior ask is "extends <stem>#<n>" with the new evidence, not a fresh restatement>

## Cost (optional — when engine or eval runs were involved)
<per-run or per-role cost/token table>
```

6. **Filename**: `<YYYY-MM-DD>-<source-slug>.md`; slug distinct per wave/phase so reports never
   clobber (existing practice).
7. **Self-check before emitting**: every cited path exists; version read from the manifest;
   repeats are `extends`; report reads cold (zero-context test); severities present on
   friction/misses/proposals.
8. **What it does NOT do**: fix anything, triage the backlog, edit the tool, write CHANGELOG
   entries, or file reports for unregistered tools.

## Component 3 — `feedback-triage` (downstream)

`plugins/session-workflow/skills/feedback-triage/SKILL.md`. Single-file skill in v1.

### Frontmatter description (draft)

> Triage a tool's accumulated dogfooding feedback reports into a leverage-ordered improvement
> backlog — reconcile what already shipped, cluster findings by underlying cause rather than
> symptom, assign each cluster a disposition (attack this tool, route out to the tool that
> owns it, or decline), apply a promotion gate (reinforced across reports, specific,
> actionable), and emit a triage document with a status-tracked promotion table. Use on
> "triage the feedback backlog", "cluster the feedback reports", "what should <tool> fix
> next", "promote the recurring feedback", or "/feedback-triage". Explicitly invoked
> maintenance — never run proactively; it reads a whole corpus. If the tool's binding
> registers its own triage template (e.g. keel's reflection-triage), follow that template.
> Not for consolidating journal entries into guidance (that is consolidate-knowledge), not
> for a single report (nothing to cluster yet), and not for triaging GitHub issues or a PR
> queue.

### Pipeline (the body's spine)

1. **Scope** — resolve the tool from the bindings table. Un-triaged reports = reports not
   listed as inputs by any existing triage doc in that dir (triage docs carry `-triage` in
   the filename and an explicit "Inputs" section; detection is by the input lists, not dates).
2. **Reconcile shipped first** — read the tool's CHANGELOG since the last triage; open the doc
   with **"Already shipped — NOT re-proposed"**, and mark clusters that *extend* shipped work
   as extensions, so each triage sharpens rather than repeats.
3. **Cluster by underlying cause, not symptom** — each cluster cites its evidence as
   `<stem>#<n>` proposal IDs (or slug + section for narrative findings), with counts.
4. **Disposition per cluster** — **ATTACK** (a real increment to this tool, with the proposed
   home: template / gate / skill / doc / ADR) · **ROUTE OUT** (belongs to another registered
   tool; recorded in this doc with the target named) · **DECLINE** (project-specific or
   out-of-charter; reason recorded).
5. **Promotion gate** (borrowed from consolidate-knowledge): promote only clusters that are
   **reinforced** (≥2 reports, ideally across arcs — single-report BLOCKERs exempt),
   **specific** (a concrete change with a home), and **actionable**. Under-promote rather
   than pollute; unpromoted clusters stay listed as raw.
6. **Emit the triage doc** into the tool's feedback dir,
   `<YYYY-MM-DD>-triage-<scope>.md`:

```markdown
# Triage — <tool> feedback backlog (<N> reports, <date-range>)

## Already shipped — NOT re-proposed
<changelog reconciliation; clusters below that extend shipped work say so>

## Inputs
<the explicit list of report files this triage covers>

## Headline
<2-4 sentences: what this round establishes about the tool>

## Clusters
### T1 — <underlying cause> (<disposition>; <recurrence count>)
<evidence: cited findings with stems/IDs>
| # | proposed promotion | home | status |
|---|---|---|---|
| T1a | ... | ... | proposed |

### T2 — ...

## Routed out
<cluster → target tool, what was routed>

## Declined
<cluster → reason>
```

   Status vocabulary: `proposed` / `accepted` / `shipped(<version>)` / `declined`.
7. **Tool-owned template deferral**: when `extras` names a triage template, read it and follow
   its structure/homes instead of the generic skeleton above.
8. **What it does NOT do**: build the promotions, edit the tool, bump versions, or write
   CHANGELOG entries — it ends at the backlog doc.

## Packaging

- session-workflow `0.1.3 → 0.2.0` (two new skills = minor bump). CHANGELOG entry.
- Update: `plugins/session-workflow/.claude-plugin/plugin.json` description,
  `plugins/session-workflow/README.md`, repo `README.md` ("What's inside"),
  `.claude-plugin/marketplace.json` session-workflow description + keywords (`feedback`,
  `dogfooding`, `triage`).
- No new scripts/hooks; `scripts/validate_plugins.py` and pre-commit cover the new SKILL.mds
  structurally.

## Evals

- `evals/trigger/tool-feedback.json` and `evals/trigger/feedback-triage.json` — 8 positive
  (incl. implicit/proactive phrasings for tool-feedback) + 8 negative each.
- **Sealed holdouts** `evals/trigger/holdout/{tool-feedback,feedback-triage}.json` (4–6 novel
  paraphrases each) authored in the same PR, before any tuning, never tuned against.
- Boundary negatives that MUST be present:
  - tool-feedback must NOT fire: "journal this session", "consolidate my journals", "review
    this PR and give feedback", "write a postmortem for the incident", "file a GitHub issue
    for this bug", "update the CHANGELOG".
  - feedback-triage must NOT fire: "consolidate my journals", "what patterns emerged across
    these sessions" (consolidate-knowledge), "triage the GitHub issues", "prioritize my task
    backlog", "triage this series' reflections with keel" (keel-triage's job).
  - Cross-pair: "write the feedback reports" fires tool-feedback only; "triage the feedback
    backlog" fires feedback-triage only.
- `evals/tasks/<skill>/` correct-usage rubrics (weighted):
  - tool-feedback: version-from-manifest present; one report per tool used; severities tagged;
    misses carry phase attribution; repeats expressed as `extends`; six sections present;
    self-contained cold read.
  - feedback-triage: shipped-reconciliation section present; clusters are cause-based and cite
    finding IDs; every cluster has a disposition; promotion table has home + status; gate
    honored (no single-report non-BLOCKER promotions); leverage-ordered.
  - Fixtures: tool-feedback gets a synthetic session digest (a two-tool work narrative with
    plantable findings, an inline feedback-targets table, and fake manifests carrying versions)
    under `evals/tasks/tool-feedback/fixtures/`; feedback-triage gets a synthetic mini-corpus
    (4–5 short reports with planted recurrence, one shipped item in a fake CHANGELOG, one
    route-out candidate) under `evals/tasks/feedback-triage/fixtures/`.
- `evals/config.json`: add both skills to `plugin_of_skill`.

## Migration & first run

1. User edits global CLAUDE.md: standing-practice paragraph → feedback-targets table +
   one-line pointer (user-side, after the skills ship).
2. keel's `docs/feedback/README.md` untouched (already a subset of the unified format).
3. **Validation run**: execute `feedback-triage` on craft-collection's own 21-report backlog —
   first real triage, dogfoods the skill, and closes the #1 finding of the 2026-06-09 design
   review. Its output seeds the 0.2.x improvement backlog.

## Risks & mitigations

- **Trigger adjacency** to journaling-sessions / consolidate-knowledge — mutual not-for
  clauses in all four descriptions (the two new ones carry them from birth; the two existing
  descriptions are NOT edited in v1 to avoid regressing tuned surfaces); boundary cases
  encoded in both datasets + holdouts.
- **Bindings absent** (fresh machine, other users) — ask-once, never-hunt rule.
- **`keel-triage` collision** — scoped by corpus (a tool's feedback dir vs a keel series'
  reflections) and by template deferral when triaging keel itself.
- **Report duplication across parallel per-tool reports** — route-by-ownership rule at
  capture; ROUTE OUT at triage as backstop.
- **Format drift vs keel's README** — unified format is a declared superset; any future keel
  README change that conflicts is reconciled in keel's favor for keel's dir (doc wins, per
  toolkit-awareness's source-of-truth rule).

## Out of scope (v1)

- Closure conventions (CHANGELOG crediting format, back-writing `shipped(version)` into prior
  triage docs, a status index) — v2.
- Automation/scripts (a recurrence-grep helper, a status-index generator) — only if manual
  practice shows the need.
- Editing journaling-sessions / consolidate-knowledge descriptions.

---
name: tool-feedback
description: >
  Write a per-session dogfooding feedback report for each registered in-development
  tool the session exercised — what worked, friction, misses with the phase that
  should have caught them, vacuous gates, and severity-tagged proposed changes with
  stable finding IDs — saved into that tool's own feedback directory. Use when the
  user asks for feedback on their tools ("write the feedback reports", "tooling
  feedback", "dogfood report", "capture the friction with keel / convoy") — a
  direct imperative naming one tool ("write a dogfooding feedback report for keel")
  is this skill too, since writing that report IS the skill; route it here rather
  than drafting the report freehand — and offer once, unprompted, when a session
  that exercised a registered tool is winding down. Registered tools come from a feedback-targets table the user supplies (e.g.
  in CLAUDE.md) — never hunt the filesystem for targets. Design-only or
  authoring-only use of a tool still counts as use. Not for feedback on code or PRs
  (that is code review), not for capturing general session knowledge into a memory
  store (that is journaling-sessions), and not for product feedback to a third-party
  vendor.
user-invocable: true
---

# Tool Feedback

Tools in active development improve only if every session that uses them reports
back. This skill writes that report — one per tool per distinct concern, into the
tool's own repo — in a format the downstream `feedback-triage` pass can cluster:
severity-tagged findings, stable IDs, the phase that missed, explicit links for
repeats. One tool exercised across distinct phases, concerns, or surfaces (a
library vs its consumer plugin) takes one report each, under distinct slugs. The
quality bar: a maintainer can act on it cold.

## Registered tools — the feedback-targets binding

A tool is **registered** iff a `feedback-targets` table is in loaded context (e.g.
the user's CLAUDE.md) or the user points you at one. Shape:

| tool | repo | feedback dir | extras |
|------|------|--------------|--------|
| keel | C:\Users\me\Documents\keel | docs/feedback | format: that dir's README.md |

- **No table in context → ask once** for it (or an inline binding). **Never hunt the
  filesystem** for candidate repos.
- `extras` carries per-tool obligations — a format README that stays authoritative
  for that directory, a registered triage template, "include cost table for engine
  runs". Read and honor it; if it cites a README that does not exist, fall back to
  this skill's template and note the gap in the report.
- The session **used** a tool if it invoked any of its skills/agents/commands, ran
  its engine or CLI, or substantively applied its templates/doctrine.
  **Design-only use, authoring-only use, and maintaining the tool's own repo all
  count.**
- When the tool is a skill in a repo you are also developing, its authoritative
  body is the working-tree `SKILL.md` — the installed cache can run *behind* or
  *ahead* of it. Read the working-tree file before reporting on the skill's
  current behavior, and **record which copy you actually exercised**, flagging
  any skew (`references/mechanics.md` has the two directions).

## Were you asked, or did you notice?

- **Asked** ("write the feedback reports", "tooling feedback", "dogfood report") —
  write now, no confirmation step. A **standing per-session directive** (a
  CLAUDE.md "run tool-feedback at session close" mandate) is the asked branch:
  treat it as asked and write — in an autonomous session, offer-first deadlocks.
- **You noticed** the session winding down after exercising registered tools —
  do not auto-write. Emit a **single one-line offer** naming the tools: *"This
  session exercised keel and convoy — want the two feedback reports?"* If
  declined or ignored, drop it for the session.
- Can't tell which? Offer.

## Workflow

1. **Resolve targets and destination.** From the bindings table (or an inline
   ask), list every registered tool the session **used** (per the binding
   section's definition); one report per tool, plus one per additional distinct
   concern or surface where that applies. A tool named but never exercised
   gets a one-line "no report" back to the user — not an empty file. Destination
   precedence: a dir the user named *this session* → the registered feedback dir
   → the tool's own repo — **named or registered only, never inferred**. A
   redirected destination moves the *write* only; the recurrence check (step 2)
   still reads the registered dir's index — state which baseline you used (fine
   print: `references/mechanics.md`).
2. **Check recurrence before drafting.** **Rebuild** the recurrence dir's
   `INDEX.md` first (the registered dir — step 1, even when the write is
   redirected)
   (`uv run --no-project python "${CLAUDE_PLUGIN_ROOT}/skills/feedback-triage/scripts/build_feedback_index.py" <dir>`),
   then scan it for a finding your candidate repeats. An existing index may
   predate recent reports or have been built by an older rule — rebuilding is
   cheap, idempotent, and the only staleness check that cannot false-positive;
   never degrade to a grep. A repeat is written as **"extends
   `<prior-file-stem>#<n>`"** (or "extends `<prior-file-stem>` §Misses" for a
   narrative finding) plus only the *new* evidence — never restated fresh.
3. **Route by ownership.** Engine/execution findings go to the engine tool's
   report; method/gate findings to the method tool's; skill findings to the skill
   collection's. If ownership is genuinely ambiguous, report it where it surfaced
   and say so — triage's ROUTE OUT is the backstop.
4. **Draft each report** (per tool per distinct concern — step 1) using the
   template below. Read the tool's version
   from its manifest (`plugin.json`, `pyproject.toml`, `__version__`) — never
   guess; under cache skew (above), record the version you actually ran and note
   the discrepancy.
5. **Self-check, then write** each report to
   `<resolved destination>/<YYYY-MM-DD>-<source-slug>.md` (step 1), slug distinct
   per wave/phase so reports never clobber earlier ones. Then **rebuild that
   destination's `INDEX.md`** (step 2's command, pointed at the destination) so
   the next session's recurrence check is one Read.

## Report template

```markdown
# <tool> feedback — <short title>

- **Date:** YYYY-MM-DD
- **Tool/version:** <name> <version — read from the manifest, never guessed>
- **Context:** <what the tool was applied to; which skills/components were exercised>
- **Outcome:** <one-line headline of how the session went>

## What worked
<where the tool earned its keep — name the features, so maintainers know which
complexity is paying for itself>

## Friction
<each item tagged [BLOCKER|HIGH|MED|LOW]; the concrete moment it cost time or
caused confusion — quantified when cheap (minutes lost, $ spent, retries)>

## Misses
<defects the tool failed to prevent — each with a severity tag AND the phase that
should have caught it ("phase: DoR", "phase: pre-mortem", "phase: gate",
"phase: review")>

## Vacuous gates
<anything that passed while hollow; "none observed" is a valid entry>

## Proposed promotions / changes
1. **[SEVERITY]** <suspected cause, one clause> → <the change that removes it, with its home>
2. **[SEVERITY]** extends `<prior-file-stem>#<n>` — <the new evidence only>

## Cost (optional — when engine or eval runs were involved)
<per-run or per-role cost/token table>
```

The numbered proposals are the report's **stable finding IDs** — `<file-stem>#1`,
`#2`, … — what triage docs and changelogs cite. Number proposals only; cite
friction/misses by file stem + section. (Triage mints its own `T1a` promotion IDs
— two namespaces, don't conflate them.) Your `extends` refs are load-bearing
downstream — triage follows the chain to cluster a lineage and count its
recurrence — so point them at the exact finding, not just the file.

A proposal opens with its **suspected cause** — the reporter holds the richest
evidence and triage clusters by cause; a symptom-only proposal makes the cold
triager re-derive what the session knew. It also carries its **resolution and
referents**: record a clarification the session already settled (or name the
deciding precedent), and name counted objects ("two holdout positives") —
otherwise the downstream lander re-derives them and can land the wrong one.

## Self-check before writing

- Every path the report cites exists.
- Version came from the manifest, not memory.
- Repeats are `extends` refs, not restatements.
- Severities present on friction, misses, and proposals; every miss names a phase;
  every proposal opens with its suspected cause.
- The report reads cold — a maintainer with zero session context can act on it.

## What this skill does NOT do

- Fix anything, edit the tool, or write CHANGELOG entries.
- Triage the backlog (that is `feedback-triage`, run periodically).
- Report on unregistered tools, or hunt for places to file reports.
- Capture general session knowledge — run `journaling-sessions` for that; a session
  can warrant both.

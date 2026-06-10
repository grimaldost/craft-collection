---
name: tool-feedback
description: >
  Write a per-session dogfooding feedback report for each registered in-development
  tool the session exercised — what worked, friction, misses with the phase that
  should have caught them, vacuous gates, and severity-tagged proposed changes with
  stable finding IDs — saved into that tool's own feedback directory. Use when the
  user asks for feedback on their tools ("write the feedback reports", "tooling
  feedback", "dogfood report", "capture the friction with keel / pr-pilot"), and
  offer once, unprompted, when a session that exercised a registered tool is winding
  down. Registered tools come from a feedback-targets table the user supplies (e.g.
  in CLAUDE.md) — never hunt the filesystem for targets. Design-only or
  authoring-only use of a tool still counts as use. Not for feedback on code or PRs
  (that is code review), not for capturing general session knowledge into a memory
  store (that is journaling-sessions), and not for product feedback to a third-party
  vendor.
user-invocable: true
---

# Tool Feedback

Tools in active development improve only if every session that uses them reports
back. This skill writes that report — one per tool, into the tool's own repo — in a
format the downstream `feedback-triage` pass can cluster: severity-tagged findings,
stable IDs, the phase that should have caught each miss, and explicit links when a
finding repeats an earlier one. The report is raw material for the tool's backlog;
the quality bar is "can a maintainer act on this cold."

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
  runs". Read and honor it.
- The session **used** a tool if it invoked any of its skills/agents/commands, ran
  its engine or CLI, or substantively applied its templates/doctrine.
  **Design-only and authoring-only use counts.**

## Were you asked, or did you notice?

- **Asked** ("write the feedback reports", "tooling feedback", "dogfood report") —
  write now, no confirmation step.
- **You noticed** the session winding down after exercising registered tools —
  do not auto-write. Emit a **single one-line offer** naming the tools: *"This
  session exercised keel and pr-pilot — want the two feedback reports?"* One offer,
  not a nag; if declined or ignored, drop it for the session.
- Can't tell which? Offer.

## Workflow

1. **Resolve targets.** From the bindings table, list every registered tool the
   session used. One report per tool.
2. **Check recurrence before drafting.** Grep each tool's feedback dir for the key
   terms of each candidate finding. A repeat is written as
   **"extends `<prior-file-stem>#<n>`"** (or "extends `<prior-file-stem>` §Misses"
   for a narrative finding) plus only the *new* evidence — never restated fresh.
3. **Route by ownership.** Engine/execution findings go to the engine tool's
   report; method/gate findings to the method tool's; skill findings to the skill
   collection's. If ownership is genuinely ambiguous, report it where it surfaced
   and say so — triage's ROUTE OUT is the backstop.
4. **Draft one report per tool** using the template below. Read the tool's version
   from its manifest (`plugin.json`, `pyproject.toml`, `__version__`) — never guess.
5. **Self-check, then write** each report to
   `<repo>/<feedback dir>/<YYYY-MM-DD>-<source-slug>.md`, slug distinct per
   wave/phase so reports never clobber earlier ones.

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
caused confusion>

## Misses
<defects the tool failed to prevent — each with a severity tag AND the phase that
should have caught it ("phase: DoR", "phase: pre-mortem", "phase: gate",
"phase: review")>

## Vacuous gates
<anything that passed while hollow; "none observed" is a valid entry>

## Proposed promotions / changes
1. **[SEVERITY]** <candidate template / gate / doc / skill change, with its home>
2. **[SEVERITY]** extends `<prior-file-stem>#<n>` — <the new evidence only>

## Cost (optional — when engine or eval runs were involved)
<per-run or per-role cost/token table>
```

The numbered proposals are the report's **stable finding IDs** — `<file-stem>#1`,
`#2`, … — what triage docs and changelogs cite. Number proposals only; cite
friction/misses by file stem + section.

## Self-check before writing

- Every path the report cites exists.
- Version came from the manifest, not memory.
- Repeats are `extends` refs, not restatements.
- Severities present on friction, misses, and proposals; every miss names a phase.
- The report reads cold — a maintainer with zero session context can act on it.

## What this skill does NOT do

- Fix anything, edit the tool, or write CHANGELOG entries.
- Triage the backlog (that is `feedback-triage`, run periodically).
- Report on unregistered tools, or hunt for places to file reports.
- Capture general session knowledge — run `journaling-sessions` for that; a session
  can warrant both.

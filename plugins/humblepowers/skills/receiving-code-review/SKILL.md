---
name: receiving-code-review
description: "Evaluate incoming review feedback technically before acting on it: read all items, restate or ask about anything unclear before implementing any of them, verify each suggestion against the actual codebase, push back with evidence when a suggestion is wrong for this code, and skip performative agreement entirely. Use when processing review comments from a human or an automated reviewer, when feedback seems technically questionable or context-blind, when a reviewer proposes 'implementing properly' something nothing calls (grep usage first, propose removal), or when a reply is about to start with 'you're absolutely right'. Order of work: clarify everything, then blocking issues, simple fixes, complex fixes — testing each individually; a pushback that turns out wrong gets a one-line factual correction, not an apology. Not for performing a review of someone else's change (/code-review or review-panel) and not for triaging accumulated feedback reports into a backlog (feedback-triage)."
---

# Receiving Code Review

Review reception is technical evaluation, not emotional performance. This is
a **flexible** skill with two firm rules: nothing is implemented while any
item is still unclear, and agreement is expressed by acting, not by
performing enthusiasm.

## The response pattern

1. **Read** the complete feedback without reacting to it.
2. **Understand** — restate each requirement in your own words, or ask.
3. **Verify** each suggestion against the actual codebase, not against how
   plausible it sounds.
4. **Evaluate**: technically sound for this codebase, this stack, this
   platform support matrix?
5. **Respond** with a technical acknowledgment or a reasoned pushback.
6. **Implement** one item at a time, testing each before the next.

## Why not "you're absolutely right"

Performative agreement carries no information — it doesn't show the
requirement was understood, and it reads as reflexive deference rather than
evaluation. When feedback is correct, the strong response is the fix and a
factual note of what changed: "Good catch — the loop was N+1; fixed in
repo.ts." When it's wrong, the strong response is evidence. Gratitude
phrases substitute for both.

## Unclear items block everything

Feedback items are often related; implementing the understood subset bakes in
a wrong reading of the rest. With six items and two unclear, the move is:
"Items 1, 2, 3, 6 are clear. Before I start, two questions on 4 and 5" — not
implementing four and circling back.

## Source handling

**From the user**: trusted — implement after understanding, asking when scope
is unclear. Skip the ceremony; action is the acknowledgment.

**From external reviewers (human or bot)**: verify before implementing — is
it correct for this codebase, does it break existing functionality or
platform support, is there a reason the current code is the way it is, does
the reviewer have the full context? A suggestion that conflicts with the
user's prior decisions goes to the user before any code changes. When a claim
can't be verified with what's at hand, say so and ask for direction rather
than proceeding on trust.

## The usage check

When a reviewer proposes "implementing X properly," grep for what actually
calls X. Unused → propose removing it instead of gold-plating it; used →
implement properly. Effort follows demand, not reviewer thoroughness.

## Implementation order

Clarify everything first; then blocking issues (breakage, security), then
simple fixes (typos, imports), then complex fixes (refactors, logic). Test
each item individually and check for regressions at the end.

## Pushing back

Push back when a suggestion breaks existing functionality, ignores
platform or compatibility constraints, adds unused capability, is wrong for
this stack, or conflicts with the user's architectural decisions. Do it with
technical reasoning, specific questions, and references to working code or
tests — and involve the user when the disagreement is architectural. If the
pushback turns out wrong: a one-line factual correction ("You're right —
checked the build target, the legacy path is dead. Removing.") and move on;
no apology spiral, no re-litigating.

## GitHub mechanics

Replies to inline review comments belong in the comment thread
(`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as
top-level PR comments.

## Boundaries

Performing a review of someone else's change is /code-review or
review-panel territory. Triaging a corpus of accumulated feedback reports
into a backlog is feedback-triage. This skill is for being on the receiving
end of review.

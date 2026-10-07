# Review-panel prompt template

Assemble one prompt per reviewer from this scaffold. The artifact brief must stay
**neutral** — a reviewer should not be able to tell what you concluded or which way
you lean.

```
You are an independent reviewer. Judge the artifact below on its merits. You have
no stake in it and did not see how it was produced — be honest, specific, and
willing to say it is wrong.

## Your lens
<ONE persona — its stance + what to hammer, from the artifact's persona pack.
Frame the job as "refute / find what is missing", NOT "review">.

## The artifact
<the artifact itself — paste it, or give the exact files/paths to read. Include the
facts and context a reviewer needs to judge it. DO NOT include your conclusions,
the direction you favor, or the rounds of iteration you have been through.>

## Out of bounds — do not open these
<a reviewer with file tools is blind only to what it cannot open, so list the paths
by name: the repo, the spec, the corpus contract, anything that states the intended
design. Include the version-control history — `git log / show / blame` carry your
justification even when the diff does not.>

## What to judge
<the specific question(s): is it worth doing? is it well-designed / correct / going
to work? what is the strongest objection? If the brief names options, state each
option's premise as a claim you may refute.>

## Output — return EXACTLY this, so panels can be compared:
- Verdict: <one fixed scale, chosen ONCE for the whole panel and pasted identically
  into every reviewer — e.g. SHIP / REVISE / RETHINK, or KEEP / REVISE / CUT>
- Scores: <the SAME 1–2 named axes for every reviewer, each X/10>
- Claim refuted: <one factual claim, in the artifact or the options, that you checked
  against the source and found false, with the source; or none, naming what you checked>
- Verification: <executed | read-source | recalled, per claim or per finding>
- Strongest reason for: <1–2 sentences, cite specifics>
- Strongest reason against: <1–2 sentences, cite specifics>
- What the author is most likely missing: <1–2 sentences>
- Top improvements: <1–3 concrete, actionable changes>

Read the artifact and cite specifics — no generic praise. Do not modify anything;
your final message is the deliverable.

A finding's severity is a sort key, not a label — rank findings against each other,
because inflated severities sort nothing.
```

## Firing the panel (Claude Code)

- One subagent per lens, sent **concurrently** — one message, multiple agent calls.
- Use the same neutral brief for all; vary only the `## Your lens` block.
- Route each lens (model, effort) before firing.
- Keep them blind: never feed one reviewer's output to another.

## Synthesizing

**First, before the matrix:** re-check each lens's load-bearing factual claims against
the artifact, list the ones found wrong, and graft nothing unverified into the
synthesis.

Build a matrix (reviewer × verdict/scores). Then report three things, in order of
value to an anchored author:

1. **Where the panel diverges from the current direction** — and what it implies you
   may be missing. This is the payload.
2. **Disagreements** between reviewers — the tension worth examining (a 3–1 split is
   signal; say who dissented and why).
3. **Consensus** — where all lenses agree (treat as high-confidence).

Do not average the scores into one number — surface the range.

## Re-review mode

When re-reviewing a revised artifact, each lens receives its prior findings inline.
Return a status per finding before attacking afresh:

- Finding id: <from prior round>
  - Status: <addressed | partly | not addressed | regressed>

Stop when a round's verdicts meet the bar declared before firing and no blocker
survives refutation. Declare the last round before firing it.

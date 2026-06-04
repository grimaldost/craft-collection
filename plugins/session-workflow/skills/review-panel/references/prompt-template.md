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

## What to judge
<the specific question(s): is it worth doing? is it well-designed / correct / going
to work? what is the strongest objection?>

## Output — return EXACTLY this, so panels can be compared:
- Verdict: <pick a fixed scale, e.g. SHIP / REVISE / RETHINK, or KEEP / REVISE / CUT>
- Scores: <1–2 named axes, each X/10>
- Strongest reason for: <1–2 sentences, cite specifics>
- Strongest reason against: <1–2 sentences, cite specifics>
- What the author is most likely missing: <1–2 sentences>
- Top improvements: <1–3 concrete, actionable changes>

Read the artifact and cite specifics — no generic praise. Do not modify anything;
your final message is the deliverable.
```

## Firing the panel (Claude Code)

- One subagent per lens, sent **concurrently** — one message, multiple agent calls.
- Use the same neutral brief for all; vary only the `## Your lens` block.
- Opus for high-stakes panels.
- Keep them blind: never feed one reviewer's output to another.

## Synthesizing

Build a matrix (reviewer × verdict/scores). Then report three things, in order of
value to an anchored author:

1. **Where the panel diverges from the current direction** — and what it implies you
   may be missing. This is the payload.
2. **Disagreements** between reviewers — the tension worth examining (a 3–1 split is
   signal; say who dissented and why).
3. **Consensus** — where all lenses agree (treat as high-confidence).

Do not average the scores into one number — surface the range.

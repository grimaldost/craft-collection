---
name: review-panel
user-invocable: true
description: Use when the user has iterated on a design, plan, spec, architecture, code, or prose over several rounds and can no longer judge it cleanly, before a high-stakes or hard-to-reverse decision, or when they ask for "fresh eyes", "a second opinion", "red team this", "poke holes in this", "sanity-check this independently", "am I anchored" / "too close to this", "critique this from different angles", or run "/review-panel". Prefer this over reviewing the artifact yourself — its value is convening fresh reviewer subagents that are blind to this conversation and to each other, which a review you run while anchored on the same context cannot replicate. Claude Code only (it spawns subagents); always show the plan and rough cost and ask before firing. Not for a quick factual check, a single obvious answer, or a first-pass review of something just created.
---

# Review Panel

Fresh, independent eyes on something you have been too close to. After many rounds
on an artifact, both the user and the model **anchor** on the current direction —
each new pass defends it rather than questioning it. A panel of agents that have
*never seen the iteration*, pointed at the artifact from adversarial angles,
surfaces what the anchored view structurally cannot. The deliverable is a
**comparison and synthesis**, not a single opinion.

## When to convene — and at what size

Convene when the cost of being wrong exceeds the cost of the panel:

- you have iterated many rounds and genuinely can't tell if it's good anymore;
- a high-stakes or hard-to-reverse decision (architecture, a launch, a structural choice) —
  **including a design or spec _before_ any build**, where pre-code defects (a wrong interface, a
  missed failure mode, a motivated assumption) are cheapest to fix;
- an explicit ask: "fresh eyes", "second opinion", "red team", "poke holes", "am I anchored", `/review-panel`.

**A design/spec is panel-ready only when it is concrete enough to critique** — explicit interfaces,
failure modes, data flow, and at least one worked example. Panelling a bare sketch or intent yields
bikeshedding and false confidence, not defects; iterate it to concreteness first (or fire a single
Level-1 contrarian instead). Design-stage review is a qualifier on the high-stakes trigger above,
not a standing "always review the design" gate.

Scale effort to stakes — **the ladder** (don't fire a full panel at a Level-1 question):

| Level | Convene | For |
|---|---|---|
| 1 — Solo contrarian | 1 fresh agent told to *refute* | a quick gut-check |
| 2 — Small panel | 2–3 lenses (skeptic + domain expert [+ user]) | a normal decision |
| 3 — Full panel | 4–5 lenses | an expensive / irreversible call |

## The protocol — this is what makes it work

1. **Curate a NEUTRAL artifact brief.** Like a context hand-off, but stripped of
   your conclusions. Give reviewers the artifact and what to judge — **never**
   "here's what I decided, do you agree?". Do not narrate the rounds you've been
   through or the direction you favor; that re-anchors them on you. State facts,
   not your verdict.
2. **Pick the lenses.** Default quartet: **Skeptic/Minimalist**, **Best-Practices
   Auditor**, **End-User Advocate**, **Domain Expert**. For depth, load the persona
   pack for the artifact type (below) and tailor a couple of personas to specifics.
3. **Make them blind and adversarial.** Each reviewer is blind to the others and to
   this conversation. Frame the job as *refute / find what's missing*, not "review"
   — independence over politeness.
4. **Demand structured, comparable output** — a fixed per-reviewer schema (verdict +
   scores + reasons) so results sit side by side. See `references/prompt-template.md`.
5. **Fire them.** In Claude Code, spawn one subagent per lens, concurrently (one
   message, multiple agent calls; Opus for high stakes). **Always show the plan
   first** — how many agents, which lenses, the rough cost — and get a go-ahead.
   This is expensive; never fire silently.
6. **Synthesize — don't average.** Produce a comparison matrix, where they **agree**
   (consensus = high confidence), where they **disagree** (the tension worth
   examining), and — most important for an anchored author — **where the panel
   diverges from the current direction, and what you may be missing.**

## Persona packs — load the one that fits

| Artifact | Pack | Lenses |
|---|---|---|
| design / spec / architecture | `references/personas-design.md` | architect · skeptic · user · ops |
| code / a diff | `references/personas-code.md` | security · performance · correctness · maintainability |
| writing / docs | `references/personas-writing.md` | editor · fact-checker · audience · misreader |
| plan / decision | `references/personas-plan.md` | premortem · dependencies · cost · stakeholder |
| research / a claim | `references/personas-research.md` | refuter · methodology · sources · bias |

The default quartet works for anything; the packs sharpen it. Mix and match.

## Guard-rails

- **Claude Code only.** This spawns subagents; it does not work in web chat (no
  subagent primitive). If asked there, say so and offer the manual fallback: paste
  the neutral artifact brief into N separate fresh chats yourself.
- **Cost is real.** N agents at Opus is not free. Always present the plan + estimate
  and get the go-ahead; offer to drop a ladder level if the stakes don't justify a
  full panel.
- **Independence is the whole point.** Brief reviewers with your conclusion and you
  have wasted the panel. Keep the artifact brief neutral and the reviewers blind.
- **You synthesize; they don't decide.** The panel informs; the call stays with the
  user. Surface the range, including the lone dissent — a 3–1 split is signal.

## What this does NOT do

- Replace a quick factual check or a single obvious answer — just answer it.
- Auto-fire — it proposes and waits for the go-ahead.
- Reach consensus by averaging — disagreement is the signal, not noise.

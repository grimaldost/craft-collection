---
name: brainstorming
description: "Turn an idea into an agreed design before implementation — explore project context, ask clarifying questions one at a time, propose two or three approaches with trade-offs and a recommendation, present the design in sections for approval, and record the agreed design. Use when the user proposes a feature, component, behavior change, or project whose requirements or shape are not yet pinned ('let's build', 'I want to add', 'how should we approach'), or when one request bundles several independent subsystems and needs decomposition before any single design is refined. Design before code holds for small work too — a simple project gets a proportionally short design, not an exemption. Hands the agreed design to the planning tool that owns execution (keel for governed series, plan mode or your orchestrator otherwise). Not for work already specified to execution level, and not for discussion turns where the user is thinking aloud and wants assessment rather than artifacts."
---

# Brainstorming

Turn an idea into a design the user has agreed to, through dialogue — then
hand it to planning. This is a **flexible** skill with one firm gate, stated
once: implementation starts after the user approves a design. Small work gets
a proportionally small design — a few sentences can be enough — rather than
an exemption, because simple-looking projects are where unexamined
assumptions cost the most rework.

## The flow

1. **Explore project context first.** Files, docs, recent commits — before
   asking the user anything they shouldn't have to repeat.
2. **Check scope before refining.** A request that bundles several
   independent subsystems (chat, billing, storage, analytics) gets decomposed
   first: what are the pieces, how do they relate, what order. Then design
   the first piece through the normal flow. Don't spend questions polishing
   details of something that needs splitting.
3. **Ask focused questions, one decision at a time.** One question per turn by
   default; for an expert user facing orthogonal decisions, batch a few into one
   turn via the host's question UI rather than forcing strict serialization.
   Multiple choice when it fits, open-ended when it doesn't. Aim at purpose,
   constraints, and success criteria.
4. **Propose two or three approaches** with trade-offs. Lead with the
   recommendation and the reasoning, not a neutral menu.
5. **Present the design in sections,** each scaled to its complexity — a few
   sentences when straightforward, a few hundred words when nuanced. Confirm
   each section before the next. Cover architecture, components, data flow,
   error handling, and testing — and, for work an agent or capped spawn will
   execute, whether the turn/time/cost budget suffices for the expected work.
6. **Record the agreed design** where the project keeps specs (user
   preference wins; a dated file under the repo's design-docs convention is a
   sensible default). Then self-review it with fresh eyes: placeholders or
   vague requirements, internal contradictions, scope too large for one
   implementation plan, requirements readable two ways. Fix inline.
7. **The user reviews the written spec.** Requested changes loop back;
   approval hands the spec to the planning tool that owns execution — keel
   for a governed series, plan mode or your orchestrator otherwise.

## Design for isolation

Break the system into units that each have one clear purpose, communicate
through defined interfaces, and can be understood and tested independently.
Two checks: can someone tell what a unit does without reading its internals,
and can the internals change without breaking consumers? Well-bounded units
are also easier to hold in context — reasoning and edits are more reliable
when files are focused, and a file that has grown large is usually doing too
much.

## In existing codebases

Explore the current structure before proposing changes, and follow its
patterns. Where existing code has problems that genuinely affect the work —
a tangled module the feature must touch — targeted improvement belongs in the
design. Unrelated refactoring doesn't.

## Working principles

One focused question per turn (batch orthogonal decisions for an expert user) ·
cut features that aren't needed yet, ruthlessly ·
alternatives before settling · validate incrementally rather than presenting
a finished monolith · go back when something stops making sense.

## Boundaries

Work already specified to execution level goes straight to planning or
implementation. A user thinking aloud gets assessment, not artifacts — the
deliverable of a discussion turn is your judgment, until they ask for the
design.

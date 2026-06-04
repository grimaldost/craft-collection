---
name: journaling-sessions
description: Capture knowledge from a work or reference-reading session into structured, separable, retrieval-ready entries for a long-term memory store. Use when the user says "journal", "log this", "wrap up", "session summary", "capture what we learned", or "create registries for everything" — and equally on any request to preserve what was worked out for the future, even about one specific topic — phrasings like "record the decisions/dead ends", "note the reasoning", "don't lose this", "before I forget", "so next time we don't relitigate", "so a future session benefits". Activate proactively when a substantive session is ending after 3+ decisions, findings, or ingested reference items. Covers implementation/decision sessions and end-to-end reference ingestion. Not for quick Q&A or sessions with no novel knowledge; not for consolidating prior journals into higher-level patterns (that is a separate downstream pass).
---

# Journaling Sessions

Capture what a session produced as **structured, separable, retrieval-ready
entries** — prose with metadata, one idea each — that a future session can find
and reason about in isolation. The quality bar is not "does this summarize the
session" but "will a future session, retrieving this cold months from now, be
measurably better for having it."

These entries are raw material: a downstream process clusters many of them into
generalizations, and repeated reinforcement promotes the durable ones into
long-lived guidance. Write each entry so that clustering works — that is what
every rule here optimizes for.

This skill produces raw capture. It runs an **automatic multi-pass loop** so you
get thorough output from a single invocation — you do not need to ask for
"multiple passes."

## What a session produces

Three kinds of knowledge; capture all three, not only the most obvious:

- **Conclusions** — decisions made, facts discovered, tradeoffs analyzed,
  hypotheses formed. What a meeting summary would contain.
- **Process dynamics** — the shape of the reasoning: where breakthroughs
  happened, where we got stuck, what surprised us, what assumptions proved wrong.
- **Perceptions** — what the user cared about, what engaged them or felt like
  overhead, what they pushed back on and why.

The three-part framing is a coverage checklist, not a prediction of how entries
cluster. Underjournaling conclusions is fine; underjournaling perceptions is a
systematic blind spot.

## When to produce

- The session was substantive (not quick Q&A).
- Something was decided, discovered, or perceived worth remembering.
- An authoritative source was read/ingested end-to-end.
- The user asks ("journal", "log this", "wrap up"), or the session is clearly
  ending.

## Were you asked, or did you notice? — write, or offer first

How this skill activated decides whether you write the journal now or only offer
it. The journal is real work — often several thousand tokens — and every entry
you write lands in the user's long-term store; producing one unbidden, or on a
session that wasn't worth it, is the cost to avoid.

- **The user asked — write now.** "journal", "log this", "wrap up", or any
  request to preserve what was worked out ("don't lose this", "before I
  forget", "so next time we don't relitigate"). Run the loop below and write the
  file. No confirmation step.
- **You activated on your own — offer first.** The session is winding down and
  you judged it substantive (3+ decisions/findings), but the user voiced no wish
  to capture — e.g. a bare "that's everything, thanks." Do **not** write the
  journal. Emit a **single one-line offer** naming what is capturable, then stop:
  *"This session worked out 4 decisions and a dead end worth journaling — want me
  to capture them?"* Write the entries only after the user accepts.
  - **One offer, not a nag.** If the user declines, ignores it, or says stop, do
    not offer again this session.
  - **Match a shown cadence.** If the user already journaled once this session,
    you may offer again when the next arc of work finishes — they've shown they
    want this session captured.

When you can't tell which path you're on, offer — don't auto-write.

## Pick the mode

Most sessions are one of two shapes; the capture questions differ. Pick first.

- **Implementation / decision mode** — the session did work: made a choice,
  diagnosed a bug, designed a component, ran an experiment, built something. Use
  the Conclusions / Process / Perceptions framework below.
- **Reference-ingestion mode** — the session converted an authoritative source
  (standard, textbook, regulation, paper, framework docs, teaching material) into
  entries. The reliable signal: most entries would have `origin: reading`. Use
  the eight-category taxonomy in **`references/reference-ingestion.md`**, and
  detect any declared downstream use (implementation / teaching / cross-project /
  positioning) before capturing — that file explains how.

A session can be both (implementation-targeted reference-ingestion is canonical);
run both frameworks.

## The workflow — automatic multi-pass

Once you are writing — the user asked, or accepted your offer (see "Were you
asked, or did you notice?" above) — produce all entries in a single file. Do not
pause for approval between entries. If a journal file already exists
for this session, read it first and only add what is not yet captured. If the
session contains ready-made entry drafts (e.g. from a questioning/critique pass),
include them verbatim — they are already shaped — then add the rest.

Then run this loop internally, before presenting anything:

1. **Identify the mode** (+ downstream use if reference-ingestion).
2. **Pass 1** — produce all entries for the chosen framework.
3. **Self-check (silent)** against the three coverage axes in
   **`references/coverage-check.md`**: source, downstream-use, measurability.
4. **If gaps:** run pass N+1 adding *only* the missing entries. Repeat until the
   coverage signals are clean, or a **3-pass cap** is reached. Pass 1 routinely
   under-captures, often by a lot; this loop is the mitigation, not optional.
5. **Present once:** the file, the entry count and its breakdown by entry type
   ("ran K passes; coverage clean").
6. **One surviving offer:** only if a downstream use was *declared* and remains
   thin after the cap, offer a single targeted pass naming the specific axis.
   Otherwise stop — do not offer a generic "second pass."

For long runs (40+ entries), save after each arc to avoid quality drift; the user
can say "continue journaling" to resume.

## How to produce — implementation mode

Work through these in order. Skip any with no answer. Each becomes one or more
entries. Aim for at least one process or perception entry per session.

**Conclusions.**
- *What was decided?* What was chosen, what was rejected, what evidence drove it.
  Include the WHY — the reasoning matters more than the outcome.
- *What was discovered?* Bugs diagnosed, research findings, empirical
  observations, undocumented patterns. Include the source.
- *What tradeoffs were analyzed?* Approaches compared, dimensions used, winner,
  conditions where the loser would win.
- *What hypotheses changed?* Created, confirmed, refuted, with the evidence.
- *What contradicted existing knowledge?* Both sides and how to resolve.
- *What connects across domains?* Structural similarities, shared principles.

**Process dynamics.**
- *Where did breakthroughs or turning points happen?* The reframing question, the
  observation that changed direction — high-value reusable reasoning patterns.
- *Where did we get stuck or go wrong?* Dead ends, wrong assumptions, wasted
  effort, what Claude got wrong and how it was corrected. A system that only
  remembers successes has survivorship bias.
- *What assumptions did Claude bring that were challenged?* Default
  recommendations pushed back on, consensus that didn't apply.

**Perceptions.**
- *What did the user care about most* — not the topic, but what within it
  mattered (depth vs speed, correctness vs progress, elegance vs pragmatism).
- *What was the user's energy like* — what engaged them vs felt like a chore.
- *What would help a future instance work better with this user on this topic?*

## How to produce — reference-ingestion mode

Work through the eight categories in **`references/reference-ingestion.md`** in
order, checking each against the source before deciding it does not apply.
Aim for at least one OBSERVATION entry on the source-reading dynamics.

## Output

Write entries in the structured envelope defined in
**`references/output-format.md`** — the envelope, the full field set (including
visibility and language), entry types, the ANTI_PATTERN template, area/domains,
refs, confidence, multi-user privacy, and the VALIDATED marker.

**No long-term memory store downstream?** The metadata envelope exists to be
machine-ingested and clustered. If these entries are only for your own re-reading
— no vector store or ingestion pipeline — emit each entry's CONTENT prose and skip
the envelope. Keep the discipline that carries the value (one idea per entry,
reasoning inline, anti-patterns hunted); drop only the ceremony.

## Writing quality

Five rules carry most of the value; the full craft is in
**`references/writing-for-retrieval.md`**:

1. **Be concrete and include the reasoning inline.** "Haiku passes gates at
   Sonnet's rate for 5-15x less cost" beats "Haiku is cheaper."
2. **One idea per entry.** If it wants to exceed ~300 words, it's two entries.
3. **Anti-patterns are the most valuable entries** — actively hunt for what was
   tried and failed, not only what worked.
4. **Apply the reconstruction test at drafting time:** would a future instance
   benefit from this *specifically*, vs. reconstructing it from generic training?
   If training already covers it, don't draft it.
5. **Front-load the distinctive concept** and use specific names — the first
   sentence does the heaviest retrieval work.

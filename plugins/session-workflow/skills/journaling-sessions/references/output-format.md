# Output Format — structured journal entries

How to write a well-formed journal entry. This is the full, default format —
every journaling session uses it. It produces separable, retrieval-ready entries
for a long-term memory store: raw captures that a downstream process will cluster
into generalizations and, with reinforcement, promote into durable guidance.

## Contents

1. The entry envelope
2. Why explicit markers (not running prose)
3. Field reference
4. Authorship and multi-user privacy
5. Entry types
6. Writing ANTI_PATTERN entries
7. Area and domains — how they work together
8. refs and supersession
9. Confidence calibration
10. The VALIDATED marker

---

## 1. The entry envelope

```
--- ENTRY_START ---
type: DECISION | FINDING | OBSERVATION | TRADEOFF | HYPOTHESIS | CONTRADICTION | CONNECTION | ANTI_PATTERN
author: <stable user ID — e.g., user:alex-rivera>
timestamp: <ISO 8601 — when journaled>
occurred_at: <optional ISO 8601 — when the event happened, if different>
area: <single value — the life area or activity, e.g., platform_engineering>
language: <ISO 639-1 code — en, pt, etc. Default from author preference.>
origin: chat | code | meeting | reading
visibility: private | team:<n> | public
session: <kebab-case-session-name>
domains: <2-5 tags, free-form — at least one broad, one narrow>
entities: <optional comma-separated people, products, systems referenced>
confidence: <0.0-1.0>
refs: <optional — H-035, investigation-16, arXiv:2501.13956, supersedes:K-002>
summary: <optional — single sentence compact version for progressive disclosure>
--- CONTENT ---
<prose — one idea, concrete, with reasoning>
--- ENTRY_END ---
```

## 2. Why explicit markers (not running prose)

The `--- ENTRY_START ---` / `--- ENTRY_END ---` markers are separability
enforcement, not formatting preference. Coherent prose flowing between entries
creates plausible-distractor effects at retrieval time (Chroma 2025 on
long-context performance) and lets an embedder treat adjacent entries as a
single narrative when it should treat them as separable evidence. Never run
prose across boundaries, add narrative connective tissue between entries, or
compress multiple entries into one envelope.

## 3. Field reference

`author` is the identity of whose memory this entry belongs to, not who is
discussed in the content. An entry by Alex about a colleague still has
`author: user:alex-rivera`. **Format:** `user:<identifier>` where the
identifier is stable, lowercase, and uniquely identifies the human whose memory
this is.

`timestamp` is when the entry was journaled. `occurred_at` is when the event
actually happened, filled in when it differs from journaling time. If you
journal on Thursday a decision made Monday, `timestamp` is Thursday and
`occurred_at` is Monday.

`area` names the life domain or activity this entry belongs to. Single-valued on
purpose: forcing one choice keeps the vocabulary clean. Examples:
`platform_engineering`, `api_development`, `language_learning`,
`endurance_training`, `home_cooking`.

`language` is the ISO 639-1 code of the entry's prose, defaulting to the
author's preference. It lets retrieval scope to one language when the store holds
several.

`origin` records where the knowledge came from. `chat` = a conversation session.
`code` = extracted from a code review, implementation log, or commit. `meeting` =
a conversation with other humans. `reading` = research notes from a paper,
standard, or article.

`visibility` controls how broadly an entry can be retrieved in a multi-user
store. `private` (the default) means only the author retrieves it. `team:<n>`
means a named team can. `public` means anyone can. Most entries should be
private; elevate only when the knowledge is genuinely general.

`entities` anchors the embedder on specific named references. Use the most
specific form available: "Alex Rivera (backend team)" rather than just "Alex".
Free-form for now.

`session` is a kebab-case name for the arc this entry belongs to. Long sessions
that span multiple arcs use arc-specific names (`qdrant-selection`,
`protocol-design`) rather than one broad name.

`summary` is optional but recommended for entries longer than 200 words: a
single sentence capturing the essence, used for progressive disclosure when a
cluster is large.

## 4. Authorship and multi-user privacy

A store may hold many authors' memories; retrieval filters by `author` so one
person's sessions do not pollute another's queries and privacy boundaries hold.
A missing `author:` is a bug, not an optional omission. The author is *whose
memory this is*, not *who is discussed*. When the content names people or
entities that could collide with other names in the store, disambiguate inline
("Alex — the backend team, not the client contact") rather than relying on the
embedder.

## 5. Entry types

- **DECISION** — a choice was made. What, why, what was rejected.
- **FINDING** — something was discovered through investigation or data.
- **OBSERVATION** — a noteworthy pattern, quality issue, process insight, or
  perception about the session, the user, or the reasoning process itself. Use
  when the entry is meta-level (about HOW work is happening, not WHAT was
  decided or found). If unsure: does it describe the conversation, the
  collaboration, or the reasoning? If yes, OBSERVATION. If it describes the
  domain being discussed, it's probably FINDING.
- **TRADEOFF** — approaches were compared with explicit dimensions.
- **HYPOTHESIS** — a claim was created, validated, or refuted.
- **CONTRADICTION** — existing knowledge conflicts with new evidence.
- **CONNECTION** — a pattern in one domain maps to another.
- **ANTI_PATTERN** — an approach that looked reasonable was tried or strongly
  considered, failed for a specific reason, and the failure generalizes.

## 6. Writing ANTI_PATTERN entries

Anti-patterns are the most valuable entries in the journal. Most knowledge
capture records what worked; expertise lives in what didn't. A good ANTI_PATTERN
entry answers four questions:

1. **What was tried or strongly considered?** Name the specific approach
   concretely. "Three-tier MemoryStore hierarchy." Not "an over-complex store
   design."
2. **Why did it look reasonable?** The tempting logic that led someone
   (including future instances) toward it. This is the trap — future sessions
   will feel the same pull.
3. **How did it fail?** The specific failure mode, not a vague "didn't work."
4. **When does the failure generalize?** The conditions that predict the same
   failure in other contexts.

Anti-patterns are distinct from CONTRADICTION (knowledge conflict) and TRADEOFF
(a deliberate live choice between viable options). Use ANTI_PATTERN when
something specifically looked good and specifically failed.

Example:

```
--- ENTRY_START ---
type: ANTI_PATTERN
author: user:alex-rivera
timestamp: 2026-04-14T16:30:00Z
area: platform_engineering
language: en
origin: chat
visibility: private
session: persistence-layer-architecture-qdrant
domains: api_design, abstraction_design, anti_pattern
entities: MemoryStore, VectorMemoryStore, HybridMemoryStore, Qdrant
confidence: 0.9
summary: A three-tier capability hierarchy collapses to two tiers whenever the middle tier has no independent backend, so the intermediate abstraction becomes aspirational documentation rather than a real contract.
--- CONTENT ---
Three-tier MemoryStore hierarchy (MemoryStore → VectorMemoryStore →
HybridMemoryStore) looks reasonable because it lets consumers declare
capabilities they need via the type system. The trap: the middle tier has no
independent backend — any store that supports vector search also supports
hybrid search. The hierarchy collapses to two real tiers in practice (plain k-v
and vector+hybrid), and the middle name becomes aspirational documentation
rather than a concrete contract. Rejected in favor of a single MemoryStore
protocol with SearchMode as a method parameter. Generalizes: capability
hierarchies fail whenever the supposed intermediate tier has no independent
implementation — the abstraction leaks immediately and forces consumers to know
which backend they're using anyway.
--- ENTRY_END ---
```

## 7. Area and domains — how they work together

Two fields jointly describe what an entry is about; they answer different query
patterns.

`area` (single-valued) names the life domain or activity where the entry
belongs — the primary scoping filter. `domains` (multi-valued, free-form) names
subject-matter concepts; it can be narrower than an area or cut across several.

The two together let you write precise queries: "area is platform_engineering
AND domains contains working_style" returns exactly what you want. Use 2-5 domain
tags per entry; fewer than two usually misses a broad tag, more than five usually
means multiple entries.

| area | domains | what the entry is about |
|------|---------|-----|
| `platform_engineering` | `working_style, comprehensive_capture` | a perception about how Alex prefers to capture knowledge |
| `platform_engineering` | `persistence, embedding_theory, anti_pattern` | a technical insight about why header-field markers fail with embedders |
| `language_learning` | `working_style, study_planning` | a perception about how Alex plans language study |
| `endurance_training` | `working_style, zone_2, habit_formation` | a perception about how Alex approaches endurance training |

`working_style` appears in three rows but `area` separates them — a query for
"working_style in platform_engineering" finds the first two and correctly
excludes language-learning and endurance.

**Context anchoring rule.** When a broad domain tag is used, the entry prose must
name the specific scope even though area encodes it structurally. "In
platform-engineering work, Alex prefers comprehensive capture" beats
"Alex prefers comprehensive capture" — the embedder reads only the content
field, so scope must appear in prose to influence clustering.

**Tag format:** short, lowercase, underscore-separated. Reuse tags from prior
entries when the subject matches; introduce new ones only when genuinely novel.

## 8. refs and supersession

`refs:` links entries across sessions, turning isolated entries into a traceable
graph. Populate it for: **continuation** (`refs: session:qdrant-selection, H-035`),
**challenge to prior knowledge** (`refs: supersedes:K-002`), **evidence source**
(`refs: arXiv:2501.13956`), or **validation target**
(`refs: questioning-round:persistence-architecture`).

**Supersession.** If an entry revises a prior decision or finding, mark it with
`supersedes:` in refs AND add a marker sentence at the end of CONTENT:

```
SUPERSEDES: [prior-entry-ref or prior-session:topic] — [brief explanation of
what changed and why the prior conclusion no longer holds].
```

The refs entry makes it queryable; the CONTENT marker makes the signal visible
to the embedder so supersession patterns cluster across sessions. **Do not
silently contradict** a prior entry — that pollutes the store with two
equally-valid-looking claims, which a downstream synthesis pass will cluster as
equally valid, producing confused generalizations.

## 9. Confidence calibration

Confidence is not "how sure it feels." It's "how much the evidence justifies."
Downstream filters, promotion rules, and synthesis weighting depend on it being
consistent across writers and sessions — a miscalibrated score doesn't just
mislead a reader, it changes whether an entry is ever promoted into durable
guidance. Anchor to evidence type, not to feeling:

| Range | Meaning | Typical evidence |
|-------|---------|------------------|
| 0.95–1.0 | Directly observed, reproducible, or mathematically necessary | Bug fix confirmed by failing-then-passing test. Behavior verified by running it. |
| 0.85–0.94 | Strong multi-source evidence or extensive investigation | 9-candidate evaluation with clear winner. Pattern observed 5+ times. |
| 0.70–0.84 | Solid reasoning with one strong piece of evidence | Typical DECISION confidence. Holds up but not stress-tested across scenarios. |
| 0.55–0.69 | Reasonable but partial | Tentative TRADEOFF, early design choice, HYPOTHESIS with one supporting observation. |
| 0.35–0.54 | Speculative but grounded | Pattern observed once, not yet tested. ANTI_PATTERN from a single failure. |
| 0.15–0.34 | Hunch, first impression, possibly artifact | Novel domain, small sample, unclear causation. |
| Below 0.15 | Not worth writing | Would add noise to the pipeline. |

**Calibration rules:**

- **Most DECISION entries land in 0.70–0.84.** Anything higher needs explicit
  evidence beyond "we thought about it and decided."
- **HYPOTHESIS entries cap at 0.69 by default.** If they're provable, they're
  FINDINGs — and promotion treats the two differently.
- **Perception entries rarely exceed 0.75.** Most signals about user priorities
  or working style are inferred from limited cues.
- **Survived-stress-testing bonus is +0.1.** A DECISION that passed genuine
  challenge earns a one-tier bump AND carries a VALIDATED marker (§10).
- **Confidence does not encode importance.** A 0.95 entry about a naming
  convention is less useful than a 0.65 entry about a controversial architecture
  choice. Importance belongs in the content.

Before writing a score, ask: what would need to change for me to revise this down
by 0.2? If the answer is "nothing concrete — I'd just feel differently," the
number is too high.

## 10. The VALIDATED marker

When a DECISION survived explicit stress-testing, encode that in the CONTENT
field itself — not only in the confidence number — because a downstream synthesis
pass clusters on CONTENT, and the stress-test signal only clusters with similar
signals if it appears in the prose. Required sentence at the end of CONTENT:

```
VALIDATED: survived questioning on [brief topic] — key challenges considered:
[1-2 sentence summary of what was challenged and how it held up].
```

Example closing: *"VALIDATED: survived questioning on whether local mode matches
production semantics — the HNSW-vs-brute-force gap was raised and dismissed
because dev tests use >50K vectors, which triggers HNSW in both modes."*

**When to apply it:**
- When a DECISION was stress-tested during the session — whether by a formal
  questioning pass or by substantive in-turn pressure-testing (specific
  alternatives considered, specific concerns raised, specific resolutions given).
- If a ready-made entry draft already carries the marker, preserve it verbatim.
- **Never invent VALIDATED** for decisions merely discussed, even at length. The
  test: can you name the specific challenge(s) considered? If yes, VALIDATED. If
  "we thought it through carefully," not VALIDATED.

This distinguishes a 0.85 DECISION that survived scrutiny from a 0.85 DECISION
that merely felt confident — but only if the marker is actually present.

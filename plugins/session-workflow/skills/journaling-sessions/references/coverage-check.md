# Coverage Check — the criteria the multi-pass loop runs

The core skill's workflow runs an **internal** capture → self-check → fill-gaps
loop before presenting anything. This file is the checklist that self-check runs.
It is not a user-facing offer: it is the writer-side discipline that decides
whether another internal pass is needed. Only one user-facing offer survives —
see "The single surviving offer" at the end.

## Contents

1. Why the loop exists (pass-1 under-captures)
2. The three axes
3. Source-axis signals
4. Downstream-use-axis signals
5. Measurability-axis signals
6. The reconstruction test
7. Scale guidance
8. The single surviving offer

---

## 1. Why the loop exists

Pass 1 systematically under-captures 30–50% of the most valuable content. Seven
documented sessions replicated the pattern: pass-1 passes the surface coverage
signals, then a re-read adds 30–50% more entries covering
author-interpretation, condition-qualified principles, and framing-shift content
that is easy to compress into a DECISION's rationale at pass-1. Treat pass-1 as
first-draft, never final output. The loop is the mitigation: keep re-reading and
adding until the signals below are clean (or a 3-pass cap is reached).

## 2. The three axes

- **Source axis** — did we capture what the document/session says?
- **Downstream-use axis** — did we capture what the downstream use will actually
  ask of the journal?
- **Measurability axis** — is each principle stated in a form the downstream use
  could operationalize, or merely conceptually?

The three are distinct, each with its own failure mode. Measurability is the one
most likely to trip on implementation-target sessions that pass the other two.

## 3. Source-axis signals

Trigger another pass (or flag, if at the cap) when:

- **Zero ANTI_PATTERN entries** in a reference-ingestion session with ten or more
  `origin: reading` entries. Almost always a capture gap against a source that
  names traps.
- **At least one of the eight reference-ingestion categories has no
  representative entry.** Deterministic and mechanical to detect.
- **Universal quantifier in the trigger phrase** ("everything," "all," "complete
  cover," "full," "entire") AND no section-by-section source traversal was
  performed. Walk the source section by section and confirm at least one entry
  per substantive section.
- **Entry count below the minimum-yield hint for source size** (see Scale
  guidance).
- **No OBSERVATION or perception entry** for a substantive session.

## 4. Downstream-use-axis signals

When a downstream use was declared, check the use axis, not only the source axis:

- *Implementation target declared AND fewer than 3 DECISION entries.* Sessions
  with a named implementation target should anchor each target-specific
  commitment as a DECISION. This signal drives most gaps once the source axis is
  clean (168 entries recovered across six sessions in the v2 test).
- *Teaching target declared AND no comparative-distinction entries.* The seminar
  retrieves on head-to-head positions.
- *Teaching target declared AND fewer than two citation-anchor entries* with full
  publisher/edition/locus specificity.
- *Teaching target declared AND zero pedagogical-scaffold entries AND zero
  pedagogical-commitment DECISIONs.* Descriptive coverage of a debate without
  anchoring what the teacher commits to has captured what the debate is but not
  what the seminar does with it.
- *Cross-project lens declared AND zero CONNECTION entries* spanning the named
  projects.
- *Competitive positioning declared AND zero entries naming differentiators or
  gaps.*

## 5. Measurability-axis signals

When a declared use has an operational layer (code to write, seminar decisions,
metrics to compare):

- *Principles captured in conceptual form only.* "Separability-vs-coherence is
  the underlying principle" is conceptual; "wrap each fragment in explicit
  envelopes, never concatenate with coherent prose between them" is operational.
  Overwhelmingly conceptual entries on an implementation-target session fail.
- *Author-interpretations compressed into DECISION rationales.* When
  author-interpretation content appears only inside a DECISION's rationale rather
  than as its own OBSERVATION/ANTI_PATTERN entry, the pattern won't cluster as a
  distinct anchor. Test: for each substantive interpretation, is there a
  dedicated entry with the interpretation as headline content?
- *Load-bearing sections of a session deliverable not individually entried.* If
  the session produced a multi-section analysis, does the journal have one entry
  per load-bearing framing-shift it surfaced?

## 6. The reconstruction test

For each candidate entry, ask: *would a future Claude instance benefit from
knowing this specifically, rather than reconstructing it from generic training?*
Apply this **at drafting time**, not only at review — if the answer is "no,
generic training covers this," do not draft the entry.

- **Journal it:** context-dependent facts, specific numeric thresholds,
  post-cutoff regulation, named results with specific arguments. (Res. CMN 4.966
  effective 2026-01-01; Qdrant HNSW default m=16; a specific critic's specific
  argument.)
- **Skip it:** textbook results training already has. (Black–Scholes formula;
  CAPM derivation; the HNSW algorithm itself; Python list-comprehension syntax;
  Pydantic's basic `BaseModel` pattern.)

The test is not "is the topic important" (Black–Scholes is important). It is
"would storing this make a future instance measurably better than one without
it." For widely-taught frameworks, concentrate depth on the non-reconstructible
layer (reception, post-X developments, specific critics) and compress the parts
training covers thickly.

## 7. Scale guidance

Size the journal to the session's knowledge density, not to a number.

- **Quick consultation:** 0–2 entries (often skip).
- **Focused work:** 3–6.
- **Research session:** 6–10.
- **Architecture discussion:** 8–14.
- **Multi-topic sprint:** 10–20 (25–35 for long substantive sessions is not
  padding if each entry stands alone).
- **Reference-ingestion:** scales with source size. A short paper/chapter →
  8–15; a multi-hundred-page standard or textbook → 40–80. Below ~30 on a large
  source almost always means categories 1, 2, 4, or 5 were under-captured. Above
  ~100 usually means category boundaries dissolved into near-duplicates.

No hard cap. Multi-arc sessions split by arc, with arc-specific `session:` names.
For runs over ~40 entries, produce in 2–3 internal passes saving after each arc
to avoid quality drift. Across all scales, aim for at least one process or
perception entry — underjournaling perceptions is the systematic blind spot.

## 8. The single surviving offer

When all signals are clean after the internal loop, **do not offer a second
pass.** State the entry count and layer breakdown and stop. The only surviving
user-facing offer: if a downstream use was *declared* AND it remains thin after
the 3-pass cap, surface one targeted offer naming the specific axis and
categories a further pass would target. Keep it answerable in one word.

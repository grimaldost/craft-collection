# Reference-Ingestion Mode

Use this mode when the session converted an authoritative source (standard,
textbook, regulation, research paper, methodology document, framework
documentation, teaching material) into structured entries. Origins are mostly
`reading`. Use this taxonomy *instead of* the implementation-mode
Conclusions/Process/Perceptions framework.

## Contents

1. Signals that the session is reference-ingestion
2. Detect the downstream use-case before capturing
3. The eight-category taxonomy
4. Also aim for perceptions and process entries

---

## 1. Signals that the session is reference-ingestion

- A document was read end-to-end.
- A reference artifact was produced during the session.
- The trigger phrase uses a universal quantifier ("everything," "all knowledge,"
  "complete cover," "create registries for everything").
- Most resulting entries would have `origin: reading` — the most reliable
  dispatch. If that is true, default to reference-ingestion mode.

## 2. Detect the downstream use-case before capturing

Reference-ingestion sessions have **three coverage axes**, not one. **Source
coverage** — did we capture what the document says? — is the obvious axis and the
eight-category taxonomy below is built for it. **Use coverage** — did we capture
what the downstream retrieval will actually ask of the journal? — is the second.
**Measurability coverage** — is each principle stated in a form the downstream use
could operationalize, or merely in conceptual form? — is the third, and the one
most likely to trip on implementation-target sessions that otherwise look
complete. Most capture gaps live on the second and third axes, not the first.

Before capturing, scan the session for a declared downstream use:

- **Implementation target** — the knowledge will guide building, configuring, or
  operating a specific project. Signals: a named project, workload parameters, a
  deployment target, a "for X's persistence layer" lens. → Requires DECISION
  entries anchoring each target-specific commitment (which config, which API,
  which thresholds), plus CONNECTION entries mapping source mechanics to target
  workflows.
- **Teaching / lesson-planning target** — the knowledge will be taught. Signals:
  a named audience, a course, a curriculum, "for lesson planning," "for
  students." → Requires comparative-distinction entries (head-to-head
  positions), full citation anchors (publisher, edition, page/paragraph),
  pedagogical-scaffold entries, and DECISION entries anchoring pedagogical
  commitments (which reading gets assigned, which debate frames a seminar).
- **Cross-project lens** — the knowledge will be reused across several projects.
  Signals: multiple project names with "and." → Requires CONNECTION entries
  spanning the named projects.
- **Competitive / positioning lens** — the knowledge will position one system
  against others. Signals: "against the competitive landscape," "for
  positioning." → Requires differentiator entries (what the positioned system
  does that peers do not) and gap entries (what peers do that it does not), with
  honesty-about-unknowns applied symmetrically.

If no downstream use is declared, proceed with source coverage as the only axis,
but surface the no-use state at the end and offer retroactive declaration (with
the null option foregrounded — some sessions are genuinely general-understanding
work).

A session can declare *both* a mode shape and a downstream use.
Implementation-targeted reference-ingestion is the canonical example.

## 3. The eight-category taxonomy

Work through these in order. Each produces one or more entries. Skip any a source
does not cover, but check every category against the source before deciding —
under-capture almost always means a category went unchecked. The categories
overlap at the margins; a single entry may belong to several. That is fine.

### 1. Distinctions the source draws that sound similar in natural language

What terms does the source treat as distinct that natural language conflates?
Each non-trivial distinction is its own FINDING entry. Two shapes:

**Intra-source distinctions** — pairs the source itself formally separates.
Dominates on standards, regulations, framework docs, mature-library APIs.
*Examples:* FVOCI-debt vs. FVOCI-equity; EIR vs. credit-adjusted EIR; retrieval
vs. generation in RAG; dense vs. sparse retrieval; `upsert` vs. `add`+`update` in
Qdrant; HNSW's `m` vs. `ef_construct`; aerobic vs. anaerobic base-building.

**Cross-source comparative distinctions** — positions in a debate. A well-formed
entry names four elements: which proponents take which positions, the specific
positions, the evidence each adduces, and the conditions under which each claim
applies. Smoothing any into consensus defeats the purpose. Dominates on
interpretive humanities, competitive system landscapes, methodological schools.
*Examples:* Brenner vs. Wood vs. Postone on capitalism's origins; Seiler's
polarized vs. Friel's pyramidal training; Mem0's flat facts vs. Letta's
episodic/semantic/procedural partition; DSPy's compile-time optimization vs.
LangChain's runtime composition.

**Teaching target check.** When teaching is declared, comparative distinctions
are load-bearing — the seminar retrieves on head-to-head positions.

### 2. Specific values, thresholds, and constants

Every number the source hard-codes as a decision boundary, default, or reference
parameter deserves its own FINDING entry. Code branches on these; training
generally does not preserve them. *Examples:* 30 days past due for SICR; 90 days
for default; Basel IV output floor at 72.5%; Qdrant HNSW defaults (m=16,
ef_construct=128); cluster size cap of 15; Zone 2 at 60–70% HRmax.

### 3. Implementation mechanics the LLM would otherwise hallucinate

Specific formulas, decomposition schemes, algorithmic recipes, procedural
machinery that diverge from the naive implementation. Each a FINDING entry.
*Examples:* PD × LGD × EAD with the EIR-vs-credit-adjusted-EIR discounting rule;
SA-CCR EAD = 1.4 × (RC + PFE); RRF fusion formula (`score = Σ 1/(k + rank)`);
NSGA-II non-dominated sort; pytest fixture resolution order.

### 4. Canonical traps explicitly named or implied by the source

ANTI_PATTERN entries (four-question template). **Actively search for these — the
source usually names them, and they are the most valuable category.** If a
reference-ingestion session produces zero ANTI_PATTERN entries, re-read the
source looking for "shall not," "does not apply," "prohibited," "common error,"
"trap," "incorrect," "misapplication," or equivalents. *Examples:* applying EIR
to gross carrying amount in Stage 3; using localStorage in Claude artifacts;
mutable default arguments in Python; presentist fallacy in historical
interpretation.

### 5. Context-dependent facts that training can't reconstruct

Jurisdiction-, version-, release-, or locality-specific content. Each a FINDING
entry with the specific context in the first sentence so the embedder anchors on
it. *Examples:* Brazilian federal-debt pricing conventions (LTN, NTN-F, LFT,
NTN-B); Res. CMN 4.966 effective date; Qdrant v1.x API shape; `uv` command syntax
vs pip; Brazilian school curriculum specifics.

### 6. Sanity checks and identity relationships

Things that must be equal, whose ratio is bounded, whose sign is determined —
invariants that catch implementation errors. Each a FINDING entry stating the
identity and what it catches. *Examples:* put-call parity; CIP for FX forwards;
normalized embedding ‖v‖ = 1 for cosine similarity; F1 = 2PR/(P+R);
`__eq__` consistency with `__hash__`.

### 7. Composition and integration across concepts

How pieces combine — the value of the composition a generic LLM would miss by
composing naively. CONNECTION entries. Universal across domains. *Examples:* XVA
composition (CVA + DVA + FVA + KVA + MVA with wrong-way risk); BM25 + dense + RRF
fusion as a single search primitive; a raw-capture → synthesized-pattern →
reinforced-rule promotion chain in a memory store; how `uv` + `ruff` + `ty` +
`pytest` compose as a quality pipeline.

### 8. Named results, canonical references, and lookup anchors

Specific named objects a future session might retrieve by name. Each a FINDING
entry centered on one named object — the lookup-anchor layer that makes the rest
navigable. *Examples:* Jamshidian's decomposition; Fang–Oosterlee COS method;
HNSW (Malkov 2016); RRF (Cormack 2009); GEPA (2024); Braudel's longue durée;
Hobsbawm's "long 19th century."

## 4. Also aim for perceptions and process entries

The source-reading arc has its own process dynamics — which parts the user wanted
re-read, which topics they flagged as relevant, how they intend to use the
resulting registries. One or two OBSERVATION entries per reference-ingestion
session is the right order of magnitude.

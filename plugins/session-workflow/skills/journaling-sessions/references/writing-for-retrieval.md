# Writing for Retrieval

How to phrase entry prose so it clusters and retrieves well in any vector store.
An embedder sees only the CONTENT field as text — not the type, not the domains,
not the confidence. Every signal that should matter for clustering, similarity,
and synthesis must be encoded in the prose itself. Entries that read fine to a
human but embed poorly get lost in the pipeline. (Concrete examples below use
MiniLM/BM25, but the principles hold for any sentence-transformer + keyword
store.)

## Contents

1. Core writing discipline
2. Embedding-aware phrasing
3. Never invent project-specific details

---

## 1. Core writing discipline

**Be concrete.** "Connection pooling is faster" teaches nothing. "Connection
pooling cut p99 latency from 800ms to 120ms under 200 concurrent requests by
eliminating per-request TCP+TLS setup" teaches everything.

**Include reasoning inline.** The decision itself is less valuable than the WHY,
and it should co-occur in the same embedding. "Connection pooling enabled by
default because it cut p99 latency 6x under load" is one embedding. "Connection
pooling enabled by default. Rationale: latency." is the same information but
weaker — rationale appears as a throwaway second sentence.

**Perceptions are first-class.** "The user pushed back on the domain tag list
being hardcoded — they want this domain-agnostic, applicable to any area of life"
is as valuable as any technical finding. Don't relegate perceptions to
afterthoughts.

**One idea per entry.** Split compound entries so each can cluster independently.
A decision about connection pooling and an observation about the user's priorities
are two entries, not one. When an entry wants to be longer than 300 words, it's
usually two entries in disguise.

**Length sweet spot: 80–300 words per entry.** Shorter entries produce sparse
embeddings that cluster unreliably. Longer entries dilute semantic density.

## 2. Embedding-aware phrasing

**Front-load the distinctive concept.** Sentence-transformers weight early tokens
more heavily. Put the most uniquely identifying content in the first sentence.
- Bad: "After reviewing several options in a focused session, we landed on Qdrant
  as the backend."
- Good: "Qdrant selected as the persistence backend for in-traversal filtering
  and Apache 2.0 licensing — the deciding factors after a 9-candidate evaluation."

**Use specific names, not pronouns or roles.** "Alex" anchors better than
"the user." "MiniLM" beats "the embedder we have now." Proper nouns and IDs also
give keyword search strong hits that dense vectors may miss.

**Use discriminative technical terms over generic ones.** "In-traversal
filtering" beats "efficient filtered search." "Scalar INT8 quantization" beats
"vector compression." The precise term occupies a more unique direction in vector
space.

**Vary lead sentences across entries.** If five entries start with "The user
pushed back on..." they cluster by that phrase rather than by their distinctive
content. Recast openings to lead with the actual subject matter.

**Keep each entry self-contained.** It will be retrieved and reasoned about in
isolation. Don't write "as discussed earlier." Restate the relevant context
compactly. Assume the reader is a future instance six months from now who has
never seen this session.

**Put specific values and thresholds in the first sentence and the summary.**
"30 days past due triggers SICR under IFRS 9" beats "SICR has a rebuttable
presumption" that mentions the number only in passing.

**Prefer prose over bullet lists.** Lists fragment ideas into tokens the embedder
treats separately. A coherent paragraph produces a tighter vector. Use lists only
when the content is genuinely enumerative.

**Name what it isn't, when useful.** Contrasts sharpen the vector. "Qdrant, not
LanceDB" encodes a comparison in one phrase. "A single MemoryStore protocol, not
a three-tier hierarchy" encodes a rejected alternative inline.

**Use substrate similarity, not surface similarity, for analogies.** "ArXiv ML
surveys are the reference class because both are fast-moving, noisy, not-
peer-reviewed material" beats "both are written documents." Substrate framing
clusters with future entries making analogies at the same depth.

**Condition-qualify principles rather than stating them unconditionally.**
"Principle X holds under conditions C" beats "Principle X, usually." "Equal
weights appropriate until ≥200 labeled examples per Dawes 1979" beats "Equal
weights are the default."

**Flag tensions between sources explicitly rather than smoothing them.** When two
sources reach different conclusions under different scopes, name the tension and
give the scope-differentiated resolution. A clean unified claim that papers over
disagreement is a specific failure mode — a reader holding only one source reaches
a conclusion incompatible with a reader holding the other.

**Avoid marketing-tone adjectives.** "Elegant," "powerful," "robust," "seamless,"
"revolutionary" are low-information words with high training-data density. They
push entries toward a generic "recommendation" cluster. Replace with concrete
attributes.

## 3. Never invent project-specific details

When an entry names a project, system, or codebase you do not have concrete
knowledge about (from user memories, conversation history, or pasted specs), do
not write plausible-sounding specifics. Verify project details in context first.
If no concrete information is available, in order of preference: (a) ask the user
for the spec, (b) write the entry generically with an explicit flag that the
project-specific claims require verification, or (c) decline and flag the gap as
an OBSERVATION noting what a future session would need. The failure mode being
prevented is "plausible-sounding guessed project specifics that enter the store
looking grounded when they are grounded in nothing" — a silent pollution pathway,
expensive because hallucinated entries propagate and appear in future retrieval
as false anchors.

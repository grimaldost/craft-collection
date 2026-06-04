# Cognitive-Memory (mantis) Adapter

**Load this only when journaling for mantis / cognitive-memory.** For any other
use, the generic core plus `output-format.md` is sufficient — this file adds the
system context, extra fields, and promotion semantics that only matter when
entries feed the cogmem ingestion pipeline.

## Contents

1. The three layers and why the quality bar is what it is
2. Extra fields cogmem adds
3. Author identity and multi-user privacy
4. Confidence as promotion input
5. The VALIDATED marker
6. The embedder is the gatekeeper

---

## 1. The three layers and why the quality bar is what it is

Every journal entry lands in cognitive-memory as an **experience** that
meditation will cluster against future sessions. The quality test is not "does
this capture the session" but "will meditation cluster this usefully against
entries from sessions yet to come." A good entry anchors on content future
sessions may also produce — a specific pattern, a named failure mode, a concrete
distinction — in phrasing that will match across authors, models, and contexts.

Cognitive-memory organizes knowledge into three layers of the same kind of
object — prose with metadata — playing different roles. **Experiences** are the
raw captures this journal produces: dense in specifics, naming real people,
decisions, dates. **Hypotheses** are synthesized by meditation when a cluster of
experiences share an underlying pattern; they articulate a generalization rather
than describing a specific event. **Wisdom** is what hypotheses become after
enough reinforcement cycles confirm them, eventually injected into future LLM
sessions.

Meditation cannot synthesize good hypotheses from bad experiences. It clusters by
semantic similarity of content, reads a cluster through an LLM, and asks that LLM
to articulate the pattern. Concrete, specific, well-written experiences produce
reflective hypotheses; vague or formulaic experiences produce worse-than-mediocre
ones because the LLM cannot extract meaning that is not there. Everything the
core skill teaches about embedding-aware writing exists to give meditation good
inputs.

## 2. Extra fields cogmem adds

Beyond the lean generic set in `output-format.md`, cogmem entries carry:

```
visibility: private | team:<n> | public
language: <ISO 639-1 code — en, pt, etc. Default from author preference.>
```

And the `origin` field extends to include `meditation` — **reserved** for entries
synthesized by cogmem itself; it should never appear in a journal entry, since
those are produced by meditation directly. Journal origins are `chat`, `code`,
`meeting`, `reading`.

`visibility` determines how broadly an entry can be retrieved. `private` (the
default) means only the author can retrieve it. `team:<n>` means a named team can.
`public` means any cogmem user can. Most entries should be private; elevate only
when the knowledge is genuinely general.

## 3. Author identity and multi-user privacy

cogmem is a multi-user system; retrieval filters by `author` so User A's sessions
do not pollute User B's queries and privacy boundaries hold. A missing `author:`
is a bug, not an optional omission. The author is *whose memory this is*, not
*who is discussed*. When the content discusses people or entities that could
collide with other names in cogmem, disambiguate inline ("Claire — Stone treasury
team, not the neighbor") rather than relying on the embedder.

## 4. Confidence as promotion input

The confidence-calibration table in `output-format.md` applies. cogmem adds
promotion-specific rules, because downstream filters, promotion gates, and
synthesis weighting depend on confidence being consistent across writers:

- **HYPOTHESIS entries cap at 0.69 by default.** If they're provable, they're
  FINDINGs — and promotion treats FINDINGs and HYPOTHESES differently.
- **Survived-questioning bonus is +0.1.** A DECISION that passed genuine
  stress-testing earns a one-tier bump AND includes a VALIDATED marker (below).
- The promotion gate reads confidence + reinforcement count, so a miscalibrated
  score doesn't just mislead a reader — it changes whether an experience is ever
  promoted to wisdom.

## 5. The VALIDATED marker

When a DECISION survived explicit questioning, that fact must be encoded in the
CONTENT field itself — not only in the confidence number — because meditation
clusters on CONTENT. Required sentence at the end of CONTENT:

```
VALIDATED: survived questioning on [brief topic] — key challenges considered:
[1-2 sentence summary of what was challenged and how it held up].
```

Example closing: *"VALIDATED: survived questioning on whether local mode matches
production semantics — the HNSW-vs-brute-force gap was raised and dismissed
because dev tests use >50K vectors, which triggers HNSW in both modes."*

**Who applies it:**
- A questioning/critique pass emits this marker for decisions it tested; preserve
  it verbatim when incorporating such drafts.
- The writer applies VALIDATED when a DECISION was stress-tested during the
  session itself, whether or not a formal questioning mode was active. In-turn
  pressure-testing counts if the challenge was substantive: specific alternatives
  considered, specific concerns raised, specific resolutions given.
- **Never invent VALIDATED** for decisions merely discussed, even at length. The
  test: can you name the specific challenge(s) considered? If yes, VALIDATED. If
  "we thought it through carefully," not VALIDATED.

This distinguishes a 0.85 DECISION that survived scrutiny from a 0.85 DECISION
that merely felt confident — but only if the marker is actually present.

## 6. The embedder is the gatekeeper

The embedder sees only CONTENT as text — not type, domains, or confidence. cogmem
currently calibrates against MiniLM (max similarity ~0.567 on seed wisdom); the
practical consequence is that every signal that should matter for clustering must
live in the prose. The full prose discipline is in `writing-for-retrieval.md`;
this is the reason it is not optional for cogmem.

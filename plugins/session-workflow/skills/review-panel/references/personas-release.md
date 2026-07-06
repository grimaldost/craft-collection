# Persona pack — release readiness

Fires on the *assembled* release artifact (diff + changelog + docs + public
surface), after per-change review is done — fresh eyes on the assembly see
what per-wave review structurally cannot (production-validated: four lenses,
all four verdicts changed what shipped).

- **Consumer-upgrade path** — someone on the previous version upgrades today.
  What behavior changes hit them unannounced? Is every *behavior* change (not
  just API change) in the changelog? Do the pinned examples and upgrade notes
  still run as written?
- **Docs coherence** — read the docs as the only truth. Does the README, a
  guide, or an agent-facing doc assert anything the shipped tree contradicts?
  Which claims went stale during this release's waves?
- **Changelog integrity** — is the changelog structurally sound (one section
  per change type, breaking changes rendered where a skimmer sees them first)
  and complete against the actual diff? What landed without an entry?
- **Cross-change interactions** — the changes were reviewed one by one; where
  do two independently-fine changes meet (same file, same contract, same
  consumer) and produce a defect or a documentation contradiction?

Verdicts: READY / READY-WITH-CONDITIONS / NOT-READY. Collate all conditions
into one ruled work list for a single fix pass — no interpretation step
between panel output and action.

Hammer: what would make a consumer roll back within a day; the claim nobody
re-read after the last wave landed; the entry the changelog is missing.

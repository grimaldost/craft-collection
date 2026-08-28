# feedback-triage mechanics — folded detail

Edge-case mechanics behind the SKILL.md pipeline. The body carries the rules;
this file carries the why and the rare-path detail.

## Triage-doc detection — why H1-only, never the filename

A doc counts as a triage doc (a loop OUTPUT, excluded from inputs) only if its
first heading starts with `# Triage` — the same rule `build_feedback_index.py`
applies. A filename test misclassifies in both directions:

- legitimate INPUT reports whose slug mentions triage: a tool-feedback report
  *about* the `feedback-triage` tool itself, or a `<date>-triage-round-<tool>`
  wave slug — both open with a `# <tool> feedback` H1 and must be indexed
  (observed: 7 `triage-round-*` reports plus `2026-06-14-feedback-triage-batch-run.md`
  silently dropped by the old filename filter);
- house variants that ARE triage docs without the standard slug: keel's
  `<date>-backlog-triage.md` still counts because its H1 opens `# Triage —`.

## Later passes — the delta form

A pass over a corpus that already has a baseline triage doc emits a NEW doc,
never an edit of the baseline — two sessions editing one status table clobber
each other, and an edited baseline erases the audit trail. The delta doc:

- lists only the new reports under **Inputs**;
- states that it supersedes the prior promotion table as the status of record;
- carries a consolidated current-backlog table — every open row, its current
  status, and which pass set it;
- continues the baseline's cluster-ID namespace (a baseline ending at T4 makes
  the next new cluster T5), so statuses track across passes.

One new report over a baseline is a valid delta pass — statuses move and watch
rows get their corroboration. "Nothing to cluster" prohibits only a corpus of
one with no baseline.

## Why step 2 checks the checkout, and step 5 checks the row set

Both are readings a pass used to perform from memory and got wrong.

**A stale checkout.** Three passes in one month reconciled against trees 4, 29
and 2 commits behind their remotes. The 29-commit one was a full release behind
with a remote-tracking ref 16 days stale, so even `git log origin/main` lied
until a fetch; the 4-commit one sat at 0.2.0 while the field-exercised version
was 0.3.0, and it was caught only because a report named a version the manifest
did not have. Every shipped-or-absent verdict taken against such a tree is wrong
in the same direction, and the doc that results becomes the status of record for
passes that follow.

**An unbuilt promoted row reads as an absent home.** Grounding against source
answers "is the mechanism there?" and cannot answer "was this already decided?"
A pass verified — correctly — that a skill had no environment-traps section and
DECLINED three findings for want of a home, when that note had been a promoted
row for five weeks and a prior baseline had already re-verified it absent. The
same corpus had a whole document's rows never carried into the next doc at all.
The row set is the only thing that answers the second question, so it is read,
not recalled.

## Concurrent sessions on one corpus

If another session may be triaging the same corpus: at scope, note any triage
doc already dated today; at emit, re-list the dir — if a triage doc covering the
same corpus appeared since scope, reconcile with it (fold or extend) instead of
emitting a competing duplicate. Two same-day triage docs over one corpus split
the status ledger and both go stale.

## Fan-out digest subagents — the owner taxonomy

When a multi-tool corpus is digested by per-tool subagents, the brief's owner
taxonomy must enumerate **each registered tool's own skills/components**, not
just describe the tools. A finding about tool X's own skill is otherwise
misrouted to whichever tool the brief described in most detail (observed: a
pr-pilot skill finding mistagged as craft-collection's because the brief
detailed craft and only named pr-pilot).

## A corpus split across several passes in one round

A large backlog is sometimes triaged by scope rather than all at once — a
cross-cutting pass first, then one pass per component. The delta form above
assumes one pass per baseline and misfires here in two ways.

**The consolidated backlog belongs to the LAST pass of the round.** If every
partial pass carries "every open row, its current status, and which pass set it",
the round ends with three competing status ledgers over one backlog — the
orphaning failure the consolidated table exists to prevent, in a new form. An
earlier partial pass reconciles only the rows it touches and says so; it names
the pass that owes the consolidation.

**A forwarded report stays un-triaged.** `## Inputs` doubles as the pass's input
list and as its coverage claim, and those separate the moment a pass forwards.
The coverage parser credits every known stem named anywhere in that section,
prose included, so naming a report there closes it — and a report closed by a
pass that did not disposition its findings vanishes from the next pass's input
list. Name only what the pass closes; a report with any forwarded finding is
named under a different heading and reappears as un-triaged, which is correct
even though it means the later pass re-reads a report this one partly used.
Prefer that overlap: it costs a re-read, where the alternative costs a finding.

**Observed.** A cross-cutting pass over 6 of 29 reports named two
un-dispositioned reports inside `## Inputs` while explaining why they were out of
scope. Both were credited as covered and left `### Untriaged`. The step-7 rebuild
caught it — the just-triaged check reads the same list from the other direction.

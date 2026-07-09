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

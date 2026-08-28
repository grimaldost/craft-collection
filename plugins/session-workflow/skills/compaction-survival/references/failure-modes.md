# Anchor failure modes — what each one costs

A lookup table, not a rule: read it when an anchor is not paying for itself, or
when reviewing one someone else wrote. The rules that prevent these live in the
SKILL.md protocol.

| Pattern | What it costs |
|---------|---------------|
| Anchor created, then never updated | Resume reads a stale cursor; work is redone or skipped. |
| State kept only in context | The compaction the anchor exists to survive erases it. |
| Re-read skipped on resume | Acts on the summary's gaps; relitigates settled decisions. |
| Anchor grown into a transcript | Becomes the token hog it was meant to prevent. |
| Non-idempotent resume | Re-runs a finished irreversible step, or stacks a second attempt on a half-done one. |
| Closed in prose, never renamed | Injection de-ranks it and offers the rename, but strays accumulate until renamed — sweep at wind-down. |
| Mission paraphrased, order lost | A user instruction that fixed a mechanism survives compaction as a summary; the substitution then reads as a design choice and no gate can point at the original. |
| Reversal quoted without naming what it replaces | The superseded rule also lives in persistent memory and in older anchor text, so the reversal does not overwrite it - it joins it. Two live orders, and the stale one looks corroborated by every other copy. |
| Operationally-critical sections written last | The injection spends its budget top-down; whatever sits at the end is what a cut takes. A real anchor was cut inside "Resume steps" while the mission prose above it survived intact. Position is priority - the fix is the order, not the size. Two anchors past 1,100 lines recovered cleanly because the truncation note says to open the file. |
| Resume steps written in relative paths | They run in an environment the resume did not set up. A shell's working directory is not guaranteed across a restart, and a relative command does not fail there - it succeeds somewhere else. One certification artefact was written into the wrong repository this way, and recovered only by a `mv` that should not have been needed. |
| Peer track sharing the tree, undeclared | Two autonomous sessions, one HEAD: a peer's commit lands on your branch by fast-forward. Disclosure on every commit that touches shared surface is what makes it benign; the anchors are per-track, so a lesson learned by one reaches the other only if it is routed into both. |
| Track abandoned mid-cursor | Not marked done in content, so the closed-but-unrenamed sweep cannot see it. It keeps asserting a cursor the durable state contradicts - one read `Phase 1 IN PROGRESS` for four days after that phase was committed. Read `--list-dormant` when arming the next anchor, which is the one moment a human is reliably present. |
| Closed on the deliverable, not on the session | Closing is correct; stopping there is not. One session closed a read-only review track and then ran 2h20 of file-creating work with no anchor at all. |

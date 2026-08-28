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

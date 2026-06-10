# forge feedback corpus (synthetic) — docs/feedback/ of tools/forge, read in full

## File: 2026-05-20-wave-5.md
- Tool/version: forge 0.6.0
- Misses: [HIGH] Spec §3 said "model the loader on tests/helpers/loader_ref.py" —
  that file does not exist; executor improvised. phase: gate.
- Proposed promotions:
  1. [HIGH] check-ready should resolve "model-on" file pointers to real paths.

## File: 2026-05-26-wave-6.md
- Tool/version: forge 0.6.1
- Friction: [MED] `forge report` output has no machine-readable form; we parse the
  table with regex in CI.
- Misses: [HIGH] Spec cited "the proven dedupe helper" — the helper exists but
  silently skips records with missing keys, which is exactly what wave 6's data
  has; the gate never checked the referent against our shapes. phase: gate.
- Proposed promotions:
  1. [MED] Add `--json` to `forge report`.
  2. [HIGH] extends 2026-05-20-wave-5#1 — referent grounding must also cover
     "reuse the proven helper" claims, not just file pointers.

## File: 2026-06-01-wave-7.md
- Tool/version: forge 0.6.1
- Misses: [HIGH] Spec asserted "mirrors the wave-4 precedent" — wave 4 never
  actually adopted that pattern (counterfactual precedent); caught in review.
  phase: gate.
- Friction: [LOW] Banner prints even with `--quiet`.
- Proposed promotions:
  1. [HIGH] Verify claimed precedents against the actual prior artifact.

## File: 2026-06-05-wave-8.md
- Tool/version: forge 0.7.0
- Friction: [HIGH] forge's run wrapper killed a 25-minute relay engine run at its
  default 15-minute timeout; the timeout belongs to the engine, not the spec gate.
- Proposed promotions:
  1. [HIGH] Stop wrapping engine execution; or surface the engine's own timeout.

## File: 2026-06-08-wave-9.md
- Tool/version: forge 0.7.2
- Misses: [HIGH] check-ready PASSED a spec whose §4 named a fixture that does
  not exist (tests/fixtures/empty_ledger.json); executor 404'd an hour in.
  phase: gate. [BLOCKER] `forge fix --apply` truncated the spec file to zero
  bytes when the disk hit quota mid-write — destructive, unrecoverable without
  git. phase: gate (write should be atomic: temp file + rename).
- Proposed promotions:
  1. [HIGH] check-ready must FAIL on unresolvable file references in any
     spec section, not just anchors.
  2. [BLOCKER] Make `forge fix --apply` writes atomic (temp file + rename);
     never truncate the target on a failed write.

## File: tools/forge CHANGELOG.md (excerpt)
## 0.7.0 — 2026-06-03
- Added `--json` to `forge report` (machine-readable output).
## 0.6.1 — 2026-05-24
- Anchor checks (path:line) now resolve against the working tree.

## Registered tools (from the user's CLAUDE.md)

| tool | repo | feedback dir | extras |
|------|------|--------------|--------|
| forge | tools/forge | docs/feedback | — |
| relay | tools/relay | docs/feedback | engine/execution concerns belong here |

# Holdout baselines — seal-with-baseline records

One row per sanctioned holdout run, recorded next to the seals (the N29a rule:
a holdout is sealed **with** a baseline number, and re-baselined after any
`description` edit so a later tuning round has a same-surface reference).
Running the holdout for a baseline is the single sanctioned read of a sealed
set; tuning against it spends it (see the 2026-06-10 spent-holdout precedent).

| skill | run date | description measured | recall (CI) | specificity (CI) | set | repeats | error runs | cost | notes |
|---|---|---|---|---|---|---|---|---|---|
| compaction-survival | 2026-07-06 | session-workflow 0.12.0 @ 7ac448c (includes the #84 /anchor + cold-start sentence) | 1.00 [0.76, 1.00] | 1.00 [0.70, 1.00] | 4+ / 3− | 3 | 13/21, 1 no-activation (fired-then-errored counts as activation, per the N28a rule) | $2.37 list-equiv | First baseline — the holdout was sealed pre-N29a with no birth number, so this run creates the reference the #84 reseal note required. Dev set has never run (`report/triggers.json` has no entry); the dev-vs-holdout overfit comparison is n/a until it does. |

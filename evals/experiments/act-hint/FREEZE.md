# Freezing the act-hint detector (the two-stage choreography)

Everything below is mechanical. The judgement calls were made while the materials were
authored; this file is the button-pressing, and it follows the same four steps as the
worked precedent at
`plugins/experiment-discipline/skills/experiment-rigor/examples/rg-2x2/FREEZE.md`.

Run from the repo root; `$DIR` is relative to it.

    DIR=evals/experiments/act-hint

## State before stage 1

The record is authored, `report.md` is rendered from it, and **every material SHA is
already filled** — `freeze_fill.py` was run once without `--freeze-sha`. That order is
not optional: `outcomes[].verifier.hash` sits inside `ER-PREREG`'s frozen subset, so a
placeholder committed at stage 1 and filled at stage 2 would read as drift from the
frozen plan. Only `plan_frozen_at` is outstanding, and only because a commit cannot name
its own SHA.

**If a material changes before stage 1** — a bank prompt reworded, an oracle pattern
fixed, `firing_table.py` regenerated — reset that material's `sha256` in `record.yaml`
to its `PENDING_...` token (the tokens are listed in `freeze_fill.MATERIALS`) and run
`freeze_fill.py` again; it refills the token with the new hash. Do not hand-edit the
hash to the new value: `freeze_fill.py` treats a *differing* non-token hash as a
post-freeze edit and fails loudly, and that behaviour is the one you want left intact.

Confirm that state before committing anything:

    uv run --no-project --with pyyaml -- python "$DIR/freeze_fill.py" --check
    #   -> "UP TO DATE ..."   (nothing to fill but the freeze coordinates)

    uv run --no-project --with pyyaml -- \
      python plugins/experiment-discipline/skills/experiment-rigor/scripts/validate.py \
      "$DIR/record.yaml"
    #   -> ER-ANCHOR (1 failure), WARN ER-XCHECK, WARN ER-PREREG. Nothing else.

That failure set IS the pre-freeze state. `ER-ANCHOR` fails and `ER-PREREG` warns for one
reason — `plan_frozen_at.commit` is absent — and both clear at stage 2. `ER-XCHECK` is a
declared posture (`source: hand`, with `run.hand_reason` stating why no fathom ledger
backs these rows) and stays a warning afterwards.

## Stage 1 — commit the frozen pre-registration and its materials

The frozen record intentionally fails `ER-ANCHOR`, so the `experiment-rigor-validate`
pre-commit hook is skipped for **this commit only**. That is the freeze bootstrap, not a
defect, and never an addition to the standing skip list — stage 2 restores the gate and
the record must then pass it. Every other hook still runs; the render drift gate passes
because `report.md` was rendered from the record it is committed beside.

    git add "$DIR"
    SKIP=check-merge-conflict,check-added-large-files,check-json,experiment-rigor-validate \
      git commit -m "freeze(act-hint): detector pre-registration and materials (stage 1)"

The `check-merge-conflict,check-added-large-files,check-json` skips are the standing
Windows-Application-Control workaround on this machine; drop them elsewhere. `check-json`
is the one that stings here — a detector's materials **are** JSON (bank, four arm rules,
firing table, oracle patterns, labeled set) — so on this machine the JSON is validated
instead by `test_firing_table.py` and `test_oracle.py`, both of which parse every one of
those files and fail loudly on a malformed one.

## Stage 1b — make the freeze commit durable

A squash-merge can drop the freeze commit from the branch and a rename can move the
record out from under the path `git show` will ask for. Close both here.

    FREEZE_SHA=$(git rev-parse HEAD)
    git tag freeze/act-hint-stage1 "$FREEZE_SHA"

`plan_frozen_at.path` closes the second half and `freeze_fill.py` writes it for you: the
record's repo-relative path **at the freeze commit**, historical and never updated when
the record moves. CI checks out at `fetch-depth: 0` for the same reason; a depth-1 clone
is *expected* to fail the reconstruction, loudly, and no skip may be added to make it
pass.

## Stage 2 — fill the coordinates, then commit the pair with the gates restored

    uv run --no-project --with pyyaml -- \
      python "$DIR/freeze_fill.py" --freeze-sha "$FREEZE_SHA"

It replaces the freeze-fill region with the real `plan_frozen_at` block (commit, path,
and the commit's own committer date — no wall clock), re-verifies every material SHA
against the files on disk, re-renders `report.md`, and re-runs the validator and the
drift gate. Expected tail: `0 failure(s), 1 warning(s), no drift`.

A `FROZEN-MATERIAL MISMATCH` line instead means a material was edited after it was
hashed into the record. That is the integrity check firing, not a hiccup: do not
re-hash. Work out what changed, and if the change is wanted, redo the freeze from
stage 1 with a new commit.

    git add "$DIR/record.yaml" "$DIR/report.md"
    SKIP=check-merge-conflict,check-added-large-files,check-json \
      git commit -m "freeze(act-hint): fill the frozen coordinates (stage 2)"

`experiment-rigor-validate` runs on this commit and must pass.

## Post-commit verification

    # 1. the record passes at measurement tier (ER-XCHECK is a WARN, not a failure)
    uv run --no-project --with pyyaml -- \
      python plugins/experiment-discipline/skills/experiment-rigor/scripts/validate.py \
      "$DIR/record.yaml"
    #   -> "OK (1 warning(s))", exit 0

    # 2. the committed report is in sync with the record
    uv run --no-project --with pyyaml -- \
      python plugins/experiment-discipline/skills/experiment-rigor/scripts/render.py \
      --check "$DIR/record.yaml"
    #   -> "OK .../record.yaml", exit 0

    # 3. the suite is green, including the pre-spend shape gate
    uv run --no-project --with pyyaml -- python scripts/run_tests.py

    # 4. the plan is priced, and the materials re-verified, before a cent moves
    uv run --no-project --with pyyaml -- python "$DIR/run_arms.py" --dry-run
    #   -> "frozen materials verified against record.yaml"
    #      192 runs, $24.96 - $59.52 projected, ceiling $75.00

Only after all four does `run_arms.py` (no `--dry-run`) get to spend anything. It
re-runs the material check itself and exits 2 rather than spawning if any frozen
material has moved, and it halts *before* a spawn whose own cap could take the total
past the ceiling — so the ceiling is never crossed and then noticed.

## What stays, and why

`freeze_fill.py` stays after the freeze: `test_record_shape.py` imports its SHA logic as
the single source of truth for what the record's material block should contain, and §6's
`finalize.py` re-verifies the same hashes before it writes any result. `firing_table.py`
stays for the same reason — `--check` fails when the committed table drifts from what the
real router now produces, which is how a router change becomes visible instead of
silently invalidating a frozen experiment.

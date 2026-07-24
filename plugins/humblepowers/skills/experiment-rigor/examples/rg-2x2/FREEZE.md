# FREEZE choreography for the RG-2x2 dogfood record (delete this file at stage 2)

This record is a real pre-registration freeze. A commit cannot name its own SHA, so
the freeze is a **two-stage handoff**: commit the frozen pre-registration first, then
fill `plan_frozen_at.commit` (and the wave-2 amendment's commit) with that SHA. The
delivered `record.yaml` is the STAGE-1 frozen version — design, outcomes, analysis plan,
threats — with `plan_frozen_at.commit: PENDING` and **no results / posterior / amendment**.
`finalize.py` adds those after the freeze commit exists.

Run these from the repo root. Paths are relative to it.

    DIR=plugins/humblepowers/skills/experiment-rigor/examples/rg-2x2

## Stage 1 — commit the frozen pre-registration

The frozen record intentionally fails `ER-ANCHOR` (its commit is `PENDING`), so the
`experiment-rigor-validate` pre-commit hook must be skipped for THIS commit only — the
freeze bootstrap, not a defect. Every other hook still runs (the render drift gate
passes: the delivered `report.md` matches the frozen record). Pin the commit date so the
freeze provably predates the declared first run (`run.first_run_at: 2026-07-24T12:00:00Z`);
`ER-ANCHOR` compares the git committer date against it.

    git add "$DIR/record.yaml" "$DIR/report.md" "$DIR/finalize.py" "$DIR/FREEZE.md"
    SKIP=check-merge-conflict,check-added-large-files,experiment-rigor-validate \
      GIT_AUTHOR_DATE="2026-07-24T00:00:00Z" GIT_COMMITTER_DATE="2026-07-24T00:00:00Z" \
      git commit -m "freeze(experiment-rigor): RG-2x2 pre-registration (stage 1)"

(The `check-merge-conflict,check-added-large-files` skips are the standing
Windows-Application-Control workaround on this machine; drop them elsewhere. The
`experiment-rigor-validate` skip is the freeze bootstrap.)

## Stage 2 — finalize, then commit the finished pair

Take the freeze SHA and run the finalize step. It is DETERMINISTIC and IDEMPOTENT: it
fills `plan_frozen_at.commit` and the wave-2 amendment's commit with the SHA, adds the
per-arm results (Wilson CIs recomputed by `stats.py`), the amendment, and the
prior -> posterior update; regenerates `report.md`; and re-validates.

    FREEZE_SHA=$(git rev-parse HEAD)
    uv run --no-project --with pyyaml -- \
      python "$DIR/finalize.py" --freeze-sha "$FREEZE_SHA" --record "$DIR/record.yaml"

Expected tail: `finalized ... (1 warning(s), 0 failures, no drift)`. The one warning is
`ER-XCHECK` — `source: hand` at the measurement tier is the honest state (the original
RG-2x2 was hand-orchestrated in fathom PR #15; no ledger travels with it). A WARN does
not fail the gate.

Then delete this note and commit the finalized pair with all hooks running:

    rm "$DIR/FREEZE.md"
    git add "$DIR/record.yaml" "$DIR/report.md"
    git rm "$DIR/FREEZE.md"
    git commit -m "feat(experiment-rigor): finalize the RG-2x2 dogfood record (stage 2)"

`finalize.py` STAYS — `scripts/test_acceptance_rg2x2.py` imports it as the single source
of truth for the finalized content and re-runs the whole freeze -> finalize -> validate
flow against a temp-repo freeze commit.

## Post-commit verification (what to check, and the expected output)

    # 1. The finalized record passes the full gate (ER-XCHECK is a WARN, not a failure):
    uv run --no-project --with pyyaml -- \
      python "$DIR/../../scripts/validate.py" "$DIR/record.yaml"
    #   -> "OK (1 warning(s))", exit 0

    # 2. The committed report.md is in sync with the record (no drift):
    uv run --no-project --with pyyaml -- \
      python "$DIR/../../scripts/render.py" --check "$DIR/record.yaml"
    #   -> "OK .../record.yaml", exit 0

    # 3. The section-5 acceptance suite is green (six-defect map + decision tier):
    uv run --no-project --with pyyaml -- python scripts/run_tests.py

## The two documented decisions this fixture makes

- **`source: hand`.** The original RG-2x2 was hand-orchestrated before this discipline
  existed; reconstructed here as the chain root, so no machine-readable ledger travels
  with it. `ER-XCHECK` is a measurement-tier WARN by design.
- **`amendment.commit == the freeze commit`.** The +4/12 wave-2 confirmation bar for the
  exploratory footprint was fixed after the wave-1 post-hoc signal and before wave-2. In
  this reconstruction the whole pre-registration is frozen at a single commit, so the
  amendment anchors to it; the validator's chronology check confirms the amendment commit
  predates the wave-2 run it governs (`governs_first_run_at: 2026-07-24T18:00:00Z`). A
  live sequential design would carry a distinct between-waves amendment commit — the
  fixture models the discipline's shape, not a live wave cadence.

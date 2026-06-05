# Skill design review — round-4 final panel (9 skills)

Four fresh Opus reviewers (MINIMALIST, AUDITOR, ADVOCATE, DOMAIN-EXPERT), each
scoring all **nine** skills blind to each other and to the behavioral eval, same
rubric as round-1/3. Run after the autonomous build-out (eval fixes, the two new
skills evaluate-skill + consolidate-knowledge). Agent ids: a9fb5a991a194b661 ·
aa972d8d5806ce034 · a5f6d145e5cb868e1 · ad834d9a563c23518.

## Verdict matrix (Worth-it / Design, out of 10)

| Skill | MINIMALIST | AUDITOR | ADVOCATE | DOMAIN-EXPERT | Consensus |
|---|---|---|---|---|---|
| data-engineering-discipline | KEEP 9/8 | KEEP 9/6 | KEEP 9/7 | KEEP 9/8 | **KEEP — ranked #1 by all four** |
| evaluate-skill *(new)* | KEEP 8/8 | KEEP 9/8 | KEEP 8/8 | KEEP 9/8 | **KEEP — unanimous; engine verified** |
| review-panel | KEEP 8/9 | KEEP 8/9 | KEEP 8/9 | KEEP 8/9 | **KEEP — unanimous; best design (9)** |
| journaling-sessions | KEEP 8/7 | KEEP 9/7 | REVISE 7/6 | KEEP 8/7 | KEEP — trim the weight |
| python-engineering | REVISE 6/7 | KEEP 7/6 | KEEP 7/7 | KEEP 8/8 | KEEP — trim the philosophy |
| refresh-stack | KEEP 7/8 | KEEP 7/8 | KEEP 7/8 | KEEP 7/8 | **KEEP — unanimous, exemplary command** |
| context-handoff | KEEP 6/8 | KEEP 7/9 | KEEP 7/9 | KEEP 6/9 | KEEP — thinnest value, top design |
| consolidate-knowledge *(new)* | KEEP 7/8 | REVISE 6/7 | REVISE 6/7 | KEEP 7/8 | KEEP/REVISE split — add a script + example |
| toolkit-awareness | KEEP 7/8 | KEEP 6/8 | KEEP 7/8 | REVISE 5/6 | KEEP — trim to the script (+ a real parser bug) |

**Zero CUTs from any lens, again.** Every skill clears the deserve-to-exist bar.

## The new skills

**evaluate-skill — unanimous KEEP, and the engine was verified, not taken on faith.**
AUDITOR and DOMAIN-EXPERT read the code: "`stats.wilson_interval` is mathematically
correct; `decide_pairwise` genuinely requires *both* swap-orderings to name the same
winner (real position-bias control); `score_from_criteria` recomputes from rubric
weights × the judge's met-flags rather than trusting the model's arithmetic; the
config-contamination trap is real and load-bearing." That is the strongest possible
validation of productizing the eval — the skill ships correct measurement machinery a
base model could not reconstruct. Notes: ship a `--scaffold` to lower the setup cliff;
fix a stale `run_all.py` docstring ("all 3 skills"); surface judge-agreement in the
scorecard as a trust signal.

**consolidate-knowledge — KEEP/REVISE split (2–2).** The promotion gate (reinforced +
specific + non-reconstructable + actionable), the "under-promoting is safe; over-
promoting pollutes the durable layer" asymmetry, the "losing the scar" anti-pattern,
and supersession reconciliation are all praised as sound. The REVISE case (AUDITOR,
ADVOCATE): it is the only discipline skill that is **prose-only with no script and no
worked example**, its margin over a base model asked to "find patterns in these notes"
is the thinnest in the set, and it overlaps journaling-sessions' framing. To earn
standalone status: **(1) add a small clustering script** (read entry files, group by
area/domains, surface candidate clusters + singletons — so the model does judgment,
not bookkeeping, like its siblings); **(2) add one worked before→after example** (raw
cluster → promoted GUIDANCE entry); (3) sharpen the trigger boundary vs journaling.

## Where the panel agreed (the standing recommendations)

1. **Put the long skills on a context diet.** All four flag it again: python-engineering
   (~400 lines) and data-engineering-discipline (~305 + 7 refs) restate 2026 consensus
   and inline content their references already hold; lead with the checklist + scripts,
   demote the philosophy. (Still the deferred editorial backlog — now flagged by two
   independent panels.)
2. **toolkit-awareness: trim to its script + fix a verified parser bug.** DOMAIN-EXPERT
   found a real one: `scan_toolkit._read_frontmatter` is a hand-rolled non-YAML reader
   that mis-handles `>` folded-scalar descriptions — truncating to the first line — i.e.
   it would mis-report python-engineering's and data-engineering's own descriptions
   (which use `>`). The prompt-authoring half of the body is also skimmable filler.
3. **The new unanimous gap — a retrieval/apply skill.** All four independently: the
   collection captures (journaling), consolidates (consolidate-knowledge), hands off,
   reviews, and evaluates knowledge — but **nothing loads the durable guidance back
   into a running session.** "It captures and consolidates but never closes the loop by
   feeding it forward into new work, which is where the whole pipeline's value is
   realized." This replaces the consolidation gap (now filled) as the top missing skill.
   DOMAIN-EXPERT also names a possible SQL/query-correctness skill as a second gap.

## Collection verdict (synthesis)

Unanimous: a coherent, unusually disciplined two-plugin set with deliberate seams —
a knowledge lifecycle (journaling → consolidate, plus handoff / toolkit / review /
eval) and an engineering-correctness loop (python + data-contract + the freshness
loop that maintains them). The distinguishing virtue, named by every lens, is that the
heaviest skills are **backed by working, tested code** (Wilson CIs, swap-order judging,
`is_behind` 0ver handling, runnable parity/contract scripts) — they extend capability,
not just lecture. The strongest members (data-engineering-discipline, review-panel,
evaluate-skill) earn their cost decisively; the command-first / manual-only skills pay
zero auto-context. The one standing smell is **length under skim-pressure** in the long
discipline skills. The set is "one editing pass away from being tighter than it is
comprehensive."

## Round-1 → round-4 arc

- toolkit-awareness: REVISE×3 (round-1, the plugin-blind bug) → KEEP×4 (round-3, fixed)
  → KEEP×3/REVISE×1 (round-4, now "trim to script" + the folded-scalar parser nit).
- review-panel: new → unanimous KEEP, best-designed, three rounds running.
- evaluate-skill, consolidate-knowledge: new this round; eval debuts unanimous-KEEP with
  a verified engine, consolidate debuts KEEP/REVISE (sound, needs a script + example).
- The two big skills' body-bloat note persists because the broad trim stays deferred.

## Method note

Run via 4 parallel free-text Agent calls (not a schema-workflow) — clean, zero failures,
~2–4 min each. The matrix is hand-assembled from the four independent reviews.

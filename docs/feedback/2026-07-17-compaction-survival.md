# compaction-survival feedback — cold-start anchor vs a git-cleanliness stop hook

- **Date:** 2026-07-17
- **Tool/version:** session-workflow 0.16.0 (exercised from the working tree)
- **Context:** armed the protocol by hand for an overnight autonomous run (Phase
  A llm-signature integration + Phase B trigger-tuning A/B). The session's
  harness had no anchor hook (`SESSION_WORKFLOW_ANCHOR_HOOKS` unset), so I used
  `references/cold-start.md`: a hand-maintained anchor at
  `.claude/anchors/2026-07-17-overnight-integration.md` with the tail marker,
  re-read and rewritten each turn.
- **Outcome:** the anchor did its job — state stayed recoverable across many
  turns and background-eval boundaries — but the recommended anchor path
  collided with the environment's git-cleanliness stop hook, once per turn,
  until I worked around it.

## What worked

- **The cold-start recipe is sufficient without the plugin surface.** Building
  the anchor from the section list (mission, plan pointer, cursor, in-flight
  work, invariants, last-known-good, resume steps) + the `<!-- anchor:tail -->`
  split worked with nothing installed. The in-flight-work section (background
  task IDs + log paths + "do not relaunch over this output") was the load-bearing
  part across ~6 background eval boundaries — no double-launch happened.
- **HEAD/TAIL split kept the injected region bounded** as phases folded to
  one-line tail history.

## Friction

- **[MED] The recommended anchor path reads as "untracked" to a repo git-check
  stop hook.** This environment runs a `Stop` hook that flags uncommitted /
  untracked files. `.claude/anchors/` is untracked working state by design, so
  the hook fired *every turn* ("There are untracked files… please commit and
  push") until I added `.claude/anchors/` to `.gitignore`. The cold-start recipe
  names `.claude/anchors/<date>-<slug>.md` as the path but says nothing about
  the directory reading as untracked — in any repo with a cleanliness gate,
  that is guaranteed recurring noise for the whole run.

## Misses

- **[LOW] No `.gitignore` guidance for the anchor dir (phase: cold-start docs).**
  The anchor is explicitly discardable working state ("live working state,
  discarded once the run completes"), so it should never be committed — which is
  exactly the case a `.gitignore` entry expresses. The recipe (and the CLAUDE.md
  minimal-contract snippet it tells you to mirror) should ship the one line
  `.claude/anchors/` alongside the path recommendation, so a repo-hosted run
  doesn't rediscover the collision.

## Vacuous gates

- None observed (this skill has no gate of its own; the friction was an
  *external* gate interacting with it).

## Proposed promotions / changes

1. **[MED]** anchor dir is discardable working state but reads as untracked to
   repo cleanliness gates → add one line to `references/cold-start.md` (and the
   minimal-contract list): "in a git repo, add `.claude/anchors/` to
   `.gitignore` — the anchor is working state, never an artifact." Removes a
   per-turn stop-hook collision for any repo-hosted autonomous run. Home:
   `plugins/session-workflow/skills/compaction-survival/references/cold-start.md`.

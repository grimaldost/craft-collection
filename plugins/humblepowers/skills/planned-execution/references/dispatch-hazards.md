# Dispatch hazards — what bites a delegated step

Environment traps that cost a plan real time. Each is stated as the observation
and the sequencing that avoids it; none is a rule about how to plan, which is
why they live here rather than in the body.

## Format-on-save hooks rewrite the file after you write it

A hook that runs after `Write` reformats what you wrote — quote style, wrapping,
exploded call arguments — and some also strip unused symbols. Two consequences,
and the second is the one that surprises people:

- **Author each import in the same step that first references it.** An "add the
  import now, use it later" sequence breaks under a strip-on-save hook: it
  removes the still-unused import the instant it lands, and the later step hits
  an undefined name.
- **Re-read from disk before any edit anchored on remembered text.** Even a
  format-only hook that never strips anything still changes the file's bytes, so
  a patch keyed to the exact string you wrote will miss. This is the more common
  case, because a well-built format hook deliberately excludes the
  import-removing autofix and therefore produces *only* this failure.

## An isolated worktree nests, so `../` siblings do not resolve

A per-agent worktree lives at `repo/.claude/worktrees/<agent>/`, so a sibling
dependency declared as `../other-repo` resolves inside the worktree tree and
fails. Declare it in the brief, use whatever provisioning the environment offers,
and do not reach for a junction, a symlink, or a bulk copy of the sibling repos —
observed once as a security-classifier refusal followed by the same thing done
another way, which is the pattern the classifier exists to prevent. A single line
of warning in the spawning prompt was the mitigation that worked.

## Per-phase commits in a multi-phase worktree

Stage a phase's full file set and commit with no unrelated tracked-dirty files:
pre-commit stashes whatever is unstaged, a format hook may auto-fix a staged
file, and the stash-pop then conflicts — the commit aborts, the file left `MM`
(staged + unstaged auto-fix). Recover by re-`git add`-ing the auto-fixed file;
prevent it by committing each phase from an otherwise-clean tree.

## A backgrounded gate ends the subagent's turn

The harness notifies the *parent* when a background task finishes, not the child
that started it, so a subagent that backgrounds a long gate and ends its turn
waiting is never woken: it takes a manual resume message. Observed five times in
one session on pytest, suite and build runs of 5-15 minutes, costing about six
manual interventions. The implementer template carries the rule
(`subagent-prompts.md`); the same session recorded zero recurrences once the
instruction was in the prompt.

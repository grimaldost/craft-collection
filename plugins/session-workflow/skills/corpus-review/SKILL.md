---
name: corpus-review
description: >
  Audit a large file corpus — dozens to hundreds of docs, configs, or mixed
  code-plus-docs-plus-tests — by fanning out blind reviewers over partitions,
  adversarially verifying every high-severity finding before acting on it,
  fixing in disjoint file partitions, and re-auditing with fresh eyes until the
  findings converge. Use when reviewing or auditing a whole repo's
  documentation, a release's doc set, an entire plugin or package, or any file
  set too large for one reader to hold at once; on asks like "review all the
  docs before we push", "audit the whole repo for X", "blind review across these
  N files", "do a pre-push review of everything", or "check the docs still match
  the code across the project". It orchestrates the audit on the harness's
  parallel subagent and workflow primitives and ships no engine of its own. Not
  for a fresh-eyes panel on a single design, spec, or artifact (that is
  review-panel), not for reviewing one change's diff for bugs and regressions
  (that is a diff review / code-review), and not for behaviorally measuring
  whether a skill triggers and performs (that is evaluate-skill).
---

# Corpus Review

A single reader cannot hold a few hundred files in working memory, and a single
pass over them misses what only a second angle catches. The pattern that scales:
partition the corpus, review each partition blind and in parallel, verify a
finding before acting on it, fix without collisions, and re-audit until the
findings dry up.

This is a **flexible** skill, and it ships no engine — it orchestrates the audit
on whatever parallel-agent or workflow primitive the harness provides, and
degrades to plain sequential review when none is available. What stays firm is
the shape of the loop.

## The loop

1. **Partition the corpus into coherent groups** — by directory, subsystem, or
   artifact kind — each small enough for one reviewer to read closely together
   with the real source it should agree with (a doc against the `src/` it
   describes, a config against what consumes it).
2. **Review each partition blind and in parallel.** One reviewer per group, each
   unaware of the others, so findings are not anchored by a shared first read.
   The reviewer reads the artifact *and* its ground truth, never the artifact
   alone.
3. **Adversarially verify every high-severity finding before acting.** A finding
   is a claim until a second, skeptical agent confirms it against the code.
   Unverified findings are where a fan-out wastes the most effort — a confident
   reviewer can be confidently wrong.
4. **Fix in disjoint file partitions.** Parallel editors that never touch the
   same file need no worktrees and cannot collide; partition the confirmed
   findings by file before fixing.
5. **Re-audit with fresh eyes, and stop on convergence.** Each round's
   high-severity yield should fall; halt when it drops below a threshold instead
   of running an open-ended next round on noise. A falling curve (for example
   157 → 49 → 9 findings) is the stop signal.

## Execute the artifact, don't only read it

For a corpus with executable parts — hooks, scripts, example programs, a CLI —
the highest-assurance round runs the artifact with synthetic inputs rather than
reading it. Executing every hook with a sample payload and every example script
catches what reading cannot: a fix-introduced regression, a reference to a
symbol that no longer exists, an example that no longer runs. Reading-only
rounds routinely pass these.

## Concurrency and resume

- **Cap peak concurrency.** A large fan-out hits provider rate limits; a ceiling
  on simultaneous reviewers trades a little wall-clock for not having to re-run a
  rate-limited slice.
- **Make slices resumable.** Record which partitions converged, so a failed or
  rate-limited slice re-runs on its own without redoing the rest.

## Common failure modes

| Pattern | What it costs |
|---------|---------------|
| Reading the artifact without its source | Misses doc-vs-code drift; confirms the doc against itself. |
| Acting on unverified findings | Fixes a confidently-wrong claim; adds churn. |
| One reviewer for too large a group | Attention thins; the tail of the group gets a shallow read. |
| Reading-only on an executable corpus | Runtime breakage and fix-introduced regressions survive. |
| Parallel editors on shared files | Collisions, lost edits, or a forced serialization. |
| No convergence rule | An open-ended Nth round reviews mostly noise. |

## Boundaries

- **review-panel** convenes a fresh-eyes panel on a *single* design, spec, or
  artifact the user has iterated on. A corpus is the other axis — many artifacts,
  one angle each, fanned out — so it is this skill's job, not a panel's.
- **code-review / a diff review** reads one change's diff for bugs and
  regressions. A corpus review reads whole files against their ground truth,
  not a diff.
- **evaluate-skill** measures whether a skill triggers and performs — behavioral
  measurement of one tool, not a content audit of a file set.

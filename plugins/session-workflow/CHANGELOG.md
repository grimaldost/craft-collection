# Changelog — session-workflow

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

## 0.20.0 — 2026-07-24

Triage 2026-07-23 row T2a (Inputs coverage contract), reconciled against what
the parser actually does: `extract_inputs_coverage` was verified ALREADY
tolerant of any format carrying full stems (bullets, numbering, prose,
backticks — token-boundary match anywhere in the Inputs/Addendum sections).
The 2026-07-22 zero-coverage emit failed on stem FRAGMENTATION (a
date-grouped prose list factored the date prefix out, so no full stem
appeared), which no parser can safely reconstruct.

### Changed

- **feedback-triage SKILL.md:** the template's Inputs slot states the real
  contract (full stems, one per line; a factored-out date prefix reads as
  zero coverage), and step 7 closes with the mechanical self-check — re-run
  the index builder and read `### Untriaged`; just-triaged stems still listed
  means the Inputs did not parse. Fix before ending the pass.
- **test_build_feedback_index.py:** regression test pinning the failure class
  boundary — fragmented stems yield zero coverage, full stems parse from any
  surrounding format.

## 0.19.0 — 2026-07-23

Backlog P1-5 (triage T22a): anchor lifecycle hardening in `anchor_inject.py`.
A contract change, deliberate: a stale anchor is no longer injected in full.

### Changed

- **Age-gated injection tiers.** An anchor updated within 24h injects its full
  HEAD as before. Older, it degrades to a POINTER: path + title (first heading
  after frontmatter) + age + a confirm-to-expand line + the exact
  `mv <name> <stem>.closed.md` close command. A dead track now costs a
  paragraph per session start instead of up to 8K chars, and is still never
  silently dropped. The concurrent-tracks warning (other open anchors, rename
  commands for terminal-but-unrenamed ones) rides both tiers. Telemetry gains
  `tier: full|pointer`.
- **Matcher widened to `compact|resume|clear|startup`.** `/clear` wipes
  context in a continuing session — an explicit reset signal, same treatment
  as compact/resume. `startup` (fresh process) is the crash-restart path and
  gets a recency gate: inject only when the anchor was updated within 6h
  (`STARTUP_RECENT_S`), so an ordinary new session in a cwd with an old
  anchor stays untaxed. Mirrored in the cold-start recipe
  (`references/cold-start.md`). Accepted cost, named: when the gate env is on,
  the hook subprocess now spawns on every session start (the matcher cannot
  see mtimes) — only its OUTPUT is gated.

Test contract updated in kind: the old "stale -> full body + warning" case is
replaced by pointer-tier assertions (body withheld, close command present,
bounded size), plus startup-window, clear-source, boundary (23h), and
telemetry-tier cases.

## 0.18.0 — 2026-07-23

Backlog P1-4: mechanize the standing tool-feedback default. Both hooks ship
wired but inert (house rule); enabling is two env vars.

### Added

- **Skill-exercise ledger (async PostToolUse, gate
  `SESSION_WORKFLOW_EXERCISE_LEDGER=1`).** Matcher `^Skill$|^mcp__plugin_.*`;
  appends `{ts, tool, skill, prompt_id}` per invocation to
  `<CLAUDE_PLUGIN_DATA>/exercise-ledger/<session_id>.jsonl`
  (`SESSION_WORKFLOW_LEDGER_DIR` overrides; tempdir fallback). This is the
  substrate for real-session activation telemetry — the observational
  replacement for spent trigger holdouts — and the evidence base the Stop
  nudge reads. Registered `async: true`: a headless probe (2.1.218) verified
  async hooks still receive the full stdin payload, so the append costs the
  turn nothing.
- **Feedback-debt Stop nudge (gate `SESSION_WORKFLOW_FEEDBACK_NUDGE=1`).**
  At Stop, when the ledger shows plugin tools were exercised, no
  `tool-feedback` invocation is on record, and the transcript counts at least
  `SESSION_WORKFLOW_NUDGE_MIN_TURNS` (default 8) real user turns, it emits one
  `decision:"block"` whose reason asks the model to apply the tool-feedback
  skill — or finish if nothing is worth recording. "Real user turns" is
  literal: `type=="user"` transcript records count only when they carry human
  text — tool results (the majority of user-typed records: 64 of 71 in the
  reviewed real transcript, all textless) and synthetic
  `[SYSTEM NOTIFICATION`/`<task-notification>` completions are excluded, a
  defect the adversarial review caught before ship (the gate would otherwise
  have been ~10x too loose and effectively inert). `stop_hook_active` exits
  early (probe-verified loop guard); a marker file caps the nudge at once per
  session; the block prints before the marker persists so a delivery failure
  never burns the slot (regression-tested by forcing the print to fail).
  Known imprecision, accepted and documented: a report written without
  invoking the skill is not detected.

Both paths: stdlib-only, ASCII-only runtime output, every failure exits 0.
Test sibling `test_exercise_ledger.py` covers gates, matcher mirror, hostile
session ids, marker semantics, debt clearing, synthetic-turn exclusion, and
garbage stdin.

## 0.17.0 — 2026-07-23

`toolkit-awareness` / `scan_toolkit.py` gains three related staleness defenses,
all in the SessionStart path. Minor bump: the scan script gained capability, no
skill `description` changed (no holdout implications).

### Added

- **Skill-list skew, beside the version check.** `_merge_skew` compares installed
  vs source *versions*, which sees nothing when an install carries no `plugin.json`
  at all — yet whole skills can still be missing locally. A new `_skill_list_skew`
  diffs the skill *directory* names (subdirs holding a `SKILL.md`) between each
  plugin's marketplace source and its installPath, and emits one caveat per lagging
  plugin: `installed copy lags repo: <plugin> missing skills: a, b -- consider
  claude plugin update <plugin>`. Missing-in-installed only (an extra local skill is
  not the footgun); an unresolvable source is compared against nothing — absence of
  evidence is not skew. Reuses the source-dir resolution the version check uses
  (factored into `_source_plugin_dir`).
- **Serving-snapshot check (frozen-snapshot detector).** The desktop app can serve
  a plugin hooks snapshot frozen weeks behind the installed cache while every disk
  layer reads "current"; the only observable is the session transcript's recorded
  hook-command strings differing from the installed `hooks.json`. On `--session-start`
  the scan reads the hook envelope from stdin (fail-open: non-tty only, any error
  skips), parses `transcript_path` as NDJSON, collects each `attachment.command`
  containing `${CLAUDE_PLUGIN_ROOT}` (settings-level hooks vary legitimately and are
  excluded), and diffs them against the joined `command + args` form every installed
  plugin `hooks.json` declares. A recorded command that no install produces yields a
  caveat (deduped, capped at 2) naming the frozen snapshot and pointing at `claude -p`
  to verify headless. No transcript / no records / all matched -> silence. A new
  `--check-serving <transcript_path>` mode runs the same diff on demand, printing
  either `serving snapshot matches installed hooks` or the caveat lines; always exits 0.
- **Inventory cache for `--session-start`.** The inject shells to the `claude` CLI
  (seconds), which is why it can't default on. The path now fingerprints the settings,
  installed-plugin, and marketplace-manifest files (plus the script itself and the
  scan roots) by mtime/size; a warm hit under 24h prints the cached inventory without
  invoking the CLI. A miss or any error falls back to a full scan, then writes the
  cache atomically (tmp + `os.replace`) — every cache failure path is silent, never
  fatal. `--no-cache` forces a scan; the table and `--json` modes never touch the
  cache. The persisted record carries the plugins' installPaths so the
  serving-snapshot check still works on a cache hit without the CLI. The
  `TOOLKIT_AWARENESS_INJECT` default is deliberately unchanged: cache first, measure,
  then decide whether the inject is cheap enough to enable by default.

Fifteen new fixture/NDJSON tests (skill-list skew, fingerprint sensitivity, cache
hit/miss/TTL/corrupt, transcript parsing, matched-vs-frozen serving diff, and the
`--check-serving` CLI). Existing version-skew and stale-checkout tests unchanged.

## 0.16.2 — 2026-07-22

### Fixed

- **evaluate-skill: ASCII-only runtime output.** `aggregate.py` and
  `run_triggers.py` emitted em dashes in `print()` / list-item strings that reach
  a console at runtime — the same cp1252-mojibake class the 0.16.1 llm-signature
  fix closed, surfaced across the plugins by the 2026-07-22 stress sweep. Runtime
  strings now use ASCII hyphens; docstrings (never encoded to a console) are
  untouched. The recurrence argues for a mechanical lint over per-instance fixes;
  that gate is tracked in `docs/design/2026-07-22-hooks-program.md`.

## 0.16.1 — 2026-07-22

### Fixed

- **llm-signature: ASCII-only CLI error output.** The could-not-resolve stderr
  message carried an em dash; on Windows a child process encodes it as cp1252
  (0x97) while a utf-8-decoding parent's reader thread raises and returns
  `stderr=None` — which made `test_render_signature.py` fail environment-
  dependently and blocked every push from this machine. Same cp1252 trap class
  the hook conventions already ban for hook stdout; runtime-emitted text in
  bundled scripts now follows it too (docstrings/comments unaffected).

## 0.16.0 — 2026-07-17

New capability: provenance signing for agent-assisted work. Minor bump: a new
skill and script. Maintainer-directed design decisions, recorded: the signature
is always machine-generated (a hand-typed one rots, and wrong provenance is
worse than none); it is selective (enabled plugins only, `--plugin` to narrow);
the model listed is the one writing and orchestrating at commit time — the one
responsible for the change; and the model appears only in `Assisted-By`, never
as a commit co-author (`Co-Authored-By: Claude` boilerplate carries no
information and is actively scrubbed).

### Added

- **`llm-signature` skill** — sign agent-assisted work with two machine-readable
  git trailers: `Assisted-By: <exact-model-id>` and
  `Agent-Stack: <name>@<version> (<marketplace>); ...` (harness + enabled
  plugins; the marketplace label is a lookup key, so URLs stay out of commits).
  Spec in `references/spec.md` (`llm-signature/v1`), including read-back
  recipes (`git log --format='%(trailers:key=Assisted-By,valueonly)'`) and an
  optional `prepare-commit-msg` hook recipe.
- **`scripts/render_signature.py`** — renders the trailer block from live
  sources: the model from the session transcript's last main-loop assistant
  message (sidechain/subagent and `<synthetic>` entries never sign; transcript
  auto-discovery matches the munged cwd under `~/.claude/projects/` and is
  gated on a live session so a stale transcript cannot sign the wrong model),
  the stack from `claude plugin list --json` + `claude --version`. Render mode
  fails loud when the model is unresolvable (never guesses); `--apply
  <msg-file>` is the commit-safe mode — refreshes trailers idempotently, scrubs
  `Co-Authored-By: Claude/Anthropic` lines and "Generated with Claude Code"
  badges (human co-authors always survive), and exits 0 on any failure so a
  signing problem never blocks a commit. Stdlib-only, 15 tests
  (`test_render_signature.py`, bare-python runnable), verified live in-session
  (resolved the running model and harness version end-to-end).

### Fixed (review round, same release)

From the four-lens adversarial panel (architect / skeptic / correctness /
adopter) convened on this branch — unanimous REVISE, kernel endorsed, six
defects reproduced by execution and fixed test-first:

- **`--apply` could abort a commit on a non-UTF-8 message** — only `OSError`
  was caught, and `UnicodeDecodeError` is a `ValueError`; legal git
  (`i18n.commitEncoding`) crashed the hook with exit 1. Now reads bytes,
  round-trips via `surrogateescape`, and the whole apply path catches
  `Exception` — no input produces a nonzero exit (non-UTF-8 regression test).
- **`git commit --verbose` silently lost the signature** — the block was
  inserted after the scissors line, inside the diff preview git strips (and the
  scrub mutated diff lines). Everything from the scissors line on is now
  frozen; the block lands before it.
- **The glue heuristic could hide the trailers from git** — checking only the
  last line welded the block onto a prose paragraph ending in a trailer-shaped
  line (`Note: …`), and `git interpret-trailers --parse` returned empty. The
  block now joins an existing paragraph only when EVERY line of it is
  trailer-shaped; a test asserts `git interpret-trailers` actually parses the
  output.
- **A custom `core.commentChar` resurrected aborted commits** — a comment-only
  message under `commentChar=;` was treated as content and signed.
  `apply_to_message` takes the configured comment char (read via
  `git config core.commentChar` in hook mode).
- **The scrubber destroyed content it didn't own** — a human co-author named
  Claude (`<claude.dubois@example.fr>`) was deleted, and `_AI_BADGE.search`
  ate body prose mentioning "generated with … Claude". Scrubs are now anchored
  to the vendor's identity (anthropic.com / claude+noreply addresses), match
  flush-left whole lines only, and never touch indented/quoted examples — the
  "human co-authors never match" claim is now true (tested). A
  `Claude-Session:` trailer is deliberately left untouched (session
  traceability, not attribution marketing) — decision recorded in the spec.
- **Transcript auto-discovery could sign the wrong model** — `CLAUDECODE`
  proves *some* session is live, not that the newest-mtime `.jsonl` is
  *this* session's, and the lossy cwd-munging collides distinct projects
  (`my.repo` ≡ `my-repo`). A candidate now signs only when fresh (30-min
  window) AND the cwd recorded inside the transcript verifies against this one
  by exact path; nothing verifiable → refuse to sign. The residual
  same-cwd-concurrent-sessions race is documented honestly in the spec with
  the deterministic escape (`--transcript`/`--model`). Auto-discovery also
  gained descendant-dir nomination (hook at repo root, session started
  deeper), and unsigned (human) commits no longer pay the claude-CLI calls.
- **The hook recipe could brick a repo** — with `uv` off PATH or a moved
  install path, the verbatim `prepare-commit-msg` recipe exited nonzero and
  aborted every commit, human ones included. The recipe now guards its
  preconditions (`command -v uv || exit 0`, script-exists check, `|| true`).
- Docs honesty from the same round: `Agent-Stack` semantics renamed to
  **environment-at-commit** provenance ("enabled" ≠ "shaped the work"); an
  **Adopting in a repo** section defines the one CLAUDE.md line the trigger's
  "a project that adopts the signature" refers to; real model IDs noted as
  dated (`claude-sonnet-4-5-20250929`-style), so read-back greps match
  history; "provenance record, not cryptographic signature" stated; the
  repeated-`Agent-Stack:`-keys and augment-vs-replace alternatives recorded
  with their rejection rationale. CRLF messages round-trip. Declined, with
  rationale: cutting `--json`/`--plugin` (they implement the owner's
  selectivity constraint) and reducing the stack to harness-only (contradicts
  the owner's requirement to list the tool stack). Test suite 15 → 23.
  SKILL.md word budget 365 → 412 (adoption pointer + honest semantics; no
  clause retired).

### Notes

- Trigger surface: a dev trigger dataset ships
  (`evals/trigger/llm-signature.json`, 7+/6−) and the skill is registered in
  `evals/config.json`; the sealed holdout is deferred to the next calibration
  round so it can be sealed **with a birth baseline**, per the 0.6.5 doctrine —
  no holdout is sealed without a birth number.
- Word budget seeded: llm-signature 365.

## 0.15.0 — 2026-07-16

### Changed

- **Capability-conditional wording (multi-agent portability).** review-panel,
  compaction-survival, toolkit-awareness, and evaluate-skill no longer gate
  load-bearing instructions on the harness name: each states the capability it
  needs and a degradation ladder (fresh-context subagents -> sequential clean
  contexts; CLI plugin enumeration -> AGENTS.md index -> directory scan;
  hook re-injection -> manual anchor re-read). Claude Code mechanics stay as
  mechanism notes. Word-budget baselines bumped for the four bodies: the
  growth displaces nothing — conditional ladders replaced absolute
  harness-gating that read as "skip this skill" off Claude Code.
- **AgentRunner seam.** The evaluate-skill engine routes spawns through an
  AgentRunner protocol with headless Claude Code as its only backend today;
  trigger numbers remain measured on Claude Code (plugin mirror re-synced).

## 0.14.3 — 2026-07-14

### Fixed

- **evaluate-skill: errored-before-activation runs no longer feed a recall
  verdict.** A held-out or dev positive run that errors *before* the skill can
  activate (e.g. `Prompt is too long`, which never executes the query) carries no
  evidence the description failed, yet the scorecard (`aggregate.py`) and
  `holdout_check.py` read the strict recall — which counts those runs as misses —
  into a gate / DROP verdict. `score_skill` already excludes them
  (`recall_excl_errors`); this brings the two report surfaces to parity **without
  changing the gated number**: the scorecard recall cell gains an
  `(err=N; excl=X)` annotation (+ legend), and `holdout_check` prints the
  error-excluded recall and names the infra cause instead of declaring "overfit"
  when excluding the errors would clear the dev bound. Also fixes
  `holdout_check.py`'s docstring, which advertised positional
  `[repeats] [concurrency]` the argparse rejects (`--repeats` / `--concurrency`).
  Resolves the `choosing-models` birth-baseline caveat: 3 identical
  `Prompt is too long` errors on one held-out query read 0.75 / below-gate where,
  excluding them, recall was 1.00. `aggregate.py` is copied to the bundled
  template; `test_scripts_in_sync` guards the pair.

## 0.14.2 — 2026-07-14

### Changed

- **review-panel:** the cost guardrail routes reviewer tier through a
  capacity-dispatch policy when one is installed (e.g. humblepowers'
  choosing-models, per its stakes rule); the ladder and the step-5 "Opus for
  high stakes" default stay as the standalone fallback. Net −1 word.

## 0.14.1 — 2026-07-14

### Fixed

- **toolkit-awareness reads the right repo under a git hook.**
  `_source_behind_upstream` ran `git -C <dir>`, but a hook exports `GIT_DIR`,
  which takes **precedence over `-C`** — so every child git answered about the
  *outer* repo. Two consequences, one cause: the staleness check silently
  reported another checkout's "commits behind" (the exact wrong-repo reading
  the check exists to prevent), and the pre-push suite failed inside `git push`
  while passing standalone, which blocked every push from a hook-installed
  clone. Both git call sites now scrub `GIT_*` from the child environment via a
  shared `_git_env()`. Regression test sets `GIT_DIR` to a decoy repo and
  asserts the real answer; it fails without the fix.

## 0.14.0 — 2026-07-14

Build round for the 2026-07-14 triage. The 0.13.0 anchor wave shipped the close
*mechanism* (rename) without a lifecycle *trigger*, and terminal anchors piled up
(seven stranded across ~8 tracks in three days); this wave escalates that
recurrence from prose to a mechanism, and closes a matching hole in the feedback
loop's own precision (findings and open rows leaving by omission). Minor bump: the
hook and two skills gained capability.

### Added

- **Anchor lifecycle: terminal anchors stop accumulating (T13a/T13b/T13c).**
  `anchor_inject.py` gains `is_content_terminal()` — one predicate, anchored to a
  whole-anchor `status:` line so a folded per-phase "STEP 1 status: done" does not
  match. It drives three behaviors: selection **de-ranks** a content-terminal
  anchor below live tracks (`select_anchor`), so a newer closed-but-unrenamed
  track no longer shadows an older active one; the multi-anchor warning now emits
  the exact `mv <name>.md <name>.closed.md` for each terminal-but-unrenamed
  anchor; and `list_stale()` / `anchor_inject.py --list-stale` backs a new
  `/anchor close --stale` cycle-end sweep. The rename stays the only signal that
  *stops* injection — in-content status only reorders and offers the rename, so
  T5b's bright line holds. compaction-survival SKILL states close-at-cycle-end and
  the wind-down sweep; the failure-mode row for "closed in prose, never renamed"
  now names the mitigation. (`v19-sw#1`, `datacontext-anchor-accumulation#1/#2/#3`,
  `datacontext-reconciliation-sw#1`, `dc-campaign#3`.) **Scope of T13c, stated
  honestly:** de-ranking resolves the *terminal-shadowing* case — a stale
  closed-but-unrenamed track shadowing a live one, which is what the accumulation
  reports evidenced. A genuinely-*active* wrong-track anchor (`context-handoff#2`)
  is not disambiguated by content; it still warns and names the tracks, and a
  track-scoped selection signal (an active-anchor pointer or branch scoping) is
  carried as a **watch row**, not built this wave — de-ranking is not a substitute
  for it. The predicate approach was chosen over a pointer for the shadowing case
  because it needs no new convention.
- **In-flight work as a first-class cursor element (T13d)** + two resume-discipline
  lines: a cursor is eventually-consistent during tool outages — trust the
  version-control log/ledgers over it when they disagree (CS2); a stored recovery
  command is validated against the live artifact before an unattended run (CS1).
  (`staging-runall-sw#2`, `dc-campaign#1`, `tu-grounding §Friction`.)
- **compaction-survival cold-start reachability (T15a).** The by-hand recipe lives
  inside the skill, unreachable exactly when the skill is absent from the menu; the
  doctrine now keeps a compact minimal contract (anchor path, tail marker, cursor,
  `.closed.md` rename) in `references/cold-start.md` for mirroring into the CLAUDE.md
  protocol snippet, where a menu-less session still has it.
  (`data-context-deep-review-sw#1`, `mantis-docs §Friction`.)
- **feedback-triage closure invariant (T14a/T14b).** Step 7 asserts **input
  coverage** before emit — every `<stem>#<n>` in the Inputs appears under a
  disposition, so a finding leaves only with one, never by omission; step 2
  reconciles **open rows across every triage doc in the dir** (via the INDEX
  `## Triage coverage` map), not just the latest chain, so an off-chain
  cycle-scoped triage's rows do not orphan. The template's ledger gains the third
  closing assertion. Co-decided with keel's `reflection-triage` P3a.
  (`convoy-governance-sw#1`, `keel-post-0120-sw#1`.)
- **build_feedback_index credits addendum coverage (FT1).** Coverage now reads a
  triage doc's `## Inputs` plus its dated `## Addendum …` sections, so a report
  handled in an addendum stops resurfacing as `### Untriaged`. (`v19-sw#2`.)
- **context-handoff third mode: Backlog (CH1).** A curated slice can become a
  persisted repo document (findings-with-stable-IDs at a named path) that neither
  returns nor continues a thread — modes table, trigger row, workflow branch, and
  a Backlog template. Owner-directed build of a watch-status row (a single report,
  `context-handoff#1`); recorded as such.
- **review-panel: barrier before a verify stage (RW1).** Step 6 notes that when a
  verify stage follows the lenses, findings are collected in a barrier first — a
  pipeline that drops a finding on a verifier's error loses a real finding to a
  coarse failure, not a refutation. (`backlog-build-round#1`.)

### Notes

- **Word budgets re-seeded, growth named:** compaction-survival 1143→1391,
  feedback-triage 1556→1677, context-handoff 1560→1847, review-panel 1082→1120 —
  each the additive doctrine above, no clause retired. Per the "consolidate before
  you grow" check, compaction-survival and context-handoff are the two homes that
  grew most and are flagged for a consolidation pass next round.
- **Not built: FT2** (a tool-feedback note against bare "triage" in report
  filenames). The structural cause it guards — filename misclassification — is
  already fixed by the shipped H1-authoritative rule + the T6a version stamp;
  adding the note would re-prose an already-closed cause.
- **review-panel standing-authorization firing branch** (`data-context-deep-review-sw#2`)
  was found already shipped (SKILL.md durable-pre-authorization line) during
  triage grounding — confirmed, not re-built.

## 0.13.0 — 2026-07-09

Build round for the 2026-07-09 triage: the anchor gains machine-readable
structure the hook can honor (the root cause behind the whole truncation
lineage), and the feedback loop's scope/recurrence substrate stops depending
on trust and hand arithmetic. Minor bump: the hook and the index builder
gained capability.

### Added

- **anchor/v1 two-tier structure (T1a) + head-aware injection (T1b).** The
  anchor convention gains a literal `<!-- anchor:tail -->` marker: HEAD above
  (mission, cursor with next-action, invariants, last-known-good, resume
  steps), append-only TAIL below (decisions log, folded history).
  `anchor_inject.py` now injects only the HEAD when the marker is present —
  the live state is never the part the 8K bound cuts — and notes that a tail
  exists on disk. Marker-less anchors keep the whole-file behavior; the 8K
  truncation stays as the final bound. Displaces: the blind whole-file slice
  as the only behavior (5-report truncation lineage:
  `w4-compaction-anchor#1 → multiwave#1 → restarts#1 → datacontext-v1 §Friction
  → v18-postcycle#1`).
- **Multi-track warning in the hook (T5a).** With more than one open anchor in
  a cwd, the injection warns and names the others, so a resumed session on a
  concurrent track doesn't silently follow the wrong cursor; telemetry gains
  `open_anchors`. (`datacontext-v1-session-workflow#1`.)
- **Close is stub-then-rename (T1c/T5b).** SKILL.md protocol, `/anchor close`,
  and cold-start.md now state: on close, rewrite the anchor to a minimal
  landed stub, then rename to `*.closed.md` — the rename is the only close
  signal the hook honors; a prose "status: CLOSED" line does not stop
  re-injection. Displaces the full-ledger close format and the ambiguous
  "newest non-closed" doctrine line (`v18-postcycle#1/#2`).
- **NEXT-ACTION-ON-RESUME slot + pending-interaction re-ask (T2a/T2b).** The
  cursor's next action is a named, in-place-rewritten slot (one imperative
  step + a precondition to verify); an unanswered question/approval is armed
  there for verbatim re-ask. Displaces the ad-hoc prose "ON RESUME" blocks
  (`multiwave#2 → restarts#2`).
- **INDEX provenance stamp (T6a) + triage coverage (T6c).**
  `build_feedback_index.py` stamps its generator version and detection rule
  into the header (a stale-cache-built INDEX is visibly stale —
  `keel-post-0110-triage#1`, HIGH), and emits a `## Triage coverage` section
  mapping each `# Triage`-H1 doc to the report stems its Inputs cover, plus a
  computed `### Untriaged` remainder — the scope step becomes one Read
  (INDEX-minus-INDEX; the by-hand subtraction lost 6 reports across three
  passes). feedback-triage step 1 consumes it and states the corpus count with
  a thin-corpus branch (T8b).
- **Grounding before the promotion gate (T7a).** feedback-triage step 5 now
  grounds every row against the tool's current source (mechanism absent or
  present, implementable as stated, truthfully named) before gating — wording
  co-decided with keel's reflection-triage step 3, which shipped the same
  discipline (`keel-post-0110-triage#2`, `convoy-backlog-build#1`).
- **Delta-pass form specified (T8a/T8c).** Later passes emit a NEW doc
  (Inputs = new reports only; supersedes the baseline as status of record;
  consolidated backlog table; namespace continuation) — body clause in step 7,
  detail in `references/mechanics.md`; the "single report" negative trigger is
  disambiguated (a 1-report delta over a baseline is valid)
  (`convoy-triage-delta-pass#1/#2`, `v17-reflect-triage-passes#1`).

### Changed

- **tool-feedback step 2 rebuilds the INDEX before the recurrence check
  (T6b)** — an existing index may predate recent reports or an older detection
  rule; rebuild-always displaces the build-only-if-missing branch and the
  false-positive-prone count heuristic (`trs-etl-refactor-session-workflow#2`,
  `datacontext-v1-session-workflow#2`).
- **tool-feedback granularity wording (T4a):** one report per tool per
  distinct concern/surface (a library vs its consumer plugin) — displaces the
  ambiguous "one report per tool" line (`v16-cycle-disciplines#2`,
  `trs-etl-refactor-session-workflow#3`).
- Word budgets re-seeded for the growth these mechanisms brought:
  compaction-survival 952→1143 (two-tier anchor + close protocol displace the
  flat section list and its "keep it bounded" clause), feedback-triage
  1402→1556 (grounding + delta form displace the hand-subtraction scope
  procedure), tool-feedback 1117→1170 (rebuild-always displaces the
  conditional-build branch).

### Fixed (review round, same release)

From the adversarial review of this branch: `/anchor` stamps `format:
anchor/v1` (the structure it now writes) and its `close` gains the multi-track
guard the snapshot path already had (close the anchor whose `task:` line
matches; never stub-close another track's). `anchor_inject.py`: annotations no
longer evaluate at import (`from __future__ import annotations` — a 3.9 hook
runner would have failed before the exit-0 guard existed), an empty-HEAD
marker falls back to whole-file injection, the multi-track warning names at
most 5 anchors and counts the rest, mtimes are race-safe, and the module
docstring describes the head-aware behavior. `build_feedback_index.py`:
Inputs-coverage stem matching is boundary-aware (the corpus has
prefix-colliding stems — `refresh-on-read` vs `refresh-on-read-execution`).
README's hook bullet describes HEAD-only injection and the multi-track
warning. tool-feedback step 4's flat "one report per tool" (left unedited by
the T4a pass, contradicting the new granularity) now reads "each report (per
tool per distinct concern)", and step 2 restates at the point of action that
the rebuild targets the registered dir (budget 1170→1188).

## 0.12.0 — 2026-07-06

Build round for the 2026-07-06 triage (the tu-v16 campaign reports + the
polish-session residuals): the anchor hook's Windows encoding defect with its
lying telemetry, UTF-8 output across the unicode-printing scripts, the skew
check one layer below installed-vs-source, compaction-survival's cold-start
path, and a second production-validated review-panel pack. Minor bump: the
scripts and the pack library gained capability.

### Fixed

- **`anchor_inject.py` silently no-oped on Windows for any non-ASCII anchor —
  while telemetry logged success (N33a).** The hook runner hands the script a
  cp1252 stdout; campaign anchors essentially always carry non-ASCII (arrows,
  accented prose), so the print raised `UnicodeEncodeError`, the
  never-break-the-session fail-safe swallowed it, and the harness received 0
  bytes — after a success-shaped `anchor-inject` record had already been
  written, so `log.ndjson` pointed the wrong way. The script now forces UTF-8
  at the seam (`sys.stdout.reconfigure`, in-script so manual registrations
  inherit it), writes success telemetry only after the payload reached stdout,
  and emits a distinct `anchor-inject-failed` event (error class included)
  from the except path — still exit 0, never break a session start, never lie
  about it. Regression tests pipe a `→ · ⚠` anchor through a forced cp1252
  stdout and prove a failing emit logs the failure event, not the success.
- UTF-8 stdout in `scan_toolkit.py` and `build_feedback_index.py` (N33b) —
  same cause, cosmetic form: em-dashes mojibake through cp1252 pipes and a
  `→` in a description crashed the scan outright. Both now `reconfigure` to
  UTF-8 (`errors=replace`), matching `run_triggers.py`'s shipped precedent;
  cp1252-pipe regression tests added.

### Added

- **`scan_toolkit.py` flags a source checkout behind its fetched upstream
  (N38a)** — the skew below the 0.10.0 installed-vs-source flag: when the
  local marketplace checkout itself trails origin, installed==source reads
  "no skew" while both lag (a 13-commits-behind main nearly re-ran a whole
  audit). Per marketplace location, `git rev-list --count HEAD..@{u}` now
  yields a "source N commit(s) behind its fetched upstream" caveat; no
  network — it sees fetched-but-not-merged; non-repos, missing upstreams,
  and absent git are silently skipped. Fixture-tested with a real
  origin/clone pair.
- **compaction-survival `references/cold-start.md` (N36a)** — arming the
  protocol without the plugin surface: the anchor file by hand, manual hook
  registration in `settings.local.json` (with the `${CLAUDE_PLUGIN_ROOT}`
  caveat), and a verify-by-piping step naming the non-ASCII fixture. Three
  reports hit this in three distinct degraded contexts (stale plugin
  snapshot, mid-flight enablement, SDK harness without the skill menu) and
  each reverse-engineered the same recipe from source. The body gains one
  pointer bullet, the README's hook section points at the recipe, and the
  frontmatter description gains a final sentence naming `/anchor` and the
  recipe — **reseal note:** the sealed trigger holdout predates this
  description edit and should be re-baselined before the next
  description-tuning round (additive tail edit after the negative-space
  clauses, not trigger tuning; recall shift unlikely).
- **review-panel `references/personas-release.md` (N37a)** — the second
  production-validated lens set, captured as a pack: consumer-upgrade path /
  docs coherence / changelog integrity / cross-change interactions, firing on
  the *assembled* release artifact after per-change review, with the verdict
  and collate-conditions-into-one-work-list conventions from the validated
  run (4/4 verdicts changed what shipped). The pack table gains its row, and
  `personas-design.md` gains a library-vs-service re-grounding line for the
  ops lens (N37b).

Word budgets re-seeded and named: compaction-survival 908→952 (cold-start
pointer bullet), review-panel 1062→1082 (pack table row).

## 0.11.0 — 2026-07-05

Corpus-review round from the 2026-07-05 polish session (PRs #76–#78, #80, #81 +
the post-merge consistency pass): a vacuous-gate fix, two new trigger-harness
capabilities, doc-drift fixes, and one reseal-gated description edit. Minor bump:
the bundled eval-engine scripts gained capability.

### Fixed

- **The anchor hook's tests actually run now (#77).** `test_anchor_inject.py`
  used pytest `tmp_path` fixtures, but `run_tests.py` (the pre-push and CI
  runner) executes each module with bare `python` — the module collected zero
  tests, printed nothing, and exited 0, so the suite reported PASS while running
  none of the anchor re-injection hook's 8 tests. A vacuous gate on a shipped,
  load-bearing feature (since 0.8.0). Converted to the stdlib-runnable pattern
  every sibling uses; bare `python` now runs all 8 and prints `ok:`.
  `build_feedback_index.py` also gained `-h`/`--help` (the flag was swallowed as
  a directory arg → "not a directory: --help", exit 1); regression tests added
  for both.
- Doc drift (#76): the README documents both SessionStart hooks — the anchor
  re-injection hook (`SESSION_WORKFLOW_ANCHOR_HOOKS=1`, shipped 0.8.0) was
  missing and the section header read "Hook" singular; toolkit-awareness's
  example invocation uses the Store-stub-safe `uv run --no-project -- python`
  form its own hooks.json already used; `/anchor` documents all seven anchor
  categories (Decisions log was missing, and it said "all six"); review-panel's
  Level-3 firing step gains a fallback to the Levels-1–2 Agent-tool mechanism
  when the Workflow tool is unavailable, and drops the undefined "max-effort"
  tier conflation.
- Eval docs (#78 + this pass): `action_discipline_skills`, the sealed-holdout
  mechanism (`holdout_check.py` + seal-with-baseline), `pairwise.txt`,
  `disallowed_tools_trigger`, `cwd_fixture_of_skill`, and the auth preflight are
  all documented in `eval-harness.md`'s config sample/prose/gotchas;
  `evals/README.md`'s spawn/cost figure (5× stale) replaced with a
  self-correcting formula; evaluate-skill's outcome-eval pointer names fathom
  instead of the retired dyno; toolkit-awareness's body names its own
  SessionStart hook (doc parity with compaction-survival).

### Added

- **Trigger harness (#80, N28a):** per-skill `cwd_fixture_of_skill` — a
  cwd-dependent skill (corpus-review: fires over the files in front of it) is
  measured in a committed populated fixture (`evals/trigger/fixtures/corpus/`)
  instead of reading a false 0.00 recall in the empty temp cwd — and a deny-list
  preflight (`unknown_deny_tools` vs `KNOWN_CLI_TOOLS`): a stale name like
  `MultiEdit` now fails fast with the offender named instead of silently
  erroring every spawn (~20% sample shrink, 2026-06-28). A regression test locks
  in that a fired-then-errored run still counts as an activation. The bundled
  engine copy under evaluate-skill/scripts/ is re-synced.

### Changed

- **Description edit (#81) — reseal note:** tool-feedback's `description`
  trigger example "keel / pr-pilot" → "keel / convoy" (with the matching body
  offer-prompt example). Made with maintainer sign-off; the skill's sealed
  holdout predates the edit and should be re-baselined before the next
  description-tuning round.

## 0.10.0 — 2026-07-05

First build round of the 2026-07-05 triage (`docs/feedback/2026-07-05-triage-craft-collection.md`,
clusters N25–N32). Body, reference, and script work only — no skill `description`
changed, no holdout implications.

### Changed

- **review-panel** (N25b + N26a): one firing-mechanics rework absorbing five open
  rows instead of five appends — launch/publish trigger in "When to convene"
  (before an irreversible outward step; fresh eyes found launch-blockers on
  self-verified trees twice); Level-3 Workflow execution variant (per-lens
  reasoning-effort + schema-forced comparable output, which the Agent tool lacks);
  a persist-raw-before-synthesis step with the destination named at plan time (a
  truncated notification or dead orchestrator otherwise loses the corpus);
  durable pre-authorization counts as the go-ahead (autonomous sessions
  deadlocked on the mandatory fresh ask); corpus-audit negative space →
  `corpus-review` (N24b, open since 06-28); copy-skew guard-rail. Cost guard-rail
  tightened to offset.
- **toolkit-awareness / `scan_toolkit.py`** (N27a): flags installed-vs-source
  version skew per plugin — compares each installed version against its
  marketplace source manifest (live working tree for `directory` marketplaces,
  local clone for git), annotates rows with `source_version` + a visible suffix,
  and emits one scan caveat. Third-arc promotion (a stale 0.2.2 cache once hid an
  entire skill); graduates the N18b watch row. Six new fixture tests, no CLI
  required; unresolvable sources are skipped — absence of evidence is not skew.
- **tool-feedback + feedback-triage** (N32a/b): first consolidation pass under
  the 0.9.0 shrink doctrine — eager bodies 1541→1309 (−15%) and 1808→1578 (−13%)
  words, edge-case mechanics folded into each skill's new
  `references/mechanics.md` (copy-skew directions, destination fine print,
  H1-only triage-doc detection rationale, concurrent-session choreography,
  fan-out owner taxonomy). No rule lost; the duplicated index-build command
  deduped. Short of the rows' ≥20% aspiration — the remaining prose is layered
  (contracts, worked examples, fresh doctrine), per the verify-redundancy-first
  contingency the rows carry.

## 0.9.0 — 2026-07-05

The digestion side of the feedback loop gains a structural-fix preference and a
standing shrink path — the direct response to the stress panel's accretion
finding (loop bodies grew one clause per promoted finding, 806→1621 and 907→1491
words in 19 days, with no disposition that ever removes prose; see
`2026-07-02-stress-panel-repo-infra-and-meta` §Misses + proposal #9, plus a user
directive to digest cause-first and prefer structural fixes over appends).
Body-only — no skill `description` changed, no holdout implications.

### Changed

- **feedback-triage**: ATTACK now names a **fix shape derived from the cause**,
  with an explicit preference order — remove/simplify → restructure → mechanize
  → append prose (last, and only naming what it displaces). The promotion table
  gains a `fix shape` column so the choice is visible and auditable per row. New
  pipeline step 6, **"Consolidate before you grow"**: every pass emits shrink
  rows for homes that took appends, carry unexercised clauses, or near the size
  cap — the loop can now shrink a tool, not only grow it. The promotion-gate
  ledger's closing assertion adds "no prose append shipped without a named
  displacement". Offset: the re-prosing anti-pattern tightened to one sentence
  (it duplicated the escalation ladder).
- **tool-feedback**: proposals open with the suspected cause
  (`<cause> → <the change that removes it>`) — the reporter holds the richest
  evidence and triage clusters by cause, so capture now hands the cluster step a
  warm hypothesis instead of a cold symptom. Friction/misses quantify when cheap
  (minutes, $, retries — the corpus's strongest findings are the quantified
  ones), and the self-check verifies cause-before-symptom.

## 0.8.0 — 2026-07-04

The anchor gains its mechanical layer: automatic re-injection after compaction
or resume. Evidence-gated per the memory-suite v2 design — shipped only after
measurement established prevalence (32 real sessions with compaction events in
~30 days of local history; two same-day CC restarts wiped in-session state
while the on-disk anchor survived). No skill `description` changed.

### Added

- **Anchor re-injection hook** (`skills/compaction-survival/scripts/anchor_inject.py`
  + a second SessionStart entry in `hooks/hooks.json`, matcher `compact|resume`):
  re-injects the newest non-closed `.claude/anchors/*.md` as `additionalContext`
  in freshly compacted or resumed sessions. INERT by default — enable with
  `SESSION_WORKFLOW_ANCHOR_HOOKS=1`. Stale anchors (>24h) inject with an
  explicit warning rather than being silently trusted or suppressed; oversized
  anchors truncate at 8K chars; every injection appends an `anchor-inject`
  NDJSON telemetry line; every failure path exits 0 (a broken hook must never
  break a session start). Stdlib-only, TDD'd (8 tests, red-first).

### Changed

- **compaction-survival body**: "Explicit surfaces" documents the env-gated
  re-injection hook alongside `/compaction-survival` and `/anchor`. Body-only;
  the trigger description is untouched (no holdout implications).
- **hooks.json description** now names both inert hooks and their env gates.

### Not shipped, deliberately

- **PreCompact freshness gate**: parked. The measured local incident profile
  justifies re-injection (recovery), not compaction-blocking (gating) — and
  the gate carries a wedge risk at full context that remains unvalidated.
- **Synthetic fidelity matrix** (the 20-trial dyno bank): retired unrun. A
  4/4-unanimous analyst panel scored its value-of-information below cost, and
  retrospective mining of real session history supersedes it as evidence.

## 0.7.0 — 2026-07-04

The anchor gains an explicit command surface. No skill `description` changed —
no holdout implications; the new command has no auto-trigger surface at all
(explicit invocation only).

### Added

- **`/anchor` command** (`commands/anchor.md`): one-off control-anchor snapshot
  on demand — the manual backstop before a deliberate `/compact`, usable with
  or without the compaction-survival protocol armed. Writes the six anchor
  categories to `.claude/anchors/<run>.md` (identity frontmatter with a step
  counter), drops a self-ignoring `.claude/anchors/.gitignore` (`*`), appends
  an `anchor-write` NDJSON telemetry line per use, and supports `/anchor close`
  to archive a finished run's anchor. Telemetry doubles as the measurement
  seed for the dogfood-telemetry path named in the memory-suite v2 design.

### Changed

- **compaction-survival body** gains an "Explicit surfaces" section: direct
  invocation arms the protocol immediately (create/refresh the anchor now, then
  keep the cadence); `/anchor` is named as the one-off backstop and the
  boundary between the two is stated — the backstop replaces the prose ask,
  not the cadence. Body-only edit; the trigger description is untouched.

## 0.6.5 — 2026-07-02

context-handoff trigger-surface retune, closing the 0.6.4 holdout re-validation
flag. **The skill `description` changed again**; the spent 2026-06 holdout is
folded into the dev set and a fresh holdout ships **with a baseline measured at
seal time** — no holdout is "sealed" without a birth number again (a sealed-but-
never-run holdout hid this skill's overfit for four days).

### Changed

- **context-handoff description (v2 of the retune):** names the intent category
  ("packaged so a receiver with zero shared context can take it cold") and adds
  packaging vocabulary ("package this up…", "bundle this…", "standalone brief /
  self-contained handoff") alongside the existing trigger phrases; SUBTASK/FORK
  glosses tightened; the redundant `user-invocable: true` dropped (docs: menu-only,
  default true — an ablation run confirmed no trigger effect).
- **Dev trigger set 8+/8− → 12+/11−:** the spent holdout's 7 queries folded in.
  Two folded positives are marked `expected_hard` on semantic grounds (recorded in
  their notes): "offload… to a **background task**… paste the result back" and
  "carve… into a bounded **sub-task**… hand the result back" carry legitimate
  Task-tool readings in today's Claude Code, and flickered 0–2/3 across four
  same-day runs regardless of description wording. They are reported separately
  (`recall_hard`), not hidden.
- **Fresh holdout sealed with baseline** (4 intent-level positives avoiding all
  description vocabulary + 3 near-misses): dev gated recall **0.80** CI[0.63,0.90],
  specificity **1.00**; held-out baseline **0.08** (1/12 fires) / specificity 1.00.
  Recorded, deliberately NOT tuned against.

### Finding (recorded, not fixable by description tuning)

- Same-day control runs show the June dev number (0.95, r5) does not replicate:
  the pre-0.6.4 description scores 0.69 on today's folded dev set, and four
  description variants land 0.64–0.80 inside overlapping CIs. Combined with the
  0.08 fresh-holdout baseline, the evidence says **auto-triggering is dominated
  by lexical proximity to the description; pure intent-level paraphrases rarely
  trigger under any wording measured.** Routed to the mechanism-level eval
  backlog (competition arm / trigger-mechanics, issue #54) rather than another
  rewording round.

## 0.6.4 — 2026-07-02

Nine fixes from the second (post-fix) stress-review panel — seams of the 0.6.3/
eval-harness fixes plus loop-closing gaps. Code fixes test-first. **One skill
`description` changed (context-handoff — the fake slash-command triggers were
demoted to plain words): its trigger holdout
(`evals/trigger/holdout/context-handoff.json`) must be re-validated, and treated
as spent for the next description-tuning round.**

### Fixed

- **`judge.py` double-counted repeated criterion ids.** A judge verdict repeating
  a criterion id summed its weight twice — the recomputed score could exceed 1.0
  and flip a fail into a pass. Met ids are now deduped before weighing, unknown
  ids score 0, and the score is clamped to [0, 1]. (Synced to the bundled
  evaluate-skill engine.)
- **`run_triggers.py` reported query-level CIs with no matching point estimates.**
  `recall_ci_query` shipped without `recall_query`, so a downstream consumer
  paired the POOLED point with the query-level interval — the point could sit
  outside its own CI. The report now carries `recall_query` /
  `specificity_query` (majority-fire per query, same unit as the CIs). (Synced.)
- **`holdout_check.py` mixed estimator families.** The dev pooled recall point was
  compared against the query-level interval's lower bound, tripping false
  "DROP/overfit" verdicts. `dev_recall_pair()` now picks point + CI from one
  family (query-level when the report has both, pooled otherwise), and the
  held-out point is chosen in the same unit.
- **`scan_toolkit.py` rendered YAML quotes literally.** A quoted frontmatter
  `name`/`description` kept its surrounding quotes in the inventory (6 installed
  skills rendered with a leading `"`). Matched quote pairs are stripped, `\"`
  and doubled `''` unescaped.
- **`build_feedback_index.py` was blind to §Misses/§Friction.** tool-feedback and
  feedback-triage sanction `extends <stem> §Misses` as a recurrence target, but
  the index only listed `## Proposed` items — the affordance pointed at nothing
  greppable. Flush-left bullets under `## Misses` / `## Friction` are now indexed
  as `§`-stub entries (fence-aware, severity tags stripped).
- **tool-feedback / feedback-triage invoked the index builder by a cwd-relative
  path** (`skills/feedback-triage/scripts/…`), which resolves nowhere on an
  installed plugin. Both now use the
  `"${CLAUDE_PLUGIN_ROOT}/skills/feedback-triage/scripts/build_feedback_index.py"` form.
- **feedback-triage's triage-doc rule contradicted its script.** The skill said
  H1 `# Triage —` *or* a `triage` filename; `build_feedback_index.py`
  deliberately uses H1-only (a filename test misclassifies input reports about
  the triage tool itself). The doctrine now states the H1-only rule and why.
- **context-handoff advertised `/subtask` `/fork` `/spinoff`** — none ship as
  commands, so following the skill's own invocation table dead-ends. The
  description, invocation table, and examples now use plain trigger phrases;
  `user-invocable: true` added (the skill itself is `/context-handoff`). This is
  the description change flagged above.
- **consolidate-knowledge had no default write location** — step 1 read "prior
  promoted guidance" and step 7 emitted entries, but no path existed, so each
  run re-promoted the same clusters. The durable layer is now pinned to
  `docs/journal/guidance.md` by default (a store's configured path wins),
  referenced by both steps and the no-store fallback.

### Docs

- Plugin README: added the two shipped-but-unlisted skills
  (`compaction-survival`, `corpus-review`).

## 0.6.3 — 2026-07-02

Five fixes from the #52 stress-review panel. No skill
`description` (the eval-gated trigger surface) changed, so no holdout re-seal.

### Fixed

- **`toolkit-awareness` / `scan_toolkit.py`** — the scan was blind to
  plugin-provided components: `_scan_plugins` parsed `claude plugin list --json`
  for each plugin's `installPath` but never walked the components under it, so a
  machine with ~40 plugin skills and 4 active plugin hooks still reported
  `SKILLS (2)` / `HOOKS (0)`. A new pure `_enumerate_plugin_components(name,
  install_path)` walks each plugin's `skills/*/SKILL.md`, `commands/*.md`,
  `agents/*.md`, and `hooks/hooks.json` events, tags each item with its owning
  plugin, and merges them into the per-kind sections; the table now annotates
  plugin-owned rows `[plugin]`. When the CLI or an `installPath` is unavailable,
  the output degrades to an explicit caveat ("plugin-provided components not
  enumerated") instead of a misleading bare `HOOKS (0)`. Unit-tested against a
  fixture plugin tree (no `claude` CLI required).
- **`feedback-triage` / `build_feedback_index.py`** — two parser defects minted
  phantom finding IDs. `_PROPOSAL` matched any indented numbered line and was
  fence-unaware, so a proposal's nested numbered sub-list and numbered lines
  inside fenced code blocks became extra/duplicate IDs (`stem#1` mapping to two
  titles); it now tracks fenced-code state and accepts a proposal only flush-left
  (`^\d+\.`, no leading whitespace — where the template writes them). And the
  `_SEVERITY` charset widened to `[A-Za-z0-9/-]+` so digit/hyphen tags like
  `**[P1]**` / `**[P2-HIGH]**` are stripped, not left glued to the title.
  Regression tests added.

### Changed

- **`consolidate-knowledge`** — the pipeline gains an input ledger and an
  already-promoted reconciliation, mirroring its sibling `feedback-triage`: Gather
  now reads prior promoted guidance first and records an **Inputs** scope (entry
  count / sessions / date range), and a new step 2 opens the output with an
  **"Already promoted — NOT re-promoted"** reconciliation so an overlapping re-run
  no longer re-promotes the same guidance (the durable-layer pollution the skill
  warns against).
- **`journaling-sessions` + `consolidate-knowledge`** — closed the storage
  contract between the pair: journaling now names a default journal location
  (`docs/journal/<YYYY-MM-DD>-<session>.md`, overridable by a `target_store`
  `path`), and consolidate's Gather step states it reads from there by default —
  previously journaling never said where the file went and consolidate had no
  defined place to gather from.
- **README** — the `context-handoff` line dropped the `/subtask` and `/fork`
  slash-command formatting (no such command files exist — they are only trigger
  phrases in the skill's description, so a cold user typing `/subtask` got an
  unknown-command failure) in favor of naming the trigger phrasing ("spin this
  off", "hand this off", "new session for this").
## 0.6.2 — 2026-07-02

Eval-harness correctness (from the 2026-07-02 adversarial stress panel). Fixes the
bundled `evaluate-skill` engine and `evals/harness/` in lockstep (`#49`).

### Fixed

- **`judge.py` — the LLM judge no longer inherits the user's real `~/.claude`.**
  `judge_pointwise` / `judge_pairwise` now take an isolated, skill-free `config_dir`
  (threaded from `grade_tasks` via a dedicated `config_judge`); without it the judge
  spawn loaded the user's CLAUDE.md, hooks, and installed plugins — including the
  skill under evaluation — contaminating verdicts and making them non-reproducible.
- **`grade_tasks.py` — an infrastructure failure no longer persists a fake score.**
  `main` now runs the `preflight_auth` probe before the fan-out and refuses to write
  a report when every WITH arm errored; `_summarize` excludes errored units from
  `correct_usage` and the pairwise tallies (adds `n_usage_valid` / `n_pairwise_valid`),
  so a 401/timeout no longer overwrites a real `grading.json` entry with `0.00`.
- **`grade_tasks.py` / `run_all.py` — a skill with no `evals/tasks/` suite is skipped,
  not crashed on.** `config.json` maps more skills than have grading suites; the
  grading stage now skips the missing ones cleanly instead of dying with an unhandled
  `FileNotFoundError` after the trigger stage already spent its spawn budget.
- **`run_triggers.py` / `holdout_check.py` — honest, query-level confidence intervals.**
  The pooled `recall_ci` treated correlated `query × repeat` outcomes as independent
  trials (intervals too narrow); `score_skill` now also reports `recall_ci_query` /
  `specificity_ci_query` (unit = the query, majority-fire = pass), and `holdout_check`
  consumes the query-level bound so a within-noise held-out recall no longer trips a
  spurious "overfit" verdict.

## 0.6.1 — 2026-07-01

### Fixed

- **`feedback-triage` / `build_feedback_index.py`** — a consolidated `BACKLOG.md`
  kept beside a feedback dir's reports is a loop OUTPUT (a status digest), not a
  source report; it is now excluded from the generated index by exact name, like
  `INDEX.md` and `README.md`. Previously it was counted as a report, inflating
  the report count and emitting a spurious `## BACKLOG` section. Regression test
  added.

## 0.6.0 — 2026-06-28

Structural-hardening release (from the 2026-06-28 structural review).

### Added

- **`compaction-survival`** skill (flexible) — maintain a persisted, re-readable
  control anchor so a long autonomous run survives context compaction: one file
  with the mission, a plan pointer, a live cursor, invariants, last-known-good
  state, and resume steps, updated each step and re-read each turn. Intra-actor
  state recovery, distinct from `context-handoff`'s inter-actor brief. (The
  blind cross-model panel that reviewed the 2026-06-23 triage re-homed this from
  a proposed `context-handoff` mode to a dedicated skill.)
- **`corpus-review`** skill (flexible) — audit a large file corpus by blind
  fan-out → adversarial-verify → disjoint-partition fix → re-audit to
  convergence, with an execute-the-artifact lens. Ships no engine of its own
  (orchestrates on the harness's parallel/workflow primitives; degrades to
  sequential), deliberately avoiding the bundled-script drift the eval-engine
  fix below addressed.
- Each new skill ships a calibrated description + balanced trigger dataset +
  sealed holdout under `evals/trigger/`, registered in `evals/config.json`. The
  live `run_triggers` recall/specificity gate is cost-gated; run it with
  oversight before merge.
- Sealed trigger holdouts for **`context-handoff`** and **`journaling-sessions`**
  — both auto-trigger surfaces that had a base trigger dataset but no protected
  generalization set.

### Fixed

- The bundled `evaluate-skill/scripts/` engine had drifted behind the tested
  `evals/harness/` source (it is a distribution template users copy into their
  own `evals/harness/`): `run_triggers` was missing `preflight_auth`,
  `expected_hard`/`recall_hard`, and error sampling; `aggregate` lacked
  action-discipline gating; `grade_tasks` / `claude_runner` lagged. Re-synced the
  four drifted files verbatim and added `evals/harness/test_scripts_in_sync.py`
  asserting byte-identity so the template cannot silently regress again (wired
  through `run_tests.py` → pre-push + CI). No existing skill `description`
  changed.

## 0.5.1 — 2026-06-24

Two fixes from a headless + leak-closed validation pass on the `step-digest` style.
(1) **Activation value corrected.** The plugin ships the style under its namespaced
name, so it is selected with `"outputStyle": "session-workflow:step-digest"` (or
picked in `/config`). The bare `step-digest` resolves only for a project-local
`.claude/output-styles/` file — the earlier instruction silently did nothing for
plugin installs. (2) **Doctrine tightened.** When a step produces a deliverable a
later step will reproduce or finalize (a function body, a snippet, an exact
message, a value), the digest now carries it verbatim rather than only describing
the change — a strict digest-only relay (no files crossing between steps) flagged
this as a major gap. No skill `description` changed, so no holdout re-seal.

## 0.5.0 — 2026-06-24

New `step-digest` **output style** (`output-styles/step-digest.md`) — the plugin's first
output style. It installs two communication registers while keeping Claude's coding behaviour
(`keep-coding-instructions: true`): lean working narration (brief action lines, with the
load-bearing reasoning behind a non-obvious decision and anything surprising still surfaced
mid-stream), then a fixed-field digest under a `## Digest` heading at the end of every
substantive turn (`TL;DR` / `Changed` / `Decisions` / `Verified` / `Next` / `Open`, later
fields omitted when they carry nothing). The aim: a long agent-driven run reads back from its
per-step digests instead of its full transcript. Selectable and off by default — enable with
`"outputStyle": "session-workflow:step-digest"` in user/project settings or via `/config`; not
forced over a user's other output-style choices. Design:
`docs/design/2026-06-24-step-digest-design.md` (a `SubagentStop` enforcement hook for subagent
coverage is the deferred Phase 2). New artifact — no skill `description` changed, so no holdout
re-seal.

## 0.4.4 — 2026-06-23

`review-panel` "When to convene" — name the **design/spec-before-build** case explicitly (a
qualifier on the high-stakes trigger, where pre-code defects are cheapest to catch) **with a
maturity gate**: a design is panel-ready only when concrete enough to critique (explicit
interfaces, failure modes, data flow, ≥1 worked example) — panelling a bare sketch yields
bikeshedding and false confidence, not defects. From the 2026-06-23 triage (**N19a**, reinforced
across two design-stage arcs — `2026-06-17-backlog-remediation-design-build#2` +
`2026-06-19-triage-round-review-panel#1`); a blind fresh-eyes review of the proposal added the
maturity guard. Body-only — no `description` change, so no holdout re-seal.

## 0.4.3 — 2026-06-19

`feedback-triage` index-builder (`scripts/build_feedback_index.py`) false-exclusion fix.
`_is_report` dropped any file whose name contained the substring `triage`, treating it as
a loop output — silently excluding legitimate INPUT reports from the generated `INDEX.md`:
a `tool-feedback` report *about* the `feedback-triage` tool, or a
`<date>-triage-round-<tool>` wave slug. With the report invisible to `INDEX.md`, the next
session's recurrence check (`extends`-lookup) could not see it. Observed this round: 7
`triage-round-*` reports plus the pre-existing `2026-06-14-feedback-triage-batch-run.md`,
and the keel `…-craft-triage-design-premortem.md` report, were all dropped. Triage docs are
now detected by their `# Triage` H1 (`_is_triage_doc`), not a filename substring; a report
whose slug merely contains `triage` is indexed. (`digest` stays name-based — no observed
false-exclusion.) Script + test only — no skill `description` changed, so no holdout re-seal.

## 0.4.2 — 2026-06-19

Hook `python`-invocation portability: the SessionStart toolkit-inventory hook
(`toolkit-awareness/scripts/scan_toolkit.py`) ran via a bare `python` (the
Microsoft-Store app-execution stub trap on Windows without Python on PATH). Now `uv run
--no-project -- python …` — completing the portability fix begun in 0.4.1 (the feedback
index-builder invocation). Hook-manifest only — no skill `description` changed.

## 0.4.1 — 2026-06-19

From the 2026-06-19 triage. **N18a** — the `feedback-triage` index-builder
(`scripts/build_feedback_index.py`) docstring and the `tool-feedback` /
`feedback-triage` invocation references now use `uv run --no-project python …`. A bare
`python` (or `python3`) resolves to the Microsoft-Store app-execution stub on a Windows
machine without Python on PATH and aborts — it cost a retry on each index rebuild in
the field. Doc / invocation only — no skill `description` changed, so no holdout re-seal.

Known broader scope (out of this fix, tracked separately): the plugins' `hooks.json` and
the pre-commit `lint_register` / `run_tests` entries invoke a bare `python` and have the
same failure on that setup.

## 0.4.0 — 2026-06-17

Two changes from the 2026-06-17 triage, both shaped by a fresh-eyes review panel.
Body/doctrine only — neither skill's `description` (the eval-gated trigger surface)
changed, so no holdout re-seal.

### Added

- `feedback-triage`: an **escalation rule** in the ATTACK disposition (step 4) plus a
  matching **"Re-prosing a recurrence"** anti-pattern. When a finding recurred *after*
  a fix already shipped at the same enforcement layer (≥2 post-fix reports) and its
  cause is **mechanically reachable** at the next layer, the promotion moves one rung
  down — prose → required structure → script/gate → hook → linter/CI — instead of
  re-prosing the same advice. Gated so it can't over-mechanize a judgment-bound
  recurrence (a dispatch-timing nudge, a naming call), which takes sharper prose or
  DECLINE, not a forced rung. Cross-references the existing `skill-authoring` rule
  ("a constraint that needs caps to hold needs a gate, not louder prose") so the two
  statements don't drift. (The meta-finding from this round: a class of finding that
  recurs despite shipped prose is signalling the wrong enforcement layer, not weak
  prose — e.g. the strip-on-save trap, fixed at last in the hook.)

### Changed

- `tool-feedback`: **destination resolution** folded into Workflow step 1, replacing
  the assumption that a report always lands in the tool's own repo. A report's
  destination, in precedence, is a dir the user named *this session* (a consolidated
  external sink with per-tool subdirs ⇒ `<sink>/<tool>/`) → the registered feedback
  dir → the tool's own repo; only a **named or registered** dir is resolved, never an
  inferred one (per `2026-06-17-datatools-docs-plugin-remediation-tool-feedback#2`,
  `2026-06-17-debt-engine-tool-feedback#2`). A **redirected write does not relocate
  the recurrence baseline** — when a registered binding exists, step 2 still reads
  *its* index, so a one-off sink can't sever recurrence and resurface settled findings
  (the silent-misroute bug the panel caught). Step 2 now **builds a missing `INDEX.md`
  first** rather than degrading to grep (`2026-06-17-debt-engine-tool-feedback#1`), and
  a tool the user *named* but the session never exercised gets an explicit "named but
  not exercised → no report" line, not a silent omission
  (`2026-06-17-datatools-docs-plugin-remediation-tool-feedback#3`,
  `2026-06-17-v1-publish-wheel-fix-tool-feedback#2`). The persistent-binding registry
  (`#N9c`) stays routed to the user's CLAUDE.md — a `TARGETS.md` under the gitignored
  `docs/feedback/` would not travel.

## 0.3.1 — 2026-06-15

Two watch-item refinements from the backlog; body-only, descriptions unchanged (no
holdout re-seal).

### Added

- `tool-feedback`: a proposal carries its **resolution and referents**, not just its
  question — record the clarification the session validated (or the deciding
  precedent) and name any counted objects, so the downstream lander doesn't re-derive
  or hunt (per `2026-06-09-feedback-skills-021-landing#1`, the prior triage's `#T4`).
- `evaluate-skill`: a boundary note — it evaluates one skill's triggering + output,
  not a whole plugin's end-task outcomes; a plugin-vs-plugin comparison is an
  outcome/task-bank harness (dyno-style), not this single-skill behavioral eval (per
  `2026-06-14-humble-vs-super-run#2`, the `#N7a` watch row).

## 0.3.0 — 2026-06-15

Feedback-loop ergonomics from the carried-forward 2026-06-14 triage backlog (`#T3`,
`#T5`, context-handoff `#T7`) plus the owner-tagging fix from
`2026-06-14-feedback-triage-batch-run`. Doctrine + a new stdlib script; the three
skills' `description` blocks (the eval-gated trigger surfaces) are unchanged, so no
holdout re-seal.

### Added

- `feedback-triage/scripts/build_feedback_index.py` — rebuilds a feedback dir's
  `INDEX.md` (one entry per report + its numbered proposals) so an `extends`-lookup
  is one Read instead of N phrasing-fragile greps (`#T5a`). `tool-feedback` rebuilds
  it on write and reads it in the recurrence check; `feedback-triage` rebuilds it at
  scope. Stdlib-only, unit-tested; the `INDEX.md` output is a generated, gitignored
  local artifact.
- `tool-feedback`: a **standing-directive = asked** branch — an autonomous session
  under a CLAUDE.md "run at session close" mandate treats it as asked and writes,
  instead of emitting an offer no one is present to accept (`#T3a`); and
  **maintaining a registered tool's own repo now explicitly counts as use** (`#T3b`).
- `feedback-triage`: a fan-out **owner-tagging** rule — enumerate each registered
  tool's own skills/components in a digest brief's owner taxonomy so a finding about
  tool X's own skill isn't misrouted (`2026-06-14-feedback-triage-batch-run#1`); a
  **digest-for-handoff** middle path for a tool that owns its triage flow (`#2`); and
  a **read-order convention** for same-wave `-execution`/`-authoring` pairs (`#T5c`).
- `context-handoff`: **state the INTENT behind an adaptable step**, not just the
  procedure — strongest in FORK mode, where an executor resolves novel situations in
  a step's spirit only if the spirit is written down (`#T7`).

### Changed

- `tool-feedback` recurrence check (step 2) now reads `INDEX.md` first, with grep as
  the fallback.

Deliberately not done: a committed `docs/feedback/README.md` (`#T5b`) — craft's
`docs/` is gitignored and its binding cites no format README (unlike keel's), so the
skill's own report template stays the format authority; a gitignored README would
only duplicate and drift.

## 0.2.3 — 2026-06-14

Body-only refinements to `tool-feedback` from the 2026-06-14 feedback batch
(`2026-06-13-dyno-skilleval-design-build-run`, `2026-06-14-humble-vs-super-design`
/ `-run`); the `description` (the eval-gated trigger surface) is unchanged, so no
holdout re-seal.

### Added

- `tool-feedback`: the cache-vs-working-tree note now covers **version skew in
  either direction** — the installed/cached copy can run *behind* the working tree
  (a stale install) or *ahead* of it (a newer install over an older manifest), so
  the manifest version and the executed version can disagree; record which copy you
  actually ran and flag the skew (per
  `2026-06-13-dyno-skilleval-design-build-run#5`, extending the 0.2.2
  working-tree-authoritative note).
- `tool-feedback`: a **README-fallback** rule — if a registered tool's `extras`
  cites a format README that doesn't exist in the tree, fall back to this skill's
  template and note the missing README as a maintainer gap (per
  `2026-06-14-humble-vs-super-design` §Friction, reinforced by `-run`).

## 0.2.2 — 2026-06-13

Two strands land together: body/process fixes from the three-tool digest run
(`2026-06-13-feedback-loop-multitool-run`), and trigger-surface calibration from
the feedback-loop eval remediation (`2026-06-09-feedback-loop-live-eval`,
`2026-06-10-feedback-loop-eval-remediation`).

### Added

- `feedback-triage`: reconcile-shipped (step 2) now also reads `git log` and the
  current source for a component that ships without its own CHANGELOG (an eval
  harness, a scripts dir) — its increments land as commits, so a CHANGELOG-only
  pass reads shipped work as still-open (per
  `2026-06-13-feedback-loop-multitool-run#1`; a triage subagent had filed three
  already-committed eval-harness fixes as open).
- `feedback-triage`: scope (step 1) recognizes a triage doc by a `# Triage —`
  first heading or a filename containing `triage`, not only a `*-triage-*.md`
  glob, so a house naming variant (keel's `<date>-backlog-triage.md`) is not
  silently re-triaged; the dir is listed directly rather than globbed (per
  `2026-06-13-feedback-loop-multitool-run#2`).
- `feedback-triage`: a concurrent-triage guard — note any triage doc already
  dated today at scope, and re-list the dir at emit (step 6) before writing, to
  avoid duplicating a concurrent session's triage (per
  `2026-06-13-feedback-loop-multitool-run#4`, extending
  `2026-06-09-cc-gitattributes-hygiene#2`).
- `tool-feedback`: a note that a skill under development is authoritative in its
  working-tree `SKILL.md`, not the installed/cached copy the `Skill` loader serves
  (per `2026-06-13-feedback-loop-multitool-run#3`).

### Changed

- `tool-feedback` `description`: added a clause targeting the canonical imperative
  ("write a dogfooding feedback report for keel") — the trigger measured as a miss
  (per `2026-06-10-feedback-loop-eval-remediation` Miss "canonical imperative
  0/14", `2026-06-09-feedback-loop-live-eval#3`). It is additive and
  specificity-safe, but the 2026-06-13 re-run shows it still fires 0/3 headless —
  see the eval note below; it reads as a triggering-threshold limit, not a
  description gap.
- `feedback-triage` `description`: negative space added — a governed series' own
  reflections go to the method tool's triage skill (e.g. keel's `keel-triage`),
  not this generic pass (specificity, per
  `2026-06-10-feedback-loop-eval-remediation`).
- `evals/trigger/tool-feedback.json`: swapped the journaling near-miss negative
  for a CHANGELOG/release-notes boundary negative — the spec-mandated boundary
  ("does not write CHANGELOG entries") was untested (per
  `2026-06-09-feedback-loop-live-eval#5`, `2026-06-09-pr9-premerge-gap-disposition#2`).

These are trigger-surface (`description`) and trigger-dataset changes.
`evaluate-skill` was re-run 2026-06-13 (132 spawns, ~$9): **specificity 1.00**
across dev + holdout for both skills (the new CHANGELOG-boundary negative is
correctly rejected). **Recall is inconclusive** — the trigger arm's
flail-to-error rate (~55–65%, the unshipped trigger-arm-damping residual) muddies
it; error-excluded recall is 0.89 (`tool-feedback`) / 0.79 (`feedback-triage`),
and the canonical imperative fires 0/3 (a likely triggering-threshold limit, to
flag as expected-hard rather than chase). Treat recall as provisional until the
harness damps flail.

## 0.2.1 — 2026-06-09

Wording promotions from the feedback-loop skills' first dogfood run, recorded
in `2026-06-09-feedback-skills-first-run` (craft-collection's feedback dir).
Body-only edits: both skills' `description` blocks — the eval-gated trigger
surfaces — are untouched.

### Added

- `feedback-triage`: **Promotion-gate ledger** as a first-class template
  section — the gate shows its work per cluster (cleared on reinforcement /
  BLOCKER-exempt / `watch` / raw, and why), closing with the assertion that no
  singleton non-BLOCKER was promoted; pipeline step 5 now requires it
  (per 2026-06-09-feedback-skills-first-run#1).
- `feedback-triage`: `watch` added to the status vocabulary — the middle
  disposition for an anchored-but-singleton row, parked until a second report
  corroborates it — and the BLOCKER exemption's scope clarified to the
  BLOCKER's own row: sibling rows from the same report need their own ledger
  justification or take `watch` (per 2026-06-09-feedback-skills-first-run#4).
- `feedback-triage`: the cluster-**splitting** rule named as the dual of
  collapsing — split one super-cause into separate clusters when its
  corollaries have distinct homes and distinct concrete fixes
  (per 2026-06-09-feedback-skills-first-run#3).
- `feedback-triage`: first-run base cases stated explicitly — no triage doc yet
  ⇒ the whole corpus is un-triaged (step 1); no last triage ⇒ the
  reconciliation window is the whole CHANGELOG to date (step 2); empty
  `extras` ⇒ the fallback template is authoritative (step 7)
  (per 2026-06-09-feedback-skills-first-run#2).
- `feedback-triage`: the disposition tie-breaker — route by where the fix
  lands, not where the artifact lives (step 4) — and the disk-is-authoritative
  scope note: an invocation-vs-directory discrepancy is resolved in the
  directory's favor and noted under Inputs (step 1)
  (per 2026-06-09-feedback-skills-first-run#7).
- `tool-feedback` + `feedback-triage`: the loop's two ID namespaces documented
  on both sides — report finding IDs (`<file-stem>#<n>`) vs triage promotion
  IDs (`T1a`) — and triage now explicitly follows `extends` chains when
  clustering, making capture-time `extends` refs load-bearing
  (per 2026-06-09-feedback-skills-first-run#5).

### Changed

- evals/README ("Reading the feedback-loop skills' numbers"): holdout
  interpretation note — two of `tool-feedback`'s three holdout positives are
  session-framed by design; if holdout recall drops, suspect those two before
  concluding the description fails to generalize
  (per 2026-06-09-feedback-skills-first-run#8).

Deliberately not in this release: per-task rubric support in the
`evaluate-skill` engine (2026-06-09-feedback-skills-first-run#6) — an engine
schema change, left recorded for a separate initiative.

## 0.2.0 — 2026-06-09

### Added

- `tool-feedback` skill — per-session dogfooding feedback capture for registered
  in-development tools: one report per tool used (design-only use counts), into
  that tool's own feedback directory. Unified format: keel's six sections plus
  severity tags (BLOCKER/HIGH/MED/LOW), phase attribution on misses, stable
  finding IDs on proposals (`<file-stem>#<n>`), capture-time recurrence checks
  ("extends" refs instead of restatements), and an optional cost table. Targets
  bind via a user-supplied `feedback-targets` table (ask once, never hunt).
  Offer-first when self-activated.
- `feedback-triage` skill — the downstream pass: reconcile shipped work first,
  cluster reports by underlying cause (not symptom), assign ATTACK / ROUTE OUT /
  DECLINE dispositions, apply a promotion gate (reinforced ≥2 reports — single-
  report BLOCKERs exempt — specific, actionable), and emit a leverage-ordered
  triage doc with a `proposed/accepted/shipped(version)/declined` status table.
  Defers to tool-registered triage templates (e.g. keel's reflection-triage).
  `/feedback-triage`.

## 0.1.3 — 2026-06-07

### Changed

- `toolkit-awareness`: the description now covers ownership resolution — which
  installed skill owns a given concern (a rubric, a schema, project conventions),
  so a prompt references the owner instead of duplicating it — plus narrower
  inventory questions such as which hooks are configured. Triggers eval: recall
  0.79 (FAIL) → 1.00, with 0.92 on held-out unseen paraphrases and specificity
  1.00.

## 0.1.2 — 2026-06-06

Make `journaling-sessions` output faithful to a structured memory store without
losing its store-agnostic default — every addition below is optional, and with no
`target_store` profile the output is unchanged.

### Added

- Optional `validated:` envelope field. A stress-tested DECISION now emits **both**
  the structured field (which a store filters and weights on) and the in-prose
  `VALIDATED:` marker (for the embedder); previously only the marker existed, so
  every ingested entry was `validated=None`.
- Optional `target_store` profile that binds `author` and `area` to a downstream
  store's existing vocabulary, so entries are not silently orphaned by generic
  scope keys. New `references/store-binding.md`.
- `PATTERN` entry type — the positive mirror of `ANTI_PATTERN`.
- `references/envelope-schema.json` — a versioned (`schema_version` 1),
  machine-readable envelope contract (fields, required set, enum sets) a consuming
  store can conformance-test its parser against.

### Changed

- The prose-only (no-envelope) output branch is now gated on an **explicit** "no
  store" opt-in instead of being inferred; a `target_store` profile makes the
  envelope mandatory.
- Documented `area`/`author` as downstream scope/partition keys, with an enum
  subset rule (matching value **and** case) for stores that strict-parse enums.

## 0.1.1 — 2026-06-05

### Added

- `consolidate-knowledge` skill — the downstream pass that distills many
  `journaling-sessions` entries across sessions into durable, promoted guidance
  (cluster → synthesize → promotion gate → reconcile supersession).
  `/consolidate-knowledge`.
- `review-panel` skill — convene fresh, blind, adversarial reviewer subagents on
  an artifact you've anchored on; neutral brief, structured comparable output,
  synthesis over averaging, a stakes-scaled ladder. Claude Code only; asks before
  firing. `/review-panel`.
- `evaluate-skill` skill — behaviorally evaluate a skill by running it headless
  many times: triggering (recall / specificity), correct-usage (rubric judge),
  and a with/without baseline, each with Wilson 95% CIs. Ships the eval engine in
  `scripts/`. Claude Code only; cost-gated. `/evaluate-skill`.

  These three landed on 2026-06-04, after the initial-release docs were written,
  and shipped in the `0.1.1` tag — recorded here to match.

### Fixed

- Corrected the `repository` URL to `grimaldost/craft-collection` (the previous
  `grimaldo-stanzani` owner did not resolve).

## 0.1.0 — 2026-06-04

Initial release.

- `journaling-sessions` skill — generic core + on-demand references, with an
  automatic internal multi-pass loop (replaces the old manual "do another pass").
- `context-handoff` skill — generalized for any fresh context (new session,
  spawned task, teammate, issue); SUBTASK and FORK modes.
- `toolkit-awareness` skill — live `scan_toolkit.py` inventory + durable guidance
  on referencing the toolkit in prompts; optional inert SessionStart inject hook.

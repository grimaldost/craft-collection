# Changelog — engineering-discipline

All notable changes to this plugin are documented here. Bump the `version` in
`.claude-plugin/plugin.json` with each release.

Tags start at 0.5.0; earlier versions were released before this plugin's releases were
tagged.

## [0.6.1] - 2026-10-08

A false block in the uv hook, a README claim no gate backed, a local firing counter for
both hooks, and a word ceiling on the data skill's references. No SKILL.md body changed:
data-engineering-discipline stays at 2312/2312, python-engineering at 2314/2314 and
refresh-stack at 484/484.

### Fixed

- **`uv_enforce` no longer blocks a heredoc that writes a blocked word as data.** A PR
  body written with `cat > b.md <<EOF` holding a markdown table was blocked: the row
  `| virtualenv | 21.3.0 |` put `virtualenv` at a command position after the row's
  leading pipe. A heredoc body is now skipped when two things hold: its operator line is
  one simple command (outside quotes, no `;`, `&`, `|`, parentheses, braces, `$(` or
  backtick, and no trailing backslash) whose program is `cat`, `tee`, `git` or `gh`, past
  any assignments and redirections; and the body cannot run code (a quoted or
  backslashed delimiter, or no `$(` or backtick in the body). The terminator is the exact
  word on its own line (leading tabs dropped after `<<-`; a CR ignored), several heredocs
  on one line are read in order, and an unterminated body runs to the end of input, as
  in bash. Every other heredoc is scanned as in 0.6.0, so a body fed to a shell, an
  interpreter, a pipe, a loop or a substitution still blocks, and the walk stops
  stripping at a line that leaves a quote open or ends in a backslash. The rule is
  fail-closed by design: a data-only heredoc of another shape (`body=$(cat <<EOF`,
  `cat <<EOF | grep x`, `sudo tee`) is still scanned, so a table row like the one above
  still blocks there; writing it as `cat > file <<'EOF'` avoids that. The block message now names the matched words
  (``Blocked `virtualenv`.``); `verdict()` still returns `'block'` or `'allow'`, and the
  new `blocked_match()` returns the words. Displaces: nothing (the README PreToolUse
  bullet; no SKILL.md body words). (2026-10-07 maintenance triage.)
- **The READMEs no longer say the data checks run in this project's gates.** The
  plugin README said the runnable data checks were wired into this project's pre-commit
  and CI gate, and the root README said they were already in the gates; neither
  `.pre-commit-config.yaml` nor the validate workflow runs them, only their unit tests.
  Both now say the seven data scripts exit non-zero on a finding and that a project
  wires them into its own CI.
  The 0.4.0 entry below keeps its original wording as the dated record. Displaces: the
  false sentence, reworded in place. (2026-10-08 release review.)

### Added

- **A local firing counter for both hooks.** A new stdlib module, `hooks/hook_log.py`,
  appends one JSON line per firing to `hook-log.ndjson`: `uv_enforce` on each block
  (`ts`, `hook`, `verdict`, `matched`, `session`), `ruff_format` on each format run it
  starts (`ts`, `hook`, `files`, `session`). No command text, file path or file content
  is written, and nothing is sent over the network. The directory is
  `ENGINEERING_DISCIPLINE_STATE_DIR` when set, else `CLAUDE_PLUGIN_DATA`, else
  `engineering-discipline` under the system temp directory. Appending stops at
  1,000,000 bytes, and every write error is swallowed, so `uv_enforce` still exits 2 on
  a block and `ruff_format` still exits 0. Only the hooks' `main()` functions log, so
  `verdict()` and `harness_adapters` never write the log. `python hooks/hook_log.py`,
  run with the same state-directory variables the hooks saw, prints the firings per
  hook and skips any line it cannot read. There is no opt-out variable. Every
  test that runs a hook's `main()` points the state directory at a temporary directory.
  Displaces: nothing (a README paragraph, a sentence each in the `hooks.json`
  description, the root README and SECURITY.md; no SKILL.md body words). SECURITY.md also
  drops its claim that the other plugins' hooks are off by default, which the root
  README's Hooks table contradicts.
- **A word ceiling on `data-engineering-discipline/references/`, at 18,319 words.**
  `scripts/word_budget.py` counts every `.md` file under a recorded `references/`
  directory (recursive, with the same counter as SKILL.md bodies), and
  `scripts/validate_plugins.py` fails when the count passes the ceiling in the new
  `scripts/reference_budget.json`, naming the directory, the count and the ceiling. A
  recorded directory that is missing or holds no `.md` files fails too. The ceiling is
  today's count, so any growth needs a reviewed bump that names what it displaces.
  `word_budget.py --report` lists the directory below the skill bodies. Displaces:
  nothing (one sentence in CONTRIBUTING.md; no SKILL.md body words).

## [0.6.0] - 2026-10-07

Hook scope change and a new parity_check flag. The compaction-summary bullet replaces
the over-broad re-read-at-each-phase framing; the parity check gains a new refusal reason
and an `--allow-empty` flag; the format hook narrows which files receive turn-level formatting.

### Fixed

- **`parity_check.py` no longer passes two empty tables**: header-only CSVs (or a filter
  that empties both sides) printed `PARITY OK` and exited 0, although the docstring and
  SKILL.md said an unassessable comparison is never a pass. `compare()` now returns
  `ok=None` with the reason `empty population: two empty tables match and prove nothing`;
  the CLI prints `PARITY NOT ASSESSED` and exits 1, and its hint names the opt-out that
  matches each reason. New flag `--allow-empty` (keyword `allow_empty` on `compare()`)
  accepts two empty inputs when an empty result is the expected outcome. One empty side
  still fails on the row-count delta. Recipe 13 now names this refusal and says a
  hand-written judge gates every relation-level check on a non-empty population first.
  Displaces: nothing (a one-clause pointer in the recipe; no SKILL.md body words).
  (2026-10-06 delta triage: T140a.)

### Changed

- **The end-of-turn format hook formats only files in a project that declares ruff.**
  Before, `hooks/ruff_format.py` ran `uvx ruff format` on every `.py` file a Write or
  Edit touched, wherever it lived: it rewrote whole files in a repository not formatted
  with ruff, and broke the recorded sha of a frozen file on its first edit. Now a file
  is formatted only when a `ruff.toml`, a `.ruff.toml`, or a `pyproject.toml` with a
  `[tool.ruff]` or `[tool.ruff.*]` table sits in its directory or an ancestor, up to
  and including the repository root (the directory holding `.git`). A `pyproject.toml`
  without a ruff table does not end the walk, so a monorepo subpackage under a root
  `ruff.toml` still formats. What stops being formatted: files outside any project,
  and files in a repository with no `ruff.toml`, `.ruff.toml` or `[tool.ruff]`. A
  project that uses ruff only through a dev dependency or pre-commit, with no config,
  loses end-of-turn formatting; adding an empty `[tool.ruff]` table opts it back in.
  An unreadable or malformed `pyproject.toml` counts as no declaration: nothing is
  formatted, nothing is printed, and the hook still always exits 0. The legacy
  single-file payload and `harness_adapters.format_decision` apply the same scope, so
  other harnesses keep identical semantics. Displaces: the unconditional format of
  every edited file, reworded in place in the README PostToolBatch bullet and the
  `hooks.json` description; no `data-engineering-discipline` body words. Only a
  `[tool.ruff]` table header
  counts as a declaration in `pyproject.toml`: ruff's other valid spellings (`[tool]`
  with a `ruff` dotted or inline key, a quoted `[tool."ruff"]`) are not detected, so
  such a project is not formatted; pinned by a test. The `python-engineering`
  SKILL.md enforcement sentence now says the hook formats each edit in ruff projects
  (displaces "as it happens"; word-neutral, 2314/2314). (2026-10-06 delta triage: T141b.)
- **scenarios.md Step 4.3 "Identify all consumers"**: replaces "Enumerate every
  notebook, dashboard, downstream pipeline, export, or report" with a census rule
  and method (a consumer list you read is a claim; one you enumerated is evidence).
  Adds a new Watch for section naming two consumer failure modes. The Cross-scenario
  notes section gains two rules: run each producer's exact statement against the real
  store (not a stand-in), and a count step asserts its count against an independent
  enumeration. Displaces: the named enumeration opening, replaced by the rule and
  method. Reference prose only; SKILL.md body stays at 2312 words. (2026-10-06 delta
  triage: T72c, T72e, T73b, T73c.)
- **Recipe 18 "Versioning a frozen judge" in `parity-recipes.md`, with a pointer from
  SKILL.md Oracle integrity**: after a red, repairing the judge is admissible only as
  a new judge version in its own change by the judge's author, at least as strict
  where the contract cares, with a self-test that keeps every earlier planted bank and
  adds an intended-effect pass and a planted-loss fail, and a freeze file that appends
  version, reason and sha with old and new verdicts shown side by side. The recipe also
  carries the stale-surface rule: a verifier that reads a shared surface is re-run when
  that surface's producer changes, with its own scratch state removed first. The
  strictness table gains a row. Displaces: the body's "with the reason" becomes the
  pointer "parity-recipes Recipe 18" (word-neutral, body stays at 2312 words); the
  stale-surface rule lands as reference prose with no body words. (2026-10-06 delta
  triage: T141a, T72d.)
- **`data-engineering-discipline` SKILL.md source-of-truth bullet**: the "For a long
  session" prose at non-negotiable 2 (source of truth) is replaced with guidance for
  fact-checking under pressure: a fact from a compaction summary, an anchor, or an
  adversarial reviewer must be re-measured before coding, not assumed. Displaces: "For
  a long session: re-read the primary sources at each phase. Don't trust the session
  summary." (word-neutral, 2312/2312). (2026-10-06 delta triage: T75b.)
- **Recipe 9 "Constraint pre-flight against production data" in `parity-recipes.md`**:
  the recipe is rewritten to measure the premise at the grain of the change before
  design is committed. Before relaxing a constraint, count nulls for all mandatory
  columns, not only the columns the first failing quarantine reason names. Before
  trusting a switch is inert, run the fixture with and without it and diff what it
  wrote, refusing a pass when either run failed or both wrote nothing. Displaces:
  the header comment from "Run before declaring" to "Run before declaring or relaxing";
  adds a new subsection with fixture-diff example (Python). (2026-10-06 delta triage:
  T142a.)
- **Principle 9 and new Recipe 19 "Capture a producer's output as a fixture"**: a
  fixture or check target that stands in for a producer, whether its output (a CLI
  table, a log line, an API envelope) or its address (the interface it binds, the view
  it answers on), is a measurement taken from the producer, including the shapes where
  a field is empty; it is not a value chosen beside the parser or read from the
  producer's name. Principle 9 gains one short example of each half. Recipe 19 gives
  the method: a scratch instance of the producer, each output shape provoked, verbatim
  capture with the date and producer version, the scratch deleted. The strictness
  table gains a row. Displaces: the how-to half of Principle 9's mechanical-defense
  sentence ("sampled directly from production") moves into Recipe 19, and Principle 9
  now points there, so the method is stated once. Reference prose only; SKILL.md body
  unchanged. (2026-10-06 delta triage: T72a, T89a, T72b.)

## [0.5.1] - 2026-09-19

The `python-engineering` recommended stack still pinned `ruff-pre-commit` to
`v0.15.7`, the version the collection's own `.pre-commit-config.yaml` had
already moved past to `v0.16.8` — a scaffolded project or a `check_versions`
run against the current `stack.toml` both quoted a rev the collection no
longer runs itself. Patch bump, no other behavior change.

### Changed

- **`python-engineering/stack.toml` and `scaffold.py`** — `ruff-pre-commit`
  moved from `v0.15.7` to `v0.16.8`, matching this repo's own pin. Guarded by
  two new regression tests (`test_scaffold.py`,
  `test_check_versions.py`) so the two copies cannot drift silently again.

## [0.5.0] - 2026-08-11

`data-engineering-discipline` vNext: a re-tiering with three new rejecting
checks. Every word now sits in a cost tier and earns that tier by passing that
tier's test; every growth names its displacement. Body 2736 -> 2312 words with
the `word_budget.json` ceiling ratcheted to **2312 — the measured count, zero
headroom**, because a ceiling with slack in it buys a future append that never
has to name what it displaces; references 28,759 -> **16,546** (`wc -w` over
`references/*.md`, the same method as the 28,759 figure); scripts 4 -> 7 plus a
mutation harness; description 223 -> 243 words, itemised under Changed.

### Added

- **`producer_census.py`** and **`parity_check.py --two-producer A B
  --join-key K`** — the corpus's only HIGH finding, as checks rather than
  prose. A contract column written by two producers that were never run
  together is a finding; the two-producer mode asserts the JOIN before
  asserting any value, because a dtype or rendering mismatch drops rows and a
  comparison over the survivors reads clean. Producer-local suites structurally
  cannot see this, and a shared column belongs to no seam, so the scoped-change
  lane's correct application keeps the gap open. Body gains a bright line;
  `parity-recipes.md` gains Recipe 16.
- **Parity numerics**, unlanded since July: `--null-mismatch` (key-aligned null
  PLACEMENT, on by default, answering to the same `--null-tol` knob as the null
  rate), `--tol-col NAME=ATOL`, and `--residual-zero NAME`, which reports a
  residual column as a cardinality hazard rather than a value one. Recipe 17.
- **`which_copy.py`** — `__file__` plus the installed version, exit 1 when a
  checkout shadows an installed distribution. Prose since 0.1.5; fired in two
  sessions. The Axiom-2 sub-bullet becomes a pointer.
- **`mutate_check.py`** and `test_mutate_check.py` — perturb one column, assert
  the named check reddens. A mutation a check documents it cannot see is
  declared a known gap, so the pin breaks in both directions. **Stated at its
  real reach:** the runnable `--check` surface is two checks (`parity`,
  `schema`); `contract_check`, `freshness_check` and `producer_census` are held
  against the same fixtures by the paired TEST MODULE, not by the CLI; the
  `schema` arm mutates a harness-local coarse schema rather than
  `schema_diff.py`'s pandas dtype path; and `which_copy` is in neither, having
  its own unit test. So: five of six shipped checks held red by the test suite,
  two invocable through the tool.
- Body: the cross-producer bright line; grain, fanout and `DISTINCT`-as-fanout-
  repair; time semantics across joins; replay against a mutated source; and two
  plain-declarative rails — the oracle is not edited in the change it judges,
  and irreversible operations are proposed rather than executed, with the plain
  statement that this skill's force is advisory and a prompt rule is not a gate.
- `contract-templates.md` gains the compatibility-mode table (including the
  transitive variants and `NONE` as a configured fail-open gate) and the note
  that no independent adoption survey exists. Factual currency, no behavioral
  claim.

### Changed

- **The description — three changes, not one.** (1) The `writing tests for a
  pipeline` trigger measured 0.33 recall despite being explicitly enumerated; it
  becomes "writing or changing the tests, fixtures, or expected values that gate
  a pipeline", which names the oracle no sibling claims. (2) A schema-as-data
  ruling is added as negative space: such a document counts when code is
  generated from or validated against it, not when its only consumers render it.
  (3) One parenthetical example is cut to pay for it. 223 -> 243 words. An
  earlier draft also deleted the closing `If so, this skill applies — pin the
  contract, verify the observable source, and check parity on real data` clause;
  that deletion was not authorised, the net +1-word figure hid it, and it has
  been reverted, because the single sanctioned holdout read cannot attribute
  movement across four simultaneous edits. All three land as one change buying
  one holdout reseal.
- **MEASURED, and (1) did not work.** The dev pass and the sealed holdout were
  both bought on 2026-08-11 (105 spawns, $9.97) and the row is filed in
  `evals/trigger/holdout/BASELINES.md`. The pre-registered gate for (1) was
  1/3 -> 3/3 on `Write tests for the billing aggregation pipeline so a bad
  change can't ship silently`; it measured **1/3 on three valid runs with zero
  errored positive runs — no movement**. Dev recall 0.82 [0.66, 0.91] and
  specificity 1.00 [0.90, 1.00] both clear their gates, but recall on the
  byte-identical fixture was 0.939 before the edit, and two other positives
  regressed. That decline is descriptive only (Fisher exact p ~ 0.26, runs
  clustered by query), so it licenses no revert — it licenses **not claiming
  (1) as a fix**. (2) fares better and is bounded: on its three sealed cases the
  ruling is decidable but not uniform — one positive fires 3/3, the other misses
  0/3, the negative correctly stays silent, n = 1 query per outcome. The one
  genuine generalization row on this surface, the 0.1.15 intent paraphrase,
  fires 3/3.
- `contract_check.validate` raises on a contract shape it cannot read. A nested
  `{"columns": {...}}` contract iterated to zero recognised rules and returned
  an empty violation list — a green contract check over rows that violate it.
  Found by the new mutation harness.

### Removed

- `references/glossary.md` and `references/community-practices.md`, and the
  dbt / Pydantic / JSON Schema renderings in `contract-templates.md`. Zero
  citations across fourteen exercise reports; a current model reconstructs all
  of it; and the tool survey had no refresh mechanism, so retiring it is also
  the stale-pointer fix rather than a refresh that would go stale again.
- `llm-failure-modes.md` Modes 1-8 (zero citations, generic LLM hygiene), and
  `principles.md`'s replayability and schema-evolution groups — each file's own
  head note carries the destination.
- `scenarios.md` Section 1, the new-dataset playbook, which had been the one
  retirement here with no replacement written down. It has one: the body covers
  that case directly (the contract-is-the-spec line and the new-dataset
  checklist item) and `principles.md` applies every principle group to it under
  a `New dataset:` bullet, so the playbook was a second definition site. Section
  numbering is unchanged and the file now says so, since sections are cited by
  number and the first heading is `## 2`.
- Body: `## When to invoke` and `### How to use this skill in practice`, which
  restated the description and the checklist; `## Make the discipline visible
  in your output`, whose four positive directives are replaced by two negative
  rails; the observability group, whose content survives as the
  `freshness_check.py` invocation in the body and as `principles.md` Group 7
  (lineage and observability); and the five contract checkboxes, which
  become the invocations that execute them.
- Two closing paragraphs, cut in the same pass and named here for the ledger:
  Axiom 2's note that it "replaces the migration-specific framing of legacy is
  the source of truth" (the skill narrating its own edit history to the reader
  who has to pay for those words), and Axiom 4's closing list of mechanical
  defenses, which enumerated the references table three sections above it.

### Moved

- `llm-failure-modes.md` Modes 9, 10, 12 and 13 — fabricated telemetry,
  confabulated anchors, silence read as status, fail-open tooling — to
  `humblepowers:verification-before-completion` as
  `references/evidence-fabrication.md`. None is about data; the clearest
  recorded instance of the fail-open mode diagnosed a defect in an eval
  harness. Modes 11 and 14 stay, and the numbering is unchanged so older
  citations still resolve.

## [0.4.0] - 2026-08-11

Backlog wave 1. The hook rule for the whole collection: a hook ships on with a
documented opt-out, or it does not ship. A hook whose gate nobody sets has never
run, which reads as enforcement in the manifest and is absent in the session.

### Removed

- **The data pre-shipping checklist Stop nudge** (`stop_nudge.py`, its test, and
  its `hooks.json` registration; `DATAENG_CHECKLIST_NUDGE` is gone). Exhortation
  delivered through a hook, inert behind an unset variable, and its path globs
  (`models/*`) would have matched ORM and ML model directories the moment it
  fired. The four runnable data checks already wired into this project's
  pre-commit and CI gate reject rather than remind. (CRAF-B47)
- **The plugin-local trigger dataset** under `evals/`. It used a schema the
  shipped runner validates as invalid (no `should_trigger` key), had no consumer,
  and carried 6 cases against the 22 in `evals/trigger/`, which is the single
  source. (CRAF-B49)

### Changed

- `harness_adapters.parse_json_payload` no longer reaches through to the retired
  module's private `_load_payload` — the coupling the seam existed to prevent.
  The six-line tolerant JSON read is inlined.
- The README states that both remaining hooks are unconditional, and why there
  is no third one.

## [0.3.0] - 2026-07-23

### Fixed

- **`ruff_format.py` moved from per-call `PostToolUse` to turn-level
  `PostToolBatch`, closing the strip-between-batched-edits race (3+ recorded
  recurrences).** Formatting the first of two batched edits before the second
  applies invalidates the second edit's `old_string` match. `PostToolBatch`
  fires once per assistant turn, after all of that turn's `PostToolUse` calls
  (a batch of one still fires it), so the format now runs once at the end of
  the turn instead of racing the edits themselves. The hook accepts both
  payload shapes: the batch shape (`tool_calls: [...]`) collects every
  `Write`/`Edit` call's `.py` path, dedupes preserving first-seen order, drops
  non-`.py` and no-longer-existing paths, and formats all survivors with a
  single `uvx ruff format p1 p2 ...` invocation; the legacy single-payload
  shape (a top-level `tool_input`, from a manual invocation or an older
  `PostToolUse` registration) keeps working unchanged. Format-only doctrine
  unchanged — `ruff check --fix` is still never run per-edit.
  `hooks.json`'s `PostToolUse` registration for this hook is removed outright
  (not left in place alongside `PostToolBatch`), since keeping it would
  preserve the race. **Caveat: `PostToolBatch` requires CLI >= 2.1.218.** On
  an older CLI the event never fires, so per-edit auto-format stops firing
  entirely (there is no PostToolUse fallback registered), and the
  pre-commit/CI gate is the floor until the CLI is upgraded.

### Added

- **`uv_enforce.py` covers the PowerShell tool and the Windows py-launcher.**
  `hooks.json`'s `PreToolUse` matcher is now `Bash|PowerShell` (the PowerShell
  tool carries the same `tool_input.command` field, including `;`-chained
  commands). Two new command-position arms block `py [-3[.N]] -m pip install`
  and `py [-3[.N]] -m venv` — the py-launcher is the same interpreter-form
  act as `python -m pip install` / `python -m venv` under a different name.
  The existing command-position anchoring keeps `uv pip install`, quoted
  mentions, and words merely ending in "py" (`numpy`, `happy`) unmatched.

## [0.2.0] - 2026-07-16

### Changed

- **Enforcement ladder wording (multi-agent portability).** python-engineering's
  pre-commit section and the README's Hooks section no longer assume act-time
  hooks fired: enforcement is stated as the ladder — act-time on Claude Code,
  commit-time via the exported pre-commit floor (`check-uv-hygiene` +
  `adapters/pre-commit/craft-floor.yaml`), else advisory. refresh-stack and
  data-engineering-discipline verified already harness-neutral (no edit).
  Word-budget baseline bumped for python-engineering (+53 words): the growth
  displaces nothing — it names the degradation tiers where the text previously
  implied a hook.

### Added

- **hooks/harness_adapters.py** — harness-agnostic entry points wrapping the
  tested hook cores in place (format_decision, bash_verdict, block_message,
  parse_json_payload) plus thin Claude Code payload adapters; the seam for
  other harnesses' hook systems (ADR-0003).

## [0.1.15] - 2026-07-14

Build round for the 2026-07-14 craft triage (rows T16, T17, and DED1). A
consumer-contract-breaking DataHub emitter shipped because the discipline was
never selected — its trigger surface did not claim "a metadata/catalog emitter
with a downstream consumer"; this wave names that case and the tool/API-payload
case, and gives bounded changes a scoped lane. Body + reference + `description`
edit — the `description` change carries a holdout reseal obligation.

### Changed

- **`data-engineering-discipline` triggers name non-tabular consumer contracts
  (T16a).** The frontmatter `description` and the "When to invoke" list now name a
  metadata / catalog / lineage emitter whose output a separate tool loads, and a
  tool / API response payload a client depends on; the activation test adds the
  fields/types/closed-vocabularies of a payload. Non-negotiable #3 extends parity
  to "the emitted contract loads and validates in the real consumer (or a
  producer-owned encoding of it)." (`dc-reconciliation-ed §Misses/#1`,
  `dc-v4-cycle#1`.) **Holdout reseal:** the `description` edit changed the trigger
  surface; three fresh cases were sealed into
  `evals/trigger/holdout/data-engineering-discipline.json` (two positive
  emitter/payload, one over-fire guard) and `BASELINES.md` records a pending
  recall/specificity A/B against the pre-0.1.15 description. Not run this pass
  (cost-gated); the prior 7 cases are spent dev data.
- **`references/scenarios.md` gains a tool/API-payload contract row (T16b),**
  mapping columns→payload fields, dtypes→field types/closed vocabularies,
  consumers→client tests + recorded eval expectations + stubs; parity means the
  payload validates in the real client. Extends the N31a library-API-change row.
- **A front-loaded "Scoped-change lane" section (T17a),** mirroring
  python-engineering's edit lane: a bounded change to one transform/seam pins the
  contract for *that* seam and runs only the parity/real-data checks that touch it,
  skipping the full-migration apparatus — the four non-negotiables still hold for
  the seam. (`v19-ed#1`; the over-load-for-small-work cause is a 4-report chain
  whose python-engineering half already shipped.)
- **`references/llm-failure-modes.md` Mode 12 gains an observer-vs-target probe
  line (DED1):** a watcher reporting the world gone may be reporting its own
  instrument broken (a git-bash `/c/...` path handed to a Windows interpreter) —
  probe the observer with a known-present path first. A defense line within an
  existing mode, not a new mode.
- Word budget re-seeded: data-engineering-discipline 2544→2736 (the scoped lane,
  the emitter trigger/parity lines, the scenarios resource row; no clause retired).

## [0.1.14] - 2026-07-05

Corpus-review doc-accuracy round (PR #74) plus the post-merge consistency pass
(2026-07-05 polish session: blind audit + fresh-eyes round 2). Docs only; no
skill `description` changed.

### Fixed

- README: `freshness_check.py` added to the data-engineering scripts list
  (shipped 0.1.6, never listed), and the PostToolUse hook entry corrected to
  **format-only** — it still claimed `ruff format` + `ruff check --fix`, but the
  `--fix` half was deliberately removed per-edit (it strips an import added in
  one edit before a later edit uses it); hooks.json, `ruff_format.py`, its test
  guard, and CONTRIBUTING already said so — the README was the lone outlier.
- python-engineering SKILL: `httpx` row added to the Canonical Stack table
  (pinned in `stack.toml`, endorsed in `ecosystem_rationale.md`, absent from
  the table).
- references/security.md: pip-audit installs into the `security` dependency
  group (was `dev`), matching `scaffold.py` and `project_templates.md`.
- references/currency_review.md: After-the-Review checklist rewritten for the
  `stack.toml` era — pins live in `stack.toml` (SKILL.md carries none), and
  `check_versions.py` reads its tool list via `load_tools()` (the "TOOLS dict"
  it told reviewers to update does not exist).
- references/project_templates.md: `uv_build` unpinned in the build-system
  template, matching `scaffold.py`'s output and the template's own
  "`uv init --lib` default" prose.
- marketplace.json (repo-level): description synced to plugin.json
  ("toolchain manifest").

## [0.1.13] - 2026-07-05

Triage row N31a (2026-07-05 craft triage): the schema-evolution guidance is
discoverable from the eager body for non-tabular contracts. Two arcs re-derived
by hand what `scenarios.md` already covered — a library API change (tu-v12) and
an append-only JSONL event log (convoy telemetry) — because the eager body's
examples were all columns/dtypes. Body + reference edit; no skill `description`
changed.

### Changed

- `data-engineering-discipline` SKILL.md: the "Scale to the change" additive
  example and the `scenarios.md` index row now name the non-tabular shapes
  (event types, enum values, API fields) alongside columns, so a
  non-tabular-contract author recognizes the existing playbook applies.
- `references/scenarios.md` Step 2.1 gains the **library API change** row: a
  new symbol or default-preserving overload is additive; a new raise/guard on
  a previously-silent path is breaking, whatever the docstring says.

## [0.1.12] - 2026-07-03

### Changed

- `data-engineering-discipline` reference (`scenarios.md`): the schema-compatibility
  mode values are now code-formatted (`` `BACKWARD` ``, `` `FORWARD` ``, `` `FULL` ``,
  `` `NONE` ``) — correct markdown for literal enum values, and it clears the
  register linter's all-caps-run check now that the linter runs marketplace-wide.

## [0.1.11] - 2026-07-02

Seam fixes from the second (post-fix) stress-review panel: five confirmed defects
sitting at the edges of the 0.1.10 fixes, each fixed test-first. Hooks / scripts
only — no skill `description` changed, so no holdout re-seal.

### Fixed

- **`uv_enforce.py` regression: `python -m pip install` no longer blocked.** The
  0.1.10 command-position anchoring left the module form unmatched (the interpreter,
  not `pip`, sits at the command position). A dedicated `python -m pip install` arm
  restores the block; `python -m pipx install` stays allowed.
- **`uv_enforce.py` comment stripping ate real commands.** Any `#` started a
  "comment", so `curl url#frag && pip install z` had its tail stripped and escaped.
  A `#` now starts a comment only at the start of a word (input start or after
  whitespace), matching bash; `url#frag` stays scannable.
- **`contract_check.py` enum⇄dtype contradiction.** The 0.1.10 str-normalized enum
  rejected `'1.0'` on a column whose `dtype: 'int'` accepts it (integer-valued
  rendering). Enum membership now compares on a canonical numeric form (`'1.0'` ==
  `'1'` == `1`; exact-int path preserves big-int precision); non-numerics and bools
  still compare as plain strings.
- **`parity_check.py` non-finite poisoning.** Literal `nan`/`inf` cells pass
  `float()` and poison sums (`nan - nan = nan` fails every tolerance), so identical
  tables FAILED. Non-finite values are now treated as non-numeric (excluded from
  sums), and the `ok` verdict explicitly requires finite deltas.
- **`parity_check.py` typo'd `--keys` neutered cardinality.** A key column absent
  from both tables made every row key `(None,)`, collapsing both sides to
  cardinality 1 == 1 — the check vacuously passed. `compare()` now raises
  `ValueError`, and the CLI exits 2 (usage error, distinct from parity-fail 1).

## [0.1.10] - 2026-07-02

Mechanical-layer bug fixes from the GitHub issue #51 stress-review panel — nine
confirmed false-pass / false-block defects in the hooks and runnable scripts, each
fixed test-first (a reproducing test added and watched fail before the fix). No
skill `description` changed (hooks / scripts only), so no holdout re-seal.

### Fixed

- **`uv_enforce.py` false positives.** A mere *mention* of `pip install` — inside a
  quoted string (`grep -rn "pip install" docs/`), a commit message, a heredoc, or a
  `#`-comment — was exit-2 blocked. Blocked installers now match only at a plausible
  command position (start of string, or after `&&` / `||` / `;` / `|` / `$(` / a
  newline), and quoted regions and `#`-comments are stripped before matching.
- **`uv_enforce.py` false-blocked `uv pip install`.** uv's own pip interface was
  caught by the bare-`pip install` rule; a negative lookbehind for `uv ` now allows it.
- **`stop_nudge.py` never reached Claude.** It printed the nudge to stderr on exit 0,
  which the Stop-hook contract discards. It now emits `{"decision":"block","reason":…}`
  as JSON on stdout (exit 0) and guards against re-triggering itself by honoring
  `stop_hook_active` in the payload. Still inert unless `DATAENG_CHECKLIST_NUDGE=1`.
- **`parity_check.py` null-rate false pass.** A single `--tol` gated both sum and
  null-rate deltas, so `--tol 1.0` made null-rate checking inert (a column going 100%
  NULL passed PARITY OK). A separate `--null-tol` (default 0.0) now gates null-rate
  independently of the sum tolerance.
- **`schema_diff.py` false "schemas match".** (a) Without pandas it inferred no dtypes
  yet still printed "schemas match", hiding an int→str retype; it now prints a loud
  "dtype comparison SKIPPED (pandas not installed)" and exits 2 when columns match but
  dtypes were unchecked. (b) The hardcoded `nrows=1000` sample is replaced by a full
  read by default, with an explicit `--nrows` cap — a retype that only appears in later
  rows is no longer missed.
- **`contract_check.py` numeric-enum false fail.** An integer enum (`[1, 2, 3]`) flagged
  every valid CSV value because the raw string `'1'` was tested against int members.
  Both sides are now normalized to `str` before the membership test.
- **`freshness_check.py` `--max-lag` broken for temporal cursors.** `--max-lag` was
  `type=float`, so a date/datetime cursor computed `timedelta <= float` → TypeError →
  a false "STALE: uncomparable (tz-aware vs naive?)". A numeric `--max-lag` is now
  interpreted as a number of DAYS for a temporal cursor, and the misleading tz reason
  string is corrected.
- **`doctor.py` comment-scan false pass.** Checks were raw substring scans over the whole
  `pyproject.toml`, so a project documenting "we do NOT use pip-audit; quote-style is a
  TODO" in comments scored 6/6. `pyproject.toml` is now parsed with `tomllib` (raising
  doctor's floor to 3.11, matching `check_versions.py`) so comments no longer satisfy the
  uv / ruff-single-quote / dependency-groups / pip-audit checks.
- **`check_versions.py` failed open.** Any fetch error set `behind=False`, so a total
  network failure reported `behind_count=0` ("no drift"). The `--json` output gains an
  `errors` count and the tool exits 2 when any fetch failed — an unknown result is
  distinguishable from a clean stack *for consumers that read `errors` or the exit
  code* (a caller that only reads `behind_count` still sees "no drift").

## [0.1.9] - 2026-06-28

From the 2026-06-28 structural review. No skill `description` changed (body /
references / scripts only), so no holdout re-seal.

### Changed

- `data-engineering-discipline`: a consolidated "a producer can look verified and
  still mislead" table under Axiom 2 (wrong layer/version · build on a behavior
  the code doesn't deliver · read the reasons not the verdict · measure a
  paper-defined subgroup on real data) with a decline-on-recurrence cap — the
  last prose increment for this judgment-bound axiom. New `parity-recipes.md`
  Recipe 15 (differential-baseline: the stash-test and the base-commit set-diff)
  for proving net-zero regression in a noisy suite. Recipe 13 / Scenario 8.2 now
  cross-link `verification-before-completion`'s red-before-green. (The Axiom-2
  re-elaborations across `principles.md` / `llm-failure-modes.md` were assessed
  for consolidation and left — each carries a distinct anti-pattern/corrective,
  so they are layering, not redundancy.)
- `python-engineering`: SKILL.md trimmed 459 → 396 lines — the inlined
  `[dependency-groups]` TOML moved to its home in `project_templates.md`, the
  duplicated uv-command list de-duped, the `Settings` example and ruff-migration
  notes compressed, the Reference Files list collapsed to a compact index. No
  rule lost.

### Added (mechanize)

- `scaffold.py` emits a `uv run ty check src` CI step (ty has no pre-commit hook).
- `stop_nudge.py` names `freshness_check.py` for incremental-load changes.
- `uv_enforce.py` also blocks `poetry update` / `pipenv` / `conda install`
  (word-bounded; the `CLAUDE_ALLOW_PIP` escape hatch is intact).
- `doctor.py` recognizes GitLab CI and CircleCI alongside GitHub Actions.
- Deferred follow-up: `doctor.py` `@override`-on-structural-Protocol and
  `from __future__ import annotations`-on-3.14 checks (hard static analysis).

## [0.1.8] - 2026-06-19

(0.1.7 is the concurrent hooks/pre-commit `python`-portability fix; this N17a
change ceded it and took 0.1.8 since it is eval-gated and lands later.)

From the 2026-06-19 triage. **N17a** — the `data-engineering-discipline`
`description` (the eval-gated trigger surface) gains the operational/freshness
phrasing family it under-fired on across two arcs (`di-incremental-debug` +
`parquet-upsert-direct-serving`): a consumed dataset that "ran but didn't update /
is stale / isn't refreshing / the watermark didn't advance", **data-qualified**
("a consumed dataset", "a table/extract") so it does NOT fire on non-data "didn't
update" cases (a stale CI badge, a UI that won't re-render, an in-app memoized
value). A first held-out set (`evals/trigger/holdout/data-engineering-discipline.json`)
was sealed **before** the edit, and the base trigger dataset gains both freshness
positives and the non-data over-fire negatives so the gated specificity actually
tests the over-fire (not just the held-out recall, which is verdict-only).

**Trigger-surface change — gated on the eval before merge:** must clear
`run_triggers.py data-engineering-discipline` (specificity ≥ 0.9, recall ≥ 0.8) and
`holdout_check.py data-engineering-discipline` (held-out recall within the dev CI).

## [0.1.7] - 2026-06-19

Hook `python`-invocation portability. The three hooks — `ruff_format` (PostToolUse),
`uv_enforce` (PreToolUse), `stop_nudge` (Stop) — invoked a bare `python`, which on a
Windows machine without Python on PATH resolves to the Microsoft-Store app-execution
stub and aborts (the trap fixed for the index-builder in session-workflow 0.4.1). They
now run via `uv run --no-project -- python …`, the form `.pre-commit-config.yaml`'s
`validate-plugins` hook already uses (this release also brings the repo's `lint-register`
and `run-tests` pre-commit entries to the same form). Trade-off: ~150 ms of uv startup
per invocation — acceptable, since the project is uv-native and `ruff_format` already
shells to `uvx`. CI (`validate.yml`) is unaffected — `actions/setup-python` puts `python`
on PATH there. Hook-manifest / repo-config only; no skill `description` changed, so no
holdout re-seal.

## [0.1.6] - 2026-06-19

From the 2026-06-19 triage, hardened by a pre-mortem + 3-lens blind review before any
code. **N16a** — a new runnable freshness gate
(`data-engineering-discipline/scripts/freshness_check.py`): the executable escalation
of the prose "freshness monitor" checklist line that did not bind a 2nd
incremental-staleness recurrence (the cache-builds-once-never-re-pulls bug, where
`max(cursor)` freezes while the run self-reports `success`). The review hardened it
pre-ship: a typed-comparison contract (a string cursor — `'9' > '10'` mis-orders — and
a tz-aware-vs-naive mix are rejected as `uncomparable`, not silently compared), a
non-vacuous default (`ok=None` when neither a prior snapshot nor a source max is
available — never a false pass), and a per-group helper + a row-count-per-bucket recipe
so a single frozen partition or a skipped-rows gap is catchable rather than hidden
behind a global max. Red-green tested; Recipe 14 + a pre-shipping checklist line + the
"Runnable checks" entry wire it in. Script / reference / body only — no skill
`description` changed, so no holdout re-seal.

## [0.1.5] - 2026-06-17

From the 2026-06-17 triage (revised by a fresh-eyes review panel). The headline is
**N10** — the recurring strip-on-save trap, fixed at last at the **hook** layer after
three shipped prose notes failed to bind it (the worked example behind
session-workflow 0.4.0's new escalation rule). Mechanism / body / reference only; no
skill `description` changed, so no holdout re-seal.

### Changed

- **`hooks/ruff_format.py` is now format-only.** It ran `uvx ruff format` then
  `uvx ruff check --fix`; the `--fix` strips an import added in one edit before a later
  edit uses it (F401 is a false positive on an incomplete file). `--fix` is dropped —
  it is owned by the pre-commit/CI gate, where the file is complete (`ruff check .` in
  `validate.yml` is the non-silent backstop). Command construction is extracted to
  `ruff_commands()` and guarded by a red-green test (`test_never_runs_destructive_autofix`);
  `CONTRIBUTING.md` and the hook docstring are updated in lockstep so the behavior isn't
  "restored" by a future maintainer. Closes the 4×-recurring trap
  (`2026-06-15-eval-harness-hardening-build`, `2026-06-16-context-size-calibration#2`,
  and the two prior `planned-execution` instances).

### Added

- `data-engineering-discipline`: **Mode 14 — traced the wrong copy**
  (editable-vs-installed / stale-cache divergence) in `references/llm-failure-modes.md`,
  with its mechanical defense (resolve `module.__file__` + version before any
  source-based behavior claim) and a defenses-table row; Axiom 2 §2 now states that
  reading a non-executing copy is inference, not observation, and cross-links
  `systematic-debugging` for the debug-time check (`#N8d`, from the
  `2026-06-17-di-incremental-debug-data-engineering-discipline` arc — the data facet of
  the round's reinforced observe-don't-infer cluster).
- `python-engineering`: a **project-convention-deference** rule in the edit lane —
  where a project states its own conventions (`AGENTS.md` / `CLAUDE.md` / `ruff.toml`),
  those govern and this skill's defaults are the fallback — plus a micro-edit (one-line
  docstring/string) carve-out (`#N13a`); and an explicit **tests live in a top-level
  `tests/` tree, never under `src/`** layout rule, mechanically enforced by a new
  `doctor.py` `tests-not-in-src` check, since colocated tests ship in the built wheel
  (`#N13b`).

Deferred (watch): the incremental-freshness gate (`scripts/freshness_check.py`, `#N12a`)
— single-arc, so by this round's own escalation rule a new mechanism waits for a
reinforced recurrence; the trigger-phrasing tuning (`#N12b`) is reseal-gated.

## [0.1.4] - 2026-06-15

Clears the carried-forward axiom-2 corollaries the 2026-06-13 / 2026-06-14
triages marked "still UNBUILT" (`2026-06-09-triage-craft-collection` clusters
`T3`, `T4`, `T5`, `T7`, `T9`, surfaced again in the 2026-06-14 carry-forward
list), plus the two `python-engineering` items (`2026-06-13-triage` `T9a`
edit-lane and `T9b` `@override` caveat) and the `T13` testing-strength /
shift-left asks. Reference/body content only — no skill's `description` (the
eval-gated trigger surface) changed, so no holdout re-seal.

### Added

- `references/llm-failure-modes.md` — the **absence-read-as-state** pair, the
  mirror of the 0.1.3 fabrication family (Modes 9–11):
  - **Mode 12 — silence read as status on an unattended run** (`T3`): a frozen
    tracker / unmoved HEAD is slow-vs-dead-ambiguous, not terminal; disambiguate
    with an independent observable (process tree + artifact mtimes) before any
    takeover, and read completion from the materialized result, never from
    quiet. Includes the stall→takeover recovery sequence (quiescence → in-diff
    review → independent re-verify → merge). Extends Mode 9's disk-truth
    protocol rather than restating it.
  - **Mode 13 — fail-open tooling** (`T9`): a gate where *did-not-run* and
    *found-nothing* produce the same green (`command | filter` + "no output ⇒
    pass", return-code-blind, exception-swallowing) manufactures false
    confidence; assert the tool exists and exited zero, treat non-zero as
    BLOCKED, prefer built-ins for fences, and prove the gate red twice (planted
    violation + tool removed).
  - Cross-mode synthesis gains an "absence read as a state" entry; the
    mechanical-defenses table gains liveness-probe and fail-closed-tooling rows.
    `SKILL.md` quick-warning list + resource count updated (11 → 13 modes).
- `references/principles.md` — Principle 20 gains a **blast-radius corollary**
  (`T4`): an "all sites" precondition by grep must not be `src`-only — scope to
  `tests/`, `docs/`, config / generated trees, and sibling consumer repos, and
  treat the result as a checklist, not a one-time count. Cross-referenced from
  the consumer-enumeration steps in `scenarios.md` (2.3 lineage walk, 4.2
  input inventory).
- `references/parity-recipes.md` — two checks that govern whether any strictness
  rung can be trusted:
  - **Recipe 12 — cover every unit, not a sample** (`T5`): enumerate the
    complete set from the source-of-truth registry and assert the gate covers
    all of it (the CONSUMER-SWAP input-set diff included); a gate that pins a
    sample is hollow in coverage.
  - **Recipe 13 — prove the check can fail before trusting it green** (`T7`):
    plant a known divergence and watch the check catch it before trusting the
    pass; covers the fixture-must-participate trap and the verbatim-move
    `git show HEAD:… | diff` recipe.
  - Strictness-ladder note added distinguishing these (coverage / non-vacuity
    preconditions) from the strictness layers.
- `skills/python-engineering/SKILL.md` — a **"modifying existing code (the edit
  lane)"** section (`T9a`) surfacing only edit-relevant rules (match local
  convention, Protocol-first seams, `@override` semantics, import hygiene under
  strip-on-save, quoting, scope discipline) without the scaffold / Docker /
  observability / CI payload; and the **`@override` PEP-698 caveat** (`T9b`) in
  the Typing Philosophy section (do not annotate `@override` on a plain
  structural class that doesn't subclass its Protocol — the two are mutually
  exclusive).
- `skills/python-engineering/references/testing_and_qa.md` — **mutation testing**
  (test strength vs. presence; `mutmut`, killed/total score) and **the economics
  of shift-left** (the cost-of-defect curve that makes the pyramid's cheap layers
  non-optional) (`T13`), with a pointer added from the `SKILL.md` reference-files
  index.

## [0.1.3] - 2026-06-14

Acts on the data-engineering backlog from the 2026-06-13 / 2026-06-14 triages
(`2026-06-13-triage-craft-collection#T1`/`#T6`, reinforced by the
`datatools-bedrock-arc`, `ws-runtime-arc`, and `v1-cut-arc` reports). Reference
content only — the four non-negotiables, the 21 principles, and the
`data-engineering-discipline` `description` (the eval-gated trigger surface) are
unchanged, so no holdout re-seal.

### Added

- `references/llm-failure-modes.md` — the **fabrication family**: three new modes for
  inference *invented* as observation (the sharpest Axiom-2 violation, distinct from
  the drift modes 2/8):
  - **Mode 9 — fabricated telemetry**: async status events (notifications, monitor
    streams, dry-run callbacks, "approved / merged / complete" events) treated as
    system state; defense = a disk-truth protocol (verify every event against an
    append-only source before any status report or state-changing action).
  - **Mode 10 — confabulated anchors + projected verification**: a cited
    test / fixture / file / symbol never read or non-existent; one part verified and
    the whole recorded clean; a `file:lo-hi` slice ending inside a collection literal.
    Defense = an anchor-provenance pass (every cited anchor traces to a read; name the
    scope verified; read to the closing delimiter; a handed-down fix brief is a claim
    whose anchors are verified before applying).
  - **Mode 11 — the verifier inherits none of the design's documented traps**: fresh
    pattern-matching / verifier code reproduces a trap the design recorded; put traps
    in the artifacts verifiers read (review prompts, planted-failure fixtures), not
    only design docs.
  - Cross-mode synthesis + mechanical-defenses table updated; `SKILL.md` quick-warning
    list + resource count updated (8 → 11 modes).
- `references/scenarios.md` — three playbooks for wave shapes the prior scenarios
  didn't cover (per `#T6`):
  - **Scenario 8 — building an enforcement gate** (the data product is a verdict
    function): the dataset→verdict translation table, the non-vacuity matrix
    (plant-fires / empty-allow-list / real-tree negative-pin), green-on-arrival.
  - **Scenario 9 — repairing a contract to match shipped reality**: the
    backward-repair direction (consumers' observed reality outranks an unread
    declaration), retire the aspiration durably, land with a parity pin.
  - **Scenario 10 — cutting a release across independently-merged waves**: assembled
    re-seal, clean-room + strict real-data sweep, cross-wave docs / release-notes
    completeness via a blind audit panel.
  - Cross-scenario note: **the lint / format toolchain is a consumer** — run the
    repo's own gate on a representative transformed file before locking a diff-shape
    constraint; state constraints in content terms, not position terms.
- `references/parity-recipes.md` — **Recipe 11: contract fingerprint** (byte-stable
  surface token): the pin / re-seal mechanism Scenarios 9 and 10 rely on, with its
  strictness-ladder and recipe-selector rows.

Carried forward (still unbuilt): the prior triage's axiom-2 corollaries
(unattended-run observability, src-only blast-radius, non-vacuous-parity recipes,
fail-open tooling) and the `N2e` behavior-change-no-output proxy (`watch`).
*Update: the four axiom-2 corollaries shipped in 0.1.4; `N2e` remains `watch`.*

## [0.1.2] - 2026-06-07

### Changed

- `python-engineering`: the description now scopes to existing, inherited, and
  legacy projects as much as greenfield — assessing and modernizing a current
  setup, not only scaffolding a new one — so "modernize this project's tooling"
  phrasings trigger. Surfaced by the triggers eval; narrow "is my config
  current?" asks remain a triggering-threshold limit (the model answers them
  directly) and were left unforced rather than overfit.

## [0.1.1] - 2026-06-05

- Fixed: corrected the `repository` URL to `grimaldost/craft-collection` (the
  previous `grimaldo-stanzani` owner did not resolve).

## [0.1.0] - 2026-06-04

Initial release.

- `python-engineering` skill with `stack.toml` as the single source of truth for
  version pins.
- `data-engineering-discipline` skill (relocated, examples genericized).
- Scripts: `scaffold.py`, `doctor.py`, `check_versions.py`, `schema_diff.py`,
  `parity_check.py`, `contract_check.py` — all with stdlib-runnable tests.
- Hooks: ruff-format (PostToolUse), uv-enforce (PreToolUse), optional data
  checklist nudge (Stop, off by default).
- Tier-3 freshness loop: drift detection + monthly `currency` cron +
  `/refresh-stack` review command.

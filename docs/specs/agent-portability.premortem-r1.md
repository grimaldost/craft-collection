# Pre-mortem pass — round 1 (saved verbatim by the caller)

- Spec: docs/specs/agent-portability.md
- Date: 2026-07-16
- Reviewer: pre-mortem-review (fresh subagent, non-author)
- Spec-hash: 5101d47aaa7fd46e79ae246027baddbf79e04597afbd9bb5b1747a7c03e5b145

---
# Pre-mortem review — `docs/specs/agent-portability.md`

Reviewed blind against the tree at `/home/user/craft-collection` (no authoring-session knowledge). Every gate script, cited core, and cited line was read; populations were enumerated by listing files; baseline gates were executed read-only (`lint_register.py` → clean, `validate_plugins.py` → valid, `word_budget.py` → within budget).

## Findings

```yaml
- id: FM-1
  severity: BLOCKER
  evidence: evals/harness/test_scripts_in_sync.py:17-46; evals/harness/claude_runner.py (byte-identical twin, verified by diff); evals/harness/run_triggers.py:21, grade_tasks.py:24, judge.py:22 (the actual call sites)
  smallest_fix: "§8/PR08 prompt: name BOTH copies and the sync direction — edit evals/harness/claude_runner.py (the source of truth per test_scripts_in_sync.py's 'Re-copy: cp evals/harness/X' message), re-copy the 7 SYNCED engine files to the plugin, and add test_scripts_in_sync passing to the acceptance criterion."
  blast_radius: "The SYNCED set is 7 files (aggregate, claude_runner, grade_tasks, judge, run_all, run_triggers, stats); touching call sites in run_triggers/grade_tasks/judge drags all of them into PR08's diff and re-copy."
  disconfirming_test: "grep -rn 'claude_runner' evals/harness/test_scripts_in_sync.py — if claude_runner.py were not in the SYNCED tuple, a plugin-only refactor would pass."
  consumed_input: "run_tests.py collects evals/harness/test_scripts_in_sync.py (SEARCH_DIRS includes 'evals', scripts/run_tests.py:24) and it asserts _norm(bundled) == _norm(harness) per file (line 37) — any §8 PR that edits only the plugin copy fails pre-push and CI."
  target_section: "section 8"

- id: FM-2
  severity: MAJOR
  evidence: scripts/word_budget.json vs live counts — 21 of 23 bodies sit at exactly 0 words of headroom, review-panel and planned-execution at 1 (verified by executing word_budget.py + per-skill diff); spec line 150-152 requires "stays at or under its baseline", DoD line 277 allows baselines "only lowered"
  smallest_fix: "PR03–PR05 prompts: pre-authorize the named fallback the ratchet itself supports (word_budget.py:79-81 — a reviewed baseline bump that names what the growth displaces) when replacement-in-place would force cutting load-bearing text that the trigger evals then flag."
  blast_radius: "Touches scripts/word_budget.json, which validate_plugins.py reads on every run (validate_plugins.py:158) — a bump is visible to pre-commit and CI immediately."
  disconfirming_test: "Draft the §3 review-panel rewording (~24 words replacing the two ~8-word 'Claude Code only' gates at SKILL.md:4 and :97) and run word_budget.py — if it fits under 1120 without deleting other prose, this mode is refuted."
  consumed_input: "validate_plugins.py:158 calls check_budgets(current_counts(), load_baselines()); check_budgets fails any body over baseline (word_budget.py:77-81)."
  target_section: "sections 3-5"

- id: FM-3
  severity: MAJOR
  evidence: docs/specs/agent-portability.md:201-210 (§7) — craft-floor.yaml is "copy-pasteable ... for consumer projects" and invokes scripts/check_uv_hygiene.py, a file that does not exist in any consumer repo; no .pre-commit-hooks.yaml packaging is specified anywhere in the spec
  smallest_fix: "§7: state the delivery mechanism — either add a repo-root .pre-commit-hooks.yaml so consumers reference craft-collection as a pre-commit `repo:` by URL, or require the floor file's comments to instruct copying check_uv_hygiene.py alongside; and strengthen the acceptance criterion from 'parses under pre-commit' to 'runs in a fixture consumer repo'."
  blast_radius: "A repo-root .pre-commit-hooks.yaml is a new mechanically-consumed artifact (pre-commit reads it from any repo referenced by URL) — it must name real entry points and survives every future rev tag."
  disconfirming_test: "In a scratch consumer repo, paste craft-floor.yaml as specced and run `pre-commit run --all-files` — the check_uv_hygiene entry fails with file-not-found, confirming; if pre-commit resolves it, refuted."
  consumed_input: "pre-commit resolves a local `entry: python scripts/check_uv_hygiene.py` against the CONSUMER repo's root — verified against §7's own text, which places the script only in this repo."
  target_section: "section 7"

- id: FM-4
  severity: MAJOR
  evidence: scripts/run_tests.py:24 — SEARCH_DIRS = ('plugins', 'evals'); scripts/ contains zero test files today; the repo's convention for scripts/-targeting tests is evals/harness/ (test_lint_register.py:10-13, test_validate_plugins.py, test_word_budget.py)
  smallest_fix: "§1 and §7 prompts: name evals/harness/ as the home of test_gen_agents_md.py and the check_uv_hygiene tests (matching test_lint_register.py's sys.path pattern), and add 'run_tests.py output lists the new test file' to both acceptance criteria."
  blast_radius: "None beyond the two PRs — no shared config changes; alternatively extending SEARCH_DIRS would touch every future test discovery."
  disconfirming_test: "Create an empty scripts/test_probe.py that prints 'ok:' and run scripts/run_tests.py — if it appears in the PASS list, discovery covers scripts/ and this mode is refuted."
  consumed_input: "run_tests.py:28 rglob's test_*.py only under plugins/ and evals/; an undiscovered test file is silently skipped (the vacuous-gate class run_tests.py's own docstring names, lines 5-9)."
  target_section: "sections 1 and 7"

- id: FM-5
  severity: MAJOR
  evidence: evals/trigger/ has 21 datasets — refresh-stack and refresh-models absent (both are disable-model-invocation: true, refresh-stack/SKILL.md frontmatter); evals/trigger/holdout/ has 18 — review-panel and evaluate-skill absent
  smallest_fix: "§3/§5 acceptance criteria: scope the eval requirement to datasets that exist ('trigger evals where a dataset exists; holdout where sealed') and explicitly exempt refresh-stack as manual-only/non-triggering — or explicitly order creating the missing holdouts, acknowledging the scope growth."
  disconfirming_test: "ls evals/trigger/refresh-stack.json evals/trigger/holdout/review-panel.json — if both exist, the criteria are satisfiable as written and this mode is refuted."
  consumed_input: "§3's acceptance ('the four skills' trigger/holdout evals all pass') and §5's ('the touched skills' evals pass') consume per-skill JSON datasets under evals/trigger/ and evals/trigger/holdout/, which the harness (run_triggers.py, holdout_check.py) loads by skill name."
  target_section: "sections 3 and 5"

- id: FM-6
  severity: MAJOR
  evidence: plugins/engineering-discipline/hooks/test_ruff_format.py:5 — `from ruff_format import ruff_commands, target_file`; target_file is a module-level function (ruff_format.py:22), NOT inside main(); stop_nudge.py's extraction is _load_payload (stop_nudge.py:81) with an already-injectable main
  smallest_fix: "§6: replace 'moved from the main() bodies' with 'harness_adapters.py imports/wraps the existing extraction functions (target_file, _load_payload) without relocating them' — otherwise the move breaks test_ruff_format.py:5 and violates §6's own 'existing hook tests stay green untouched' criterion."
  disconfirming_test: "grep -n 'from ruff_format import' plugins/engineering-discipline/hooks/test_ruff_format.py — if tests imported nothing payload-shaped from the hook modules, relocation would be safe and this mode refuted."
  consumed_input: "test_ruff_format.py:5 imports target_file by name from ruff_format at module load; run_tests.py executes it with cwd=hooks/ (run_tests.py:42-44), so a relocated symbol is an ImportError, not a soft failure."
  target_section: "section 6"

- id: FM-7
  severity: MINOR
  evidence: .pre-commit-config.yaml:17-19 — trailing-whitespace and end-of-file-fixer run on all files including a repo-root AGENTS.md; §1 (spec lines 111-112) pins determinism but not hygiene of the generated bytes
  smallest_fix: "§1 acceptance: add 'output ends with exactly one trailing newline and contains no trailing whitespace' — otherwise the hygiene fixers and the §2 freshness gate rewrite the file in opposite directions forever."
  blast_radius: "Only AGENTS.md and the two hygiene hooks; no other artifact affected."
  disconfirming_test: "Generate a file lacking a final newline, run `pre-commit run end-of-file-fixer --files AGENTS.md`, then the --check — if both pass, refuted."
  consumed_input: "end-of-file-fixer mutates any file not ending in exactly one \\n; gen_agents_md.py --check (per §2) compares committed bytes to a fresh render — two writers, one file."
  target_section: "sections 1-2"

- id: FM-8
  severity: MINOR
  evidence: scripts/lint_register.py:33-34 — DEFAULT_SCOPE = ROOT/'plugins'; pre-commit invokes it with pass_filenames:false and no args (.pre-commit-config.yaml:36-39); CI likewise (validate.yml:24)
  smallest_fix: "§9 acceptance: either drop 'the register linter passes' (it never sees docs/) or make it real: 'lint_register.py docs/ run explicitly in the PR'."
  disconfirming_test: "Plant a 'YOU MUST' line in a scratch docs/probe.md and run scripts/lint_register.py with no args — exit 0 confirms docs/ is out of scope."
  consumed_input: "lint_register.py lints only the paths given, defaulting to plugins/ (lint_register.py:234); neither gate wiring passes docs/."
  target_section: "section 9"

- id: FM-9
  severity: MINOR
  evidence: plugins/session-workflow/README.md:29,34 — plugin README still describes review-panel and evaluate-skill as "Claude Code only"; review-panel's frontmatter description (SKILL.md:4) is a §3 target, and every frontmatter edit invalidates the §2-gated AGENTS.md
  smallest_fix: "§3 prompt: add the plugin README lines to the touched set, and one sentence in §§3-5 prompts: 'a description edit requires regenerating AGENTS.md in the same PR (the §2 gate will otherwise block).'"
  disconfirming_test: "After a mock §3 rewording, grep -rn 'Claude Code only' plugins/session-workflow/README.md — a hit confirms the drift the spec leaves unowned."
  consumed_input: "gen_agents_md.py --check (per §2, wired in pre-commit + CI) re-renders from frontmatter; any PR03-05 description edit without regeneration fails that gate."
  target_section: "sections 3-5"
```

## Prose summary (most likely first)

1. **FM-1 (BLOCKER, §8).** The spec's Concept→module map and §8 place the eval-runner seam in `plugins/.../evaluate-skill/scripts/claude_runner.py` and never mention that `evals/harness/` holds a byte-identical twin of it **and of the call-site files** (`run_triggers.py`, `grade_tasks.py`, `judge.py`), enforced verbatim by `test_scripts_in_sync.py` — whose error message names `evals/harness/` as the copy **source**, the inverse of the spec's framing. A PR08 implementer following the spec literally produces a guaranteed-red pre-push/CI gate, and the "one concern" manifest row hides a 7-file, two-tree diff.

2. **FM-2 (MAJOR, §§3–5).** I executed the word-budget ratchet: 21 of 23 bodies have exactly zero headroom (review-panel: 1 word). §3's prescribed replacement text is ~3× longer than the gates it replaces, yet the spec forbids the escape valve the gate itself documents (a reviewed baseline bump naming displacement, `word_budget.py:79-81`) — DoD says baselines are "only lowered". ADR-0005 sanctions replacement-in-place, but the spec should pre-authorize the fallback or the likely outcome is silent deletion of load-bearing prose policed only by manual evals.

3. **FM-3 (MAJOR, §7).** The consumer floor as specced cannot execute in a consumer repo: `craft-floor.yaml` invokes `scripts/check_uv_hygiene.py`, which exists only in this repo, and the spec creates no `.pre-commit-hooks.yaml` (the artifact pre-commit mechanically requires to consume hooks from a remote repo by URL). Its acceptance criterion ("parses under pre-commit") would pass while the deliverable is unusable by its only audience.

4. **FM-4 (MAJOR, §§1, 7).** `run_tests.py` discovers tests only under `plugins/` and `evals/` (`run_tests.py:24`). §1's `test_gen_agents_md.py` "in the generator's" location and §7's hygiene tests naturally land in `scripts/`, where no gate ever executes them — the exact vacuous-gate class the runner's own docstring warns about. The repo's existing convention (scripts/-targeting tests live in `evals/harness/`, e.g. `test_lint_register.py`) just needs to be named in the prompts.

5. **FM-5 (MAJOR, §§3, 5).** The eval acceptance criteria reference datasets that do not exist: `refresh-stack` has no trigger or holdout dataset (it is `disable-model-invocation: true` — trigger evals are meaningless for it), and `review-panel` and `evaluate-skill` have trigger sets but no holdouts. As written, PR05's and part of PR03's criteria are unsatisfiable.

6. **FM-6 (MAJOR, §6).** "Payload extraction moved from the `main()` bodies" contradicts the tree: `target_file` is already a module-level function that `test_ruff_format.py:5` imports by name, and `stop_nudge.py`'s extraction is `_load_payload` behind an injectable `main`. Relocating them breaks §6's own "tests stay green untouched" criterion; the spec should say the adapters *wrap* the existing extraction functions in place.

7. **FM-7/8/9 (MINOR).** Generated-AGENTS.md bytes vs the hygiene fixers (potential two-writer loop); §9's vacuous "register linter passes" (the linter never scans `docs/`); and unowned cross-artifact drift (plugin README "Claude Code only" lines; AGENTS.md regeneration obligation inside PR03–05).

## cleared

- "23 skills" — enumerated: exactly 23 `plugins/*/skills/*/SKILL.md`; one command (`plugins/session-workflow/commands/anchor.md`), one output style (`plugins/session-workflow/output-styles/step-digest.md`) — matches §1's acceptance population.
- All four "pure core" citations exist at the cited lines (observed): `ruff_format.py:31 def ruff_commands`, `uv_enforce.py:69 def verdict`, `scan_toolkit.py:37 def _read_frontmatter`, `claude_runner.py` docstring line 3/5 `parse_stream`/`claude -p`.
- Coupling evidence anchors all check out (observed): `review-panel/SKILL.md:4` and `:97` "Claude Code only"; `engineering-discipline/hooks/hooks.json:11 ${CLAUDE_PLUGIN_ROOT}`; `session-workflow/hooks/hooks.json:22 "matcher": "compact|resume"`; `scan_toolkit.py:409 'claude', 'plugin', 'list'` with graceful degradation (returns `[]` on any CLI failure, `scan_toolkit.py:414-421`); `anchor.md:2` and `step-digest.md:2`; `.pre-commit-config.yaml:30 id: ruff-format`.
- §1's `_read_frontmatter` reuse is sound for THIS repo's shapes (observed): every one of the 23 SKILL.md descriptions is either a `>`/`>-` block scalar (handled at `scan_toolkit.py:56-64`) or a single-line quoted/plain scalar (handled by `_unquote`); `anchor.md` (no `name:` key — stem fallback needed, description single-line) and `step-digest.md` (plain single-line) also parse. The reuse instruction correctly names `_read_frontmatter`, not the 100-char-truncating `_preview`/`_scan_skills` path.
- Importing `_read_frontmatter` via importlib is viable: `scan_toolkit.py` is stdlib-only with a `__name__` guard — import has no side effects (observed).
- §6's "three existing hook test files" exist: `test_ruff_format.py`, `test_uv_enforce.py`, `test_stop_nudge.py` (listed).
- Spec's gate-commands list matches `.github/workflows/validate.yml:19-28` and `.pre-commit-config.yaml:25-53`; enforcement-status table rows for register/word-budget/structure ("pre-commit + CI") are accurate (observed; register lint and structural validation also executed clean here).
- `data-engineering-discipline` "already harness-neutral" (§5): zero case-insensitive "claude" hits in its SKILL.md (observed via grep).
- §4's referenced files exist: `planned-execution/subagent-prompts.md`, `choosing-models/models.toml` (listed).
- `docs/method/review-checklist.md` exists; README has an Install section for §9's link; `AGENTS.md` and `adapters/` do not yet exist (clean creation targets).
- All six ADRs exist and the spec's readings of 0001/0003/0005/0006 are faithful (observed).

## conditions

(Structured fixes should the caller prefer CONDITIONAL-CERTIFY after resolving FM-1; as it stands FM-1 plus three MAJORs warrant revision.)

- **C1 (FM-1):** §8 rewritten to name `evals/harness/` as the edit surface, the 7-file SYNCED re-copy to the plugin, and `test_scripts_in_sync.py` in the acceptance criterion.
- **C2 (FM-2):** PR03–05 prompts pre-authorize a reviewed `word_budget.json` bump naming displacement as the fallback when replacement-in-place fails evals.
- **C3 (FM-3):** §7 names the consumer delivery mechanism (`.pre-commit-hooks.yaml` repo-hook packaging, or copy-the-script instruction) and a fixture-consumer-repo acceptance run.
- **C4 (FM-4):** §1/§7 prompts place new tests in `evals/harness/` and assert they appear in `run_tests.py` output.
- **C5 (FM-5):** §3/§5 eval criteria scoped to datasets that exist; refresh-stack exempted by name.
- **C6 (FM-6):** §6 reworded: adapters wrap existing extraction functions in place; nothing is relocated out of the hook modules.

Unverified-offline: 2 (the §3–§5 trigger/holdout eval runs require the `claude` CLI with credentials; the §2 pre-commit failure-mode simulation requires a mutating `pre-commit run`, which this read-only pass could not perform)
PREMORTEM-VERDICT: NEEDS-REVISION — reviewer: pre-mortem-review (fresh subagent, non-author)

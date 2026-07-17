# Pre-mortem certification artifact — round 2 (saved verbatim by the caller; latest-wins)

- Spec: docs/specs/agent-portability.md
- Date: 2026-07-16
- Reviewer: pre-mortem-review-r2 (fresh subagent, non-author)
- Spec-hash: 5c717c319386d5d5d2130754f418185a940a6636d7a6b17ec9f77902014c1b85
- Round 1 record: docs/specs/agent-portability.premortem-r1.md (NEEDS-REVISION; all findings folded)

---
# Pre-mortem re-gate — round 2 (resolution audit) — `docs/specs/agent-portability.md`

- Date: 2026-07-16
- Reviewer: pre-mortem-review-r2 (fresh subagent, non-author; no knowledge of the authoring session or of round 1 beyond the saved verdict record)
- Reviewed against: the live tree at `/home/user/craft-collection` (every fold-cited file re-read; populations re-enumerated; `word_budget.py` re-executed read-only — "23 skill bodies within budget"; no file modified)
- Prior record: `docs/specs/agent-portability.premortem-r1.md` (NEEDS-REVISION, FM-1..FM-9)

## Part 1 — Resolution audit (FM-1..FM-9)

| Finding | Status | Current-text evidence (spec line, verified against code) |
|---|---|---|
| FM-1 (BLOCKER, §8 sync twins) | **RESOLVED** | Spec:246–254 names `evals/harness/claude_runner.py` as "the edit surface … the sync **source** per `evals/harness/test_scripts_in_sync.py`", lists all seven SYNCED files verbatim matching the tuple at `evals/harness/test_scripts_in_sync.py:18–26`, names the real call sites (`run_triggers.py`, `grade_tasks.py`, `judge.py` — confirmed importers at `run_triggers.py:21`, `grade_tasks.py:24`, `judge.py:22`), orders the same-PR re-copy, and spec:257–258 puts `test_scripts_in_sync.py` in the acceptance criterion. Sync direction matches the test's "Re-copy: cp evals/harness/{name}" message (test:39). Concept map row (spec:98) also corrected. Not narrowed. |
| FM-2 (MAJOR, word budget) | **RESOLVED** | Spec:158–162 pre-authorizes "the ratchet's own escape valve — a reviewed baseline bump that names what the growth displaces"; §4 (spec:179–181) and §5 (spec:196–197) inherit it by reference; DoD (spec:316–318) no longer says "only lowered" — it now permits growth "only as the §3 fallback". Ground truth re-confirmed: 21/23 bodies at exactly 0 headroom, review-panel and planned-execution at 1 (executed `word_budget.py` against `scripts/word_budget.json`). |
| FM-3 (MAJOR, consumer delivery) | **RESOLVED** | Spec:226–229: "(b) a repo-root `.pre-commit-hooks.yaml` exporting that check as a hook id, so a consumer references this repository as a pre-commit `repo:` by URL — the delivery mechanism, since a local `entry:` would resolve against the consumer's root where the script does not exist". Acceptance strengthened to a fixture consumer repo where `pre-commit run --all-files` "resolves and executes every entry, hygiene hook included" (spec:237–240). Artifact list (spec:6) and concept map (spec:99) both carry `.pre-commit-hooks.yaml`. See advisory ADV-2. |
| FM-4 (MAJOR, test homing) | **RESOLVED** | §1: "`evals/harness/test_gen_agents_md.py` (that directory, not `scripts/`, is where `run_tests.py` discovers tests) … and appears in `run_tests.py` output" (spec:123–125); §7: "Tests live in `evals/harness/` … since `scripts/run_tests.py` discovers only `plugins/` and `evals/`" (spec:234–235) plus "appears in `run_tests.py` output" (spec:236–237). Ground truth: `SEARCH_DIRS = ('plugins', 'evals')` at `scripts/run_tests.py:24`; `evals/harness/` already houses `test_lint_register.py`, `test_validate_plugins.py`, `test_word_budget.py`. |
| FM-5 (MAJOR, phantom datasets) | **RESOLVED** | §3: "holdout evals where a sealed holdout exists (review-panel and evaluate-skill have trigger sets but no holdouts today)" (spec:166–167) — matches listings: both present in `evals/trigger/`, both absent from `evals/trigger/holdout/`. §4: "plus holdouts, which all three have" (spec:184) — choosing-tools, planned-execution, choosing-models all present in `evals/trigger/holdout/`. §5: "refresh-stack is exempt by name — it is `disable-model-invocation: true` with no trigger dataset" (spec:201–202) — frontmatter confirmed (`refresh-stack/SKILL.md:4`), no `evals/trigger/refresh-stack.json`. Gate-commands line scoped to match: "for every §3–§5-touched skill that has a dataset" (spec:57). No silent narrowing — the promoted requirement (evals where datasets exist) is fully kept. |
| FM-6 (MAJOR, relocation breaks tests) | **RESOLVED** | §6 now reads "**imports and wraps** the extraction and decision functions where they already live … nothing is relocated out of the hook modules" (spec:206–210). All five named symbols exist in place: `target_file` (`ruff_format.py:22`), `ruff_commands` (`:31`), `cwd_is_uv_project` (`uv_enforce.py:58`), `verdict` (`:69`), `_load_payload` (`stop_nudge.py:81`); `test_ruff_format.py:5` imports `ruff_commands, target_file` and `test_uv_enforce.py:5` imports `verdict` by name — the wrap-in-place constraint keeps them green. See advisory ADV-3. |
| FM-7 (MINOR, generated-byte hygiene) | **RESOLVED** | §1 acceptance: "no trailing whitespace and ends with exactly one newline (so the pre-commit hygiene fixers and the §2 gate never fight over the bytes)" (spec:120–122); hygiene asserted in the new test (spec:124–125). Matches `.pre-commit-config.yaml` `trailing-whitespace`/`end-of-file-fixer` hooks. |
| FM-8 (MINOR, vacuous docs/ lint) | **RESOLVED** | §9 acceptance: "`scripts/lint_register.py docs/` is run explicitly in the PR (the linter's default scope is `plugins/` only, so a bare invocation never sees `docs/`)" (spec:279–280). Ground truth: `DEFAULT_SCOPE = ROOT / 'plugins'` (`lint_register.py:34`), `scope = args.paths or [DEFAULT_SCOPE]`. |
| FM-9 (MINOR, README drift + regen obligation) | **RESOLVED** | §3 touched set includes "`plugins/session-workflow/README.md:29` and `:34` still read 'Claude Code only'" (spec:155–156) — both lines confirmed live; "any frontmatter-description edit regenerates `AGENTS.md` in the same PR — an obligation from PR01 onward, mechanized when §2's gate lands" (spec:156–158), inherited by §4 (spec:180–181) and §5 (spec:196–197). Coherent with the manifest's PR03–05-may-precede-PR02 ordering. |

No fold silently narrowed a promoted item: the eval scoping (FM-5) narrows only to datasets that verifiably exist, and the gate-commands line, section criteria, and DoD all narrow identically.

## Part 2 — Fold-introduced defects hunted

Every claim the fold added or reworded was re-grounded against code (details in `cleared:`). Nothing found that survives the rising bar — no new claim misidentifies a file, symbol, line, population, direction, or mechanism in a way that could corrupt the gated decision. New findings:

```yaml
[]  # no BLOCKER/MAJOR/MINOR findings survive the rising bar
```

Notable advisories (non-blocking; fold as advisories, no re-round owed):

```yaml
- id: ADV-1
  severity: ADVISORY
  evidence: "docs/specs/agent-portability.md:6 — the 'Output artifact(s)' header omits the §8 edit surface (evals/harness/claude_runner.py + the re-copied plugin mirror) and §2's config edits (.pre-commit-config.yaml, .github/workflows/validate.yml), all of which §2/§8 and the concept map do carry."
  smallest_fix: "Append 'evals/harness runner seam + plugin mirror re-copy; §2 gate wiring' to the header list."
  disconfirming_test: "Diff the header list against the union of files each §-criterion touches."
  target_section: "header"
- id: ADV-2
  severity: ADVISORY
  evidence: "§7 (spec:226-229) specifies .pre-commit-hooks.yaml but not the hook's `language:`. The repo root has no pyproject.toml (ls: CONTRIBUTING.md LICENSE README.md SECURITY.md docs evals plugins ruff.toml scripts), so `language: python` would require packaging the repo; `language: script` (shebang + exec bit on scripts/check_uv_hygiene.py) works without it. The fixture-consumer acceptance run (spec:237-240) already disconfirms a wrong choice, so this cannot silently pass."
  smallest_fix: "One clause in §7(b): 'as language: script (the repo is not pip-installable)'."
  disconfirming_test: "In the fixture consumer, reference the repo by URL with language: python and run pre-commit — install fails for an unpackaged repo."
  target_section: "section 7"
- id: ADV-3
  severity: ADVISORY
  evidence: "§6's justification 'the existing tests import those symbols by name' (spec:209-210) is exact for target_file/ruff_commands (test_ruff_format.py:5) and verdict (test_uv_enforce.py:5) but over-broad for _load_payload — test_stop_nudge.py:8 imports decide, main, nudge_message, should_nudge, not _load_payload. The operative instruction (wrap in place, relocate nothing) is correct and safe either way."
  smallest_fix: "None required; optionally soften to 'the existing tests import hook-module symbols by name'."
  disconfirming_test: "grep -n _load_payload plugins/engineering-discipline/hooks/test_stop_nudge.py — no hit."
  target_section: "section 6"
```

## Part 3 — Post-fold coherence

- **Sections vs gate commands:** the gate-commands eval line (spec:57, "and holdouts where sealed … every §3–§5-touched skill that has a dataset; run manually; results recorded in the PR description") agrees with §3/§4/§5 criteria and with the enforcement-status row "trigger-eval gates … review-only, run manually per touched skill" (spec:83). The §2 gate is correctly marked "After §2 lands" (spec:56) and "planned" in the table (spec:82). Register/word-budget/structure rows match actual wiring (`.pre-commit-config.yaml` local hooks; `validate.yml` steps; `run-tests` at pre-push + CI).
- **DoD vs sections:** DoD's derived-artifacts list (spec:311–318) names exactly the three artifact classes the sections create obligations for (AGENTS.md/§2, SYNCED mirror/§8, word_budget.json/§3-fallback) with matching mechanisms; no contradiction with §3's escape valve.
- **PR manifest:** PR01–PR09 ↔ §1–§9 remains a bijection (spec:284–294); dependency notes (spec:296–299) are consistent with §3's "obligation from PR01 onward, mechanized when §2's gate lands" bridge.
- **Fold ledger anchors:** all nine `artifact:line` rows land — spec:247 "sync **source**", :162 "baseline bump that names what the growth displaces", :226 ".pre-commit-hooks.yaml", :123 "evals/harness/test_gen_agents_md.py (that directory, not scripts/", :201 "refresh-stack is exempt by name", :206 "**imports and wraps**", :121 "exactly one newline", :279 "lint_register.py docs/", :156 "frontmatter-description edit regenerates AGENTS.md" (verified by printing each line).

## cleared

- Fold ledger: all nine anchor lines contain their claimed snippets (printed each of spec lines 247, 162, 226, 123, 201, 206, 121, 279, 156).
- §8 SYNCED-file claims: the seven names in spec:250–251 exactly equal the `SYNCED` tuple (`evals/harness/test_scripts_in_sync.py:18–26`); sync direction (harness → plugin) matches test:38–39; call-site claim matches importers (`run_triggers.py:21`, `grade_tasks.py:24`, `judge.py:22`); "pure parts untouched" names match the harness docstring (`evals/harness/claude_runner.py:3–5` — `parse_stream`, `AgentRun`, `build_command`, `claude -p`).
- Dataset populations: `evals/trigger/` = 21 skill datasets (no refresh-stack, no refresh-models); `evals/trigger/holdout/` = 18 (review-panel, evaluate-skill, consolidate-knowledge absent) — §3's named no-holdout pair, §4's "all three have", and §5's python-engineering-has-both all correct.
- refresh-stack exemption: `disable-model-invocation: true` at `plugins/engineering-discipline/skills/refresh-stack/SKILL.md:4`; no trigger dataset exists.
- `run_tests.py` discovery: `SEARCH_DIRS = ('plugins', 'evals')` (`scripts/run_tests.py:24`); `evals/harness/` is demonstrably the home of scripts-targeting tests (`test_lint_register.py`, `test_validate_plugins.py`, `test_word_budget.py` present).
- §6 wrap-in-place ground truth: `target_file` (`ruff_format.py:22`), `ruff_commands` (`:31`), `cwd_is_uv_project` (`uv_enforce.py:58`), `verdict` (`:69` — matching the spec's `uv_enforce.py:69` citation), `_load_payload` (`stop_nudge.py:81`); `test_ruff_format.py:5` and `test_uv_enforce.py:5` import by name; three hook test files exist.
- §7 mirror citation: `.pre-commit-config.yaml:30` is exactly `id: ruff-format`.
- FM-8 ground truth: `DEFAULT_SCOPE = ROOT / 'plugins'` (`scripts/lint_register.py:34`), args-or-default scope.
- FM-9 ground truth: `plugins/session-workflow/README.md:29` and `:34` both still read "Claude Code only"; `review-panel/SKILL.md:4` and `:97` likewise.
- FM-2 ground truth re-executed: 23 bodies, 21 at 0 headroom, 2 at 1 — "nearly every body sits at zero headroom" (spec:159–160) is accurate; suite currently "within budget".
- Populations for §1: exactly 23 `plugins/*/skills/*/SKILL.md`, one command (`anchor.md`, description at line 2 "Snapshot the run's control anchor…"), one output style (`step-digest.md`, `name: step-digest` at line 2).
- Context-section coupling anchors: `engineering-discipline/hooks/hooks.json:11` `${CLAUDE_PLUGIN_ROOT}`; `session-workflow/hooks/hooks.json:22` `"matcher": "compact|resume"`; `scan_toolkit.py` CLI shell-out with graceful degradation (returns `[]` on any failure) and `_read_frontmatter` at the cited region.
- Creation targets all still absent (clean): `AGENTS.md`, `adapters/`, `scripts/gen_agents_md.py`, `scripts/check_uv_hygiene.py`, `.pre-commit-hooks.yaml`, `docs/portability.md`, `harness_adapters.py`.
- Supporting artifacts exist: `docs/method/review-checklist.md`; all six ADRs in `docs/adr/`; CI workflow steps match the gate-commands list.

## Verdict rationale

All nine round-1 findings are RESOLVED with no silent narrowing; the folds introduced no defect that could corrupt the decision this spec gates. The three advisories are optional wording/completeness improvements, each already backstopped by an acceptance criterion or harmless as written. Under the rising bar this is a certification, with the advisories folded as advisories.

Unverified-offline: 3 (the §3–§5 trigger/holdout eval runs require the `claude` CLI with credentials; the §2 stale-index rejection demo and the §7 fixture-consumer `pre-commit run` are mutating/network operations this read-only pass could not perform)
PREMORTEM-VERDICT: CERTIFIED — reviewer: pre-mortem-review-r2 (fresh subagent, non-author)

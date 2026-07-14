# Complexity Scoring Rubric

This rubric defines how to score a development task for model routing. The
score is 0-100, mapping to three tiers. Apply it mentally as you write or
read each task -- no external tool needed.

Ported near-verbatim from the predecessor cycle's calibrated rubric; the
worked calibration (trivial-task override, cross-shape floor, verification
discount) carries observed-run evidence and moves only on new calibration
evidence.

---

## Score Ranges and Tier Mapping

| Score  | Tier   | Character                                    |
|--------|--------|----------------------------------------------|
| 0-25   | weak   | Mechanical, pattern-following, single-file    |
| 26-55  | mid    | Multi-step, moderate reasoning, coordination  |
| 56-100 | strong | Deep reasoning, novel design, expert domain   |

> **Thresholds and model assignments live in [`../models.toml`](../models.toml)**
> -- data, calibratable, refreshed by `/refresh-models`. This file defines
> *how to score*; `models.toml` defines *what runs*.
>
> A fourth opt-in tier (`frontier`) exists above strong but is **never
> assigned by score** -- the author opts in manually. See the skill body for
> the criteria.

---

## Pre-check: Trivial Task Override

Before applying the point system, check: **does this task involve any
logic at all?** If the task is purely text substitution, config edits,
version bumps, typo fixes, or boilerplate documentation with no
conditional logic, start from a **base of 15** instead of 30.

This unlocks the 0-14 score range for truly mechanical work and prevents
simple tasks from clustering near the weak/mid boundary.

| Task type                                    | Base |
|----------------------------------------------|------|
| Has any logic, reasoning, or design decision | 30   |
| Pure text/config change, zero logic           | 15   |

---

## Cross-shape floor (root-cause locality)

Before the additive signals below, check whether this task is *cross-shape*: its
correctness depends on a site the prompt does NOT point at. The triggers key on
**what the prompt covers**, not on file counts -- a task can span many files and
not be cross-shape, or touch one file and be cross-shape.

If ANY trigger fires, **replace the score with 26** (the bottom of `mid`) when the
additive total is lower. The floor only ever raises a sub-26 score into `mid`; it
never lowers a task already at `mid`/`strong`, and it does NOT add to the additive
total -- deeper reasoning still scores up through the normal axes, so a genuinely
hard cross-shape task can land well above 26. A floored task is `mid` at `medium`
confidence by default; the low-confidence tier-bump below still applies, but reserve
`low` (which bumps mid -> strong) for a cross-shape task that is ALSO irreducibly
single-pass-hard -- not one merely uncertain because the prompt is thin (a thin
prompt is a reason to fire the floor, not to bump past mid).

| Trigger -- any one fires the floor                                            |
|-------------------------------------------------------------------------------|
| **Uncovered displaced cause** -- the fix must land in a different file/function/layer than where the symptom is observed, AND the prompt points only at the symptom site (if the prompt already names the fix site, this does not fire) |
| **Uncovered shared-helper fan-out** -- the change is to shared / common / helper / base code, AND the prompt does not enumerate every caller that must stay correct (you need not know the exact count; if you cannot name all consumers from the prompt, treat it as fired) |
| **Uncovered backend / parity** -- two or more implementations (backends, dialects, code paths, an ETL-vs-serving pair) must produce equivalent results, AND at least one is not named in the prompt as an edit site (if the prompt names every implementation to change, that is breadth, not cross-shape -- do not fire) |

Every trigger keys on a site the prompt does NOT point at -- the *relationship*
between symptom and fix, not how many files or modules the task spans. A change
spread across many modules that are all the obvious, named edit sites is NOT
cross-shape; raw breadth or repo size never triggers this floor.

---

## Scoring Signals

Evaluate these signals and add/subtract points. Start at the appropriate
**base** (15 or 30 per the pre-check above), then adjust.

### Task structure (+0 to +25)

**"Files" means code files requiring distinct logic**, not data files
read/written. A script that reads 7 CSVs and writes 11 parquets is one
code file touching many data files -> score based on the script's logic,
not the number of data files.

| Signal                              | Points  |
|-------------------------------------|---------|
| Single-file change, clear pattern   | +0      |
| 2-3 files, straightforward logic    | +5      |
| 4+ files or cross-module            | +10     |
| Multi-system coordination           | +15     |
| Requires architectural decisions    | +20-25  |

### Reasoning depth (+0 to +25)

| Signal                              | Points  |
|-------------------------------------|---------|
| Copy/paste with substitutions       | +0      |
| Sequential steps, clear order       | +5      |
| Conditional logic, branching paths  | +10     |
| Trade-off analysis needed           | +15     |
| Novel algorithm or proof-like work  | +20-25  |

### Domain specificity (+0 to +15)

**Testing discount:** When writing tests for existing domain logic (not
implementing it) and the test cases are specified in the prompt, reduce
domain score by one level (e.g., +8 -> +5, +12 -> +8).

| Signal                              | Points  |
|-------------------------------------|---------|
| Generic CRUD / utilities            | +0      |
| Standard framework patterns         | +3      |
| Domain-specific rules               | +8      |
| Regulatory / compliance             | +12-15  |

### Context dependency (+0 to +10)

| Signal                              | Points  |
|-------------------------------------|---------|
| Self-contained, no external context | +0      |
| Needs awareness of codebase style   | +3      |
| Needs domain knowledge not in prompt| +7      |
| Needs both codebase + domain        | +10     |

### Output size (+0 to +5)

**Cap rule:** If reasoning depth scored +0 (copy/paste), output size is
capped at +0 regardless of actual length. Long boilerplate is still
boilerplate -- length does not imply cognitive complexity.

| Signal                              | Points  |
|-------------------------------------|---------|
| Short (< 50 lines of code)         | +0      |
| Medium (50-150 lines)              | +2      |
| Long (150-400 lines)               | +3      |
| Very long (400+ lines)             | +5      |

### Adjustment factors (-15 to +10)

| Signal                              | Points  |
|-------------------------------------|---------|
| Has mechanical verification (tests) | -5      |
| Clear, specific acceptance criteria | -5      |
| Boilerplate / template work         | -5      |
| Ambiguous requirements              | +5      |
| Security-sensitive code             | +5      |
| Performance-critical path           | +5      |

---

## Quick Heuristic Shortcuts

For speed, you can also pattern-match on keywords:

**Likely weak (0-25):**
- add field/column, rename, format, fix typo, bump version, add test for
  simple function, scaffold/template, change label/text, update docs,
  simple migration, add env var, boilerplate endpoint

**Likely mid (26-55):**
- refactor, pipeline, integrate API, migrate data, aggregate/transform,
  error handling, validation logic, multi-file change, webhook handler,
  batch processing, query optimization, add caching layer

**Likely strong (56-100):**
- architect, design system, regulatory/compliance, security audit, optimize
  performance, concurrent/race condition, novel algorithm, distributed system,
  consensus protocol, complex state machine, multi-stage migration with
  rollback, ML model integration with feature engineering

---

## Confidence Assessment

After scoring, also assess your confidence:

| Confidence | Meaning                                              |
|------------|------------------------------------------------------|
| high       | Clear signals, unambiguous task, confident in tier    |
| medium     | Some ambiguity, could be one tier higher or lower     |
| low        | Significant unknowns, recommend erring toward stronger|

**When confidence is low**, bump the tier up by one level, capping at strong
(`frontier` is never auto-assigned). The cost of a retry (wasted call +
developer time reviewing bad output) exceeds the cost difference between
tiers.

---

## Worked Examples

### Example 1: "Add an `updated_at` timestamp column to the `users` table"

- Pre-check: pure DDL/config change -> **base 15**
- Task structure: single-file, single table -> +0
- Reasoning: copy/paste with substitution -> +0
- Domain: generic CRUD -> +0
- Context: self-contained -> +0
- Output: short -> +0
- Adjustments: clear criteria (-5), boilerplate (-5)
- **Total: 15 + 0 - 10 = 5 -> weak, confidence: high**

### Example 2: "Refactor sales report query to two-step CTE with role-based filtering"

- Pre-check: has logic (CTE design, JOIN reasoning) -> **base 30**
- Task structure: 1-2 files, needs JOIN logic -> +5
- Reasoning: conditional logic (CTE ordering, filter rules) -> +10
- Domain: standard framework pattern -> +3
- Context: needs awareness of table schemas -> +3
- Output: medium -> +2
- Adjustments: clear criteria (-5)
- **Total: 30 + 5 + 10 + 3 + 3 + 2 - 5 = 48 -> mid, confidence: high**

### Example 3: "Design a multi-stage document approval state machine with audit trail and rollback"

- Pre-check: has deep logic -> **base 30**
- Task structure: multi-module, needs integration -> +15
- Reasoning: complex conditionals, state transitions -> +20
- Domain: domain-specific rules (approval workflows) -> +8
- Context: needs both codebase + domain -> +10
- Output: long -> +3
- Adjustments: security-sensitive (+5)
- **Total: 30 + 15 + 20 + 8 + 10 + 3 + 5 = 91 -> strong, confidence: high**

### Example 4: "Fix the trailing-zero formatting in the exported report total"

- Pre-check: trailing-zero trimming is conditional logic, not pure text
  substitution -> **base 30** (a rater who reads it as a pure "format" task starts
  at base 15 -> total 8; either way it is weak before the floor)
- Task structure: the prompt names one file (`report.py`) -> +0
- Reasoning: looks like a small formatting fix -> +0
- Domain: generic utilities -> +0
- Context: needs codebase awareness -> +3
- Output: short -> +0
- Adjustments: clear criteria (-5), has tests (-5)
- Additive total: 30 + 3 - 10 = 23 -> weak
- **Cross-shape floor:** the real fix is a shared `format_amount` helper whose
  callers are not all named in the prompt (uncovered shared-helper fan-out), so a
  fix touching only `report.py` can leave other consumers wrong -> **replace with 26
  -> mid, confidence: medium**
- Lesson: the prompt's surface (one named file, short) scored weak; the *defect
  shape* (a shared helper the prompt did not point at) set the tier.

### Example 5: "Rename `legacy_id` to `external_id` across all 6 model files (listed below) and their references"

- Pre-check: pure rename, no logic -> **base 15**
- Task structure: 6 files -> +10
- Reasoning: copy/paste substitution -> +0
- Domain: generic -> +0
- Context: needs codebase awareness -> +3
- Output: short -> +0
- Adjustments: clear criteria (-5)
- Additive total: 15 + 10 + 3 - 5 = 23 -> weak
- **Cross-shape floor: does NOT fire.** The change fans out across 6 files, but the
  prompt *enumerates every file and reference* -- coverage is complete, so this is
  breadth, not cross-shape. Raw file count never fires the floor.
- **Final: weak, confidence: high.** Contrast with Example 4: same surface tier, but
  there the fix site was *uncovered* (a shared helper the prompt did not name) -> mid;
  here every site is named -> weak. The floor keys on coverage, not breadth.

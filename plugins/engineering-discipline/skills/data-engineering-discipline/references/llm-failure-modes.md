# LLM Failure Modes in Data Engineering

This skill is consumed by an LLM workflow. LLMs introduce specific failure
modes that mechanical discipline must defend against, because the agent
will not self-correct without scaffolding.

The dominant pattern is **plausible-but-wrong code**: output that compiles,
runs, and produces believable numbers while silently changing meaning. SQL
is especially dangerous because failures don't throw — they return numbers
that look fine. The defense is always mechanical: contracts, parity diffs,
CI gates, hooks — never social ("the agent should know better").

For each failure mode below, four parts:

1. **Mode** — what goes wrong.
2. **Detection** — how to spot it happening (signals to watch for).
3. **Defense** — the mechanical countermeasure.
4. **Concrete example** — drawn from real cases.

---

## Mode 1 — Plausible-but-wrong code

**The pattern.** The agent generates SQL or Python that compiles, runs,
and produces output that looks reasonable to a quick glance. Under
specific data conditions, it silently drops rows, coarsens groups,
mismatches dtypes, or applies a transformation that's subtly wrong.

**Detection signals.**

- Row count of new output is suspiciously close to but not exactly equal
  to the baseline row count.
- Aggregates differ by small percentages that get hand-waved as "rounding."
- Edge-case partitions (month-end, year-end, leap days) show larger
  deviations than typical partitions.
- The agent says "the data looks right" without having run a diff.
- New code "works on the sample" but the sample is hand-crafted.

**Defense.**

- Row-level + aggregate parity diff against the baseline output as a
  non-negotiable done-gate. The baseline is the legacy output for a
  migration, the current output for a refactor, the declared contract
  for a new dataset, the last-known-good output for an investigation.
  See `parity-recipes.md`.
- Schema diff (columns + dtypes) before any data comparison.
- "Looks reasonable" is forbidden as a done-criterion. Looks reasonable
  is the *weakest* test pyramid layer; it cannot replace contract checks
  or parity diffs.

**Example (migration form).** Migration silently changes the output of
a daily aggregate. Row count: existing 69,449, new 31,032. Aggregates:
existing total amount $4.2M, new total $4.2M. The agent reports "totals
match, looks good." The row count delta means each row in the new output
represents a coarser grouping than before. The total matches because
aggregation is associative; the per-row meaning has silently changed.

**Example (new-dataset form).** The first run of a new pipeline
produces 50,000 rows. The agent says "that's a reasonable volume for a
customer dimension." A row-count check against the source (which has
55,000 distinct customers) would reveal 5,000 customers silently
dropped by a join condition.

---

## Mode 2 — Plan drift / context truncation

**The pattern.** In multi-turn sessions, the agent writes a plan early
based on a quick read of the existing code (or upstream data, or
upstream spec). The plan becomes the source of truth as the
conversation progresses. Code is built against the plan rather than
against the primary source. When the plan was lossy — and it always is
— the build inherits the loss.

This is the dominant LLM failure mode across all scenarios. In
migrations and refactors, the plan misses corner-case branches in
existing code. In new-dataset work, the plan misses corner-case values
in source data. In schema-evolution work, the plan misses the current
materialized schema (vs. the schema YAML).

**Detection signals.**

- The agent references the "plan" or "task list" when justifying a code
  decision, rather than the primary source (code, data, or spec).
- The agent says "as we discussed earlier" about details that were
  inferred, not verified.
- The agent has not re-opened the primary source file in the last
  several turns.
- The session is long; context is summarized; specific column names or
  identifiers are paraphrased rather than quoted.
- "Integrate X later" appears in the plan and X never returns.

**Defense.**

- **Re-read the primary source at the start of each phase**, regardless
  of confidence. The plan is a notepad; the source is the contract.
- For multi-day work, re-establish context at the start of each session
  by reading source files, not by reading conversation summaries.
- The plan tracks intent; the primary source tracks reality. When they
  disagree, reality wins.

**Example (migration form).** A real migration had a plan that captured
"orders + revenue data" as one input. The actual source script extracted
TWO tables. The agent deferred the second indefinitely; the `revenue`
column silently disappeared from output. A migration like this can take
dozens of commits to chase the gap back down.

**Example (new-dataset form).** The plan describes a source as
"customer events." The actual source has three distinct event types
with different shapes. The new pipeline handles only the first type
and silently drops the others.

---

## Mode 3 — "Improving while executing a scope-bounded task"

**The pattern.** The agent reflexively renames columns for clarity,
simplifies schemas, refactors architecture, splits modules — during
any task whose scope was supposed to be bounded. Each individual change
is a legitimate engineering choice in isolation. Bundled into a
scope-limited task, they are silent regressions.

This is the universal form of "improving while migrating." It applies
to migrations (where the scope is bug-for-bug parity), refactors (where
the scope is no functional change), schema-evolution PRs (where the
scope is one specific change), and bug-fix PRs (where the scope is the
bug, not adjacent cleanup).

**Detection signals.**

- The agent describes a code change as "cleaner," "more consistent," or
  "more pythonic" during a scope-bounded task.
- Column names in the new output don't match the existing output
  exactly (in a migration or refactor).
- Group keys in the new aggregate are a subset of the existing keys.
- A "redundant" column or group key is dropped without a divergence
  document.
- The agent says "I noticed this was suboptimal and fixed it" without
  having asked first.
- The PR's diff is larger than the stated scope implies.

**Defense.**

- Explicit **improvement-freeze rule** in the scope-bounded task's
  agent instructions: improvements are deferred to a backlog file
  (`IMPROVEMENTS.md`) consulted after the scoped task completes.
- Every code change in a scope-bounded PR must map to either:
  (a) a baseline-preserving translation,
  (b) a documented divergence in the appropriate artifact
      (`MIGRATION_NOTES.md`, `CONTRACT_CHANGELOG.md`) with sign-off,
  (c) an item on the post-task improvements backlog.
- Parity gate enforces no column renames during migrations / refactors.
- For new-dataset and schema-evolution scenarios, the analogous gate is
  contract conformance: the producer's output matches the declared
  contract exactly.

**Example (migration form).** A migration silently renames `unit_cost
→ uc`, `base_fee → base_fee_amt`, `margin_raw → margin`. Each
rename looks reasonable — shorter, more consistent. Downstream Excel
workbooks keyed on the original names break the next morning.

**Example (refactor form).** A "pure refactor" PR also tightens a
constraint from `nullable: true` to `nullable: false` because "the data
doesn't seem to have nulls." The next month-end batch hits the null
case and the pipeline fails.

**Example (new-dataset form).** The declared contract says `tier` is
one of `bronze`, `silver`, `gold`, `platinum`. The producer writes
`diamond` too because "the source has that value." The contract drifted
from the implementation; downstream consumers crash on the new value.

---

## Mode 4 — Synthetic-fixtures-only validation

**The pattern.** The LLM writes both the production code and the test
fixtures. The fixtures satisfy the code's assumptions because the same
mind generated both. The unit tests pass at high coverage. Real
production data fails immediately because production data violates
assumptions the LLM didn't think to encode in fixtures.

**Detection signals.**

- Test coverage is very high (>90%) and tests were written by the LLM.
- Fixtures are small (single-digit row counts) and hand-crafted.
- Tests pass deterministically every time.
- The agent has not run the code against production-shaped data.
- All edge cases tested are "obvious" edge cases (null, empty); none
  reflect actual production distributions.

**Defense.**

- Pair every LLM-generated unit test suite with a real-data integration
  test that uses fixtures **the LLM did not generate** — sampled directly
  from production.
- Required staging run on at least the last 30 days of production data
  before declaring done.
- Every constraint declared in the schema must be validated against
  production data (see Principle 10).

**Example.** Schema declares `nullable: false` on `rate_frag`, `uc`,
`margin`, `base_fee_amt`. Every unit test passes (fixtures had no
nulls). First staging run fails: adjustment coverage gaps produce null
`uc`; same-day operations have `tenure_days=0` → division by zero →
null. The constraints were drafted from "what makes sense," not from
"what production data actually looks like."

---

## Mode 5 — Confabulated signatures and identifiers

**The pattern.** The agent generates plausible function calls with
wrong parameter names, wrong return types, or non-existent string
identifiers. The patterns come from training-data priors, not from the
current installed version of the library.

**Detection signals.**

- The agent calls a function it hasn't called recently in the session.
- The agent uses a string identifier (calendar name, source name, schema
  name) without first listing the registry.
- The agent uses keyword arguments with names that "sound right" but
  weren't verified.
- Runtime errors of the form `TypeError: unexpected keyword argument
  'rtol'` or `KeyError: 'calendar_c'`.

**Defense.**

- For any unfamiliar primitive, **a 10-line smoke script using
  `inspect.signature(fn)` is a required first step**:

```python
import inspect
from mylib.compute import weighted_average
print(inspect.signature(weighted_average))
# Now you know the actual parameter names.
```

- For any string identifier, enumerate the registry first:

```python
from mylib.calendars import list_calendars
print(list_calendars())
# ['calendar_a', 'calendar_b', ...]
```

- Treat every keyword argument as suspect until verified.

**Example.** A single migration phase produced eight signature
confabulations caught at runtime:

| Confabulated | Actual |
|--------------|--------|
| `assert_frame_equal(rtol=...)` | `rel_tol=` |
| `weighted_average(keys=...)` | `group_cols=` |
| `business_date_range(...)` returns `Date` | Returns `Datetime[μs]` |
| `WindowSpec(as_of_date=Series)` | Takes `Sequence[date]` |
| `apply_adjustment(...)` for resample | Use `resample_bulk` |
| `resample_bulk(value_col=...)` | `@singledispatch`, positional only |
| Output col == input col name | Output col literally `'interpolated'` |
| Calendar `'calendar_c'` | Registry has `'calendar_a'` |

Each cost a debug round. Total cost: hours. Cost of `inspect.signature`
per primitive: 30 seconds.

---

## Mode 6 — "Looks reasonable" as the done-gate

**The pattern.** The agent runs the pipeline, eyeballs the output, sees
plausible numbers, declares done. Skips the test pyramid layers entirely.

**Detection signals.**

- Done-claim arrives before the parity diff has run.
- Done-claim references "the data looks correct" or "the totals match"
  without specific numerical comparisons.
- No mention of contract checks, unit tests, or parity gates.
- The agent has run the pipeline exactly once.

**Defense.**

- The pre-shipping checklist in `SKILL.md` is the active gate. If any
  item cannot be answered "yes," the work is not done.
- "Looks reasonable" is the production-observability layer of the test
  pyramid — the *weakest* gate. It cannot substitute for contract or
  parity gates.
- For migrations and refactors: row-level diff against the baseline is
  the done-gate, not eyeballing. For new datasets: contract conformance
  + real-data integration test. For schema evolutions: compatibility
  check + consumer notification.

**Example (migration form).** In the session that motivated this
skill, three earlier moments declared "done" before parity tests
revealed schema divergences. Each "done" claim was based on "the
pipeline runs and the data looks reasonable." Each time, a parity diff
was deferred. Each time, the parity diff — when finally run — found a
regression.

**Example (new-dataset form).** The agent ships a new pipeline,
declares done because "the rows look right." A later constraint check
against 90 days of production data reveals 200 violations of a declared
`not_null` constraint. The eyeball test missed what the constraint
check would have caught immediately.

---

## Mode 7 — Confidence miscalibration / no escalation under uncertainty

**The pattern.** The agent has no instinct to escalate when uncertain.
It confabulates with the same fluent confidence as when correct. A
junior engineer would say "I'm not sure — can you clarify?" An LLM
ships.

**Detection signals.**

- The agent makes a decision based on ambiguous spec text without
  flagging the ambiguity.
- The agent picks a default when multiple interpretations are reasonable,
  without surfacing the choice.
- The agent's code review responses say "I made this choice because…"
  retroactively, rather than "I'd like to ask…" proactively.

**Defense.**

- Encode the ambiguity-flagging requirement in agent instructions: when
  spec text is ambiguous, stop and ask before proceeding.
- Code review checklist: every defaulted choice the agent made is
  re-validated by a human before merge.
- For high-risk areas (contracts, schema changes, migrations), require
  explicit sign-off on every interpretation.

**Example (migration form).** "Match the legacy output" leaves dozens
of small choices — exact dtype representation, exact ordering of group
keys, exact null behavior on edge cases. An LLM resolves each silently.
A human-in-the-loop reviewer would catch divergences before they ship;
an LLM left alone produces a migration that compiles but doesn't match.

**Example (new-dataset form).** A contract spec says `tier` is one of
"bronze, silver, gold, platinum." The source data also has `enterprise`
and `trial` values. The LLM either silently buckets them into the
declared enum (wrong) or fails on every row (better, but disruptive).
The right move is to flag the discrepancy before writing the
transform.

---

## Mode 8 — Plan-as-spec drift across sessions

**The pattern.** Across multiple sessions (or after context
truncation), the agent loses track of the *original* contract (legacy
contract for a migration, source-data shape for a new dataset, current
contract for a schema evolution) and works from session-summary
surrogates. Subsequent sessions inherit distortions from earlier ones.

**Detection signals.**

- Multi-session work where the second-session agent never re-reads the
  primary source files (existing code, source data, contract YAML).
- Session-handoff summaries that paraphrase rather than quote.
- Column names mentioned in handoff don't exactly match column names in
  the primary source.
- Disagreement between sessions on what the contract "is."

**Defense.**

- Session handoff includes primary-source file references, not just
  summaries. Subsequent sessions re-read the files.
- Persist the baseline (schema, row count, aggregates, declared
  contract) as a versioned artifact in the repo. Subsequent sessions
  diff against the artifact, not against memory.
- Treat `MIGRATION_NOTES.md` / `CONTRACT_CHANGELOG.md` as the
  authoritative log of intentional changes. Anything not in it is an
  unintentional divergence to investigate.

**Example (migration form).** A two-week migration spans many
sessions. By session five, the agent is convinced that `payment_method`
was always excluded from the group-by because session three "decided"
that. Session three actually deferred the decision, with a TODO.
Session one's plan listed `payment_method` as a required group key.
Reading the legacy code (which no session did after session one) would
have ended the confusion in thirty seconds.

**Example (schema-evolution form).** A long-running schema-evolution
project spans many sessions. The contract YAML was updated in session
two to add a `customer_tier_v2` column. Session five sees only the
session-summary mention of "tier work" and produces code that writes
to the deprecated `customer_tier` column. Reading the current
contract YAML would have caught the staleness immediately.

---

## Cross-mode patterns

Several failure modes share common roots:

**"The agent prefers reasoning over data inspection."**
Modes 1, 4, 6, 7, 8 all reflect this. The defense pattern is identical
across them: require concrete data inspection at specific gates. The
parity diff is the data-inspection gate that covers all five modes.

**"The agent treats summarized context as ground truth."**
Modes 2, 5, 8 share this. The defense pattern: re-read primary sources
(existing code, library signatures, contract YAML, source data) rather
than trusting session summaries.

**"The agent improves what it shouldn't and accepts what it shouldn't."**
Modes 3, 7 share this. The defense pattern: explicit instructions about
when to defer to the user vs. when to act.

---

## Mechanical defenses summary

Every mode above is defended by one or more of these mechanical layers:

| Defense | Modes addressed | Implementation |
|---------|----------------|----------------|
| Row-level + aggregate parity diff | 1, 3, 4, 6 | See `parity-recipes.md` |
| Schema diff in CI | 1, 3 | dbt `state:modified`, custom scripts |
| Contract enforcement | 1, 3, 4 | dbt contracts, ODCS YAML |
| Re-read primary sources each phase | 2, 5, 8 | Agent-instructions rule |
| `inspect.signature` smoke script | 5 | Required before unfamiliar primitive |
| Registry enumeration before identifier use | 5 | Required before string identifier use |
| Production-data constraint validation | 4 | Pre-flight queries in `principles.md` Principle 10 |
| Real-data integration tests | 4 | Required staging run before "done" |
| Improvement-freeze rule | 3 | Explicit in agent instructions |
| Documented divergences (MIGRATION_NOTES) | 3, 7, 8 | Required artifact |
| Ambiguity-flagging requirement | 7 | Agent instructions: ask before defaulting |
| Pre-shipping checklist | 6, all | `SKILL.md` |

None of these defenses rely on the agent's self-assessment. All are
mechanical: code, files, CI gates, runnable scripts. **Make the
discipline mechanical, not social.**

---

## The "LLM as junior engineer" framing — and where it breaks

The transferable discipline patterns from teaching juniors:

- Code review.
- Conventions docs (CLAUDE.md, AGENTS.md).
- Pre-commit hooks.
- CI gates.
- Pair programming.

Where the analogy breaks down:

- A junior engineer has **shame** about silent breakage. An LLM has none.
- A junior engineer **escalates** when uncertain. An LLM confabulates
  with the same fluent confidence.
- A junior engineer **remembers** yesterday's conversation. An LLM's
  context window forgets.
- A junior engineer can **detect their own confusion**. An LLM cannot
  distinguish certainty from confidence.

The corrective: every place where a junior engineer's instinct would
catch a problem, the LLM workflow needs a mechanical replacement. Schema
diff catches what the junior's eye would catch. Parity diff catches what
the junior's "wait, that doesn't look right" would catch. CI gates catch
what the junior would escalate. Hooks catch what the junior would
double-check.

This is what "make the discipline mechanical, not social" means in
practice. The discipline exists because the agent cannot supply it
itself.

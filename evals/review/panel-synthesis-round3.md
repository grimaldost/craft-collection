# Skill design review — round-3 panel (post-correctness-fix)

Four fresh Opus reviewers (MINIMALIST, AUDITOR, ADVOCATE, DOMAIN-EXPERT), each
scoring all **seven** skills blind to each other and to the behavioral eval, using
the same rubric as round-1 (`skill-design-review-prompt.md`). Run after the round-2
correctness pass, specifically to see whether the fixes moved the verdicts. Agent
ids: a35608e126263cf0b · a1795587c2c347743 · ab34bc5248cdf21fd · a32a3229dda306d6f.

## Verdict matrix (Worth-it / Design, out of 10)

| Skill | MINIMALIST | AUDITOR | ADVOCATE | DOMAIN-EXPERT | Consensus |
|---|---|---|---|---|---|
| journaling-sessions | KEEP 8/7 | KEEP 9/9 | KEEP 8/8 | KEEP 9/8 | **KEEP — unanimous, top-3 all** |
| review-panel *(new)* | KEEP 8/8 | KEEP 9/9 | KEEP 9/9 | KEEP 8/8 | **KEEP — unanimous, top-tier** |
| data-engineering-discipline | REVISE 7/5 | KEEP 9/8 | KEEP 9/8 | KEEP 9/8 | **KEEP — highest worth-it (9×3)** |
| toolkit-awareness | KEEP 7/8 | KEEP 8/9 | KEEP 7/8 | KEEP 8/8 | **KEEP — unanimous (was REVISE×3)** |
| refresh-stack | KEEP 7/9 | KEEP 7/9 | KEEP 7/9 | KEEP 7/9 | **KEEP — unanimous, cleanest design** |
| python-engineering | REVISE 6/6 | KEEP 8/7 | REVISE 6/7 | KEEP 8/9 | KEEP — but trim the body |
| context-handoff | REVISE 5/8 | KEEP 7/8 | KEEP 8/9 | KEEP 7/9 | KEEP — best-designed, thinnest value |

Mean worth-it / design: journaling 8.5/8.0 · review-panel 8.5/8.5 · data-eng 8.5/7.25
· toolkit 7.5/8.25 · python-eng 7.0/7.25 · refresh-stack 7.0/9.0 · context-handoff 6.75/8.5.

## The headline: the round-2 fixes are independently confirmed

**toolkit-awareness flipped from REVISE×3 → KEEP×4.** In round-1 three reviewers
ran `scan_toolkit.py`, got empty results, and docked it for a real bug (the scan was
blind to plugin-packaged components — exactly the packaging model the skills ship
in). This round, reviewers independently verified the *fix*: AUDITOR — "it genuinely
shells out to `claude plugin list --json`, parses the `id`→`plugin@marketplace`
shape, pulls descriptions from `.claude-plugin/plugin.json`, and degrades to `[]` on
any CLI failure." The headline bug is gone, and the verdict moved with it.

Two more fixes were confirmed by the blind panel without being told to look:
- **data-eng dbt claim** (DOMAIN-EXPERT): "correctly states that dbt `contract:
  enforced` validates names and dtypes but does *not* enforce `constraints` at build
  — a subtle, frequently-misstated fact." That's the flat-wrong claim we corrected.
- **python-eng `is_behind` 0ver fix** (DOMAIN-EXPERT + AUDITOR): "a genuinely
  sophisticated touch — most authors would miss that comparing only major.minor
  makes every 0.0.x release invisible to drift." That's the ty-blindness fix.

No reviewer found the round-1 content bugs (the Polars Recipe-6 contradiction, the
plugin-blind scan) — they're fixed. **Zero CUT verdicts**, again, from any lens —
including the ruthless minimalist.

## Where the panel agreed (the standing recommendations)

1. **The two big skills carry too much always-loaded prose.** Unanimous-ish: both
   `python-engineering` (401-line body) and `data-engineering-discipline` (~300-line
   body + ~3,900 lines of references) restate base-model knowledge and repeat their
   core axioms 2–3× across SKILL.md + references. Fix = aggressive progressive
   disclosure: thin body (decision rules, version-deltas, checklist, scripts), push
   the reconstructable philosophy entirely into references. This is the dominant
   collection-wide note — and it is exactly the editorial trim deferred in round-2.
2. **A consolidation / "meditation" skill is missing.** THREE of four independently
   flagged it: journaling explicitly writes raw input for a downstream "cluster →
   promote into durable guidance" pass that no skill performs — "a user adopting
   journaling has a dangling promise." The clearest candidate for a new skill.
3. **Descriptions keyword-stuff** (AUDITOR): the auto-firing skills front-load long
   trigger-phrase lists that bury the discriminating value proposition; lead with
   *what the skill uniquely does*, trail the phrase list.
4. **Surface the runnable scripts earlier** (ADVOCATE, on data-eng + python-eng):
   the scripts are the concrete payoff but sit near the end of the bodies.
5. **Cross-link the shared "neutral brief" technique** between context-handoff and
   review-panel instead of re-deriving it in each.

## Where they split (the judgment calls)

- **context-handoff** — MINIMALIST REVISE 5/8 ("closest to pure base-model
  behavior; cut the worked examples"); the other three KEEP 7–8/8–9 ("the skill I'd
  be most reliably glad to see fire," ADVOCATE). Elegant + safe vs. thin marginal
  lift. If one skill were ever cut, all four name this one — but none actually cuts it.
- **python-engineering** — MINIMALIST/ADVOCATE REVISE on bloat + over-broad trigger;
  AUDITOR/DOMAIN-EXPERT KEEP 8/ and praise its currency ("I found essentially no
  staleness"). The split is "trim the lecture" vs. "the specifics are gold" — both
  true, and they target different lines (cut philosophy, keep version-deltas+scripts).
- **data-engineering-discipline** — DOMAIN-EXPERT/AUDITOR/ADVOCATE rank it #1–2 for
  forensic, money-saving, *correct* content; MINIMALIST REVISE 7/5 purely on volume.
  Worth-it is not in question; design (footprint) is.

DOMAIN-EXPERT also flagged two minor python-eng over-reaches worth a look: "src
layout is mandatory for *all* projects" is stronger than ecosystem consensus, and the
"ty 10-100× faster than mypy" figure quotes vendor numbers as fact (the skill marks
vendor claims elsewhere — be consistent). And suggested a possible **SQL-correctness /
query-review** skill as a second gap ("the data discipline guards the contract but
stops at the warehouse boundary").

## Collection verdict (synthesis)

Unanimous across lenses: a **coherent, well-separated, genuinely useful set** — two
clean plugins (session-workflow = capture/handoff/inventory/review; engineering-
discipline = Python standards + data-contract guardrails + the freshness loop that
maintains them), with real cross-wiring and low harmful overlap. The authors "clearly
understood the currency problem" (DOMAIN-EXPERT) — volatile facts externalized to
`stack.toml` + dated citation blocks, with a real `/refresh-stack` loop to keep them
honest — and the bundled scripts are genuinely engineered (stdlib-only, graceful
degradation, `parity_check.py` even prints its own blind spot). The one dominant
weakness is **footprint, not redundancy or misfire**: the two discipline skills bet
the model reads carefully when it will skim. The set is "one editing pass away from
being tighter than it is comprehensive" (MINIMALIST). Two gaps named: the
consolidation/meditation pass (3 of 4), and possibly a SQL-review skill (1).

## Round-1 → round-3 delta

- **toolkit-awareness: REVISE×3 → KEEP×4** (the plugin-blind bug we fixed).
- **review-panel: new → unanimous KEEP, top-tier (8–9 / 8–9)** — productizing the
  panel validated; it even reviewed itself well.
- data-eng, journaling: unchanged top tier; the round-1 content bugs are gone.
- python-engineering, context-handoff: unchanged shape — the bloat/thinness notes
  persist because the round-2 pass deliberately deferred the editorial trims.

## Method note

Run via 4 parallel Agent calls (free-text output), not a schema-forced workflow —
clean, zero StructuredOutput failures (cf. the round-2 workflow, which needed two
runs). For a panel whose value is rich prose judgment, free text beats forced schema.

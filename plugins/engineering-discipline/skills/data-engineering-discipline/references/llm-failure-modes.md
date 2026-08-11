# LLM Failure Modes in Data Engineering

This skill is consumed by an LLM workflow. LLMs introduce specific failure
modes that mechanical discipline must defend against, because the agent
will not self-correct without scaffolding.

The dominant pattern is **plausible-but-wrong code**: output that compiles,
runs, and produces believable numbers while silently changing meaning. SQL
is especially dangerous because failures don't throw — they return numbers
that look fine. The defense is always mechanical: contracts, parity diffs,
CI gates, hooks — never social ("the agent should know better").

Two modes are catalogued here, and the numbering is historical so older
citations still resolve. Modes 1–8 were retired in 2026-08: they described
generic LLM hygiene that a current base model supplies unprompted, and across
fourteen exercise reports not one cited them. Modes 9, 10, 12 and 13 moved to
`humblepowers:verification-before-completion`
(`references/evidence-fabrication.md`) — fabricated telemetry, confabulated
anchors, silence read as status, fail-open tooling. None is about data; the
clearest recorded instance of the last one diagnosed a defect in an eval
harness. They were paying rent inside a data skill, reachable only by someone
doing data work.

What stays is what the corpus cites and what is specific to producing a
dataset: a verifier that inherits none of the design's documented traps, and
a source read from the wrong copy of the code.

For each failure mode below, four parts:

1. **Mode** — what goes wrong.
2. **Detection** — how to spot it happening (signals to watch for).
3. **Defense** — the mechanical countermeasure.
4. **Concrete example** — drawn from real cases.

---

## Mode 11 — The verifier inherits none of the design's documented traps

**The pattern.** A design or spec documents a pattern trap (a regex that
matches only column-0 anchors and misses function-scoped imports; an enum
that must include a rare value). Then a *fresh* piece of verification or
pattern-matching code — a review script, a CI check, the run's own first
verifier — reproduces the exact trap the design warned about, because the
trap lived only in the design doc and the verifier's author (a different
agent, or the same agent in a different role) never read it.

**Detection signals.**

- A verifier / check / review script written from scratch in a wave whose
  design documents a relevant trap.
- Pattern-matching anchored on position (column 0, line start) rather than
  content.
- The trap is recorded in a design doc or ADR that the verifier's prompt
  does not include.
- "We documented this" used as if documentation were enforcement.

**Defense.**

- Put traps in the artifacts the verifier actually reads — the review
  prompt, a wave-output flag, the checker's own test fixtures — not only
  in the design doc.
- A documented trap is a candidate test case: encode it as a
  planted-failure fixture the verifier must catch, so a verifier blind to
  the trap fails its own self-test.
- Treat "the design documents X" as necessary, not sufficient: the
  question is whether the code that checks for X reads where X is written.

**Example.** A wave's design documented that a column-0-anchored regex
would miss function-scoped imports. The run's own first verification
script — written fresh for that wave — used a column-0-anchored regex and
missed exactly those imports. The trap was in the design doc; the verifier
read only its prompt.

---

## Mode 14 — Traced the wrong copy: editable-vs-installed / stale-cache divergence

**The pattern.** The agent debugs a behavior by reading source — but the
source it reads is not the code the process runs. The same library is present
twice: an editable checkout (`pip install -e`, a sibling repo on `PYTHONPATH`)
and an installed release in the venv, often at different versions with
different internals. The agent traces the editable copy, forms a confident
causal claim from it, and the claim is false because the *release* copy — a
different architecture — is what executed.

This is Axiom 2's blind spot at import resolution: reading source is only
observation if it is the source that ran. Mode 10 cites an anchor that doesn't
exist; this reads a real anchor that isn't the live one.

**Detection signals.**

- A behavior / regression claim ("the source has no 2026-06-16 branch", "this
  function returns X") with no `module.__file__` / version resolved first.
- The library is present editable AND as a release (a sibling checkout plus a
  venv install), or a stale `__pycache__` / cached wheel is in play.
- Logger names, class names, or code paths in the real run don't match the
  source being read (`facade._sink` runs while `manager._parquet` is read).
- "I verified by reading the code" — but the failing path was never run.

**Defense — resolve the loaded module before reading its source.**

- Before any source-based behavior claim, run
  `python -c "import m; print(m.__file__, getattr(m, '__version__', '?'))"`
  and read *that* file. The run's logs / emitted query / loaded-module path
  outrank the source tree.
- In editable / multi-repo / stale-cache setups, treat "I read the code" as
  unverified until the loaded path is confirmed.
- This is the data form of `systematic-debugging`'s "confirm the source you
  read is the code that runs."

**Example.** An "incremental load ran but the dataset didn't update to 2026-06-16"
regression: the agent traced an editable `warehouse-io 0.6.x` sibling and
asserted "the source has no 2026-06-16" — while the venv imported the `1.0.1`
release, a different read architecture. A direct query showed the date existed
(3,644 rows). One `import warehouse_io; print(__file__, version)` before
reading would have pre-empted pages of wrong inference.

---

## Cross-mode patterns

**"The agent fabricates evidence and presents it as observation."**
Mode 11 is the local form: the trap was documented, and the fresh verifier
reproduced it anyway, so "we documented this" was recorded as if it were
enforcement. The wider family — an invented event, a cited anchor never read,
an absence over-read as a verdict — lives in
`verification-before-completion`'s `references/evidence-fabrication.md`. The
shared root is Axiom 2: a signal *about* the system stood in for the system.

**"The agent treats summarized context as ground truth."**
Mode 14 is the sharpest data-side case, and the one a summary cannot fix by
being more careful: the primary source was re-read faithfully, and it was the
wrong copy. Confirm the source you re-read is the one that runs, not an
editable or cached twin.

---

## Mechanical defenses summary

Both modes above are defended mechanically, never by self-assessment:

| Defense | Mode | Implementation |
|---------|------|----------------|
| Traps in the verifier's own inputs | 11 | Review prompts, planted-failure fixtures, wave-output flags |
| A documented trap becomes a planted-failure fixture | 11 | `mutate_check.py` — a verifier blind to the trap fails its own self-test |
| Resolve the loaded module before a source claim | 14 | `which_copy.py`; the run's logs and loaded path outrank the source tree |
| Row-level + aggregate parity diff | both | See `parity-recipes.md` |
| Pre-shipping checklist | both | `SKILL.md` |

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

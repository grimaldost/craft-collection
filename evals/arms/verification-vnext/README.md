# verification-before-completion — vNext candidate arm

**Not shipped, and not shippable yet.** This directory holds a candidate body for
`verification-before-completion` as an experimental arm. The plugin's own copy is
unchanged and stays unchanged until each change below has its obligation
discharged. `test_vnext_arm.py` asserts that separation rather than trusting it.

Mount the directory next to a plugin root to run it: the arm is a complete skill
directory (`verification-before-completion/SKILL.md` plus its `references/`), so
an eval harness can point at it exactly as it points at the shipped skill. The
frontmatter `description` is byte-identical to the shipped one on purpose — the
contrast under test is the body diff, and a second moving part would make any
observed difference unattributable.

## What differs from the shipped body

Three procedures move out to `references/non-vacuity.md`; three rows arrive in
*What claims require*; one existing clause gains four words.

| # | change | why it is here and not in the plugin |
|---|---|---|
| body displacement | the exit-code-after-a-pipe mechanics, the byte-precise-restore mechanics, and the zero-net-regression baseline recipe move to a reference; each bright line stays | non-inferiority against the current body on the code class has not been measured. A shrink that costs footprint is not a free shrink |
| row: data output | a hard case and its expected value written down before the fix, recomputed by a path that does not reuse the transform | the data class has already returned one null for a wording change and one for a gate; a second null and the row comes out |
| row: doc/report claim | the cited span read whole — the file, not a line range | rests on two corpus instances of one failure mode, no measurement |
| row: a check ran | the count of units it saw, non-zero | the mechanism is already shipped in `scripts/run_tests.py`; the body row that names it is not measured, and a row on a rigid skill is a false-positive risk until it is |
| pristine output | extends to warnings and a jumped runtime, not only the pass count | two corpus instances, no positive test of its own; it rides the displacement's result and is labelled unmeasured either way |

Not here, on purpose: any tier-conditional clause. The register is rigid, the
ladder that would justify one is non-monotone and single-bank, and — the reason
that settles it — the harness cannot condition a skill's activation on a
subagent's model, so the sentence would name a decision nothing can act on. The
one place a tier fact is implementable is the gate hook's activation predicate,
where it sits inert and marked provisional. No config row either: no local bank,
no local trials, and shipping on literature alone is the defect this whole pass
exists to repair.

## Word-budget arithmetic

Measured with the repository's own counter (`scripts/word_budget.py`), which
counts whitespace-separated tokens in everything after the frontmatter.

| section | shipped | candidate | delta |
|---|---|---|---|
| preamble | 37 | 37 | 0 |
| The gate | 103 | 86 | −17 |
| What claims require | 143 | 223 | **+80** |
| Regression tests are red-green verified | 103 | 103 | 0 |
| A verifier is trusted green only after seen red | 137 | 102 | −35 |
| Delegated work | 28 | 28 | 0 |
| Finishing a change | 105 | 74 | −31 |
| Wording that signals an unverified claim | 32 | 32 | 0 |
| Boundaries | 57 | 57 | 0 |
| **body total** | **790** | **787** | **−3** |

Displaced 83 words, spent 80, net −3 against a recorded budget of 800. The body
gains three rows and still shrinks, so no baseline is bumped and the size
question never has to be argued.

**The design estimate did not hold, and it is written down rather than rounded
to.** The plan projected freeing about 130 words and landing near 720. The
procedures named were worth 83 once counted, because roughly a third of each
passage was the bright line that had to stay. The doctrinal requirement —
displace, never append — is met at −3; the projected shrink is not, and nothing
was cut to manufacture it. Chasing the estimate would have meant displacing
content the plan did not name as procedure, which is how a size target starts
removing measured material.

## Obligations, and what each null costs

Every row here is withdrawn on its own evidence, one row at a time. The order
matters: the displacement gates the rest, because rows that cannot fit without it
do not ship at all.

- **The displacement** needs non-inferiority against the current body on the code
  class, margin −0.10. If it fails, the displacement reverts and the surviving
  rows fit the 10 words of existing headroom or wait.
- **The data row** needs a correctness lift of at least +0.15 in a cell with real
  headroom — a bare arm failing at least a quarter of the time — and a clean
  false-positive reading. Another null and the row comes out; that is
  pre-committed, not a judgement to be made later.
- **The doc/report row** needs at least +0.15 on a defect reachable only past the
  end of a plausible line-range slice. Null and the row comes out.
- **The check-ran row** needs the count gate demonstrated red on a suite that
  silently collects zero and currently reports a pass. That part is discharged:
  `evals/harness/test_run_tests.py` plants exactly that module and watches the
  runner fail it. The body row still owes a clean false-positive reading.
- **All four rows together** owe the false-positive veto. Three new "requires"
  rows on a rigid skill is the shape that over-triggered once before — the
  rejected arm wrote a test on every trivial code edit — and that veto outranks
  any lift. If it fails, the rows are withdrawn as a set and re-proposed
  individually.

An honest "this does not replicate" retires rows rather than shipping them, and
that outcome is worth its cost. The corresponding entry in the plugin CHANGELOG
names what is measured and what is not; nothing here is described as pending in
the shipped surface, because a reader of the plugin should see only what its
evidence funds.

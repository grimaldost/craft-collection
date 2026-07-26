# The tier-0 check — the inline report skeleton

`check` is the rung below `probe`: an evaluation act answered in the response
itself. It has **no file, no record, and no validator** — nothing here exits
non-zero — and `check` never appears as a `tier:` field value. It is guidance,
deliberately flexible, and it leaves the entry criterion for the tiers above it
untouched: a record is owed when a decision rides on the result.

The rung exists because the alternative to a cheap shape is not a rigorous one,
it is an unstructured assertion — "it seems faster", "B is better" — which
carries no method, no denominator, and nothing a later reader can re-check.

The response opens with the activation line in its tier-0 form,
`[experiment-rigor | check -> inline]`. The artifact reference is the literal
`inline` because there is no artifact: nothing resolves it and no checker
verifies it, which is why this rung's line is reviewed rather than gated. At
`probe` and above the line names the record instead and is generated from it
(`render.py --activation-line`), so the claim there is tied to a file.

## When the shape is owed — the evaluation-act boundary

An **evaluation act** asks a question whose correct answer is a valuative claim:
"is this effective", "which of these is better", "is it worth it", "did that
change help". The answer is a judgement about quality, and it is only as good as
the method and the numbers behind it.

An **execution or lookup request** asks for an action or a fact, and its correct
answer is the action's result: "run the test suite and paste the output", "what
is the syntax for a Wilson interval", "rename this function everywhere". The
`check` shape is ceremony there — the answer is the output or the fact, and a
five-element wrapper around it adds nothing.

A borderline item resolves on one question: **does the correct response make a
quality claim?** If it does, the shape is owed; if the response is complete
without one, it is not. The rule reads the ask, not the responder's phrasing: a
comparison produced in support of a claim owes the shape whether or not a
verdict is volunteered — declining to conclude is itself a conclusion and is
reported as one, as the second worked example below does.

| Request | Kind | Shape owed |
|---|---|---|
| "Which of these two prompts does better on our tickets?" | evaluation act | yes |
| "Is the new retry logic actually faster?" | evaluation act | yes |
| "Did the fix help, or did we just get lucky?" | evaluation act | yes |
| "Run the suite and show me the failures" | execution | no |
| "Run the tests and tell me if they're ok" | execution | no |
| "Rename this helper across the package" | execution | no |
| "What does `clopper_pearson` do here?" | lookup | no |

Three edges worth naming. An execution request whose result the responder then
judges — "run the benchmark", followed by a claim about which config won — has
become an evaluation act at the point of the judgement, and the shape attaches to
that half, not to the run. A request for a number ("what is our current pass
rate") is a lookup, not a claim about quality: report the number with its
denominator and stop. And a correctness question — did the tests pass, does the
output match, is this number right — asks after a fact even when it is phrased
valuatively ("tell me if it's ok"): report the answer with its numbers and stop;
the shape attaches only when answering requires weighing, not checking.

## The five elements

- **Method** — what was compared, over what material, and how it was run. Enough
  that the reader could repeat it: the arms or options, the items they ran over,
  the number of passes, and anything held fixed.
- **Metric** — what counts as success, stated so a second person would score the
  same run the same way. "Better" is not a metric; "exact match on the invoice
  total" is. When nothing was measured, the metric names what the judgement
  rests on — the criteria being weighed — so the basis is inspectable.
- **Result(s), with denominators** — every rate as a numerator over a
  denominator, every timing with its run count. A bare percentage or a bare
  "improved" cannot be re-checked, and this is the element most often dropped.
  When no measurement was taken, saying so *is* the result — the element is the
  explicit absence, not an invented number.
- **Conclusion** — the claim the numbers support, at the size they support it. A
  small margin on a small sample is reported as a direction, not a finding.
- **What this updates** — one line: what the reader should now believe or do
  differently. "Nothing yet" is a legitimate answer and a common one.

The order and the wording are not fixed, and a check that carries all five in two
sentences is a good check. The point is that every element is answerable, not
that the response has five headings.

## Three worked examples

**Ask:** "Which of our two extraction prompts is better?"

> Method — ran both prompts over the same 40 invoices from last week's batch, one
> pass each, same model and settings, graded against the hand-checked totals.
> Metric — exact match on the invoice total.
> Results — prompt A 31/40, prompt B 35/40; 4 invoices failed under both.
> Conclusion — B is ahead by 4 of 40 on one pass over a single shared batch. The
> direction is B; the size is not established at this sample.
> What this updates — enough to keep drafting with B, not enough to retire A
> (retiring is a decision, so it would want a record at probe or above).

**Ask:** "Did the caching change make the importer faster?"

> Method — timed the same 12-file fixture import three times before and three
> times after the change, same machine, nothing else running.
> Metric — wall-clock seconds for a full import.
> Results — before 41, 39, 44 s (3 runs); after 38, 42, 37 s (3 runs).
> Conclusion — the two ranges overlap at 3 runs each, so this cannot separate a
> real gain from run-to-run noise.
> What this updates — nothing yet. If the claim has to be defended, the next step
> is more repeats under a probe record, not another eyeball.

**Ask:** "Is the new config loader better than the old one?" — with nothing
measured.

> Method — read both implementations side by side; no measurement was taken.
> Metric — the judgement rests on three named criteria: fewer failure paths, no
> silent fallbacks, one place to add a key.
> Results — no numbers beyond inspection counts: the old loader swallows two
> error cases the new one surfaces, and adding a key touches 3 files before, 1
> after.
> Conclusion — better on the named criteria, by inspection only — a code-reading
> judgement, not a measured effect.
> What this updates — enough to prefer the new loader here; any claim about
> speed or failure rates would need numbers first.

## What this rung is not

It is not a lighter validator: there is no artifact, so there is nothing for
`validate.py` to read and no gate to fail. Its truthfulness is carried by the
response containing the shape, which is why it is reviewed and measured rather
than gated.

It does not lower the bar above it. When a result will move a decision, or
someone will be asked to trust it later, copy `templates/probe.yaml` and open a
record; the five elements map onto the record's fields — method onto `design`,
metric onto the outcome's operationalization, results onto the arms with their
numerators and denominators, conclusion onto the verdict, and "what this updates"
onto the belief update. Nothing learned at tier-0 is thrown away by graduating.

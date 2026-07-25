# Threats to validity — the closed enum

The nine core threats every record must address. `validate.py` reads the enum
from `templates/schema.json` and fails (`ER-THREAT`) when a core key carries no
row — silence on a threat is itself the finding. Each `threats.<key>` row states
a `status` of `controlled` or `residual` and a non-empty `statement`; the
substance of the statement is ceded to review, its presence is not. An extension
threat is allowed as `custom_<slug>` and is held to the same row shape, but it
can never stand in for a missing core key: core coverage is unconditional.

The keys below are the catalog; `test_threats_catalog.py` asserts this list
equals `schema.json`'s `threat_enum` exactly, so the two never drift.

### `contamination_familiarity`

The model has already seen the task, its answer, or a near neighbour — in
pretraining, in a retrieval store, or in an earlier arm of the same run — and
familiarity inflates the score rather than the manipulation. Controlled when the
tasks are held out or freshly generated and no arm primes a later one; residual
when the corpus may overlap pretraining or a shared context could have leaked
across arms.

### `prompt_format_sensitivity`

The measured effect rides on surface prompt formatting — delimiters, field
order, whitespace, casing — rather than on the intervention under test.
Controlled when the format is held fixed across arms, or varied and shown not to
move the outcome; residual when a single format is used and its influence is
unmeasured.

### `judge_bias`

An automated or model judge systematically favours one arm on a feature that is
not the construct — length, style, or answer position. Controlled when the judge
is blind to arm, order is swapped between the two arms, and inter-judge
agreement is reported; residual when a single-order, arm-aware judge grades.

### `model_version_drift`

The model under test changes between arms or over the wall-clock of the run — a
silent provider version bump — confounding the comparison with the manipulation.
Controlled when the model-version string is pinned and cross-checked against the
run ledger; residual when arms ran on different dates, or the provider may have
rolled the model without a recorded pin.

### `nondeterminism`

Sampling variance across identical calls; a single draw per cell mistakes noise
for effect. Controlled when repeats or epochs and a reported interval capture the
variance on the randomization unit; residual when n is small and each condition
was drawn once.

### `construct_validity_proxy`

The measured proxy — a verifier's pass or fail, a rubric score — is not the
construct the claim is about (whether the tool "helps"). Controlled when the
operationalization is pre-registered and argued to stand for the construct;
residual when the proxy is a convenient stand-in whose gap to the construct is
left unstated.

### `token_length_confound`

One arm's prompt or output is systematically longer, and length — not the
manipulation — drives the outcome or the cost. Controlled when length is balanced
across arms, or measured and shown not to explain the effect; residual when the
intervention adds tokens and length is not accounted for.

### `selection_exclusion`

Trials dropped after the fact — errors, timeouts, hand-picked outliers — bias the
surviving set. Controlled when exclusion rules are pre-registered and the
disposition reconciles (completed plus excluded equals the total); residual when
drops are ad hoc or the disposition does not close.

### `generalization`

The result holds for this task set, this model, and this moment, but the claim is
made more broadly. Controlled when the claim is scoped to the tested population
and any wider belief moves through a cross-experiment GRADE link that carries the
breadth qualitatively; residual when a single experiment's finding is generalized
without that qualification.

# The shipping gate — its evidence, and where it bends

Background for the four shipping requirements in the skill body. Read it when a
skill cannot be gated the normal way, or when someone argues the register rules
are taste.

## Two classes the harness cannot gate at trigger time

- A skill whose trigger inherently depends on the cwd corpus — an empty eval cwd
  cannot fire it.
- A heavy orchestration skill that fires and then exceeds the eval's turn cap,
  which is scored as an error rather than an activation.

For those, requirement 4 becomes **manual-observation activation evidence**: it
fires and correctly out-selects its named siblings in a populated, real context,
plus clean specificity, with the harness-fixture follow-up recorded. Precedent:
`corpus-review` shipped exactly this way. Do not re-block the class on a 0.00
recall artifact that measures the fixture rather than the skill.

## What a pre-registered threshold has to declare

Requirement 4's thresholds are only evidence if the design could have moved
them. State the **maximum movement attainable at the planned repeat count, and
its p**, at the moment the threshold is registered.

The case that forced this: a description edit was written for one under-firing
query and shipped against a pre-registered bar. The query moved 1/3 to 1/3 —
zero movement — while the dev aggregate fell 0.939 to 0.818 (Fisher p about
0.26, query-clustered denominators, so no revert was licensed either). Nobody
had computed what the eval could detect: at 3 repeats the *maximum* achievable
movement on that query carries p about 0.4. The design could not have separated
whatever the edit did, so a failed edit and a design incapable of succeeding
left the same record, and $9.97 bought a result that answers nothing.

If the design cannot reach the bar, raise repeats or do not register it.

## The register question is measured, not aesthetic

The craft-collection record: calibrated descriptions reach 0.95–1.00 trigger
recall on current models, and the one overfit description in the collection's
history was caught by a sealed holdout collapsing (1.00 on the dev set,
0.25–0.50 unseen) — tuning pressure, not register, is what moves recall.

The persuasion-style alternative rests on a compliance study (objectionable-request
compliance under social-influence framings) whose outcome variable is not process
adherence in agentic work; treat its transfer here as unsupported until the
register ablation says otherwise.

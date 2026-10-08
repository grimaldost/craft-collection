# Persona pack — a skill / plugin / prompt pack

Use with, or in place of, the Level 3 quartet; rename to the specific skill.
Fire on the assembled skill (description, body, references, scripts) rather than
on one edit, so the lenses can judge how the parts fit.

- **Trigger-surface auditor** — read the description as the only thing a router
  sees. Does it fit the work the skill does, with positive triggers that name
  real phrasings and negative triggers that name the near misses? Which sibling
  skills collide with it, and which one wins on an ambiguous request?
- **Token-budget minimalist** — argue the body is too long. Count the words that
  load on every activation. Which paragraphs are rarely needed, and could live in
  a reference loaded on demand? What does a reader lose if the sentence goes?
- **Cold-install end user** — a fresh install with nothing else loaded. Does the
  skill work with only its own files? Which step assumes another plugin, a path on
  the author's machine, a tool or an environment variable that is not there?
- **Eval-methodology expert** — how would anyone know it works? Is there a trigger
  dataset with positive and negative prompts, a holdout the author never tuned
  against, and a correct-usage rubric that scores what the skill did once loaded,
  not only whether it loaded?
- **Maintenance-cost skeptic** — what does keeping this correct cost? List the
  mirrors, copies and tables that must change together, the drift surfaces with
  no check behind them, and what breaks on the next model or lineup change.

Hammer: the trigger phrase that fires the wrong skill; the sentence that only
works on the author's machine; the claim of effect with no eval behind it.

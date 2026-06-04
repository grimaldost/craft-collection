# Top-Tier Plugin & Skill Patterns (research, 2026-06)

What the best plugins / skill collections do, distilled to adoptable techniques.
Sources inline.

## Exemplars

- **anthropics/skills** — a skill is a dir with `SKILL.md` + `scripts/` /
  `references/` / `assets/`. `skill-creator` encodes a five-phase loop (intent →
  research → write → test/eval → improve) and ships `init_skill`, `package_skill`,
  `run_loop` (description tuner), and an eval viewer.
  https://github.com/anthropics/skills
- **anthropics/claude-code** official marketplace — 13 plugins in 4 categories
  (development / productivity / learning / security); each marketplace entry has
  `name`, `description`, `source`, `category`, `version`, `author`. `plugin-dev`
  holds the canonical `skill-development` / `hook-development` skills.
  https://github.com/anthropics/claude-code/blob/main/.claude-plugin/marketplace.json
- **obra/superpowers** — multi-harness; a meta-skill injected in full at
  `SessionStart` so the agent always searches for skills; enforcement over
  suggestion (TDD deletes pre-test code; 2–5 min task units; two-stage review).
  Caveat: full SessionStart injection has real token cost and doesn't reach
  subagents — prefer a *compact* trigger injection.
  https://github.com/obra/superpowers
- **wshobson/agents** & **commands** — single-purpose plugins (install one →
  only its components load); skills chunked ~8 KB; a three-layer `plugin-eval`
  QA harness (static → LLM-judge → Monte-Carlo trigger reliability). Commands
  split Workflows vs Tools, lowercase-hyphen action names.
  https://github.com/wshobson/agents · https://github.com/wshobson/commands
- **davila7/claude-code-templates** — CLI package manager + web catalog; typed
  `npx --agent/--command/--hook` install. https://github.com/davila7/claude-code-templates
- Indexes: **hesreallyhim/awesome-claude-code**; **claude-code-json-schema**
  (unofficial `plugin.json`/`marketplace.json` schemas for `$schema`).

## Skill-authoring craft

Source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices

- **Progressive disclosure**: metadata (always loaded) → SKILL.md (on relevance)
  → bundled files (on need). SKILL.md is a table of contents.
- **Token budget**: body < 500 lines (superpowers tightens: getting-started
  < 150 words, frequently-loaded < 200, others < 500). "Context window is a
  public good"; cut what Claude already knows.
- **Descriptions**: third person; both *what* and *when* with concrete triggers;
  superpowers' rule — **triggering conditions only, never a workflow summary**
  (else Claude acts on the description and skips the skill); skill-creator —
  be "a little pushy," over-specify contexts.
- **Naming**: gerund-ish, lowercase-hyphen, ≤64 chars; no `helper`/`utils`;
  semantic helper-file names.
- **References**: one level deep from SKILL.md; add a TOC to any file > 100 lines
  (partial `head -100` reads miss content); organize by domain.
- **Degrees of freedom**: prose for high-freedom tasks, parameterized pseudocode
  for medium, "run exactly this script, do not modify" for low.
- **Discipline toolkit**: checklists for multi-step work; flowcharts only for
  non-obvious decision points; a **red-flags / rationalization table**
  (`Excuse | Reality`). Escalate to MUST/NEVER sparingly for load-bearing rules.

## Scripts vs hooks

- **Scripts** for deterministic ops (validate, format, scaffold, codegen):
  cheaper and more reliable than token generation; must handle their own errors;
  justify every constant in a comment; state execute-vs-read intent.
- **Hooks** for behaviour the model can't be trusted to do every time:
  PostToolUse format/lint, PreToolUse destructive-command guards, SessionStart
  context. Real example set: **disler/claude-code-hooks-mastery** (PreToolUse
  blocks `rm -rf`/`.env` access; PostToolUse ruff/ty validators; Stop forces
  continuation until tests pass) — implemented as PEP-723 `uv run` single-file
  scripts. https://github.com/disler/claude-code-hooks-mastery

## Delivering artifacts well

- **Evals before docs**: run Claude without the skill, log failures, write ≥3
  eval scenarios, baseline, then write minimal instructions. Eval JSON:
  `{ skills, query, files, expected_behavior }`.
- **Triggering as a measured quantity**: skill-creator's 20-query trigger test +
  description auto-tuning; wshobson's Monte-Carlo (50–100 runs).
- **Claude-A/Claude-B loop**: one instance authors, a fresh instance uses on real
  tasks; promote over-read files into SKILL.md, delete never-read files.
- **Definition of Done**: specific what+when description; body < 500 lines;
  references one level deep; no time-sensitive content; consistent terminology;
  ≥3 evals; tested on Haiku+Sonnet+Opus; scripts handle errors.
- **Versioning**: treat prompts/skills as versioned immutable artifacts;
  regression-test old-vs-new in CI (**promptfoo** — declarative YAML suites,
  deterministic assertions, GitHub Action). https://github.com/promptfoo/promptfoo

## Marketplace UX

Categorize explicitly; fill `displayName`/`category`/`keywords`/`tags`/
`homepage`/`license`; frictionless install one-liners + browsable catalog;
per-component doc template (purpose / coordination / features / use-cases);
`$schema` on both JSON files; `claude plugin validate` before publishing.

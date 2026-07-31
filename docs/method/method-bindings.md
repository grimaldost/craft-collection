# Method bindings — craft-collection

The method is project-agnostic; this file binds each slot and upgrade to a
concrete mechanism in THIS project.

## Portability slots

| Slot (what it must provide) | craft-collection binding |
|---|---|
| **ADR home** — a numbered decision log | `docs/adr/` |
| **Spec format** — numberable sections, acceptance criteria | `docs/specs/<slug>.md` from `docs/method/spec-template.md` |
| **Guardrails + gate commands** — deterministic pass/fail | pre-commit (`.pre-commit-config.yaml`: ruff lint+format, register linter, structural validator, hygiene); `uv run --no-project --with pyyaml -- python scripts/run_tests.py`; `uv run --no-project --with pyyaml -- python scripts/validate_plugins.py`; `uv run --no-project python scripts/lint_register.py`; `uv run --no-project python scripts/word_budget.py`; CI `.github/workflows/validate.yml` |
| **Review checklist** — project-specific, blocking | `docs/method/review-checklist.md` (as shipped; tailor per wave) |
| **Reflection sink** — feeds the next round | session-workflow `tool-feedback` → `feedback-triage` loop; intake `docs/feedback/` (created when the first report lands) |

## Upgrade bindings

| Upgrade | What it must provide | craft-collection binding |
|---|---|---|
| **DoR gate** | spec-readiness check before decompose | `docs/method/definition-of-ready.md` + `uvx --from git+https://github.com/grimaldost/keel keel check-ready <spec>` |
| **Pre-mortem** | a stateless adversarial pass | keel's `pre-mortem-prompt.md` run by a fresh non-author subagent, blind to the authoring session |
| **Wave budget** | forecast + drift gate | `[budget]` block in `series.toml` skeleton (`docs/method/series-toml-skeleton.md`) — manual until an orchestrator is bound |
| **Edit-time invariant hook** | block edits that violate a boundary | engineering-discipline's own hooks (`ruff_format`, `uv_enforce`) while working in this repo |

## Orchestrator

| | craft-collection |
|---|---|
| Series runner | none bound — the series tables run as manual checklists |
| Single-unit discipline | humblepowers (this repo's own plugin: TDD, systematic-debugging, verification-before-completion) |
| Cross-series memory | session-workflow journaling → consolidate-knowledge (this repo's own plugin) |
| Capacity dispatch | humblepowers `choosing-models` |

*A slot left unbound is a method-not-fully-applied warning. Bind every row before
running a series under the method.*

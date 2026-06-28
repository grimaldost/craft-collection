---
name: python-engineering
description: >
  Modern Python engineering standards and best practices. Use this skill
  whenever a user wants to: scaffold a Python project, configure tooling
  (uv, ruff, ty, mypy, structlog, pytest, hypothesis, pydantic-settings,
  opentelemetry, pip-audit), set up pyproject.toml, src-layout, pre-commit,
  CI/CD, Docker — for an existing, inherited, or legacy project as much as a
  greenfield one (assessing and modernizing current setup, not just scaffolding
  new) — or asks about Python
  architecture, packaging, testing, type
  checking, observability, security, async patterns, typing.Protocol, dependency
  injection, CLAUDE.md, or Cursor rules. Covers hexagonal architecture,
  functional core/imperative shell, property-based testing, snapshot testing,
  testcontainers, Trusted Publishers, and Sigstore.
---

# Modern Python Engineering Standards

Apply these standards whenever scaffolding, advising on, or generating Python code
and configuration.

---

## Core Philosophy

1. **Ecosystem-First**: Before writing custom logic, evaluate standardized
   solutions. Custom scripts are liabilities; community tools are assets.
2. **Fail Fast**: Catch errors at startup (typed config) and at commit time
   (pre-commit hooks), not in production.
3. **src layout is mandatory** — never flat layout for production projects.
4. **Single quotes** for code literals; **double quotes** for docstrings.
5. **Never suggest `pip`, `poetry`, or `virtualenv`** — always `uv`.
6. **Astral-first toolchain**: prefer `uv` + `ruff` + `ty` for the unified,
   high-performance developer experience.
7. **Protocol-first typing**: prefer `typing.Protocol` (structural subtyping)
   over ABCs for interfaces. Reserve ABCs for shared implementation only.
8. **Async for I/O-bound services**: reach for `async`/`await` on web services and
   I/O-bound code — not CPU-bound work or one-shot scripts. Use `asyncio.TaskGroup`
   over `asyncio.gather()`.
9. **Observable when it runs as a service**: for anything long-running, logging
   alone is insufficient — instrument with OpenTelemetry traces, metrics, and
   correlated structured logs. Right-size it; a CLI or one-off script doesn't need
   distributed tracing.
10. **Secure the supply chain**: pin dependencies with hashes, audit for CVEs
    in CI, use Trusted Publishers for PyPI releases.

---

## Modifying existing code (the edit lane)

Most work in an existing project is an *edit*, not a scaffold. When the task
is to change a few files in a project that already has its layout, tooling,
and CI, the scaffolding, Docker, observability, and CI sections below are
not the relevant rules — skip them. Match what the surrounding code already
does, and apply only the rules that govern the lines you touch (for a
**micro-edit** — a one-line docstring or string change — even these are mostly
moot: match the touched line's local form, run the project's gate, and stop):

- **Match the local convention first — project config governs.** Read 2–3
  nearby files before editing. The project's existing patterns — even where
  they differ from this skill's greenfield defaults — are the contract for an
  edit; a one-file modernization that diverges from the rest of the module is
  noise, not improvement. Where the project states its own conventions
  (`AGENTS.md`, `CLAUDE.md`, `ruff.toml`, a style guide), **those govern and
  this skill's defaults are the fallback** — defer, don't override.
- **Protocol-first typing for new interfaces.** A new seam introduced inside
  existing code prefers `typing.Protocol` (structural) over an ABC, unless the
  surrounding code already commits to ABCs. See the Typing Philosophy section.
- **`@override` semantics.** When overriding a real base-class method, annotate
  it `@override` (PEP 698); do not add `@override` to a class that only
  structurally satisfies a `Protocol` — see the caveat in Typing Philosophy.
- **Import hygiene.** Keep imports at module top, grouped stdlib / third-party /
  first-party (ruff's isort handles ordering). When a format-on-save or
  autofix hook strips unused imports, add an import in the *same* edit that
  first references it — an "import now, use later" split loses the import to
  the hook between edits.
- **Quoting and docstrings.** Single quotes for code literals, double quotes
  for docstrings (the project's ruff config enforces this; an edit that fights
  it just gets reformatted).
- **Don't widen the scope.** An edit's diff is its scope. Adjacent cleanup,
  renames, and "while I'm here" refactors belong in a separate change — the
  same scope discipline `data-engineering-discipline` applies to a migration.

If the task is actually to *modernize* an inherited project's tooling (assess
the current setup and bring it to standard), that is the broader scope the
rest of this skill and `scripts/doctor.py` cover — run the doctor, then work
through its findings.

---

## The Canonical Stack

| Layer            | Tool                  | Notes                                      |
|------------------|-----------------------|--------------------------------------------|
| Package manager  | `uv`                  | Replaces pip + virtualenv + poetry + pyenv |
| Build backend    | `uv_build`            | Default from `uv init`, PEP 621-compliant |
| Lint + Format    | `ruff`                | Single-quote enforced in both linter+fmt   |
| Type checking    | `ty` (primary)        | Astral's Rust-based checker (beta, fast)   |
|                  | `mypy` (stable alt)   | Use if `ty` coverage is insufficient       |
| Config mgmt      | `pydantic-settings`   | Typed env vars, SecretStr for secrets      |
| Logging          | `structlog`           | JSON in prod, pretty in dev                |
| Observability    | `opentelemetry`       | Traces + metrics; correlate with structlog |
| Testing          | `pytest`              | Unit (pure) + integration (I/O)            |
| Property testing | `hypothesis`          | For data processing, serialization, algos  |
| Security audit   | `pip-audit`           | CVE scanning against OSV database in CI    |
| CLI (if needed)  | `typer`               | Type-hint-driven argument parsing          |
| Web (if needed)  | `fastapi`             | Interface layer only — keep logic in core/ |

### A note on type checkers

**`ty`** (by Astral, the ruff/uv team) is the forward-looking choice: much faster
than mypy (Astral reports 10-100× on large codebases), built-in language server,
first-class intersection types,
and advanced reachability analysis. It is currently in **beta** (0.0.x) and
evolving rapidly toward a 1.0 release.

**`mypy`** remains the battle-tested, stable option for projects that need
full typing ecosystem coverage today.

**Recommendation**: Use `ty` for new projects and active development (fast
feedback loop). Keep `mypy` in CI as a secondary check if your project relies
on mypy plugins (e.g., `django-stubs`, `sqlalchemy-stubs`). For VS Code /
Cursor users, install the `ty` extension for the language server.

---

## Typing Philosophy

**Prefer `Protocol` over ABCs** for interface definitions. Protocols enable
structural subtyping (static duck typing) — any class that implements the
required methods satisfies the Protocol without inheriting from it. This
aligns with Python's duck-typing nature and keeps classes decoupled.

```python
from typing import Protocol

class Repository(Protocol):
    """Any class with save() and get() satisfies this contract."""
    def save(self, entity: dict) -> str: ...
    def get(self, entity_id: str) -> dict | None: ...

# No inheritance needed — just implement the methods
class PostgresRepository:
    def save(self, entity: dict) -> str: ...
    def get(self, entity_id: str) -> dict | None: ...
```

Reserve ABCs only when you need: runtime `isinstance()` enforcement, shared
method implementations via inheritance, or `@abstractmethod` guarantees.

### Python 3.14 typing improvements

**PEP 649 (deferred annotations)**: On Python 3.14+, annotations are lazily
evaluated. Forward references work natively — no need for
`from __future__ import annotations`. Drop that import on new 3.14+ projects.

**Other modern typing patterns**: use `Self` for fluent APIs, `@override` for
explicit method overriding, `ParamSpec` for typed decorators, and
`TypeIs` / `TypeGuard` for type narrowing in guards.

> **`@override` caveat (PEP 698).** `@override` requires an actual base-class
> method to override. On a plain structural class that satisfies a `Protocol`
> *without* subclassing it — the Protocol-first default above — do not add
> `@override`: there is no base method, so the type checker flags it as an
> error. Structural conformance and `@override` are mutually exclusive; reach
> for `@override` only inside a real inheritance chain (an ABC subclass, or a
> class that explicitly subclasses its base).

→ Full architecture rationale: **Read `references/ecosystem_rationale.md`**

---

## Project Layout Decision

Ask (or infer) whether the project is a **Library/Data tool** or an
**Application**.

- **Library layout** → domain-centric modules exposed directly
  (`src/mylib/datatools/`, `src/mylib/core/`)
- **Application layout** → decouple logic from entry points
  (`src/myapp/core/` + `src/myapp/interface/`)
- **Tests** → a top-level `tests/` tree, **never inside `src/`**. Colocated
  `src/.../tests/` modules ship inside the built wheel and pollute the installed
  package; for per-unit suites (datajobs, plugins) mirror the package under
  `tests/<area>/<name>/`. (`doctor.py` flags any `test_*.py` found under `src/`.)

The application layout follows the **functional core / imperative shell**
pattern: `core/` contains pure business logic (no I/O, fully testable),
while `interface/` contains thin adapters (FastAPI routes, CLI commands,
database clients). Connect them via `Protocol` interfaces and constructor
injection.

→ Full directory trees and the authoritative `pyproject.toml` template:
**Read `references/project_templates.md`**

---

## Scaffolding Protocol

When generating a project for a user:

1. **Resolve names** from the project name they provide:
   - PyPI: `kebab-case` (e.g., `my-cool-tool`)
   - Package: `snake_case` (e.g., `src/my_cool_tool/`)
   - Classes: `PascalCase`

2. **Mandatory substitutions in `pyproject.toml`**:
   - `[project] name`
   - `[tool.ruff.lint.isort] known-first-party = ["actual_name"]`

3. **Strip irrelevant optional deps**: if user doesn't mention data processing,
   remove `datatools` extras; if no CLI, remove `typer`; if no web, remove
   `fastapi`.

4. **Initialization command**: always `uv init --lib <project-name>` to get the
   src layout with `uv_build` from the start.

---

## Dependency Management (PEP 735)

Use `[dependency-groups]` (PEP 735) for development dependencies — **not**
`[project.optional-dependencies]`, which is for end-user feature extras
(`pip install mylib[cli]`). Dev deps are local-only and must not ship with the
package. Group into `lint` / `test` / `security`, plus a `dev` group that
includes them.

→ The authoritative `[dependency-groups]` block:
**Read `references/project_templates.md`**

---

## Ruff Single-Quote Enforcement

Critical: both the **formatter** and **linter** must be aligned or they fight.

```toml
[tool.ruff.format]
quote-style = "single"

[tool.ruff.lint.flake8-quotes]
inline-quotes = "single"
docstring-quotes = "double"
multiline-quotes = "double"
```

Ruff 0.8+ deltas: the `TCH` category is now `TC` (use `"TC"` in `select`);
`ANN101` / `ANN102` were removed (don't list them in `ignore`); block
suppression via `# ruff: disable[RULE]` / `# ruff: enable[RULE]` avoids per-line
`# noqa`.

---

## Configuration Management Pattern

Never read `os.getenv()` directly. Use a typed `Settings(BaseSettings)` from
`pydantic-settings`, with `SecretStr` for secrets (masked in logs). Keep `.env`
gitignored and commit `.env.template` to document required keys.

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: SecretStr
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


settings = Settings()
```

→ Why typed config (fail-fast at startup, validation): **Read
`references/ecosystem_rationale.md`**

---

## Observability

Observability has three pillars: **structured logs**, **distributed traces**,
and **metrics**. Use `structlog` for logging and `opentelemetry` for
traces/metrics. Correlate them by injecting trace IDs into log entries.

→ Full structlog + OpenTelemetry setup, stdlib bridge, FastAPI middleware,
and pytest integration: **Read `references/observability.md`**

The minimum-viable `configure_logging()` (JSON in prod, pretty in dev) and the
full trace-correlated setup both live in **`references/observability.md`** —
call it once at application startup (CLI entry point or FastAPI `lifespan`).

---

## Pre-commit Hooks

`scripts/scaffold.py` writes the canonical `.pre-commit-config.yaml`
(trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files,
plus `ruff` + `ruff-format` at the revs pinned in `stack.toml`). Install with
`uv run pre-commit install`.

> **Note on ty in pre-commit**: `ty` has no official pre-commit hook yet. Run it
> via `uv run ty check src` in CI or as a local script.

---

## Key uv Commands

```bash
uv init --lib my-project        # Scaffold with src layout + uv_build
uv add <package>                # Add runtime dependency
uv add --dev <package>          # Add dev dependency (PEP 735)
uv add --group lint <package>   # Add to specific dependency group
uv sync                         # Install all deps from lockfile
uv sync --frozen                # CI: install without updating lockfile
uv run pytest                   # Run tests in project venv
uv run ruff check src           # Lint
uv run ruff format src          # Format
uv run ty check src             # Type check (ty)
uv run mypy src                 # Type check (mypy, if used)
uv python install 3.14          # Install a specific Python version
uv python pin 3.14              # Pin project to Python 3.14
```

---

## AI-Assistant Configuration

Modern Python projects include configuration files for AI coding assistants.
These are committed to the repo and provide persistent project context.

- **`CLAUDE.md`** — Read by Claude Code at conversation start. Include
  build/test commands, architecture decisions, code style preferences.
  Keep under ~50 concise instructions. Use `/init` to auto-generate.
- **`.cursor/rules/*.mdc`** — Cursor rules with frontmatter-based glob
  matching (e.g., scope rules to `app/routers/*.py`).
- **`.github/copilot-instructions.md`** — Repo-level instructions for
  GitHub Copilot Chat and Code Review.

→ Full templates and patterns: **Read `references/ai_config.md`**

---

## Supply-Chain Security

Add these to every CI pipeline:

```bash
uv run pip-audit                  # Scan for known CVEs (OSV database)
uv run ruff check src --select S  # Bandit-equivalent security linting
```

For package publishers: use **Trusted Publishers** on PyPI (OIDC-based, no
long-lived API tokens) and **Sigstore attestations** (automatic with the
canonical GitHub Action). Pin all dependencies with cryptographic hashes
via `uv lock`.

→ Full security setup and CI integration: **Read `references/security.md`**

---

## Reference Files

Exhaustive templates and patterns — read on demand:

- **`project_templates.md`** — `pyproject.toml` master config, both directory layouts, GitHub Actions CI.
- **`ecosystem_rationale.md`** — why each tool, Protocol vs ABC, functional core / imperative shell, DI.
- **`observability.md`** — structlog + OpenTelemetry setup, trace correlation, FastAPI middleware.
- **`testing_and_qa.md`** — pytest, Hypothesis, mutation/snapshot testing, testcontainers, unit/integration split.
- **`docker_patterns.md`** — multi-stage Dockerfile with uv, CI/CD Docker caching.
- **`security.md`** — Trusted Publishers, Sigstore, pip-audit, dependency pinning.
- **`ai_config.md`** — CLAUDE.md, Cursor rules, Copilot instructions.
- **`currency_review.md`** — quarterly review protocol for keeping the skill current.

---

## Scripts, freshness, and keeping current

> **last-reviewed: 2026-06-04.** Pinned versions live in `stack.toml` — the
> single source of truth this skill cites instead of repeating numbers in prose.
> When exact current versions matter, verify against PyPI / context7 at the
> point of use; a pinned floor can lag the latest release.

Bundled scripts (`scripts/`):

```bash
python scripts/scaffold.py my-cool-tool  # new project to standard (uv init + canonical pyproject + pre-commit)
python scripts/doctor.py [path]          # audit an existing project against the standard
python scripts/check_versions.py         # compare stack.toml pins to latest on PyPI (--json for CI)
```

**Freshness loop (Tier 3).** `check_versions.py` detects drift (exits non-zero
when a pin is behind a newer minor/major); a monthly CI cron opens a drift
issue; the **`/refresh-stack`** command reviews each changelog and proposes the
`stack.toml` + guidance updates for you to approve — mechanical bumps applied on
approval, guidance edits never auto-applied. See `references/currency_review.md`
for the full review checklist.

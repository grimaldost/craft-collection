---
name: python-engineering
description: >
  Modern Python engineering standards and best practices. Use this skill
  whenever a user wants to: scaffold a Python project, configure tooling
  (uv, ruff, ty, mypy, structlog, pytest, hypothesis, pydantic-settings,
  opentelemetry, pip-audit), set up pyproject.toml, src-layout, pre-commit,
  CI/CD, Docker, or asks about Python architecture, packaging, testing, type
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

→ Full architecture rationale: **Read `references/ecosystem_rationale.md`**

---

## Project Layout Decision

Ask (or infer) whether the project is a **Library/Data tool** or an
**Application**.

- **Library layout** → domain-centric modules exposed directly
  (`src/mylib/datatools/`, `src/mylib/core/`)
- **Application layout** → decouple logic from entry points
  (`src/myapp/core/` + `src/myapp/interface/`)

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
`[project.optional-dependencies]`. Dev deps are local-only and must not ship
with the package.

```toml
[dependency-groups]
dev = [
    { include-group = "lint" },
    { include-group = "test" },
    { include-group = "security" },
    "pre-commit",
]
lint = [
    "ruff>=0.15",
    "ty",
]
test = [
    "pytest>=8.0",
    "pytest-cov",
    "pytest-asyncio>=0.24",
    "hypothesis",
]
security = [
    "pip-audit",
]
```

Reserve `[project.optional-dependencies]` for **feature extras** that end users
install (e.g., `pip install mylib[cli]`).

Key commands:
```bash
uv add --dev pytest              # Adds to [dependency-groups] dev
uv add --group lint ruff         # Adds to [dependency-groups] lint
uv sync                          # Installs all default groups
uv sync --group test             # Installs specific group
uv run pytest                    # Runs in project venv
```

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

### Ruff 0.8+ Migration Notes

- The `TCH` rule category was renamed to **`TC`**. Use `"TC"` in `select`.
- `ANN101` / `ANN102` were **removed** — do not list them in `ignore`.
- Block suppression comments are now supported:
  `# ruff: disable[N803]` / `# ruff: enable[N803]` to suppress rules for a
  block of code without per-line `# noqa`.

---

## Configuration Management Pattern

Never use `os.getenv()` directly. Always use `pydantic-settings`:

```python
# src/my_package/core/config.py
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration — loaded from .env."""

    DEBUG: bool = False
    APP_NAME: str = 'My App'
    API_KEY: SecretStr  # Masked in logs automatically

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore',
    )


settings = Settings()
```

Use `.env` (gitignored) for secrets and `.env.template` (committed) to
document required keys.

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

For exhaustive templates and patterns, read these as needed:

- **`references/project_templates.md`** — Full `pyproject.toml` template
  (Build, Ruff, ty, Mypy, Pytest), both directory layouts, GitHub Actions CI
  workflow. Read this when scaffolding any project or generating config files.

- **`references/ecosystem_rationale.md`** — Rationale for each tool choice,
  Protocol vs ABC philosophy, architecture patterns (functional core /
  imperative shell, dependency injection). Read when explaining *why*.

- **`references/observability.md`** — Full structlog + OpenTelemetry setup:
  stdlib bridge, trace ID correlation, FastAPI middleware, metrics, and
  pytest integration. Read when setting up logging or observability.

- **`references/testing_and_qa.md`** — Pytest patterns, Hypothesis for
  property-based testing, snapshot testing, testcontainers, unit vs
  integration split, async testing. Read when generating tests or QA strategy.

- **`references/docker_patterns.md`** — Multi-stage Dockerfile with uv, CI/CD
  Docker caching. Read when containerizing a Python project.

- **`references/security.md`** — Supply-chain security: Trusted Publishers,
  Sigstore attestations, pip-audit, dependency pinning, CI pipeline.
  Read when hardening a project's security posture.

- **`references/ai_config.md`** — Templates for CLAUDE.md, Cursor rules,
  and Copilot instructions. Read when setting up AI-assistant configuration.

- **`references/currency_review.md`** — Quarterly review protocol and
  checklist for keeping the skill up-to-date with the Python ecosystem.

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

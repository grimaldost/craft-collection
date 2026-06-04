# AI-Assistant Configuration Guide

Modern Python projects include configuration files that give AI coding
assistants persistent project context. These files are committed to the repo
and shared with the team.

## 1. CLAUDE.md (Claude Code)

Claude Code reads `CLAUDE.md` from the project root at conversation start.
It provides build commands, architecture decisions, and code style preferences.

### Template

```markdown
# CLAUDE.md

## Build & Test Commands
- `uv sync` to install dependencies
- `uv run pytest` to run all tests
- `uv run pytest tests/unit/test_specific.py::test_name` for a single test
- `uv run ruff check src tests` to lint
- `uv run ruff format src tests` to format
- `uv run ty check src` to type check

## Project Architecture
- src layout: all source code in `src/<package_name>/`
- `core/` contains pure business logic (no I/O, no framework imports)
- `interface/` contains thin adapters (FastAPI routes, CLI commands)
- Connect layers via `typing.Protocol` interfaces

## Code Style
- Single quotes for strings, double quotes for docstrings
- Type hints on all function signatures
- Google-style docstrings on public functions
- Use `pydantic-settings` for configuration, never `os.getenv()`
- Use `structlog` for logging, never `print()` or `logging.info()`

## Conventions
- One test file per module (e.g., `test_services.py` for `services.py`)
- Use `pytest.mark.integration` for tests that require external resources
- All new code must pass `ruff check`, `ruff format --check`, and `ty check`
```

### Best Practices

Keep CLAUDE.md **under ~50 concise instructions**. Tell Claude *how to find*
information rather than dumping everything — for example, "see
`docs/architecture.md` for the full system design" rather than inlining the
entire architecture doc. Use the `/init` command to auto-generate a starter
file, then customize it.

## 2. Cursor Rules (`.cursor/rules/*.mdc`)

Cursor rules use frontmatter-based glob matching to scope instructions to
specific file patterns. Create one `.mdc` file per concern.

### Example: `.cursor/rules/python-style.mdc`

```markdown
---
description: Python code style and conventions
globs: ["**/*.py"]
---

- Use single quotes for strings, double quotes for docstrings
- All functions must have type annotations
- Use `typing.Protocol` for interfaces, not ABCs
- Use `pydantic-settings` for config, never `os.getenv()`
- Use structlog for logging
- Tests go in `tests/unit/` or `tests/integration/`
```

### Example: `.cursor/rules/api-routes.mdc`

```markdown
---
description: FastAPI route conventions
globs: ["src/**/interface/*.py", "src/**/routers/*.py"]
---

- Routes are thin: validate input, call core service, return response
- Use `Depends()` for dependency injection
- Return Pydantic models, not raw dicts
- All routes must have OpenAPI summary and description
```

## 3. Copilot Instructions (`.github/copilot-instructions.md`)

GitHub Copilot reads this file for repo-level context in Chat and Code Review.

### Template

```markdown
# Copilot Instructions

This is a Python project using the Astral toolchain (uv, ruff, ty).

## Stack
- Package manager: uv (never suggest pip or poetry)
- Linting/formatting: ruff with single-quote enforcement
- Type checking: ty (primary), mypy (CI secondary)
- Testing: pytest with hypothesis for property-based tests
- Logging: structlog (JSON in prod, pretty in dev)
- Config: pydantic-settings (never os.getenv)

## Architecture
- src layout with functional core / imperative shell pattern
- `core/` = pure business logic, no I/O
- `interface/` = thin adapters (FastAPI, CLI, DB clients)
- Use `typing.Protocol` for interface contracts

## Code Review Guidelines
- Reject raw string formatting for SQL (use parameterized queries)
- Reject `print()` statements (use structlog)
- Reject `os.getenv()` (use pydantic-settings)
- Reject `Any` types in public APIs without justification
```

## 4. Shared Patterns

All three files share ~80% of content. Consider maintaining a canonical
source document (e.g., `docs/engineering-standards.md`) and deriving the
AI config files from it. The project-specific commands and glob patterns
are the main differentiators.

### AI-Friendly Project Patterns

Beyond configuration files, these patterns help AI assistants generate
better code:

- **Complete type annotations** on all function signatures
- **Pydantic models** instead of raw dicts for data shapes
- **Clear module boundaries** with src layout
- **Google-style docstrings** on public functions
- **One test file per module** with descriptive test names
- **Explicit imports** (no wildcard `from module import *`)

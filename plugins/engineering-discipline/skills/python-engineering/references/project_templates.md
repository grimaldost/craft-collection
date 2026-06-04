# Project Structure & Templates

This file provides the "golden path" templates for a modern Python repository.
It is the **Single Source of Truth** for configuration, adhering to the `src`
layout and the Astral toolchain (`uv` + `ruff` + `ty`).

## 1. Project Directory Structure

### Option A: The Data/Library Layout

*Best for: Utilities, Data Processing, SDKs.*
*Philosophy: Domain-centric. Submodules are exposed directly.*

```text
my-library/
├── .github/
│   ├── workflows/ci.yml
│   └── copilot-instructions.md  # GitHub Copilot context
├── .cursor/rules/               # Cursor AI rules (optional)
├── .env.template
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version              # Pinned via `uv python pin`
├── CLAUDE.md                    # Claude Code context
├── LICENSE
├── README.md
├── uv.lock
├── pyproject.toml               # MASTER CONFIG (See Section 2)
├── src/
│   └── my_library/              # Package Name (snake_case)
│       ├── __init__.py
│       ├── py.typed             # PEP 561 marker for type stubs
│       │
│       ├── module_a/            # Domain Logic (e.g., datatools)
│       │   ├── __init__.py
│       │   └── logic.py
│       │
│       └── core/                # (Optional) Shared Internal Utils
│           ├── __init__.py
│           ├── config.py        # pydantic-settings
│           └── logging.py       # structlog configuration
│
└── tests/
    ├── __init__.py
    ├── conftest.py              # Shared fixtures
    ├── unit/
    │   └── test_logic.py
    └── integration/
        └── test_cli.py
```

### Option B: The Application Layout

*Best for: Web APIs, CLIs, Background Workers.*
*Philosophy: Decoupled. Logic (`core`) is separate from Entry Points
(`interface`).*

```text
my-app/
├── .github/
│   ├── workflows/ci.yml
│   └── copilot-instructions.md  # GitHub Copilot context
├── .cursor/rules/               # Cursor AI rules (optional)
├── .env.template
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version
├── CLAUDE.md                    # Claude Code context
├── Dockerfile                   # (See references/docker_patterns.md)
├── LICENSE
├── README.md
├── uv.lock
├── pyproject.toml
├── src/
│   └── my_app/
│       ├── __init__.py
│       ├── py.typed
│       ├── core/                # Business Logic (no framework imports)
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── logging.py
│       │   ├── domain.py
│       │   └── services.py
│       │
│       └── interface/           # Entry Points (thin wrappers)
│           ├── __init__.py
│           ├── api.py           # FastAPI
│           └── cli.py           # Typer
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    └── integration/
```

---

## 2. `pyproject.toml` (The Master Config)

This template uses `uv_build` (the default build backend from `uv init --lib`)
and PEP 735 dependency groups.

```toml
# ── Build System ──────────────────────────────────────────────
[build-system]
requires = ["uv_build>=0.11,<1"]
build-backend = "uv_build"

# ── Project Metadata ─────────────────────────────────────────
[project]
name = "my-project"
version = "0.1.0"
description = "Modern Python Project."
authors = [{ name = "Your Name", email = "you@example.com" }]
requires-python = ">=3.12"
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Operating System :: OS Independent",
    "Typing :: Typed",
]
dependencies = [
    "pydantic-settings>=2.0",
]

# ── Feature Extras (for end users: `pip install mylib[cli]`) ─
[project.optional-dependencies]
cli = ["typer[all]"]

# ── Dependency Groups (PEP 735 — dev only, never published) ──
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

# ── Ruff (Linter & Formatter) ────────────────────────────────
[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src"]
exclude = [".git", ".venv", "dist", "build", "__pycache__"]

[tool.ruff.lint]
select = [
    "E", "W",   # pycodestyle
    "F",         # pyflakes
    "B",         # flake8-bugbear
    "S",         # flake8-bandit (security)
    "I",         # isort
    "N",         # pep8-naming
    "UP",        # pyupgrade
    "C4",        # flake8-comprehensions
    "ISC",       # implicit-str-concat
    "SIM",       # flake8-simplify
    "T20",       # flake8-print
    "PT",        # flake8-pytest-style
    "Q",         # flake8-quotes
    "RUF",       # ruff-specific
    "ANN",       # flake8-annotations
    "ASYNC",     # flake8-async
    "TC",        # flake8-type-checking (TYPE_CHECKING block optimization)
]

[tool.ruff.lint.flake8-quotes]
inline-quotes = "single"
docstring-quotes = "double"
multiline-quotes = "double"

[tool.ruff.lint.isort]
# ACTION: Update this to match the package name
known-first-party = ["my_project"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "ANN"]
"sandbox.py" = ["ALL"]

[tool.ruff.format]
quote-style = "single"
indent-style = "space"
skip-magic-trailing-comma = false

# ── ty (Astral Type Checker) ─────────────────────────────────
# ty uses pyproject.toml [tool.ty] or ty.toml for configuration.
# Minimal config — ty has sensible defaults.

# ── Mypy (stable alternative / secondary CI check) ───────────
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
check_untyped_defs = true
no_implicit_optional = true
ignore_missing_imports = true
pretty = true

# ── Pytest Configuration ─────────────────────────────────────
[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q --cov=src --strict-markers"
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks integration tests",
]
```

---

## 3. GitHub Actions CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13", "3.14"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --frozen

      - name: Lint
        run: uv run ruff check src tests

      - name: Format check
        run: uv run ruff format --check src tests

      - name: Type check (ty)
        run: uv run ty check src

      - name: Tests
        run: uv run pytest --cov-report=xml

      - name: Security audit
        run: uv run pip-audit

      # Optional: secondary type check with mypy
      # - name: Type check (mypy)
      #   run: uv run mypy src
```

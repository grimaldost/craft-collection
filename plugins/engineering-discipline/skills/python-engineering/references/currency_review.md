# Currency Review Protocol

This file defines a structured process for keeping the python-engineering skill
aligned with the evolving Python ecosystem. Run this review **quarterly** or
whenever a major tool release is announced.

---

## Quick Start

Run the version checker to see what's current vs. what the skill pins:

```bash
python scripts/check_versions.py
```

Or with JSON output for programmatic use:

```bash
python scripts/check_versions.py --json
```

Then work through the checklist below.

---

## Review Checklist

### 1. Tool Versions & Compatibility

Check each tool in the canonical stack for new releases:

- [ ] **uv** — Check [astral.sh/blog](https://astral.sh/blog) and
  [github.com/astral-sh/uv/releases](https://github.com/astral-sh/uv/releases).
  Look for: new subcommands, changed defaults, new PEP support, `uv init`
  template changes, deprecations.

- [ ] **ruff** — Check
  [github.com/astral-sh/ruff/releases](https://github.com/astral-sh/ruff/releases).
  Look for: new rule categories worth adding to the `select` list, formatter
  style guide changes (e.g., the 2026 style guide in v0.15), removed/renamed
  rules, new `target-version` options.

- [ ] **ty** — Check
  [github.com/astral-sh/ty/releases](https://github.com/astral-sh/ty/releases).
  Look for: graduation from beta to stable, new configuration options,
  `[tool.ty]` schema changes, pre-commit hook availability, new diagnostic
  rules worth enabling.

- [ ] **mypy** — Check
  [github.com/python/mypy/releases](https://github.com/python/mypy/releases).
  Look for: new Python version support, plugin API changes, strict mode
  additions, deprecations.

- [ ] **pytest** — Check
  [github.com/pytest-dev/pytest/releases](https://github.com/pytest-dev/pytest/releases).
  Look for: new fixtures, changed defaults, deprecated features, minimum
  Python version bumps.

- [ ] **pytest-asyncio** — Check for `asyncio_mode` changes, new decorators,
  compatibility with latest pytest.

- [ ] **pydantic-settings** — Check for new `SettingsConfigDict` options,
  source providers, breaking changes.

- [ ] **structlog** — Check for new processors, renderer changes, stdlib
  bridge improvements.

- [ ] **opentelemetry-api / opentelemetry-sdk** — Check for signal stability
  changes (traces=stable, metrics=stable, logs=experimental). Check for
  new auto-instrumentation packages.

- [ ] **hypothesis** — Check for new strategies, changed defaults, new
  features.

- [ ] **pip-audit** — Check for new vulnerability database integrations,
  changed output formats.

- [ ] **pre-commit hooks** — Check that pinned `rev:` values in
  `.pre-commit-config.yaml` template are reasonably current. Update
  `pre-commit-hooks`, `ruff-pre-commit`, and any new hooks worth adding.

### 2. Python Version Policy

- [ ] **EOL check**: Verify which Python versions have reached end-of-life.
  Update `requires-python`, `target-version`, `python_version`, and the CI
  matrix accordingly. Reference:
  [devguide.python.org/versions](https://devguide.python.org/versions/).

- [ ] **New stable release**: If a new Python stable version shipped (e.g.,
  3.15), add it to the CI matrix and classifiers. Test that all recommended
  tools support it.

- [ ] **New language features**: Check if new PEPs affect recommendations.
  Examples: PEP 649 (deferred evaluation), PEP 750 (template strings),
  PEP 758 (unparenthesized except). Update code examples if a new syntax is
  now idiomatic.

### 3. PEP & Packaging Standards

- [ ] **PEP 735** (Dependency Groups): Check for new tool support beyond uv.
  If pip adds native support, update the Docker patterns.

- [ ] **PEP 751** (pylock.toml): Check if this has been adopted. If so,
  consider adding `uv export --format pylock.toml` guidance.

- [ ] **Build backends**: Check if `uv_build` has graduated to 1.0 or if
  there are meaningful changes. Check if hatchling has new features worth
  noting.

- [ ] **New PEPs**: Scan
  [peps.python.org](https://peps.python.org/#accepted-peps-accepted-but-not-yet-implemented)
  for accepted packaging/typing PEPs that affect recommendations.

### 4. Ecosystem Shifts

- [ ] **Astral toolchain consolidation**: Check if ruff, ty, and uv have
  merged any configuration or if there's a unified config format.

- [ ] **ty stability**: If ty has reached stable (1.0+), update the skill to
  make it the sole primary recommendation and demote mypy to "legacy /
  plugin-dependent" status.

- [ ] **New tools**: Scan Python community (Reddit r/Python, Hacker News,
  Python Bytes podcast, pydevtools.com) for tools gaining significant traction
  that might warrant inclusion or mention.

- [ ] **Deprecated patterns**: Check if any recommended patterns have been
  superseded. Examples: new structlog API, new pytest-asyncio mode, new
  FastAPI patterns (e.g., Pydantic v3).

### 5. CI/CD & Docker

- [ ] **GitHub Actions**: Check if `astral-sh/setup-uv` has a new major
  version. Check if `actions/checkout`, `docker/build-push-action`, etc.
  have new versions.

- [ ] **Docker base images**: Verify `python:X.XX-slim` tags are current.
  Check if the uv Docker copy pattern
  (`COPY --from=ghcr.io/astral-sh/uv:latest`) is still recommended.

- [ ] **Security**: Check for any supply-chain security changes (Sigstore,
  SBOM requirements, new PyPI policies).

### 6. Skill Structure

- [ ] **Line counts**: Verify SKILL.md stays under 500 lines. If it's
  growing, move content to reference files.

- [ ] **Cross-references**: Verify all `references/` file paths in SKILL.md
  point to files that exist and have correct content.

- [ ] **Code examples**: Run the code snippets mentally or in a sandbox to
  verify they're syntactically valid with current tool versions.

- [ ] **Description**: Re-evaluate the frontmatter description. Does it
  still trigger correctly? Are there new trigger phrases to add?

---

## After the Review

1. Update version pins in `SKILL.md`, `references/project_templates.md`, and
   the pre-commit config template.
2. Update `scripts/check_versions.py` TOOLS dict if packages were added or
   removed from the stack.
3. Update the skill title if the naming convention has changed.
4. Re-package the `.skill` file if distributing via claude.ai.
5. Commit changes with a message like:
   `chore(skill): quarterly currency review — YYYY-QN`

---

## Key Sources to Monitor

| Source                                    | What to watch for                |
|-------------------------------------------|----------------------------------|
| [astral.sh/blog](https://astral.sh/blog)  | uv, ruff, ty releases           |
| [PyPI release feeds](https://pypi.org)     | Tool version bumps               |
| [Python Insider](https://blog.python.org)  | CPython releases, PEP status     |
| [devguide.python.org/versions](https://devguide.python.org/versions/) | EOL schedule  |
| [peps.python.org](https://peps.python.org) | New accepted PEPs               |
| [Python Bytes podcast](https://pythonbytes.fm) | Community trends             |
| [r/Python](https://reddit.com/r/Python)   | Emerging tools, community shifts |
| [pydevtools.com](https://pydevtools.com)   | Tooling comparisons, guides     |

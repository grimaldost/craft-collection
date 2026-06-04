# Supply-Chain Security Guide

This file covers Python supply-chain security practices: dependency auditing,
Trusted Publishers, Sigstore attestations, and CI pipeline integration.

## 1. Dependency Auditing with pip-audit

`pip-audit` scans your dependency tree against the OSV (Open Source
Vulnerabilities) database for known CVEs.

```bash
# Install as a dev dependency
uv add --group dev pip-audit

# Scan the current environment
uv run pip-audit

# Scan from requirements (useful in CI)
uv run pip-audit -r requirements.txt

# JSON output for programmatic processing
uv run pip-audit --format json --output audit-results.json
```

Add to your CI workflow:

```yaml
      - name: Security audit
        run: uv run pip-audit
```

## 2. Ruff Security Rules (Bandit Equivalent)

Ruff's `S` rule category (flake8-bandit) provides static security analysis
at 10-100x the speed of standalone Bandit. These rules are already included
in the recommended `select` list in `project_templates.md`.

Key rules to be aware of:
- `S101`: Use of `assert` in production code (ignored in tests via per-file-ignores)
- `S105`: Hardcoded password strings
- `S106`: Hardcoded password arguments
- `S301-S303`: Pickle and insecure hash usage
- `S608`: SQL injection via string formatting

## 3. Dependency Pinning with Hashes

`uv lock` generates a lockfile with cryptographic hashes for every dependency.
Always commit `uv.lock` and use `--frozen` in CI:

```bash
uv sync --frozen   # Fail if lockfile is out of date
```

This ensures bit-for-bit reproducible installs and detects tampering.

## 4. Trusted Publishers (PyPI)

For any package you publish to PyPI, configure **Trusted Publishing** to
eliminate long-lived API tokens. This uses OpenID Connect (OIDC) to
authenticate your CI directly with PyPI.

Setup in GitHub Actions:

1. Go to PyPI → Your Project → Publishing → Add a new publisher
2. Select GitHub Actions and configure your repo/workflow/environment
3. Update your publish workflow:

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  push:
    tags: ["v*"]

permissions:
  id-token: write  # Required for OIDC

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi  # Optional: use environment protection rules
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5

      - name: Build
        run: uv build

      - name: Publish
        uses: pypa/gh-action-pypi-publish@release/v1
        # No API token needed — uses OIDC
```

## 5. Sigstore Attestations

When using `gh-action-pypi-publish`, Sigstore attestations are generated
automatically (PEP 740). These provide cryptographic proof of provenance:
which CI workflow, from which commit, built the artifact. Over 132,000
packages on PyPI have attestations as of early 2026.

No additional configuration is needed — the GitHub Action handles it.

## 6. Complete CI Security Pipeline

Combine all security checks in your CI workflow:

```yaml
      # After installing dependencies
      - name: Lint (includes security rules)
        run: uv run ruff check src tests

      - name: Security audit
        run: uv run pip-audit

      - name: Verify lockfile integrity
        run: uv sync --frozen
```

## 7. Additional Recommendations

- **Never commit secrets** to git. Use `.env` (gitignored) + `pydantic-settings`
  with `SecretStr` for runtime secret handling.
- **Enable GitHub Dependabot** or **Renovate** for automated dependency
  update PRs. Both work well with `uv.lock`.
- **Review new dependencies** before adding them. Check download counts,
  maintenance activity, and known vulnerabilities on PyPI and Snyk.
- **SBOM generation** via CycloneDX format is trending toward compliance
  requirements. Consider `cyclonedx-bom` for regulated environments.

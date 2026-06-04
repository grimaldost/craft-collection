# Docker Patterns for Python with uv

This file provides production-grade Dockerfile patterns using `uv` for
dependency management.

## 1. Multi-Stage Dockerfile (Application)

This is the recommended pattern for deploying Python applications. It uses
multi-stage builds to keep the final image small and secure.

```dockerfile
# ── Stage 1: Build ────────────────────────────────────────────
FROM python:3.14-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies without the project itself
# --frozen ensures the lockfile is not updated
# --no-install-project skips installing the current package
RUN uv sync --frozen --no-install-project --no-dev

# Copy source code
COPY src/ src/
COPY README.md ./

# Install the project itself
RUN uv sync --frozen --no-dev

# ── Stage 2: Runtime ─────────────────────────────────────────
FROM python:3.14-slim AS runtime

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Ensure the venv's Python is on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Don't buffer stdout/stderr
ENV PYTHONUNBUFFERED=1

# Run as non-root
RUN useradd --create-home appuser
USER appuser

# Default command (adjust to your app)
CMD ["python", "-m", "my_app"]
```

## 2. Key Principles

### Layer Caching

The Dockerfile copies `pyproject.toml` and `uv.lock` *before* the source
code. This means dependency installation is cached and only re-runs when
dependencies change — not on every code change.

### --frozen Flag

Always use `--frozen` in Docker builds and CI. This ensures the lockfile is
not updated during the build, guaranteeing reproducible installs.

### --no-dev Flag

Production images should never include development dependencies. The `--no-dev`
flag excludes the `dev` dependency group.

### Non-root User

Always run the application as a non-root user for security.

## 3. Dockerfile for Libraries (Testing Only)

Libraries don't typically ship as Docker images, but you may want a container
for CI or testing:

```dockerfile
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY src/ src/
COPY tests/ tests/
RUN uv sync --frozen

CMD ["uv", "run", "pytest"]
```

## 4. Docker Compose (Development)

For local development with hot-reload:

```yaml
# compose.yml
services:
  app:
    build:
      context: .
      target: builder    # Use the builder stage for dev
    volumes:
      - ./src:/app/src   # Hot-reload source code
    ports:
      - "8000:8000"
    environment:
      - DEBUG=true
    command: uv run uvicorn my_app.interface.api:app --reload --host 0.0.0.0
```

## 5. .dockerignore

Always include a `.dockerignore` to keep the build context small:

```text
.git
.venv
__pycache__
*.pyc
.env
.mypy_cache
.ruff_cache
.pytest_cache
dist
build
*.egg-info
node_modules
```

## 6. GitHub Actions with Docker

For CI that builds and pushes Docker images:

```yaml
# .github/workflows/docker.yml
name: Docker

on:
  push:
    tags: ["v*"]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

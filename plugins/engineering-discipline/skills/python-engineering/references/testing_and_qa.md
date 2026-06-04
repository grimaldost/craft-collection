# Testing & QA Guide

This file defines the standards for testing, built on the `pytest` framework
with Hypothesis for property-based testing, snapshot testing for complex
outputs, and testcontainers for integration tests.

## 1. The Standard Framework: `pytest`

We strictly use `pytest` over `unittest`.

- **Why**: Simple `assert` syntax, powerful fixtures, ecosystem dominance.
- **Location**: All tests reside in `tests/`, with `unit/` and `integration/`
  subdirectories.

## 2. Test Categories

### A. Unit Tests (`tests/unit/`)

Test the **Core Domain** logic. These must be fast, run in memory, and have
**zero** external dependencies (no DB, no API calls, no filesystem).

```python
# tests/unit/test_logic.py
import pytest

from my_package.module_a.logic import calculate_curve


def test_calculate_curve_standard():
    """Test standard calculation logic."""
    # Arrange
    data = [1, 2, 3]

    # Act
    result = calculate_curve(data)

    # Assert
    assert result.is_valid


def test_calculate_curve_empty_raises():
    """Empty input should raise ValueError."""
    with pytest.raises(ValueError, match='empty'):
        calculate_curve([])


@pytest.mark.parametrize(
    ('input_data', 'expected'),
    [
        ([1], 1.0),
        ([1, 2], 1.5),
        ([1, 2, 3], 2.0),
    ],
)
def test_calculate_curve_parametrized(input_data, expected):
    """Parametrized test for multiple inputs."""
    result = calculate_curve(input_data)
    assert result.value == pytest.approx(expected)
```

### B. Integration Tests (`tests/integration/`)

Test the **interaction** between components or with external systems
(filesystem, DB, API interface, CLI).

```python
# tests/integration/test_cli.py
import pytest
from typer.testing import CliRunner

from my_package.interface.cli import app

runner = CliRunner()


@pytest.mark.integration
def test_cli_version_command():
    """Test that the CLI app starts and reports version."""
    result = runner.invoke(app, ['--version'])
    assert result.exit_code == 0
    assert 'v0.1.0' in result.stdout
```

## 3. Property-Based Testing with Hypothesis

Hypothesis generates randomized inputs to find edge cases that manual test
cases miss. Each property-based test catches roughly **50× more mutations**
than a typical unit test.

**Use Hypothesis for**: data processing, serialization/deserialization,
algorithmic code, parsers, validators, and any function with a clear
input-output contract.

```python
# tests/unit/test_serialization.py
from hypothesis import given, strategies as st

from my_package.core.models import Transaction


@given(
    amount=st.decimals(min_value=0, max_value=1_000_000, places=2),
    currency=st.sampled_from(['USD', 'BRL', 'EUR']),
)
def test_transaction_roundtrip(amount, currency):
    """Serializing and deserializing a Transaction is lossless."""
    txn = Transaction(amount=amount, currency=currency)
    serialized = txn.to_dict()
    restored = Transaction.from_dict(serialized)
    assert restored == txn


@given(data=st.lists(st.integers(), min_size=1))
def test_sort_is_idempotent(data):
    """Sorting twice produces the same result as sorting once."""
    once = sorted(data)
    twice = sorted(once)
    assert once == twice
```

Install: `uv add --group test hypothesis`

## 4. Snapshot Testing

Snapshot testing eliminates the tedium of writing assertions for complex
data structures. Two approaches:

### A. inline-snapshot (source-code-embedded)

The expected value lives in the test source file itself. Run
`pytest --inline-snapshot=fix` to auto-populate or update snapshots.

```python
from inline_snapshot import snapshot


def test_api_response_shape():
    """Verify the API response structure."""
    result = build_response(user_id='u_1')
    assert result == snapshot({
        'user_id': 'u_1',
        'status': 'active',
        'permissions': ['read', 'write'],
    })
```

Install: `uv add --group test inline-snapshot`

### B. syrupy (file-based)

Stores snapshots in `__snapshots__/` directories as `.ambr` files. Better
for large or binary outputs. Run `pytest --snapshot-update` to regenerate.

```python
def test_report_output(snapshot):
    """Verify the full report output."""
    report = generate_report(period='Q3')
    assert report == snapshot
```

Install: `uv add --group test syrupy`

## 5. Integration Testing with Testcontainers

For integration tests that need real databases, use `testcontainers-python`
instead of mocking. It spins up disposable Docker containers per test session.

```python
# tests/integration/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope='session')
def postgres_url():
    """Provide a real PostgreSQL URL for integration tests."""
    with PostgresContainer('postgres:16') as pg:
        yield pg.get_connection_url()


# tests/integration/test_repository.py
@pytest.mark.integration
def test_save_and_retrieve(postgres_url):
    """Test real database round-trip."""
    repo = PostgresRepository(postgres_url)
    entity_id = repo.save({'name': 'test'})
    result = repo.get(entity_id)
    assert result['name'] == 'test'
```

Install: `uv add --group test testcontainers`

## 6. HTTP Testing

For testing code that calls external HTTP APIs:

- **respx**: deterministic mock for httpx in unit tests
- **pytest-recording + VCR.py**: record-and-replay for integration tests
  against real APIs (record once, replay forever)

```python
# Unit test with respx (no network)
import httpx
import respx

@respx.mock
async def test_fetch_user():
    respx.get('https://api.example.com/users/1').respond(
        json={'id': 1, 'name': 'Alice'},
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get('https://api.example.com/users/1')
    assert resp.json()['name'] == 'Alice'
```

## 7. Fixtures (`conftest.py`)

Use `conftest.py` at the `tests/` root for shared fixtures. Prefer factory
fixtures over complex setup:

```python
# tests/conftest.py
import pytest

from my_package.core.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    """Provide test settings with isolated temp directory."""
    return Settings(
        DEBUG=True,
        APP_NAME='test',
        API_KEY='test-secret',  # noqa: S106
    )


@pytest.fixture
def sample_data():
    """Factory fixture for sample data."""
    def _make(n: int = 10):
        return list(range(1, n + 1))
    return _make
```

## 8. Async Testing

With `pytest-asyncio` and `asyncio_mode = "auto"` in `pyproject.toml`, async
tests just work:

```python
async def test_fetch_data():
    """Async test — no decorator needed with asyncio_mode='auto'."""
    result = await fetch_data(source='test')
    assert result is not None
```

## 9. Coverage

Coverage is configured via `pyproject.toml` (`addopts = "--cov=src"`).

For CI, generate an XML report for upload to coverage services:

```bash
uv run pytest --cov-report=xml --cov-report=term-missing
```

## 10. Pytest Configuration Reference

Your `pyproject.toml` should include:

```toml
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

Key flags: `-ra` shows summary of all test outcomes except passed, `-q` for
quiet output, `--cov=src` measures coverage of the `src/` directory,
`--strict-markers` fails on unregistered markers (prevents typos).

## 11. Running Tests

```bash
uv run pytest                       # All tests
uv run pytest tests/unit            # Unit tests only
uv run pytest -m 'not integration'  # Skip integration tests
uv run pytest -m 'not slow'         # Skip slow tests
uv run pytest -x                    # Stop on first failure
uv run pytest -k 'test_calculate'   # Run tests matching pattern
```

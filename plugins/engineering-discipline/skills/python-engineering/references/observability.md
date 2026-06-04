# Observability Guide

This file provides the complete observability setup: structlog for structured
logging, OpenTelemetry for distributed traces and metrics, and the correlation
pattern that ties them together.

## 1. Full Structlog Configuration with stdlib Bridge

The stdlib bridge routes Python's built-in `logging` (used by third-party
libraries like `uvicorn`, `sqlalchemy`, `httpx`) through structlog's pipeline.

```python
# src/my_package/core/logging.py
import logging
import sys

import structlog


def configure_logging(*, log_level: str = 'INFO') -> None:
    """Configure structured logging with stdlib bridge.

    JSON in production (non-TTY), pretty-printed in development (TTY).
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt='iso'),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if sys.stdout.isatty():
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # Quiet noisy third-party loggers
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
```

## 2. OpenTelemetry Trace ID Correlation

Inject `trace_id` and `span_id` from the active OTel span into every log
entry. This allows jumping from a trace span to the exact logs in your
observability backend (Grafana, Datadog, Elasticsearch).

```python
# src/my_package/core/otel.py
from opentelemetry import trace


def add_otel_trace_context(
    _logger: object,
    _method_name: str,
    event_dict: dict,
) -> dict:
    """Structlog processor: inject OTel trace/span IDs into log entries."""
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        event_dict['trace_id'] = format(ctx.trace_id, '032x')
        event_dict['span_id'] = format(ctx.span_id, '016x')
    return event_dict
```

Add this processor to the shared processors list in `configure_logging()`:

```python
shared_processors: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    add_otel_trace_context,  # <-- inject trace context
    structlog.stdlib.add_log_level,
    # ... rest of processors
]
```

## 3. OpenTelemetry SDK Setup

```python
# src/my_package/core/telemetry.py
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_telemetry(*, service_name: str) -> None:
    """Configure OpenTelemetry tracing with OTLP export."""
    resource = Resource.create({'service.name': service_name})
    provider = TracerProvider(resource=resource)

    # Export spans to an OTel Collector (default: localhost:4317)
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
```

## 4. FastAPI Integration

```python
# src/my_package/interface/api.py
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from my_package.core.logging import configure_logging
from my_package.core.telemetry import configure_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_telemetry(service_name='my-service')
    yield


app = FastAPI(lifespan=lifespan)

# One line: automatic HTTP span creation for all routes
FastAPIInstrumentor.instrument_app(app)
```

Required packages:

```bash
uv add opentelemetry-api opentelemetry-sdk
uv add opentelemetry-exporter-otlp-proto-grpc
uv add opentelemetry-instrumentation-fastapi
```

## 5. Request-Scoped Context with contextvars

Bind request context once in middleware — it appears in all log lines:

```python
# src/my_package/interface/middleware.py
import uuid

import structlog


async def logging_middleware(request, call_next):
    """Bind request-scoped context for all log lines."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=str(uuid.uuid4()),
        path=request.url.path,
        method=request.method,
    )
    response = await call_next(request)
    return response
```

## 6. Using the Logger

```python
import structlog

logger = structlog.get_logger()


def process_payment(user_id: str, amount: float) -> None:
    log = logger.bind(user_id=user_id, amount=amount)

    log.info('payment_started')
    # ... business logic ...
    log.info('payment_completed', transaction_id='txn_123')
```

## 7. Startup Integration

### Typer CLI

```python
import typer

from my_package.core.logging import configure_logging

app = typer.Typer()


@app.callback()
def main() -> None:
    """Application entry point."""
    configure_logging()
```

## 8. Testing with structlog

```python
import structlog


def test_payment_logs_started():
    """Verify structured log output."""
    with structlog.testing.capture_logs() as cap_logs:
        process_payment(user_id='u_1', amount=99.99)

    assert cap_logs[0]['event'] == 'payment_started'
    assert cap_logs[0]['user_id'] == 'u_1'
    assert cap_logs[0]['log_level'] == 'info'
```

## 9. Configuration via pydantic-settings

Integrate log level and OTel endpoint with your app config:

```python
class Settings(BaseSettings):
    LOG_LEVEL: str = 'INFO'
    OTEL_EXPORTER_OTLP_ENDPOINT: str = 'http://localhost:4317'
    OTEL_SERVICE_NAME: str = 'my-service'
    # ...

settings = Settings()
configure_logging(log_level=settings.LOG_LEVEL)
configure_telemetry(service_name=settings.OTEL_SERVICE_NAME)
```

## 10. When to Use What

- **Structlog alone**: scripts, CLIs, simple services without distributed tracing needs.
- **Structlog + OpenTelemetry traces**: any multi-service or API-backed application.
- **Full stack (traces + metrics + logs)**: production services where you need
  SLO monitoring, latency histograms, and correlated debugging.

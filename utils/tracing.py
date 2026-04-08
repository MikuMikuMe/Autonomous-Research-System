"""
Distributed Tracing — OpenTelemetry and LangSmith integration.

Provides both context managers and decorators for tracing:
  - LLM API calls
  - Agent executions
  - Pipeline phases

Works with:
  - OpenTelemetry-compatible backends (Jaeger, Zipkin, OTLP)
  - LangSmith (via LANGCHAIN_API_KEY)
  - Lightweight SpanRecord fallback when no backend configured

Configuration:
  OTEL_EXPORTER_OTLP_ENDPOINT  — OTLP endpoint (e.g., http://localhost:4317)
  OTEL_SERVICE_NAME             — Service name (default: autonomous-research)
  LANGCHAIN_API_KEY             — Enable LangSmith tracing
  TRACE_ENABLED                 — Set to "false" to disable (default: enabled)
  Or via configs/pipeline.yaml -> tracing section

Usage (context managers):
    with trace_agent("research_agent", iteration=3) as span_data:
        result = do_work()

    with trace_llm_call("generate", model="gemini-2.5-flash") as span_data:
        response = llm.generate(prompt)

Usage (decorators):
    @trace_agent_decorator("research_agent")
    def my_agent_function(): ...

    @trace_llm_decorator
    def my_llm_call(): ...
"""

from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _tracing_config() -> dict:
    """Load tracing config from pipeline.yaml."""
    try:
        from utils.config_loader import load_pipeline_config
        return load_pipeline_config().get("tracing", {})
    except Exception:
        return {}


def is_tracing_enabled() -> bool:
    """Check if distributed tracing is enabled."""
    # Env var override
    env_val = os.environ.get("TRACE_ENABLED", "").lower()
    if env_val == "false":
        return False
    if env_val == "true":
        return True
    # Check config
    cfg = _tracing_config()
    if cfg.get("enabled") is not None:
        return bool(cfg["enabled"])
    # Check LangSmith env var
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        return True
    # Default: enabled
    return True


TRACE_ENABLED = is_tracing_enabled()
_trace_records: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Lightweight SpanRecord fallback
# ---------------------------------------------------------------------------

@dataclass
class SpanRecord:
    """Lightweight span record for when OpenTelemetry is not installed."""
    name: str
    start_time: float
    end_time: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


# ---------------------------------------------------------------------------
# OpenTelemetry setup
# ---------------------------------------------------------------------------

_tracer = None


def _try_init_otel():
    """Try to initialize OpenTelemetry. Returns tracer or None."""
    global _tracer
    if _tracer is not None:
        return _tracer

    if not TRACE_ENABLED:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({
            "service.name": os.environ.get(
                "OTEL_SERVICE_NAME",
                _tracing_config().get("service_name", "autonomous-research"),
            ),
        })
        provider = TracerProvider(resource=resource)

        # Try OTLP exporter first
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
            except ImportError:
                pass
        else:
            # Console exporter for development
            try:
                from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            except ImportError:
                pass

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("autonomous-research")
        return _tracer
    except ImportError:
        return None
    except Exception:
        return None


def get_tracer():
    """Get the OpenTelemetry tracer (or None if not available)."""
    return _try_init_otel()


# ---------------------------------------------------------------------------
# LangSmith helpers
# ---------------------------------------------------------------------------

def _ensure_langsmith_configured() -> bool:
    """Ensure LangSmith env vars are set. Returns True if available."""
    if not os.environ.get("LANGCHAIN_API_KEY"):
        return False
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    cfg = _tracing_config()
    project = cfg.get("langsmith_project", "autonomous-research")
    os.environ.setdefault("LANGCHAIN_PROJECT", project)
    return True


# ---------------------------------------------------------------------------
# Context-manager APIs (primary)
# ---------------------------------------------------------------------------

@contextmanager
def trace_llm_call(
    operation: str,
    *,
    model: str = "",
    provider: str = "",
    prompt_length: int = 0,
    **extra_attrs: Any,
) -> Generator[dict[str, Any], None, None]:
    """Trace an LLM API call (context manager).

    Usage:
        with trace_llm_call("generate", model="gemini-2.5-flash") as span_data:
            result = client.generate(prompt)
            span_data["response_length"] = len(result)
    """
    span_data: dict[str, Any] = {
        "model": model,
        "provider": provider,
        "prompt_length": prompt_length,
        **extra_attrs,
    }

    if not TRACE_ENABLED:
        yield span_data
        return

    tracer = _try_init_otel()
    start = time.time()

    if tracer:
        try:
            with tracer.start_as_current_span(f"llm.{operation}") as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.provider", provider)
                span.set_attribute("llm.prompt_length", prompt_length)
                for k, v in extra_attrs.items():
                    span.set_attribute(f"llm.{k}", str(v))
                try:
                    yield span_data
                    span.set_attribute("llm.response_length", span_data.get("response_length", 0))
                except Exception as e:
                    span.record_exception(e)
                    raise
        except Exception:
            yield span_data
    else:
        try:
            yield span_data
            record = SpanRecord(
                name=f"llm.{operation}",
                start_time=start,
                end_time=time.time(),
                attributes=span_data,
            )
            _trace_records.append(record.__dict__)
        except Exception as e:
            record = SpanRecord(
                name=f"llm.{operation}",
                start_time=start,
                end_time=time.time(),
                attributes=span_data,
                status="error",
                error=str(e),
            )
            _trace_records.append(record.__dict__)
            raise


@contextmanager
def trace_agent(
    agent_name: str,
    *,
    iteration: int = 0,
    seed: int = 0,
    **extra_attrs: Any,
) -> Generator[dict[str, Any], None, None]:
    """Trace an agent execution span (context manager).

    Usage:
        with trace_agent("cross_validation", iteration=3) as span_data:
            result = run_agent()
            span_data["claims_verified"] = 5
    """
    span_data: dict[str, Any] = {
        "agent": agent_name,
        "iteration": iteration,
        "seed": seed,
        **extra_attrs,
    }

    if not TRACE_ENABLED:
        yield span_data
        return

    tracer = _try_init_otel()
    start = time.time()

    if tracer:
        try:
            with tracer.start_as_current_span(f"agent.{agent_name}") as span:
                span.set_attribute("agent.name", agent_name)
                span.set_attribute("agent.iteration", iteration)
                span.set_attribute("agent.seed", seed)
                for k, v in extra_attrs.items():
                    span.set_attribute(f"agent.{k}", str(v))
                try:
                    yield span_data
                except Exception as e:
                    span.record_exception(e)
                    raise
        except Exception:
            yield span_data
    else:
        try:
            yield span_data
            record = SpanRecord(
                name=f"agent.{agent_name}",
                start_time=start,
                end_time=time.time(),
                attributes=span_data,
            )
            _trace_records.append(record.__dict__)
        except Exception as e:
            record = SpanRecord(
                name=f"agent.{agent_name}",
                start_time=start,
                end_time=time.time(),
                attributes=span_data,
                status="error",
                error=str(e),
            )
            _trace_records.append(record.__dict__)
            raise


@contextmanager
def trace_pipeline(
    mode: str,
    *,
    goal: str = "",
    **extra_attrs: Any,
) -> Generator[dict[str, Any], None, None]:
    """Trace an entire pipeline run (context manager)."""
    span_data: dict[str, Any] = {"mode": mode, "goal": goal, **extra_attrs}

    if not TRACE_ENABLED:
        yield span_data
        return

    tracer = _try_init_otel()
    start = time.time()

    if tracer:
        try:
            with tracer.start_as_current_span(f"pipeline.{mode}") as span:
                span.set_attribute("pipeline.mode", mode)
                span.set_attribute("pipeline.goal", goal)
                try:
                    yield span_data
                except Exception as e:
                    span.record_exception(e)
                    raise
        except Exception:
            yield span_data
    else:
        try:
            yield span_data
        finally:
            record = SpanRecord(
                name=f"pipeline.{mode}",
                start_time=start,
                end_time=time.time(),
                attributes=span_data,
            )
            _trace_records.append(record.__dict__)


# Alias for compatibility with remote-style API
trace_phase = trace_pipeline


# ---------------------------------------------------------------------------
# Decorator APIs (alternative)
# ---------------------------------------------------------------------------

def trace_llm_decorator(func: Callable) -> Callable:
    """Decorator to trace LLM calls with timing and metadata."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not TRACE_ENABLED:
            return func(*args, **kwargs)

        start = time.time()

        # Try LangSmith
        try:
            if _ensure_langsmith_configured():
                from langsmith import traceable
                traced = traceable(name=func.__name__, tags=["llm"])(func)
                return traced(*args, **kwargs)
        except Exception:
            pass

        # Fallback to OTel
        tracer = _try_init_otel()
        if tracer:
            with tracer.start_as_current_span(f"llm.{func.__name__}") as span:
                span.set_attribute("llm.function", func.__name__)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("llm.duration_ms", (time.time() - start) * 1000)
                    return result
                except Exception as e:
                    span.set_attribute("llm.error", str(e))
                    raise

        return func(*args, **kwargs)
    return wrapper


def trace_agent_decorator(agent_name: str) -> Callable:
    """Decorator factory to trace agent execution."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not TRACE_ENABLED:
                return func(*args, **kwargs)

            start = time.time()

            # Try LangSmith
            try:
                if _ensure_langsmith_configured():
                    from langsmith import traceable
                    traced = traceable(
                        name=f"agent.{agent_name}",
                        tags=["agent", agent_name],
                    )(func)
                    return traced(*args, **kwargs)
            except Exception:
                pass

            # Fallback to OTel
            tracer = _try_init_otel()
            if tracer:
                with tracer.start_as_current_span(f"agent.{agent_name}") as span:
                    span.set_attribute("agent.name", agent_name)
                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute("agent.duration_ms", (time.time() - start) * 1000)
                        return result
                    except Exception as e:
                        span.set_attribute("agent.error", str(e))
                        raise

            return func(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Record access
# ---------------------------------------------------------------------------

def get_trace_records() -> list[dict[str, Any]]:
    """Get all recorded trace spans (lightweight fallback mode)."""
    return list(_trace_records)


def clear_trace_records() -> None:
    """Clear recorded trace spans."""
    _trace_records.clear()
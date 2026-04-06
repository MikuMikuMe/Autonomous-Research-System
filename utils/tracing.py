"""
Distributed Tracing — LangSmith and OpenTelemetry integration.

Provides tracing decorators and context managers for LLM calls,
agent executions, and pipeline phases.

Enable via configs/pipeline.yaml -> tracing.enabled: true
or env vars: LANGCHAIN_TRACING_V2=true, LANGCHAIN_API_KEY=...
"""

from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _tracing_config() -> dict:
    """Load tracing config from pipeline.yaml."""
    try:
        from utils.config_loader import load_pipeline_config
        return load_pipeline_config().get("tracing", {})
    except Exception:
        return {}


def is_tracing_enabled() -> bool:
    """Check if distributed tracing is enabled."""
    cfg = _tracing_config()
    if cfg.get("enabled"):
        return True
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"


def _ensure_langsmith_configured() -> bool:
    """Ensure LangSmith env vars are set."""
    if not os.environ.get("LANGCHAIN_API_KEY"):
        return False
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    cfg = _tracing_config()
    project = cfg.get("langsmith_project", "autonomous-research")
    os.environ.setdefault("LANGCHAIN_PROJECT", project)
    return True


# ---------------------------------------------------------------------------
# OpenTelemetry setup
# ---------------------------------------------------------------------------

_otel_tracer = None


def _get_otel_tracer():
    """Lazy-init OpenTelemetry tracer."""
    global _otel_tracer
    if _otel_tracer is not None:
        return _otel_tracer
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

        provider = TracerProvider()
        # Console exporter for development; replace with OTLP for production
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _otel_tracer = trace.get_tracer("autonomous-research")
        return _otel_tracer
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def trace_llm_call(func: Callable) -> Callable:
    """Decorator to trace LLM calls with timing and metadata."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_tracing_enabled():
            return func(*args, **kwargs)

        start = time.time()
        metadata = {
            "function": func.__name__,
            "module": func.__module__,
        }

        # Try LangSmith callback
        try:
            if _ensure_langsmith_configured():
                from langsmith import traceable
                traced = traceable(name=func.__name__, tags=["llm"])(func)
                result = traced(*args, **kwargs)
                metadata["duration_ms"] = (time.time() - start) * 1000
                return result
        except Exception:
            pass

        # Fallback to OpenTelemetry
        tracer = _get_otel_tracer()
        if tracer:
            with tracer.start_as_current_span(f"llm.{func.__name__}") as span:
                span.set_attribute("llm.function", func.__name__)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("llm.success", True)
                    span.set_attribute("llm.duration_ms", (time.time() - start) * 1000)
                    return result
                except Exception as e:
                    span.set_attribute("llm.success", False)
                    span.set_attribute("llm.error", str(e))
                    raise

        return func(*args, **kwargs)
    return wrapper


def trace_agent(agent_name: str) -> Callable:
    """Decorator factory to trace agent execution."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not is_tracing_enabled():
                return func(*args, **kwargs)

            start = time.time()

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

            tracer = _get_otel_tracer()
            if tracer:
                with tracer.start_as_current_span(f"agent.{agent_name}") as span:
                    span.set_attribute("agent.name", agent_name)
                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute("agent.success", True)
                        span.set_attribute("agent.duration_ms", (time.time() - start) * 1000)
                        return result
                    except Exception as e:
                        span.set_attribute("agent.success", False)
                        span.set_attribute("agent.error", str(e))
                        raise

            return func(*args, **kwargs)
        return wrapper
    return decorator


@contextmanager
def trace_phase(phase_name: str, metadata: dict | None = None) -> Generator[dict, None, None]:
    """Context manager to trace a pipeline phase."""
    ctx: dict[str, Any] = {"phase": phase_name, "start_time": time.time()}
    if metadata:
        ctx.update(metadata)

    if not is_tracing_enabled():
        yield ctx
        ctx["duration_ms"] = (time.time() - ctx["start_time"]) * 1000
        return

    tracer = _get_otel_tracer()
    if tracer:
        with tracer.start_as_current_span(f"phase.{phase_name}") as span:
            span.set_attribute("phase.name", phase_name)
            if metadata:
                for k, v in metadata.items():
                    span.set_attribute(f"phase.{k}", str(v))
            try:
                yield ctx
                ctx["duration_ms"] = (time.time() - ctx["start_time"]) * 1000
                span.set_attribute("phase.success", True)
                span.set_attribute("phase.duration_ms", ctx["duration_ms"])
            except Exception as e:
                span.set_attribute("phase.success", False)
                span.set_attribute("phase.error", str(e))
                raise
    else:
        yield ctx
        ctx["duration_ms"] = (time.time() - ctx["start_time"]) * 1000

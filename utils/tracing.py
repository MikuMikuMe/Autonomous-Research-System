"""
Distributed Tracing — OpenTelemetry integration for LLM calls and orchestrator.

Provides lightweight tracing that works with:
  - OpenTelemetry-compatible backends (Jaeger, Zipkin, OTLP)
  - LangSmith (via LANGSMITH_API_KEY)
  - Console output (fallback when no backend configured)

Configuration via environment variables:
  OTEL_EXPORTER_OTLP_ENDPOINT  — OTLP endpoint (e.g., http://localhost:4317)
  OTEL_SERVICE_NAME             — Service name (default: autonomous-research)
  LANGSMITH_API_KEY             — Enable LangSmith tracing
  TRACE_ENABLED                 — Set to "false" to disable (default: enabled)

Usage:
    from utils.tracing import trace_llm_call, trace_agent, get_tracer

    with trace_agent("research_agent", iteration=3):
        result = do_work()

    with trace_llm_call("generate", model="gemini-2.5-flash", prompt_tokens=100):
        response = llm.generate(prompt)
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TRACE_ENABLED = os.environ.get("TRACE_ENABLED", "true").lower() != "false"
_tracer = None
_trace_records: list[dict[str, Any]] = []


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
            "service.name": os.environ.get("OTEL_SERVICE_NAME", "autonomous-research"),
        })
        provider = TracerProvider(resource=resource)

        # Try OTLP exporter
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
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


@contextmanager
def trace_llm_call(
    operation: str,
    *,
    model: str = "",
    provider: str = "",
    prompt_length: int = 0,
    **extra_attrs: Any,
) -> Generator[dict[str, Any], None, None]:
    """Trace an LLM API call.

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
                    span.set_status(trace.StatusCode.OK)  # type: ignore[attr-defined]
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))  # type: ignore[attr-defined]
                    span.record_exception(e)
                    raise
        except Exception:
            yield span_data
    else:
        # Lightweight fallback: just record timing
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
    """Trace an agent execution span.

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
                    span.set_status(trace.StatusCode.OK)  # type: ignore[attr-defined]
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))  # type: ignore[attr-defined]
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
    """Trace an entire pipeline run."""
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
                    span.set_status(trace.StatusCode.OK)  # type: ignore[attr-defined]
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))  # type: ignore[attr-defined]
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


def get_trace_records() -> list[dict[str, Any]]:
    """Get all recorded trace spans (lightweight fallback mode)."""
    return list(_trace_records)


def clear_trace_records() -> None:
    """Clear recorded trace spans."""
    _trace_records.clear()

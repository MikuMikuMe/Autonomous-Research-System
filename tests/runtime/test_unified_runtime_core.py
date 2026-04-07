# pyright: reportAny=false
"""Tests for the unified ResearchRuntime core."""

from __future__ import annotations

from pathlib import Path

from runtime.core import ResearchRuntime, RuntimeConfig, RuntimeSummary
from utils.context import ResearchContext
from utils.events import EventBus, EventType, PipelineEvent


def test_runtime_config_loads_defaults() -> None:
    config = RuntimeConfig(
        project_root=Path("."),
        research_agents=["agents.research_agent", "agents.cross_validation_agent"],
    )
    assert config.max_iterations == 10
    assert config.converge_threshold == 0.90
    assert config.flaw_halt_severity == "critical"
    assert len(config.research_agents) == 2


def test_runtime_config_for_mode_returns_dict() -> None:
    config = RuntimeConfig(
        project_root=Path("."),
        research_agents=[],
    )
    overrides = config.for_mode("goal")
    assert isinstance(overrides, dict)


def test_runtime_run_emits_events_and_returns_summary(monkeypatch) -> None:
    events: list[PipelineEvent] = []
    bus = EventBus()
    bus.subscribe(events.append)

    config = RuntimeConfig(
        project_root=Path("."),
        research_agents=["agents.research_agent"],
    )

    fake_report = {
        "converged": True,
        "iterations_completed": 3,
        "verified_ratio": 0.95,
    }

    def fake_research_loop(**kwargs):
        return fake_report

    monkeypatch.setattr(
        "orchestration.continuous_research_loop.run_research_loop",
        fake_research_loop,
    )
    monkeypatch.setattr(ResearchRuntime, "_load_memory_store", lambda self: None)

    runtime = ResearchRuntime(config=config, bus=bus)
    summary = runtime.run(mode="goal", goal="Test research goal")

    assert summary.converged is True
    assert summary.iterations_completed == 3
    assert summary.mode == "goal"
    assert summary.error is None
    assert summary.context.goal == "Test research goal"

    event_types = [e.type for e in events]
    assert EventType.AGENT_STARTED in event_types
    assert EventType.PIPELINE_FINISHED in event_types


def test_runtime_handles_loop_failure_gracefully(monkeypatch) -> None:
    events: list[PipelineEvent] = []
    bus = EventBus()
    bus.subscribe(events.append)

    config = RuntimeConfig(
        project_root=Path("."),
        research_agents=[],
    )

    def failing_loop(**kwargs):
        raise RuntimeError("Research loop exploded")

    monkeypatch.setattr(
        "orchestration.continuous_research_loop.run_research_loop",
        failing_loop,
    )
    monkeypatch.setattr(ResearchRuntime, "_load_memory_store", lambda self: None)

    runtime = ResearchRuntime(config=config, bus=bus)
    summary = runtime.run(mode="goal", goal="Will fail")

    assert summary.converged is False
    assert summary.error == "Research loop exploded"
    assert summary.iterations_completed == 0


def test_pipeline_runtime_alias_is_research_runtime() -> None:
    from runtime.core import PipelineRuntime
    assert PipelineRuntime is ResearchRuntime


def test_runtime_summary_dataclass() -> None:
    ctx = ResearchContext(goal="test")
    summary = RuntimeSummary(
        results={"converged": True},
        converged=True,
        total_duration=1.5,
        iterations_completed=3,
        context=ctx,
        mode="goal",
    )
    assert summary.converged is True
    assert summary.iterations_completed == 3
    assert summary.total_duration == 1.5
    assert summary.mode == "goal"
    assert summary.error is None

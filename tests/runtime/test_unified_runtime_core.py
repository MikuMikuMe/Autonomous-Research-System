from __future__ import annotations

from pathlib import Path

import runtime.core as runtime_core
from runtime.core import PipelineRuntime, RuntimeConfig
from utils.context import PipelineContext
from utils.events import EventBus, EventType, PipelineEvent
from utils.schemas import JudgeResult


def test_runtime_core_runs_agents_and_research_through_shared_flow(monkeypatch) -> None:
    events: list[PipelineEvent] = []
    bus = EventBus()
    bus.subscribe(events.append)

    config = RuntimeConfig(
        project_root=Path("."),
        core_agents=["detection", "mitigation"],
        research_agents=["agents.research_agent"],
    )
    agent_calls: list[tuple[str, int]] = []
    research_calls: list[str] = []

    monkeypatch.setattr(PipelineRuntime, "_load_memory_store", lambda self: None)
    monkeypatch.setattr(
        runtime_core.PipelineContext,
        "load",
        classmethod(lambda cls, seed=42: PipelineContext(seed=seed)),
    )

    runtime = PipelineRuntime(
        config=config,
        bus=bus,
        run_agent=lambda agent, seed, _: agent_calls.append((agent, seed)) or 0,
        run_research_module=lambda module, _: research_calls.append(module) or 0,
        run_judge=lambda agent: JudgeResult(True, [f"{agent} passed"]),
        classify_error=lambda exc, stderr: "Unknown",
        run_format_check=lambda: None,
    )

    summary = runtime.run()

    assert agent_calls == [("detection", 42), ("mitigation", 42)]
    assert research_calls == ["agents.research_agent"]
    assert summary.all_passed is True
    assert summary.results == {
        "detection": {"passed": True, "attempts": 1},
        "mitigation": {"passed": True, "attempts": 1},
    }
    assert [event.type for event in events if event.type == EventType.OUTPUTS_UPDATED] == [
        EventType.OUTPUTS_UPDATED,
        EventType.OUTPUTS_UPDATED,
    ]
    assert events[-1].type == EventType.PIPELINE_FINISHED


def test_runtime_core_retries_failed_attempts_before_passing(monkeypatch) -> None:
    bus = EventBus()
    config = RuntimeConfig(project_root=Path("."), core_agents=["detection"], research_agents=[])
    attempts: list[tuple[str, int]] = []
    returncodes = iter([1, 0])

    monkeypatch.setattr(PipelineRuntime, "_load_memory_store", lambda self: None)
    monkeypatch.setattr(
        runtime_core.PipelineContext,
        "load",
        classmethod(lambda cls, seed=42: PipelineContext(seed=seed)),
    )

    runtime = PipelineRuntime(
        config=config,
        bus=bus,
        run_agent=lambda agent, seed, _: attempts.append((agent, seed)) or next(returncodes),
        run_research_module=lambda module, _: 0,
        run_judge=lambda agent: JudgeResult(True, [f"{agent} passed"]),
        classify_error=lambda exc, stderr: "Unknown",
        run_format_check=lambda: None,
    )

    summary = runtime.run()

    assert attempts == [("detection", 42), ("detection", 44)]
    assert summary.results["detection"] == {"passed": True, "attempts": 2}
    assert summary.all_passed is True

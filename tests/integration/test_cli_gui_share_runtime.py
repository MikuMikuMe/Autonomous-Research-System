from __future__ import annotations

import queue

from gui import streaming_orchestrator
from orchestration import orchestrator
from runtime.core import ResearchRuntime, RuntimeSummary
from utils.context import ResearchContext
from utils.events import EventBus, EventType, PipelineEvent


def test_cli_and_gui_build_the_same_runtime_class() -> None:
    cli_runtime = orchestrator.build_runtime(EventBus())
    gui_runtime = streaming_orchestrator.build_runtime(EventBus())

    assert isinstance(cli_runtime, ResearchRuntime)
    assert isinstance(gui_runtime, ResearchRuntime)
    assert type(cli_runtime) is type(gui_runtime)


def test_cli_entrypoint_delegates_to_shared_runtime(monkeypatch) -> None:
    calls: list[str] = []

    def fake_run(self, **kwargs) -> RuntimeSummary:
        calls.append(type(self).__name__)
        return RuntimeSummary(
            results={"converged": True, "iterations_completed": 1},
            converged=True,
            total_duration=0.0,
            iterations_completed=1,
            context=ResearchContext(goal="test"),
            mode="goal",
        )

    monkeypatch.setattr(ResearchRuntime, "run", fake_run)

    assert orchestrator.main([]) == 0
    assert calls == ["ResearchRuntime"]


def test_gui_entrypoint_delegates_to_shared_runtime(monkeypatch) -> None:
    calls: list[str] = []

    def fake_run(self, **kwargs) -> RuntimeSummary:
        calls.append(type(self).__name__)
        return RuntimeSummary(
            results={"converged": True, "iterations_completed": 1},
            converged=True,
            total_duration=0.0,
            iterations_completed=1,
            context=ResearchContext(goal="test"),
            mode="goal",
        )

    monkeypatch.setattr(ResearchRuntime, "run", fake_run)

    streaming_orchestrator.run_pipeline(queue.Queue())
    assert calls == ["ResearchRuntime"]


def test_cli_prints_memory_events(capsys) -> None:
    orchestrator._print_cli_event(
        PipelineEvent(
            type=EventType.MEMORY_INSIGHT,
            agent="research",
            line="[MEMORY] relevant prior knowledge found",
        )
    )
    orchestrator._print_cli_event(
        PipelineEvent(
            type=EventType.JOURNEY_SUMMARY,
            summary={
                "total_iterations": 5,
                "converged": True,
                "verified_ratio": 0.95,
            },
        )
    )

    out = capsys.readouterr().out
    assert "[MEMORY] relevant prior knowledge found" in out
    assert "RESEARCH JOURNEY SUMMARY" in out

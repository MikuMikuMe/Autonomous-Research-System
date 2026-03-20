from __future__ import annotations

import queue

from gui import streaming_orchestrator
from orchestration import orchestrator
from runtime.core import PipelineRuntime, RuntimeSummary
from utils.context import PipelineContext
from utils.events import EventBus


def test_cli_and_gui_build_the_same_runtime_class() -> None:
    cli_runtime = orchestrator.build_runtime(EventBus())
    gui_runtime = streaming_orchestrator.build_runtime(EventBus())

    assert isinstance(cli_runtime, PipelineRuntime)
    assert isinstance(gui_runtime, PipelineRuntime)
    assert type(cli_runtime) is type(gui_runtime)


def test_cli_entrypoint_delegates_to_shared_runtime(monkeypatch) -> None:
    calls: list[str] = []

    def fake_run(self: PipelineRuntime) -> RuntimeSummary:
        calls.append(type(self).__name__)
        return RuntimeSummary(
            results={"detection": {"passed": True, "attempts": 1}},
            all_passed=True,
            seed=42,
            total_duration=0.0,
            context=PipelineContext(seed=42),
            agent_run_records=[],
        )

    monkeypatch.setattr(PipelineRuntime, "run", fake_run)

    assert orchestrator.main([]) == 0
    assert calls == ["PipelineRuntime"]


def test_gui_entrypoint_delegates_to_shared_runtime(monkeypatch) -> None:
    calls: list[str] = []

    def fake_run(self: PipelineRuntime) -> RuntimeSummary:
        calls.append(type(self).__name__)
        return RuntimeSummary(
            results={"detection": {"passed": True, "attempts": 1}},
            all_passed=True,
            seed=42,
            total_duration=0.0,
            context=PipelineContext(seed=42),
            agent_run_records=[],
        )

    monkeypatch.setattr(PipelineRuntime, "run", fake_run)

    streaming_orchestrator.run_pipeline(queue.Queue())
    assert calls == ["PipelineRuntime"]

from __future__ import annotations

import queue

from gui import streaming_orchestrator
from orchestration import orchestrator
from runtime.core import PipelineRuntime, RuntimeSummary
from utils.context import PipelineContext
from utils.events import EventBus, EventType, PipelineEvent


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


def test_cli_prints_memory_events(capsys) -> None:
    orchestrator._print_cli_event(
        PipelineEvent(
            type=EventType.MEMORY_INSIGHT,
            agent="detection",
            line="[MEMORY] seed 91 passed before for detection",
        )
    )
    orchestrator._print_cli_event(
        PipelineEvent(
            type=EventType.JOURNEY_SUMMARY,
            summary={
                "total_runs": 2,
                "agents": {
                    "detection": {
                        "total_attempts": 3,
                        "success_rate": 0.667,
                        "best_seed": 91,
                        "recent_trials": [
                            {
                                "passed": False,
                                "error_type": "SchemaValidation",
                                "feedback_preview": "Missing mitigation summary",
                            }
                        ],
                        "improvement_directions": ["Prefer seed 91"],
                    }
                },
            },
        )
    )

    out = capsys.readouterr().out
    assert "[MEMORY] seed 91 passed before for detection" in out
    assert "MEMORY SUMMARY" in out
    assert "Total runs remembered: 2" in out
    assert "Prefer seed 91" in out
    assert "last_failure=SchemaValidation: Missing mitigation summary" in out

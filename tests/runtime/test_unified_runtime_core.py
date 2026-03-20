from __future__ import annotations

from pathlib import Path

import runtime.core as runtime_core
from runtime.core import PipelineRuntime, RuntimeConfig
from utils.context import PipelineContext
from utils.events import EventBus, EventType, PipelineEvent
from utils.schemas import JudgeResult


class _MemoryStub:
    def __init__(self) -> None:
        self.persisted: dict[str, object] | None = None
        self.pruned_keep_recent: int | None = None
        self.recommend_requests: list[tuple[str, list[int], int]] = []

    def best_seed_for_agent(self, agent: str, default_seed: int = 42) -> tuple[int, str]:
        return 91, f"seed 91 passed before for {agent}"

    def recommend_seed_for_agent(self, agent: str, attempted_seeds: list[int], default_seed: int = 42) -> tuple[int, str]:
        self.recommend_requests.append((agent, list(attempted_seeds), default_seed))
        if attempted_seeds:
            return 93, f"using untried seed 93 for {agent}"
        return 91, f"using proven seed 91 for {agent}"

    def persist_run_from_context(self, ctx, seed: int, all_passed: bool, total_duration: float, agent_runs, verifications):
        self.persisted = {
            "ctx_seed": ctx.seed,
            "seed": seed,
            "all_passed": all_passed,
            "total_duration": total_duration,
            "agent_runs": agent_runs,
            "verifications": verifications,
        }
        return 1

    def prune_old_runs(self, keep_recent: int = 50) -> int:
        self.pruned_keep_recent = keep_recent
        return 0

    def journey_summary(self) -> dict[str, object]:
        return {
            "total_runs": 3,
            "agents": {
                "detection": {
                    "total_attempts": 3,
                    "success_rate": 0.667,
                    "best_seed": 91,
                    "improvement_directions": ["Prefer seed 91"],
                }
            },
        }


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


def test_runtime_core_uses_memory_seed_and_emits_summary(monkeypatch) -> None:
    events: list[PipelineEvent] = []
    bus = EventBus()
    bus.subscribe(events.append)
    config = RuntimeConfig(project_root=Path("."), core_agents=["detection"], research_agents=[])
    attempts: list[tuple[str, int]] = []
    memory = _MemoryStub()

    monkeypatch.setattr(PipelineRuntime, "_load_memory_store", lambda self: memory)
    monkeypatch.setattr(
        runtime_core.PipelineContext,
        "load",
        classmethod(lambda cls, seed=42: PipelineContext(seed=seed)),
    )

    runtime = PipelineRuntime(
        config=config,
        bus=bus,
        run_agent=lambda agent, seed, _: attempts.append((agent, seed)) or 0,
        run_research_module=lambda module, _: 0,
        run_judge=lambda agent: JudgeResult(True, [f"{agent} passed"]),
        classify_error=lambda exc, stderr: "Unknown",
        run_format_check=lambda: None,
    )

    summary = runtime.run()

    assert attempts == [("detection", 91)]
    assert summary.seed == 91
    assert memory.recommend_requests == [("detection", [], 42)]
    assert memory.persisted is not None
    assert memory.persisted["seed"] == 91
    assert memory.pruned_keep_recent == 50
    assert [event.type for event in events if event.type == EventType.MEMORY_INSIGHT] == [EventType.MEMORY_INSIGHT]
    assert [event.type for event in events if event.type == EventType.JOURNEY_SUMMARY] == [EventType.JOURNEY_SUMMARY]


def test_runtime_core_uses_memory_for_retry_seed_selection(monkeypatch) -> None:
    bus = EventBus()
    config = RuntimeConfig(project_root=Path("."), core_agents=["detection"], research_agents=[])
    attempts: list[tuple[str, int]] = []
    returncodes = iter([1, 0])
    memory = _MemoryStub()

    monkeypatch.setattr(PipelineRuntime, "_load_memory_store", lambda self: memory)
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

    assert attempts == [("detection", 91), ("detection", 93)]
    assert memory.recommend_requests == [
        ("detection", [], 42),
        ("detection", [91], 44),
    ]
    assert summary.results["detection"] == {"passed": True, "attempts": 2}

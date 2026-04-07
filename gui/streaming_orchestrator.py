"""
Streaming orchestrator for the Autonomous Research System GUI.

Runs the research loop in a background thread and pushes events
to a queue that the WebSocket consumer broadcasts to clients.
"""

from __future__ import annotations

import os
import queue
import sys
from pathlib import Path

from runtime.core import ResearchRuntime, RuntimeConfig
from utils.events import EventBus


PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_runtime(bus: EventBus) -> ResearchRuntime:
    config = RuntimeConfig.from_project_root(PROJECT_ROOT)
    return ResearchRuntime(config=config, bus=bus)


def run_research(
    event_queue: queue.Queue[dict[str, object]],
    mode: str = "goal",
    goal: str = "",
    claims_source: str | None = None,
    max_iterations: int | None = None,
    converge_threshold: float | None = None,
) -> None:
    """Run research loop; events are pushed to event_queue for WebSocket broadcast."""
    bus = EventBus()
    bus.connect_queue(event_queue)
    bus.log("research", f"Starting {mode} research...")
    runtime = build_runtime(bus)
    _ = runtime.run(
        mode=mode,
        goal=goal,
        claims_source=claims_source,
        max_iterations=max_iterations,
        converge_threshold=converge_threshold,
    )


# Backward compat alias
def run_pipeline(event_queue: queue.Queue[dict[str, object]]) -> None:
    """Legacy alias — runs goal-oriented research."""
    run_research(event_queue, mode="goal")

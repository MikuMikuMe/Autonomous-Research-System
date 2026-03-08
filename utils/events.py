"""
Typed EventBus for the Bias Audit Pipeline.

Replaces raw event_queue.put({"type": "agent_log", ...}) with typed
PipelineEvent dataclasses and an EventBus with subscriber support.
Bridges to the existing GUI queue via connect_queue() for backward compat.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable


class EventType(Enum):
    AGENT_STARTED = "agent_started"
    AGENT_LOG = "agent_log"
    AGENT_PROGRESS = "agent_progress"
    AGENT_FINISHED = "agent_finished"
    JUDGE_RESULT = "judge_result"
    OUTPUTS_UPDATED = "outputs_updated"
    PIPELINE_FINISHED = "pipeline_finished"


@dataclass
class PipelineEvent:
    type: EventType
    agent: str = ""
    line: str = ""
    progress: float = 0.0
    label: str = ""
    returncode: int = 0
    passed: bool = False
    feedback: list[str] = field(default_factory=list)
    retry_hint: str | None = None
    attempt: int = 0
    all_passed: bool = False
    results: dict | None = None

    def to_queue_dict(self) -> dict:
        """Convert to the plain-dict format the GUI expects."""
        d: dict = {"type": self.type.value, "agent": self.agent}
        if self.type == EventType.AGENT_LOG:
            d["line"] = self.line
        elif self.type == EventType.AGENT_PROGRESS:
            d["progress"] = self.progress
            d["label"] = self.label
        elif self.type == EventType.AGENT_FINISHED:
            d["returncode"] = self.returncode
        elif self.type == EventType.JUDGE_RESULT:
            d["passed"] = self.passed
            d["feedback"] = self.feedback
            d["retry_hint"] = self.retry_hint
            d["attempt"] = self.attempt
        elif self.type == EventType.PIPELINE_FINISHED:
            d["all_passed"] = self.all_passed
            d["results"] = self.results or {}
        return d


class EventBus:
    """Typed event dispatcher with optional queue bridge for the GUI."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[PipelineEvent], None]] = []
        self._queue: queue.Queue | None = None

    def connect_queue(self, q: queue.Queue) -> None:
        """Bridge to existing GUI event_queue (backward compatible)."""
        self._queue = q

    def subscribe(self, callback: Callable[[PipelineEvent], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, event: PipelineEvent) -> None:
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                pass
        if self._queue:
            self._queue.put(event.to_queue_dict())

    # --- Convenience emitters ---

    def log(self, agent: str, line: str) -> None:
        self.emit(PipelineEvent(type=EventType.AGENT_LOG, agent=agent, line=line))

    def progress(self, agent: str, pct: float, label: str = "") -> None:
        self.emit(PipelineEvent(type=EventType.AGENT_PROGRESS, agent=agent, progress=pct, label=label))

    def started(self, agent: str) -> None:
        self.emit(PipelineEvent(type=EventType.AGENT_STARTED, agent=agent))

    def finished(self, agent: str, returncode: int) -> None:
        self.emit(PipelineEvent(type=EventType.AGENT_FINISHED, agent=agent, returncode=returncode))

    def judge_result(self, agent: str, passed: bool, feedback: list[str],
                     retry_hint: str | None = None, attempt: int = 0) -> None:
        self.emit(PipelineEvent(
            type=EventType.JUDGE_RESULT, agent=agent, passed=passed,
            feedback=feedback, retry_hint=retry_hint, attempt=attempt,
        ))

    def outputs_updated(self, agent: str) -> None:
        self.emit(PipelineEvent(type=EventType.OUTPUTS_UPDATED, agent=agent))

    def pipeline_finished(self, all_passed: bool, results: dict) -> None:
        self.emit(PipelineEvent(
            type=EventType.PIPELINE_FINISHED, all_passed=all_passed, results=results,
        ))

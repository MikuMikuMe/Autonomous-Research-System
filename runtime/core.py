"""
ResearchRuntime — Structured execution runtime for the Autonomous Research System.

Wraps the continuous research loop with EventBus integration, memory
management, and configuration loading.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.context import ResearchContext, ResearchMode
from utils.events import EventBus
from utils.schemas import AgentRunRecord, VerificationRecord


def _load_pipeline_config(project_root: Path) -> dict[str, Any]:
    path = project_root / "configs" / "pipeline.yaml"
    if not path.exists():
        return {}
    try:
        import yaml

        with path.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except ImportError:
        return {}
    except Exception:
        return {}


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: Path
    research_agents: list[str]
    max_iterations: int = 10
    converge_threshold: float = 0.90
    flaw_halt_severity: str = "critical"
    evolve_every: int = 2
    compact_every: int = 3

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> "RuntimeConfig":
        root = Path(project_root).resolve()
        cfg = _load_pipeline_config(root)
        loop_cfg = cfg.get("research_loop", {})
        return cls(
            project_root=root,
            research_agents=list(
                cfg.get("research_agents")
                or [
                    "agents.research_agent",
                    "agents.cross_validation_agent",
                    "agents.flaw_detection_agent",
                    "agents.verification_agent",
                    "agents.gap_check_agent",
                    "agents.coverage_agent",
                    "agents.topic_coverage_agent",
                    "agents.optimizer_agent",
                ]
            ),
            max_iterations=loop_cfg.get("max_iterations", 10),
            converge_threshold=loop_cfg.get("converge_threshold", 0.90),
            flaw_halt_severity=loop_cfg.get("flaw_halt_severity", "critical"),
            evolve_every=loop_cfg.get("evolve_every", 2),
            compact_every=loop_cfg.get("compact_every", 3),
        )

    def for_mode(self, mode: str) -> dict[str, Any]:
        """Return mode-specific overrides from config."""
        root_cfg = _load_pipeline_config(self.project_root)
        modes = root_cfg.get("modes", {})
        return dict(modes.get(mode, {}))


@dataclass
class RuntimeSummary:
    results: dict[str, Any]
    converged: bool
    total_duration: float
    iterations_completed: int
    context: ResearchContext
    mode: str = "goal"
    error: str | None = None


class ResearchRuntime:
    """Wraps the continuous research loop with event bus and config."""

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        bus: EventBus,
    ) -> None:
        self.config = config
        self.bus = bus

    def _load_memory_store(self):
        try:
            from agents.memory_agent import MemoryStore
            return MemoryStore()
        except ImportError:
            return None

    def run(
        self,
        mode: str = "goal",
        goal: str = "",
        claims_source: str | None = None,
        max_iterations: int | None = None,
        converge_threshold: float | None = None,
        flaw_halt_severity: str | None = None,
    ) -> RuntimeSummary:
        """Run the research loop and return a structured summary."""
        from orchestration.continuous_research_loop import run_research_loop

        # Apply mode overrides from config
        mode_overrides = self.config.for_mode(mode)
        iters = max_iterations or mode_overrides.get("max_iterations") or self.config.max_iterations
        threshold = converge_threshold or mode_overrides.get("converge_threshold") or self.config.converge_threshold
        halt = flaw_halt_severity or self.config.flaw_halt_severity

        self.bus.log("research", f"Starting {mode} research: {goal or 'general research'}")
        self.bus.started("research")

        start = time.time()
        ctx = ResearchContext(
            mode=ResearchMode(mode),
            goal=goal,
        )

        try:
            report = run_research_loop(
                claims_source=claims_source,
                goal=goal or "Verify and refine research claims through iterative evidence gathering",
                max_iterations=iters,
                converge_threshold=threshold,
                flaw_halt_severity=halt,
                mode=mode,
            )
        except Exception as exc:
            duration = time.time() - start
            self.bus.log("research", f"[ERROR] Research loop failed: {exc}")
            self.bus.pipeline_finished(False, {"error": str(exc)})
            return RuntimeSummary(
                results={"error": str(exc)},
                converged=False,
                total_duration=duration,
                iterations_completed=0,
                context=ctx,
                mode=mode,
                error=str(exc),
            )

        duration = time.time() - start
        converged = report.get("converged", False)
        iterations = report.get("iterations_completed", 0)

        self.bus.log(
            "research",
            f"Research {'converged' if converged else 'completed'} after {iterations} iterations ({duration:.1f}s)"
        )
        self.bus.pipeline_finished(converged, report)

        # Update context from report
        ctx.converged = converged
        ctx.current_iteration = iterations
        ctx.save()

        return RuntimeSummary(
            results=report,
            converged=converged,
            total_duration=duration,
            iterations_completed=iterations,
            context=ctx,
            mode=mode,
        )


# ---- Backward compatibility aliases ----
PipelineRuntime = ResearchRuntime

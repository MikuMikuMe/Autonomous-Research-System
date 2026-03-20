from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from utils.context import PipelineContext
from utils.events import EventBus
from utils.schemas import AgentRunRecord, JudgeResult, VerificationRecord


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
    core_agents: list[str]
    research_agents: list[str]
    max_retries: int = 3
    initial_seed: int = 42

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> "RuntimeConfig":
        root = Path(project_root).resolve()
        pipeline = _load_pipeline_config(root).get("pipeline", {})
        return cls(
            project_root=root,
            core_agents=list(pipeline.get("core_agents") or ["detection", "mitigation", "auditing"]),
            research_agents=list(
                pipeline.get("research_agents")
                or [
                    "agents.research_agent",
                    "agents.gap_check_agent",
                    "agents.coverage_agent",
                    "agents.topic_coverage_agent",
                    "agents.reproducibility_agent",
                    "agents.verification_agent",
                    "agents.optimizer_agent",
                ]
            ),
        )


@dataclass
class RuntimeSummary:
    results: dict[str, dict[str, object]]
    all_passed: bool
    seed: int
    total_duration: float
    context: PipelineContext
    agent_run_records: list[AgentRunRecord] = field(default_factory=list)


class PipelineRuntime:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        bus: EventBus,
        run_agent: Callable[[str, int, EventBus], int],
        run_research_module: Callable[[str, EventBus], int],
        run_judge: Callable[[str], JudgeResult],
        classify_error: Callable[[Exception | None, str], str],
        run_revision: Callable[[str], subprocess.CompletedProcess[str]] | None = None,
        run_format_check: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.run_agent = run_agent
        self.run_research_module = run_research_module
        self.run_judge = run_judge
        self.classify_error = classify_error
        self.run_revision = run_revision or self._default_run_revision
        self.run_format_check = run_format_check or self._default_run_format_check

    def _default_run_revision(self, actionable_feedback: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["JUDGE_FEEDBACK"] = actionable_feedback
        return subprocess.run(
            [sys.executable, "-m", "agents.revision_agent"],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(self.config.project_root),
        )

    def _default_run_format_check(self) -> None:
        try:
            from agents.format_check_agent import apply_format_fixes, run_format_check

            format_result = run_format_check(paper_only=True)
            if not format_result["passed"]:
                self.bus.log("auditing", "  [FORMAT] Issues found; applying fixes...")
                apply_format_fixes()
        except ImportError:
            return

    def _load_memory_store(self):
        try:
            from agents.memory_agent import MemoryStore

            return MemoryStore()
        except ImportError:
            return None

    def _persist_failed_event(self, agent_name: str, actionable_feedback: str) -> None:
        try:
            from agents.memory_agent import persist_event

            persist_event(agent_name, "failed", actionable_feedback)
        except ImportError:
            return

    def _verify_claims(self, ctx: PipelineContext) -> list[VerificationRecord]:
        verification_records: list[VerificationRecord] = []
        try:
            from agents.verification_agent import verify_paper_claims

            verification_report = verify_paper_claims()
        except ImportError:
            return verification_records

        claims = verification_report.get("claims") or []
        if not isinstance(claims, list):
            return verification_records

        for claim in claims:
            if not isinstance(claim, dict):
                continue
            verification_records.append(
                VerificationRecord(
                    claim=str(claim.get("claim", "")),
                    verified=claim.get("verified"),
                    evidence=str(claim.get("evidence", "")),
                    error=claim.get("error"),
                )
            )
        ctx.verifications.extend(verification_records)
        return verification_records

    def _metrics_snapshot(self, agent_name: str, ctx: PipelineContext) -> dict[str, Any] | None:
        if agent_name == "detection" and ctx.baseline:
            return ctx.baseline.to_dict()
        if agent_name == "mitigation" and ctx.mitigation:
            return ctx.mitigation.to_dict()
        return None

    def _pick_seed(self, agent_name: str, attempt: int, memory, prior_attempts: list[AgentRunRecord]) -> tuple[int, str]:
        attempted_seeds = [record.seed for record in prior_attempts if record.agent == agent_name]
        if memory:
            try:
                default_seed = self.config.initial_seed if attempt == 1 else self.config.initial_seed + attempt
                if hasattr(memory, "recommend_seed_for_agent"):
                    return memory.recommend_seed_for_agent(agent_name, attempted_seeds, default_seed)
                if attempt == 1:
                    return memory.best_seed_for_agent(agent_name, self.config.initial_seed)
            except Exception:
                pass
        if attempt > 1:
            seed = self.config.initial_seed + attempt
            return seed, f"retry with incremented seed {seed}"
        return self.config.initial_seed, "default seed (no memory available)"

    def run(self) -> RuntimeSummary:
        ctx = PipelineContext(seed=self.config.initial_seed)
        memory = self._load_memory_store()
        pipeline_start = time.time()
        results: dict[str, dict[str, object]] = {}
        agent_run_records: list[AgentRunRecord] = []
        seed = self.config.initial_seed

        for agent_name in self.config.core_agents:
            self.bus.started(agent_name)

            for attempt in range(1, self.config.max_retries + 1):
                seed, seed_reason = self._pick_seed(agent_name, attempt, memory, agent_run_records)
                self.bus.memory_insight(agent_name, f"[MEMORY] {seed_reason}")
                if attempt > 1:
                    self.bus.log(agent_name, f"\n  [RETRY {attempt}/{self.config.max_retries}] seed={seed}")

                agent_start = time.time()
                returncode = self.run_agent(agent_name, seed, self.bus)
                agent_duration = time.time() - agent_start
                self.bus.finished(agent_name, returncode)

                if returncode != 0:
                    self.bus.log(agent_name, f"\n  [FAILED] Agent exited with error (returncode {returncode}). Retrying...")
                    self.bus.judge_result(agent_name, False, ["Agent exited with error. Retrying..."], attempt=attempt)
                    agent_run_records.append(
                        AgentRunRecord(
                            agent=agent_name,
                            seed=seed,
                            attempt=attempt,
                            passed=False,
                            duration_seconds=agent_duration,
                            error=f"Exit code {returncode}",
                            error_type="SubprocessError",
                        )
                    )
                    continue

                if agent_name == "auditing":
                    self.run_format_check()

                ctx = PipelineContext.load(seed=seed)
                judge_result = self.run_judge(agent_name)
                metrics_snap = self._metrics_snapshot(agent_name, ctx)

                self.bus.judge_result(
                    agent_name,
                    judge_result.passed,
                    judge_result.feedback,
                    judge_result.retry_hint,
                    attempt,
                )

                if judge_result.passed:
                    results[agent_name] = {"passed": True, "attempts": attempt}
                    self.bus.outputs_updated(agent_name)
                    agent_run_records.append(
                        AgentRunRecord(
                            agent=agent_name,
                            seed=seed,
                            attempt=attempt,
                            passed=True,
                            duration_seconds=agent_duration,
                            metrics_snapshot=metrics_snap,
                            judge_feedback=judge_result.feedback,
                        )
                    )
                    break

                if judge_result.retry_hint == "revise_claims" and judge_result.actionable_feedback:
                    self._persist_failed_event(agent_name, judge_result.actionable_feedback)
                    verification_records = self._verify_claims(ctx)
                    failed_claims = [record for record in verification_records if record.verified is False]
                    if failed_claims:
                        evidence = "; ".join((record.evidence or record.error or "")[:100] for record in failed_claims)
                        judge_result = JudgeResult(
                            passed=judge_result.passed,
                            feedback=judge_result.feedback,
                            retry_hint=judge_result.retry_hint,
                            actionable_feedback=(
                                f"{judge_result.actionable_feedback}\n\n"
                                f"[Verification Agent] Code-based check: {evidence}"
                            ),
                        )

                    self.bus.log(agent_name, "\n  [REVISION] Invoking Revision Agent to fix claim contradictions...")
                    revision_result = self.run_revision(judge_result.actionable_feedback or "")
                    if revision_result.returncode == 0:
                        self.bus.log(agent_name, "  [REVISION] Applied. Re-running Judge...")
                        revised_judge_result = self.run_judge(agent_name)
                        self.bus.judge_result(
                            agent_name,
                            revised_judge_result.passed,
                            revised_judge_result.feedback,
                            revised_judge_result.retry_hint,
                            attempt,
                        )
                        if revised_judge_result.passed:
                            results[agent_name] = {"passed": True, "attempts": attempt}
                            self.bus.outputs_updated(agent_name)
                            agent_run_records.append(
                                AgentRunRecord(
                                    agent=agent_name,
                                    seed=seed,
                                    attempt=attempt,
                                    passed=True,
                                    duration_seconds=time.time() - agent_start,
                                    metrics_snapshot=metrics_snap,
                                    judge_feedback=revised_judge_result.feedback,
                                )
                            )
                            break
                    else:
                        self.bus.log(
                            agent_name,
                            f"  [REVISION] FAILED: {revision_result.stderr or revision_result.stdout or 'unknown'}",
                        )

                agent_run_records.append(
                    AgentRunRecord(
                        agent=agent_name,
                        seed=seed,
                        attempt=attempt,
                        passed=False,
                        duration_seconds=agent_duration,
                        error="; ".join(judge_result.feedback[:3]),
                        error_type=self.classify_error(None, "; ".join(judge_result.feedback)),
                        metrics_snapshot=metrics_snap,
                        judge_feedback=judge_result.feedback,
                        retry_hint=judge_result.retry_hint,
                    )
                )

                if attempt == self.config.max_retries:
                    results[agent_name] = {
                        "passed": False,
                        "attempts": attempt,
                        "feedback": judge_result.feedback,
                    }
                    self.bus.log(
                        agent_name,
                        f"\n  [FAILED] {agent_name} failed after {self.config.max_retries} attempts. Stopping pipeline.",
                    )
                    break

            if not results.get(agent_name, {}).get("passed"):
                break

        all_passed = all(result["passed"] for result in results.values())
        total_duration = time.time() - pipeline_start

        if memory:
            try:
                _ = memory.persist_run_from_context(
                    ctx,
                    seed=seed,
                    all_passed=all_passed,
                    total_duration=total_duration,
                    agent_runs=agent_run_records,
                    verifications=ctx.verifications,
                )
                memory.prune_old_runs(keep_recent=50)
            except Exception:
                traceback.print_exc()

            try:
                journey = memory.journey_summary()
                self.bus.journey_summary(journey)
            except Exception:
                traceback.print_exc()

        if all_passed:
            self.bus.log(
                "research",
                f"\n{'─' * 50}\n  RESEARCH PHASE — alphaXiv, Gap Check, Coverage, Reproducibility\n{'─' * 50}",
            )
            for module in self.config.research_agents:
                self.bus.log("research", f"\n  >> {module}")
                _ = self.run_research_module(module, self.bus)

        self.bus.pipeline_finished(all_passed, results)
        return RuntimeSummary(
            results=results,
            all_passed=all_passed,
            seed=seed,
            total_duration=total_duration,
            context=ctx,
            agent_run_records=agent_run_records,
        )

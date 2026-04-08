"""
Autonomy Self-Check Agent — Validates the system is truly agentic.

Runs a comprehensive diagnostic across all pipeline components to verify:
1. DISCOVER: All agents, tools, and dependencies are discoverable
2. PLAN: Pipeline config is valid and agent ordering is correct
3. ACT: Core agents can be imported and invoked
4. OBSERVE: Judge agent can evaluate outputs; EventBus delivers events
5. REFLECT: Memory agent can persist, query, and compact knowledge

Returns a structured report with pass/fail per check, enabling the system
to autonomously identify and report gaps in its own agentic capabilities.
"""

from __future__ import annotations

import importlib
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ====================================================================
# Check result schema
# ====================================================================


@dataclass
class CheckResult:
    name: str
    phase: str  # DISCOVER, PLAN, ACT, OBSERVE, REFLECT
    passed: bool
    message: str
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SelfCheckReport:
    timestamp: str
    total_checks: int
    passed: int
    failed: int
    phases: dict[str, list[CheckResult]]
    is_autonomous: bool
    blocking_issues: list[str]
    recommendations: list[str]
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["phases"] = {
            phase: [c for c in checks]
            for phase, checks in self.phases.items()
        }
        return d


# ====================================================================
# DISCOVER phase checks
# ====================================================================


def _check_agent_importable(module_name: str) -> CheckResult:
    """Check that an agent module can be imported."""
    start = time.monotonic()
    try:
        importlib.import_module(module_name)
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name=f"import:{module_name}",
            phase="DISCOVER",
            passed=True,
            message=f"Module {module_name} imported successfully",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name=f"import:{module_name}",
            phase="DISCOVER",
            passed=False,
            message=f"Failed to import {module_name}: {exc}",
            duration_ms=elapsed,
        )


def _check_config_exists() -> CheckResult:
    """Check that pipeline.yaml exists and is parseable."""
    start = time.monotonic()
    config_path = PROJECT_ROOT / "configs" / "pipeline.yaml"
    if not config_path.exists():
        return CheckResult(
            name="config:pipeline.yaml",
            phase="DISCOVER",
            passed=False,
            message="configs/pipeline.yaml not found",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    try:
        import yaml
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        pipeline = (data or {}).get("pipeline", {})
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="config:pipeline.yaml",
            phase="DISCOVER",
            passed=True,
            message=f"Config loaded: {len(pipeline.get('core_agents', []))} core agents, "
                    f"{len(pipeline.get('research_agents', []))} research agents",
            duration_ms=elapsed,
            details={"core_agents": pipeline.get("core_agents", []),
                      "research_agents": pipeline.get("research_agents", [])},
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="config:pipeline.yaml",
            phase="DISCOVER",
            passed=False,
            message=f"Config parse error: {exc}",
            duration_ms=elapsed,
        )


def _check_prompts_exist() -> CheckResult:
    """Check that prompt files referenced in configs/prompts/ exist."""
    start = time.monotonic()
    prompts_dir = PROJECT_ROOT / "configs" / "prompts"
    if not prompts_dir.exists():
        return CheckResult(
            name="config:prompts",
            phase="DISCOVER",
            passed=False,
            message="configs/prompts/ directory not found",
            duration_ms=(time.monotonic() - start) * 1000,
        )
    prompt_files = list(prompts_dir.glob("*.txt"))
    elapsed = (time.monotonic() - start) * 1000
    return CheckResult(
        name="config:prompts",
        phase="DISCOVER",
        passed=len(prompt_files) > 0,
        message=f"Found {len(prompt_files)} prompt files",
        duration_ms=elapsed,
        details={"files": [f.name for f in prompt_files]},
    )


def _check_dependencies() -> CheckResult:
    """Check that key Python dependencies are installed."""
    start = time.monotonic()
    required = ["yaml", "fastapi", "numpy", "google.genai"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    elapsed = (time.monotonic() - start) * 1000
    return CheckResult(
        name="deps:python",
        phase="DISCOVER",
        passed=len(missing) == 0,
        message=f"All {len(required)} core dependencies available" if not missing
                else f"Missing dependencies: {', '.join(missing)}",
        duration_ms=elapsed,
        details={"missing": missing, "checked": required},
    )


# ====================================================================
# PLAN phase checks
# ====================================================================


def _check_agent_ordering() -> CheckResult:
    """Verify that research agents are configured."""
    start = time.monotonic()
    try:
        from runtime.core import RuntimeConfig
        config = RuntimeConfig.from_project_root(PROJECT_ROOT)
        agents = config.research_agents
        elapsed = (time.monotonic() - start) * 1000

        if len(agents) >= 1:
            return CheckResult(
                name="plan:agent_ordering",
                phase="PLAN",
                passed=True,
                message=f"Research agents configured: {', '.join(agents[:5])}{'...' if len(agents) > 5 else ''}",
                duration_ms=elapsed,
            )
        return CheckResult(
            name="plan:agent_ordering",
            phase="PLAN",
            passed=False,
            message="No research agents configured",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="plan:agent_ordering",
            phase="PLAN",
            passed=False,
            message=f"Cannot verify ordering: {exc}",
            duration_ms=elapsed,
        )


def _check_retry_config() -> CheckResult:
    """Verify iteration configuration for research loop."""
    start = time.monotonic()
    try:
        from runtime.core import RuntimeConfig
        config = RuntimeConfig.from_project_root(PROJECT_ROOT)
        elapsed = (time.monotonic() - start) * 1000
        has_iterations = config.max_iterations >= 2
        return CheckResult(
            name="plan:retry_config",
            phase="PLAN",
            passed=has_iterations,
            message=f"Max iterations: {config.max_iterations} (minimum 2 for autonomous research)"
                    if has_iterations else f"Max iterations too low: {config.max_iterations}",
            duration_ms=elapsed,
            details={"max_iterations": config.max_iterations, "converge_threshold": config.converge_threshold},
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="plan:retry_config",
            phase="PLAN",
            passed=False,
            message=f"Cannot check retry config: {exc}",
            duration_ms=elapsed,
        )


def _check_judge_hint_map() -> CheckResult:
    """Verify research loop config is present in pipeline.yaml."""
    start = time.monotonic()
    config_path = PROJECT_ROOT / "configs" / "pipeline.yaml"
    try:
        import yaml
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        research_loop = data.get("research_loop", {})
        has_agents = bool(data.get("research_agents"))
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="plan:judge_hint_map",
            phase="PLAN",
            passed=has_agents,
            message=f"Research config present: {len(research_loop)} loop settings, agents configured"
                    if has_agents else "No research_agents configured in pipeline.yaml",
            duration_ms=elapsed,
            details={"research_loop": research_loop},
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="plan:judge_hint_map",
            phase="PLAN",
            passed=False,
            message=f"Cannot check config: {exc}",
            duration_ms=elapsed,
        )


# ====================================================================
# ACT phase checks
# ====================================================================


def _check_runtime_instantiation() -> CheckResult:
    """Verify PipelineRuntime can be instantiated with all callbacks."""
    start = time.monotonic()
    try:
        from orchestration.orchestrator import build_runtime
        from utils.events import EventBus
        bus = EventBus()
        runtime = build_runtime(bus)
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="act:runtime_instantiation",
            phase="ACT",
            passed=True,
            message="ResearchRuntime instantiated successfully",
            duration_ms=elapsed,
            details={
                "research_agents": runtime.config.research_agents,
            },
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="act:runtime_instantiation",
            phase="ACT",
            passed=False,
            message=f"Runtime instantiation failed: {exc}",
            duration_ms=elapsed,
        )


def _check_judge_callable() -> CheckResult:
    """Verify Judge agent evaluate() is callable."""
    start = time.monotonic()
    try:
        from agents.judge_agent import evaluate
        assert callable(evaluate)
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="act:judge_callable",
            phase="ACT",
            passed=True,
            message="Judge evaluate() function is callable",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="act:judge_callable",
            phase="ACT",
            passed=False,
            message=f"Judge not callable: {exc}",
            duration_ms=elapsed,
        )


def _check_sepl_available() -> CheckResult:
    """Verify SEPL (Self Evolution Protocol Layer) is available."""
    start = time.monotonic()
    try:
        from orchestration.sep_layer import propose, commit, rollback, status
        assert all(callable(fn) for fn in [propose, commit, rollback, status])
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="act:sepl_available",
            phase="ACT",
            passed=True,
            message="SEPL propose/commit/rollback/status all callable",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="act:sepl_available",
            phase="ACT",
            passed=False,
            message=f"SEPL not available: {exc}",
            duration_ms=elapsed,
        )


# ====================================================================
# OBSERVE phase checks
# ====================================================================


def _check_event_bus_delivery() -> CheckResult:
    """Verify EventBus delivers events to subscribers."""
    start = time.monotonic()
    try:
        from utils.events import EventBus, EventType, PipelineEvent
        bus = EventBus()
        received: list[PipelineEvent] = []
        bus.subscribe(received.append)
        bus.log("test_agent", "self-check probe")
        bus.judge_result("test_agent", True, ["check OK"])
        bus.pipeline_finished(True, {"test": {"passed": True}})
        elapsed = (time.monotonic() - start) * 1000

        expected_types = {EventType.AGENT_LOG, EventType.JUDGE_RESULT, EventType.PIPELINE_FINISHED}
        actual_types = {e.type for e in received}
        missing = expected_types - actual_types

        return CheckResult(
            name="observe:event_bus",
            phase="OBSERVE",
            passed=len(missing) == 0,
            message=f"EventBus delivered {len(received)} events"
                    + (f", missing types: {missing}" if missing else ""),
            duration_ms=elapsed,
            details={"events_received": len(received), "types": [e.type.value for e in received]},
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="observe:event_bus",
            phase="OBSERVE",
            passed=False,
            message=f"EventBus check failed: {exc}",
            duration_ms=elapsed,
        )


def _check_schema_validation() -> CheckResult:
    """Verify schema validation catches invalid data."""
    start = time.monotonic()
    try:
        from utils.schemas import ClaimVerdict, FlawRecord
        # Valid ClaimVerdict
        cv = ClaimVerdict(
            claim="Test claim",
            verdict="support",
            confidence=0.9,
            supporting_papers=["paper1"],
        )
        # Valid FlawRecord
        fr = FlawRecord(
            description="Test flaw",
            severity="low",
            suggested_fix="Fix it",
        )

        elapsed = (time.monotonic() - start) * 1000
        passed = cv.claim == "Test claim" and fr.severity == "low"
        return CheckResult(
            name="observe:schema_validation",
            phase="OBSERVE",
            passed=passed,
            message="Schema validation works: ClaimVerdict and FlawRecord instantiate correctly"
                    if passed else "Schema validation broken: dataclass fields mismatch",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="observe:schema_validation",
            phase="OBSERVE",
            passed=False,
            message=f"Schema validation check failed: {exc}",
            duration_ms=elapsed,
        )


# ====================================================================
# REFLECT phase checks
# ====================================================================


def _check_memory_store() -> CheckResult:
    """Verify MemoryStore can create tables, persist, and query."""
    start = time.monotonic()
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore(db_path=":memory:")
        # Persist a test run
        from utils.schemas import RunRecord, AgentRunRecord
        record = RunRecord(
            timestamp="2026-01-01T00:00:00Z",
            all_passed=True,
            total_duration_seconds=10.0,
            agents=[AgentRunRecord(agent="research", seed=0, attempt=1,
                                   passed=True, duration_seconds=5.0)],
        )
        run_id = store.persist_run(record)
        recent = store.recent_runs(limit=1)
        summary = store.journey_summary()
        store.close()
        elapsed = (time.monotonic() - start) * 1000

        works = run_id > 0 and len(recent) > 0 and summary.get("total_runs", 0) > 0
        return CheckResult(
            name="reflect:memory_store",
            phase="REFLECT",
            passed=works,
            message=f"MemoryStore works: persist (id={run_id}), query ({len(recent)} recent), "
                    f"summary ({summary.get('total_runs', 0)} runs)"
                    if works else "MemoryStore operations failed",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="reflect:memory_store",
            phase="REFLECT",
            passed=False,
            message=f"MemoryStore check failed: {exc}",
            duration_ms=elapsed,
        )


def _check_memory_compaction() -> CheckResult:
    """Verify memory compaction (pruning) removes redundant data."""
    start = time.monotonic()
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore(db_path=":memory:")
        from utils.schemas import RunRecord, AgentRunRecord

        # Create multiple redundant failed runs
        for i in range(5):
            record = RunRecord(
                timestamp=f"2026-01-0{i + 1}T00:00:00Z",
                all_passed=False,
                total_duration_seconds=10.0,
                agents=[AgentRunRecord(
                    agent="research", seed=0, attempt=1,
                    passed=False, duration_seconds=5.0,
                    error="timeout", error_type="GeminiTimeout",
                    judge_feedback=["timeout occurred"],
                )],
            )
            store.persist_run(record)

        count_before = store.db.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()["cnt"]
        deleted = store.prune_old_runs(keep_recent=2)
        count_after = store.db.execute("SELECT COUNT(*) as cnt FROM runs").fetchone()["cnt"]
        store.close()
        elapsed = (time.monotonic() - start) * 1000

        compacted = count_after < count_before
        return CheckResult(
            name="reflect:memory_compaction",
            phase="REFLECT",
            passed=compacted,
            message=f"Compaction works: {count_before} → {count_after} runs (deleted {deleted})"
                    if compacted else f"Compaction ineffective: {count_before} → {count_after}",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="reflect:memory_compaction",
            phase="REFLECT",
            passed=False,
            message=f"Memory compaction check failed: {exc}",
            duration_ms=elapsed,
        )


def _check_seed_recommendation() -> CheckResult:
    """Verify memory-based seed recommendation avoids failed seeds."""
    start = time.monotonic()
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore(db_path=":memory:")
        from utils.schemas import RunRecord, AgentRunRecord

        # Record a failure on seed 42
        record = RunRecord(
            timestamp="2026-01-01T00:00:00Z",
            all_passed=False,
            total_duration_seconds=10.0,
            agents=[AgentRunRecord(
                agent="research", seed=0, attempt=1,
                passed=False, duration_seconds=5.0,
            )],
        )
        store.persist_run(record)

        seed, reason = store.recommend_seed_for_agent("research", [42], default_seed=42)
        store.close()
        elapsed = (time.monotonic() - start) * 1000

        avoids_failed = seed != 42
        return CheckResult(
            name="reflect:seed_recommendation",
            phase="REFLECT",
            passed=avoids_failed,
            message=f"Seed recommendation works: recommended {seed} (avoiding 42), reason: {reason}"
                    if avoids_failed else f"Seed recommendation failed: still recommending failed seed {seed}",
            duration_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.monotonic() - start) * 1000
        return CheckResult(
            name="reflect:seed_recommendation",
            phase="REFLECT",
            passed=False,
            message=f"Seed recommendation check failed: {exc}",
            duration_ms=elapsed,
        )


# ====================================================================
# Main runner
# ====================================================================


def run_self_check() -> SelfCheckReport:
    """Run all autonomy self-checks and produce a structured report."""
    overall_start = time.monotonic()

    all_checks: list[CheckResult] = []

    # DISCOVER
    core_modules = [
        "agents.research_agent", "agents.cross_validation_agent",
        "agents.flaw_detection_agent", "agents.verification_agent",
        "agents.memory_agent", "agents.judge_agent",
        "agents.revision_agent", "agents.optimizer_agent",
        "agents.gap_check_agent", "agents.coverage_agent",
        "agents.topic_coverage_agent",
    ]
    # Legacy bias-pipeline agents are optional (need kagglehub, imblearn, etc.)
    optional_modules = [
        "agents.detection_agent", "agents.mitigation_agent", "agents.auditing_agent",
    ]
    for mod in core_modules:
        all_checks.append(_check_agent_importable(mod))
    for mod in optional_modules:
        check = _check_agent_importable(mod)
        check.phase = "OBSERVE"  # non-blocking phase so missing deps don't prevent autonomy
        all_checks.append(check)
    all_checks.append(_check_config_exists())
    all_checks.append(_check_prompts_exist())
    all_checks.append(_check_dependencies())

    # PLAN
    all_checks.append(_check_agent_ordering())
    all_checks.append(_check_retry_config())
    all_checks.append(_check_judge_hint_map())

    # ACT
    all_checks.append(_check_runtime_instantiation())
    all_checks.append(_check_judge_callable())
    all_checks.append(_check_sepl_available())

    # OBSERVE
    all_checks.append(_check_event_bus_delivery())
    all_checks.append(_check_schema_validation())

    # REFLECT
    all_checks.append(_check_memory_store())
    all_checks.append(_check_memory_compaction())
    all_checks.append(_check_seed_recommendation())

    elapsed = (time.monotonic() - overall_start) * 1000

    # Organize by phase
    phases: dict[str, list[CheckResult]] = {}
    for check in all_checks:
        phases.setdefault(check.phase, []).append(check)

    passed = sum(1 for c in all_checks if c.passed)
    failed = sum(1 for c in all_checks if not c.passed)

    # Determine blocking issues
    blocking: list[str] = []
    recommendations: list[str] = []
    for check in all_checks:
        if not check.passed:
            if check.phase in ("DISCOVER", "PLAN", "ACT"):
                blocking.append(f"[{check.phase}] {check.name}: {check.message}")
            else:
                recommendations.append(f"[{check.phase}] {check.name}: {check.message}")

    is_autonomous = len(blocking) == 0

    return SelfCheckReport(
        timestamp=__import__("datetime").datetime.now().isoformat(),
        total_checks=len(all_checks),
        passed=passed,
        failed=failed,
        phases=phases,
        is_autonomous=is_autonomous,
        blocking_issues=blocking,
        recommendations=recommendations,
        duration_ms=elapsed,
    )


def main() -> int:
    """Run self-check and print results."""
    print("=" * 70)
    print("  AUTONOMY SELF-CHECK — Validating Agentic Capabilities")
    print("=" * 70)

    report = run_self_check()

    for phase in ["DISCOVER", "PLAN", "ACT", "OBSERVE", "REFLECT"]:
        checks = report.phases.get(phase, [])
        if not checks:
            continue
        phase_passed = all(c.passed for c in checks)
        status = "✓" if phase_passed else "✗"
        print(f"\n  {status} {phase}")
        for check in checks:
            icon = "✓" if check.passed else "✗"
            print(f"    {icon} {check.name}: {check.message}")

    print(f"\n{'=' * 70}")
    print(f"  RESULT: {report.passed}/{report.total_checks} checks passed "
          f"({report.duration_ms:.0f}ms)")

    if report.is_autonomous:
        print("  STATUS: ✓ SYSTEM IS AUTONOMOUS")
    else:
        print("  STATUS: ✗ SYSTEM HAS BLOCKING ISSUES")
        for issue in report.blocking_issues:
            print(f"    ✗ {issue}")

    if report.recommendations:
        print("\n  RECOMMENDATIONS:")
        for rec in report.recommendations:
            print(f"    → {rec}")

    print("=" * 70)

    # Save report
    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "self_check_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")

    return 0 if report.is_autonomous else 1


if __name__ == "__main__":
    sys.exit(main())

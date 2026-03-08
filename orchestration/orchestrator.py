"""
Unified Agentic System — Orchestrator
Runs Detection → Mitigation → Auditing → Research (alphaXiv, gap check, coverage, reproducibility).
Judge Agent evaluates each core output; failed agents are retried with feedback.
Uses PipelineContext for shared state, EventBus for typed events,
and MemoryStore for rich self-evolution memory.
"""

import os
import sys
import subprocess
import time
import traceback
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

MAX_RETRIES = 3

from utils.context import PipelineContext
from utils.events import EventBus, EventType
from utils.schemas import AgentRunRecord, VerificationRecord


def _load_pipeline_config():
    path = os.path.join(PROJECT_ROOT, "configs", "pipeline.yaml")
    if not os.path.exists(path):
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}
    except Exception:
        return {}

_pipeline = _load_pipeline_config().get("pipeline", {})
AGENTS = _pipeline.get("core_agents") or ["detection", "mitigation", "auditing"]
RESEARCH_AGENTS = _pipeline.get("research_agents") or [
    "agents.research_agent",
    "agents.gap_check_agent",
    "agents.coverage_agent",
    "agents.topic_coverage_agent",
    "agents.reproducibility_agent",
    "agents.verification_agent",
    "agents.optimizer_agent",
]


def _classify_error(exc: Exception | None, stderr: str = "") -> str:
    """Classify an error into a category for memory storage."""
    msg = str(exc) if exc else stderr
    if "LaTeX" in msg or "pdflatex" in msg:
        return "LaTeXCompileError"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "GeminiTimeout"
    if "schema" in msg.lower() or "missing key" in msg.lower():
        return "SchemaValidation"
    if "FileNotFoundError" in msg or "not found" in msg.lower():
        return "FileNotFound"
    if "JSONDecodeError" in msg:
        return "JSONParse"
    return "Unknown"


def run_agent(agent_name: str, seed: int = 42) -> bool:
    """Run an agent as subprocess. Returns True if exit code 0."""
    module_map = {
        "detection": "agents.detection_agent",
        "mitigation": "agents.mitigation_agent",
        "auditing": "agents.auditing_agent",
    }
    module = module_map[agent_name]
    cmd = [sys.executable, "-m", module, str(seed)]
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def run_judge(agent_name: str):
    """Run judge evaluation for an agent. Returns JudgeResult dataclass."""
    from agents.judge_agent import evaluate
    return evaluate(agent_name)


def parse_retry_hint(hint: str) -> int:
    """Extract seed from retry hint for detection/mitigation. Returns incrementing seed."""
    if hint and "different_seed" in str(hint):
        return None
    return 42


def run_research_phase(bus: EventBus):
    """Run research pipeline: alphaXiv, gap check, coverage, reproducibility."""
    print("\n" + "─" * 70)
    print("  RESEARCH PHASE — alphaXiv, Gap Check, Coverage, Reproducibility")
    print("─" * 70)
    bus.log("research", "RESEARCH PHASE — alphaXiv, Gap Check, Coverage, Reproducibility")
    for module in RESEARCH_AGENTS:
        print(f"\n  >> {module}")
        bus.log("research", f"Running {module}...")
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=PROJECT_ROOT,
            capture_output=False,
        )
        if result.returncode != 0:
            print(f"  [WARN] {module} exited with {result.returncode} (non-fatal)")


def main():
    print("=" * 70)
    print("  UNIFIED AGENTIC SYSTEM — Orchestrator")
    print("  Pipeline: Detection → Mitigation → Auditing → Research")
    print("  Judge evaluates core agents; Research runs after paper is ready")
    print("=" * 70)

    ctx = PipelineContext(seed=42)
    bus = EventBus()
    bus.subscribe(lambda e: None)  # CLI: no GUI queue

    # Initialize memory store
    try:
        from agents.memory_agent import MemoryStore
        memory = MemoryStore()
    except ImportError:
        memory = None

    pipeline_start = time.time()
    results = {}
    agent_run_records: list[AgentRunRecord] = []
    seed = 42

    for agent_name in AGENTS:
        print(f"\n{'─' * 70}")
        print(f"  AGENT: {agent_name.upper()}")
        print("─" * 70)
        bus.started(agent_name)

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                seed = 42 + attempt
                print(f"\n  [RETRY {attempt}/{MAX_RETRIES}] seed={seed}")

            agent_start = time.time()
            error_msg = None
            error_type = None

            success = run_agent(agent_name, seed=seed)
            agent_duration = time.time() - agent_start

            if not success:
                error_msg = f"Agent exited with error (non-zero exit code)"
                error_type = "SubprocessError"
                print(f"\n  [JUDGE] Agent exited with error. Retrying...")
                agent_run_records.append(AgentRunRecord(
                    agent=agent_name, seed=seed, attempt=attempt,
                    passed=False, duration_seconds=agent_duration,
                    error=error_msg, error_type=error_type,
                ))
                continue

            # Format check (auditing only)
            if agent_name == "auditing":
                try:
                    from agents.format_check_agent import run_format_check, apply_format_fixes
                    fc = run_format_check(paper_only=True)
                    if not fc["passed"]:
                        print("  [FORMAT] Issues found; applying fixes...")
                        apply_format_fixes()
                except ImportError:
                    pass

            # Load context from files after agent completes
            ctx = PipelineContext.load(seed=seed)

            # Judge evaluates — returns JudgeResult dataclass
            judge_result = run_judge(agent_name)

            for msg in judge_result.feedback:
                prefix = "  ✓" if judge_result.passed else "  ✗"
                print(f"{prefix} {msg}")

            bus.judge_result(
                agent_name, judge_result.passed, judge_result.feedback,
                judge_result.retry_hint, attempt,
            )

            # Capture metrics snapshot for memory
            metrics_snap = None
            if agent_name == "detection" and ctx.baseline:
                metrics_snap = ctx.baseline.to_dict()
            elif agent_name == "mitigation" and ctx.mitigation:
                metrics_snap = ctx.mitigation.to_dict()

            if judge_result.passed:
                results[agent_name] = {"passed": True, "attempts": attempt}
                print(f"\n  → {agent_name} PASSED (attempt {attempt})")
                bus.finished(agent_name, 0)
                bus.outputs_updated(agent_name)
                agent_run_records.append(AgentRunRecord(
                    agent=agent_name, seed=seed, attempt=attempt,
                    passed=True, duration_seconds=agent_duration,
                    metrics_snapshot=metrics_snap,
                    judge_feedback=judge_result.feedback,
                ))
                break
            else:
                print(f"\n  [JUDGE] FAILED. Retry hint: {judge_result.retry_hint}")

                if judge_result.retry_hint == "revise_claims" and judge_result.actionable_feedback:
                    try:
                        from agents.memory_agent import persist_event
                        persist_event(agent_name, "failed", judge_result.actionable_feedback)
                    except ImportError:
                        pass

                    # Verification Agent
                    verification_records: list[VerificationRecord] = []
                    try:
                        from agents.verification_agent import verify_paper_claims
                        vreport = verify_paper_claims()
                        if vreport.get("claims"):
                            for c in vreport["claims"]:
                                verification_records.append(VerificationRecord(
                                    claim=c.get("claim", ""),
                                    verified=c.get("verified"),
                                    evidence=c.get("evidence", ""),
                                    error=c.get("error"),
                                ))
                            ctx.verifications.extend(verification_records)
                            failed_claims = [c for c in vreport["claims"] if c.get("verified") is False]
                            if failed_claims:
                                evidence = "; ".join(
                                    c.get("evidence", c.get("error", ""))[:100] for c in failed_claims
                                )
                                judge_result = judge_result.__class__(
                                    passed=judge_result.passed,
                                    feedback=judge_result.feedback,
                                    retry_hint=judge_result.retry_hint,
                                    actionable_feedback=(
                                        f"{judge_result.actionable_feedback}\n\n"
                                        f"[Verification Agent] Code-based check: {evidence}"
                                    ),
                                )
                    except ImportError:
                        pass

                    print("  [REVISION] Invoking Revision Agent to fix claim contradictions...")
                    env = os.environ.copy()
                    env["JUDGE_FEEDBACK"] = judge_result.actionable_feedback or ""
                    rev = subprocess.run(
                        [sys.executable, "-m", "agents.revision_agent"],
                        env=env,
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                    )
                    if rev.returncode == 0:
                        print("  [REVISION] Applied. Re-running Judge...")
                        judge_result2 = run_judge(agent_name)
                        for msg in judge_result2.feedback:
                            prefix = "  ✓" if judge_result2.passed else "  ✗"
                            print(f"{prefix} {msg}")
                        if judge_result2.passed:
                            results[agent_name] = {"passed": True, "attempts": attempt}
                            print(f"\n  → {agent_name} PASSED after revision (attempt {attempt})")
                            bus.finished(agent_name, 0)
                            agent_run_records.append(AgentRunRecord(
                                agent=agent_name, seed=seed, attempt=attempt,
                                passed=True, duration_seconds=time.time() - agent_start,
                                metrics_snapshot=metrics_snap,
                                judge_feedback=judge_result2.feedback,
                            ))
                            break
                    else:
                        print(f"  [REVISION] Failed: {rev.stderr or rev.stdout or 'unknown'}")

                agent_run_records.append(AgentRunRecord(
                    agent=agent_name, seed=seed, attempt=attempt,
                    passed=False, duration_seconds=agent_duration,
                    error="; ".join(judge_result.feedback[:3]),
                    error_type=_classify_error(None, "; ".join(judge_result.feedback)),
                    metrics_snapshot=metrics_snap,
                    judge_feedback=judge_result.feedback,
                    retry_hint=judge_result.retry_hint,
                ))

                if attempt == MAX_RETRIES:
                    results[agent_name] = {"passed": False, "attempts": attempt, "feedback": judge_result.feedback}
                    print(f"\n  → {agent_name} FAILED after {MAX_RETRIES} attempts. Stopping pipeline.")
                    bus.finished(agent_name, 1)
                    break

        if not results.get(agent_name, {}).get("passed"):
            break

    # Summary
    print("\n" + "=" * 70)
    print("  PIPELINE SUMMARY")
    print("=" * 70)
    for name, r in results.items():
        status = "PASS" if r["passed"] else "FAIL"
        attempts = r.get("attempts", 0)
        print(f"  {name:<12} {status}  (attempts: {attempts})")
    print("=" * 70)

    all_passed = all(r["passed"] for r in results.values())
    total_duration = time.time() - pipeline_start

    # Persist rich memory
    if memory:
        try:
            memory.persist_run_from_context(
                ctx,
                seed=seed,
                all_passed=all_passed,
                total_duration=total_duration,
                agent_runs=agent_run_records,
                verifications=ctx.verifications,
            )
        except Exception:
            traceback.print_exc()

    bus.pipeline_finished(all_passed, results)

    if all_passed:
        run_research_phase(bus)
        print("\n" + "=" * 70)
        print("  ALL PHASES COMPLETE")
        print("=" * 70)
        print("  Outputs in outputs/")
        print("  - outputs/paper/paper.tex, paper_sections/*.tex")
        print("  - outputs/research_findings.json, gap_report.json")
        print("  - outputs/coverage_suggestions.json, reproducibility_report.json")
        print("  - outputs/*.png, *.json, *.npz")
    else:
        print("\n  Pipeline incomplete. Fix failures and re-run.")
        sys.exit(1)


if __name__ == "__main__":
    main()

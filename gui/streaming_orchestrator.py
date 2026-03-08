"""
Streaming Orchestrator — Runs the pipeline with real-time event emission.
Used by the GUI server; original orchestrator.py remains for CLI.
Uses EventBus.connect_queue() to bridge typed events to the GUI queue,
and MemoryStore for rich self-evolution memory.
"""

import os
import sys
import subprocess
import queue
import time
import traceback

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from utils.context import PipelineContext
from utils.events import EventBus
from utils.schemas import AgentRunRecord, VerificationRecord

MAX_RETRIES = 3
AGENTS = ["detection", "mitigation", "auditing"]
RESEARCH_MODULES = ["agents.research_agent", "agents.gap_check_agent", "agents.coverage_agent", "agents.reproducibility_agent"]

MODULE_MAP = {
    "detection": "agents.detection_agent",
    "mitigation": "agents.mitigation_agent",
    "auditing": "agents.auditing_agent",
}


def _classify_error(stderr: str = "") -> str:
    """Classify an error for memory storage."""
    if "LaTeX" in stderr or "pdflatex" in stderr:
        return "LaTeXCompileError"
    if "timeout" in stderr.lower():
        return "GeminiTimeout"
    if "schema" in stderr.lower() or "missing key" in stderr.lower():
        return "SchemaValidation"
    return "Unknown"


def _run_agent_subprocess(agent_name: str, seed: int, bus: EventBus):
    """Run agent as subprocess, stream stdout lines through EventBus."""
    module = MODULE_MAP[agent_name]
    cmd = [sys.executable, "-u", "-m", module, str(seed)]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=SCRIPT_DIR,
    )

    for line in iter(proc.stdout.readline, ""):
        if line:
            s = line.rstrip()
            if s.startswith("[QMIND_PROGRESS]"):
                try:
                    rest = s[len("[QMIND_PROGRESS]"):]
                    pct_str, _, label = rest.partition("|")
                    pct = float(pct_str)
                    bus.progress(agent_name, pct, label)
                except ValueError:
                    pass
                continue
            bus.log(agent_name, s)

    proc.wait()
    return proc.returncode


def _run_research_module(module_name: str, bus: EventBus) -> int:
    """Run a research module as subprocess, stream stdout through EventBus."""
    cmd = [sys.executable, "-u", "-m", module_name]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=SCRIPT_DIR,
    )

    for line in iter(proc.stdout.readline, ""):
        if line:
            bus.log("research", line.rstrip())

    proc.wait()
    return proc.returncode


def _run_judge(agent_name: str):
    """Run judge evaluation. Returns JudgeResult dataclass."""
    from agents.judge_agent import evaluate
    return evaluate(agent_name)


def run_pipeline(event_queue: queue.Queue):
    """
    Run the full pipeline, putting events into event_queue via EventBus.
    Events: agent_started, agent_log, agent_finished, judge_result, outputs_updated, pipeline_finished
    """
    bus = EventBus()
    bus.connect_queue(event_queue)

    ctx = PipelineContext(seed=42)

    # Initialize memory store
    try:
        from agents.memory_agent import MemoryStore
        memory = MemoryStore()
    except ImportError:
        memory = None

    bus.log("", "Pipeline starting...")

    pipeline_start = time.time()
    results = {}
    agent_run_records: list[AgentRunRecord] = []
    seed = 42

    for agent_name in AGENTS:
        bus.started(agent_name)
        bus.log(agent_name, f"  Starting {agent_name} agent (loading libraries & data — may take 10–30s)...")

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                seed = 42 + attempt
                bus.log(agent_name, f"\n  [RETRY {attempt}/{MAX_RETRIES}] seed={seed}")

            agent_start = time.time()
            returncode = _run_agent_subprocess(agent_name, seed, bus)
            agent_duration = time.time() - agent_start
            bus.finished(agent_name, returncode)

            if returncode != 0:
                bus.log(agent_name, f"\n  [FAILED] Agent exited with error (returncode {returncode}). Retrying...")
                bus.judge_result(agent_name, False, ["Agent exited with error. Retrying..."], attempt=attempt)
                agent_run_records.append(AgentRunRecord(
                    agent=agent_name, seed=seed, attempt=attempt,
                    passed=False, duration_seconds=agent_duration,
                    error=f"Exit code {returncode}", error_type="SubprocessError",
                ))
                continue

            # Reload context from files after agent completes
            ctx = PipelineContext.load(seed=seed)

            bus.log(agent_name, f"  Running Judge evaluation for {agent_name}...")
            judge_result = _run_judge(agent_name)
            bus.log(
                agent_name,
                f"\n  [Judge] {'PASSED' if judge_result.passed else 'FAILED'}"
                + ("" if judge_result.passed else f": {'; '.join(judge_result.feedback[:3])}"),
            )
            bus.judge_result(
                agent_name, judge_result.passed, judge_result.feedback,
                judge_result.retry_hint, attempt,
            )

            metrics_snap = None
            if agent_name == "detection" and ctx.baseline:
                metrics_snap = ctx.baseline.to_dict()
            elif agent_name == "mitigation" and ctx.mitigation:
                metrics_snap = ctx.mitigation.to_dict()

            if judge_result.passed:
                results[agent_name] = {"passed": True, "attempts": attempt}
                bus.outputs_updated(agent_name)
                agent_run_records.append(AgentRunRecord(
                    agent=agent_name, seed=seed, attempt=attempt,
                    passed=True, duration_seconds=agent_duration,
                    metrics_snapshot=metrics_snap,
                    judge_feedback=judge_result.feedback,
                ))
                break
            else:
                if judge_result.retry_hint == "revise_claims" and judge_result.actionable_feedback:
                    bus.log(agent_name, "\n  [REVISION] Invoking Revision Agent to fix claim contradictions...")

                    # Verification Agent
                    try:
                        from agents.verification_agent import verify_paper_claims
                        vreport = verify_paper_claims()
                        if vreport.get("claims"):
                            for c in vreport["claims"]:
                                ctx.verifications.append(VerificationRecord(
                                    claim=c.get("claim", ""),
                                    verified=c.get("verified"),
                                    evidence=c.get("evidence", ""),
                                    error=c.get("error"),
                                ))
                    except ImportError:
                        pass

                    env = os.environ.copy()
                    env["JUDGE_FEEDBACK"] = judge_result.actionable_feedback
                    rev = subprocess.run(
                        [sys.executable, "-m", "agents.revision_agent"],
                        env=env,
                        capture_output=True,
                        text=True,
                        cwd=SCRIPT_DIR,
                    )
                    if rev.returncode == 0:
                        bus.log(agent_name, "  [REVISION] Applied. Re-running Judge...")
                        judge_result2 = _run_judge(agent_name)
                        bus.log(
                            agent_name,
                            f"  [Judge] {'PASSED' if judge_result2.passed else 'FAILED'} after revision"
                            + ("" if judge_result2.passed else f": {'; '.join(judge_result2.feedback[:3])}"),
                        )
                        bus.judge_result(
                            agent_name, judge_result2.passed, judge_result2.feedback,
                            attempt=attempt,
                        )
                        if judge_result2.passed:
                            results[agent_name] = {"passed": True, "attempts": attempt}
                            bus.outputs_updated(agent_name)
                            agent_run_records.append(AgentRunRecord(
                                agent=agent_name, seed=seed, attempt=attempt,
                                passed=True, duration_seconds=time.time() - agent_start,
                                metrics_snapshot=metrics_snap,
                                judge_feedback=judge_result2.feedback,
                            ))
                            break
                    else:
                        bus.log(agent_name, f"  [REVISION] FAILED: {rev.stderr or rev.stdout or 'unknown'}")

                agent_run_records.append(AgentRunRecord(
                    agent=agent_name, seed=seed, attempt=attempt,
                    passed=False, duration_seconds=agent_duration,
                    error="; ".join(judge_result.feedback[:3]),
                    error_type=_classify_error("; ".join(judge_result.feedback)),
                    metrics_snapshot=metrics_snap,
                    judge_feedback=judge_result.feedback,
                    retry_hint=judge_result.retry_hint,
                ))

                if attempt == MAX_RETRIES:
                    bus.log(agent_name, f"\n  [FAILED] {agent_name} failed after {MAX_RETRIES} attempts. Stopping pipeline.")
                    results[agent_name] = {"passed": False, "attempts": attempt, "feedback": judge_result.feedback}
                    break

        if not results.get(agent_name, {}).get("passed"):
            break

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

    # Research phase
    if all_passed:
        bus.log("research", f"\n{'─'*50}\n  RESEARCH PHASE — alphaXiv, Gap Check, Coverage, Reproducibility\n{'─'*50}")
        for module in RESEARCH_MODULES:
            bus.log("research", f"\n  >> {module}")
            _run_research_module(module, bus)

    bus.log(
        "",
        f"\n{'='*50}\n  Pipeline {'PASSED' if all_passed else 'FAILED'}. "
        + ("All agents passed." if all_passed else f"Failed at: {', '.join(a for a, r in results.items() if not r.get('passed'))}"),
    )
    bus.pipeline_finished(all_passed, results)

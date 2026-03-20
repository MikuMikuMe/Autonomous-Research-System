from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from runtime.core import PipelineRuntime, RuntimeConfig
from utils.events import EventBus, EventType, PipelineEvent


PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MODULE_MAP = {
    "detection": "agents.detection_agent",
    "mitigation": "agents.mitigation_agent",
    "auditing": "agents.auditing_agent",
}


def _classify_error(exc: Exception | None, stderr: str = "") -> str:
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


def _run_agent_subprocess(agent_name: str, seed: int, bus: EventBus) -> int:
    module = MODULE_MAP[agent_name]
    bus.log(agent_name, f"Starting {agent_name} agent...")
    result = subprocess.run(
        [sys.executable, "-m", module, str(seed)],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
    )
    return result.returncode


def _run_research_module(module_name: str, bus: EventBus) -> int:
    bus.log("research", f"Running {module_name}...")
    result = subprocess.run(
        [sys.executable, "-m", module_name],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
    )
    if result.returncode != 0:
        bus.log("research", f"[WARN] {module_name} exited with {result.returncode} (non-fatal)")
    return result.returncode


def _run_judge(agent_name: str):
    from agents.judge_agent import evaluate

    return evaluate(agent_name)


def _print_cli_event(event: PipelineEvent) -> None:
    if event.type == EventType.AGENT_STARTED:
        print(f"\n{'─' * 70}")
        print(f"  AGENT: {event.agent.upper()}")
        print("─" * 70)
    elif event.type == EventType.AGENT_LOG and event.line:
        print(f"  {event.line}")
    elif event.type == EventType.JUDGE_RESULT:
        for line in event.feedback:
            prefix = "✓" if event.passed else "✗"
            print(f"  {prefix} {line}")
    elif event.type == EventType.PIPELINE_FINISHED:
        results: dict[str, dict[str, Any]] = event.results or {}
        print("\n" + "=" * 70)
        print("  PIPELINE SUMMARY")
        print("=" * 70)
        for name, result in results.items():
            status = "PASS" if result.get("passed") else "FAIL"
            attempts = result.get("attempts", 0)
            print(f"  {name:<12} {status}  (attempts: {attempts})")
        print("=" * 70)


def build_runtime(bus: EventBus | None = None) -> PipelineRuntime:
    event_bus = bus or EventBus()
    config = RuntimeConfig.from_project_root(PROJECT_ROOT)
    return PipelineRuntime(
        config=config,
        bus=event_bus,
        run_agent=_run_agent_subprocess,
        run_research_module=_run_research_module,
        run_judge=_run_judge,
        classify_error=_classify_error,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Bias Audit Pipeline through the shared runtime.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _ = parse_args(argv)
    print("=" * 70)
    print("  UNIFIED AGENTIC SYSTEM — Orchestrator")
    print("  Pipeline: Detection → Mitigation → Auditing → Research")
    print("  Judge evaluates core agents; Research runs after paper is ready")
    print("=" * 70)

    bus = EventBus()
    bus.subscribe(_print_cli_event)
    summary = build_runtime(bus).run()

    if summary.all_passed:
        print("\n" + "=" * 70)
        print("  ALL PHASES COMPLETE")
        print("=" * 70)
        print("  Outputs in outputs/")
        print("  - outputs/paper/paper.tex, paper_sections/*.tex")
        print("  - outputs/research_findings.json, gap_report.json")
        print("  - outputs/coverage_suggestions.json, reproducibility_report.json")
        print("  - outputs/*.png, *.json, *.npz")
        return 0

    print("\n  Pipeline incomplete. Fix failures and re-run.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

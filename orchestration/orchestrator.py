"""
CLI-facing orchestrator for the Autonomous Research System.

Wraps ResearchRuntime with a CLI event printer for terminal usage.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from runtime.core import ResearchRuntime, RuntimeConfig
from utils.events import EventBus, EventType, PipelineEvent


PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _print_cli_event(event: PipelineEvent) -> None:
    if event.type == EventType.AGENT_STARTED:
        print(f"\n{'─' * 70}")
        print(f"  PHASE: {event.agent.upper()}")
        print("─" * 70)
    elif event.type == EventType.AGENT_LOG and event.line:
        print(f"  {event.line}")
    elif event.type == EventType.MEMORY_INSIGHT and event.line:
        print(f"  {event.line}")
    elif event.type == EventType.JUDGE_RESULT:
        for line in event.feedback:
            prefix = "✓" if event.passed else "✗"
            print(f"  {prefix} {line}")
    elif event.type == EventType.JOURNEY_SUMMARY:
        summary = event.summary or {}
        print("\n" + "-" * 70)
        print("  RESEARCH JOURNEY SUMMARY")
        print("-" * 70)
        for key, val in summary.items():
            if isinstance(val, dict):
                print(f"  {key}:")
                for k2, v2 in val.items():
                    print(f"    {k2}: {v2}")
            else:
                print(f"  {key}: {val}")
    elif event.type == EventType.PIPELINE_FINISHED:
        results: dict[str, Any] = event.results or {}
        print("\n" + "=" * 70)
        print("  RESEARCH SUMMARY")
        print("=" * 70)
        converged = results.get("converged", False)
        iterations = results.get("iterations_completed", 0)
        print(f"  Converged: {'Yes' if converged else 'No'}")
        print(f"  Iterations: {iterations}")
        if results.get("error"):
            print(f"  Error: {results['error']}")
        print("=" * 70)


def build_runtime(bus: EventBus | None = None) -> ResearchRuntime:
    event_bus = bus or EventBus()
    config = RuntimeConfig.from_project_root(PROJECT_ROOT)
    return ResearchRuntime(config=config, bus=event_bus)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous Research System — Orchestrator")
    parser.add_argument("--mode", choices=["goal", "report"], default="goal",
                        help="Research mode: goal-oriented or report/deep-dive")
    parser.add_argument("--goal", "-g", default="", help="Research goal")
    parser.add_argument("--topic", default=None, help="[report] Topic for deep-dive")
    parser.add_argument("--claims", "-c", default=None, help="Path to claims file")
    parser.add_argument("--iterations", "-n", type=int, default=None, help="Max iterations")
    parser.add_argument("--threshold", "-t", type=float, default=None, help="Convergence threshold")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    mode = args.mode
    goal = args.goal
    if mode == "report" and args.topic:
        goal = f"Produce a comprehensive research report on: {args.topic}"

    print("=" * 70)
    print("  AUTONOMOUS RESEARCH SYSTEM — Orchestrator")
    print(f"  Mode: {mode.upper()}")
    if goal:
        print(f"  Goal: {goal[:60]}{'...' if len(goal) > 60 else ''}")
    print("=" * 70)

    bus = EventBus()
    bus.subscribe(_print_cli_event)
    runtime = build_runtime(bus)
    summary = runtime.run(
        mode=mode,
        goal=goal,
        claims_source=args.claims,
        max_iterations=args.iterations,
        converge_threshold=args.threshold,
    )

    if summary.converged:
        print("\n" + "=" * 70)
        print("  RESEARCH CONVERGED")
        print("=" * 70)
        print("  Outputs in outputs/")
        print("  - outputs/research_loop_report.json")
        print("  - outputs/cross_validation_report.json")
        print("  - outputs/flaw_report.json")
        print("  - outputs/verification_report.json")
        return 0

    if summary.error:
        print(f"\n  Research failed: {summary.error}")
        return 1

    print(f"\n  Research completed after {summary.iterations_completed} iterations (not converged).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

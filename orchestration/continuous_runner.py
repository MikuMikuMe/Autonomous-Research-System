"""
Continuous Iteration Runner — Runs the pipeline in a loop with periodic compaction.

Implements the full DISCOVER → PLAN → ACT → OBSERVE → REFLECT cycle:

1. DISCOVER: Run self-check to verify system readiness
2. PLAN: Load pipeline config, pick seeds from memory
3. ACT: Execute the pipeline (Detection → Mitigation → Auditing → Research)
4. OBSERVE: Collect results, evaluate via Judge, persist to memory
5. REFLECT: Compact knowledge, remove obsolete data, self-diagnose

Usage:
  python -m orchestration.continuous_runner                    # Run once
  python -m orchestration.continuous_runner --iterations 5     # Run N iterations
  python -m orchestration.continuous_runner --compact-only     # Just compact memory
  python -m orchestration.continuous_runner --self-check       # Just run self-check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run_self_check(quiet: bool = False) -> bool:
    """DISCOVER phase: Verify system is ready for autonomous operation."""
    from agents.self_check_agent import run_self_check

    report = run_self_check()
    if not quiet:
        status = "AUTONOMOUS" if report.is_autonomous else "NOT AUTONOMOUS"
        print(f"\n  [SELF-CHECK] {report.passed}/{report.total_checks} checks passed — {status}")
        for issue in report.blocking_issues:
            print(f"    ✗ {issue}")
    return report.is_autonomous


def _compact_memory(quiet: bool = False) -> dict:
    """REFLECT phase: Compact knowledge, removing redundant/obsolete entries."""
    try:
        from agents.memory_agent import MemoryStore

        store = MemoryStore()
        # First, prune old runs
        pruned = store.prune_old_runs(keep_recent=50)
        # Then, compact knowledge (deduplicate insights, verifications, feedback)
        compacted = store.compact_knowledge()
        store.close()

        total_removed = pruned + sum(compacted.values())
        if not quiet:
            print(f"\n  [COMPACT] Pruned {pruned} old runs, compacted: {compacted}")
            print(f"  [COMPACT] Total entries removed: {total_removed}")
        return {"pruned_runs": pruned, "compacted": compacted, "total_removed": total_removed}
    except Exception as exc:
        if not quiet:
            print(f"\n  [COMPACT] Error during compaction: {exc}")
        return {"error": str(exc)}


def _run_pipeline_iteration(iteration: int, quiet: bool = False) -> dict:
    """ACT + OBSERVE: Run one full pipeline iteration."""
    from orchestration.orchestrator import build_runtime, _print_cli_event
    from utils.events import EventBus

    bus = EventBus()
    if not quiet:
        bus.subscribe(_print_cli_event)

    if not quiet:
        print(f"\n{'=' * 70}")
        print(f"  ITERATION {iteration} — Pipeline Execution")
        print(f"{'=' * 70}")

    start = time.time()
    summary = build_runtime(bus).run()
    elapsed = time.time() - start

    result = {
        "iteration": iteration,
        "all_passed": summary.all_passed,
        "seed": summary.seed,
        "duration_seconds": round(elapsed, 2),
        "results": {
            name: {
                "passed": data.get("passed", False),
                "attempts": data.get("attempts", 0),
            }
            for name, data in summary.results.items()
        },
    }

    if not quiet:
        status = "PASSED" if summary.all_passed else "FAILED"
        print(f"\n  [ITERATION {iteration}] {status} in {elapsed:.1f}s (seed={summary.seed})")

    return result


def run_continuous(
    iterations: int = 1,
    compact_interval: int = 3,
    quiet: bool = False,
) -> dict:
    """Run the pipeline continuously with periodic compaction.

    Args:
        iterations: Number of iterations to run (0 = just self-check + compact)
        compact_interval: Run compaction every N iterations
        quiet: Suppress output
    """
    overall_start = time.time()
    report: dict = {
        "iterations_requested": iterations,
        "iterations_completed": 0,
        "self_check_passed": False,
        "iteration_results": [],
        "compaction_results": [],
        "total_duration_seconds": 0,
    }

    # ── DISCOVER ──
    if not quiet:
        print("\n" + "=" * 70)
        print("  CONTINUOUS RUNNER — DISCOVER Phase")
        print("=" * 70)

    is_ready = _run_self_check(quiet=quiet)
    report["self_check_passed"] = is_ready

    if not is_ready:
        if not quiet:
            print("\n  [ABORT] System not ready for autonomous operation. Fix blocking issues first.")
        report["total_duration_seconds"] = round(time.time() - overall_start, 2)
        return report

    # ── Initial compaction ──
    if not quiet:
        print("\n  [REFLECT] Initial knowledge compaction...")
    compact_result = _compact_memory(quiet=quiet)
    report["compaction_results"].append({"phase": "initial", **compact_result})

    # ── PLAN + ACT + OBSERVE + REFLECT loop ──
    for i in range(1, iterations + 1):
        try:
            iteration_result = _run_pipeline_iteration(i, quiet=quiet)
            report["iteration_results"].append(iteration_result)
            report["iterations_completed"] = i

            # Periodic compaction (REFLECT)
            if i % compact_interval == 0:
                if not quiet:
                    print(f"\n  [REFLECT] Periodic compaction after iteration {i}...")
                compact_result = _compact_memory(quiet=quiet)
                report["compaction_results"].append({"phase": f"iteration_{i}", **compact_result})

        except KeyboardInterrupt:
            if not quiet:
                print(f"\n  [STOPPED] User interrupted after iteration {i}")
            break
        except Exception as exc:
            if not quiet:
                print(f"\n  [ERROR] Iteration {i} failed: {exc}")
                traceback.print_exc()
            report["iteration_results"].append({
                "iteration": i,
                "error": str(exc),
                "all_passed": False,
            })
            # REFLECT: Try to learn from the error
            try:
                from agents.memory_agent import persist_event
                persist_event("continuous_runner", "error", str(exc)[:500])
            except Exception:
                pass

    # ── Final compaction ──
    if not quiet:
        print("\n  [REFLECT] Final knowledge compaction...")
    compact_result = _compact_memory(quiet=quiet)
    report["compaction_results"].append({"phase": "final", **compact_result})

    report["total_duration_seconds"] = round(time.time() - overall_start, 2)

    # ── Save report ──
    output_dir = PROJECT_ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "continuous_runner_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if not quiet:
        passed = sum(1 for r in report["iteration_results"] if r.get("all_passed"))
        total = len(report["iteration_results"])
        print(f"\n{'=' * 70}")
        print(f"  CONTINUOUS RUNNER — Complete")
        print(f"  Iterations: {total}, Passed: {passed}, Failed: {total - passed}")
        print(f"  Total time: {report['total_duration_seconds']:.1f}s")
        print(f"  Report: {report_path}")
        print(f"{'=' * 70}")

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Bias Audit Pipeline continuously with periodic compaction."
    )
    parser.add_argument(
        "--iterations", "-n", type=int, default=1,
        help="Number of pipeline iterations to run (default: 1)",
    )
    parser.add_argument(
        "--compact-interval", type=int, default=3,
        help="Run knowledge compaction every N iterations (default: 3)",
    )
    parser.add_argument(
        "--compact-only", action="store_true",
        help="Only run knowledge compaction (no pipeline execution)",
    )
    parser.add_argument(
        "--self-check", action="store_true",
        help="Only run autonomy self-check (no pipeline execution)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress output (only print final summary)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.self_check:
        is_ready = _run_self_check(quiet=args.quiet)
        return 0 if is_ready else 1

    if args.compact_only:
        result = _compact_memory(quiet=args.quiet)
        return 0 if "error" not in result else 1

    report = run_continuous(
        iterations=args.iterations,
        compact_interval=args.compact_interval,
        quiet=args.quiet,
    )

    all_passed = all(r.get("all_passed", False) for r in report["iteration_results"])
    return 0 if (all_passed or report["iterations_requested"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())

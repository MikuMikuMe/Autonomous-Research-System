"""
Entry point for the Autonomous Research System.

Two modes:
  1. Goal-oriented (default): Iteratively research toward a quantifiable goal.
  2. Report: Deep-dive into a topic, producing a comprehensive research report.

Usage:
  python main.py --goal "Prove that transformer models outperform RNNs for NLP"
  python main.py --report --topic "Recent advances in quantum error correction"
  python main.py --goal "..." --claims claims.json --iterations 8
"""

import argparse
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Autonomous Research System\n\n"
            "  python main.py --goal 'My research goal'                    # Goal-oriented mode\n"
            "  python main.py --report --topic 'Topic for deep dive'       # Report mode\n"
            "  python main.py --goal '...' --claims claims.json -n 5       # With claims file\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--goal", "-g", default=None, help="Research goal (activates goal-oriented mode)")
    mode.add_argument("--report", action="store_true", help="Activate report/deep-dive mode")

    p.add_argument("--topic", default=None, help="[report] Topic for deep-dive research")
    p.add_argument("--claims", "-c", default=None, help="Path to claims file (JSON or text)")
    p.add_argument("--iterations", "-n", type=int, default=None, help="Max iterations")
    p.add_argument("--threshold", "-t", type=float, default=None, help="Convergence threshold (0.0-1.0)")
    p.add_argument("--flaw-halt", default=None, choices=["critical", "high", "any", "none"],
                    help="Flaw severity that blocks convergence")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    p.add_argument("--help", "-h", action="help", help="Show this help message and exit")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()

    if args.report:
        # Report mode: deep-dive research
        from orchestration.continuous_research_loop import run_research_loop
        topic = args.topic or "General research survey"
        report = run_research_loop(
            claims_source=args.claims,
            goal=f"Produce a comprehensive research report on: {topic}",
            max_iterations=args.iterations or 5,
            converge_threshold=args.threshold,
            flaw_halt_severity=args.flaw_halt,
            quiet=args.quiet,
            mode="report",
        )
        sys.exit(0 if not report.get("error") else 1)
    else:
        # Goal-oriented mode (default)
        from orchestration.continuous_research_loop import run_research_loop
        goal = args.goal or "Verify and refine research claims through iterative evidence gathering"
        report = run_research_loop(
            claims_source=args.claims,
            goal=goal,
            max_iterations=args.iterations,
            converge_threshold=args.threshold,
            flaw_halt_severity=args.flaw_halt,
            quiet=args.quiet,
            mode="goal",
        )
        sys.exit(0 if report.get("converged") or not report.get("error") else 1)



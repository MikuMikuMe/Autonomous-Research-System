"""Entry point for the Bias Audit Pipeline and Continuous Research Loop."""

import argparse
import sys


def _parse_top_level(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Autonomous Research System.\n\n"
            "  python main.py                         # Run the bias audit pipeline\n"
            "  python main.py --research              # Start continuous research loop\n"
            "  python main.py --research --claims claims.json --goal 'My goal' -n 5"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p.add_argument("--research", action="store_true", help="Run continuous research loop instead of bias pipeline")
    p.add_argument("--claims", "-c", default=None, help="[research] Path to claims file")
    p.add_argument("--goal", "-g", default=None, help="[research] Research goal text")
    p.add_argument("--iterations", "-n", type=int, default=None, help="[research] Max iterations")
    p.add_argument("--threshold", "-t", type=float, default=None, help="[research] Convergence threshold")
    p.add_argument("--flaw-halt", default=None, choices=["critical", "high", "any", "none"], help="[research] Flaw severity that blocks convergence")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    p.add_argument("--help", "-h", action="help", help="Show this help message and exit")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_top_level()

    if args.research:
        from orchestration.continuous_research_loop import run_research_loop
        report = run_research_loop(
            claims_source=args.claims,
            goal=args.goal or "Verify and refine research claims through iterative evidence gathering",
            max_iterations=args.iterations,
            converge_threshold=args.threshold,
            flaw_halt_severity=args.flaw_halt,
            quiet=args.quiet,
        )
        sys.exit(0 if report.get("converged") or not report.get("error") else 1)
    else:
        from orchestration.orchestrator import main
        main()


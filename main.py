"""Entry point for the Autonomous Research System.

Modes:
  python main.py "Your research idea"         # Run generalized research
  python main.py --research --claims claims.json  # Run continuous research loop
  python main.py --pipeline                    # Run legacy bias audit pipeline
"""

import argparse
import sys


def _parse_top_level(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Autonomous Research System.\n\n"
            "  python main.py \"Your research idea\"          # Generalized research\n"
            "  python main.py --research --claims claims.json # Continuous research loop\n"
            "  python main.py --pipeline                      # Legacy bias audit pipeline"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p.add_argument("idea", nargs="?", default=None, help="Research idea/topic/question (generalized mode)")
    p.add_argument("--pipeline", action="store_true", help="Run legacy bias audit pipeline")
    p.add_argument("--research", action="store_true", help="Run continuous research loop (claims-based)")
    p.add_argument("--claims", "-c", default=None, help="[research] Path to claims file")
    p.add_argument("--goal", "-g", default=None, help="Research goal text")
    p.add_argument("--iterations", "-n", type=int, default=5, help="Max iterations (default: 5)")
    p.add_argument("--threshold", "-t", type=float, default=0.85, help="Convergence threshold (default: 0.85)")
    p.add_argument("--flaw-halt", default="critical", choices=["critical", "high", "any", "none"],
                    help="Flaw severity that blocks convergence")
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    p.add_argument("--help", "-h", action="help", help="Show this help message and exit")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_top_level()

    if args.pipeline:
        # Legacy bias audit pipeline
        from orchestration.orchestrator import main
        main()
    elif args.research:
        # Claims-based continuous research loop
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
        # Generalized research mode (default)
        idea = args.idea
        if not idea:
            idea = input("Enter your research idea: ").strip()
            if not idea:
                print("Error: No research idea provided.")
                sys.exit(1)

        from orchestration.langgraph_orchestrator import run_research
        report = run_research(
            idea,
            goal=args.goal,
            max_iterations=args.iterations,
            converge_threshold=args.threshold,
            flaw_halt_severity=args.flaw_halt,
            quiet=args.quiet,
        )

        # Print narrative report
        if report.get("narrative_report"):
            print("\n" + "─" * 70)
            print("REPORT:")
            print("─" * 70)
            print(report["narrative_report"])

        sys.exit(0 if not report.get("error") else 1)


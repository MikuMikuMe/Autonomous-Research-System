"""
Research Pipeline Orchestrator — Runs research agents in sequence:
1. Research Agent — alphaXiv queries to prove claims from bias_mitigation, Bias Auditing, Bias Detection PDFs
2. Gap Check Agent — Compare paper + research vs how_biases_are_introduced.pdf
3. Coverage Agent — Find papers for gaps (alphaXiv)
4. Reproducibility Agent — Run detection/mitigation with multiple seeds to verify claims

Run after the main pipeline (orchestrator.py) has produced outputs/paper_draft.md.
Requires ALPHAXIV_TOKEN in .env for Research and Coverage agents.
"""

import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)


def run_module(module: str, *args) -> bool:
    """Run a Python module. Returns True if success."""
    cmd = [sys.executable, "-m", module] + list(args)
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def main():
    print("=" * 70)
    print("  RESEARCH PIPELINE — alphaXiv + Gap Check + Coverage + Reproducibility")
    print("=" * 70)

    # 1. Research Agent (alphaXiv)
    print("\n  [1/4] Research Agent — alphaXiv queries for claims")
    if not run_module("research_agent"):
        print("  Research agent failed (check ALPHAXIV_TOKEN in .env)")
    else:
        print("  Research agent OK")

    # 2. Gap Check (needs paper_draft.md; works even if empty)
    print("\n  [2/4] Gap Check Agent — vs how_biases_are_introduced.pdf")
    run_module("gap_check_agent")
    print("  Gap check OK")

    # 3. Coverage Agent (alphaXiv for gaps)
    print("\n  [3/4] Coverage Agent — Find papers for gaps")
    if not run_module("coverage_agent"):
        print("  Coverage agent failed (check ALPHAXIV_TOKEN)")
    else:
        print("  Coverage agent OK")

    # 4. Reproducibility (runs detection 3x + mitigation)
    print("\n  [4/4] Reproducibility Agent — Verify claims with multiple seeds")
    run_module("reproducibility_agent")
    print("  Reproducibility OK")

    print("\n" + "=" * 70)
    print("  RESEARCH PIPELINE COMPLETE")
    print("  Outputs:")
    print("    outputs/research_findings.json")
    print("    outputs/gap_report.json")
    print("    outputs/coverage_suggestions.json")
    print("    outputs/reproducibility_report.json")
    print("=" * 70)


if __name__ == "__main__":
    main()

"""
Unified Agentic System — Orchestrator
Runs Detection → Mitigation → Auditing → Research (alphaXiv, gap check, coverage, reproducibility).
Judge Agent evaluates each core output; failed agents are retried with feedback.
"""

import os
import sys
import subprocess
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

MAX_RETRIES = 3

# Config composition (Phase 4): load from pipeline.yaml if present
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
    """Run judge evaluation for an agent. Returns (passed, feedback, retry_hint, actionable_feedback)."""
    from agents.judge_agent import evaluate
    r = evaluate(agent_name)
    return r["passed"], r["feedback"], r.get("retry_hint"), r.get("actionable_feedback")


def parse_retry_hint(hint: str) -> int:
    """Extract seed from retry hint for detection/mitigation. Returns incrementing seed."""
    if hint and "different_seed" in str(hint):
        return None  # Signal: use different seed
    return 42


def run_research_phase():
    """Run research pipeline: alphaXiv, gap check, coverage, reproducibility."""
    print("\n" + "─" * 70)
    print("  RESEARCH PHASE — alphaXiv, Gap Check, Coverage, Reproducibility")
    print("─" * 70)
    for module in RESEARCH_AGENTS:
        print(f"\n  >> {module}")
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

    results = {}
    seed = 42

    for agent_name in AGENTS:
        print(f"\n{'─' * 70}")
        print(f"  AGENT: {agent_name.upper()}")
        print("─" * 70)

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                seed = 42 + attempt  # Vary seed on retry
                print(f"\n  [RETRY {attempt}/{MAX_RETRIES}] seed={seed}")

            # Run agent
            success = run_agent(agent_name, seed=seed)
            if not success:
                print(f"\n  [JUDGE] Agent exited with error. Retrying...")
                continue

            # Format check (auditing only): validate and fix table/format issues before Judge
            if agent_name == "auditing":
                try:
                    from agents.format_check_agent import run_format_check, apply_format_fixes
                    fc = run_format_check(paper_only=True)
                    if not fc["passed"]:
                        print("  [FORMAT] Issues found; applying fixes...")
                        apply_format_fixes()
                except ImportError:
                    pass

            # Judge evaluates
            passed, feedback, retry_hint, actionable_feedback = run_judge(agent_name)

            for msg in feedback:
                prefix = "  ✓" if passed else "  ✗"
                print(f"{prefix} {msg}")

            if passed:
                results[agent_name] = {"passed": True, "attempts": attempt}
                print(f"\n  → {agent_name} PASSED (attempt {attempt})")
                break
            else:
                print(f"\n  [JUDGE] FAILED. Retry hint: {retry_hint}")

                # AI Court / Autogenesis: Judge delegates fix → Verification (code-based) → Revision (Observe → Optimize)
                if retry_hint == "revise_claims" and actionable_feedback:
                    # Remember: persist failure for Optimizer
                    try:
                        from agents.memory_agent import persist_event
                        persist_event(agent_name, "failed", actionable_feedback)
                    except ImportError:
                        pass
                    # Optional: Verification Agent generates code, runs it to verify claims (never hardcode)
                    try:
                        from agents.verification_agent import verify_paper_claims
                        vreport = verify_paper_claims()
                        if vreport.get("claims") and any(c.get("verified") is False for c in vreport["claims"]):
                            evidence = "; ".join(c.get("evidence", c.get("error", ""))[:100] for c in vreport["claims"] if c.get("verified") is False)
                            actionable_feedback = f"{actionable_feedback}\n\n[Verification Agent] Code-based check: {evidence}"
                    except ImportError:
                        pass
                    print("  [REVISION] Invoking Revision Agent to fix claim contradictions...")
                    env = os.environ.copy()
                    env["JUDGE_FEEDBACK"] = actionable_feedback
                    rev = subprocess.run(
                        [sys.executable, "-m", "agents.revision_agent"],
                        env=env,
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                    )
                    if rev.returncode == 0:
                        print("  [REVISION] Applied. Re-running Judge...")
                        passed2, feedback2, _, _ = run_judge(agent_name)
                        for msg in feedback2:
                            prefix = "  ✓" if passed2 else "  ✗"
                            print(f"{prefix} {msg}")
                        if passed2:
                            results[agent_name] = {"passed": True, "attempts": attempt}
                            print(f"\n  → {agent_name} PASSED after revision (attempt {attempt})")
                            break
                    else:
                        print(f"  [REVISION] Failed: {rev.stderr or rev.stdout or 'unknown'}")

                if attempt == MAX_RETRIES:
                    results[agent_name] = {"passed": False, "attempts": attempt, "feedback": feedback}
                    print(f"\n  → {agent_name} FAILED after {MAX_RETRIES} attempts. Stopping pipeline.")
                    break

        if not results.get(agent_name, {}).get("passed"):
            break  # Stop pipeline on failure

    # Summary
    print("\n" + "=" * 70)
    print("  PIPELINE SUMMARY")
    print("=" * 70)
    for name, r in results.items():
        status = "PASS" if r["passed"] else "FAIL"
        attempts = r.get("attempts", 0)
        print(f"  {name:<12} {status}  (attempts: {attempts})")
    print("=" * 70)

    # Remember: persist session to memory for self-evolution (Optimizer)
    try:
        from agents.memory_agent import persist_session
        persist_session(results)
    except ImportError:
        pass

    all_passed = all(r["passed"] for r in results.values())
    if all_passed:
        run_research_phase()
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

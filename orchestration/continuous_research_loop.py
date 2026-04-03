"""
Continuous Research Loop — iterative, self-evolving research agent.

Each iteration follows DISCOVER → PLAN → ACT → OBSERVE → REFLECT:

  DISCOVER  Load and validate claims; run autonomy self-check.
  PLAN      Derive research queries from claims + memory gaps.
  ACT       Verify claims (code), retrieve papers, cross-validate,
            detect flaws.
  OBSERVE   Score iteration convergence (verified_ratio, no critical flaws).
  REFLECT   Persist findings to memory; evolve prompts via SEPL;
            compact knowledge every N iterations.

The loop terminates when:
  - verified_ratio >= converge_threshold AND no critical/high flaws
  - OR max_iterations is reached
  - OR the user presses Ctrl-C

Usage:
  python -m orchestration.continuous_research_loop \\
         --claims path/to/claims.json \\
         --goal   "Prove that threshold adjustment preserves fairness" \\
         --iterations 8

  # Or import directly:
  from orchestration.continuous_research_loop import run_research_loop
  run_research_loop(claims_source="claims.json", goal="...", max_iterations=5)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Configuration ─────────────────────────────────────────────────────────────

def _loop_config_from_yaml() -> dict:
    """Load research_loop section from configs/pipeline.yaml."""
    try:
        import yaml  # type: ignore[import]
        cfg_path = PROJECT_ROOT / "configs" / "pipeline.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("research_loop", {})
    except Exception:
        return {}


# ── Main entry point ──────────────────────────────────────────────────────────

def run_research_loop(
    claims_source: str | list | None = None,
    goal: str = "Verify and refine research claims through iterative evidence gathering",
    max_iterations: int | None = None,
    converge_threshold: float | None = None,
    evolve_every: int | None = None,
    compact_every: int | None = None,
    flaw_halt_severity: str | None = None,
    quiet: bool = False,
) -> dict:
    """Run the continuous research loop.

    Args:
        claims_source: Path to claims file, list of claim dicts, or None for
                       outputs/idea_input.json.
        goal:          High-level research goal (stored in memory).
        max_iterations: Override for pipeline.yaml research_loop.max_iterations.
        converge_threshold: Fraction of claims that must be verified to converge.
        evolve_every:   Evolve prompts (SEPL) every N iterations.
        compact_every:  Compact memory every N iterations.
        flaw_halt_severity: "critical"|"high"|"any"|"none" — severity that blocks
                            convergence.
        quiet:          Suppress progress output.

    Returns:
        Report dict saved to outputs/research_loop_report.json.
    """
    yaml_cfg = _loop_config_from_yaml()
    max_iterations = max_iterations or yaml_cfg.get("max_iterations", 10)
    converge_threshold = converge_threshold or yaml_cfg.get("converge_threshold", 0.90)
    evolve_every = evolve_every or yaml_cfg.get("evolve_every", 2)
    compact_every = compact_every or yaml_cfg.get("compact_every", 3)
    flaw_halt_severity = flaw_halt_severity or yaml_cfg.get("flaw_halt_severity", "critical")

    overall_start = time.time()
    report: dict = {
        "goal": goal,
        "claims_source": str(claims_source) if claims_source else "idea_input.json",
        "max_iterations": max_iterations,
        "converge_threshold": converge_threshold,
        "iterations_completed": 0,
        "converged": False,
        "iteration_results": [],
        "final_knowledge_summary": {},
        "total_duration_seconds": 0,
    }

    _print(quiet, "\n" + "=" * 70)
    _print(quiet, "  CONTINUOUS RESEARCH LOOP")
    _print(quiet, f"  Goal: {goal}")
    _print(quiet, "=" * 70)

    # ── DISCOVER ──────────────────────────────────────────────────────────────
    _print(quiet, "\n  [DISCOVER] Loading claims and validating system readiness...")

    try:
        from utils.claims_loader import load_claims
        claims = load_claims(claims_source)
    except FileNotFoundError as exc:
        _print(quiet, f"  [ABORT] Claims file not found: {exc}")
        report["error"] = str(exc)
        return _finalise(report, overall_start, quiet)

    if not claims:
        _print(quiet, "  [ABORT] No claims found. Provide a claims file or run idea_input_agent first.")
        report["error"] = "No claims loaded"
        return _finalise(report, overall_start, quiet)

    _print(quiet, f"  [DISCOVER] {len(claims)} claims loaded.")

    # Register goal in memory
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        goal_id: int | None = store.log_research_goal(goal)
        store.close()
    except Exception:
        goal_id = None

    # Autonomy self-check
    if not _self_check(quiet):
        _print(quiet, "  [WARN] Self-check issues detected — continuing with degraded autonomy.")

    # ── Main loop ─────────────────────────────────────────────────────────────
    for iteration in range(1, max_iterations + 1):
        _print(quiet, f"\n{'─' * 70}")
        _print(quiet, f"  ITERATION {iteration}/{max_iterations}")
        _print(quiet, f"{'─' * 70}")

        iter_start = time.time()
        iter_result: dict = {
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "claims_total": len(claims),
            "claims_verified": 0,
            "claims_contradicted": 0,
            "papers_retrieved": 0,
            "flaws_detected": 0,
            "critical_flaws": 0,
            "converged": False,
            "evolved": False,
            "duration_seconds": 0,
        }

        try:
            # ── PLAN ──────────────────────────────────────────────────────────
            _print(quiet, "\n  [PLAN] Generating research queries from claims...")
            queries = _derive_queries(claims, iteration, quiet)

            # ── ACT ───────────────────────────────────────────────────────────

            # 1. Verify claims with auto-generated code
            _print(quiet, "\n  [ACT] Verifying claims...")
            verification_report = _run_verification(claims, quiet)

            # 2. Retrieve related papers
            _print(quiet, "\n  [ACT] Retrieving related papers...")
            research_findings, paper_count = _run_research(queries, quiet)
            iter_result["papers_retrieved"] = paper_count

            # 3. Cross-validate claims against papers
            _print(quiet, "\n  [ACT] Cross-validating against literature...")
            cv_report = _run_cross_validation(claims, research_findings, quiet)

            # 4. Detect flaws
            _print(quiet, "\n  [ACT] Detecting flaws...")
            flaw_report = _run_flaw_detection(claims, verification_report, cv_report, quiet)

            # ── OBSERVE ───────────────────────────────────────────────────────
            _print(quiet, "\n  [OBSERVE] Scoring iteration...")

            verified_count = sum(
                1 for c in verification_report.get("claims", [])
                if c.get("verified") is True
            )
            contradicted_count = sum(
                1 for r in cv_report.get("results", [])
                if r.get("verdict") == "contradict"
            )
            critical_flaws = sum(
                1 for f in flaw_report.get("flaws", [])
                if f.get("severity") == "critical"
            )
            high_flaws = sum(
                1 for f in flaw_report.get("flaws", [])
                if f.get("severity") == "high"
            )
            total_flaws = len(flaw_report.get("flaws", []))

            iter_result["claims_verified"] = verified_count
            iter_result["claims_contradicted"] = contradicted_count
            iter_result["flaws_detected"] = total_flaws
            iter_result["critical_flaws"] = critical_flaws

            n_verifiable = len(verification_report.get("claims", [])) or 1
            verified_ratio = verified_count / n_verifiable

            blocking = _is_blocking_flaw(flaw_halt_severity, critical_flaws, high_flaws, total_flaws)
            converged = verified_ratio >= converge_threshold and not blocking

            iter_result["converged"] = converged
            iter_result["verified_ratio"] = round(verified_ratio, 3)

            _print(
                quiet,
                f"  [OBSERVE] Verified {verified_count}/{n_verifiable} ({verified_ratio:.0%}), "
                f"{total_flaws} flaws ({critical_flaws} critical), "
                f"{'CONVERGED ✓' if converged else 'not converged yet'}",
            )
            for alert in flaw_report.get("alerts", []):
                _print(quiet, f"  ⚠  {alert}")

            # ── REFLECT ───────────────────────────────────────────────────────
            _print(quiet, "\n  [REFLECT] Updating memory...")
            _persist_iteration(
                goal_id, iteration, claims, verification_report, cv_report, flaw_report
            )

            # Evolve prompts via SEPL
            if iteration % evolve_every == 0:
                evolved = _evolve(quiet)
                iter_result["evolved"] = evolved

            # Compact memory
            if iteration % compact_every == 0:
                _compact(quiet)

            # Update claims for next iteration: replace verified ones with gaps
            if not converged:
                claims = _refine_claims(claims, cv_report, flaw_report, quiet)

        except KeyboardInterrupt:
            _print(quiet, f"\n  [STOPPED] User interrupted after iteration {iteration}.")
            break
        except Exception as exc:
            _print(quiet, f"\n  [ERROR] Iteration {iteration} failed: {exc}")
            if not quiet:
                traceback.print_exc()
            iter_result["error"] = str(exc)

        iter_result["duration_seconds"] = round(time.time() - iter_start, 2)
        report["iteration_results"].append(iter_result)
        report["iterations_completed"] = iteration

        if iter_result.get("converged"):
            report["converged"] = True
            _print(quiet, f"\n  ✓ Research loop CONVERGED after {iteration} iteration(s).")
            if goal_id is not None:
                try:
                    from agents.memory_agent import MemoryStore
                    s = MemoryStore()
                    s.update_goal_progress(goal_id, iteration, "achieved")
                    s.close()
                except Exception:
                    pass
            break

    # ── Final compaction + knowledge summary ──────────────────────────────────
    _print(quiet, "\n  [REFLECT] Final memory compaction...")
    _compact(quiet)

    try:
        from agents.memory_agent import MemoryStore
        s = MemoryStore()
        report["final_knowledge_summary"] = s.research_journey_summary()
        s.close()
    except Exception:
        pass

    return _finalise(report, overall_start, quiet)


# ── Pipeline steps ────────────────────────────────────────────────────────────

def _derive_queries(claims: list[dict], iteration: int, quiet: bool) -> list[str]:
    """Convert claims to research queries using Gemini (fallback: claim text itself)."""
    try:
        from utils.llm_client import generate_json, is_available
        if is_available():
            claims_text = "\n".join(f"- {c.get('text', '')}" for c in claims[:15])
            prompt = (
                f"Iteration {iteration}. Convert these research claims into concise academic "
                "search queries (max 12 queries, 1 per claim, distil to key concepts).\n"
                f"Claims:\n{claims_text}\n\n"
                'Return JSON: {"queries": ["query1", "query2", ...]}'
            )
            result = generate_json(prompt)
            if result and result.get("queries"):
                queries = [str(q) for q in result["queries"][:12] if q]
                _print(quiet, f"  [PLAN] {len(queries)} queries generated via Gemini.")
                return queries
    except Exception:
        pass

    # Fallback: use claim text directly
    queries = [c.get("text", "")[:120] for c in claims[:10] if c.get("text")]
    _print(quiet, f"  [PLAN] {len(queries)} queries derived from claim text (no LLM).")
    return queries


def _run_verification(claims: list[dict], quiet: bool) -> dict:
    try:
        from agents.verification_agent import verify_claim
        results = []
        for claim in claims:
            text = claim.get("text", "")
            if not text:
                continue
            context = {k: v for k, v in claim.items() if k != "text"}
            result = verify_claim(text, context)
            result["claim"] = text
            results.append(result)
            status = "✓" if result.get("verified") else ("✗" if result.get("verified") is False else "?")
            _print(quiet, f"    [{status}] {text[:70]}")
        return {"timestamp": datetime.now().isoformat(), "claims": results}
    except Exception as exc:
        _print(quiet, f"  [WARN] Verification failed: {exc}")
        return {"claims": [], "error": str(exc)}


def _run_research(queries: list[str], quiet: bool) -> tuple[dict, int]:
    try:
        from agents.research_agent import run_research
        findings = run_research(queries=queries, max_queries=len(queries))
        papers = set()
        for entry in findings.get("queries", []):
            for r in entry.get("results", []):
                for p in r.get("papers_used", []):
                    papers.add(p.get("title", ""))
        count = len(papers)
        _print(quiet, f"  [ACT] Retrieved {count} unique papers.")
        return findings, count
    except Exception as exc:
        _print(quiet, f"  [WARN] Research retrieval failed: {exc}")
        return {}, 0


def _run_cross_validation(claims: list[dict], findings: dict, quiet: bool) -> dict:
    try:
        from agents.cross_validation_agent import cross_validate_claims
        report = cross_validate_claims(claims, findings)
        _print(quiet, f"  [ACT] {report.get('summary', '')}")
        return report
    except Exception as exc:
        _print(quiet, f"  [WARN] Cross-validation failed: {exc}")
        return {"results": [], "error": str(exc)}


def _run_flaw_detection(
    claims: list[dict], ver_report: dict, cv_report: dict, quiet: bool
) -> dict:
    try:
        from agents.flaw_detection_agent import detect_flaws
        report = detect_flaws(claims, ver_report, cv_report)
        _print(quiet, f"  [ACT] {report.get('summary', '')}")
        return report
    except Exception as exc:
        _print(quiet, f"  [WARN] Flaw detection failed: {exc}")
        return {"flaws": [], "alerts": [], "error": str(exc)}


def _persist_iteration(
    goal_id: int | None,
    iteration: int,
    claims: list[dict],
    ver_report: dict,
    cv_report: dict,
    flaw_report: dict,
) -> None:
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()

        if goal_id is not None:
            store.update_goal_progress(goal_id, iteration)

        # Persist cross-validated knowledge
        for r in cv_report.get("results", []):
            store.add_knowledge(
                claim=r.get("claim", ""),
                source="cross_validation",
                confidence=r.get("confidence", 0.5),
                supporting_papers=r.get("supporting_papers", []),
                verdict=r.get("verdict", "neutral"),
                rationale=r.get("rationale", ""),
                goal_id=goal_id,
            )

        # Persist new pitfalls
        for flaw in flaw_report.get("flaws", []):
            if flaw.get("severity") in ("critical", "high"):
                store.add_pitfall(
                    description=flaw.get("description", ""),
                    flaw_type=flaw.get("type", "unknown"),
                )

        # Mark verified claims as effective methods
        for c in ver_report.get("claims", []):
            if c.get("verified"):
                store.add_effective_method(
                    description=c.get("claim", "")[:500],
                    method_type="verified_claim",
                    domain="",
                )

        store.close()
    except Exception:
        pass


def _refine_claims(
    claims: list[dict],
    cv_report: dict,
    flaw_report: dict,
    quiet: bool,
) -> list[dict]:
    """Update claim list: keep unresolved + add gap-filling claims from Gemini."""
    contradicted_texts = {
        r.get("claim", "") for r in cv_report.get("results", [])
        if r.get("verdict") == "contradict"
    }
    critical_texts = {
        f.get("claim", "") for f in flaw_report.get("flaws", [])
        if f.get("severity") in ("critical", "high")
    }

    # Retain claims that need more work
    remaining = [
        c for c in claims
        if c.get("text") in contradicted_texts
        or c.get("text") in critical_texts
        or c.get("verified") is not True
    ]

    # Ask Gemini to suggest gap-filling claims
    gaps = [f.get("description", "") for f in flaw_report.get("flaws", []) if f.get("description")]
    if gaps:
        try:
            from utils.llm_client import generate_json, is_available
            if is_available():
                gaps_text = "\n".join(f"- {g}" for g in gaps[:5])
                prompt = (
                    "Based on these research gaps/flaws, suggest 1-3 new specific claims "
                    "that would address them:\n"
                    f"{gaps_text}\n\n"
                    'Return JSON: {"claims": [{"text": "...", "domain": "..."}]}'
                )
                result = generate_json(prompt)
                if result and result.get("claims"):
                    from utils.claims_loader import _normalise  # type: ignore[attr-defined]
                    new_claims = _normalise(result["claims"])
                    remaining.extend(new_claims)
                    _print(quiet, f"  [PLAN] Added {len(new_claims)} gap-filling claims for next iteration.")
        except Exception:
            pass

    return remaining if remaining else claims


def _evolve(quiet: bool) -> bool:
    """Run SEPL propose+commit to evolve prompts based on memory."""
    try:
        from orchestration.sep_layer import SEPLayer
        sepl = SEPLayer()
        proposals = sepl.propose()
        if proposals.get("proposals"):
            result = sepl.commit()
            _print(quiet, f"  [EVOLVE] Applied {result.get('applied', 0)} prompt refinements via SEPL.")
            return True
        _print(quiet, "  [EVOLVE] No new proposals from SEPL.")
    except Exception as exc:
        _print(quiet, f"  [EVOLVE] SEPL unavailable: {exc}")
    return False


def _compact(quiet: bool) -> None:
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        pruned = store.prune_old_runs(keep_recent=50)
        compacted = store.compact_knowledge()
        store.close()
        _print(quiet, f"  [COMPACT] Pruned {pruned} runs, compacted {sum(compacted.values())} entries.")
    except Exception as exc:
        _print(quiet, f"  [COMPACT] Error: {exc}")


def _self_check(quiet: bool) -> bool:
    try:
        from agents.self_check_agent import run_self_check
        report = run_self_check()
        if not quiet:
            status = "AUTONOMOUS" if report.is_autonomous else "NOT AUTONOMOUS"
            print(f"  [SELF-CHECK] {report.passed}/{report.total_checks} checks — {status}")
        return report.is_autonomous
    except Exception:
        return True  # Non-blocking: continue even if self-check can't run


# ── Convergence helpers ───────────────────────────────────────────────────────

def _is_blocking_flaw(
    halt_severity: str, critical: int, high: int, total: int
) -> bool:
    if halt_severity == "none":
        return False
    if halt_severity == "any":
        return total > 0
    if halt_severity == "high":
        return critical > 0 or high > 0
    # default: "critical"
    return critical > 0


# ── Output helpers ────────────────────────────────────────────────────────────

def _finalise(report: dict, start: float, quiet: bool) -> dict:
    report["total_duration_seconds"] = round(time.time() - start, 2)
    out_path = OUTPUT_DIR / "research_loop_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    _print(quiet, f"\n{'=' * 70}")
    _print(quiet, "  RESEARCH LOOP — Complete")
    _print(quiet, f"  Iterations: {report['iterations_completed']}/{report['max_iterations']}")
    _print(quiet, f"  Converged:  {'Yes ✓' if report['converged'] else 'No'}")
    _print(quiet, f"  Duration:   {report['total_duration_seconds']:.1f}s")
    _print(quiet, f"  Report:     outputs/research_loop_report.json")
    _print(quiet, f"{'=' * 70}")

    return report


def _print(quiet: bool, msg: str) -> None:
    if not quiet:
        print(msg)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Continuous self-evolving research loop.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--claims", "-c", default=None,
        help="Path to claims JSON/text file (default: outputs/idea_input.json)",
    )
    p.add_argument(
        "--goal", "-g",
        default="Verify and refine research claims through iterative evidence gathering",
        help="High-level research goal.",
    )
    p.add_argument(
        "--iterations", "-n", type=int, default=None,
        help="Max iterations (default from pipeline.yaml or 10)",
    )
    p.add_argument(
        "--threshold", "-t", type=float, default=None,
        help="Convergence threshold 0.0-1.0 (default 0.90)",
    )
    p.add_argument(
        "--evolve-every", type=int, default=None,
        help="Evolve prompts every N iterations (default 2)",
    )
    p.add_argument(
        "--flaw-halt", default=None,
        choices=["critical", "high", "any", "none"],
        help="Flaw severity that blocks convergence (default: critical)",
    )
    p.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run_research_loop(
        claims_source=args.claims,
        goal=args.goal,
        max_iterations=args.iterations,
        converge_threshold=args.threshold,
        evolve_every=args.evolve_every,
        flaw_halt_severity=args.flaw_halt,
        quiet=args.quiet,
    )
    return 0 if report.get("converged") or not report.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())

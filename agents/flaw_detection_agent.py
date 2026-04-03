"""
Flaw Detection Agent — Identifies logical, statistical, and methodological
flaws in research claims and experimental findings.

Three detection passes:
  1. Literature contradictions (from cross_validation_report.json)
  2. Code-verification failures (from verification_report.json)
  3. Gemini semantic analysis against known pitfalls from memory

New critical/high-severity flaws are stored as pitfalls in MemoryStore so
future iterations automatically avoid repeating them.

Output: outputs/flaw_report.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def detect_flaws(
    claims: list[dict],
    verification_report: dict | None = None,
    cross_validation_report: dict | None = None,
) -> dict:
    """Detect flaws across all *claims* using three passes.

    Args:
        claims: Normalised list from utils.claims_loader.load_claims().
        verification_report: From verification_agent, or None to load from disk.
        cross_validation_report: From cross_validation_agent, or None to load from disk.

    Returns:
        Report dict with 'flaws', 'alerts', and 'summary'.
    """
    if verification_report is None:
        verification_report = _load_json(os.path.join(OUTPUT_DIR, "verification_report.json")) or {}
    if cross_validation_report is None:
        cross_validation_report = _load_json(os.path.join(OUTPUT_DIR, "cross_validation_report.json")) or {}

    known_pitfalls = _get_known_pitfalls()

    report: dict = {
        "timestamp": datetime.now().isoformat(),
        "claims_analyzed": len(claims),
        "flaws": [],
        "alerts": [],
        "summary": "",
    }

    _pass_literature_contradictions(report, cross_validation_report)
    _pass_verification_failures(report, verification_report)
    _pass_gemini_analysis(report, claims, verification_report, cross_validation_report, known_pitfalls)

    # Sort flaws by severity
    report["flaws"].sort(key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 3))

    critical = sum(1 for f in report["flaws"] if f.get("severity") == "critical")
    high = sum(1 for f in report["flaws"] if f.get("severity") == "high")
    total = len(report["flaws"])
    report["summary"] = (
        f"{total} flaws detected ({critical} critical, {high} high). "
        + ("Immediate attention required." if critical or high else "No blocking issues.")
    )

    _persist_pitfalls(report)

    out_path = os.path.join(OUTPUT_DIR, "flaw_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


# ── Detection passes ──────────────────────────────────────────────────────────

def _pass_literature_contradictions(report: dict, cv_report: dict) -> None:
    for result in cv_report.get("results", []):
        if result.get("verdict") == "contradict":
            flaw = {
                "type": "literature_contradiction",
                "severity": "high",
                "claim": result.get("claim", ""),
                "description": (
                    f"Claim is contradicted by retrieved literature. "
                    f"{result.get('rationale', '')}"
                ),
                "contradicting_papers": result.get("contradicting_papers", []),
                "suggested_fix": "Revise the claim to align with, or explicitly address, the contradicting papers.",
            }
            report["flaws"].append(flaw)
            report["alerts"].append(
                f"[HIGH] Literature contradiction: '{result.get('claim', '')[:100]}'"
            )


def _pass_verification_failures(report: dict, ver_report: dict) -> None:
    for c in ver_report.get("claims", []):
        if c.get("verified") is False:
            flaw = {
                "type": "verification_failure",
                "severity": "critical",
                "claim": c.get("claim", ""),
                "description": (
                    f"Claim failed automated code verification. "
                    f"Evidence: {c.get('evidence', c.get('error', 'unknown'))}"
                ),
                "suggested_fix": "Correct the claim or the underlying data/methodology.",
            }
            report["flaws"].append(flaw)
            report["alerts"].append(
                f"[CRITICAL] Verification failed: '{c.get('claim', '')[:100]}'"
            )


def _pass_gemini_analysis(
    report: dict,
    claims: list[dict],
    ver_report: dict,
    cv_report: dict,
    known_pitfalls: list[dict],
) -> None:
    try:
        from utils.llm_client import generate_json, is_available
    except ImportError:
        return
    if not is_available():
        return

    claims_text = "\n".join(f"- {c.get('text', str(c))}" for c in claims[:20])
    pitfalls_text = (
        "\n".join(f"- {p.get('description', '')}" for p in known_pitfalls[:10])
        if known_pitfalls else "None recorded yet."
    )
    ver_summary = ver_report.get("summary", "No verification data.")
    cv_summary = cv_report.get("summary", "No cross-validation data.")

    prompt = (
        "You are a rigorous research reviewer. Analyze the claims below for flaws.\n\n"
        f"Claims:\n{claims_text}\n\n"
        f"Automated verification status: {ver_summary}\n"
        f"Literature cross-validation: {cv_summary}\n"
        f"Previously recorded pitfalls:\n{pitfalls_text}\n\n"
        "Identify flaws in these categories:\n"
        "  1. Logical inconsistencies or circular reasoning\n"
        "  2. Statistical or methodological errors\n"
        "  3. Unsupported or unverifiable assumptions\n"
        "  4. Overgeneralisation or scope creep\n"
        "  5. Missing controls or unaddressed confounders\n\n"
        "Return JSON:\n"
        "{\n"
        '  "flaws": [\n'
        "    {\n"
        '      "type": "logical|statistical|methodological|assumption|scope",\n'
        '      "severity": "critical|high|medium|low",\n'
        '      "claim": "<affected claim text>",\n'
        '      "description": "<what is wrong>",\n'
        '      "suggested_fix": "<how to fix it>"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    response = generate_json(prompt)
    if response and "flaws" in response:
        for flaw in response["flaws"]:
            if not isinstance(flaw, dict) or not flaw.get("description"):
                continue
            report["flaws"].append(flaw)
            if flaw.get("severity") in ("critical", "high"):
                report["alerts"].append(
                    f"[{flaw['severity'].upper()}] {flaw.get('description', '')[:120]}"
                )


# ── Memory helpers ────────────────────────────────────────────────────────────

def _get_known_pitfalls() -> list[dict]:
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        pitfalls = store.get_known_pitfalls()
        store.close()
        return pitfalls
    except Exception:
        return []


def _persist_pitfalls(report: dict) -> None:
    new = [f for f in report.get("flaws", []) if f.get("severity") in ("critical", "high")]
    if not new:
        return
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        for flaw in new:
            store.add_pitfall(
                description=flaw.get("description", ""),
                flaw_type=flaw.get("type", "unknown"),
            )
        store.close()
    except Exception:
        pass


def _load_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 64)
    print("  FLAW DETECTION AGENT")
    print("=" * 64)

    claims: list[dict] = []
    try:
        from utils.claims_loader import load_claims
        claims = load_claims()
    except Exception:
        pass

    if not claims:
        idea = _load_json(os.path.join(OUTPUT_DIR, "idea_input.json"))
        if idea:
            for hyp in idea.get("hypotheses", []):
                claims.append({"id": f"hyp_{len(claims)}", "text": hyp})

    if not claims:
        print("  No claims found. Run idea_input_agent first or provide a claims file.")
        return 1

    report = detect_flaws(claims)
    print(f"\n  {report['summary']}")
    for alert in report.get("alerts", []):
        print(f"  ⚠  {alert}")
    print(f"\n  Saved: outputs/flaw_report.json")

    has_critical = any(f.get("severity") == "critical" for f in report.get("flaws", []))
    return 1 if has_critical else 0


if __name__ == "__main__":
    sys.exit(main())

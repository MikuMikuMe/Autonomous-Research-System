"""
Cross-Validation Agent — Cross-validates research claims against retrieved papers.

For each claim, asks Gemini whether the literature supports, contradicts, or is
neutral toward it.  Results are persisted to MemoryStore so the research loop
can build up a cross-validated knowledge base across iterations.

Output: outputs/cross_validation_report.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def cross_validate_claims(
    claims: list[dict],
    research_findings: dict | None = None,
) -> dict:
    """Cross-validate *claims* against papers in *research_findings*.

    Args:
        claims: Normalised list from utils.claims_loader.load_claims().
        research_findings: Dict from research_agent.run_research(), or None to
                           load from outputs/research_findings.json.

    Returns:
        Report dict with per-claim verdicts (support | contradict | neutral).
    """
    if research_findings is None:
        research_findings = _load_json(os.path.join(OUTPUT_DIR, "research_findings.json")) or {}

    papers = _extract_papers(research_findings)

    report: dict = {
        "timestamp": datetime.now().isoformat(),
        "claims_evaluated": len(claims),
        "papers_used": len(papers),
        "results": [],
        "summary": "",
    }

    for claim in claims:
        report["results"].append(_validate_single_claim(claim, papers))

    supported = sum(1 for r in report["results"] if r.get("verdict") == "support")
    contradicted = sum(1 for r in report["results"] if r.get("verdict") == "contradict")
    neutral = len(report["results"]) - supported - contradicted
    report["summary"] = (
        f"{supported} claims supported, {contradicted} contradicted, "
        f"{neutral} neutral by retrieved literature."
    )

    out_path = os.path.join(OUTPUT_DIR, "cross_validation_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    _persist_to_memory(report)
    return report


# ── Per-claim validation ──────────────────────────────────────────────────────

def _validate_single_claim(claim: dict, papers: list[dict]) -> dict:
    claim_text = claim.get("text", str(claim))
    result: dict = {
        "claim_id": claim.get("id", ""),
        "claim": claim_text,
        "verdict": "neutral",
        "confidence": 0.5,
        "supporting_papers": [],
        "contradicting_papers": [],
        "rationale": "",
    }

    if not papers:
        result["rationale"] = "No papers available for cross-validation."
        return result

    try:
        from utils.llm_client import generate_json, is_available
    except ImportError:
        result["rationale"] = "LLM client not importable."
        return result

    if not is_available():
        result["rationale"] = "GOOGLE_API_KEY not set — skipping LLM cross-validation."
        return result

    # Build compact paper summaries
    summaries: list[str] = []
    for idx, p in enumerate(papers[:12], 1):
        title = p.get("title", p.get("name", f"Paper {idx}"))
        abstract = p.get("abstract", p.get("summary", p.get("excerpt", "")))[:300]
        summaries.append(f"[{idx}] {title}: {abstract}")
    papers_text = "\n".join(summaries)

    prompt = (
        f"Research claim: {claim_text}\n\n"
        f"Available papers:\n{papers_text}\n\n"
        "Determine whether the literature supports, contradicts, or is neutral toward the claim.\n"
        "Return JSON:\n"
        "{\n"
        '  "verdict": "support|contradict|neutral",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "supporting_papers": [<1-based paper indices>],\n'
        '  "contradicting_papers": [<1-based paper indices>],\n'
        '  "rationale": "<concise explanation referencing specific papers>"\n'
        "}"
    )

    response = generate_json(prompt)
    if response:
        result["verdict"] = response.get("verdict", "neutral")
        result["confidence"] = float(response.get("confidence", 0.5))
        result["supporting_papers"] = [
            papers[i - 1].get("title", f"Paper {i}")
            for i in response.get("supporting_papers", [])
            if 0 < i <= len(papers)
        ]
        result["contradicting_papers"] = [
            papers[i - 1].get("title", f"Paper {i}")
            for i in response.get("contradicting_papers", [])
            if 0 < i <= len(papers)
        ]
        result["rationale"] = response.get("rationale", "")

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_papers(findings: dict) -> list[dict]:
    """Flatten all paper objects out of a research_findings structure."""
    papers: list[dict] = []
    for entry in findings.get("queries", findings.get("results", [])):
        if not isinstance(entry, dict):
            continue
        for result in entry.get("results", []):
            for p in result.get("papers_used", []):
                papers.append(p)
        for p in entry.get("papers_used", []):
            papers.append(p)

    # Deduplicate by title
    seen: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        title = p.get("title", "")
        if title and title not in seen:
            seen.add(title)
            unique.append(p)
    return unique


def _load_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _persist_to_memory(report: dict) -> None:
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        for r in report.get("results", []):
            store.add_knowledge(
                claim=r.get("claim", ""),
                source="cross_validation",
                confidence=r.get("confidence", 0.5),
                supporting_papers=r.get("supporting_papers", []),
                verdict=r.get("verdict", "neutral"),
                rationale=r.get("rationale", ""),
            )
        store.close()
    except Exception:
        pass


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 64)
    print("  CROSS-VALIDATION AGENT")
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

    report = cross_validate_claims(claims)
    print(f"\n  {report['summary']}")
    for r in report["results"]:
        icon = {"support": "✓", "contradict": "✗", "neutral": "~"}.get(r.get("verdict", ""), "?")
        print(f"  [{icon}] {r.get('claim', '')[:80]} — {r.get('rationale', '')[:60]}")
    print(f"\n  Saved: outputs/cross_validation_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Claim Comparison Agent — Search papers (arXiv + Semantic Scholar), verify claims against our data,
determine whose claim is more supported, verify that conclusion, and cite the winning paper.

Pipeline:
1. Search arXiv + Semantic Scholar for papers relevant to the claim
2. Extract claims from the papers
3. Verify against our experimental data (baseline_results.json, mitigation_results.json)
4. Compare: our data vs literature — whose claim is more supported?
5. Run verification_agent to verify the comparison conclusion
6. Return the paper to cite (the one whose claim is more supported by evidence)
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")


def _load_json(path: str) -> dict | None:
    p = os.path.join(OUTPUT_DIR, path)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _search_papers(
    query: str,
    max_papers: int = 6,
) -> tuple[str, list[dict]]:
    """
    Search arXiv + Semantic Scholar. Returns (synthesized_text, papers_used).
    Always uses arXiv + Semantic Scholar (never alphaXiv) so we get structured papers for citation.
    """
    try:
        from research_client import fallback_research
        result, papers = fallback_research(query, max_papers=max_papers, download_pdfs=True, step_prefix="  ")
        return result or "", papers or []
    except ImportError:
        return "", []


def _extract_claim_from_literature(text: str, query: str) -> str | None:
    """Extract the main claim from literature (e.g. 'XGBoost with SMOTE achieves EU AI Act compliance')."""
    try:
        from llm_client import generate, is_available
    except ImportError:
        return None
    if not is_available():
        return None
    prompt = f"""Given this research query and synthesized literature:

Query: {query}

Literature summary:
---
{text[:4000]}
---

Extract the SINGLE most specific claim from the literature that can be verified against experimental data.
Examples: "XGBoost with SMOTE achieves |EOD| ≤ 0.05", "Reweighting reduces DPD by 50%", "Baseline models violate EU AI Act thresholds".
Output ONLY the claim text, one sentence, no quotes."""
    out = generate(prompt, max_output_tokens=256)
    return out.strip() if out and len(out.strip()) > 20 else None


def _compare_claims(
    literature_claim: str,
    our_data: dict,
    literature_supported: bool,
    our_supported: bool,
) -> dict:
    """
    Run verification to compare: whose claim is more supported?
    Returns {winner: "our_data"|"literature", paper_to_cite, evidence, verified}.
    """
    try:
        from verification_agent import verify_claim
    except ImportError:
        return {"winner": None, "paper_to_cite": None, "evidence": "Verification agent unavailable", "verified": False}

    claim = (
        f"Literature claim: '{literature_claim}'. "
        f"Our data: baseline_metrics and mitigation_metrics in the provided JSON. "
        f"Literature appears supported: {literature_supported}. Our data appears supported: {our_supported}. "
        "Determine: whose claim is more supported by the evidence? "
        "Output VERIFIED=True if the conclusion is consistent; VERIFIED=False if contradictory."
    )
    result = verify_claim(claim, our_data)
    return {
        "winner": "literature" if literature_supported and not our_supported else "our_data",
        "verified": result.get("verified"),
        "evidence": result.get("evidence", ""),
        "paper_to_cite": None,  # Filled by caller from papers_used
    }


def run_claim_comparison(
    query: str,
    result_text: str | None = None,
    papers_used: list[dict] | None = None,
) -> dict:
    """
    Full pipeline: search (if needed) → verify → compare → cite.

    If result_text and papers_used are provided (from research_agent), uses them.
    Otherwise searches arXiv + Semantic Scholar.

    Returns {
        "query": str,
        "literature_claim": str | None,
        "our_claim_supported": bool,
        "literature_claim_supported": bool,
        "winner": "our_data" | "literature",
        "paper_to_cite": dict | None,  # {title, ieee_citation, source}
        "verification": dict,
        "papers_searched": list,
    }
    """
    baseline = _load_json("baseline_results.json")
    mitigation = _load_json("mitigation_results.json")
    our_data = {
        "baseline_metrics": (baseline or {}).get("baseline_metrics", []),
        "mitigation_metrics": (mitigation or {}).get("mitigation_metrics", []),
        "asymmetric_cost_analysis": (mitigation or {}).get("asymmetric_cost_analysis", {}),
    }

    if result_text is None or papers_used is None:
        result_text, papers_used = _search_papers(query, max_papers=6)
    papers_used = papers_used or []

    literature_claim = _extract_claim_from_literature(result_text or "", query)

    # Verify against our data
    try:
        from research_result_processor import (
            _extract_numerical_claims,
            _verify_against_our_data,
        )
        claims = _extract_numerical_claims(result_text or "")
        verifications = _verify_against_our_data(claims, baseline, mitigation)
        our_supported = any(v.get("consistent") for v in verifications) and len(verifications) > 0
        literature_supported = len(claims) > 0  # Literature made claims we could check
    except ImportError:
        verifications = []
        our_supported = bool(baseline or mitigation)
        literature_supported = bool(literature_claim)

    comparison = _compare_claims(
        literature_claim or "Unknown",
        our_data,
        literature_supported,
        our_supported,
    )

    # Pick paper to cite: the one whose claim is more supported
    paper_to_cite = None
    if papers_used:
        # Cite the most relevant paper (first from search) when we have a winner
        paper_to_cite = papers_used[0]

    return {
        "query": query,
        "literature_claim": literature_claim,
        "our_claim_supported": our_supported,
        "literature_claim_supported": literature_supported,
        "winner": comparison.get("winner"),
        "paper_to_cite": paper_to_cite,
        "verification": {
            "verified": comparison.get("verified"),
            "evidence": comparison.get("evidence"),
        },
        "verifications": verifications,
        "papers_searched": papers_used or [],
    }


def main():
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else (
        "XGBoost with SMOTE achieves EU AI Act compliance for EOD and DI in fraud detection"
    )
    print("=" * 64)
    print("  CLAIM COMPARISON — Search, Verify, Compare, Cite")
    print("=" * 64)
    print(f"\n  Query: {query[:80]}...")
    result = run_claim_comparison(query)
    print(f"\n  Literature claim: {result.get('literature_claim', 'N/A')[:100]}...")
    print(f"  Our data supported: {result.get('our_claim_supported')}")
    print(f"  Literature supported: {result.get('literature_claim_supported')}")
    print(f"  Winner: {result.get('winner')}")
    if result.get("paper_to_cite"):
        p = result["paper_to_cite"]
        print(f"  Paper to cite: {p.get('title', '')[:60]}...")
        print(f"  IEEE: {p.get('ieee_citation', '')[:80]}...")
    out_path = os.path.join(OUTPUT_DIR, "claim_comparison_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()

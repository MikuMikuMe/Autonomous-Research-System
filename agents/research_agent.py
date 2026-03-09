"""
Research Agent — Finds papers supporting claims from:
- bias_mitigation.pdf
- Bias Auditing Framework.pdf
- Bias Detection findings.pdf

Uses research_client: alphaXiv Assistant V2 (if ALPHAXIV_TOKEN) or arXiv + Semantic Scholar + Gemini.
ALWAYS searches arXiv + Semantic Scholar for claim verification (even when alphaXiv is used for synthesis).
Saves findings to outputs/research_findings.json.
Validation runs in parallel: verify claims against our data, compare whose claim is more supported, cite winner.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Dynamic query generation from pipeline outputs (paper.tex, results, gaps)
# Falls back to hardcoded defaults if no context is available yet.
def _get_research_queries(max_queries: int = 10) -> list[str]:
    try:
        from utils.query_generator import generate_research_queries
        return generate_research_queries(max_queries=max_queries)
    except Exception as e:
        print(f"  [Research] Query generation failed ({e}), using defaults")
        from utils.query_generator import DEFAULT_RESEARCH_QUERIES
        return DEFAULT_RESEARCH_QUERIES[:max_queries]


def run_research(queries: list[str] | None = None, max_queries: int = 10, force_arxiv_semantic: bool = False) -> dict:
    """
    Query research for each question. Returns findings dict.

    When force_arxiv_semantic=True (or alphaXiv fails), ALWAYS uses arXiv + Semantic Scholar
    so we get structured papers_used for claim verification and citation.
    """
    if queries is None:
        queries = _get_research_queries(max_queries)
    findings = {
        "timestamp": datetime.now().isoformat(),
        "source_pdfs": [
            "bias_mitigation.pdf",
            "Bias Auditing Framework.pdf",
            "Bias Detection findings.pdf",
        ],
        "queries": [],
        "results": [],
        "errors": [],
    }

    try:
        from utils.research_client import answer_research_query_sync, fallback_research
    except ImportError as e:
        findings["errors"].append(f"research_client not available: {e}")
        return findings

    findings_lock = threading.Lock()
    out_path = os.path.join(OUTPUT_DIR, "research_findings.json")

    def _validate_and_compare(idx: int, result: str, q: str, papers_used: list, step_pfx: str):
        """Validate against our data; run claim comparison; determine paper to cite."""
        validation = {}
        try:
            from utils.research_result_processor import process_and_validate_result
            validation = process_and_validate_result(result, q, step_prefix=step_pfx)
        except ImportError:
            print(f"{step_pfx}[Validate] research_result_processor not available.", flush=True)
        except Exception as ve:
            print(f"{step_pfx}[Validate] Error: {ve}", flush=True)

        # Claim comparison: whose claim is more supported? Cite the winner.
        try:
            from agents.claim_comparison_agent import run_claim_comparison
            comparison = run_claim_comparison(q, result_text=result, papers_used=papers_used)
            validation["claim_comparison"] = {
                "winner": comparison.get("winner"),
                "paper_to_cite": comparison.get("paper_to_cite"),
                "literature_claim": comparison.get("literature_claim"),
            }
            if comparison.get("paper_to_cite"):
                print(f"{step_pfx}[Cite] Paper to cite: {comparison['paper_to_cite'].get('title', '')[:50]}...", flush=True)
        except ImportError:
            pass
        except Exception as ce:
            print(f"{step_pfx}[Compare] Error: {ce}", flush=True)

        with findings_lock:
            if idx < len(findings["results"]) and findings["results"][idx].get("success"):
                findings["results"][idx]["validation"] = validation
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(findings, f, indent=2, ensure_ascii=False)
        print(f"{step_pfx}[Validate] Done, saved.", flush=True)

    validation_futures = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, query in enumerate(queries):
            findings["queries"].append(query)
            step = f"[{i+1}/{len(queries)}] "
            print(f"\n  {step}Research query {i+1} of {len(queries)}:", flush=True)
            try:
                # Use arXiv + Semantic Scholar when we need papers_used for claim verification
                if force_arxiv_semantic:
                    result, papers_used = fallback_research(query, max_papers=6, step_prefix=f"  {step}")
                else:
                    result, papers_used = answer_research_query_sync(query, step_prefix=f"  {step}")
                    # If alphaXiv returned no papers, run arXiv+SS for citation
                    if not papers_used and result:
                        print(f"  {step}Running arXiv + Semantic Scholar for claim verification...", flush=True)
                        _, papers_used = fallback_research(query, max_papers=4, download_pdfs=False, step_prefix=f"  {step}")

                print(f"  {step}Query {i+1} complete. Validating and comparing claims...", flush=True)

                findings["results"].append({
                    "query": query,
                    "summary": result[:8000] if result else "",
                    "success": True,
                    "validation": {},
                    "papers_used": papers_used,
                })
                result_idx = len(findings["results"]) - 1

                fut = executor.submit(
                    _validate_and_compare,
                    result_idx,
                    result,
                    query,
                    papers_used,
                    f"  {step}",
                )
                validation_futures.append(fut)

                with findings_lock:
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(findings, f, indent=2, ensure_ascii=False)
            except Exception as e:
                findings["results"].append({
                    "query": query,
                    "error": str(e),
                    "success": False,
                })
                findings["errors"].append(f"Query '{query[:50]}...': {e}")
                print(f"  {step}Query {i+1} FAILED: {e}", flush=True)

        for fut in as_completed(validation_futures):
            try:
                fut.result()
            except Exception as e:
                print(f"  [Validate] Future error: {e}", flush=True)

    out_path = os.path.join(OUTPUT_DIR, "research_findings.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {out_path}")
    return findings


if __name__ == "__main__":
    print("=" * 60)
    print("  Research Agent — alphaXiv Assistant V2 / arXiv + Semantic Scholar + Gemini")
    print("  Proving claims from bias_mitigation, Bias Auditing, Bias Detection PDFs")
    print("=" * 60)
    run_research(max_queries=5)  # Start with 5 to avoid rate limits

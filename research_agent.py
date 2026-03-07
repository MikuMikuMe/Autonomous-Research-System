"""
Research Agent — Finds papers supporting claims from:
- bias_mitigation.pdf
- Bias Auditing Framework.pdf
- Bias Detection findings.pdf

Uses research_client: alphaXiv Assistant V2 (if ALPHAXIV_TOKEN) or arXiv + Semantic Scholar + Gemini.
Saves findings to outputs/research_findings.json.
Validation runs in parallel with the next alphaXiv query.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Queries derived from docs/RESEARCH_CHECKLIST.md and the three PDFs
RESEARCH_QUERIES = [
    "How do baseline ML models in fraud detection violate EU AI Act fairness thresholds (SPD, EOD, disparate impact)?",
    "Equalized odds post-processing: Fairlearn ThresholdOptimizer and techniques to reduce EOD below 0.05 for EU AI Act compliance",
    "ExponentiatedGradient EqualizedOdds in-processing: achieving |EOD| ≤ 0.05 in imbalanced financial datasets",
    "SMOTE vs reweighting for fairness in credit scoring and fraud detection: recent comparative studies",
    "Accuracy-fairness trade-off in bias mitigation: post-processing threshold adjustment",
    "Adversarial debiasing effectiveness and accuracy penalty in financial AI",
    "Bias types in AI: data, algorithmic, measurement, selection, temporal — systematic review",
    "Fairness metrics conflicts: demographic parity vs equalized odds vs disparate impact trade-offs",
    "EU AI Act Article 10 human-in-the-loop and high-risk AI requirements",
    "Bias auditing frameworks: pre-deployment assessment, continuous monitoring, stakeholder participation",
    "NYC Local Law 144 and EU AI Act risk-based conformity for automated decision systems",
    "Model selection for fairness: XGBoost vs Random Forest vs Logistic Regression under class imbalance",
]


def run_research(queries: list[str] | None = None, max_queries: int = 10) -> dict:
    """
    Query alphaXiv for each research question. Returns findings dict.
    """
    queries = queries or RESEARCH_QUERIES[:max_queries]
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
        from research_client import answer_research_query_sync
    except ImportError as e:
        findings["errors"].append(f"research_client not available: {e}")
        return findings

    findings_lock = threading.Lock()
    out_path = os.path.join(OUTPUT_DIR, "research_findings.json")

    def _validate_in_background(idx: int, result: str, q: str, step_pfx: str):
        """Run validation in thread; update findings and save when done."""
        validation = {}
        try:
            from research_result_processor import process_and_validate_result
            validation = process_and_validate_result(result, q, step_prefix=step_pfx)
        except ImportError:
            print(f"{step_pfx}[Validate] research_result_processor not available.", flush=True)
        except Exception as ve:
            print(f"{step_pfx}[Validate] Error: {ve}", flush=True)
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
                result, papers_used = answer_research_query_sync(query, step_prefix=f"  {step}")
                print(f"  {step}Query {i+1} complete. Validating in background, starting next...", flush=True)

                findings["results"].append({
                    "query": query,
                    "summary": result[:8000] if result else "",
                    "success": True,
                    "validation": {},
                    "papers_used": papers_used,
                })
                result_idx = len(findings["results"]) - 1

                # Run validation in parallel with next query
                fut = executor.submit(
                    _validate_in_background,
                    result_idx,
                    result,
                    query,
                    f"  {step}",
                )
                validation_futures.append(fut)

                # Save immediately (validation will overwrite with full data when done)
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

        # Wait for all validations to finish
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

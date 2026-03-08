"""
Coverage Agent — For each gap from gap_check_agent, uses research_client to find
papers that cover those topics (alphaXiv Assistant V2 or arXiv + Semantic Scholar + Gemini).
Writes a coverage report with suggested citations to add to the paper.
Validation runs in parallel with the next alphaXiv query.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")


def _load_gap_report() -> dict | None:
    path = os.path.join(OUTPUT_DIR, "gap_report.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_coverage() -> dict:
    """
    For each gap, query alphaXiv for papers. Build coverage report.
    """
    gap_report = _load_gap_report()
    if not gap_report or not gap_report.get("gaps"):
        return {"message": "No gaps to cover. Run gap_check_agent first.", "suggestions": []}

    suggestions = []
    try:
        from utils.research_client import answer_research_query_sync
    except ImportError:
        return {
            "message": "research_client not available. Install arxiv, semanticscholar, pypdf, httpx.",
            "gaps": gap_report["gaps"],
            "suggestions": [],
        }

    gaps = gap_report["gaps"]
    suggestions_lock = threading.Lock()
    out_path = os.path.join(OUTPUT_DIR, "coverage_suggestions.json")

    def _validate_in_background(idx: int, result: str, q: str, step_pfx: str, suggs: list, gaps_count: int):
        validation = {}
        try:
            from utils.research_result_processor import process_and_validate_result
            validation = process_and_validate_result(result, q, step_prefix=step_pfx)
        except (ImportError, Exception) as ve:
            print(f"{step_pfx}[Validate] Skipped: {ve}", flush=True)
        with suggestions_lock:
            if idx < len(suggs) and suggs[idx].get("success"):
                suggs[idx]["validation"] = validation
            report = {
                "timestamp": datetime.now().isoformat(),
                "source": "gap_report.json",
                "gaps_count": gaps_count,
                "suggestions": suggs,
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"{step_pfx}[Validate] Done, saved.", flush=True)

    validation_futures = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, gap in enumerate(gaps):
            topic = gap["topic"]
            query = f"Recent papers (2022-2025) on: {topic}. Focus on financial AI, credit scoring, or fraud detection if relevant."
            step = f"[{i+1}/{len(gaps)}] "
            print(f"\n  {step}Coverage query {i+1} of {len(gaps)} — gap: '{topic[:50]}...'", flush=True)
            try:
                result, papers_used = answer_research_query_sync(query, step_prefix=f"  {step}")
                print(f"  {step}Gap {i+1} complete. Validating in background, starting next...", flush=True)

                suggestions.append({
                    "gap_topic": topic,
                    "query": query,
                    "papers_summary": result[:4000] if result else "",
                    "success": True,
                    "validation": {},
                    "papers_used": papers_used,
                })
                sugg_idx = len(suggestions) - 1

                fut = executor.submit(
                    _validate_in_background,
                    sugg_idx,
                    result,
                    query,
                    f"  {step}",
                    suggestions,
                    len(gaps),
                )
                validation_futures.append(fut)

                with suggestions_lock:
                    report = {
                        "timestamp": datetime.now().isoformat(),
                        "source": "gap_report.json",
                        "gaps_count": len(gaps),
                        "suggestions": suggestions,
                    }
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(report, f, indent=2, ensure_ascii=False)
            except Exception as e:
                suggestions.append({
                    "gap_topic": topic,
                    "query": query,
                    "error": str(e),
                    "success": False,
                })
                print(f"  {step}Gap {i+1} FAILED: {e}", flush=True)

        for fut in as_completed(validation_futures):
            try:
                fut.result()
            except Exception as e:
                print(f"  [Validate] Future error: {e}", flush=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "source": "gap_report.json",
        "gaps_count": len(gap_report["gaps"]),
        "suggestions": suggestions,
    }

    out_path = os.path.join(OUTPUT_DIR, "coverage_suggestions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {out_path}")
    return report


if __name__ == "__main__":
    print("=" * 60)
    print("  Coverage Agent — Find papers for gaps")
    print("=" * 60)
    run_coverage()

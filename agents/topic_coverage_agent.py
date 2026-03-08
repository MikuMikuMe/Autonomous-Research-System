"""
Topic Coverage Agent — Verifies that all key topics from the reference PDFs
(bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf)
are mentioned in the paper. Uses Gemini to extract topics and check coverage.
Runs after the Auditing Agent produces paper.tex (LaTeX-only pipeline).
"""

import json
import os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
PAPER_TEX = os.path.join(OUTPUT_DIR, "paper", "paper.tex")
REPORT_PATH = os.path.join(OUTPUT_DIR, "topic_coverage_report.json")


# Fallback topics when Gemini extraction fails (derived from PDF structure)
FALLBACK_TOPICS = [
    {"pdf_name": "bias_mitigation.pdf", "topic": "SMOTE and reweighting", "keywords": ["SMOTE", "reweighting", "XGBoost", "Huang", "Turetken"]},
    {"pdf_name": "bias_mitigation.pdf", "topic": "Post-processing threshold adjustment", "keywords": ["threshold", "post-processing", "Fairlearn", "ThresholdOptimizer"]},
    {"pdf_name": "bias_mitigation.pdf", "topic": "Accuracy-fairness trade-off", "keywords": ["accuracy", "fairness", "trade-off", "EOD", "DPD"]},
    {"pdf_name": "bias_mitigation.pdf", "topic": "Equalized Odds", "keywords": ["equalized odds", "EOD", "FPR", "TPR"]},
    {"pdf_name": "Bias Auditing Framework.pdf", "topic": "Bias audit lifecycle", "keywords": ["audit", "lifecycle", "pre-deployment", "post-deployment"]},
    {"pdf_name": "Bias Auditing Framework.pdf", "topic": "Governance", "keywords": ["governance", "AI Ethics", "review board", "transparency"]},
    {"pdf_name": "Bias Auditing Framework.pdf", "topic": "Conformity assessment", "keywords": ["conformity", "assessment", "EU AI Act"]},
    {"pdf_name": "Bias Detection findings.pdf", "topic": "Sources of bias", "keywords": ["representational bias", "measurement bias", "algorithmic bias"]},
    {"pdf_name": "Bias Detection findings.pdf", "topic": "Demographic parity", "keywords": ["demographic parity", "statistical parity", "SPD"]},
    {"pdf_name": "Bias Detection findings.pdf", "topic": "Disparate impact", "keywords": ["disparate impact", "four-fifths", "DI"]},
]


def _get_fallback_topics() -> list[dict]:
    """Return predefined topics when Gemini extraction is unavailable."""
    return FALLBACK_TOPICS


def _load_paper_draft() -> str:
    """Load paper.tex (LaTeX-only pipeline)."""
    if os.path.exists(PAPER_TEX):
        with open(PAPER_TEX, encoding="utf-8") as f:
            return f.read()
    return ""


def _check_topic_in_paper(topic: dict, paper_text: str) -> dict:
    """
    Check if a topic is covered in the paper (keyword presence or Gemini semantic check).
    Returns {covered: bool, evidence: str, confidence: str}.
    """
    keywords = topic.get("keywords", [])
    paper_lower = paper_text.lower()
    matches = []
    for kw in keywords:
        if kw.lower() in paper_lower:
            matches.append(kw)
    if matches:
        return {
            "covered": True,
            "evidence": f"Keywords found: {', '.join(matches)}",
            "confidence": "high" if len(matches) >= 2 else "medium",
        }

    try:
        from utils.llm_client import generate, is_available
    except ImportError:
        return {"covered": False, "evidence": "No keywords found", "confidence": "low"}

    if not is_available():
        return {"covered": False, "evidence": "No keywords found", "confidence": "low"}

    prompt = f"""Topic from {topic['pdf_name']}: "{topic['topic']}" (keywords: {', '.join(keywords)})
Paper excerpt (first 8000 chars):
---
{paper_text[:8000]}
---

Is this topic substantially covered in the paper (even with different wording)?
Answer: COVERED or NOT_COVERED. One line only."""

    result = generate(prompt, max_output_tokens=50)
    covered = result and "COVERED" in result.upper() and "NOT" not in result.upper().split()[0]
    return {
        "covered": covered,
        "evidence": result.strip() if result else "Gemini check failed",
        "confidence": "gemini",
    }


def run_topic_coverage() -> dict:
    """
    Extract topics from source PDFs, check coverage in paper.tex.
    Returns report with covered/missing topics per PDF.
    """
    try:
        from utils.pdf_source_extractor import extract_topics_from_pdfs
    except ImportError:
        return {
            "error": "pdf_source_extractor not available",
            "timestamp": datetime.now().isoformat(),
        }

    paper_text = _load_paper_draft()
    if not paper_text or len(paper_text.strip()) < 500:
        return {
            "error": "paper.tex not found or too short. Run auditing_agent first.",
            "timestamp": datetime.now().isoformat(),
        }

    topics = extract_topics_from_pdfs()
    if not topics:
        topics = _get_fallback_topics()
    if not topics:
        return {
            "message": "No topics extracted (Gemini may be unavailable). Set GOOGLE_API_KEY.",
            "timestamp": datetime.now().isoformat(),
            "paper_length": len(paper_text),
        }

    results = []
    by_pdf = {}
    for t in topics:
        check = _check_topic_in_paper(t, paper_text)
        entry = {
            "pdf_name": t["pdf_name"],
            "topic": t["topic"],
            "keywords": t["keywords"],
            "covered": check["covered"],
            "evidence": check["evidence"],
            "confidence": check["confidence"],
        }
        results.append(entry)
        pdf = t["pdf_name"]
        if pdf not in by_pdf:
            by_pdf[pdf] = {"covered": [], "missing": []}
        if check["covered"]:
            by_pdf[pdf]["covered"].append(t["topic"])
        else:
            by_pdf[pdf]["missing"].append(t["topic"])

    report = {
        "timestamp": datetime.now().isoformat(),
        "paper_source": str(PAPER_TEX),
        "paper_length": len(paper_text),
        "total_topics": len(topics),
        "covered_count": sum(1 for r in results if r["covered"]),
        "missing_count": sum(1 for r in results if not r["covered"]),
        "by_pdf": by_pdf,
        "details": results,
        "passed": all(r["covered"] for r in results),
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


def format_report(report: dict) -> str:
    """Format the coverage report for console output."""
    if report.get("error"):
        return f"  Error: {report['error']}"
    if report.get("message"):
        return f"  {report['message']}"

    lines = [
        "",
        "  Topic Coverage Report",
        "  " + "-" * 40,
        f"  Total topics: {report.get('total_topics', 0)}",
        f"  Covered: {report.get('covered_count', 0)}",
        f"  Missing: {report.get('missing_count', 0)}",
        f"  Passed: {'Yes' if report.get('passed') else 'No'}",
        "",
    ]
    by_pdf = report.get("by_pdf", {})
    for pdf, data in by_pdf.items():
        lines.append(f"  [{pdf}]")
        missing = data.get("missing", [])
        if missing:
            lines.append(f"    Missing: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")
        else:
            lines.append("    All topics covered.")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("  Topic Coverage Agent — Verify PDF topics in paper")
    print("=" * 60)
    report = run_topic_coverage()
    print(format_report(report))
    print(f"\n  Report saved: {REPORT_PATH}")

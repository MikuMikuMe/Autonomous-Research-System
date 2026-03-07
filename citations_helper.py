"""
Citations Helper — Collect IEEE citations from research_findings and coverage_suggestions.
Used by auditing_agent to build dynamic references for the paper.
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")


def collect_ieee_citations() -> list[dict]:
    """
    Collect all papers_used from research_findings.json and coverage_suggestions.json.
    Prioritizes paper_to_cite from claim_comparison (whose claim is more supported).
    Deduplicates by title. Returns list of {title, ieee_citation, source}.
    """
    seen_titles = set()
    citations = []
    priority_cites = []  # Papers to cite from claim comparison (verified as more supported)

    # 1. Collect paper_to_cite from claim_comparison (verified winner)
    claim_path = os.path.join(OUTPUT_DIR, "claim_comparison_report.json")
    if os.path.exists(claim_path):
        try:
            with open(claim_path, encoding="utf-8") as f:
                cc = json.load(f)
            p = cc.get("paper_to_cite")
            if p and (p.get("title") or p.get("ieee_citation")):
                priority_cites.append(p)
        except (json.JSONDecodeError, OSError):
            pass

    # 2. From research_findings: paper_to_cite in validation.claim_comparison
    for path in [
        os.path.join(OUTPUT_DIR, "research_findings.json"),
        os.path.join(OUTPUT_DIR, "coverage_suggestions.json"),
    ]:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        results = data.get("results", []) or data.get("suggestions", [])
        for r in results:
            v = r.get("validation", {}) or {}
            pc = v.get("claim_comparison", {}).get("paper_to_cite")
            if pc and (pc.get("title") or pc.get("ieee_citation")):
                priority_cites.append(pc)
            for p in r.get("papers_used", []):
                title = (p.get("title") or "").strip()
                ieee = (p.get("ieee_citation") or "").strip()
                if not title and not ieee:
                    continue
                key = title.lower()[:80] if title else ieee[:80]
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                citations.append({
                    "title": title,
                    "ieee_citation": ieee or title,
                    "source": p.get("source", ""),
                })

    # Prepend priority cites (verified as more supported)
    for p in reversed(priority_cites):
        title = (p.get("title") or "").strip()
        ieee = (p.get("ieee_citation") or "").strip()
        if title or ieee:
            key = title.lower()[:80] if title else ieee[:80]
            if key not in seen_titles:
                seen_titles.add(key)
                citations.insert(0, {
                    "title": title,
                    "ieee_citation": ieee or title,
                    "source": p.get("source", ""),
                })

    return citations


def _format_pdf_citation(c: dict) -> str:
    """Format a citation from source PDFs for the references section."""
    raw = (c.get("raw") or "").strip()
    source_pdf = (c.get("source_pdf") or "").strip()
    doi = (c.get("doi") or "").strip()
    if raw:
        suffix = f" [Cited in {source_pdf}]" if source_pdf else ""
        if doi:
            return f"{raw}. https://doi.org/{doi}{suffix}"
        return f"{raw}.{suffix}"
    return ""


def collect_pdf_citations() -> list[dict]:
    """Collect citations from source PDFs (bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf)."""
    try:
        from pdf_source_extractor import get_all_citations
        return get_all_citations()
    except ImportError:
        return []


def format_references_markdown(
    static_refs: list[str],
    dynamic_citations: list[dict],
    pdf_citations: list[dict] | None = None,
) -> str:
    """Merge static references with dynamic IEEE citations and source PDF citations."""
    lines = ["# References", ""]
    for ref in static_refs:
        lines.append(f"- {ref}")
        lines.append("")

    # Add citations from source PDFs (avoid duplicates with static by author-year)
    static_lower = " ".join(static_refs).lower()
    if pdf_citations is None:
        pdf_citations = collect_pdf_citations()
    if pdf_citations:
        lines.append("## Literature Cited in Source Documents")
        lines.append("")
        lines.append(
            "The following are cited in our reference documents "
            "(bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf)."
        )
        lines.append("")
        seen_raw = set()
        for c in pdf_citations:
            raw = (c.get("raw") or "").strip()
            if raw and raw in seen_raw:
                continue
            seen_raw.add(raw)
            formatted = _format_pdf_citation(c)
            if formatted:
                lines.append(f"- {formatted}")
                lines.append("")

    if dynamic_citations:
        lines.append("## Literature Retrieved via Semantic Scholar & arXiv")
        lines.append("")
        lines.append(
            "The following papers were retrieved during our research validation pipeline "
            "and used to support claims in this paper. Citations are in IEEE format."
        )
        lines.append("")
        for c in dynamic_citations:
            ieee = c.get("ieee_citation", c.get("title", ""))
            if ieee:
                lines.append(f"- {ieee}")
                lines.append("")
    return "\n".join(lines)

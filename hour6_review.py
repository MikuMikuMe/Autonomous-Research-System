"""
Hour 6: Review, Format, and Citations
Uses Gemini to:
- Verify paper structure (Background, Use Case, Detection, Mitigation, Audit, Discussion)
- Check formulas are present (Demographic Parity, Disparate Impact, Equalized Odds, Accuracy, F1)
- Optionally search for recent papers to support claims (Google Search grounding)
- Suggest citation updates
"""

import os
import json
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
PAPER_DIR = os.path.join(OUTPUT_DIR, "paper")
SECTIONS_DIR = os.path.join(OUTPUT_DIR, "paper_sections")

REQUIRED_STRUCTURE = [
    "Background",
    "Use Case",
    "Detection",
    "Mitigation",
    "Audit Framework",
    "Discussion",
]
REQUIRED_FORMULAS = [
    "Demographic Parity",
    "Disparate Impact",
    "Equalized Odds",
    "Accuracy",
    "F1",
]


def _read_file(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return f.read()


def run_structure_review(draft_text: str) -> dict | None:
    """Use Gemini to verify paper structure and formulas."""
    try:
        from llm_client import generate, is_available
        if not is_available():
            return None
    except ImportError:
        return None

    preview = draft_text[:10000] + "..." if len(draft_text) > 10000 else draft_text

    prompt = f"""You are a research paper reviewer. Check this draft for Hour 6 compliance.

**Required structure (in order):** {", ".join(REQUIRED_STRUCTURE)}
**Required formulas in methodology:** {", ".join(REQUIRED_FORMULAS)}

**Paper draft (excerpt):**
{preview}

**Your task:**
1. List which required sections are present (by name).
2. List which required formulas are mentioned.
3. Note any missing items.
4. Overall: is the paper ready for submission format-wise?

Respond in JSON:
{{"sections_present": ["list"], "sections_missing": ["list"], "formulas_present": ["list"], "formulas_missing": ["list"], "ready": true/false, "summary": "1-2 sentences"}}
"""
    out = generate(prompt)
    if not out:
        return None
    m = re.search(r"\{[\s\S]*\}", out)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def run_citation_research(paper_claims: str) -> dict | None:
    """Use Gemini with Google Search grounding to find recent papers supporting the claims."""
    try:
        from llm_client import generate_with_grounding, is_available
        if not is_available():
            return None
    except ImportError:
        return None

    prompt = f"""Search for RECENT (2023-2025) academic papers that support these claims about bias in financial AI / credit scoring / fraud detection:

{paper_claims}

For each relevant paper you find, provide:
- Title
- Authors
- Year
- Key finding that supports our claims
- URL or DOI if available

Focus on: EU AI Act fairness thresholds, SMOTE for bias mitigation, accuracy-fairness trade-off, demographic parity in credit/fraud.

Respond with a structured list. If no recent papers found, say so.
"""
    out = generate_with_grounding(prompt)
    return {"research": out} if out else None


def run_full_review(draft_path: str = None, use_research: bool = True) -> dict:
    """Run Hour 6 review: structure check + optional citation research."""
    draft_path = draft_path or os.path.join(OUTPUT_DIR, "paper_draft.md")
    draft = _read_file(draft_path)

    result = {
        "structure_review": None,
        "citation_research": None,
        "recommendations": [],
    }

    # 1. Structure and formula review
    struct = run_structure_review(draft)
    result["structure_review"] = struct
    if struct:
        if struct.get("sections_missing"):
            result["recommendations"].append(
                f"Add missing sections: {', '.join(struct['sections_missing'])}"
            )
        if struct.get("formulas_missing"):
            result["recommendations"].append(
                f"Add formulas to methodology: {', '.join(struct['formulas_missing'])}"
            )
        if struct.get("ready"):
            result["recommendations"].append("Paper structure is submission-ready.")

    # 2. Citation research (with grounding)
    if use_research and draft:
        # Claims aligned with docs/RESEARCH_CHECKLIST.md; use alphaXiv MCP for more papers
        claims = """
- Baseline ML models (LR, Random Forest) in fraud detection violate EU AI Act fairness thresholds (|SPD|<=0.1, |EOD|<=0.05).
- SMOTE + XGBoost improves fairness compared to reweighting logistic regression; model selection matters.
- Reweighting produces no measurable change for LR/KNN (Huang & Turetken, 2025).
- Accuracy-fairness trade-off: mitigation may increase false positives (asymmetric cost in fraud).
- Adversarial debiasing reduces EOD up to 58%% but incurs 15%% accuracy loss.
- Post-processing (threshold adjustment): sub-200ms latency, but requires demographic data (GDPR).
- Audit frameworks: pre-deployment data assessment, continuous monitoring, stakeholder participation.
"""
        research = run_citation_research(claims)
        result["citation_research"] = research

    return result


def format_review_report(review: dict) -> str:
    """Format the Hour 6 review as a readable report."""
    lines = ["=" * 60, "  Review, Format, and Citations", "=" * 60]

    struct = review.get("structure_review")
    if struct:
        lines.append("\n  Structure review:")
        lines.append(f"    Sections present: {', '.join(struct.get('sections_present', []))}")
        if struct.get("sections_missing"):
            lines.append(f"    Sections missing: {', '.join(struct['sections_missing'])}")
        lines.append(f"    Formulas present: {', '.join(struct.get('formulas_present', []))}")
        if struct.get("formulas_missing"):
            lines.append(f"    Formulas missing: {', '.join(struct['formulas_missing'])}")
        lines.append(f"    Ready: {struct.get('ready', False)}")
        lines.append(f"    Summary: {struct.get('summary', 'N/A')}")
    else:
        lines.append("\n  Structure review: (Gemini not available — run with GOOGLE_API_KEY)")

    research = review.get("citation_research")
    if research and research.get("research"):
        lines.append("\n  Citation research (recent papers):")
        for line in research["research"][:1500].split("\n"):
            lines.append(f"    {line}")
    else:
        lines.append("\n  Citation research: (no additional papers found or Gemini unavailable)")

    if review.get("recommendations"):
        lines.append("\n  Recommendations:")
        for r in review["recommendations"]:
            lines.append(f"    - {r}")

    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    review = run_full_review(use_research=True)
    print(format_review_report(review))

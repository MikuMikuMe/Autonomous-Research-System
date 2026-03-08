"""
Gap Check Agent — Compares paper and research findings against how_biases_are_introduced.pdf.
Identifies topics from the PDF that are not yet covered. Uses docs/RESEARCH_CHECKLIST.md
as the canonical topic list (derived from how_biases_are_introduced.pdf and related PDFs).
"""

import json
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
CHECKLIST_PATH = os.path.join(PROJECT_ROOT, "docs", "RESEARCH_CHECKLIST.md")

# Topics from how_biases_are_introduced.pdf (from RESEARCH_CHECKLIST + common themes)
# Each: (topic, keywords that indicate coverage)
TOPICS_FROM_HOW_BIASES = [
    ("Bias types: data, algorithmic, measurement, selection, temporal", ["data bias", "algorithmic bias", "measurement bias", "selection bias", "temporal bias", "confounding"]),
    ("Fairness metrics: demographic parity, equalized odds, disparate impact", ["demographic parity", "equalized odds", "disparate impact", "DPD", "EOD", "DI"]),
    ("Metric conflicts and trade-offs", ["metric conflict", "trade-off", "tradeoff", "incompatible"]),
    ("EU AI Act thresholds", ["SPD", "EOD", "0.1", "0.05", "EU AI Act", "threshold"]),
    ("Detection pipeline", ["baseline", "group-wise", "intersectional", "sensitive attribute"]),
    ("Toolkits: AI Fairness 360, Fairlearn, Aequitas", ["fairness 360", "fairlearn", "aequitas", "toolkit"]),
    ("Reweighting for fairness", ["reweight", "reweighting"]),
    ("SMOTE and data augmentation", ["SMOTE", "ADASYN", "ROS", "oversampling", "augmentation"]),
    ("Model selection matters", ["XGBoost", "model selection", "random forest", "logistic regression"]),
    ("Adversarial debiasing", ["adversarial", "debiasing"]),
    ("Post-processing threshold adjustment", ["threshold adjustment", "post-processing", "postprocessing"]),
    ("Human-in-the-loop", ["human-in-the-loop", "human in the loop", "Article 10"]),
    ("Audit frameworks", ["audit", "pre-deployment", "monitoring", "stakeholder"]),
    ("Legal compliance: NYC LL 144, EU AI Act", ["NYC", "Local Law 144", "EU AI Act", "conformity"]),
    ("Audit gaps", ["intersectional", "one-shot", "affected community", "socio-technical"]),
]


def _load_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def _check_coverage(text: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """Return (covered, list of matched keywords)."""
    text_lower = text.lower()
    matched = [k for k in keywords if k.lower() in text_lower]
    return len(matched) > 0, matched


def run_gap_check() -> dict:
    """
    Compare paper + research findings against how_biases_are_introduced.pdf topics.
    Returns gap report.
    """
    paper_path = os.path.join(OUTPUT_DIR, "paper", "paper.tex")
    if not os.path.exists(paper_path):
        paper_path = os.path.join(OUTPUT_DIR, "paper_draft.md")
    research_path = os.path.join(OUTPUT_DIR, "research_findings.json")

    paper_text = _load_text(paper_path)
    research_text = ""
    if os.path.exists(research_path):
        with open(research_path, encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("results", []):
            research_text += r.get("summary", "") + " "
            research_text += r.get("query", "") + " "

    combined = (paper_text + " " + research_text).lower()

    report = {
        "source": "how_biases_are_introduced.pdf (via RESEARCH_CHECKLIST)",
        "covered": [],
        "gaps": [],
        "summary": "",
    }

    for topic, keywords in TOPICS_FROM_HOW_BIASES:
        covered, matched = _check_coverage(combined, keywords)
        if covered:
            report["covered"].append({"topic": topic, "matched": matched})
        else:
            report["gaps"].append({"topic": topic, "suggested_keywords": keywords})

    n_total = len(TOPICS_FROM_HOW_BIASES)
    n_covered = len(report["covered"])
    report["summary"] = f"{n_covered}/{n_total} topics covered. {len(report['gaps'])} gaps."

    out_path = os.path.join(OUTPUT_DIR, "gap_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {out_path}")

    # Write gap sections into the paper so agents' findings are reflected
    if report["gaps"]:
        _write_gaps_section(report)
        _recompile_paper_with_gaps()

    return report


def _write_gaps_section(report: dict) -> None:
    """Generate a paper section for each identified gap. Saved to paper_sections/07_gaps.tex."""
    sections_dir = os.path.join(OUTPUT_DIR, "paper_sections")
    os.makedirs(sections_dir, exist_ok=True)

    lines = [
        "\\section{Identified Research Gaps}",
        "\\label{sec:gaps}",
        "",
        "The following topics from our reference literature (how\\_biases\\_are\\_introduced.pdf) "
        "are not yet fully covered in this paper. Future work should address these gaps.",
        "",
    ]
    for i, g in enumerate(report["gaps"], 1):
        topic = g.get("topic", "Unknown").replace("_", r"\_")
        keywords = g.get("suggested_keywords", [])
        lines.extend([
            f"\\subsection{{{topic}}}",
            "",
            f"Relevant concepts to incorporate include: "
            + ", ".join(f"``{k}''" for k in keywords[:5]) + ".",
            "",
            _gap_section_content(topic, keywords).replace("_", r"\_").replace("%", r"\%"),
            "",
        ])

    lines.append(
        "These gaps were identified by automated comparison against the research checklist. "
        "Addressing them would strengthen the paper's alignment with the broader fairness-in-AI literature."
    )
    path = os.path.join(sections_dir, "07_gaps.tex")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Wrote gap section: {path}")


def _gap_section_content(topic: str, keywords: list[str]) -> str:
    """Return 1–2 sentences of suggested content for each known gap type."""
    topic_lower = topic.lower()
    if "toolkit" in topic_lower or "fairness 360" in topic_lower or "fairlearn" in topic_lower:
        return (
            "Established toolkits such as AI Fairness 360 (IBM), Fairlearn (Microsoft), and Aequitas "
            "(University of Chicago) provide implementations of fairness metrics and mitigation algorithms. "
            "Our experiments use Fairlearn for EOD-targeted post-processing; a comparative survey of toolkits "
            "would help practitioners choose appropriate frameworks for EU AI Act compliance."
        )
    if "human" in topic_lower or "article 10" in topic_lower:
        return (
            "The EU AI Act Article 10 requires human oversight of high-risk AI systems. Human-in-the-loop "
            "designs—where human reviewers can override or correct automated decisions—complement technical "
            "fairness metrics. Future work should integrate HITL requirements into the bias-audit framework."
        )
    return (
        f"Future revisions should expand coverage of {topic} with supporting citations from the literature."
    )


def _recompile_paper_with_gaps() -> None:
    """Reassemble paper.tex and regenerate PDF to include the new gaps section."""
    try:
        from agents.auditing_agent import assemble_paper_tex
        assemble_paper_tex()
        print("  Reassembled paper.tex with gap sections.")
        # Regenerate PDF so it matches the updated paper
        try:
            from utils.latex_generator import compile_latex
            ok, msg = compile_latex()
            if ok:
                print(f"  PDF regenerated: {msg}")
            else:
                print(f"  PDF regeneration: {msg}")
        except ImportError:
            pass
    except ImportError:
        pass


def format_gap_report(report: dict) -> str:
    """Format for console output."""
    lines = [
        "=" * 60,
        "  Gap Check — vs how_biases_are_introduced.pdf",
        "=" * 60,
        report["summary"],
        "",
        "Covered:",
    ]
    for c in report["covered"]:
        lines.append(f"  ✓ {c['topic']}")
        lines.append(f"    (matched: {', '.join(c['matched'][:3])}...)")
    lines.append("")
    lines.append("Gaps (not covered):")
    for g in report["gaps"]:
        lines.append(f"  ✗ {g['topic']}")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("  Gap Check Agent")
    print("  Comparing paper + research vs how_biases_are_introduced.pdf")
    print("=" * 60)
    report = run_gap_check()
    print(format_gap_report(report))

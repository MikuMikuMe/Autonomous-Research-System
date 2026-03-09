"""
Query Generator — Dynamically generates research and citation queries
from pipeline outputs (paper.tex, baseline/mitigation results, gap report).

3-tier fallback: LLM (Gemini) → rule-based extraction → hardcoded defaults.
"""

import json
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
PAPER_DIR = os.path.join(OUTPUT_DIR, "paper")

# Hardcoded defaults (original static queries) — ultimate fallback
DEFAULT_RESEARCH_QUERIES = [
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

DEFAULT_CITATION_QUERIES = [
    "bias mitigation financial AI credit scoring",
    "EU AI Act fairness thresholds algorithmic",
    "equalized odds demographic parity fraud detection",
    "SMOTE fairness imbalanced classification",
    "disparate impact machine learning",
    "bias auditing lifecycle AI systems",
    "threshold adjustment post-processing fairness",
    "ExponentiatedGradient Fairlearn fairness",
]


def _load_context() -> dict:
    """Load available pipeline outputs for query generation."""
    ctx = {
        "paper_summary": "",
        "results_summary": "",
        "gaps_summary": "",
    }

    # Paper: extract abstract and section headings
    paper_path = os.path.join(PAPER_DIR, "paper.tex")
    if os.path.exists(paper_path):
        try:
            with open(paper_path, encoding="utf-8") as f:
                tex = f.read()
            parts = []
            # Extract abstract
            abs_match = re.search(
                r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL
            )
            if abs_match:
                parts.append("Abstract: " + abs_match.group(1).strip()[:2000])
            # Extract section headings
            sections = re.findall(r"\\(?:sub)*section\{([^}]+)\}", tex)
            if sections:
                parts.append("Sections: " + "; ".join(sections))
            ctx["paper_summary"] = "\n".join(parts) if parts else ""
        except Exception:
            pass

    # Baseline results
    baseline_path = os.path.join(OUTPUT_DIR, "baseline_results.json")
    mitigation_path = os.path.join(OUTPUT_DIR, "mitigation_results.json")
    results_parts = []

    if os.path.exists(baseline_path):
        try:
            with open(baseline_path, encoding="utf-8") as f:
                baseline = json.load(f)
            for m in baseline.get("baseline_metrics", []):
                violations = []
                if m.get("eu_ai_act_spd_violation"):
                    violations.append(f"SPD={m.get('demographic_parity_diff', '?'):.4f}")
                if m.get("eu_ai_act_eod_violation"):
                    violations.append(f"EOD={m.get('equalized_odds_diff', '?'):.4f}")
                status = f"violations: {', '.join(violations)}" if violations else "compliant"
                results_parts.append(
                    f"Baseline {m['model']}: acc={m.get('accuracy', 0):.3f}, "
                    f"DPD={m.get('demographic_parity_diff', 0):.4f}, "
                    f"EOD={m.get('equalized_odds_diff', 0):.4f}, "
                    f"DI={m.get('disparate_impact_ratio', 0):.4f} ({status})"
                )
        except Exception:
            pass

    if os.path.exists(mitigation_path):
        try:
            with open(mitigation_path, encoding="utf-8") as f:
                mitigation = json.load(f)
            for m in mitigation.get("mitigation_metrics", []):
                results_parts.append(
                    f"Mitigated {m['model']}: acc={m.get('accuracy', 0):.3f}, "
                    f"DPD={m.get('demographic_parity_diff', 0):.4f}, "
                    f"EOD={m.get('equalized_odds_diff', 0):.4f}, "
                    f"DI={m.get('disparate_impact_ratio', 0):.4f}"
                )
        except Exception:
            pass

    ctx["results_summary"] = "\n".join(results_parts) if results_parts else "No experimental results available yet."

    # Gap report
    gap_path = os.path.join(OUTPUT_DIR, "gap_report.json")
    if os.path.exists(gap_path):
        try:
            with open(gap_path, encoding="utf-8") as f:
                gaps = json.load(f)
            gap_items = []
            for g in gaps.get("gaps", []):
                topic = g.get("topic", "")
                kws = g.get("suggested_keywords", [])
                gap_items.append(f"- {topic}" + (f" (keywords: {', '.join(kws)})" if kws else ""))
            ctx["gaps_summary"] = "\n".join(gap_items) if gap_items else "No gaps identified."
        except Exception:
            pass

    if not ctx["gaps_summary"]:
        ctx["gaps_summary"] = "No gap report available yet."

    return ctx


def _generate_via_llm(ctx: dict, max_research: int, max_citation: int) -> dict | None:
    """Try LLM-based query generation. Returns dict with research_queries and citation_queries, or None."""
    # Skip if no meaningful context
    if not ctx["paper_summary"] and ctx["results_summary"] == "No experimental results available yet.":
        return None

    try:
        from utils.config_loader import load_prompt
        from utils.llm_client import generate_json
    except ImportError:
        return None

    prompt = load_prompt(
        "research_queries",
        paper_summary=ctx["paper_summary"] or "Not available yet.",
        results_summary=ctx["results_summary"],
        gaps_summary=ctx["gaps_summary"],
        max_research=max_research,
        max_citation=max_citation,
    )
    if not prompt:
        return None

    result = generate_json(prompt)
    if not result:
        return None

    research = result.get("research_queries", [])
    citation = result.get("citation_queries", [])

    if not isinstance(research, list) or not isinstance(citation, list):
        return None

    # Filter out non-string or empty entries
    research = [q for q in research if isinstance(q, str) and q.strip()][:max_research]
    citation = [q for q in citation if isinstance(q, str) and q.strip()][:max_citation]

    if not research and not citation:
        return None

    return {"research_queries": research, "citation_queries": citation}


def _generate_rule_based(ctx: dict, max_research: int, max_citation: int) -> dict:
    """Rule-based query generation from structured pipeline data."""
    research_queries = []
    citation_queries = []

    # From baseline results: queries about models with violations
    baseline_path = os.path.join(OUTPUT_DIR, "baseline_results.json")
    if os.path.exists(baseline_path):
        try:
            with open(baseline_path, encoding="utf-8") as f:
                baseline = json.load(f)
            for m in baseline.get("baseline_metrics", []):
                model = m.get("model", "")
                if m.get("eu_ai_act_spd_violation") or m.get("eu_ai_act_eod_violation"):
                    research_queries.append(
                        f"How does {model} exhibit fairness violations in fraud detection "
                        f"under EU AI Act thresholds (SPD ≤ 0.1, EOD ≤ 0.05)?"
                    )
                    citation_queries.append(f"{model} fairness bias fraud detection")
        except Exception:
            pass

    # From mitigation results: queries about techniques used
    mitigation_path = os.path.join(OUTPUT_DIR, "mitigation_results.json")
    if os.path.exists(mitigation_path):
        try:
            with open(mitigation_path, encoding="utf-8") as f:
                mitigation = json.load(f)
            models_seen = set()
            for m in mitigation.get("mitigation_metrics", []):
                model = m.get("model", "")
                if model in models_seen:
                    continue
                models_seen.add(model)
                # Extract technique name from model string (e.g. "XGBoost+SMOTE" -> "SMOTE")
                technique = model.split("+")[-1] if "+" in model else ""
                if technique:
                    research_queries.append(
                        f"{technique} effectiveness for bias mitigation in financial AI: "
                        f"accuracy-fairness trade-off and EU AI Act compliance"
                    )
                    citation_queries.append(f"{technique} fairness bias mitigation")
        except Exception:
            pass

    # From gap report: queries for uncovered topics
    gap_path = os.path.join(OUTPUT_DIR, "gap_report.json")
    if os.path.exists(gap_path):
        try:
            with open(gap_path, encoding="utf-8") as f:
                gaps = json.load(f)
            for g in gaps.get("gaps", []):
                topic = g.get("topic", "")
                if topic:
                    research_queries.append(
                        f"Recent papers (2022-2025) on: {topic}. "
                        f"Focus on financial AI, credit scoring, or fraud detection if relevant."
                    )
                for kw in g.get("suggested_keywords", []):
                    if kw:
                        citation_queries.append(kw)
        except Exception:
            pass

    # From paper.tex: queries based on section headings
    paper_path = os.path.join(PAPER_DIR, "paper.tex")
    if os.path.exists(paper_path):
        try:
            with open(paper_path, encoding="utf-8") as f:
                tex = f.read()
            sections = re.findall(r"\\section\{([^}]+)\}", tex)
            for sec in sections:
                sec_clean = sec.strip()
                if sec_clean.lower() not in {"introduction", "conclusion", "references", "appendix"}:
                    citation_queries.append(f"{sec_clean} financial AI")
        except Exception:
            pass

    return {
        "research_queries": research_queries[:max_research],
        "citation_queries": citation_queries[:max_citation],
    }


def generate_research_queries(max_queries: int = 10) -> list[str]:
    """Generate research queries for the research agent.

    Tries LLM-based generation, then rule-based, then hardcoded defaults.
    """
    ctx = _load_context()

    # Tier 1: LLM
    llm_result = _generate_via_llm(ctx, max_research=max_queries, max_citation=8)
    if llm_result and llm_result.get("research_queries"):
        print(f"  [QueryGen] Generated {len(llm_result['research_queries'])} research queries via LLM")
        return llm_result["research_queries"]

    # Tier 2: Rule-based
    rule_result = _generate_rule_based(ctx, max_research=max_queries, max_citation=8)
    if rule_result.get("research_queries"):
        print(f"  [QueryGen] Generated {len(rule_result['research_queries'])} research queries via rules")
        return rule_result["research_queries"]

    # Tier 3: Hardcoded defaults
    print("  [QueryGen] Using default hardcoded research queries")
    return DEFAULT_RESEARCH_QUERIES[:max_queries]


def generate_citation_queries(max_queries: int = 8) -> list[str]:
    """Generate citation queries for Semantic Scholar search.

    Tries LLM-based generation, then rule-based, then hardcoded defaults.
    """
    ctx = _load_context()

    # Tier 1: LLM
    llm_result = _generate_via_llm(ctx, max_research=10, max_citation=max_queries)
    if llm_result and llm_result.get("citation_queries"):
        print(f"  [QueryGen] Generated {len(llm_result['citation_queries'])} citation queries via LLM")
        return llm_result["citation_queries"]

    # Tier 2: Rule-based
    rule_result = _generate_rule_based(ctx, max_research=10, max_citation=max_queries)
    if rule_result.get("citation_queries"):
        print(f"  [QueryGen] Generated {len(rule_result['citation_queries'])} citation queries via rules")
        return rule_result["citation_queries"]

    # Tier 3: Hardcoded defaults
    print("  [QueryGen] Using default hardcoded citation queries")
    return DEFAULT_CITATION_QUERIES[:max_queries]

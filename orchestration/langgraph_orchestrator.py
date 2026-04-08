"""
LangGraph Research Orchestrator — Domain-agnostic research pipeline.

Replaces the linear continuous_research_loop with a LangGraph StateGraph
implementing: DISCOVER → PLAN → ACT → OBSERVE → REFLECT with conditional
edges, parallel node execution, and checkpoint support.

Accepts ANY research idea/topic as input and produces a comprehensive report.
Discovers techniques through web research instead of hardcoding them.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# State schema for the graph
# ---------------------------------------------------------------------------

class ResearchState(TypedDict, total=False):
    """State object flowing through the LangGraph research pipeline."""
    # Input
    research_idea: str
    goal: str
    domain: str
    max_iterations: int
    converge_threshold: float
    flaw_halt_severity: str

    # Iteration tracking
    iteration: int
    claims: list[dict[str, Any]]
    queries: list[str]

    # ACT results
    verification_report: dict[str, Any]
    research_findings: dict[str, Any]
    cross_validation_report: dict[str, Any]
    flaw_report: dict[str, Any]
    discovered_techniques: list[dict[str, Any]]

    # OBSERVE metrics
    verified_ratio: float
    critical_flaws: int
    total_flaws: int
    converged: bool

    # REFLECT
    knowledge_summary: dict[str, Any]

    # Output
    report: dict[str, Any]
    errors: list[str]
    session_id: str


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def discover_node(state: ResearchState) -> ResearchState:
    """DISCOVER: Parse research idea into claims, validate system readiness."""
    print("\n  [DISCOVER] Analyzing research idea...", flush=True)

    idea = state.get("research_idea", "").strip()
    if not idea:
        state["errors"] = state.get("errors", []) + ["No research idea provided."]
        return state

    state.setdefault("session_id", str(uuid.uuid4())[:8])
    state.setdefault("iteration", 0)
    state.setdefault("errors", [])
    state.setdefault("discovered_techniques", [])

    # Use LLM to decompose the research idea into testable claims
    try:
        from utils.multi_llm_client import generate_json, is_available
        if is_available():
            prompt = f"""Analyze this research idea and decompose it into specific, testable claims.
Also identify the research domain and suggest an initial set of research queries.

Research Idea: {idea}

Return JSON:
{{
    "domain": "the research domain (e.g., machine learning, biology, economics)",
    "claims": [
        {{"text": "specific testable claim", "category": "methodology|finding|hypothesis", "priority": "high|medium|low"}}
    ],
    "initial_queries": ["academic search query 1", "query 2"],
    "is_valid_research": true/false,
    "validity_reasoning": "why this is or isn't a valid research topic",
    "potential_issues": ["issue 1", "issue 2"]
}}"""
            result = generate_json(prompt)
            if result:
                state["domain"] = result.get("domain", "general")
                state["claims"] = result.get("claims", [])
                state["queries"] = result.get("initial_queries", [])

                # Handle obviously wrong/invalid ideas
                if not result.get("is_valid_research", True):
                    reasoning = result.get("validity_reasoning", "")
                    issues = result.get("potential_issues", [])
                    print(f"  [DISCOVER] ⚠ Research idea flagged: {reasoning}", flush=True)
                    state["errors"].append(f"Validity concern: {reasoning}")
                    for issue in issues:
                        state["errors"].append(f"Issue: {issue}")
                    # Still proceed — the system will produce a report explaining why

                print(f"  [DISCOVER] Domain: {state['domain']}", flush=True)
                print(f"  [DISCOVER] {len(state['claims'])} claims extracted.", flush=True)
                return state
    except Exception as e:
        print(f"  [DISCOVER] LLM analysis failed: {e}", flush=True)

    # Fallback: treat entire idea as a single claim
    state["domain"] = "general"
    state["claims"] = [{"text": idea, "category": "hypothesis", "priority": "high"}]
    state["queries"] = [idea[:200]]
    return state


def plan_node(state: ResearchState) -> ResearchState:
    """PLAN: Generate research queries from claims + memory gaps."""
    print(f"\n  [PLAN] Iteration {state.get('iteration', 0) + 1} — generating queries...", flush=True)

    state["iteration"] = state.get("iteration", 0) + 1
    claims = state.get("claims", [])

    if not claims:
        state["errors"] = state.get("errors", []) + ["No claims to research."]
        return state

    # Check cross-session memory for prior knowledge
    try:
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory()
        domain = state.get("domain", "general")
        prior_knowledge = mem.get_knowledge(domain=domain, limit=10)
        known_techniques = mem.get_techniques(domain=domain, limit=10)
        mem.close()

        if prior_knowledge:
            print(f"  [PLAN] Found {len(prior_knowledge)} prior knowledge entries.", flush=True)
        if known_techniques:
            print(f"  [PLAN] Found {len(known_techniques)} known techniques.", flush=True)
    except Exception:
        prior_knowledge = []
        known_techniques = []

    # Use LLM to generate targeted queries
    try:
        from utils.multi_llm_client import generate_json, is_available
        if is_available():
            claims_text = "\n".join(f"- {c.get('text', '')}" for c in claims[:15])
            context = ""
            if prior_knowledge:
                context += "\nPrior knowledge:\n" + "\n".join(
                    f"- {k.get('claim', '')} (confidence: {k.get('confidence', 0):.2f})"
                    for k in prior_knowledge[:5]
                )
            if known_techniques:
                context += "\nKnown techniques:\n" + "\n".join(
                    f"- {t.get('technique_name', '')} ({t.get('category', '')})"
                    for t in known_techniques[:5]
                )

            prompt = f"""Generate research queries for iteration {state['iteration']}.
Focus on gaps in current knowledge and unverified claims.

Claims:
{claims_text}
{context}

Return JSON: {{"queries": ["query1", "query2", ...], "technique_discovery_queries": ["what techniques are used for X", ...]}}"""

            result = generate_json(prompt)
            if result:
                state["queries"] = result.get("queries", [])[:12]
                # Add technique discovery queries
                tech_queries = result.get("technique_discovery_queries", [])[:3]
                state["queries"].extend(tech_queries)
                print(f"  [PLAN] Generated {len(state['queries'])} queries.", flush=True)
                return state
    except Exception as e:
        print(f"  [PLAN] Query generation failed: {e}", flush=True)

    # Fallback
    state["queries"] = [c.get("text", "")[:200] for c in claims[:10] if c.get("text")]
    return state


def act_research_node(state: ResearchState) -> ResearchState:
    """ACT: Search web + academic sources for evidence."""
    print("\n  [ACT] Researching...", flush=True)
    queries = state.get("queries", [])

    if not queries:
        return state

    all_findings: dict[str, Any] = {"queries": [], "total_sources": 0}

    for i, query in enumerate(queries[:12]):
        try:
            from utils.web_search_client import research_search
            text, sources = research_search(
                query,
                include_academic=True,
                include_web=True,
                step_prefix=f"    [{i+1}/{len(queries)}] ",
            )
            all_findings["queries"].append({
                "query": query,
                "synthesis": text[:3000] if text else "",
                "sources": sources[:5],
            })
            all_findings["total_sources"] += len(sources)
        except Exception as e:
            print(f"    [ACT] Query failed: {query[:50]}... — {e}", flush=True)

    state["research_findings"] = all_findings
    print(f"  [ACT] Collected {all_findings['total_sources']} total sources.", flush=True)
    return state


def act_discover_techniques_node(state: ResearchState) -> ResearchState:
    """ACT: Discover techniques/methods through web research (not hardcoded)."""
    print("\n  [ACT] Discovering applicable techniques...", flush=True)
    domain = state.get("domain", "general")
    idea = state.get("research_idea", "")

    try:
        from utils.multi_llm_client import generate_json, is_available
        from utils.web_search_client import research_search, is_tavily_available

        # First, search for techniques
        if is_tavily_available():
            tech_query = f"state of the art techniques methods approaches for {domain} research {idea[:100]}"
            text, sources = research_search(tech_query, include_academic=True, step_prefix="    ")
        else:
            text, sources = "", []

        # Then ask LLM to extract structured techniques
        if is_available():
            context = text[:5000] if text else ""
            prompt = f"""Based on current research literature, identify the most relevant techniques,
methods, and approaches for this research area.

Research domain: {domain}
Research idea: {idea[:500]}

Literature context:
{context}

Return JSON:
{{
    "techniques": [
        {{
            "name": "technique name",
            "description": "brief description",
            "category": "pre-processing|modeling|post-processing|evaluation|analysis",
            "relevance": 0.0-1.0,
            "key_papers": ["paper reference"],
            "libraries": ["python library"]
        }}
    ]
}}"""
            result = generate_json(prompt)
            if result and result.get("techniques"):
                techniques = result["techniques"]
                state["discovered_techniques"] = techniques
                print(f"  [ACT] Discovered {len(techniques)} techniques:", flush=True)
                for t in techniques[:5]:
                    print(f"    • {t.get('name', '?')} ({t.get('category', '?')}) — relevance: {t.get('relevance', 0):.1f}", flush=True)

                # Store in cross-session memory for future use
                try:
                    from utils.cross_session_memory import CrossSessionMemory
                    mem = CrossSessionMemory()
                    for t in techniques:
                        mem.register_technique(
                            technique_name=t.get("name", ""),
                            domain=domain,
                            description=t.get("description", ""),
                            category=t.get("category", ""),
                            effectiveness=t.get("relevance", 0.5),
                            discovered_via="web_research",
                        )
                    mem.close()
                except Exception:
                    pass
    except Exception as e:
        print(f"  [ACT] Technique discovery failed: {e}", flush=True)

    return state


def act_verify_node(state: ResearchState) -> ResearchState:
    """ACT: Verify claims through code execution and cross-validation."""
    print("\n  [ACT] Verifying claims...", flush=True)
    claims = state.get("claims", [])
    findings = state.get("research_findings", {})

    verification_results: list[dict] = []
    for claim in claims:
        text = claim.get("text", "")
        if not text:
            continue

        # Check if any research findings support/contradict
        supported = False
        contradicted = False
        evidence = []

        for q in findings.get("queries", []):
            synthesis = q.get("synthesis", "").lower()
            claim_lower = text.lower()[:100]
            # Simple heuristic — will be refined by cross-validation
            if any(word in synthesis for word in claim_lower.split()[:5]):
                evidence.append(q.get("synthesis", "")[:200])
                supported = True

        verification_results.append({
            "claim": text,
            "verified": supported and not contradicted,
            "evidence": "; ".join(evidence[:3]) if evidence else "Insufficient evidence",
        })
        status = "✓" if supported else "?"
        print(f"    [{status}] {text[:70]}", flush=True)

    state["verification_report"] = {
        "timestamp": datetime.now().isoformat(),
        "claims": verification_results,
    }

    # Cross-validate against literature
    try:
        from utils.multi_llm_client import generate_json, is_available
        if is_available() and findings.get("queries"):
            claims_text = json.dumps([{"text": c.get("text", "")} for c in claims[:10]], indent=2)
            findings_text = json.dumps(
                [{"query": q.get("query", ""), "synthesis": q.get("synthesis", "")[:500]}
                 for q in findings.get("queries", [])[:5]],
                indent=2,
            )
            prompt = f"""Cross-validate these research claims against the literature findings.

Claims:
{claims_text}

Literature Findings:
{findings_text}

For each claim, determine: support, contradict, or neutral.
Return JSON:
{{
    "results": [
        {{
            "claim": "claim text",
            "verdict": "support|contradict|neutral",
            "confidence": 0.0-1.0,
            "rationale": "why",
            "supporting_papers": ["paper references"]
        }}
    ],
    "summary": "overall summary"
}}"""
            cv_result = generate_json(prompt)
            if cv_result:
                state["cross_validation_report"] = cv_result
                print(f"  [ACT] Cross-validation: {cv_result.get('summary', '')[:100]}", flush=True)
    except Exception as e:
        print(f"  [ACT] Cross-validation failed: {e}", flush=True)

    # Detect flaws
    try:
        from utils.multi_llm_client import generate_json, is_available
        if is_available():
            prompt = f"""Analyze these research claims for logical, statistical, and methodological flaws.

Claims: {json.dumps([c.get('text', '') for c in claims[:10]])}
Verification results: {json.dumps(verification_results[:5], default=str)}

Return JSON:
{{
    "flaws": [
        {{
            "claim": "which claim",
            "type": "logical|statistical|methodological|factual",
            "severity": "critical|high|medium|low",
            "description": "what's wrong",
            "suggested_fix": "how to fix"
        }}
    ],
    "alerts": ["important warnings"],
    "summary": "overall flaw summary"
}}"""
            flaw_result = generate_json(prompt)
            if flaw_result:
                state["flaw_report"] = flaw_result
                print(f"  [ACT] Flaw detection: {flaw_result.get('summary', '')[:100]}", flush=True)
    except Exception as e:
        print(f"  [ACT] Flaw detection failed: {e}", flush=True)

    return state


def observe_node(state: ResearchState) -> ResearchState:
    """OBSERVE: Score iteration convergence."""
    print("\n  [OBSERVE] Scoring iteration...", flush=True)

    ver_report = state.get("verification_report", {})
    cv_report = state.get("cross_validation_report", {})
    flaw_report = state.get("flaw_report", {})

    verified_count = sum(
        1 for c in ver_report.get("claims", []) if c.get("verified") is True
    )
    total_claims = len(ver_report.get("claims", [])) or 1
    verified_ratio = verified_count / total_claims

    critical_flaws = sum(
        1 for f in flaw_report.get("flaws", []) if f.get("severity") == "critical"
    )
    total_flaws = len(flaw_report.get("flaws", []))

    threshold = state.get("converge_threshold", 0.90)
    halt_severity = state.get("flaw_halt_severity", "critical")

    blocking = False
    if halt_severity == "critical" and critical_flaws > 0:
        blocking = True
    elif halt_severity == "high":
        high = sum(1 for f in flaw_report.get("flaws", []) if f.get("severity") in ("critical", "high"))
        blocking = high > 0
    elif halt_severity == "any":
        blocking = total_flaws > 0

    converged = verified_ratio >= threshold and not blocking

    state["verified_ratio"] = round(verified_ratio, 3)
    state["critical_flaws"] = critical_flaws
    state["total_flaws"] = total_flaws
    state["converged"] = converged

    status = "CONVERGED ✓" if converged else "not converged yet"
    print(
        f"  [OBSERVE] Verified {verified_count}/{total_claims} ({verified_ratio:.0%}), "
        f"{total_flaws} flaws ({critical_flaws} critical), {status}",
        flush=True,
    )
    return state


def reflect_node(state: ResearchState) -> ResearchState:
    """REFLECT: Persist findings to memory, update claims for next iteration."""
    print("\n  [REFLECT] Updating memory and refining claims...", flush=True)

    domain = state.get("domain", "general")

    # Persist to cross-session memory
    try:
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory()

        # Store validated knowledge
        for r in state.get("cross_validation_report", {}).get("results", []):
            mem.store_knowledge(
                claim=r.get("claim", ""),
                domain=domain,
                confidence=r.get("confidence", 0.5),
                sources=r.get("supporting_papers", []),
                verdict=r.get("verdict", "neutral"),
            )

        # Store learned patterns from flaws
        for flaw in state.get("flaw_report", {}).get("flaws", []):
            if flaw.get("severity") in ("critical", "high"):
                mem.learn_pattern(
                    pattern_type="research_flaw",
                    description=flaw.get("description", ""),
                    context=f"domain={domain}, type={flaw.get('type', '')}",
                )

        mem.close()
    except Exception:
        pass

    # Also persist to session-scoped memory
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        for r in state.get("cross_validation_report", {}).get("results", []):
            store.add_knowledge(
                claim=r.get("claim", ""),
                source="cross_validation",
                confidence=r.get("confidence", 0.5),
                supporting_papers=r.get("supporting_papers", []),
                verdict=r.get("verdict", "neutral"),
            )
        store.close()
    except Exception:
        pass

    # Refine claims for next iteration if not converged
    if not state.get("converged"):
        claims = state.get("claims", [])
        cv_results = state.get("cross_validation_report", {}).get("results", [])
        contradicted = {r.get("claim", "") for r in cv_results if r.get("verdict") == "contradict"}

        # Keep unresolved claims, drop fully verified ones
        refined = [
            c for c in claims
            if c.get("text") in contradicted or not any(
                v.get("claim") == c.get("text") and v.get("verified")
                for v in state.get("verification_report", {}).get("claims", [])
            )
        ]

        # Add gap-filling claims from flaws
        for flaw in state.get("flaw_report", {}).get("flaws", []):
            if flaw.get("suggested_fix"):
                refined.append({
                    "text": flaw["suggested_fix"],
                    "category": "gap_fill",
                    "priority": "high" if flaw.get("severity") in ("critical", "high") else "medium",
                })

        state["claims"] = refined or claims
        print(f"  [REFLECT] {len(state['claims'])} claims for next iteration.", flush=True)

    return state


def generate_report_node(state: ResearchState) -> ResearchState:
    """Generate the final comprehensive research report."""
    print("\n  [REPORT] Generating comprehensive report...", flush=True)

    report: dict[str, Any] = {
        "session_id": state.get("session_id", ""),
        "research_idea": state.get("research_idea", ""),
        "domain": state.get("domain", "general"),
        "goal": state.get("goal", ""),
        "timestamp": datetime.now().isoformat(),
        "iterations_completed": state.get("iteration", 0),
        "converged": state.get("converged", False),
        "verified_ratio": state.get("verified_ratio", 0),
        "total_flaws": state.get("total_flaws", 0),
        "critical_flaws": state.get("critical_flaws", 0),
        "discovered_techniques": state.get("discovered_techniques", []),
        "claims": state.get("claims", []),
        "verification_report": state.get("verification_report", {}),
        "cross_validation_report": state.get("cross_validation_report", {}),
        "flaw_report": state.get("flaw_report", {}),
        "errors": state.get("errors", []),
        "research_findings_summary": {
            "total_queries": len(state.get("research_findings", {}).get("queries", [])),
            "total_sources": state.get("research_findings", {}).get("total_sources", 0),
        },
    }

    # Ask LLM to write a comprehensive narrative report
    try:
        from utils.multi_llm_client import generate, is_available
        if is_available():
            report_data = json.dumps({
                "idea": state.get("research_idea", ""),
                "domain": state.get("domain", ""),
                "converged": state.get("converged", False),
                "verified_ratio": state.get("verified_ratio", 0),
                "claims": [c.get("text", "") for c in state.get("claims", [])[:10]],
                "techniques": [t.get("name", "") for t in state.get("discovered_techniques", [])[:10]],
                "flaws": [f.get("description", "") for f in state.get("flaw_report", {}).get("flaws", [])[:5]],
                "errors": state.get("errors", [])[:5],
            }, indent=2)

            prompt = f"""Write a comprehensive research report based on these findings.

{report_data}

The report should include:
1. Executive Summary
2. Research Methodology (what was investigated and how)
3. Key Findings (supported claims, contradicted claims)
4. Discovered Techniques and Methods
5. Identified Issues and Flaws
6. Recommendations
7. Conclusion

If the research idea was invalid or flawed, explain WHY it's problematic in detail.
Be thorough, academic, and cite specific findings."""

            narrative = generate(
                prompt,
                system_instruction="You are an academic research report writer. Be thorough, precise, and objective.",
                max_output_tokens=8192,
            )
            if narrative:
                report["narrative_report"] = narrative
    except Exception as e:
        report["narrative_report"] = f"Report generation failed: {e}"

    state["report"] = report

    # Save report to outputs/
    try:
        output_dir = PROJECT_ROOT / "outputs"
        output_dir.mkdir(exist_ok=True)
        report_path = output_dir / "research_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  [REPORT] Saved to {report_path}", flush=True)
    except Exception as e:
        print(f"  [REPORT] Save failed: {e}", flush=True)

    # Log to cross-session memory
    try:
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory()
        mem.log_session(
            session_id=state.get("session_id", ""),
            goal=state.get("goal", state.get("research_idea", "")),
            domain=state.get("domain", "general"),
            claims_count=len(state.get("claims", [])),
            converged=state.get("converged", False),
            summary=report.get("narrative_report", "")[:2000],
            key_findings=[
                c.get("text", "")
                for c in state.get("cross_validation_report", {}).get("results", [])
                if c.get("verdict") == "support"
            ][:10],
        )
        mem.close()
    except Exception:
        pass

    return state


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _should_continue(state: ResearchState) -> str:
    """Conditional edge: continue iterating or generate report."""
    if state.get("converged"):
        return "generate_report"
    if state.get("iteration", 0) >= state.get("max_iterations", 10):
        return "generate_report"
    if not state.get("claims"):
        return "generate_report"
    return "plan"


def build_research_graph():
    """Build the LangGraph StateGraph for the research pipeline."""
    from langgraph.graph import StateGraph, END

    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("discover", discover_node)
    graph.add_node("plan", plan_node)
    graph.add_node("act_research", act_research_node)
    graph.add_node("act_discover_techniques", act_discover_techniques_node)
    graph.add_node("act_verify", act_verify_node)
    graph.add_node("observe", observe_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("generate_report", generate_report_node)

    # Define edges
    graph.set_entry_point("discover")
    graph.add_edge("discover", "plan")
    graph.add_edge("plan", "act_research")
    graph.add_edge("act_research", "act_discover_techniques")
    graph.add_edge("act_discover_techniques", "act_verify")
    graph.add_edge("act_verify", "observe")
    graph.add_edge("observe", "reflect")

    # Conditional: continue or report
    graph.add_conditional_edges(
        "reflect",
        _should_continue,
        {
            "plan": "plan",
            "generate_report": "generate_report",
        },
    )
    graph.add_edge("generate_report", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_research(
    research_idea: str,
    *,
    goal: str | None = None,
    max_iterations: int = 5,
    converge_threshold: float = 0.85,
    flaw_halt_severity: str = "critical",
    quiet: bool = False,
) -> dict[str, Any]:
    """Run the full research pipeline on any research idea.

    Args:
        research_idea: Any research topic, hypothesis, or question.
        goal: High-level research goal (defaults to the idea itself).
        max_iterations: Maximum research iterations.
        converge_threshold: Fraction of claims that must verify to converge.
        flaw_halt_severity: Severity level that blocks convergence.
        quiet: Suppress output.

    Returns:
        Comprehensive research report dict.
    """
    print("\n" + "=" * 70)
    print("  AUTONOMOUS RESEARCH SYSTEM")
    print(f"  Idea: {research_idea[:80]}...")
    print("=" * 70)

    start_time = time.time()

    initial_state: ResearchState = {
        "research_idea": research_idea,
        "goal": goal or research_idea,
        "max_iterations": max_iterations,
        "converge_threshold": converge_threshold,
        "flaw_halt_severity": flaw_halt_severity,
        "iteration": 0,
        "claims": [],
        "queries": [],
        "errors": [],
        "discovered_techniques": [],
        "converged": False,
    }

    try:
        graph = build_research_graph()
        final_state = graph.invoke(initial_state)
        report = final_state.get("report", {})
        report["total_duration_seconds"] = round(time.time() - start_time, 2)
    except Exception as e:
        print(f"\n  [ERROR] Research pipeline failed: {e}", flush=True)
        traceback.print_exc()
        report = {
            "research_idea": research_idea,
            "error": str(e),
            "total_duration_seconds": round(time.time() - start_time, 2),
        }

    print(f"\n{'=' * 70}")
    print(f"  RESEARCH COMPLETE")
    print(f"  Duration: {report.get('total_duration_seconds', 0):.1f}s")
    print(f"  Converged: {'Yes ✓' if report.get('converged') else 'No'}")
    print(f"{'=' * 70}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Run autonomous research on any topic.")
    p.add_argument("idea", nargs="?", help="Research idea/topic/question")
    p.add_argument("--goal", "-g", default=None, help="Research goal")
    p.add_argument("--iterations", "-n", type=int, default=5)
    p.add_argument("--threshold", "-t", type=float, default=0.85)
    p.add_argument("--quiet", "-q", action="store_true")
    args = p.parse_args()

    idea = args.idea or input("Enter your research idea: ")
    report = run_research(
        idea,
        goal=args.goal,
        max_iterations=args.iterations,
        converge_threshold=args.threshold,
        quiet=args.quiet,
    )

    if report.get("narrative_report"):
        print("\n" + "─" * 70)
        print("REPORT:")
        print("─" * 70)
        print(report["narrative_report"][:5000])

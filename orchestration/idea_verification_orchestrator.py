"""
Idea Verification Orchestrator — DeerFlow-style iterative research idea validation.

Pipeline:
  1. Extract structured research idea (hypotheses, methods, keywords) from text + images
  2. Load accumulated memory insights from prior sessions
  3. LOOP (up to MAX_ITERATIONS):
       a. Generate targeted search queries (augmented by memory insights)
       b. Search arXiv + Semantic Scholar for each query
       c. Cross-validate each claim against retrieved literature
       d. Identify flaws, contradictions, and supporting evidence
       e. Store insights to SQLite memory
       f. Refine queries for the next iteration based on newly discovered gaps
  4. Synthesize final report: novelty score, flaws, similar papers, recommendations

Each run enriches the shared memory so future runs benefit from accumulated
knowledge (known pitfalls, effective methods, common contradictions in the domain).
"""

from __future__ import annotations

import json
import queue
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"
IDEA_DIR = OUTPUT_DIR / "idea_verification"

MAX_ITERATIONS = 3
MAX_PAPERS_PER_QUERY = 5
MAX_CLAIMS_PER_ITERATION = 5
MAX_QUERIES_PER_ITERATION = 8


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _log(message: str, bus: queue.Queue | None, session_id: str) -> None:
    print(f"  [IdeaVerify] {message}", flush=True)
    if bus is not None:
        try:
            bus.put({"type": "idea_log", "session_id": session_id, "line": message})
        except Exception:
            pass


def _emit(event: dict, bus: queue.Queue | None) -> None:
    if bus is not None:
        try:
            bus.put(event)
        except Exception:
            pass


def _generate_queries(
    idea: dict,
    memory_insights: list[str],
    iteration: int,
) -> list[str]:
    """Generate search queries from idea keywords/hypotheses and memory insights."""
    queries: list[str] = []
    domain = idea.get("domain", "")
    keywords = idea.get("keywords", [])
    hypotheses = idea.get("hypotheses", [])
    methods = idea.get("proposed_methods", [])

    # Base queries from idea content
    if methods:
        queries.append(f"{domain} {' '.join(methods[:2])} survey")
    if hypotheses:
        queries.append(hypotheses[0][:200])
    if keywords:
        queries.append(" ".join(keywords[:5]))

    # In later iterations, add queries from memory insights (known gaps/pitfalls)
    if iteration > 1:
        for insight in memory_insights[:2]:
            if insight and len(insight) > 10:
                queries.append(f"{domain} {insight[:100]}")

    # LLM-enhanced queries when available
    try:
        from utils.llm_client import generate, is_available
        if is_available():
            insight_block = ""
            if memory_insights:
                insight_block = (
                    "Memory insights to incorporate:\n"
                    + "\n".join(f"- {i}" for i in memory_insights[:3])
                    + "\n\n"
                )
            prompt = (
                f"Generate 3 specific arXiv/Semantic Scholar search queries to find "
                f"papers related to this research idea:\n\n"
                f"Title: {idea.get('title', '')}\n"
                f"Problem: {idea.get('problem_statement', '')[:300]}\n"
                f"Methods: {', '.join(methods[:3])}\n"
                f"Keywords: {', '.join(keywords[:5])}\n\n"
                f"{insight_block}"
                "Output ONLY 3 lines, each being a concise search query. "
                "No numbering, no explanation."
            )
            result = generate(prompt, max_output_tokens=256)
            if result:
                llm_queries = [q.strip() for q in result.strip().splitlines() if q.strip()][:3]
                queries.extend(llm_queries)
    except Exception:
        pass

    # Deduplicate and limit
    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        key = q.lower().strip()
        if q and key not in seen:
            seen.add(key)
            deduped.append(q)
    return deduped[:MAX_QUERIES_PER_ITERATION]


def _search_papers(
    query: str,
    session_id: str,
    bus: queue.Queue | None,
) -> tuple[str, list[dict]]:
    """Search arXiv + Semantic Scholar for a query. Returns (text, papers)."""
    try:
        from utils.research_client import fallback_research
        _log(f"Searching: {query[:80]}...", bus, session_id)
        text_result, papers = fallback_research(
            query,
            max_papers=MAX_PAPERS_PER_QUERY,
            download_pdfs=False,
            step_prefix="    ",
        )
        return text_result or "", papers or []
    except ImportError as e:
        _log(f"research_client unavailable: {e}", bus, session_id)
        return "", []
    except Exception as e:
        _log(f"Search failed for '{query[:50]}': {e}", bus, session_id)
        return "", []


def _cross_validate_claim(
    claim: str,
    literature_text: str,
    papers: list[dict],
    session_id: str,
    bus: queue.Queue | None,
) -> dict:
    """Cross-validate a single claim against retrieved literature using LLM."""
    result: dict = {
        "claim": claim,
        "status": "unverifiable",
        "evidence": "",
        "papers": [p.get("title", "") for p in papers[:3]],
        "flaws": [],
        "supporting": False,
        "contradicting": False,
    }
    try:
        from utils.llm_client import generate, is_available
        if not is_available():
            return result
        prompt = (
            "You are a research peer reviewer. Evaluate this research claim against the literature.\n\n"
            f"CLAIM: {claim}\n\n"
            f"LITERATURE:\n{literature_text[:3000]}\n\n"
            "Return a JSON object with exactly these keys:\n"
            '{"status": "supported|contradicted|novel|flawed|unverifiable", '
            '"evidence": "1-2 sentence explanation", '
            '"flaws": ["list of specific flaws or gaps, empty list if none"], '
            '"supporting": true_or_false, '
            '"contradicting": true_or_false}'
        )
        response = generate(prompt, max_output_tokens=512)
        if response:
            obj_match = re.search(r"\{[\s\S]*\}", response)
            if obj_match:
                parsed = json.loads(obj_match.group(0))
                for k in ("status", "evidence", "flaws", "supporting", "contradicting"):
                    if k in parsed:
                        result[k] = parsed[k]
    except Exception as e:
        _log(f"Cross-validation error: {e}", bus, session_id)
    return result


def _synthesize_final_report(
    idea: dict,
    all_iterations: list[dict],
    session_id: str,
    bus: queue.Queue | None,
) -> dict:
    """Synthesize the final verification report from all iteration results."""
    all_paper_titles: list[str] = []
    all_flaws: list[str] = []
    supported_claims: list[str] = []
    contradicted_claims: list[str] = []

    for it in all_iterations:
        for cv in it.get("claim_verifications", []):
            status = cv.get("status", "")
            if status == "supported":
                supported_claims.append(cv["claim"])
            elif status == "contradicted":
                contradicted_claims.append(cv["claim"])
            all_flaws.extend(cv.get("flaws", []))
            all_paper_titles.extend(cv.get("papers", []))

    # Deduplicate
    all_paper_titles = list(dict.fromkeys(all_paper_titles))[:10]
    all_flaws = list(dict.fromkeys(f for f in all_flaws if f))[:10]
    supported_claims = list(dict.fromkeys(supported_claims))[:5]
    contradicted_claims = list(dict.fromkeys(contradicted_claims))[:5]

    # Novelty score: 0 = fully known, 1 = completely novel
    total = len(supported_claims) + len(contradicted_claims)
    novelty_score = round(1.0 - (len(contradicted_claims) / total), 3) if total > 0 else 0.5

    # Verdict
    if len(all_flaws) > 2:
        verdict = "flawed"
    elif contradicted_claims:
        verdict = "contradicted"
    elif supported_claims:
        verdict = "supported"
    else:
        verdict = "novel"

    recommendations: list[str] = []
    if all_flaws:
        recommendations.append(
            f"Address {len(all_flaws)} identified flaw(s) before submission: "
            + "; ".join(all_flaws[:2])
        )
    if contradicted_claims:
        recommendations.append(
            f"Revise {len(contradicted_claims)} claim(s) that contradict existing literature."
        )
    if not supported_claims and not contradicted_claims:
        recommendations.append(
            "Add more specific, testable claims and experimental details to enable validation."
        )
    if novelty_score >= 0.7:
        recommendations.append(
            "The idea appears novel — include a thorough literature comparison in the paper."
        )

    # LLM synthesis of verdict text
    try:
        from utils.llm_client import generate, is_available
        if is_available():
            iter_summaries = "\n".join(
                f"Iteration {it['iteration']}: {it.get('summary', '')}"
                for it in all_iterations
            )
            prompt = (
                "Write a 3-sentence peer review verdict for this research idea:\n\n"
                f"Title: {idea.get('title', '')}\n"
                f"Supported claims: {supported_claims}\n"
                f"Contradicted claims: {contradicted_claims}\n"
                f"Identified flaws: {all_flaws}\n"
                f"Novelty score: {novelty_score:.2f}\n"
                f"Iteration summaries:\n{iter_summaries}"
            )
            verdict_text = generate(prompt, max_output_tokens=300)
            if verdict_text:
                recommendations.insert(0, verdict_text.strip())
    except Exception:
        pass

    return {
        "novelty_score": novelty_score,
        "similar_papers": all_paper_titles,
        "flaws": all_flaws,
        "supported_claims": supported_claims,
        "contradicted_claims": contradicted_claims,
        "recommendations": recommendations,
        "verdict": verdict,
    }


def _load_memory_insights(domain: str) -> list[str]:
    """Load relevant insights from memory for the given research domain."""
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        try:
            return store.get_idea_insights(domain, limit=10)
        finally:
            store.close()
    except Exception:
        return []


def _save_to_memory(
    session_id: str,
    idea: dict,
    iterations: list[dict],
    final_report: dict,
) -> None:
    """Persist this verification session to SQLite memory for future reference."""
    try:
        from agents.memory_agent import MemoryStore
        store = MemoryStore()
        try:
            store.store_idea_session(
                session_id=session_id,
                title=idea.get("title", ""),
                domain=idea.get("domain", ""),
                hypotheses=idea.get("hypotheses", []),
                methods=idea.get("proposed_methods", []),
                keywords=idea.get("keywords", []),
                final_report=final_report,
                iterations=iterations,
            )
        finally:
            store.close()
    except Exception as e:
        print(f"  [IdeaVerify] Memory save failed: {e}", flush=True)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_idea_verification(
    text: str,
    image_paths: list[str] | None = None,
    *,
    max_iterations: int = MAX_ITERATIONS,
    bus: queue.Queue | None = None,
    session_id: str | None = None,
) -> dict:
    """
    Run the iterative idea verification pipeline.

    Args:
        text: Research idea description text.
        image_paths: Paths to uploaded image files (diagrams, figures, etc.).
        max_iterations: Maximum number of search-verify-refine iterations.
        bus: Optional event queue; idea_log / idea_* events are pushed here.
        session_id: Optional session ID; generated if not supplied.

    Returns:
        Full verification results dict (idea, iterations, final_report).
    """
    IDEA_DIR.mkdir(parents=True, exist_ok=True)

    sid = session_id or f"idea_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _log("Starting idea verification...", bus, sid)

    # ------------------------------------------------------------------
    # Step 1: Extract structured idea
    # ------------------------------------------------------------------
    _emit(
        {
            "type": "idea_progress",
            "session_id": sid,
            "step": "extract",
            "progress": 0.05,
            "label": "Extracting research idea...",
        },
        bus,
    )
    from agents.idea_input_agent import extract_idea

    idea = extract_idea(text, image_paths, session_id=sid)
    if not session_id:
        sid = idea.get("session_id", sid)

    _log(f"Idea extracted: '{idea.get('title', 'Untitled')}'", bus, sid)
    _log(f"Domain: {idea.get('domain', 'unknown')}", bus, sid)
    _log(f"Hypotheses: {len(idea.get('hypotheses', []))}", bus, sid)
    _log(f"Keywords: {', '.join(idea.get('keywords', [])[:5])}", bus, sid)
    _emit({"type": "idea_extracted", "session_id": sid, "idea": {
        "title": idea.get("title"),
        "domain": idea.get("domain"),
        "hypotheses": idea.get("hypotheses", [])[:3],
        "keywords": idea.get("keywords", [])[:6],
    }}, bus)

    # ------------------------------------------------------------------
    # Step 2: Load accumulated memory insights
    # ------------------------------------------------------------------
    _emit(
        {
            "type": "idea_progress",
            "session_id": sid,
            "step": "memory",
            "progress": 0.10,
            "label": "Loading accumulated knowledge from memory...",
        },
        bus,
    )
    memory_insights = _load_memory_insights(idea.get("domain", ""))
    if memory_insights:
        _log(
            f"Loaded {len(memory_insights)} memory insight(s) for "
            f"'{idea.get('domain', '')}' domain",
            bus,
            sid,
        )
        for insight in memory_insights[:3]:
            _log(f"  Memory: {insight}", bus, sid)
    _emit({"type": "idea_memory_loaded", "session_id": sid, "insights": memory_insights}, bus)

    # ------------------------------------------------------------------
    # Step 3: Iterative verification loop
    # ------------------------------------------------------------------
    claims = (idea.get("hypotheses", []) + idea.get("research_questions", []))[
        :MAX_CLAIMS_PER_ITERATION
    ]
    all_iterations: list[dict] = []
    running_insights = list(memory_insights)

    for iteration in range(1, max_iterations + 1):
        _log(f"\n--- Iteration {iteration}/{max_iterations} ---", bus, sid)
        base_progress = 0.15 + 0.65 * (iteration - 1) / max_iterations
        _emit(
            {
                "type": "idea_progress",
                "session_id": sid,
                "step": f"iteration_{iteration}_search",
                "progress": base_progress,
                "label": f"Iteration {iteration}/{max_iterations}: Searching literature...",
            },
            bus,
        )

        queries = _generate_queries(idea, running_insights, iteration)
        _log(f"Generated {len(queries)} search queries", bus, sid)

        # Search
        all_papers_this_iter: list[dict] = []
        all_text_this_iter: list[str] = []
        for q in queries:
            text_result, papers = _search_papers(q, sid, bus)
            all_papers_this_iter.extend(papers)
            if text_result:
                all_text_this_iter.append(text_result)

        combined_text = "\n\n".join(all_text_this_iter)[:8000]
        seen_titles: dict[str, dict] = {}
        for p in all_papers_this_iter:
            t = p.get("title", "")
            if t and t not in seen_titles:
                seen_titles[t] = p
        unique_papers = list(seen_titles.values())[:20]
        _log(f"Found {len(unique_papers)} unique papers across {len(queries)} queries", bus, sid)

        # Cross-validate
        _emit(
            {
                "type": "idea_progress",
                "session_id": sid,
                "step": f"iteration_{iteration}_validate",
                "progress": base_progress + 0.20,
                "label": f"Iteration {iteration}/{max_iterations}: Cross-validating claims...",
            },
            bus,
        )
        claim_verifications: list[dict] = []
        for claim in claims:
            cv = _cross_validate_claim(claim, combined_text, unique_papers, sid, bus)
            claim_verifications.append(cv)
            _log(f"  Claim: '{claim[:70]}...' → {cv.get('status', '?')}", bus, sid)

        # Summarise this iteration
        iter_flaws = [f for cv in claim_verifications for f in cv.get("flaws", []) if f]
        iter_supported = [cv["claim"] for cv in claim_verifications if cv.get("status") == "supported"]
        iter_contradicted = [cv["claim"] for cv in claim_verifications if cv.get("status") == "contradicted"]
        iter_summary = (
            f"Found {len(unique_papers)} papers. "
            f"{len(iter_supported)} claims supported, "
            f"{len(iter_contradicted)} contradicted, "
            f"{len(iter_flaws)} flaw(s) identified."
        )
        _log(iter_summary, bus, sid)

        iteration_result: dict = {
            "iteration": iteration,
            "queries": queries,
            "papers_found": [p.get("title", "") for p in unique_papers],
            "claim_verifications": claim_verifications,
            "flaws_found": iter_flaws,
            "summary": iter_summary,
        }
        all_iterations.append(iteration_result)
        _emit(
            {
                "type": "idea_iteration_done",
                "session_id": sid,
                "iteration": {
                    "iteration": iteration,
                    "summary": iter_summary,
                    "flaws": iter_flaws[:5],
                    "papers_count": len(unique_papers),
                },
            },
            bus,
        )

        # Enrich memory insights for the next iteration with newly found flaws
        running_insights = running_insights + [f.strip() for f in iter_flaws[:3] if f.strip()]

        # Early convergence: stop if no new findings
        if iteration >= 2:
            prev_flaws = {
                f
                for prev in all_iterations[:-1]
                for f in prev.get("flaws_found", [])
            }
            new_flaws = set(iter_flaws) - prev_flaws
            if not new_flaws and not iter_contradicted:
                _log(f"Converged at iteration {iteration} — no new findings.", bus, sid)
                break

    # ------------------------------------------------------------------
    # Step 4: Synthesize final report
    # ------------------------------------------------------------------
    _emit(
        {
            "type": "idea_progress",
            "session_id": sid,
            "step": "synthesize",
            "progress": 0.90,
            "label": "Synthesizing final report...",
        },
        bus,
    )
    final_report = _synthesize_final_report(idea, all_iterations, sid, bus)

    # ------------------------------------------------------------------
    # Step 5: Persist to memory
    # ------------------------------------------------------------------
    _emit(
        {
            "type": "idea_progress",
            "session_id": sid,
            "step": "save",
            "progress": 0.95,
            "label": "Saving insights to memory...",
        },
        bus,
    )
    _save_to_memory(sid, idea, all_iterations, final_report)

    # ------------------------------------------------------------------
    # Step 6: Write results file
    # ------------------------------------------------------------------
    full_results: dict = {
        "session_id": sid,
        "timestamp": datetime.now().isoformat(),
        "idea": idea,
        "iterations": all_iterations,
        "final_report": final_report,
        "memory_insights_used": memory_insights,
    }
    session_dir = IDEA_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    results_path = session_dir / "verification_results.json"
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump(full_results, fh, indent=2, ensure_ascii=False)

    _log(f"Verification complete. Saved: {results_path}", bus, sid)
    _emit(
        {
            "type": "idea_finished",
            "session_id": sid,
            "final_report": final_report,
            "iterations_completed": len(all_iterations),
        },
        bus,
    )
    return full_results


if __name__ == "__main__":
    import sys
    sample_text = (
        sys.argv[1] if len(sys.argv) > 1 else
        "We propose a novel transformer-based approach for multi-label text classification "
        "using contrastive learning on low-resource datasets. Our hypothesis is that "
        "fine-tuned LLMs with contrastive loss will outperform baseline methods by 10% F1 "
        "while requiring 50% less labelled data."
    )
    results = run_idea_verification(sample_text, max_iterations=2)
    print(json.dumps(results["final_report"], indent=2, ensure_ascii=False))

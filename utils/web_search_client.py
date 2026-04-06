"""
Web Search Client — Tavily-powered real-time web search with fallback.

Uses Tavily for comprehensive web search with AI-powered result extraction.
Falls back to the existing arXiv + Semantic Scholar pipeline if Tavily is unavailable.

Set TAVILY_API_KEY in .env or configs/pipeline.yaml -> search.tavily_api_key.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_tavily_key() -> str | None:
    """Get Tavily API key from env or config."""
    key = os.environ.get("TAVILY_API_KEY")
    if key:
        return key
    try:
        import yaml
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "configs", "pipeline.yaml",
        )
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("search", {}).get("tavily_api_key")
    except Exception:
        pass
    return None


def tavily_search(
    query: str,
    *,
    max_results: int = 10,
    search_depth: str = "advanced",
    include_answer: bool = True,
    include_raw_content: bool = False,
    topic: str = "general",
) -> dict[str, Any]:
    """Search the web using Tavily API.

    Returns:
        dict with keys: answer (str), results (list of {title, url, content, score}),
        query (str), response_time (float).
    """
    api_key = _get_tavily_key()
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY not set. Add to .env or configs/pipeline.yaml -> search.tavily_api_key"
        )

    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)

    response = client.search(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        include_answer=include_answer,
        include_raw_content=include_raw_content,
        topic=topic,
    )
    return response


def tavily_search_context(
    query: str,
    *,
    max_results: int = 5,
    max_tokens: int = 4000,
    search_depth: str = "advanced",
    topic: str = "general",
) -> str:
    """Get a pre-formatted context string from Tavily (ideal for LLM prompts).

    Returns a string of concatenated search result content.
    """
    api_key = _get_tavily_key()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set.")

    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)

    return client.get_search_context(
        query=query,
        max_results=max_results,
        max_tokens=max_tokens,
        search_depth=search_depth,
        topic=topic,
    )


def tavily_extract(urls: list[str]) -> list[dict[str, str]]:
    """Extract content from specific URLs using Tavily.

    Returns list of {url, raw_content} dicts.
    """
    api_key = _get_tavily_key()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY not set.")

    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)

    response = client.extract(urls=urls)
    return response.get("results", [])


def is_tavily_available() -> bool:
    """Check if Tavily API is configured."""
    return _get_tavily_key() is not None


# ---------------------------------------------------------------------------
# Unified search that combines Tavily + academic sources
# ---------------------------------------------------------------------------


def research_search(
    query: str,
    *,
    max_results: int = 10,
    include_academic: bool = True,
    include_web: bool = True,
    step_prefix: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """Unified research search combining Tavily web search and academic sources.

    Returns (synthesized_text, papers_and_sources_used).
    """
    p = step_prefix or "  "
    all_context_parts: list[str] = []
    all_sources: list[dict[str, Any]] = []

    # 1. Tavily web search
    if include_web and is_tavily_available():
        try:
            print(f"{p}[Tavily] Searching web for: {query[:80]}...", flush=True)
            result = tavily_search(
                query,
                max_results=min(max_results, 10),
                search_depth="advanced",
                include_answer=True,
                topic="general",
            )

            if result.get("answer"):
                all_context_parts.append(f"Web Search Summary:\n{result['answer']}\n")

            for r in result.get("results", []):
                source = {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", "")[:2000],
                    "score": r.get("score", 0),
                    "source": "tavily_web",
                }
                all_sources.append(source)
                all_context_parts.append(
                    f"[Web] {source['title']}\nURL: {source['url']}\n{source['content'][:1000]}\n"
                )

            print(f"{p}[Tavily] Found {len(result.get('results', []))} web results.", flush=True)
        except Exception as e:
            print(f"{p}[Tavily] Web search failed: {e}", flush=True)

    # 2. Academic sources (arXiv + Semantic Scholar via existing research_client)
    if include_academic:
        try:
            from utils.research_client import _arxiv_search, _semantic_scholar_search

            print(f"{p}[Academic] Searching arXiv...", flush=True)
            arxiv_results = _arxiv_search(query, max_results=max_results // 2)
            for paper in arxiv_results:
                all_sources.append({**paper, "source": "arxiv"})
                all_context_parts.append(
                    f"[arXiv] {paper.get('title', '')}\n"
                    f"Abstract: {paper.get('abstract', '')[:1000]}\n"
                )

            print(f"{p}[Academic] Searching Semantic Scholar...", flush=True)
            ss_results = _semantic_scholar_search(query, limit=max_results // 2)
            for paper in ss_results:
                all_sources.append({**paper, "source": "semantic_scholar"})
                all_context_parts.append(
                    f"[S2] {paper.get('title', '')}\n"
                    f"Abstract: {paper.get('abstract', '')[:1000]}\n"
                )

            print(
                f"{p}[Academic] Found {len(arxiv_results)} arXiv + {len(ss_results)} S2 papers.",
                flush=True,
            )
        except Exception as e:
            print(f"{p}[Academic] Search failed: {e}", flush=True)

    if not all_context_parts:
        return "No results found. Try broadening your search query.", []

    # 3. Synthesize with LLM
    context = "\n---\n".join(all_context_parts)[:120_000]

    try:
        from utils.multi_llm_client import generate
        print(f"{p}[Synthesis] Synthesizing {len(all_sources)} sources...", flush=True)
        synthesis = generate(
            f"Research query: {query}\n\n"
            f"Sources:\n{context}\n\n"
            "Synthesize a comprehensive, well-structured answer. "
            "Cite sources with [Web] or [arXiv] tags where relevant. "
            "Include key findings, methodology notes, and any contradictions.",
            system_instruction="You synthesize research from multiple sources. Be precise and cite sources.",
            max_output_tokens=4096,
        )
        if synthesis:
            return synthesis, all_sources
    except Exception as e:
        print(f"{p}[Synthesis] LLM synthesis failed: {e}", flush=True)

    # Fallback: return raw context
    return context[:8000], all_sources

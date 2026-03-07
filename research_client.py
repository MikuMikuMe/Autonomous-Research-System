"""
Research Client — Unified research pipeline for paper search, PDF retrieval, and synthesis.

Supports:
1. alphaXiv Assistant V2 — Chat API (api.alphaxiv.org/assistant/v2/chat) with API key
2. Fallback: arXiv + Semantic Scholar + Gemini for search, PDF download, and synthesis

Requires: ALPHAXIV_TOKEN (optional), GOOGLE_API_KEY (for fallback)
"""

import json
import os
import tempfile
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ALPHAXIV_ASSISTANT_URL = os.environ.get(
    "ALPHAXIV_ASSISTANT_URL",
    "https://api.alphaxiv.org/assistant/v2/chat",
)


def _get_alphaxiv_token() -> str | None:
    """Get alphaXiv token from env or .cursor/mcp.json."""
    token = os.environ.get("ALPHAXIV_TOKEN")
    if token:
        return token
    try:
        import pathlib
        mcp_path = pathlib.Path(__file__).resolve().parent / ".cursor" / "mcp.json"
        if mcp_path.exists():
            with open(mcp_path, encoding="utf-8") as f:
                cfg = json.load(f)
            headers = cfg.get("mcpServers", {}).get("alphaxiv", {}).get("headers", {})
            auth = headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                return auth[7:].strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# alphaXiv Assistant V2 Chat API
# ---------------------------------------------------------------------------


def alphaxiv_assistant_chat(
    message: str,
    *,
    files: list[dict[str, str]] | None = None,
    model: str = "gemini-3-pro",
    thinking: bool = True,
    deep_research: bool = True,
    llm_chat_id: str | None = None,
    parent_message_id: str | None = None,
) -> str:
    """
    Send a message to alphaXiv Assistant V2 and receive the response.
    Uses API key auth (Bearer). Handles streaming by collecting chunks.
    """
    import httpx

    token = _get_alphaxiv_token()
    if not token:
        raise RuntimeError(
            "ALPHAXIV_TOKEN not set. Add to .env for alphaXiv Assistant. "
            "See docs/ALPHAXIV_SETUP.md"
        )

    payload = {
        "message": message,
        "files": files or [],
        "llmChatId": llm_chat_id,
        "model": model,
        "thinking": thinking,
        "deepResearch": deep_research,
        "parentMessageId": parent_message_id,
        "paperVersionId": None,
        "selectionPageRange": None,
        "webSearch": "full" if deep_research else "off",
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    with httpx.Client(timeout=180.0) as client:
        response = client.post(
            ALPHAXIV_ASSISTANT_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        # Handle streaming (chunked) or JSON response
        content_type = response.headers.get("content-type", "")
        text = response.text

        if "text/event-stream" in content_type or "application/x-ndjson" in content_type:
            # SSE or NDJSON: collect text chunks
            return _parse_streaming_response(text)
        if "application/json" in content_type:
            return _parse_json_chat_response(response.json())
        # Fallback: treat as plain text
        return text.strip() if text else ""


def _parse_streaming_response(text: str) -> str:
    """Parse SSE or NDJSON streaming response into full text.
    Handles alphaXiv format: data: {"type":"delta_output_text","delta":"...","index":0}
    """
    parts = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
                if isinstance(data, dict):
                    if "delta" in data:
                        parts.append(str(data["delta"]))
                    elif "text" in data:
                        parts.append(data["text"])
                    elif "content" in data:
                        parts.append(str(data["content"]))
                elif isinstance(data, str):
                    parts.append(data)
            except json.JSONDecodeError:
                pass
        elif line and not line.startswith(":"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    if "delta" in data:
                        parts.append(str(data["delta"]))
                    elif "text" in data:
                        parts.append(data["text"])
            except json.JSONDecodeError:
                pass
    return "".join(parts).strip() or text


def _parse_json_chat_response(data: dict) -> str:
    """Extract assistant message from alphaXiv chat JSON response."""
    if not isinstance(data, dict):
        return str(data)

    # Common response shapes
    for key in ("text", "content", "message", "response", "output"):
        if key in data and data[key]:
            val = data[key]
            return val if isinstance(val, str) else json.dumps(val)

    if "choices" in data and data["choices"]:
        choice = data["choices"][0]
        if isinstance(choice, dict):
            msg = choice.get("message") or choice.get("delta") or choice
            if isinstance(msg, dict) and "content" in msg:
                return msg["content"]
            if isinstance(msg, dict) and "text" in msg:
                return msg["text"]
            if isinstance(msg, str):
                return msg

    if "messages" in data and data["messages"]:
        for m in reversed(data["messages"]):
            if isinstance(m, dict) and m.get("role") == "assistant":
                content = m.get("content") or m.get("text")
                if content:
                    return content if isinstance(content, str) else json.dumps(content)

    return json.dumps(data)


# ---------------------------------------------------------------------------
# Fallback: arXiv + Semantic Scholar + Gemini
# ---------------------------------------------------------------------------


def _format_ieee_citation(paper: dict[str, Any]) -> str:
    """Format paper metadata as IEEE citation."""
    title = paper.get("title", "")
    authors = paper.get("authors", [])
    year = paper.get("year", "")
    venue = paper.get("venue", "") or paper.get("journal", "")
    arxiv_id = paper.get("arxiv_id", "")
    source = paper.get("source", "")

    if isinstance(authors, list) and authors:
        names = []
        for a in authors[:8]:  # IEEE often truncates with "et al."
            if isinstance(a, dict):
                n = a.get("name", a.get("name", ""))
            else:
                n = getattr(a, "name", str(a))
            if n:
                parts = n.split()
                if len(parts) >= 2:
                    names.append(f"{parts[-1]}, {'. '.join(p[0] for p in parts[:-1])}.")
                else:
                    names.append(n)
        auth_str = ", ".join(names) if len(names) <= 3 else ", ".join(names[:3]) + ", et al."
    else:
        auth_str = "Authors unknown"

    if source == "arxiv" and arxiv_id:
        return f'{auth_str}, "{title}," arXiv preprint arXiv:{arxiv_id}, {year}.'
    if venue:
        return f'{auth_str}, "{title}," in {venue}, {year}.'
    return f'{auth_str}, "{title}," {year}.'


def _arxiv_search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search arXiv. Returns list of {title, abstract, pdf_url, arxiv_id, authors, year, ieee_citation}."""
    try:
        import arxiv
    except ImportError:
        return []

    results = []
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        for r in client.results(search):
            pdf_url = r.pdf_url if hasattr(r, "pdf_url") else f"https://arxiv.org/pdf/{r.entry_id.split('/')[-1]}.pdf"
            arxiv_id = r.entry_id.split("/")[-1] if r.entry_id else ""
            authors = [{"name": a.name} for a in (r.authors or [])]
            year = str(r.published.year) if hasattr(r, "published") and r.published else ""
            paper = {
                "title": r.title,
                "abstract": r.summary or "",
                "pdf_url": pdf_url,
                "arxiv_id": arxiv_id,
                "authors": authors,
                "year": year,
                "venue": "",
                "source": "arxiv",
            }
            paper["ieee_citation"] = _format_ieee_citation(paper)
            results.append(paper)
    except Exception:
        pass
    return results


def _semantic_scholar_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Semantic Scholar. Returns list with authors, year, venue, ieee_citation for citations."""
    try:
        from semanticscholar import SemanticScholar
    except ImportError:
        return []

    results = []
    try:
        sch = SemanticScholar()
        fields = ["title", "abstract", "authors", "year", "venue", "publicationVenue", "openAccessPdf", "paperId"]
        resp = sch.search_paper(query, limit=limit, fields=fields)
        items = getattr(resp, "data", None) or resp
        if not isinstance(items, (list, tuple)):
            items = list(items) if items else []
        for p in items:
            if p is None:
                continue
            pdf_url = ""
            oa = getattr(p, "openAccessPdf", None)
            if oa:
                pdf_url = oa.get("url", "") if isinstance(oa, dict) else getattr(oa, "url", "")
            authors = []
            for a in (getattr(p, "authors", None) or []):
                if hasattr(a, "name"):
                    authors.append({"name": a.name})
                elif isinstance(a, dict):
                    authors.append({"name": a.get("name", "")})
            venue = getattr(p, "venue", "") or ""
            if not venue and hasattr(p, "publicationVenue"):
                pv = p.publicationVenue
                venue = pv.get("name", "") if isinstance(pv, dict) else getattr(pv, "name", "")
            paper = {
                "title": getattr(p, "title", "") or "",
                "abstract": getattr(p, "abstract", "") or "",
                "pdf_url": pdf_url,
                "paper_id": getattr(p, "paperId", "") or "",
                "authors": authors,
                "year": str(getattr(p, "year", "") or ""),
                "venue": venue,
                "source": "semantic_scholar",
            }
            paper["ieee_citation"] = _format_ieee_citation(paper)
            results.append(paper)
    except Exception:
        pass
    return results


# Max chars per PDF to avoid memory issues with huge documents (pypdf can use 10GB+ on some)
_PDF_MAX_CHARS_PER_DOC = 150_000


def _download_pdf_text(url: str, max_chars: int | None = None) -> str:
    """Download PDF from URL and extract full text. Returns full text up to max_chars (None = no limit, capped at _PDF_MAX_CHARS_PER_DOC).
    Uses a temp file that is deleted immediately after content is extracted."""
    if not url or not url.startswith("http"):
        return ""

    try:
        import httpx
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            pdf_bytes = r.content
    except Exception:
        return ""

    limit = max_chars if max_chars is not None else _PDF_MAX_CHARS_PER_DOC
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        with PdfReader(tmp_path) as reader:
            text_parts = []
            total = 0
            for page in reader.pages:
                if limit and total >= limit:
                    break
                t = page.extract_text() or ""
                text_parts.append(t)
                total += len(t)
            full_text = "\n\n".join(text_parts)
        return full_text[:limit] if limit else full_text
    except Exception:
        return ""
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# Max chars for Gemini context (typical papers ~30–50k each; 8 papers × ~15k = 120k)
_GEMINI_CONTEXT_MAX_CHARS = 120_000


def _gemini_synthesize(query: str, papers_context: str) -> str:
    """Use Gemini to synthesize an answer from paper context."""
    from llm_client import generate, is_available

    if not is_available():
        return papers_context[:8000]  # Fallback: return raw context truncated

    context = papers_context[: _GEMINI_CONTEXT_MAX_CHARS]
    prompt = f"""You are a research assistant. Answer the following research question based on the provided context.

Research question: {query}

Context (primary sources first, then additional literature):
---
{context}
---

Provide a concise, well-structured answer. Prefer original wording and citations from the primary sources (e.g., "Huang and Turetken (2025)"). Include author-year citations in IEEE style where relevant."""

    result = generate(
        prompt,
        system_instruction="You synthesize academic research. Be precise and cite specific papers when relevant.",
        max_output_tokens=4096,
    )
    return result or papers_context[:8000]


def fallback_research(
    query: str,
    max_papers: int = 8,
    download_pdfs: bool = True,
    step_prefix: str = "",
) -> str:
    """
    Fallback: search arXiv + Semantic Scholar, optionally download PDFs, synthesize with Gemini.
    """
    p = step_prefix or "  "
    print(f"{p}[Fallback] Step 1/4: Searching arXiv...", flush=True)
    arxiv_results = _arxiv_search(query, max_results=max_papers // 2)
    print(f"{p}[Fallback] Step 2/4: Searching Semantic Scholar...", flush=True)
    ss_results = _semantic_scholar_search(query, limit=max_papers // 2)

    # Dedupe by title
    seen = set()
    all_papers = []
    for p in arxiv_results + ss_results:
        key = (p.get("title") or "").lower()[:80]
        if key and key not in seen:
            seen.add(key)
            all_papers.append(p)

    if not all_papers:
        print(f"{p}[Fallback] No papers found.", flush=True)
        return "No relevant papers found. Try broadening your search query.", []

    # Build context from abstracts and full PDF text
    papers_to_use = all_papers[:max_papers]
    print(f"{p}[Fallback] Step 3/4: Building context from {len(papers_to_use)} papers...", flush=True)
    num_papers = len(papers_to_use)
    max_per_paper = _GEMINI_CONTEXT_MAX_CHARS // max(num_papers, 1) if num_papers else 0

    context_parts = []
    for i, paper in enumerate(papers_to_use, 1):
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        pdf_url = paper.get("pdf_url", "")
        source = paper.get("source", "")

        block = f"[{i}] {title}\nAbstract: {abstract[:1500]}"
        if download_pdfs and pdf_url and "arxiv" in (source or pdf_url.lower()):
            # Prefer arXiv PDFs (more reliable) — extract full text
            pdf_text = _download_pdf_text(pdf_url)
            if pdf_text:
                block += f"\nFull text:\n{pdf_text[:max_per_paper]}"
                if len(pdf_text) > max_per_paper:
                    block += f"\n[... truncated, {len(pdf_text) - max_per_paper} chars omitted]"
        context_parts.append(block)

    context = "\n\n".join(context_parts)

    # Prepend source PDF context so synthesis prioritizes our reference documents
    try:
        from pdf_source_extractor import get_combined_context
        source_context = get_combined_context()
        if source_context:
            source_context = source_context[:40000]  # Reserve space for arXiv/SS
            context = (
                "PRIMARY SOURCES (bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf) — "
                "use these as authoritative; prefer their wording and citations:\n---\n"
                + source_context
                + "\n---\n\nADDITIONAL LITERATURE (arXiv & Semantic Scholar):\n"
                + context
            )
    except ImportError:
        pass

    print(f"{p}[Fallback] Step 4/4: Synthesizing with Gemini...", flush=True)
    result = _gemini_synthesize(query, context)
    papers_used = [
        {"title": x.get("title"), "ieee_citation": x.get("ieee_citation"), "source": x.get("source")}
        for x in papers_to_use
    ]
    print(f"{p}[Fallback] Done ({len(result)} chars, {len(papers_used)} papers for citation).", flush=True)
    return result, papers_used


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


def answer_research_query(
    query: str,
    prefer_alphaxiv: bool = True,
    step_prefix: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """
    Answer a research question using natural language.
    Returns (result_text, papers_used). papers_used is [] for alphaXiv (no structured citations).

    1. If ALPHAXIV_TOKEN set and prefer_alphaxiv: use alphaXiv Assistant V2 chat
    2. Else: use arXiv + Semantic Scholar + Gemini fallback (returns papers with IEEE citations)
    """
    p = step_prefix or ""

    if prefer_alphaxiv and _get_alphaxiv_token():
        try:
            print(f"{p}[alphaXiv] Query: {query}", flush=True)
            print(f"{p}[alphaXiv] Step 1/3: Sending to API (deep research + thinking, typically 1–2 min)...", flush=True)
            # Include source PDF context so alphaXiv grounds in our reference documents
            msg = f"Research question: {query}\n\n"
            try:
                from pdf_source_extractor import get_combined_context
                src = get_combined_context()
                if src:
                    msg += f"Our reference documents (bias_mitigation.pdf, Bias Auditing Framework.pdf, Bias Detection findings.pdf) state:\n---\n{src[:25000]}\n---\n\n"
            except ImportError:
                pass
            msg += "Please synthesize findings. Prefer original wording and citations from the reference documents (e.g., Huang and Turetken (2025)). Add supporting papers where relevant."
            result = alphaxiv_assistant_chat(
                message=msg,
                deep_research=True,
                thinking=True,
            )
            print(f"{p}[alphaXiv] Step 2/3: Response received ({len(result)} chars)", flush=True)
            print(f"{p}[alphaXiv] Step 3/3: Done.", flush=True)
            return result, []  # alphaXiv does not expose structured paper list
        except Exception as e:
            print(f"{p}[Research] alphaXiv failed ({e}), falling back to arXiv + Semantic Scholar...", flush=True)
            return fallback_research(query, step_prefix=step_prefix)
    print(f"{p}[Research] Query (arXiv+Semantic Scholar): {query}", flush=True)
    return fallback_research(query, step_prefix=step_prefix)


def answer_research_query_sync(
    query: str,
    prefer_alphaxiv: bool = True,
    step_prefix: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """Synchronous wrapper. Returns (result_text, papers_used)."""
    return answer_research_query(query, prefer_alphaxiv=prefer_alphaxiv, step_prefix=step_prefix)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "What do recent papers say about bias mitigation in credit scoring?"
    print("Query:", q[:80], "...")
    print("\n--- Response ---")
    try:
        out, papers = answer_research_query_sync(q)
        print(out[:2000] if out else "No output")
        if papers:
            print("\n--- Papers (IEEE) ---")
            for p in papers[:5]:
                print(" ", p.get("ieee_citation", p.get("title", ""))[:100])
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

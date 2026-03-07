"""
PDF Source Extractor — Extracts text and citations from source PDFs.
Used to ground the paper in original wording and citations from:
- bias_mitigation.pdf
- Bias Auditing Framework.pdf
- Bias Detection findings.pdf
"""

import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_PDFS = [
    "bias_mitigation.pdf",
    "Bias Auditing Framework.pdf",
    "Bias Detection findings.pdf",
]
MAX_CHARS_PER_PDF = 150_000


def _normalize_text(text: str) -> str:
    """Collapse extra spaces (common in PDF extraction)."""
    return re.sub(r"\s+", " ", text).strip()


def _truncate_at_sentence_boundary(text: str, max_chars: int) -> str:
    """
    Truncate text at a sentence boundary to avoid mid-sentence cuts.
    Prevents white chunks and incomplete content in the paper.
    """
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Find last sentence-ending punctuation
    last_period = cut.rfind(". ")
    last_excl = cut.rfind("! ")
    last_quest = cut.rfind("? ")
    last_end = max(last_period, last_excl, last_quest)
    if last_end > max_chars * 0.5:  # Only use if we keep at least half
        return text[: last_end + 1].strip()
    return cut.strip()


def _extract_citations(text: str) -> list[dict]:
    """Extract author-year citations and DOIs from text."""
    citations = []
    seen = set()

    # Author and Author (YYYY)
    for m in re.finditer(r"([A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+|\s+et\s+al\.?)?)\s*\((\d{4})\)", text):
        key = f"{m.group(1)} ({m.group(2)})"
        if key not in seen:
            seen.add(key)
            citations.append({"raw": key, "authors": m.group(1).strip(), "year": m.group(2)})

    # DOIs
    for m in re.finditer(r"https://doi\.org/([^\s\)\]\"]+)", text):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            citations.append({"raw": m.group(0), "doi": m.group(1)})

    return citations


def extract_all() -> dict:
    """
    Extract text and citations from all source PDFs.
    Returns dict: {pdf_name: {text, citations, normalized_text}}
    """
    result = {}
    for name in SOURCE_PDFS:
        path = os.path.join(SCRIPT_DIR, name)
        if not os.path.exists(path):
            result[name] = {"text": "", "citations": [], "normalized_text": "", "error": "file not found"}
            continue
        try:
            from pypdf import PdfReader

            reader = PdfReader(path)
            parts = []
            total = 0
            for page in reader.pages:
                if total >= MAX_CHARS_PER_PDF:
                    break
                t = page.extract_text() or ""
                parts.append(t)
                total += len(t)
            text = "\n\n".join(parts)[:MAX_CHARS_PER_PDF]
            normalized = _normalize_text(text)
            citations = _extract_citations(text)
            result[name] = {
                "text": text,
                "normalized_text": normalized,
                "citations": citations,
            }
        except Exception as e:
            result[name] = {"text": "", "citations": [], "normalized_text": "", "error": str(e)}
    return result


def get_combined_context() -> str:
    """Get combined normalized text from all PDFs for use as context."""
    data = extract_all()
    parts = []
    for name, d in data.items():
        if d.get("normalized_text") and not d.get("error"):
            parts.append(f"--- From {name} ---\n{d['normalized_text']}")
    return "\n\n".join(parts)


def get_all_citations() -> list[dict]:
    """Get deduplicated citations from all PDFs."""
    data = extract_all()
    seen = set()
    out = []
    for name, d in data.items():
        for c in d.get("citations", []):
            key = c.get("raw", "") or c.get("doi", "")
            if key and key not in seen:
                seen.add(key)
                c2 = dict(c)
                c2["source_pdf"] = name
                out.append(c2)
    return out


def save_to_outputs():
    """Extract and save to outputs/source_pdf_content.json."""
    data = extract_all()
    out_path = os.path.join(SCRIPT_DIR, "outputs", "source_pdf_content.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # Truncate text for JSON (keep full in memory for processing)
    for k, v in data.items():
        if isinstance(v, dict) and "text" in v and len(v["text"]) > 50000:
            v["text_preview"] = v["text"][:50000] + "\n[... truncated for storage ...]"
            v["text"] = v["text"][:50000]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return out_path


def get_passage_for_topic(topic_keywords: list[str], source_pdf: str | None = None, max_chars: int = 2000) -> str:
    """
    Find the most relevant passage from source PDFs for a given topic.
    Returns up to max_chars of text containing the keywords.
    """
    data = extract_all()
    best = ""
    best_score = 0
    for name, d in data.items():
        if source_pdf and name != source_pdf:
            continue
        if d.get("error"):
            continue
        text = d.get("normalized_text", "")
        if not text:
            continue
        score = sum(1 for kw in topic_keywords if kw.lower() in text.lower())
        if score > best_score:
            best_score = score
            # Find a passage containing the keywords
            for kw in topic_keywords:
                idx = text.lower().find(kw.lower())
                if idx >= 0:
                    start = max(0, idx - 200)
                    end = min(len(text), idx + max_chars)
                    raw = text[start:end]
                    best = _truncate_at_sentence_boundary(raw, max_chars)
                    if len(best) < 100:
                        best = _truncate_at_sentence_boundary(text[:max_chars], max_chars)
                    break
            if not best and score > 0:
                best = _truncate_at_sentence_boundary(text[:max_chars], max_chars)
    return best


def get_passages_from_all_pdfs(topic_keywords: list[str], max_chars_per_pdf: int = 2500) -> list[dict]:
    """
    Get relevant passages from ALL source PDFs for a topic.
    Returns list of {pdf_name, passage} with original wording from each PDF.
    Use for merging/deduplication when multiple PDFs cover the same topic.
    """
    data = extract_all()
    results = []
    for name, d in data.items():
        if d.get("error") or not d.get("normalized_text"):
            continue
        text = d["normalized_text"]
        score = sum(1 for kw in topic_keywords if kw.lower() in text.lower())
        if score == 0:
            continue
        best = ""
        for kw in topic_keywords:
            idx = text.lower().find(kw.lower())
            if idx >= 0:
                start = max(0, idx - 200)
                end = min(len(text), idx + max_chars_per_pdf)
                raw = text[start:end]
                best = _truncate_at_sentence_boundary(raw, max_chars_per_pdf)
                if len(best) < 100:
                    best = _truncate_at_sentence_boundary(text[:max_chars_per_pdf], max_chars_per_pdf)
                break
        if not best:
            best = _truncate_at_sentence_boundary(text[:max_chars_per_pdf], max_chars_per_pdf)
        results.append({"pdf_name": name, "passage": best.strip()})
    return results


def extract_topics_from_pdfs() -> list[dict]:
    """
    Use Gemini to extract key topics from each source PDF.
    Returns list of {pdf_name, topic, keywords[]} for coverage verification.
    """
    try:
        from llm_client import generate, is_available
    except ImportError:
        return []
    if not is_available():
        return []

    data = extract_all()
    all_topics = []
    for name, d in data.items():
        if d.get("error") or not d.get("text"):
            continue
        text = d["text"][:25000]  # Limit for prompt
        prompt = f"""Extract the key topics/concepts from this research document excerpt.
Document: {name}

Excerpt:
---
{text}
---

For each distinct topic, output one line: TOPIC|topic_name|keyword1,keyword2,keyword3
Use the exact terminology from the document. Output 8-15 topics. Example:
TOPIC|Demographic Parity|demographic parity, statistical parity, SPD
TOPIC|Equalized Odds|equalized odds, EOD, FPR, TPR
TOPIC|Bias Auditing Lifecycle|audit, lifecycle, pre-deployment, post-deployment

Output only lines in that format, no other text."""

        result = generate(prompt, max_output_tokens=2048)
        if not result:
            continue
        for line in result.strip().split("\n"):
            line = line.strip()
            if not line or not line.upper().startswith("TOPIC|"):
                continue
            try:
                parts = line.split("|", 2)
                if len(parts) >= 3:
                    topic_name = parts[1].strip()
                    keywords = [k.strip() for k in parts[2].split(",") if k.strip()]
                    all_topics.append({
                        "pdf_name": name,
                        "topic": topic_name,
                        "keywords": keywords[:5],
                    })
            except (IndexError, ValueError):
                continue
    return all_topics


if __name__ == "__main__":
    data = extract_all()
    for name, d in data.items():
        n = len(d.get("text", ""))
        c = len(d.get("citations", []))
        print(f"{name}: {n} chars, {c} citations")
    path = save_to_outputs()
    print(f"Saved to {path}")

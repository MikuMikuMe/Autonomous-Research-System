"""
Idea Input Agent — Parses uploaded research ideas from text and/or images.

Uses Gemini (multimodal if images are provided) to extract a structured profile:
  - title (inferred)
  - problem_statement
  - hypotheses (list of testable claims)
  - proposed_methods (list)
  - expected_outcomes (list)
  - domain (e.g. "machine learning", "NLP")
  - keywords (for paper search)
  - research_questions (list)

Falls back to rule-based extraction when Gemini is unavailable.
Saves result to outputs/idea_input.json.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_EXTRACTION_SYSTEM_PROMPT = (
    "You are a research idea analyst. Extract a structured profile from the given "
    "research idea text and any accompanying images. "
    "Return ONLY a valid JSON object with these exact keys:\n"
    "{\n"
    '  "title": "concise title (5-10 words)",\n'
    '  "problem_statement": "one-paragraph description of the research problem",\n'
    '  "hypotheses": ["list of specific, testable hypotheses"],\n'
    '  "proposed_methods": ["list of methods, algorithms, or approaches proposed"],\n'
    '  "expected_outcomes": ["list of expected results or contributions"],\n'
    '  "domain": "research domain (e.g. machine learning, NLP, computer vision, etc.)",\n'
    '  "keywords": ["5-10 keywords for paper search"],\n'
    '  "research_questions": ["list of specific research questions to answer"]\n'
    "}\n"
    "All fields are required. Lists should have at least 2-3 items each."
)


def _make_session_id() -> str:
    import random
    return f"idea_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"


def _build_extraction_prompt(text: str, image_paths: list[str] | None) -> str:
    img_note = ""
    if image_paths:
        img_note = (
            f"\n\nThe user has also uploaded {len(image_paths)} image(s). "
            "Analyze them together with the text to enrich the extracted profile."
        )
    return (
        f"Research idea description:\n\n{text}{img_note}\n\n"
        "Extract the structured research profile as specified."
    )


def _parse_llm_response(response: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown code blocks."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
    if match:
        response = match.group(1).strip()
    # Also try to find a bare JSON object
    obj_match = re.search(r"\{[\s\S]*\}", response)
    if obj_match:
        response = obj_match.group(0)
    try:
        data = json.loads(response)
        required = [
            "title", "problem_statement", "hypotheses", "proposed_methods",
            "expected_outcomes", "domain", "keywords", "research_questions",
        ]
        if all(k in data for k in required):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _rule_based_extraction(text: str) -> dict:
    """Basic keyword extraction without LLM."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    title = lines[0][:80] if lines else "Research Idea"

    words = re.findall(r'\b[A-Za-z]{4,}\b', text)
    keywords = list(dict.fromkeys(w.lower() for w in words if len(w) > 4))[:10]

    # Extract sentences that look like hypotheses (contain "will", "can", "should", "we propose")
    hypothesis_patterns = re.compile(
        r'(?:we (?:propose|hypothesize|argue|claim|show)|'
        r'(?:this|our) (?:approach|method|model|system)|'
        r'(?:will|can|should|may) (?:improve|achieve|outperform|reduce|increase))',
        re.IGNORECASE,
    )
    sentences = re.split(r'(?<=[.!?])\s+', text)
    hypotheses = [s.strip() for s in sentences if hypothesis_patterns.search(s)][:3]
    if not hypotheses:
        hypotheses = [text[:200].strip()] if text else ["No specific hypothesis found."]

    return {
        "title": title,
        "problem_statement": text[:500].strip(),
        "hypotheses": hypotheses,
        "proposed_methods": [],
        "expected_outcomes": [],
        "domain": "research",
        "keywords": keywords,
        "research_questions": [f"Can we validate: {title}?"],
    }


def _save(data: dict) -> None:
    out_path = OUTPUT_DIR / "idea_input.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_idea(
    text: str,
    image_paths: list[str] | None = None,
    *,
    session_id: str | None = None,
) -> dict:
    """
    Extract a structured research idea from text and optional images.

    Args:
        text: Research idea description text.
        image_paths: Paths to uploaded image files (diagrams, figures, screenshots).
        session_id: Optional session identifier for traceability.

    Returns:
        Structured idea dict with hypotheses, methods, keywords, etc.
    """
    sid = session_id or _make_session_id()
    structured: dict = {
        "session_id": sid,
        "timestamp": datetime.now().isoformat(),
        "raw_text": text,
        "image_paths": image_paths or [],
        "title": "",
        "problem_statement": "",
        "hypotheses": [],
        "proposed_methods": [],
        "expected_outcomes": [],
        "domain": "",
        "keywords": [],
        "research_questions": [],
        "extraction_method": "rule_based",
    }

    prompt = _build_extraction_prompt(text, image_paths)

    try:
        from utils.llm_client import generate_multimodal, is_available
        if is_available():
            response = generate_multimodal(
                prompt,
                image_paths=image_paths,
                system_instruction=_EXTRACTION_SYSTEM_PROMPT,
                max_output_tokens=2048,
            )
            if response:
                parsed = _parse_llm_response(response)
                if parsed:
                    structured.update(parsed)
                    structured["session_id"] = sid
                    structured["timestamp"] = structured["timestamp"]
                    structured["raw_text"] = text
                    structured["image_paths"] = image_paths or []
                    structured["extraction_method"] = (
                        "llm_multimodal" if image_paths else "llm"
                    )
                    _save(structured)
                    return structured
    except Exception as e:
        print(f"  [IdeaInput] LLM extraction failed: {e}", flush=True)

    # Fallback: rule-based extraction
    structured.update(_rule_based_extraction(text))
    # Restore session metadata that rule-based extraction would overwrite
    structured["session_id"] = sid
    structured["raw_text"] = text
    structured["image_paths"] = image_paths or []
    structured["extraction_method"] = "rule_based"
    _save(structured)
    return structured


if __name__ == "__main__":
    import sys
    sample = (
        sys.argv[1] if len(sys.argv) > 1 else
        "We propose a novel transformer-based model for multi-label text classification. "
        "Our hypothesis is that pre-trained language models fine-tuned with contrastive learning "
        "will outperform baseline approaches on low-resource datasets. We expect to achieve "
        "state-of-the-art F1 scores on benchmark datasets while using 50% less labelled data."
    )
    result = extract_idea(sample)
    print(json.dumps(result, indent=2, ensure_ascii=False))

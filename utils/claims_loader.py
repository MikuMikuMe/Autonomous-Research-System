"""
Claims Loader — Parse research claims from various sources.

Accepts:
  - JSON file: list of claim dicts, or dict with 'claims'/'hypotheses' key
  - Plain text file: one claim per line, or Gemini-extracted if GOOGLE_API_KEY is set
  - Python list: passed directly
  - None: falls back to outputs/idea_input.json

Returns a normalised list[dict] where each claim has:
  {id, text, domain, confidence, source, verified}
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def load_claims(source: str | list | None = None) -> list[dict]:
    """Load and normalise research claims from *source*.

    Args:
        source: File path (str), raw list of claims, or None to use
                outputs/idea_input.json.
    """
    if source is None:
        return _load_from_idea_input()
    if isinstance(source, list):
        return _normalise(source)
    path = Path(source)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        raise FileNotFoundError(f"Claims source not found: {path}")
    return _load_from_json(path) if path.suffix.lower() == ".json" else _load_from_text(path)


# ── Loaders ──────────────────────────────────────────────────────────────────

def _load_from_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return _normalise(data)

    if isinstance(data, dict):
        # Standard keys
        for key in ("claims", "hypotheses", "statements", "propositions"):
            if key in data and isinstance(data[key], list):
                return _normalise(data[key])
        # Single claim dict
        if any(k in data for k in ("text", "claim", "hypothesis", "statement")):
            return _normalise([data])
        # idea_input.json format
        return _load_from_idea_input_dict(data)

    return []


def _load_from_idea_input_dict(data: dict) -> list[dict]:
    claims: list[dict] = []
    domain = data.get("domain", "")
    for hyp in data.get("hypotheses", []):
        claims.append({"text": hyp, "domain": domain, "source": "idea_input"})
    for method in data.get("proposed_methods", []):
        claims.append({"text": f"Proposed method: {method}", "domain": domain, "source": "idea_input"})
    for rq in data.get("research_questions", []):
        claims.append({"text": rq, "domain": domain, "source": "idea_input"})
    return _normalise(claims)


def _load_from_text(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    claims = _extract_with_llm(text)
    if not claims:
        # Fallback: each substantive line is a claim
        claims = [{"text": ln.strip()} for ln in text.splitlines() if len(ln.strip()) > 20]
    return _normalise(claims)


def _load_from_idea_input() -> list[dict]:
    default = OUTPUT_DIR / "idea_input.json"
    if default.exists():
        return _load_from_json(default)
    return []


# ── LLM extraction ────────────────────────────────────────────────────────────

def _extract_with_llm(text: str) -> list[dict]:
    try:
        from utils.llm_client import generate_json, is_available
    except ImportError:
        return []
    if not is_available():
        return []
    prompt = (
        "Extract all research claims, hypotheses, and propositions from the text below.\n"
        'Return JSON: {"claims": [{"text": "...", "domain": "...", "confidence": 0.0-1.0}]}\n\n'
        f"Text:\n{text[:4000]}"
    )
    result = generate_json(prompt)
    return result.get("claims", []) if result else []


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(raw: list) -> list[dict]:
    """Ensure every claim has the canonical fields."""
    out: list[dict] = []
    for i, item in enumerate(raw):
        if isinstance(item, str):
            c: dict = {"text": item}
        elif isinstance(item, dict):
            c = dict(item)
        else:
            continue

        # Unify the text field
        if "text" not in c:
            for alias in ("claim", "hypothesis", "statement", "proposition"):
                if alias in c:
                    c["text"] = c.pop(alias)
                    break

        c.setdefault("id", f"claim_{i + 1:03d}")
        c.setdefault("domain", "")
        c.setdefault("confidence", 1.0)
        c.setdefault("source", "user")
        c.setdefault("verified", None)

        if c.get("text"):
            out.append(c)
    return out

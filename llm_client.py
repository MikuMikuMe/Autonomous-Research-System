"""
LLM Client — Gemini API with optional Google Search grounding.
Uses the new Google Gen AI SDK (google-genai). See https://ai.google.dev/gemini-api/docs
Set GOOGLE_API_KEY or GEMINI_API_KEY. Use GEMINI_MODEL to override (default: gemini-3.1-pro-preview).
Loads .env automatically if python-dotenv is installed.
"""

import os
import json
import re

# Load .env if available (optional dependency)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Model: gemini-3.1-pro-preview for latest Pro; gemini-2.5-flash for speed
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

_client = None


def _get_client():
    """Lazy init of Gemini client (new google-genai SDK)."""
    global _client
    if _client is not None:
        return _client
    if not API_KEY:
        return None
    try:
        from google import genai
        _client = genai.Client(api_key=API_KEY)
        return _client
    except ImportError:
        return None
    except Exception as e:
        print(f"  [LLM] Gemini init failed: {e}")
        return None


def is_available():
    """Return True if Gemini API is configured and usable."""
    return _get_client() is not None


def generate(
    prompt: str,
    *,
    use_grounding: bool = False,
    system_instruction: str | None = None,
    max_output_tokens: int = 8192,
) -> str | None:
    """
    Generate a response from Gemini.
    If use_grounding=True and model supports it, uses Google Search for real-time info.
    Returns None on failure.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        from google.genai import types

        config_kwargs = {
            "max_output_tokens": max_output_tokens,
            "temperature": 0.2,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        if use_grounding:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt,
                config=config,
            )
        except Exception as grounding_err:
            if use_grounding:
                config_kwargs.pop("tools", None)
                config = types.GenerateContentConfig(**config_kwargs)
                response = client.models.generate_content(
                    model=DEFAULT_MODEL,
                    contents=prompt,
                    config=config,
                )
            else:
                raise grounding_err

        if response and response.text:
            return response.text.strip()
        return None
    except Exception as e:
        print(f"  [LLM] Generate failed: {e}")
        return None


def generate_with_grounding(prompt: str, system_instruction: str | None = None) -> str | None:
    """Generate with Google Search grounding for research/verification."""
    return generate(prompt, use_grounding=True, system_instruction=system_instruction)


def generate_json(prompt: str, system_instruction: str | None = None) -> dict | None:
    """Generate and parse JSON response. Extracts JSON from markdown code blocks if needed."""
    text = generate(prompt, system_instruction=system_instruction)
    if not text:
        return None
    # Extract JSON from ```json ... ``` if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

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

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-pro")
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


def _is_rate_limit_error(err: Exception) -> bool:
    """Detect rate-limit / quota-exceeded errors from the Gemini API."""
    err_str = str(err).lower()
    if "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str:
        return True
    type_name = type(err).__name__.lower()
    return "resourceexhausted" in type_name or "ratelimit" in type_name


def _call_with_fallback(client, prompt, config, config_kwargs, use_grounding):
    """Try DEFAULT_MODEL; on rate-limit, retry once with FALLBACK_MODEL."""
    from google.genai import types

    try:
        return _call_model(client, DEFAULT_MODEL, prompt, config, config_kwargs, use_grounding)
    except Exception as e:
        if _is_rate_limit_error(e) and FALLBACK_MODEL != DEFAULT_MODEL:
            print(f"  [LLM] Rate limit on {DEFAULT_MODEL}, falling back to {FALLBACK_MODEL}")
            return _call_model(client, FALLBACK_MODEL, prompt, config, config_kwargs, use_grounding)
        raise


def _call_model(client, model, prompt, config, config_kwargs, use_grounding):
    """Call a specific model, stripping grounding tools on failure if needed."""
    from google.genai import types

    try:
        return client.models.generate_content(
            model=model, contents=prompt, config=config,
        )
    except Exception as err:
        if use_grounding and not _is_rate_limit_error(err):
            config_kwargs.pop("tools", None)
            config = types.GenerateContentConfig(**config_kwargs)
            return client.models.generate_content(
                model=model, contents=prompt, config=config,
            )
        raise


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

        response = _call_with_fallback(
            client, prompt, config, config_kwargs, use_grounding,
        )

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

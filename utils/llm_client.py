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


# ---------------------------------------------------------------------------
# Output completeness guardrail — detect truncated LLM responses
# ---------------------------------------------------------------------------

# Patterns that suggest the response was cut off mid-sentence
_TRUNCATION_INDICATORS = re.compile(
    r"(?:"
    r"(?:the|a|an|this|that|in|on|at|by|for|with|of|to|from|and|or|but)\s*$"  # ends with preposition/article/conjunction
    r"|,\s*$"           # ends with trailing comma
    r"|\.\.\.\s*$"      # ends with ellipsis (but not a sentence)
    r"|—\s*$"           # ends with em-dash
    r"|–\s*$"           # ends with en-dash
    r")",
    re.IGNORECASE,
)

# Characters that indicate a properly terminated response
_SENTENCE_TERMINATORS = frozenset(".!?\")\u201d}")


def _looks_truncated(text: str, *, min_length: int = 80) -> bool:
    """Return True if *text* appears to have been cut off before completion.

    Heuristics (conservative — only flag high-confidence truncation):
    1. Text shorter than *min_length* when a longer response was expected.
    2. Last substantive character is not a sentence terminator.
    3. Ends with a dangling preposition, article, conjunction, comma, or dash.

    Short responses (< 40 chars) are exempt since some prompts legitimately
    produce brief output.
    """
    if not text or len(text.strip()) < 40:
        return False  # too short to judge meaningfully

    stripped = text.rstrip()
    if not stripped:
        return True

    # Strip trailing LaTeX closing braces / environments for the check
    check = re.sub(r"\\end\{[^}]+\}\s*$", "", stripped).rstrip()
    if not check:
        return False

    last_char = check[-1]
    if last_char in _SENTENCE_TERMINATORS:
        return False

    if _TRUNCATION_INDICATORS.search(check):
        return True

    # If it doesn't end with a terminator and is above min_length, flag it
    if len(stripped) >= min_length and last_char not in _SENTENCE_TERMINATORS:
        return True

    return False


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


_TRUNCATION_MAX_RETRIES = 2


def generate(
    prompt: str,
    *,
    use_grounding: bool = False,
    system_instruction: str | None = None,
    max_output_tokens: int = 8192,
    _truncation_check: bool = True,
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

        if not (response and response.text):
            return None

        text = response.text.strip()

        if not _truncation_check or not _looks_truncated(text):
            return text

        print(f"  [LLM] Truncation detected ({len(text)} chars, ends: '...{text[-40:]}'). Retrying...", flush=True)
        for retry in range(1, _TRUNCATION_MAX_RETRIES + 1):
            continuation_prompt = (
                f"{prompt}\n\n"
                "CRITICAL: Your previous response was truncated. "
                "You MUST output a COMPLETE response that ends with a full sentence (period, exclamation, or question mark). "
                "Do NOT end mid-sentence."
            )
            config_kwargs_retry = {**config_kwargs, "max_output_tokens": max_output_tokens + 1024}
            config_retry = types.GenerateContentConfig(**config_kwargs_retry)
            retry_response = _call_with_fallback(
                client, continuation_prompt, config_retry, config_kwargs_retry, use_grounding,
            )
            if retry_response and retry_response.text:
                retry_text = retry_response.text.strip()
                if not _looks_truncated(retry_text):
                    print(f"  [LLM] Truncation resolved on retry {retry}.", flush=True)
                    return retry_text
                print(f"  [LLM] Still truncated on retry {retry} ({len(retry_text)} chars).", flush=True)
                text = retry_text  # keep best attempt

        print(f"  [LLM] WARNING: Response still appears truncated after {_TRUNCATION_MAX_RETRIES} retries.", flush=True)
        return text
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

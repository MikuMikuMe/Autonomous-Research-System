"""
LLM Client — Backward-compatible wrapper around BaseLLMClient providers.

This module preserves the existing generate() / generate_json() / generate_with_grounding()
API so all agents continue to work without changes. Under the hood, it delegates
to the multi-provider BaseLLMClient system.

Set any of these to enable providers:
  - GOOGLE_API_KEY / GEMINI_API_KEY  → Gemini (default primary)
  - OPENAI_API_KEY                   → OpenAI / compatible endpoints
  - ANTHROPIC_API_KEY                → Anthropic Claude

Use LLM_PROVIDER to force a specific provider: gemini | openai | anthropic
"""

from __future__ import annotations

import json
import os
import re

from utils.llm_base import BaseLLMClient, LLMResponse, get_client, list_providers

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Allow forcing a specific provider
_FORCED_PROVIDER = os.environ.get("LLM_PROVIDER")


def _get_active_client() -> BaseLLMClient | None:
    """Get the active LLM client (respects LLM_PROVIDER env var)."""
    return get_client(_FORCED_PROVIDER)


def is_available() -> bool:
    """Return True if any LLM provider is configured and usable."""
    return _get_active_client() is not None


def generate(
    prompt: str,
    *,
    use_grounding: bool = False,
    system_instruction: str | None = None,
    max_output_tokens: int = 8192,
    _truncation_check: bool = True,
) -> str | None:
    """Generate a response from the best available LLM.

    Backward-compatible: returns str | None.
    """
    client = _get_active_client()
    if client is None:
        return None

    resp = client.generate(
        prompt,
        system_instruction=system_instruction,
        max_output_tokens=max_output_tokens,
        use_grounding=use_grounding,
    )
    if not resp or not resp.text:
        return None

    text = resp.text

    if not _truncation_check or not _looks_truncated(text):
        return text

    # Retry for truncation
    print(f"  [LLM] Truncation detected ({len(text)} chars). Retrying...", flush=True)
    for retry in range(1, 3):
        continuation_prompt = (
            f"{prompt}\n\n"
            "CRITICAL: Your previous response was truncated. "
            "You MUST output a COMPLETE response that ends with a full sentence."
        )
        retry_resp = client.generate(
            continuation_prompt,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens + 1024,
        )
        if retry_resp and retry_resp.text:
            if not _looks_truncated(retry_resp.text):
                print(f"  [LLM] Truncation resolved on retry {retry}.", flush=True)
                return retry_resp.text
            text = retry_resp.text

    print("  [LLM] WARNING: Response still truncated after retries.", flush=True)
    return text


def generate_multimodal(
    text_prompt: str,
    image_paths: list[str] | None = None,
    *,
    system_instruction: str | None = None,
    max_output_tokens: int = 8192,
) -> str | None:
    """Generate with optional images. Falls back to text-only if multimodal fails."""
    client = _get_active_client()
    if client is None:
        return None

    if image_paths and client.provider_name == "gemini":
        try:
            from utils.llm_base import GeminiClient
            from google.genai import types

            gemini: GeminiClient = client  # type: ignore[assignment]
            raw_client = gemini._get_client()
            if raw_client:
                parts: list = []
                for img_path in image_paths:
                    try:
                        from pathlib import Path as _Path
                        ext = _Path(img_path).suffix.lower()
                        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
                        mime = mime_map.get(ext, "image/png")
                        with open(img_path, "rb") as fh:
                            parts.append(types.Part(inline_data=types.Blob(mime_type=mime, data=fh.read())))
                    except Exception:
                        pass
                parts.append(types.Part(text=text_prompt))
                contents = [types.Content(role="user", parts=parts)]
                config_kwargs: dict = {"max_output_tokens": max_output_tokens, "temperature": 0.2}
                if system_instruction:
                    config_kwargs["system_instruction"] = system_instruction
                config = types.GenerateContentConfig(**config_kwargs)
                response = raw_client.models.generate_content(
                    model=gemini._default_model, contents=contents, config=config,
                )
                if response and response.text:
                    return response.text.strip()
        except Exception as e:
            print(f"  [LLM] Multimodal failed, falling back to text: {e}")

    return generate(text_prompt, system_instruction=system_instruction, max_output_tokens=max_output_tokens)


def generate_with_grounding(prompt: str, system_instruction: str | None = None) -> str | None:
    """Generate with web search grounding."""
    return generate(prompt, use_grounding=True, system_instruction=system_instruction)


def generate_json(prompt: str, system_instruction: str | None = None) -> dict | None:
    """Generate and parse JSON response."""
    text = generate(prompt, system_instruction=system_instruction)
    if not text:
        return None
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Truncation detection
# ---------------------------------------------------------------------------

_TRUNCATION_INDICATORS = re.compile(
    r"(?:"
    r"(?:the|a|an|this|that|in|on|at|by|for|with|of|to|from|and|or|but)\s*$"
    r"|,\s*$"
    r"|\.\.\.\s*$"
    r"|—\s*$"
    r"|–\s*$"
    r")",
    re.IGNORECASE,
)

_SENTENCE_TERMINATORS = frozenset(".!?\")\u201d}")


def _looks_truncated(text: str, *, min_length: int = 80) -> bool:
    if not text or len(text.strip()) < 40:
        return False
    stripped = text.rstrip()
    if not stripped:
        return True
    check = re.sub(r"\\end\{[^}]+\}\s*$", "", stripped).rstrip()
    if not check:
        return False
    last_char = check[-1]
    if last_char in _SENTENCE_TERMINATORS:
        return False
    if _TRUNCATION_INDICATORS.search(check):
        return True
    if len(stripped) >= min_length and last_char not in _SENTENCE_TERMINATORS:
        return True
    return False

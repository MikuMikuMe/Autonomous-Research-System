"""
BaseLLMClient — Abstract interface for LLM providers.

All LLM integrations implement this interface, enabling multi-provider
support, cost/quality tradeoffs, and vendor redundancy.

Usage:
    from utils.llm_base import get_client
    client = get_client()  # returns best available provider
    response = client.generate("Hello, world!")
"""

from __future__ import annotations

import os
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class LLMResponse:
    """Structured response from any LLM provider."""
    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)  # prompt_tokens, completion_tokens, etc.
    grounded: bool = False
    raw: Any = None  # provider-specific raw response


class BaseLLMClient(ABC):
    """Abstract base for all LLM providers."""

    provider_name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is configured and usable."""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        use_grounding: bool = False,
    ) -> LLMResponse | None:
        """Generate a text response. Returns None on failure."""
        ...

    def generate_json(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
    ) -> dict | None:
        """Generate and parse a JSON response."""
        resp = self.generate(
            prompt,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
        )
        if not resp or not resp.text:
            return None
        text = resp.text
        # Extract JSON from ```json ... ``` if present
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def generate_with_grounding(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
    ) -> LLMResponse | None:
        """Generate with web search grounding (if supported)."""
        return self.generate(
            prompt,
            system_instruction=system_instruction,
            use_grounding=True,
        )


class GeminiClient(BaseLLMClient):
    """Google Gemini provider using google-genai SDK."""

    provider_name = "gemini"

    def __init__(self) -> None:
        self._default_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self._fallback_model = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-pro")
        self._api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
            return self._client
        except ImportError:
            return None
        except Exception as e:
            print(f"  [Gemini] Init failed: {e}")
            return None

    def is_available(self) -> bool:
        return self._get_client() is not None

    def _is_rate_limit(self, err: Exception) -> bool:
        err_str = str(err).lower()
        if "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str:
            return True
        return "resourceexhausted" in type(err).__name__.lower()

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        use_grounding: bool = False,
    ) -> LLMResponse | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            from google.genai import types

            config_kwargs: dict[str, Any] = {
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            }
            if system_instruction:
                config_kwargs["system_instruction"] = system_instruction
            if use_grounding:
                config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

            config = types.GenerateContentConfig(**config_kwargs)

            # Try primary model, fallback on rate limit
            try:
                response = client.models.generate_content(
                    model=self._default_model, contents=prompt, config=config,
                )
            except Exception as e:
                if self._is_rate_limit(e) and self._fallback_model != self._default_model:
                    print(f"  [Gemini] Rate limit on {self._default_model}, falling back to {self._fallback_model}")
                    response = client.models.generate_content(
                        model=self._fallback_model, contents=prompt, config=config,
                    )
                elif use_grounding and not self._is_rate_limit(e):
                    # Retry without grounding
                    config_kwargs.pop("tools", None)
                    config = types.GenerateContentConfig(**config_kwargs)
                    response = client.models.generate_content(
                        model=self._default_model, contents=prompt, config=config,
                    )
                else:
                    raise

            if not (response and response.text):
                return None

            return LLMResponse(
                text=response.text.strip(),
                model=self._default_model,
                provider="gemini",
                grounded=use_grounding,
                raw=response,
            )
        except Exception as e:
            print(f"  [Gemini] Generate failed: {e}")
            return None


class OpenAIClient(BaseLLMClient):
    """OpenAI-compatible provider (works with OpenAI, Azure OpenAI, Ollama, vLLM, etc.)."""

    provider_name = "openai"

    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENAI_API_KEY")
        self._base_url = os.environ.get("OPENAI_BASE_URL")  # For compatible endpoints
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from openai import OpenAI
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
            return self._client
        except ImportError:
            return None
        except Exception as e:
            print(f"  [OpenAI] Init failed: {e}")
            return None

    def is_available(self) -> bool:
        return self._get_client() is not None

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        use_grounding: bool = False,
    ) -> LLMResponse | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            messages: list[dict[str, str]] = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_output_tokens,
                temperature=temperature,
            )
            text = response.choices[0].message.content
            if not text:
                return None
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            return LLMResponse(
                text=text.strip(),
                model=self._model,
                provider="openai",
                usage=usage,
                raw=response,
            )
        except Exception as e:
            print(f"  [OpenAI] Generate failed: {e}")
            return None


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude provider."""

    provider_name = "anthropic"

    def __init__(self) -> None:
        self._api_key = os.environ.get("ANTHROPIC_API_KEY")
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key)
            return self._client
        except ImportError:
            return None
        except Exception as e:
            print(f"  [Anthropic] Init failed: {e}")
            return None

    def is_available(self) -> bool:
        return self._get_client() is not None

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        use_grounding: bool = False,
    ) -> LLMResponse | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": max_output_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_instruction:
                kwargs["system"] = system_instruction

            response = client.messages.create(**kwargs)
            text = response.content[0].text if response.content else None
            if not text:
                return None
            usage = {}
            if response.usage:
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }
            return LLMResponse(
                text=text.strip(),
                model=self._model,
                provider="anthropic",
                usage=usage,
                raw=response,
            )
        except Exception as e:
            print(f"  [Anthropic] Generate failed: {e}")
            return None


# ---------------------------------------------------------------------------
# Provider registry + smart routing
# ---------------------------------------------------------------------------

# Priority order for provider selection
_PROVIDER_PRIORITY = ["gemini", "openai", "anthropic"]

_provider_instances: dict[str, BaseLLMClient] = {}


def _init_providers() -> None:
    """Initialize all configured providers (lazy, once)."""
    if _provider_instances:
        return
    for name, cls in [("gemini", GeminiClient), ("openai", OpenAIClient), ("anthropic", AnthropicClient)]:
        instance = cls()
        if instance.is_available():
            _provider_instances[name] = instance


def get_client(provider: str | None = None) -> BaseLLMClient | None:
    """Get the best available LLM client, or a specific provider.

    Args:
        provider: Force a specific provider ("gemini", "openai", "anthropic").
                  If None, returns the first available by priority.

    Returns:
        BaseLLMClient instance or None if no providers are available.
    """
    _init_providers()
    if provider:
        return _provider_instances.get(provider)
    for name in _PROVIDER_PRIORITY:
        if name in _provider_instances:
            return _provider_instances[name]
    return None


def list_providers() -> list[str]:
    """Return names of all available providers."""
    _init_providers()
    return list(_provider_instances.keys())

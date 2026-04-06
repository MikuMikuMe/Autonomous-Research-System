"""
Multi-LLM Client — LangChain ChatModel abstraction for provider-agnostic LLM access.

Abstracts all LLM providers (Gemini, OpenAI, Anthropic, etc.) through LangChain's
ChatModel interface, making provider swapping a config file change.

Provider is selected via configs/pipeline.yaml -> llm.provider or env vars:
  LLM_PROVIDER=google|openai|anthropic|ollama
  GOOGLE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.

Falls back to the legacy google-genai client if LangChain is not installed.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseLLMClient(ABC):
    """Interface that all LLM backends must implement."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        use_grounding: bool = False,
    ) -> str | None:
        ...

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
    ) -> dict | None:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


# ---------------------------------------------------------------------------
# LangChain-based implementation
# ---------------------------------------------------------------------------

class LangChainLLMClient(BaseLLMClient):
    """LLM client backed by any LangChain ChatModel."""

    def __init__(
        self,
        provider: str = "google",
        model: str | None = None,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._provider = provider
        self._model_name = model
        self._fallback_provider = fallback_provider
        self._fallback_model = fallback_model
        self._kwargs = kwargs
        self._chat_model = None
        self._fallback_chat_model = None
        self._available: bool | None = None

    def _build_chat_model(self, provider: str, model: str | None, **extra: Any):
        """Construct the appropriate LangChain ChatModel for the given provider."""
        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                google_api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"),
                temperature=extra.get("temperature", 0.2),
                max_output_tokens=extra.get("max_output_tokens", 8192),
            )
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model or os.environ.get("OPENAI_MODEL", "gpt-4o"),
                api_key=os.environ.get("OPENAI_API_KEY"),
                temperature=extra.get("temperature", 0.2),
                max_tokens=extra.get("max_output_tokens", 8192),
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                temperature=extra.get("temperature", 0.2),
                max_tokens=extra.get("max_output_tokens", 8192),
            )
        elif provider == "ollama":
            from langchain_community.chat_models import ChatOllama
            return ChatOllama(
                model=model or os.environ.get("OLLAMA_MODEL", "llama3"),
                base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=extra.get("temperature", 0.2),
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _get_model(self):
        if self._chat_model is not None:
            return self._chat_model
        try:
            self._chat_model = self._build_chat_model(
                self._provider, self._model_name, **self._kwargs
            )
            return self._chat_model
        except Exception as e:
            print(f"  [LLM] Failed to init {self._provider}: {e}")
            return None

    def _get_fallback(self):
        if self._fallback_chat_model is not None:
            return self._fallback_chat_model
        if not self._fallback_provider:
            return None
        try:
            self._fallback_chat_model = self._build_chat_model(
                self._fallback_provider, self._fallback_model, **self._kwargs
            )
            return self._fallback_chat_model
        except Exception as e:
            print(f"  [LLM] Failed to init fallback {self._fallback_provider}: {e}")
            return None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            model = self._get_model()
            self._available = model is not None
        except Exception:
            self._available = False
        return self._available

    @property
    def provider_name(self) -> str:
        return self._provider

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        use_grounding: bool = False,
    ) -> str | None:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = self._get_model()
        if model is None:
            return None

        messages = []
        if system_instruction:
            messages.append(SystemMessage(content=system_instruction))
        messages.append(HumanMessage(content=prompt))

        try:
            response = model.invoke(messages)
            text = response.content if hasattr(response, "content") else str(response)
            return text.strip() if text else None
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate" in err_str or "quota" in err_str
            if is_rate_limit:
                fallback = self._get_fallback()
                if fallback:
                    print(f"  [LLM] Rate limit on {self._provider}, trying fallback...")
                    try:
                        response = fallback.invoke(messages)
                        text = response.content if hasattr(response, "content") else str(response)
                        return text.strip() if text else None
                    except Exception as e2:
                        print(f"  [LLM] Fallback also failed: {e2}")
            print(f"  [LLM] Generate failed: {e}")
            return None

    def generate_json(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
    ) -> dict | None:
        text = self.generate(prompt, system_instruction=system_instruction)
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
# Legacy Gemini client (backward compatible)
# ---------------------------------------------------------------------------

class LegacyGeminiClient(BaseLLMClient):
    """Wraps the original google-genai client for backward compatibility."""

    def __init__(self) -> None:
        self._delegate = None

    def _ensure_delegate(self):
        if self._delegate is not None:
            return
        try:
            from utils import llm_client as legacy
            self._delegate = legacy
        except ImportError:
            pass

    def is_available(self) -> bool:
        self._ensure_delegate()
        return self._delegate is not None and self._delegate.is_available()

    @property
    def provider_name(self) -> str:
        return "google-legacy"

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
        use_grounding: bool = False,
    ) -> str | None:
        self._ensure_delegate()
        if not self._delegate:
            return None
        return self._delegate.generate(
            prompt,
            use_grounding=use_grounding,
            system_instruction=system_instruction,
            max_output_tokens=max_output_tokens,
        )

    def generate_json(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
    ) -> dict | None:
        self._ensure_delegate()
        if not self._delegate:
            return None
        return self._delegate.generate_json(prompt, system_instruction=system_instruction)


# ---------------------------------------------------------------------------
# Client registry / factory
# ---------------------------------------------------------------------------

def _load_llm_config() -> dict:
    """Load LLM config from configs/pipeline.yaml."""
    try:
        import yaml
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "configs", "pipeline.yaml",
        )
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("llm", {})
    except Exception:
        pass
    return {}


_default_client: BaseLLMClient | None = None


def get_llm_client() -> BaseLLMClient:
    """Get the configured LLM client (singleton). Uses LangChain if available, else legacy."""
    global _default_client
    if _default_client is not None:
        return _default_client

    cfg = _load_llm_config()
    provider = os.environ.get("LLM_PROVIDER", cfg.get("provider", "google"))
    model = os.environ.get("LLM_MODEL") or cfg.get("model")
    fallback_provider = cfg.get("fallback_provider")
    fallback_model = cfg.get("fallback_model")

    try:
        _default_client = LangChainLLMClient(
            provider=provider,
            model=model,
            fallback_provider=fallback_provider,
            fallback_model=fallback_model,
        )
        return _default_client
    except Exception:
        _default_client = LegacyGeminiClient()
        return _default_client


def reset_client() -> None:
    """Reset the singleton (for testing or provider switching)."""
    global _default_client
    _default_client = None


# ---------------------------------------------------------------------------
# Convenience functions (drop-in replacements for utils.llm_client)
# ---------------------------------------------------------------------------

def generate(
    prompt: str,
    *,
    use_grounding: bool = False,
    system_instruction: str | None = None,
    max_output_tokens: int = 8192,
    _truncation_check: bool = True,
) -> str | None:
    """Generate text using the configured LLM provider."""
    client = get_llm_client()
    return client.generate(
        prompt,
        system_instruction=system_instruction,
        max_output_tokens=max_output_tokens,
        use_grounding=use_grounding,
    )


def generate_json(prompt: str, system_instruction: str | None = None) -> dict | None:
    """Generate and parse JSON response."""
    client = get_llm_client()
    return client.generate_json(prompt, system_instruction=system_instruction)


def generate_with_grounding(prompt: str, system_instruction: str | None = None) -> str | None:
    """Generate with web search grounding."""
    return generate(prompt, use_grounding=True, system_instruction=system_instruction)


def is_available() -> bool:
    """Return True if any LLM provider is configured and usable."""
    return get_llm_client().is_available()

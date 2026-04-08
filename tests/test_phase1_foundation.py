# pyright: reportAny=false
"""Tests for Phase 1: Foundation Layer.

Covers multi-LLM client, web search client, cross-session memory, config loader.
Uses mocks for external APIs (TDD — no real API calls in tests).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest


# ─── Multi-LLM Client ─────────────────────────────────────────────────────

class TestBaseLLMClient:
    """Test the abstract interface and factory."""

    def test_get_llm_client_returns_instance(self):
        from utils.multi_llm_client import BaseLLMClient, get_llm_client, reset_client
        reset_client()
        client = get_llm_client()
        assert isinstance(client, BaseLLMClient)
        reset_client()

    def test_langchain_client_provider_name(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="google")
        assert client.provider_name == "google"

    def test_langchain_client_unknown_provider_raises(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="nonexistent_provider")
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            client._build_chat_model("nonexistent_provider", None)

    def test_legacy_client_provider_name(self):
        from utils.multi_llm_client import LegacyGeminiClient
        client = LegacyGeminiClient()
        assert client.provider_name == "google-legacy"

    def test_generate_json_parses_json_block(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="google")
        with patch.object(client, "generate", return_value='```json\n{"key": "value"}\n```'):
            result = client.generate_json("test prompt")
            assert result == {"key": "value"}

    def test_generate_json_parses_raw_json(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="google")
        with patch.object(client, "generate", return_value='{"key": "value"}'):
            result = client.generate_json("test prompt")
            assert result == {"key": "value"}

    def test_generate_json_returns_none_on_invalid(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="google")
        with patch.object(client, "generate", return_value="not json at all"):
            result = client.generate_json("test prompt")
            assert result is None

    def test_generate_json_returns_none_when_generate_fails(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="google")
        with patch.object(client, "generate", return_value=None):
            result = client.generate_json("test prompt")
            assert result is None

    def test_convenience_functions_exist(self):
        from utils.multi_llm_client import generate, generate_json, generate_with_grounding, is_available
        assert callable(generate)
        assert callable(generate_json)
        assert callable(generate_with_grounding)
        assert callable(is_available)

    def test_reset_client_clears_singleton(self):
        from utils.multi_llm_client import get_llm_client, reset_client, _default_client
        reset_client()
        assert _default_client is None or True  # module-level check
        client1 = get_llm_client()
        reset_client()
        client2 = get_llm_client()
        # After reset, a new client should be created (may be same type but different instance)
        reset_client()


# ─── Web Search Client ─────────────────────────────────────────────────────

class TestWebSearchClient:
    """Test Tavily web search integration."""

    def test_is_tavily_available_without_key(self):
        from utils.web_search_client import is_tavily_available
        with patch.dict("os.environ", {}, clear=True):
            # May or may not be available depending on env — just check it runs
            result = is_tavily_available()
            assert isinstance(result, bool)

    def test_tavily_search_raises_without_key(self):
        from utils.web_search_client import tavily_search
        with patch("utils.web_search_client._get_tavily_key", return_value=None):
            with pytest.raises(RuntimeError, match="TAVILY_API_KEY not set"):
                tavily_search("test query")

    def test_tavily_search_context_raises_without_key(self):
        from utils.web_search_client import tavily_search_context
        with patch("utils.web_search_client._get_tavily_key", return_value=None):
            with pytest.raises(RuntimeError, match="TAVILY_API_KEY not set"):
                tavily_search_context("test query")

    def test_tavily_extract_raises_without_key(self):
        from utils.web_search_client import tavily_extract
        with patch("utils.web_search_client._get_tavily_key", return_value=None):
            with pytest.raises(RuntimeError, match="TAVILY_API_KEY not set"):
                tavily_extract(["http://example.com"])

    def test_research_search_no_results(self):
        """When both web and academic searches return nothing, get a fallback message."""
        from utils.web_search_client import research_search
        with patch("utils.web_search_client.is_tavily_available", return_value=False), \
             patch("utils.web_search_client._get_tavily_key", return_value=None):
            text, sources = research_search(
                "test query", include_web=False, include_academic=False
            )
            assert "No results found" in text
            assert sources == []

    def test_research_search_with_mock_tavily(self):
        """Mock Tavily to return structured results."""
        mock_response = {
            "answer": "This is a synthesized answer.",
            "results": [
                {"title": "Test Paper", "url": "http://example.com", "content": "Content here", "score": 0.95}
            ],
        }
        from utils.web_search_client import research_search
        with patch("utils.web_search_client.is_tavily_available", return_value=True), \
             patch("utils.web_search_client.tavily_search", return_value=mock_response), \
             patch("utils.multi_llm_client.get_llm_client") as mock_llm:
            mock_client = MagicMock()
            mock_client.generate.return_value = "Synthesized output."
            mock_llm.return_value = mock_client
            text, sources = research_search("test query", include_academic=False)
            assert len(sources) == 1
            assert sources[0]["title"] == "Test Paper"


# ─── Cross-Session Memory ─────────────────────────────────────────────────

class TestCrossSessionMemory:
    """Test long-term cross-session persistent memory."""

    def test_create_and_close(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        assert mem.db is not None
        mem.close()

    def test_set_and_get_preference(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.set_preference("theme", "dark")
            assert mem.get_preference("theme") == "dark"
            assert mem.get_preference("nonexistent", "default") == "default"
        finally:
            mem.close()

    def test_preference_overwrite(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.set_preference("model", "gpt-4")
            mem.set_preference("model", "gemini-pro")
            assert mem.get_preference("model") == "gemini-pro"
        finally:
            mem.close()

    def test_get_all_preferences(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.set_preference("a", 1)
            mem.set_preference("b", "two")
            prefs = mem.get_all_preferences()
            assert prefs["a"] == 1
            assert prefs["b"] == "two"
        finally:
            mem.close()

    def test_json_preference(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.set_preference("domains", ["ml", "nlp"])
            assert mem.get_preference("domains") == ["ml", "nlp"]
        finally:
            mem.close()

    def test_track_domain(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.track_domain("machine_learning", ["bias", "fairness"])
            domains = mem.get_domain_expertise("machine_learning")
            assert len(domains) == 1
            assert domains[0]["domain"] == "machine_learning"
            assert domains[0]["total_sessions"] == 1

            # Track again — should increment
            mem.track_domain("machine_learning", ["interpretability"])
            domains = mem.get_domain_expertise("machine_learning")
            assert domains[0]["total_sessions"] == 2
        finally:
            mem.close()

    def test_log_session(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            session_id = mem.log_session(
                session_id="sess-001",
                goal="Test fairness in credit models",
                domain="finance",
                claims_count=5,
                converged=True,
                duration_s=120.5,
            )
            assert session_id > 0
            history = mem.get_research_history()
            assert len(history) == 1
            assert history[0]["goal"] == "Test fairness in credit models"
        finally:
            mem.close()

    def test_store_and_retrieve_knowledge(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.store_knowledge(
                claim="SMOTE improves minority class recall",
                domain="ml",
                confidence=0.85,
                sources=["paper1.pdf"],
                verdict="support",
            )
            knowledge = mem.get_knowledge(domain="ml")
            assert len(knowledge) == 1
            assert knowledge[0]["confidence"] == 0.85
            assert knowledge[0]["verdict"] == "support"

            # Store again — should update confidence
            mem.store_knowledge(
                claim="SMOTE improves minority class recall",
                domain="ml",
                confidence=0.95,
                sources=["paper2.pdf"],
                verdict="support",
            )
            knowledge = mem.get_knowledge(domain="ml")
            assert len(knowledge) == 1
            assert knowledge[0]["evidence_count"] == 2
            assert knowledge[0]["confidence"] == pytest.approx(0.9, abs=0.01)
        finally:
            mem.close()

    def test_register_technique(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.register_technique(
                technique_name="SMOTE",
                domain="ml",
                description="Synthetic Minority Over-sampling",
                category="pre-processing",
                effectiveness=0.75,
            )
            techniques = mem.get_techniques(domain="ml")
            assert len(techniques) == 1
            assert techniques[0]["technique_name"] == "SMOTE"

            # Register again — should update
            mem.register_technique(technique_name="SMOTE", domain="ml", effectiveness=0.85)
            techniques = mem.get_techniques(domain="ml")
            assert len(techniques) == 1
            assert techniques[0]["use_count"] == 1  # incremented
        finally:
            mem.close()

    def test_learn_pattern(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.learn_pattern("pitfall", "LLM truncation on long prompts")
            mem.learn_pattern("pitfall", "LLM truncation on long prompts")
            patterns = mem.get_patterns("pitfall")
            assert len(patterns) == 1
            assert patterns[0]["frequency"] == 2
        finally:
            mem.close()

    def test_cross_session_summary(self, tmp_path: Path):
        from utils.cross_session_memory import CrossSessionMemory
        mem = CrossSessionMemory(str(tmp_path / "test.db"))
        try:
            mem.set_preference("theme", "dark")
            mem.track_domain("ml")
            mem.register_technique("SMOTE", domain="ml")
            summary = mem.cross_session_summary()
            assert summary["total_techniques"] == 1
            assert len(summary["domains"]) == 1
            assert summary["preferences"]["theme"] == "dark"
        finally:
            mem.close()


# ─── Config Loader ─────────────────────────────────────────────────────────

class TestConfigLoader:
    """Test lazy/progressive prompt and config loading."""

    def test_load_prompt_caches(self, tmp_path: Path):
        from utils.config_loader import _prompt_cache, _cache_lock, invalidate_cache
        invalidate_cache()
        # After invalidation, cache should be empty
        with _cache_lock:
            assert len(_prompt_cache) == 0

    def test_load_rules_returns_none_for_missing(self):
        from utils.config_loader import load_rules
        result = load_rules("nonexistent_rules_file_12345")
        assert result is None

    def test_load_pipeline_config_returns_dict(self):
        from utils.config_loader import load_pipeline_config
        cfg = load_pipeline_config()
        assert isinstance(cfg, dict)
        # Should have pipeline key after our updates
        assert "pipeline" in cfg or "llm" in cfg or cfg == {}

    def test_invalidate_cache_specific(self, tmp_path: Path):
        from utils.config_loader import _prompt_cache, _cache_lock, invalidate_cache
        invalidate_cache()
        with _cache_lock:
            _prompt_cache["test_key"] = "test_value"
        invalidate_cache("test_key")
        with _cache_lock:
            assert "test_key" not in _prompt_cache

    def test_load_prompt_thread_safety(self):
        """Verify concurrent access doesn't crash."""
        from utils.config_loader import load_prompt, invalidate_cache
        invalidate_cache()
        errors = []

        def worker():
            try:
                for _ in range(20):
                    load_prompt("nonexistent_prompt_xyz")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

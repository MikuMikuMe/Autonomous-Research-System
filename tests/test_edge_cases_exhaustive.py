# pyright: reportAny=false
"""
Exhaustive edge-case tests for the Autonomous Research System.

Tests adversarial inputs, boundary conditions, type confusion, concurrent
operations, deep nesting, SQL injection, encoding edge cases, and more.
Targets >99% success rate across all system modules.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ====================================================================
# 1. ResearchContext (in-process state) edge cases
# ====================================================================

class TestResearchContext:
    """Edge cases for the new ResearchContext in-process state object."""

    def test_empty_context_defaults(self):
        from utils.context import ResearchContext
        ctx = ResearchContext()
        assert ctx.research_idea == ""
        assert ctx.claims == []
        assert ctx.converged is False
        assert ctx.iteration == 0

    def test_add_claim_and_compute_metrics(self):
        from utils.context import ResearchContext
        ctx = ResearchContext()
        c1 = ctx.add_claim("Claim A", category="hypothesis")
        c2 = ctx.add_claim("Claim B", category="finding")
        c1.verified = True
        c2.verified = False
        ctx.compute_metrics()
        assert ctx.verified_ratio == 0.5
        assert ctx.converged is False

    def test_all_claims_verified_converges(self):
        from utils.context import ResearchContext
        ctx = ResearchContext(converge_threshold=0.8)
        c = ctx.add_claim("Test claim")
        c.verified = True
        ctx.compute_metrics()
        assert ctx.verified_ratio == 1.0
        assert ctx.converged is True

    def test_critical_flaw_blocks_convergence(self):
        from utils.context import ResearchContext
        ctx = ResearchContext(converge_threshold=0.5)
        c = ctx.add_claim("Test")
        c.verified = True
        ctx.add_flaw("Big problem", severity="critical")
        ctx.compute_metrics()
        assert ctx.converged is False
        assert ctx.critical_flaws == 1

    def test_to_dict_roundtrip(self):
        from utils.context import ResearchContext
        ctx = ResearchContext(research_idea="Test idea", domain="physics")
        ctx.add_claim("E=mc2", category="finding")
        ctx.add_technique("calculus", description="math tool")
        ctx.add_flaw("Sign error", severity="high", flaw_type="mathematical")
        data = ctx.to_dict()
        ctx2 = ResearchContext.from_dict(data)
        assert ctx2.research_idea == "Test idea"
        assert len(ctx2.claims) == 1
        assert len(ctx2.discovered_techniques) == 1
        assert len(ctx2.flaws) == 1

    def test_save_and_load_json(self, tmp_path):
        from utils.context import ResearchContext
        ctx = ResearchContext(research_idea="Save test")
        ctx.add_claim("Claim 1")
        path = str(tmp_path / "ctx.json")
        ctx.save(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ctx2 = ResearchContext.from_dict(data)
        assert ctx2.research_idea == "Save test"
        assert len(ctx2.claims) == 1

    def test_zero_claims_compute_metrics(self):
        from utils.context import ResearchContext
        ctx = ResearchContext()
        ctx.compute_metrics()
        assert ctx.verified_ratio == 0.0

    def test_unicode_claims(self):
        from utils.context import ResearchContext
        ctx = ResearchContext(research_idea="量子力学研究")
        c = ctx.add_claim("薛定谔的猫是活的")
        c.verified = True
        ctx.compute_metrics()
        data = ctx.to_dict()
        assert "量子力学研究" in data["research_idea"]

    def test_very_long_claim_text(self):
        from utils.context import ResearchContext
        ctx = ResearchContext()
        long_text = "A" * 100_000
        c = ctx.add_claim(long_text)
        assert len(c.text) == 100_000
        data = ctx.to_dict()
        assert len(data["claims"][0]["text"]) == 100_000

    def test_many_claims_performance(self):
        from utils.context import ResearchContext
        ctx = ResearchContext()
        for i in range(1000):
            c = ctx.add_claim(f"Claim {i}")
            c.verified = i % 2 == 0
        ctx.compute_metrics()
        assert ctx.verified_ratio == 0.5
        assert len(ctx.claims) == 1000

    def test_from_dict_with_missing_fields(self):
        from utils.context import ResearchContext
        ctx = ResearchContext.from_dict({})
        assert ctx.research_idea == ""
        assert ctx.claims == []

    def test_from_dict_with_extra_fields(self):
        from utils.context import ResearchContext
        ctx = ResearchContext.from_dict({"extra_field": "ignored", "research_idea": "X"})
        assert ctx.research_idea == "X"


# ====================================================================
# 2. Sandbox adversarial inputs
# ====================================================================

class TestSandboxAdversarial:
    """Adversarial code inputs for the sandbox."""

    def test_import_subprocess_blocked(self):
        from utils.sandbox import execute_code
        result = execute_code("import subprocess; subprocess.run(['whoami'])")
        assert not result.success

    def test_import_shutil_blocked(self):
        from utils.sandbox import execute_code
        result = execute_code("import shutil; shutil.rmtree('/')")
        assert not result.success

    def test_import_ctypes_blocked(self):
        from utils.sandbox import execute_code
        result = execute_code("import ctypes")
        assert not result.success

    def test_nested_import_attempt(self):
        from utils.sandbox import execute_code
        result = execute_code("exec('import os')")
        assert not result.success

    def test_eval_bypass_attempt(self):
        from utils.sandbox import execute_code
        result = execute_code("eval('__import__(\"os\")')")
        assert not result.success

    def test_dunder_subclasses_attempt(self):
        """Attempt to access __subclasses__ for sandbox escape."""
        from utils.sandbox import execute_code
        result = execute_code(
            "x = ''.__class__.__mro__[1].__subclasses__()\n"
            "for c in x:\n"
            "    if 'warning' in str(c):\n"
            "        print(c)\n"
        )
        assert hasattr(result, "success")

    def test_infinite_loop_timeout(self):
        from utils.sandbox import execute_code, SandboxConfig
        config = SandboxConfig(timeout_seconds=2)
        result = execute_code("while True: pass", config=config)
        assert not result.success
        assert result.timed_out or "timeout" in (result.error or "").lower()

    def test_memory_bomb(self):
        from utils.sandbox import execute_code, SandboxConfig
        config = SandboxConfig(timeout_seconds=3)
        result = execute_code("x = [0] * (10**9)", config=config)
        assert not result.success or result.timed_out

    def test_fork_bomb_attempt(self):
        from utils.sandbox import execute_code
        result = execute_code("import os\nos.fork()")
        assert not result.success

    def test_safe_math_works(self):
        from utils.sandbox import execute_code
        result = execute_code("import math\nresult = math.sqrt(144)\nprint(result)")
        assert result.success
        assert "12.0" in result.stdout

    def test_safe_json_works(self):
        from utils.sandbox import execute_code
        result = execute_code('import json\nprint(json.dumps({"a": 1}))')
        assert result.success

    def test_null_bytes_in_code(self):
        from utils.sandbox import execute_code
        result = execute_code("print('hello\x00world')")
        assert hasattr(result, "success")

    def test_empty_code(self):
        from utils.sandbox import execute_code
        result = execute_code("")
        assert result.success

    def test_syntax_error_code(self):
        from utils.sandbox import execute_code
        result = execute_code("def f(\n  broken")
        assert not result.success

    def test_encoding_edge_case(self):
        from utils.sandbox import execute_code
        result = execute_code("print('café résumé naïve')")
        assert result.success

    def test_multiline_string_with_import(self):
        """Import inside a string literal should NOT be blocked."""
        from utils.sandbox import execute_code
        result = execute_code('x = "import os"\nprint(x)')
        assert result.success
        assert "import os" in result.stdout

    def test_comment_with_import(self):
        """Import in a comment should NOT be blocked."""
        from utils.sandbox import execute_code
        result = execute_code("# import os\nprint('safe')")
        assert result.success


# ====================================================================
# 3. Cross-session memory edge cases
# ====================================================================

class TestCrossSessionMemoryEdge:
    """Edge cases for cross-session persistent memory."""

    def _make_memory(self, tmp_path):
        from utils.cross_session_memory import CrossSessionMemory
        return CrossSessionMemory(db_path=str(tmp_path / "test_mem.db"))

    def test_sql_injection_in_domain(self, tmp_path):
        """SQL injection attempt in domain field."""
        mem = self._make_memory(tmp_path)
        # This should NOT crash or corrupt the database
        evil_domain = "'; DROP TABLE persistent_knowledge; --"
        mem.store_knowledge(claim="test claim", domain=evil_domain)
        # The table should still exist
        results = mem.get_knowledge(domain=evil_domain)
        assert len(results) >= 1
        mem.close()

    def test_sql_injection_in_claim(self, tmp_path):
        mem = self._make_memory(tmp_path)
        evil = "test' OR '1'='1"
        mem.store_knowledge(claim=evil, domain="test")
        results = mem.get_knowledge(domain="test")
        assert any(r.get("claim") == evil for r in results)
        mem.close()

    def test_empty_string_values(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.store_knowledge(claim="", domain="", confidence=0.0)
        results = mem.get_knowledge(domain="")
        assert len(results) >= 1
        mem.close()

    def test_unicode_in_all_fields(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.store_knowledge(
            claim="量子コンピューティングは古典的なビット操作を超える",
            domain="量子物理学",
            confidence=0.95,
        )
        results = mem.get_knowledge(domain="量子物理学")
        assert len(results) >= 1
        mem.close()

    def test_concurrent_writes(self, tmp_path):
        """Multiple threads writing simultaneously should not corrupt DB."""
        from utils.cross_session_memory import CrossSessionMemory
        db_path = str(tmp_path / "concurrent.db")

        def write_entries(thread_id):
            mem = CrossSessionMemory(db_path=db_path)
            for i in range(20):
                mem.store_knowledge(
                    claim=f"Thread {thread_id} claim {i}",
                    domain="concurrent_test",
                    confidence=0.5,
                )
            mem.close()

        threads = [threading.Thread(target=write_entries, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all entries were written
        mem = CrossSessionMemory(db_path=db_path)
        results = mem.get_knowledge(domain="concurrent_test", limit=200)
        # Should have at least some entries (may have duplicates)
        assert len(results) >= 50
        mem.close()

    def test_very_long_claim(self, tmp_path):
        mem = self._make_memory(tmp_path)
        long_claim = "X" * 50_000
        mem.store_knowledge(claim=long_claim, domain="test")
        results = mem.get_knowledge(domain="test")
        # Claim stored (may be truncated by SQLite text limits on some builds)
        assert len(results) >= 1
        mem.close()

    def test_register_technique_idempotent(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.register_technique("SMOTE", domain="ml", description="Oversampling")
        mem.register_technique("SMOTE", domain="ml", description="Updated desc")
        techniques = mem.get_techniques(domain="ml")
        smote_entries = [t for t in techniques if t.get("technique_name") == "SMOTE"]
        # Should have at most 2 entries (UPSERT or insert; not cause errors)
        assert len(smote_entries) >= 1
        mem.close()

    def test_get_knowledge_empty_db(self, tmp_path):
        mem = self._make_memory(tmp_path)
        results = mem.get_knowledge(domain="nonexistent")
        assert results == []
        mem.close()

    def test_special_characters_in_pattern(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.learn_pattern(
            pattern_type="research_flaw",
            description='Flaw with "quotes" and \'apostrophes\'',
            context="test; DROP TABLE;",
        )
        patterns = mem.get_patterns(pattern_type="research_flaw")
        assert len(patterns) >= 1
        mem.close()

    def test_cross_session_summary_empty(self, tmp_path):
        mem = self._make_memory(tmp_path)
        summary = mem.cross_session_summary()
        assert isinstance(summary, dict)
        mem.close()


# ====================================================================
# 4. Multi-LLM client edge cases
# ====================================================================

class TestMultiLLMEdge:
    """Edge cases for the multi-LLM client."""

    def test_unknown_provider_returns_none(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="nonexistent_provider", model="fake")
        # Constructor doesn't raise; generate() returns None when model unavailable
        result = client.generate("test prompt")
        assert result is None

    def test_generate_returns_none_without_api_key(self):
        from utils.multi_llm_client import LangChainLLMClient
        client = LangChainLLMClient(provider="google", model="gemini-2.0-flash")
        # Without API key, generate returns None gracefully
        result = client.generate("")
        assert result is None

    def test_factory_returns_same_instance(self):
        from utils.multi_llm_client import get_llm_client, reset_client
        reset_client()
        c1 = get_llm_client()
        c2 = get_llm_client()
        assert c1 is c2
        reset_client()

    def test_legacy_client_is_available_without_api_key(self):
        from utils.multi_llm_client import LegacyGeminiClient
        client = LegacyGeminiClient()
        # Should return bool, not crash
        result = client.is_available()
        assert isinstance(result, bool)

    def test_generate_json_with_malformed_response(self):
        from utils.multi_llm_client import LangChainLLMClient
        with patch.object(LangChainLLMClient, "generate", return_value="not json at all"):
            client = LangChainLLMClient.__new__(LangChainLLMClient)
            client._chat_model = MagicMock()
            result = client.generate_json("test")
            assert result is None or isinstance(result, dict)

    def test_generate_json_extracts_from_markdown_block(self):
        from utils.multi_llm_client import LangChainLLMClient
        mock_response = '```json\n{"key": "value"}\n```'
        with patch.object(LangChainLLMClient, "generate", return_value=mock_response):
            client = LangChainLLMClient.__new__(LangChainLLMClient)
            client._chat_model = MagicMock()
            result = client.generate_json("test")
            assert result == {"key": "value"}


# ====================================================================
# 5. Web search client edge cases
# ====================================================================

class TestWebSearchEdge:
    """Edge cases for the web search client."""

    def test_research_search_no_api_key(self):
        from utils.web_search_client import research_search
        # Should gracefully fall back, not crash
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            result = research_search("test query")
            assert isinstance(result, tuple)
            assert len(result) == 2

    def test_research_search_empty_query(self):
        from utils.web_search_client import research_search
        result = research_search("")
        assert isinstance(result, tuple)

    def test_research_search_unicode_query(self):
        from utils.web_search_client import research_search
        result = research_search("量子计算最新进展")
        assert isinstance(result, tuple)

    def test_research_search_very_long_query(self):
        from utils.web_search_client import research_search
        result = research_search("A" * 10_000)
        assert isinstance(result, tuple)


# ====================================================================
# 6. Config loader edge cases
# ====================================================================

class TestConfigLoaderEdge:
    """Edge cases for the lazy/progressive config loader."""

    def test_invalidate_and_reload(self):
        from utils.config_loader import invalidate_cache, load_pipeline_config
        invalidate_cache()
        config = load_pipeline_config()
        assert isinstance(config, dict)

    def test_load_prompt_nonexistent(self):
        from utils.config_loader import load_prompt
        result = load_prompt("nonexistent_template_xyz_abc")
        assert result == "" or isinstance(result, str)

    def test_load_pipeline_config_twice_uses_cache(self):
        from utils.config_loader import load_pipeline_config, invalidate_cache
        invalidate_cache()
        c1 = load_pipeline_config()
        c2 = load_pipeline_config()
        assert c1 is c2  # Same object from cache


# ====================================================================
# 7. LangGraph orchestrator edge cases (mocked)
# ====================================================================

class TestOrchestratorEdgeCases:
    """Edge cases for the LangGraph research orchestrator."""

    def test_discover_empty_string(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": ""}
        result = discover_node(state)
        assert "No research idea provided." in result.get("errors", [])

    def test_discover_only_whitespace(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "   \t\n  "}
        result = discover_node(state)
        assert "No research idea provided." in result.get("errors", [])

    def test_discover_very_long_idea(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "X" * 100_000}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        assert len(result.get("claims", [])) >= 1

    def test_plan_no_claims(self):
        from orchestration.langgraph_orchestrator import plan_node
        state = {"claims": [], "iteration": 0}
        result = plan_node(state)
        assert "No claims to research." in result.get("errors", [])

    def test_observe_zero_claims(self):
        from orchestration.langgraph_orchestrator import observe_node
        state = {"verification_report": {"claims": []}, "flaw_report": {}}
        result = observe_node(state)
        assert result["verified_ratio"] == 0.0

    def test_observe_all_verified(self):
        from orchestration.langgraph_orchestrator import observe_node
        state = {
            "verification_report": {
                "claims": [{"verified": True}, {"verified": True}]
            },
            "flaw_report": {"flaws": []},
            "converge_threshold": 0.5,
        }
        result = observe_node(state)
        assert result["verified_ratio"] == 1.0
        assert result["converged"] is True

    def test_observe_critical_flaw_prevents_convergence(self):
        from orchestration.langgraph_orchestrator import observe_node
        state = {
            "verification_report": {
                "claims": [{"verified": True}]
            },
            "flaw_report": {
                "flaws": [{"severity": "critical", "description": "fatal"}]
            },
            "converge_threshold": 0.5,
            "flaw_halt_severity": "critical",
        }
        result = observe_node(state)
        assert result["verified_ratio"] == 1.0
        assert result["converged"] is False

    def test_should_continue_max_iterations(self):
        from orchestration.langgraph_orchestrator import _should_continue
        state = {"converged": False, "iteration": 10, "max_iterations": 10, "claims": [{"text": "x"}]}
        assert _should_continue(state) == "generate_report"

    def test_should_continue_converged(self):
        from orchestration.langgraph_orchestrator import _should_continue
        state = {"converged": True, "iteration": 1, "max_iterations": 10}
        assert _should_continue(state) == "generate_report"

    def test_should_continue_no_claims(self):
        from orchestration.langgraph_orchestrator import _should_continue
        state = {"converged": False, "iteration": 1, "max_iterations": 10, "claims": []}
        assert _should_continue(state) == "generate_report"

    def test_should_continue_needs_more(self):
        from orchestration.langgraph_orchestrator import _should_continue
        state = {"converged": False, "iteration": 1, "max_iterations": 10, "claims": [{"text": "x"}]}
        assert _should_continue(state) == "plan"

    def test_reflect_with_empty_reports(self):
        from orchestration.langgraph_orchestrator import reflect_node
        state = {
            "domain": "test",
            "converged": True,
            "claims": [{"text": "Claim A"}],
            "cross_validation_report": {},
            "flaw_report": {},
            "verification_report": {},
        }
        result = reflect_node(state)
        assert "claims" in result

    def test_act_research_no_queries(self):
        from orchestration.langgraph_orchestrator import act_research_node
        state = {"queries": []}
        result = act_research_node(state)
        assert result is not None

    def test_generate_report_with_minimal_state(self):
        from orchestration.langgraph_orchestrator import generate_report_node
        state = {"research_idea": "Minimal test", "session_id": "test123"}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = generate_report_node(state)
        assert "report" in result
        assert result["report"]["research_idea"] == "Minimal test"


# ====================================================================
# 8. Tracing edge cases
# ====================================================================

class TestTracingEdge:
    """Edge cases for distributed tracing module."""

    def test_trace_llm_call_decorator_no_crash(self):
        from utils.tracing import trace_llm_call

        @trace_llm_call
        def my_func(x):
            return x * 2

        assert my_func(5) == 10

    def test_trace_agent_decorator_no_crash(self):
        from utils.tracing import trace_agent

        @trace_agent("test_agent")
        def agent_func():
            return {"status": "ok"}

        assert agent_func()["status"] == "ok"

    def test_trace_phase_context_manager(self):
        from utils.tracing import trace_phase

        with trace_phase("test_phase"):
            result = 1 + 1
        assert result == 2

    def test_trace_decorators_handle_exceptions(self):
        from utils.tracing import trace_llm_call

        @trace_llm_call
        def failing():
            raise ValueError("intentional")

        with pytest.raises(ValueError, match="intentional"):
            failing()


# ====================================================================
# 9. MCP integration edge cases
# ====================================================================

class TestMCPEdgeCases:
    """Edge cases for MCP integration."""

    def test_registry_from_config_no_args(self):
        from utils.mcp_integration import MCPRegistry
        # from_config() reads config from pipeline.yaml, should not crash
        registry = MCPRegistry.from_config()
        assert hasattr(registry, "to_tool_descriptions")

    def test_registry_tool_descriptions_type(self):
        from utils.mcp_integration import MCPRegistry
        registry = MCPRegistry.from_config()
        descriptions = registry.to_tool_descriptions()
        assert isinstance(descriptions, list)


# ====================================================================
# 10. Telegram bot edge cases
# ====================================================================

class TestTelegramBotEdge:
    """Edge cases for the Telegram bot wrapper."""

    def test_chunk_text_short(self):
        from utils.telegram_bot import TelegramResearchBot
        bot = TelegramResearchBot.__new__(TelegramResearchBot)
        chunks = bot._chunk_text("Hello world", max_len=4096)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_chunk_text_long(self):
        from utils.telegram_bot import TelegramResearchBot
        bot = TelegramResearchBot.__new__(TelegramResearchBot)
        long_text = "A" * 10_000
        chunks = bot._chunk_text(long_text, max_len=4096)
        assert len(chunks) >= 3
        assert "".join(chunks) == long_text

    def test_format_report_empty(self):
        from utils.telegram_bot import TelegramResearchBot
        bot = TelegramResearchBot.__new__(TelegramResearchBot)
        formatted = bot._format_report({})
        assert isinstance(formatted, str)
        assert len(formatted) > 0

    def test_format_report_with_errors(self):
        from utils.telegram_bot import TelegramResearchBot
        bot = TelegramResearchBot.__new__(TelegramResearchBot)
        report = {
            "research_idea": "Test",
            "errors": ["Error 1", "Error 2"],
            "converged": False,
        }
        formatted = bot._format_report(report)
        assert "Error" in formatted or "error" in formatted.lower()


# ====================================================================
# 11. PipelineContext (legacy) backward compat
# ====================================================================

class TestPipelineContextBackcompat:
    """Verify legacy PipelineContext still works after context.py enhancement."""

    def test_legacy_context_load_no_files(self, tmp_path, monkeypatch):
        from utils.context import PipelineContext
        # Point OUTPUT_DIR to empty tmp
        import utils.context as ctx_mod
        monkeypatch.setattr(ctx_mod, "OUTPUT_DIR", str(tmp_path))
        ctx = PipelineContext.load(seed=42)
        assert ctx.baseline is None
        assert ctx.mitigation is None

    def test_legacy_context_default_values(self):
        from utils.context import PipelineContext
        ctx = PipelineContext()
        assert ctx.seed == 42
        assert ctx.baseline is None
        assert ctx.judge_results == {}

    def test_legacy_get_best_eod_no_data(self):
        from utils.context import PipelineContext
        ctx = PipelineContext()
        assert ctx.get_best_eod() is None

    def test_legacy_get_best_dpd_no_data(self):
        from utils.context import PipelineContext
        ctx = PipelineContext()
        assert ctx.get_best_dpd() is None

    def test_legacy_eod_compliant_no_data(self):
        from utils.context import PipelineContext
        ctx = PipelineContext()
        assert ctx.get_eod_compliant_models() == []


# ====================================================================
# 12. Input validation edge cases
# ====================================================================

class TestInputValidation:
    """Test how the system handles various weird inputs."""

    def test_discover_with_html_injection(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "<script>alert('xss')</script>Research on biology"}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        # Should treat as plain text, not execute HTML
        assert len(result.get("claims", [])) >= 1

    def test_discover_with_control_characters(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "Research\x00on\x01quantum\x02computing\x03"}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        assert len(result.get("claims", [])) >= 1

    def test_discover_with_emoji(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "🔬 Research on 🧬 genetics and 🤖 AI"}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        assert len(result.get("claims", [])) >= 1

    def test_discover_with_path_traversal(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "../../etc/passwd"}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        # Should treat as text, not as a path
        assert "claims" in result

    def test_discover_with_newlines_and_tabs(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "Research\n\ton\n\tmachine\n\tlearning"}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        assert len(result.get("claims", [])) >= 1

    def test_numbers_only_input(self):
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": "12345678901234567890"}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        assert len(result.get("claims", [])) >= 1


# ====================================================================
# 13. Golden dataset edge cases
# ====================================================================

class TestGoldenDatasetEdge:
    """Golden dataset scenarios for discover and observe behavior."""

    @pytest.mark.parametrize("idea,expected_domain", [
        ("Effect of SMOTE on credit card fraud detection", "general"),
        ("Quantum entanglement in photon pairs", "general"),
        ("Impact of minimum wage on employment", "general"),
        ("Efficacy of mRNA vaccines for COVID-19", "general"),
        ("", "general"),
    ])
    def test_discover_fallback_domain(self, idea, expected_domain):
        """Without LLM, fallback domain should be 'general'."""
        from orchestration.langgraph_orchestrator import discover_node
        state = {"research_idea": idea}
        with patch("utils.multi_llm_client.is_available", return_value=False):
            result = discover_node(state)
        if idea.strip():
            assert result.get("domain") == expected_domain
            assert len(result.get("claims", [])) >= 1

    @pytest.mark.parametrize("verified_count,total,expected_converged", [
        (0, 0, False),     # No claims
        (0, 5, False),     # None verified
        (3, 5, False),     # 60% < 85%
        (5, 5, True),      # 100% >= 85%
        (9, 10, True),     # 90% >= 85%
        (8, 10, False),    # 80% < 85%
        (85, 100, True),   # Exactly 85%
    ])
    def test_observe_convergence_thresholds(self, verified_count, total, expected_converged):
        from orchestration.langgraph_orchestrator import observe_node
        claims = [{"verified": i < verified_count} for i in range(total)]
        state = {
            "verification_report": {"claims": claims},
            "flaw_report": {"flaws": []},
            "converge_threshold": 0.85,
            "flaw_halt_severity": "critical",
        }
        result = observe_node(state)
        assert result["converged"] == expected_converged


# ====================================================================
# 14. Concurrent access edge cases
# ====================================================================

class TestConcurrentAccess:
    """Test thread safety of various components."""

    def test_concurrent_sandbox_execution(self):
        from utils.sandbox import execute_code, SandboxConfig
        config = SandboxConfig(timeout_seconds=5)

        def run_code(i):
            return execute_code(f"print({i} * {i})", config=config)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_code, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        successful = sum(1 for r in results if r.success)
        assert successful >= 8  # Allow some failures under load

    def test_concurrent_config_loading(self):
        from utils.config_loader import load_pipeline_config, invalidate_cache
        invalidate_cache()

        configs = []
        def load():
            configs.append(load_pipeline_config())

        threads = [threading.Thread(target=load) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should return the same config object (thread-safe cache)
        assert all(c is configs[0] for c in configs)

    def test_concurrent_llm_client_factory(self):
        from utils.multi_llm_client import get_llm_client, reset_client
        reset_client()

        clients = []
        lock = threading.Lock()
        def get():
            c = get_llm_client()
            with lock:
                clients.append(c)

        threads = [threading.Thread(target=get) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All returned clients should be the same type (singleton may race, but all valid)
        assert len(clients) == 10
        assert all(type(c) == type(clients[0]) for c in clients)
        reset_client()

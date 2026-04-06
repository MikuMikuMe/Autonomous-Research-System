# pyright: reportAny=false
"""Tests for Phase 3: Integration Layer.

Covers MCP integration, Docker Compose validation, and Telegram bot.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── MCP Integration ──────────────────────────────────────────────────────

class TestMCPIntegration:
    """Test MCP tool registry and client."""

    def test_mcp_server_config_creation(self):
        from utils.mcp_integration import MCPServerConfig
        config = MCPServerConfig(
            name="test-server",
            command="npx",
            args=["-y", "@test/mcp"],
        )
        assert config.name == "test-server"
        assert config.command == "npx"

    def test_mcp_tool_descriptor(self):
        from utils.mcp_integration import MCPTool
        tool = MCPTool(
            name="search",
            description="Search the web",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            server_name="web-server",
        )
        assert tool.name == "search"
        assert "query" in str(tool.input_schema)

    def test_mcp_registry_from_config_disabled(self):
        from utils.mcp_integration import MCPRegistry
        with patch("utils.config_loader.load_pipeline_config", return_value={"mcp": {"enabled": False}}):
            registry = MCPRegistry.from_config()
            assert not registry.enabled
            assert registry.server_names == []

    def test_mcp_registry_from_config_with_servers(self):
        from utils.mcp_integration import MCPRegistry
        config = {
            "mcp": {
                "enabled": True,
                "servers": [
                    {"name": "test", "command": "echo", "args": ["hello"]},
                    {"name": "web", "url": "http://localhost:3001/mcp"},
                ],
            }
        }
        with patch("utils.config_loader.load_pipeline_config", return_value=config):
            registry = MCPRegistry.from_config()
            assert registry.enabled
            assert len(registry.server_names) == 2
            assert "test" in registry.server_names
            assert "web" in registry.server_names

    def test_mcp_registry_add_server(self):
        from utils.mcp_integration import MCPRegistry, MCPServerConfig
        registry = MCPRegistry()
        config = MCPServerConfig(name="dynamic", command="python", args=["-m", "mcp_server"])
        registry.add_server(config)
        assert registry.enabled
        assert "dynamic" in registry.server_names

    def test_mcp_registry_list_tools_empty(self):
        from utils.mcp_integration import MCPRegistry
        registry = MCPRegistry()
        assert registry.list_all_tools() == []

    def test_mcp_registry_get_tool_not_found(self):
        from utils.mcp_integration import MCPRegistry
        registry = MCPRegistry()
        assert registry.get_tool("nonexistent") is None

    def test_mcp_call_tool_not_found(self):
        from utils.mcp_integration import MCPRegistry
        registry = MCPRegistry()
        result = asyncio.get_event_loop().run_until_complete(
            registry.call_tool("nonexistent")
        )
        assert not result.success
        assert "not found" in result.error

    def test_mcp_client_not_connected(self):
        from utils.mcp_integration import MCPClient, MCPServerConfig
        config = MCPServerConfig(name="test", command="echo")
        client = MCPClient(config)
        assert not client.connected
        assert client.tools == []

    def test_mcp_tool_result(self):
        from utils.mcp_integration import MCPToolResult
        result = MCPToolResult(success=True, content={"answer": 42})
        assert result.success
        assert result.content["answer"] == 42

    def test_mcp_registry_to_tool_descriptions(self):
        from utils.mcp_integration import MCPRegistry, MCPClient, MCPTool, MCPServerConfig
        registry = MCPRegistry()
        # Manually add a connected client with tools
        config = MCPServerConfig(name="test")
        client = MCPClient(config)
        client._connected = True
        client._tools = [
            MCPTool(name="search", description="Search", server_name="test"),
        ]
        registry._clients["test"] = client
        registry._enabled = True

        descriptions = registry.to_tool_descriptions()
        assert len(descriptions) == 1
        assert descriptions[0]["name"] == "search"
        assert descriptions[0]["server"] == "test"

    def test_mcp_singleton_reset(self):
        from utils.mcp_integration import get_mcp_registry, reset_mcp_registry
        reset_mcp_registry()
        with patch("utils.config_loader.load_pipeline_config", return_value={"mcp": {"enabled": False}}):
            r1 = get_mcp_registry()
            r2 = get_mcp_registry()
            assert r1 is r2
        reset_mcp_registry()


# ─── Telegram Bot ──────────────────────────────────────────────────────────

class TestTelegramBot:
    """Test Telegram bot wrapper."""

    def test_bot_not_configured_without_token(self):
        from utils.telegram_bot import TelegramResearchBot
        with patch.dict(os.environ, {}, clear=True):
            bot = TelegramResearchBot(token="")
            assert not bot.is_configured

    def test_bot_configured_with_token(self):
        from utils.telegram_bot import TelegramResearchBot
        bot = TelegramResearchBot(token="test-token-123")
        assert bot.is_configured

    def test_bot_build_without_token(self):
        from utils.telegram_bot import TelegramResearchBot
        bot = TelegramResearchBot(token="")
        assert bot.build() is None

    def test_format_report_with_error(self):
        from utils.telegram_bot import TelegramResearchBot
        report = {"error": "Something went wrong"}
        result = TelegramResearchBot._format_report(report)
        assert "Error" in result
        assert "Something went wrong" in result

    def test_format_report_with_results(self):
        from utils.telegram_bot import TelegramResearchBot
        report = {
            "domain": "machine_learning",
            "claims": [{"text": "Test claim"}],
            "verification_report": {"claims": [{"claim": "A", "verified": True}]},
            "discovered_techniques": [{"name": "SMOTE"}],
            "errors": [],
        }
        result = TelegramResearchBot._format_report(report)
        assert "machine_learning" in result
        assert "Test claim" in result
        assert "1/1" in result
        assert "SMOTE" in result

    def test_chunk_text_short(self):
        from utils.telegram_bot import TelegramResearchBot
        text = "Short text"
        chunks = TelegramResearchBot._chunk_text(text, 4000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_long(self):
        from utils.telegram_bot import TelegramResearchBot
        text = "Line\n" * 2000  # ~10000 chars
        chunks = TelegramResearchBot._chunk_text(text, 100)
        assert len(chunks) > 1
        # Reassembled text should equal original (minus potential leading newlines from splits)
        reassembled = "\n".join(chunks)
        assert len(reassembled) >= len(text) - 10

    def test_execute_research_delegates(self):
        from utils.telegram_bot import TelegramResearchBot
        mock_result = {"domain": "test", "claims": []}
        with patch("orchestration.langgraph_orchestrator.run_research", return_value=mock_result):
            result = TelegramResearchBot._execute_research("test idea")
            assert result["domain"] == "test"

    def test_execute_research_handles_error(self):
        from utils.telegram_bot import TelegramResearchBot
        with patch("orchestration.langgraph_orchestrator.run_research", side_effect=RuntimeError("fail")):
            result = TelegramResearchBot._execute_research("test idea")
            assert "error" in result


# ─── Docker Compose Validation ─────────────────────────────────────────────

class TestDockerCompose:
    """Validate Docker Compose configuration."""

    def test_docker_compose_exists(self):
        compose = Path(__file__).resolve().parent.parent / "docker-compose.yml"
        assert compose.exists()

    def test_docker_compose_valid_yaml(self):
        import yaml
        compose = Path(__file__).resolve().parent.parent / "docker-compose.yml"
        with open(compose, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "services" in data
        assert "research-api" in data["services"]

    def test_docker_compose_has_api_service(self):
        import yaml
        compose = Path(__file__).resolve().parent.parent / "docker-compose.yml"
        with open(compose, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        api = data["services"]["research-api"]
        assert "build" in api
        assert "ports" in api

    def test_docker_compose_has_latex_sidecar(self):
        import yaml
        compose = Path(__file__).resolve().parent.parent / "docker-compose.yml"
        with open(compose, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert "latex" in data["services"]

    def test_dockerfile_exists(self):
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        assert dockerfile.exists()

    def test_dockerfile_has_requirements(self):
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text()
        assert "requirements.txt" in content
        assert "EXPOSE" in content

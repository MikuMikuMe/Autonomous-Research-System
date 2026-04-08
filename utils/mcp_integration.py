"""
MCP (Model Context Protocol) Integration.

Provides a registry that loads MCP tool servers from config,
connects to them, and exposes their tools to the research pipeline.
Supports both stdio (command-based) and HTTP (SSE) transports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MCPTool:
    """Descriptor for a tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None  # For HTTP/SSE transport


@dataclass
class MCPToolResult:
    """Result of calling an MCP tool."""
    success: bool
    content: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# MCP Client (protocol-level)
# ---------------------------------------------------------------------------

class MCPClient:
    """Client for a single MCP server (stdio or HTTP transport)."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Any = None
        self._tools: list[MCPTool] = []
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPTool]:
        return list(self._tools)

    async def connect(self) -> None:
        """Connect to the MCP server and discover tools."""
        if self._connected:
            return

        try:
            if self.config.url:
                await self._connect_http()
            elif self.config.command:
                await self._connect_stdio()
            else:
                raise ValueError(f"MCP server '{self.config.name}' has no command or url")
            self._connected = True
            logger.info(
                "Connected to MCP server '%s' — %d tools available",
                self.config.name, len(self._tools),
            )
        except ImportError:
            logger.warning(
                "MCP SDK not installed. Install with: pip install mcp"
            )
            self._connected = False
        except Exception as e:
            logger.error("Failed to connect to MCP server '%s': %s", self.config.name, e)
            self._connected = False

    async def _connect_stdio(self) -> None:
        """Connect via stdio transport (subprocess)."""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env={**os.environ, **self.config.env},
            )
            transport = await stdio_client(params).__aenter__()
            self._session = ClientSession(*transport)
            await self._session.__aenter__()
            await self._session.initialize()
            await self._discover_tools()
        except ImportError:
            raise

    async def _connect_http(self) -> None:
        """Connect via HTTP/SSE transport."""
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            transport = await sse_client(self.config.url).__aenter__()
            self._session = ClientSession(*transport)
            await self._session.__aenter__()
            await self._session.initialize()
            await self._discover_tools()
        except ImportError:
            raise

    async def _discover_tools(self) -> None:
        """List tools from the connected server."""
        if not self._session:
            return
        try:
            result = await self._session.list_tools()
            self._tools = [
                MCPTool(
                    name=t.name,
                    description=getattr(t, "description", ""),
                    input_schema=getattr(t, "inputSchema", {}),
                    server_name=self.config.name,
                )
                for t in result.tools
            ]
        except Exception as e:
            logger.error("Failed to discover tools from '%s': %s", self.config.name, e)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> MCPToolResult:
        """Call a tool on the MCP server."""
        if not self._connected or not self._session:
            return MCPToolResult(success=False, error="Not connected")

        try:
            result = await self._session.call_tool(tool_name, arguments or {})
            content = result.content if hasattr(result, "content") else str(result)
            return MCPToolResult(success=True, content=content)
        except Exception as e:
            return MCPToolResult(success=False, error=str(e))

    async def disconnect(self) -> None:
        """Close the MCP session."""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None
        self._connected = False


# ---------------------------------------------------------------------------
# MCP Registry (manages multiple servers)
# ---------------------------------------------------------------------------

class MCPRegistry:
    """Registry that manages multiple MCP server connections."""

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
        self._enabled = False

    @classmethod
    def from_config(cls) -> MCPRegistry:
        """Create registry from pipeline.yaml -> mcp section."""
        registry = cls()
        try:
            from utils.config_loader import load_pipeline_config
            cfg = load_pipeline_config().get("mcp", {})
            registry._enabled = cfg.get("enabled", False)
            if not registry._enabled:
                return registry

            for server_cfg in cfg.get("servers", []):
                config = MCPServerConfig(
                    name=server_cfg.get("name", "unnamed"),
                    command=server_cfg.get("command"),
                    args=server_cfg.get("args", []),
                    env=server_cfg.get("env", {}),
                    url=server_cfg.get("url"),
                )
                registry._clients[config.name] = MCPClient(config)
        except Exception as e:
            logger.error("Failed to load MCP config: %s", e)
        return registry

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def server_names(self) -> list[str]:
        return list(self._clients.keys())

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all configured MCP servers. Returns connection status."""
        results = {}
        for name, client in self._clients.items():
            await client.connect()
            results[name] = client.connected
        return results

    def list_all_tools(self) -> list[MCPTool]:
        """List all tools from all connected servers."""
        tools = []
        for client in self._clients.values():
            if client.connected:
                tools.extend(client.tools)
        return tools

    def get_tool(self, tool_name: str) -> tuple[MCPClient, MCPTool] | None:
        """Find a tool by name across all servers."""
        for client in self._clients.values():
            for tool in client.tools:
                if tool.name == tool_name:
                    return client, tool
        return None

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> MCPToolResult:
        """Call a tool by name, routing to the correct server."""
        result = self.get_tool(tool_name)
        if not result:
            return MCPToolResult(success=False, error=f"Tool '{tool_name}' not found")
        client, _ = result
        return await client.call_tool(tool_name, arguments)

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for client in self._clients.values():
            await client.disconnect()

    def add_server(self, config: MCPServerConfig) -> None:
        """Add a server to the registry (for programmatic use)."""
        self._clients[config.name] = MCPClient(config)
        self._enabled = True

    def to_tool_descriptions(self) -> list[dict[str, Any]]:
        """Export all tools as LLM-compatible tool descriptions."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
                "server": tool.server_name,
            }
            for tool in self.list_all_tools()
        ]


# ---------------------------------------------------------------------------
# Convenience singleton
# ---------------------------------------------------------------------------

_registry: MCPRegistry | None = None


def get_mcp_registry() -> MCPRegistry:
    """Get or create the MCP registry singleton."""
    global _registry
    if _registry is None:
        _registry = MCPRegistry.from_config()
    return _registry


def reset_mcp_registry() -> None:
    """Reset the MCP registry (for testing)."""
    global _registry
    _registry = None

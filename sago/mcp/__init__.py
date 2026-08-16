"""Model Context Protocol (MCP) Integration for SAGO."""

from __future__ import annotations

from sago.mcp.client import MCPClient, MCPRemoteTool
from sago.mcp.manager import (
    DynamicMCPTool,
    MCPManager,
    MCPServerConfig,
    get_mcp_manager,
)
from sago.mcp.server import MCPServer, MCPTool, create_sago_mcp_server

__all__ = [
    "MCPServer",
    "MCPTool",
    "create_sago_mcp_server",
    "MCPClient",
    "MCPRemoteTool",
    "MCPManager",
    "get_mcp_manager",
    "MCPServerConfig",
    "DynamicMCPTool",
]

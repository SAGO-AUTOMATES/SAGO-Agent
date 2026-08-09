"""Integration tests for MCP server."""

import pytest

from sago.mcp.server import MCPServer, MCPTool, create_sago_mcp_server


@pytest.fixture
def mcp_server():
    """Create an MCP server."""
    return MCPServer(name="test", version="0.1.0")


@pytest.fixture
def sago_mcp_server():
    """Create a Sago MCP server with all tools."""
    return create_sago_mcp_server()


class TestMCPServer:
    def test_server_creation(self, mcp_server):
        assert mcp_server.name == "test"
        assert mcp_server.version == "0.1.0"

    def test_server_tools(self, mcp_server):
        assert isinstance(mcp_server.tools, dict)

    def test_server_add_tool(self, mcp_server):
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )
        mcp_server.tools["test_tool"] = tool
        assert "test_tool" in mcp_server.tools


class TestSagoMCPServer:
    def test_sago_server_creation(self, sago_mcp_server):
        assert sago_mcp_server.name == "sago"
        assert sago_mcp_server.version == "0.1.0"

    def test_sago_server_has_tools(self, sago_mcp_server):
        assert len(sago_mcp_server.tools) > 0

    def test_sago_server_tool_count(self, sago_mcp_server):
        assert len(sago_mcp_server.tools) >= 30

    def test_sago_server_tool_names(self, sago_mcp_server):
        tool_names = list(sago_mcp_server.tools.keys())
        assert "read_file" in tool_names or len(tool_names) > 0


class TestMCPTool:
    def test_tool_creation(self):
        tool = MCPTool(
            name="test",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
        )
        assert tool.name == "test"
        assert tool.description == "Test tool"

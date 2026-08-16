"""Unit tests for MCPManager, configuration discovery, and dynamic tool bridging."""

import json
from pathlib import Path

from sago.mcp.client import MCPClient
from sago.mcp.manager import MCPManager, MCPServerConfig


def test_mcp_manager_load_claude_json_config(tmp_path: Path):
    mcp_file = tmp_path / "mcp.json"
    mcp_file.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "sqlite": {
                        "command": "uvx",
                        "args": ["mcp-server-sqlite", "--db-path", "test.db"],
                        "env": {"DEBUG": "1"},
                    },
                    "remote_weather": {
                        "url": "http://127.0.0.1:9099/mcp",
                        "headers": {"Authorization": "Bearer token123"},
                    },
                }
            }
        )
    )

    mgr = MCPManager(workspace_root=tmp_path)
    servers = mgr.list_servers()
    assert len(servers) >= 2

    s_names = [s.name for s in servers]
    assert "sqlite" in s_names
    assert "remote_weather" in s_names

    sqlite_cfg = [s for s in servers if s.name == "sqlite"][0]
    assert sqlite_cfg.command == "uvx"
    assert "--db-path" in sqlite_cfg.args


def test_dynamic_mcp_tool_bridging():
    # Mock client with registered tool
    client = MCPClient(server_url="mock://test_server")
    client.is_connected = True
    client.register_remote_tool(
        name="query_db",
        description="Execute read-only SQL query",
        input_schema={
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SQL statement"},
                "limit": {"type": "integer", "description": "Row limit"},
            },
            "required": ["sql"],
        },
    )

    mgr = MCPManager()
    mgr.register_server(
        MCPServerConfig(
            name="mock_db",
            command="mock",
            enabled=True,
        )
    )
    # Inject active mock client
    mgr._clients["mock_db"] = client

    tools = mgr.get_mcp_tools()
    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "mcp_mock_db_query_db"
    assert "[mock_db]" in tool.description
    assert tool.args_model is not None

    # Test run
    res = tool.run(sql="SELECT * FROM users", limit=10)
    assert res is not None

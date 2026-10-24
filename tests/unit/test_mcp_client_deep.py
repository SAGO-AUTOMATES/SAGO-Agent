import json
from unittest.mock import MagicMock, patch

import pytest

from sago.errors.exceptions import ToolExecutionError
from sago.mcp.client import MCPClient, MCPRemoteTool


def test_mcp_remote_tool_basics():
    tool_orphan = MCPRemoteTool(name="orphan", description="orphan tool")
    with pytest.raises(ToolExecutionError, match="not connected to an MCP client"):
        tool_orphan.execute()

    client_mock = MagicMock()
    client_mock.call_tool.return_value = {"result": "ok"}
    tool = MCPRemoteTool(
        name="test_tool",
        description="desc",
        input_schema={"type": "object", "properties": {"arg": {"type": "string"}}},
        client=client_mock,
    )
    res = tool.execute(arg="val")
    assert res == {"result": "ok"}
    client_mock.call_tool.assert_called_with("test_tool", {"arg": "val"})

    tdict = tool.to_dict()
    assert tdict["name"] == "test_tool"
    assert "properties" in tdict["inputSchema"]


def test_mcp_client_env():
    client = MCPClient("mock://server")
    env = client._build_subprocess_env()
    assert isinstance(env, dict)

    client._isolated_env = {"CUSTOM_VAR": "val123"}
    iso_env = client._build_subprocess_env()
    assert iso_env.get("CUSTOM_VAR") == "val123"


def test_mcp_client_connect_mock_and_unsupported():
    c_mock = MCPClient("mock://server")
    assert c_mock.connect() is True
    assert c_mock.is_connected is True

    c_local = MCPClient("local://server")
    assert c_local.connect() is True

    c_bad = MCPClient("ftp://server")
    assert c_bad.connect() is False
    assert c_bad.is_connected is False


def test_mcp_client_connect_http():
    c_http = MCPClient("http://127.0.0.1:8000")
    with patch("httpx.Client") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_ctx

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tools": [{"name": "remote_echo", "description": "echoes text"}]
        }
        mock_ctx.get.return_value = mock_resp

        assert c_http.connect() is True
        assert "remote_echo" in c_http._tools


def test_mcp_client_connect_stdio():
    c_stdio = MCPClient("stdio://python -m mcp_server")
    with (
        patch("subprocess.Popen") as mock_popen,
        patch.object(c_stdio, "_perform_init_handshake", return_value=True),
        patch.object(c_stdio, "_refresh_tools"),
    ):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        assert c_stdio.connect() is True
        assert c_stdio.is_connected is True


def test_mcp_client_perform_init_handshake():
    c = MCPClient("stdio://server")
    # No process
    assert c._perform_init_handshake() is False

    mock_proc = MagicMock()
    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_proc.stdin = mock_stdin
    mock_proc.stdout = mock_stdout
    c._process = mock_proc

    # Valid handshake
    with patch("select.select", return_value=([mock_stdout], [], [])):
        mock_stdout.readline.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}})
            + "\n"
        )

        assert c._perform_init_handshake() is True
        assert c._initialized is True


def test_mcp_client_tools_list_and_register():
    c = MCPClient("mock://server")
    c.is_connected = True

    tool = c.register_remote_tool("custom_tool", "custom description")
    assert tool.name == "custom_tool"

    tools = c.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "custom_tool"


def test_mcp_client_call_tool_mock():
    c = MCPClient("mock://server")
    c.is_connected = True
    c.register_remote_tool("mock_tool", "mock tool")

    res = c.call_tool("mock_tool", {"param": "value"})
    assert "content" in res

    # Tool not found
    with pytest.raises(ToolExecutionError, match="not found on MCP server"):
        c.call_tool("unknown_tool", {})


def test_mcp_client_call_tool_http():
    c = MCPClient("https://mcp.example.com")
    c.is_connected = True

    with patch("httpx.Client") as mock_client_cls:
        mock_ctx = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_ctx

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": [{"type": "text", "text": "result"}]}
        mock_ctx.post.return_value = mock_resp

        res = c.call_tool("http_tool", {"arg": "val"})
        assert res["content"][0]["text"] == "result"


def test_mcp_client_call_tool_stdio():
    c = MCPClient("stdio://server")
    c.is_connected = True

    mock_proc = MagicMock()
    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_proc.stdin = mock_stdin
    mock_proc.stdout = mock_stdout
    c._process = mock_proc

    with patch("select.select", return_value=([mock_stdout], [], [])):
        mock_stdout.readline.return_value = (
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"data": "from stdio"}}) + "\n"
        )

        res = c.call_tool("stdio_tool", {"x": 1})
        assert res == {"data": "from stdio"}


def test_mcp_client_close():
    c = MCPClient("stdio://server")
    mock_proc = MagicMock()
    c._process = mock_proc
    c.is_connected = True

    c.close()
    mock_proc.terminate.assert_called_once()
    assert c.is_connected is False
    assert c._process is None


def test_mcp_client_refresh_tools_stdio():
    c = MCPClient("stdio://server")
    c.is_connected = True

    mock_proc = MagicMock()
    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_proc.stdin = mock_stdin
    mock_proc.stdout = mock_stdout
    c._process = mock_proc

    with patch("select.select", return_value=([mock_stdout], [], [])):
        mock_stdout.readline.return_value = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "tools": [
                            {
                                "name": "stdio_cat",
                                "description": "read file",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                }
            )
            + "\n"
        )

        c._refresh_tools()
        assert "stdio_cat" in c._tools

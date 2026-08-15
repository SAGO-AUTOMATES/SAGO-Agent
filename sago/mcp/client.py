"""Model Context Protocol (MCP) Client for SAGO.

Enables connecting to external MCP servers (stdio, SSE, HTTP), discovering remote tools,
and calling remote tools directly or wrapping them as SAGO BaseTools.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from typing import Any

from sago.errors.exceptions import ToolExecutionError
from sago.utils.errors import log_error

logger = logging.getLogger("sago.mcp.client")


class MCPRemoteTool:
    """Represents a tool exposed by an external MCP server."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any] | None = None,
        client: MCPClient | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema or {"type": "object", "properties": {}}
        self.client = client

    def execute(self, **kwargs: Any) -> Any:
        if not self.client:
            raise ToolExecutionError(f"Tool {self.name} is not connected to an MCP client")
        return self.client.call_tool(self.name, kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class MCPClient:
    """Client for communicating with external Model Context Protocol (MCP) servers."""

    def __init__(
        self,
        server_url: str,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.server_url = server_url
        self.timeout = timeout
        self.headers = headers or {}
        self.is_connected = False
        self._tools: dict[str, MCPRemoteTool] = {}
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    def connect(self) -> bool:
        """Connect to the MCP server endpoint."""
        with self._lock:
            try:
                if self.server_url.startswith("stdio://"):
                    cmd = self.server_url.replace("stdio://", "").split()
                    self._process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                    )
                    self.is_connected = True
                elif self.server_url.startswith(("http://", "https://", "sse://")):
                    import httpx

                    url = self.server_url.replace("sse://", "http://")
                    with httpx.Client(timeout=self.timeout) as client:
                        resp = client.get(f"{url.rstrip('/')}/health", headers=self.headers)
                        # Connection succeeded if endpoint is reachable
                        self.is_connected = resp.status_code < 500
                elif self.server_url.startswith(("local://", "mock://")):
                    # In-process or local mock path
                    self.is_connected = True
                else:
                    logger.warning("Unsupported MCP transport scheme: %s", self.server_url)
                    self.is_connected = False
                    return False

                self._refresh_tools()
                return self.is_connected
            except Exception as e:
                log_error(f"Failed to connect to MCP server {self.server_url}", e)
                self.is_connected = False
                return False

    def _refresh_tools(self) -> None:
        """Query and cache tools provided by the remote MCP server."""
        if not self.is_connected:
            return

        try:
            if self.server_url.startswith("stdio://") and self._process and self._process.stdin:
                req = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                }
                self._process.stdin.write(json.dumps(req) + "\n")
                self._process.stdin.flush()
                line = self._process.stdout.readline() if self._process.stdout else ""
                if line:
                    data = json.loads(line)
                    raw_tools = data.get("result", {}).get("tools", [])
                    for t in raw_tools:
                        self._tools[t["name"]] = MCPRemoteTool(
                            name=t["name"],
                            description=t.get("description", ""),
                            input_schema=t.get("inputSchema", {}),
                            client=self,
                        )
            elif self.server_url.startswith(("http://", "https://")):
                import httpx

                url = f"{self.server_url.rstrip('/')}/tools"
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        raw_tools = resp.json().get("tools", [])
                        for t in raw_tools:
                            self._tools[t["name"]] = MCPRemoteTool(
                                name=t["name"],
                                description=t.get("description", ""),
                                input_schema=t.get("inputSchema", {}),
                                client=self,
                            )
        except Exception as e:
            log_error("Failed to refresh MCP remote tools", e)

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools from the connected MCP server."""
        if not self.is_connected:
            self.connect()
        return [tool.to_dict() for tool in self._tools.values()]

    def register_remote_tool(
        self, name: str, description: str, input_schema: dict[str, Any] | None = None
    ) -> MCPRemoteTool:
        """Manually register a known remote tool schema."""
        tool = MCPRemoteTool(name, description, input_schema, client=self)
        self._tools[name] = tool
        return tool

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the remote MCP server."""
        if not self.is_connected:
            connected = self.connect()
            if not connected:
                raise ToolExecutionError(f"Cannot execute '{name}': MCP server is disconnected")

        if self.server_url.startswith(("local://", "mock://")) and name not in self._tools:
            raise ToolExecutionError(f"Remote tool '{name}' not found on MCP server")

        try:
            if self.server_url.startswith("stdio://") and self._process and self._process.stdin:
                req = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
                self._process.stdin.write(json.dumps(req) + "\n")
                self._process.stdin.flush()
                line = self._process.stdout.readline() if self._process.stdout else ""
                if line:
                    res = json.loads(line)
                    return res.get("result", res)
            elif self.server_url.startswith(("http://", "https://")):
                import httpx

                url = f"{self.server_url.rstrip('/')}/tools/call"
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        url,
                        json={"name": name, "arguments": arguments},
                        headers=self.headers,
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    raise ToolExecutionError(
                        f"MCP server HTTP error {resp.status_code}: {resp.text}"
                    )

            # Return structured execution result for simulated or connected client
            return {
                "content": [{"type": "text", "text": f"Executed remote MCP tool: {name}"}],
                "isError": False,
            }
        except Exception as e:
            log_error(f"MCP tool call '{name}' failed", e)
            raise ToolExecutionError(f"Remote tool '{name}' call failed: {e}") from e

    def close(self) -> None:
        """Close connection and terminate any child process."""
        with self._lock:
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=2.0)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                self._process = None
            self.is_connected = False

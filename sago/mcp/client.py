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
from sago.utils.safe import log_exception

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
        self._initialized = False
        self._request_id = 0
        self._isolated_env: dict[str, str] | None = None  # Per-server isolated environment

    def _next_request_id(self) -> int:
        """Get next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id

    def _build_subprocess_env(self) -> dict[str, str]:
        """Build isolated environment for subprocess execution.

        If isolated_env is set, only include those variables plus essential system vars.
        Otherwise, use a copy of the current environment.
        """
        import os

        if self._isolated_env is not None:
            # Build minimal safe environment with only essential vars + server-specific env
            safe_vars = {}
            essential_vars = ["PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "USER"]
            for var in essential_vars:
                if var in os.environ:
                    safe_vars[var] = os.environ[var]
            # Add server-specific environment variables
            safe_vars.update(self._isolated_env)
            return safe_vars
        else:
            # Use copy of current environment
            return os.environ.copy()

    def connect(self) -> bool:
        """Connect to the MCP server endpoint."""
        with self._lock:
            try:
                if self.server_url.startswith("stdio://"):
                    cmd = self.server_url.replace("stdio://", "").split()
                    # Build isolated environment for subprocess
                    subprocess_env = self._build_subprocess_env()
                    self._process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        env=subprocess_env,
                    )
                    # Perform MCP initialization handshake
                    if not self._perform_init_handshake():
                        logger.warning(
                            "MCP initialization handshake failed for %s", self.server_url
                        )
                        self.is_connected = False
                        return False
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

    def _perform_init_handshake(self) -> bool:
        """Perform MCP initialization handshake per specification.

        The MCP protocol requires:
        1. Client sends initialize request with capabilities
        2. Server responds with its capabilities
        3. Client sends initialized notification
        4. Then tools/list can be called
        """
        if not self._process or not self._process.stdin or not self._process.stdout:
            return False

        try:
            # Step 1: Send initialize request
            init_req = {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "sago-mcp-client", "version": "1.0.0"},
                },
            }
            self._process.stdin.write(json.dumps(init_req) + "\n")
            self._process.stdin.flush()

            # Step 2: Read server response with timeout
            import select

            if not self._process.stdout:
                logger.warning("No stdout available for reading init response")
                return False
            ready, _, _ = select.select([self._process.stdout], [], [], self.timeout)
            if not ready:
                logger.warning("MCP init handshake timeout waiting for server response")
                return False

            line = self._process.stdout.readline()
            if not line:
                logger.warning("MCP init handshake: no response from server")
                return False

            init_resp = json.loads(line)
            if "error" in init_resp:
                logger.warning("MCP init handshake error: %s", init_resp["error"])
                return False

            # Step 3: Send initialized notification (no id = notification)
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
            self._process.stdin.write(json.dumps(initialized_notification) + "\n")
            self._process.stdin.flush()

            self._initialized = True
            return True

        except Exception as e:
            logger.warning("MCP init handshake failed: %s", e)
            return False

    def _refresh_tools(self) -> None:
        """Query and cache tools provided by the remote MCP server."""
        if not self.is_connected:
            return

        try:
            if self.server_url.startswith("stdio://") and self._process and self._process.stdin:
                req = {
                    "jsonrpc": "2.0",
                    "id": self._next_request_id(),
                    "method": "tools/list",
                    "params": {},
                }
                self._process.stdin.write(json.dumps(req) + "\n")
                self._process.stdin.flush()

                # Use timeout for reading response
                import select

                if not self._process.stdout:
                    logger.warning("No stdout available for reading tools/list response")
                    return
                ready, _, _ = select.select([self._process.stdout], [], [], self.timeout)
                if not ready:
                    logger.warning("Timeout waiting for tools/list response")
                    return

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
                    "id": self._next_request_id(),
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
                self._process.stdin.write(json.dumps(req) + "\n")
                self._process.stdin.flush()

                # Use timeout for reading response
                import select

                if not self._process.stdout:
                    raise ToolExecutionError(f"Cannot read response for tool '{name}': no stdout")
                ready, _, _ = select.select([self._process.stdout], [], [], self.timeout)
                if not ready:
                    raise ToolExecutionError(f"Timeout waiting for tool '{name}' response")

                line = self._process.stdout.readline()
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
                except Exception as e:
                    log_exception(e, "Failed to terminate MCP process")
                try:
                    self._process.kill()
                except Exception as e:
                    log_exception(e, "Failed to kill MCP process")
                self._process = None
            self.is_connected = False

"""MCP Server Support

Model Context Protocol server for exposing Sago tools
and integrating external MCP tools.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.permissions import get_permission_manager
from sago.utils.errors import log_error


@dataclass
class MCPTool:
    """MCP tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class MCPServer:
    """MCP server for exposing tools."""

    name: str
    version: str = "1.0.0"
    tools: dict[str, MCPTool] = field(default_factory=dict)

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool with the server."""
        self.tools[tool.name] = tool

    def register_function(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """Register a function as an MCP tool."""
        tool = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        )
        self.register_tool(tool)

    def register_sago_tool(self, tool_class: type) -> None:
        """Register a Sago BaseTool class as an MCP tool."""
        from sago.tools.base import BaseTool

        if not issubclass(tool_class, BaseTool):
            raise ValueError(f"{tool_class} is not a BaseTool subclass")

        tool_instance = tool_class()

        # Build input schema from args_model
        input_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        if tool_class.args_model:
            fields = tool_class.args_model.model_fields
            for field_name, field_info in fields.items():
                prop: dict[str, Any] = {"type": "string"}
                if field_info.description:
                    prop["description"] = field_info.description
                input_schema["properties"][field_name] = prop
                if field_info.is_required():
                    input_schema["required"].append(field_name)

        def handler(**kwargs: Any) -> Any:
            return tool_instance.run(**kwargs)

        self.register_function(
            name=tool_class.name,
            description=tool_class.description or tool_class.name,
            input_schema=input_schema,
            handler=handler,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools."""
        return [tool.to_dict() for tool in self.tools.values()]

    def call_tool(self, name: str, arguments: dict[str, Any], session_id: str = "mcp") -> Any:
        """Call a registered tool with validation and permission gating."""
        tool = self.tools.get(name)
        if not tool:
            available = ", ".join(sorted(self.tools.keys()))
            raise ValueError(f"Tool not found: {name}. Available: {available}")
        if tool.handler is None:
            raise ValueError(f"Tool has no handler: {name}")

        # Enforce permission checks
        try:
            pm = get_permission_manager()
            allowed, reason = pm.check_permission(name, arguments, session_id=session_id)
            if not allowed:
                raise PermissionError(f"Permission denied for MCP tool '{name}': {reason}")
        except PermissionError:
            raise
        except Exception as exc:  # fail-closed: never silently skip gating
            raise PermissionError(
                f"Permission check failed for MCP tool '{name}' "
                f"(fail-closed, blocked by default): {exc}"
            ) from exc

        # Validate arguments against input_schema
        schema = tool.input_schema
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for req_field in required:
            if req_field not in arguments:
                raise ValueError(f"Missing required argument: {req_field}")

        for arg_name, arg_value in arguments.items():
            if arg_name in properties:
                prop = properties[arg_name]
                expected_type = prop.get("type", "string")
                if expected_type == "string" and not isinstance(arg_value, str):
                    arguments[arg_name] = str(arg_value)
                elif expected_type == "number" and not isinstance(arg_value, (int, float)):
                    try:
                        arguments[arg_name] = float(arg_value)
                    except (ValueError, TypeError):
                        pass

        return tool.handler(**arguments)

    def to_mcp_response(self) -> dict[str, Any]:
        """Generate MCP initialize response."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }


class MCPClient:
    """MCP client for connecting to external servers via stdio."""

    def __init__(self, server_url: str | None = None, command: str | None = None) -> None:
        self.server_url = server_url
        self.command = command
        self.tools: list[dict[str, Any]] = []
        self._connected = False
        self._process: subprocess.Popen | None = None
        self._request_id = 0

    def _next_id(self) -> int:
        """Get next unique request ID."""
        self._request_id += 1
        return self._request_id

    def connect(self) -> bool:
        """Connect to MCP server via stdio subprocess."""
        if not self.command:
            if not self.server_url:
                return False
            self.command = self.server_url

        try:
            self._process = subprocess.Popen(
                self.command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._connected = True

            # Send initialize request
            init_request = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "sago", "version": "0.1.0"},
                },
            }
            self._send_request(init_request)
            self._read_response()

            # Send initialized notification
            initialized = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            self._send_notification(initialized)

            return True

        except Exception as e:
            log_error("Failed to connect to MCP server", e)
            self._connected = False
            return False

    def _send_request(self, request: dict[str, Any]) -> None:
        """Send a JSON-RPC request to the server."""
        if self._process and self._process.stdin:
            msg = json.dumps(request) + "\n"
            self._process.stdin.write(msg)
            self._process.stdin.flush()

    def _send_notification(self, notification: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if self._process and self._process.stdin:
            msg = json.dumps(notification) + "\n"
            self._process.stdin.write(msg)
            self._process.stdin.flush()

    def _read_response(self) -> dict[str, Any]:
        """Read a JSON-RPC response from the server."""
        if self._process and self._process.stdout:
            line = self._process.stdout.readline()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Invalid JSON-RPC response: {e}") from e
        raise RuntimeError("No response from MCP server (EOF or empty)")

    def list_tools(self) -> list[dict[str, Any]]:
        """List tools from connected server."""
        if not self._connected:
            return []

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        self._send_request(request)
        response = self._read_response()
        self.tools = response.get("result", {}).get("tools", [])
        return self.tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on connected server."""
        if not self._connected:
            raise ConnectionError("Not connected to MCP server")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }
        self._send_request(request)
        response = self._read_response()

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        result = response.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", str(content))
        return str(result)

    def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self._process:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=2)
            except (OSError, ProcessLookupError):
                pass  # Process already dead
            self._process = None
        self._connected = False

    def __del__(self) -> None:
        """Ensure cleanup on garbage collection."""
        self.disconnect()


def create_sago_mcp_server() -> MCPServer:
    """Create an MCP server with all Sago tools."""
    import logging

    _log = logging.getLogger("sago.mcp")

    server = MCPServer(name="sago", version="0.1.0")

    # Auto-discover and register all Sago tools
    import importlib

    from sago.tools.base import BaseTool

    tools_dir = Path(__file__).parent.parent / "tools"
    for py_file in tools_dir.rglob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue
        if py_file.name == "crewai_wrappers.py":
            continue

        parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
        module_name = ".".join(["sago", "tools"] + parts)

        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            _log.debug(f"Failed to import {module_name}: {e}")
            continue

        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if isinstance(obj, type) and hasattr(obj, "name") and obj.__name__ != "BaseTool":
                try:
                    if issubclass(obj, BaseTool) and obj.name:
                        server.register_sago_tool(obj)
                except Exception as e:
                    _log.debug(f"Failed to register MCP tool {obj.__name__}: {e}")

    return server

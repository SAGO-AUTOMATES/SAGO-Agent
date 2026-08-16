"""Model Context Protocol (MCP) Server Manager and Dynamic Tool Bridge.

Discovers, connects to, and manages external MCP servers (stdio, SSE, HTTP),
and dynamically wraps remote MCP tools as native SAGO BaseTools for agent execution.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, create_model

from sago.mcp.client import MCPClient
from sago.paths import get_sago_home
from sago.tools.base import BaseTool

logger = logging.getLogger("sago.mcp.manager")


class MCPServerConfig(BaseModel):
    """Configuration for an external MCP server."""

    name: str
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    timeout: float = 30.0
    isolate_env: bool = True  # Isolate environment variables from global process


def _build_pydantic_model_from_json_schema(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Dynamically generate a Pydantic BaseModel class from a JSON Schema."""
    fields: dict[str, Any] = {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for field_name, field_spec in properties.items():
        t = field_spec.get("type", "string")
        py_type: type = str
        if t == "integer":
            py_type = int
        elif t == "number":
            py_type = float
        elif t == "boolean":
            py_type = bool
        elif t == "array":
            py_type = list
        elif t == "object":
            py_type = dict

        desc = field_spec.get("description", "")
        if field_name in required:
            fields[field_name] = (py_type, Field(..., description=desc))
        else:
            default_val = field_spec.get("default", None)
            fields[field_name] = (py_type | None, Field(default=default_val, description=desc))

    return create_model(f"{name.title().replace('_', '')}Args", **fields)


class DynamicMCPTool(BaseTool):
    """Wrapper that exposes a remote MCP tool as a native SAGO BaseTool."""

    def __init__(
        self,
        name: str,
        description: str,
        client: MCPClient,
        remote_name: str,
        args_model: type[BaseModel] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self._client = client
        self._remote_name = remote_name
        self.args_model = args_model

    def _run(self, **kwargs: Any) -> Any:
        # Strip None arguments
        clean_args = {k: v for k, v in kwargs.items() if v is not None}
        return self._client.call_tool(self._remote_name, clean_args)


class MCPManager:
    """Manages configured MCP servers and bridges their tools to SAGO."""

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self._servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}
        self._cached_tools: list[BaseTool] = []
        self._load_configurations()

    def _load_configurations(self) -> None:
        """Scan standard configuration paths for MCP server definitions."""
        config_candidates = [
            get_sago_home() / "mcp_servers.json",
            get_sago_home() / "mcp.json",
            self.workspace_root / ".sago" / "mcp_servers.json",
            self.workspace_root / ".sago" / "mcp.json",
            self.workspace_root / "mcp.json",
        ]

        for p in config_candidates:
            if not p.exists() or not p.is_file():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Support standard Claude/Anthropic mcpServers format
                servers_dict = data.get("mcpServers") or data.get("servers") or data
                if isinstance(servers_dict, dict):
                    for s_name, s_cfg in servers_dict.items():
                        if not isinstance(s_cfg, dict):
                            continue
                        cfg = MCPServerConfig(
                            name=s_name,
                            command=s_cfg.get("command", ""),
                            args=s_cfg.get("args", []),
                            env=s_cfg.get("env", {}),
                            url=s_cfg.get("url", ""),
                            headers=s_cfg.get("headers", {}),
                            enabled=s_cfg.get("enabled", True),
                            timeout=float(s_cfg.get("timeout", 30.0)),
                        )
                        self._servers[s_name] = cfg
            except Exception as e:
                logger.warning("Failed to parse MCP server config at %s: %s", p, e)

    def register_server(self, config: MCPServerConfig) -> None:
        """Register or update an MCP server configuration programmatically."""
        self._servers[config.name] = config
        self._clients.pop(config.name, None)

    def list_servers(self) -> list[MCPServerConfig]:
        """List all configured MCP servers."""
        return list(self._servers.values())

    def get_client(self, name: str) -> MCPClient | None:
        """Get or initialize an MCP client for a named server.

        Environment variables are isolated per-server by default to prevent
        leaking credentials between different MCP servers and the parent process.
        """
        if name in self._clients:
            return self._clients[name]

        cfg = self._servers.get(name)
        if not cfg or not cfg.enabled:
            return None

        if cfg.url:
            server_url = cfg.url
        elif cfg.command:
            cmd_line = " ".join([cfg.command] + cfg.args)
            server_url = f"stdio://{cmd_line}"
        else:
            return None

        client = MCPClient(server_url=server_url, timeout=cfg.timeout, headers=cfg.headers)

        # Store environment variables for this server instead of polluting global env
        # The MCPClient will use these when spawning subprocesses
        if cfg.env:
            if cfg.isolate_env:
                # Store isolated environment for this client
                client._isolated_env = cfg.env
            else:
                # Legacy behavior: update global environment (deprecated)
                logger.warning(
                    "MCP server '%s' has isolate_env=False, leaking env vars globally. "
                    "This is deprecated and will be removed in a future version.",
                    name,
                )
                os.environ.update(cfg.env)

        self._clients[name] = client
        return client

    def get_mcp_tools(self) -> list[BaseTool]:
        """Discover and instantiate all tools from active MCP servers."""
        tools: list[BaseTool] = []
        for s_name, cfg in self._servers.items():
            if not cfg.enabled:
                continue
            client = self.get_client(s_name)
            if not client:
                continue

            try:
                raw_tools = client.list_tools()
                for t in raw_tools:
                    t_name = t.get("name", "")
                    t_desc = t.get("description", f"MCP Tool from {s_name}")
                    schema = t.get("inputSchema", {})

                    model_cls = (
                        _build_pydantic_model_from_json_schema(t_name, schema) if schema else None
                    )
                    bridged_tool = DynamicMCPTool(
                        name=f"mcp_{s_name}_{t_name}",
                        description=f"[{s_name}] {t_desc}",
                        client=client,
                        remote_name=t_name,
                        args_model=model_cls,
                    )
                    tools.append(bridged_tool)
            except Exception as e:
                logger.debug("Could not fetch tools from MCP server %s: %s", s_name, e)

        self._cached_tools = tools
        return tools

    def test_server(self, name: str) -> dict[str, Any]:
        """Test connection and list tools for a specific server."""
        cfg = self._servers.get(name)
        if not cfg:
            return {"success": False, "error": f"Server '{name}' not found in configuration."}

        client = self.get_client(name)
        if not client:
            return {"success": False, "error": f"Failed to instantiate client for '{name}'."}

        try:
            connected = client.connect()
            tools = client.list_tools()
            return {
                "success": connected,
                "server": name,
                "tool_count": len(tools),
                "tools": [t.get("name") for t in tools],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def close_all(self) -> None:
        """Close all open MCP client connections."""
        for client in self._clients.values():
            try:
                client.close()
            except Exception:
                pass
        self._clients.clear()


_GLOBAL_MCP_MANAGER: MCPManager | None = None


def get_mcp_manager(workspace_root: Path | str | None = None) -> MCPManager:
    """Get global singleton MCPManager."""
    global _GLOBAL_MCP_MANAGER
    if _GLOBAL_MCP_MANAGER is None or workspace_root is not None:
        _GLOBAL_MCP_MANAGER = MCPManager(workspace_root=workspace_root)
    return _GLOBAL_MCP_MANAGER

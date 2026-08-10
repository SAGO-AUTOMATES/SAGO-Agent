"""Network Config Tool - View and configure network settings.

Cross-platform network configuration viewer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class NetworkConfigArgs(BaseModel):
    """Arguments for NetworkConfigTool."""

    operation: Literal["interfaces", "connections", "dns", "routes"] = Field(
        description="What to query"
    )
    interface: str | None = Field(default=None, description="Specific interface name")


class NetworkConfigTool(BaseTool):
    """Tool for viewing network configuration."""

    name = "network_config"
    description = "View network interfaces, connections, DNS settings, and routing tables."
    args_model = NetworkConfigArgs

    def _run(
        self,
        operation: str,
        interface: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Query network configuration.

        Args:
            operation: What to query.
            interface: Specific interface.

        Returns:
            Network configuration information.
        """
        if operation == "interfaces":
            return self._get_interfaces()
        elif operation == "connections":
            return self._get_connections()
        elif operation == "dns":
            return self._get_dns()
        elif operation == "routes":
            return self._get_routes()
        return f"Error: Unknown operation: {operation}"

    def _get_interfaces(self) -> str:
        """Get network interface information."""
        if self._is_windows():
            result = self._run_command("ipconfig /all")
        elif self._is_macos():
            result = self._run_command("ifconfig")
        else:
            result = self._run_command("ip addr show")

        return (
            f"=== Network Interfaces ===\n{result.stdout}"
            if result.stdout
            else "No interface information available"
        )

    def _get_connections(self) -> str:
        """Get active network connections."""
        if self._is_windows():
            result = self._run_command("netstat -an")
        else:
            result = self._run_command("ss -tuln")

        return (
            f"=== Active Connections ===\n{result.stdout}"
            if result.stdout
            else "No connection information available"
        )

    def _get_dns(self) -> str:
        """Get DNS configuration."""
        if self._is_windows():
            result = self._run_command("ipconfig /displaydns")
        elif self._is_macos():
            result = self._run_command("scutil --dns")
        else:
            result = self._run_command("cat /etc/resolv.conf")

        return (
            f"=== DNS Configuration ===\n{result.stdout}"
            if result.stdout
            else "No DNS information available"
        )

    def _get_routes(self) -> str:
        """Get routing table."""
        if self._is_windows():
            result = self._run_command("route print")
        else:
            result = self._run_command("ip route show")

        return (
            f"=== Routing Table ===\n{result.stdout}"
            if result.stdout
            else "No routing information available"
        )

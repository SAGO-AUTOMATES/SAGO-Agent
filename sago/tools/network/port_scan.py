"""Port Scanner Tool - Scan ports on a target host.

Cross-platform port scanning with common port detection.
"""

from __future__ import annotations

import socket
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class PortScanArgs(BaseModel):
    """Arguments for PortScanTool."""

    host: str = Field(description="Target host to scan")
    ports: str = Field(default="1-1024", description="Port range (e.g., '1-1024' or '80,443,8080')")
    timeout: float = Field(default=1.0, description="Connection timeout per port in seconds")


class PortScanTool(BaseTool):
    """Tool for scanning ports on a target host."""

    name = "port_scan"
    description = "Scan ports on a target host to find open services."
    args_model = PortScanArgs

    # Common port to service mapping
    _COMMON_SERVICES: dict[int, str] = {
        21: "FTP",
        22: "SSH",
        23: "Telnet",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        110: "POP3",
        143: "IMAP",
        443: "HTTPS",
        445: "SMB",
        993: "IMAPS",
        995: "POP3S",
        1433: "MSSQL",
        1521: "Oracle",
        3306: "MySQL",
        3389: "RDP",
        5432: "PostgreSQL",
        5900: "VNC",
        6379: "Redis",
        8080: "HTTP-Alt",
        8443: "HTTPS-Alt",
        27017: "MongoDB",
    }

    def _run(
        self,
        host: str,
        ports: str = "1-1024",
        timeout: float = 1.0,
        **kwargs: Any,
    ) -> str:
        """Scan ports on a host.

        Args:
            host: Target host.
            ports: Port range or list.
            timeout: Timeout per port.

        Returns:
            Scan results.
        """
        port_list = self._parse_ports(ports)
        if not port_list:
            return "Error: Invalid port specification"

        results: list[str] = [f"=== Port Scan: {host} ===\n"]
        results.append(f"Scanning {len(port_list)} ports...\n")

        open_ports: list[tuple[int, str]] = []

        for port in port_list:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                sock.close()

                if result == 0:
                    service = self._COMMON_SERVICES.get(port, "unknown")
                    open_ports.append((port, service))
            except (TimeoutError, OSError):
                continue

        if open_ports:
            results.append(f"Open ports ({len(open_ports)}):")
            for port, service in sorted(open_ports):
                results.append(f"  {port}/{service}")
        else:
            results.append("No open ports found")

        return "\n".join(results)

    def _parse_ports(self, ports_str: str) -> list[int]:
        """Parse port specification string."""
        ports: list[int] = []

        for part in ports_str.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    ports.extend(range(int(start), int(end) + 1))
                except ValueError:
                    continue
            else:
                try:
                    ports.append(int(part))
                except ValueError:
                    continue

        return sorted(set(ports))

"""DNS Lookup Tool - Perform DNS lookups and resolve hostnames.

Cross-platform DNS resolution.
"""

from __future__ import annotations

import socket
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DNSLookupArgs(BaseModel):
    """Arguments for DNSLookupTool."""

    hostname: str = Field(description="Hostname to resolve")
    lookup_type: str = Field(default="all", description="Type: A, AAAA, MX, NS, CNAME, all")


class DNSLookupTool(BaseTool):
    """Tool for performing DNS lookups."""

    name = "dns_lookup"
    description = "Perform DNS lookups to resolve hostnames and query DNS records."
    args_model = DNSLookupArgs

    def _run(
        self,
        hostname: str,
        lookup_type: str = "all",
        **kwargs: Any,
    ) -> str:
        """Perform a DNS lookup.

        Args:
            hostname: Hostname to resolve.
            lookup_type: Record type.

        Returns:
            DNS resolution results.
        """
        results: list[str] = [f"=== DNS Lookup: {hostname} ===\n"]

        # Basic resolution
        try:
            ips = socket.getaddrinfo(hostname, None)
            unique_ips = list(set(addr[4][0] for addr in ips))
            results.append("IP Addresses:")
            for ip in unique_ips:
                results.append(f"  {ip}")
        except socket.gaierror as e:
            results.append(f"Resolution failed: {e}")

        # Get hostname info
        try:
            host_info = socket.gethostbyname_ex(hostname)
            results.append(f"\nHost name: {host_info[0]}")
            results.append(f"Aliases: {host_info[1]}")
            results.append(f"IPs: {host_info[2]}")
        except socket.herror:
            pass

        # Use system dig/nslookup if available
        if lookup_type != "simple":
            for cmd_name, cmd in [
                ("dig", ["dig", hostname]),
                ("nslookup", ["nslookup", hostname]),
            ]:
                result = self._run_command(cmd, timeout=10)
                if result.returncode == 0 and result.stdout:
                    results.append(f"\n--- {cmd_name} output ---")
                    results.append(result.stdout.strip()[:2000])
                    break

        return "\n".join(results)

"""DNS Lookup Tool - Perform DNS lookups and resolve hostnames.

Cross-platform DNS resolution using the standard library, with optional
record-type queries via the system `dig` binary when available.
"""

from __future__ import annotations

import socket
import subprocess
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DNSLookupArgs(BaseModel):
    """Arguments for DNSLookupTool."""

    hostname: str = Field(description="Hostname to resolve")
    lookup_type: str = Field(default="all", description="Type: A, AAAA, MX, NS, CNAME, all, simple")


class DNSLookupTool(BaseTool):
    """Tool for performing DNS lookups."""

    name = "dns_lookup"
    description = "Perform DNS lookups to resolve hostnames and query DNS records."
    args_model = DNSLookupArgs

    def _query_record(self, hostname: str, record_type: str) -> list[str] | None:
        """Query a specific DNS record type via `dig` if available.

        Returns a list of answer lines, or None when dig is unavailable or produced
        no output. All failures are swallowed so the lookup degrades gracefully.
        """
        try:
            proc = subprocess.run(
                ["dig", "+short", record_type, hostname],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def _run(
        self,
        hostname: str,
        lookup_type: str = "all",
        **kwargs: Any,
    ) -> str:
        """Perform a DNS lookup.

        Args:
            hostname: Hostname to resolve.
            lookup_type: Record type (A, AAAA, MX, NS, CNAME, all, simple).

        Returns:
            Structured DNS resolution results.
        """
        requested = lookup_type.strip().lower()
        lines: list[str] = [f"=== DNS Lookup: {hostname} (type={requested}) ==="]

        # Basic address resolution via stdlib (works for A/AAAA).
        try:
            infos = socket.getaddrinfo(hostname, None)
            unique_ips = sorted({addr[4][0] for addr in infos})
            lines.append("IP Addresses:")
            for ip in unique_ips:
                lines.append(f"  {ip}")
        except (socket.gaierror, socket.herror) as e:
            lines.append(f"Address resolution failed: {e}")

        # Hostname info (name, aliases, IPs).
        try:
            host_info = socket.gethostbyname_ex(hostname)
            lines.append(f"\nHost name: {host_info[0]}")
            lines.append(f"Aliases: {host_info[1]}")
            lines.append(f"IPs: {host_info[2]}")
        except (socket.herror, socket.gaierror):
            pass

        # Optional record-type queries via dig (skipped for "simple").
        if requested != "simple":
            for rtype in ("A", "AAAA", "MX", "NS", "CNAME"):
                if requested in ("all", rtype.lower()):
                    answers = self._query_record(hostname, rtype)
                    if answers:
                        lines.append(f"\n--- {rtype} records ---")
                        for answer in answers:
                            lines.append(f"  {answer}")

        return "\n".join(lines)

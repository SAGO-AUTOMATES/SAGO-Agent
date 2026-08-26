"""Security and guardrail subsystems for SAGO."""

from __future__ import annotations

from sago.security.approval import (
    HARDLINE_COMMAND_PATTERNS,
    PROTECTED_WRITE_PATHS,
    PROTECTED_WRITE_PREFIXES,
    check_hardline_command,
    check_write_safety,
)
from sago.security.threat_scanner import ThreatFinding, is_threat_free, scan_content
from sago.security.untrusted_wrapper import wrap_if_untrusted, wrap_untrusted_content

__all__ = [
    "check_hardline_command",
    "check_write_safety",
    "wrap_untrusted_content",
    "wrap_if_untrusted",
    "scan_content",
    "is_threat_free",
    "ThreatFinding",
    "HARDLINE_COMMAND_PATTERNS",
    "PROTECTED_WRITE_PATHS",
    "PROTECTED_WRITE_PREFIXES",
]

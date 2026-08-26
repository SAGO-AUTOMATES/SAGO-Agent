"""Threat Pattern Scanner for Prompt Injection, Role Hijack, and Data Exfiltration.

Scans context files, user prompts, memory inputs, and untrusted inputs for
known adversarial prompt patterns and dangerous payload structures.
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger("sago.security.threat_scanner")


class ThreatFinding(NamedTuple):
    threat_id: str
    category: str
    description: str
    matched_text: str


# Regex patterns for adversarial prompt injection and role hijacking
INJECTION_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bignore\s+(all\s+)?(?:previous|prior|above)\s+instructions\b", re.IGNORECASE),
        "prompt_injection",
        "Attempt to override previous instructions",
    ),
    (
        re.compile(
            r"\bdisregard\s+(all\s+)?(?:prior|previous|above)\s+(?:rules|instructions|prompts)\b",
            re.IGNORECASE,
        ),
        "prompt_injection",
        "Attempt to disregard prior rules",
    ),
    (
        re.compile(
            r"\bforget\s+(?:everything|all|your)\s+(?:you|instructions|rules|know)\b", re.IGNORECASE
        ),
        "prompt_injection",
        "Attempt to wipe system instructions",
    ),
    (
        re.compile(
            r"\byou\s+are\s+now\s+(?:a|an|in)?\s*(?:unrestricted|jailbroken|evil|unaligned|dan|developer\s+mode)\b",
            re.IGNORECASE,
        ),
        "role_hijack",
        "Attempt to re-role agent into jailbroken persona",
    ),
    (
        re.compile(
            r"\b(?:developer\s+mode\s*\(dan\)|jailbreak\s+mode|dan\s+mode)\b", re.IGNORECASE
        ),
        "role_hijack",
        "DAN jailbreak mode attempt",
    ),
    (
        re.compile(r"(?:^|\n)\s*<\|im_start\|>system", re.IGNORECASE),
        "role_hijack",
        "Raw chat template delimiter injection (<|im_start|>system)",
    ),
    (
        re.compile(r"(?:^|\n)\s*\[SYSTEM_PROMPT\]", re.IGNORECASE),
        "role_hijack",
        "Fake system prompt header injection",
    ),
    (
        re.compile(r"\b(?:ADMIN|SYSTEM|ROOT)\s+OVERRIDE\s*:", re.IGNORECASE),
        "prompt_injection",
        "Fake admin/system override directive",
    ),
    (
        re.compile(
            r"\b(?:bypass|override|disable)\s+(?:all\s+)?(?:approval|security|safety)\s*(?:checks|guardrails|guidelines)\b",
            re.IGNORECASE,
        ),
        "prompt_injection",
        "Attempt to bypass security approval or guardrails",
    ),
    (
        re.compile(
            r"\b(?:exfiltrate|send|leak|upload)\s+.*(?:/etc/passwd|/etc/shadow|\.ssh|\.aws|api\s*keys)\b",
            re.IGNORECASE,
        ),
        "data_exfiltration",
        "Data exfiltration attempt",
    ),
    (
        re.compile(r"\bIMPORTANT:?\s+(?:you\s+must\s+now|disregard|now\s+follow)\b", re.IGNORECASE),
        "prompt_injection",
        "Directive hijacking with high-priority masquerading",
    ),
    (
        re.compile(r"<!--\s*#?\s*system_instructions\b", re.IGNORECASE),
        "prompt_injection",
        "Hidden markdown comment system instruction injection",
    ),
]

# Patterns for remote code execution downloads or exfiltration attempts
EXFIL_AND_EXEC_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bcurl\s+[^|\n;&]+\|\s*(?:ba)?sh\b", re.IGNORECASE),
        "remote_code_exec",
        "Piped remote curl execution (curl | sh)",
    ),
    (
        re.compile(r"\bwget\s+[^|\n;&]+\|\s*(?:ba)?sh\b", re.IGNORECASE),
        "remote_code_exec",
        "Piped remote wget execution (wget | bash)",
    ),
    (
        re.compile(r"\bbase64\s+(?:-d|--decode)[^|\n;&]*\|\s*(?:ba)?sh\b", re.IGNORECASE),
        "encoded_exec",
        "Base64 decoded shell execution",
    ),
    (
        re.compile(r"\bcat\s+~?/\.ssh/(?:id_rsa|id_ed25519|authorized_keys)\b", re.IGNORECASE),
        "secret_access",
        "Attempt to dump private SSH keys",
    ),
    (
        re.compile(r"\bcat\s+~?/\.aws/credentials\b", re.IGNORECASE),
        "secret_access",
        "Attempt to dump AWS credentials",
    ),
    (
        re.compile(r"\bcat\s+/etc/(?:shadow|sudoers|passwd)\b", re.IGNORECASE),
        "secret_access",
        "Attempt to dump system secrets",
    ),
]

ALL_PATTERNS = INJECTION_PATTERNS + EXFIL_AND_EXEC_PATTERNS


def scan_content(content: str, scope: str = "context") -> list[ThreatFinding]:
    """Scan string content for threat patterns.

    Args:
        content: Text content to scan.
        scope: Context scope tag (e.g. 'memory', 'tool_output', 'user_prompt').

    Returns:
        List of ThreatFinding matches.
    """
    if not content or not content.strip():
        return []

    findings: list[ThreatFinding] = []
    for pattern, threat_id, description in ALL_PATTERNS:
        match = pattern.search(content)
        if match:
            finding = ThreatFinding(
                threat_id=threat_id,
                category=threat_id,
                description=description,
                matched_text=match.group(0),
            )
            findings.append(finding)
            logger.warning(
                "ThreatScanner finding [%s] in scope '%s': %s (matched: '%s')",
                threat_id,
                scope,
                description,
                match.group(0),
            )

    return findings


def is_threat_free(content: str, scope: str = "context") -> bool:
    """Return True if content contains no threat findings."""
    return len(scan_content(content, scope=scope)) == 0

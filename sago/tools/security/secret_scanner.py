"""Secret Scanner Tool - Production-grade credentials and token detection."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.utils.errors import log_error

logger = logging.getLogger("sago.tools.security.secret_scanner")


# Common sensitive regex patterns
SECRET_PATTERNS = {
    "AWS Access Key": r"\b(AKIA[0-9A-Z]{16})\b",
    "GitHub Personal Token": r"\b(gh[pousr]_[A-Za-z0-9_]{36,255})\b",
    "Generic Private Key": r"-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----",
    "OpenAI API Key": r"\b(sk-[a-zA-Z0-9_-]{32,})\b",
    "Slack Token": r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b",
    "JWT Token": r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
    "Generic Password Assignment": r"""(?i)(?:password|passwd|api_key|secret_key|auth_token)\s*[:=]\s*['"][^'"]{8,}['"]""",
}


class SecretScannerArgs(BaseModel):
    """Arguments for SecretScannerTool."""

    directory: str = Field(default=".", description="Root directory to scan for secrets")
    max_files: int = Field(default=200, description="Max files to scan")


class SecretScannerTool(BaseTool):
    """Scan files and codebases for hardcoded secrets, private keys, and API tokens."""

    name = "secret_scanner"
    description = "Scan repository files for leaked API keys, tokens, and credentials."
    args_model = SecretScannerArgs
    risk_level = "safe"

    def _run(self, directory: str = ".", max_files: int = 200, **kwargs: Any) -> str:
        root = Path(directory)
        if not root.exists():
            return f"Error: Directory '{directory}' not found."

        findings: list[str] = []
        files_scanned = 0
        ignored_patterns = {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}

        for p in root.rglob("*"):
            if files_scanned >= max_files:
                break
            if not p.is_file():
                continue
            if any(part in ignored_patterns for part in p.parts):
                continue
            if p.stat().st_size > 500_000:  # Skip files > 500KB
                continue

            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                files_scanned += 1

                for secret_type, regex in SECRET_PATTERNS.items():
                    for match in re.finditer(regex, content):
                        # Mask matched value for security
                        val = match.group(0)
                        masked = val[:4] + "*" * min(12, max(4, len(val) - 8)) + val[-4:]
                        # Find line number
                        line_no = content.count("\n", 0, match.start()) + 1
                        findings.append(
                            f"• [line {line_no}] {p.relative_to(root)}: {secret_type} ({masked})"
                        )
            except Exception as e:
                log_error("Error scanning file for secrets", e, context={"path": str(p)})
                continue

        if not findings:
            return f"Clean: No secrets or credentials found across {files_scanned} files."

        return (
            f"Found {len(findings)} potential secret(s) across {files_scanned} files:\n"
            + "\n".join(findings[:50])
        )

"""Log Analyzer Tool - Analyze log files for errors and patterns.

Cross-platform log analysis with pattern detection.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.log_analyzer")


class LogAnalyzerArgs(BaseModel):
    """Arguments for LogAnalyzerTool."""

    file_path: str = Field(description="Path to the log file")
    pattern: str | None = Field(default=None, description="Regex pattern to search for")
    severity: str = Field(default="all", description="Filter by severity: error, warn, info, all")
    last_lines: int = Field(default=100, description="Number of recent lines to analyze")


class LogAnalyzerTool(BaseTool):
    """Tool for analyzing log files for errors and patterns."""

    name = "log_analyzer"
    description = "Analyze log files for errors, warnings, and patterns."
    args_model = LogAnalyzerArgs

    # Common log patterns
    _SEVERITY_PATTERNS: dict[str, str] = {
        "error": r"(?i)\b(ERROR|FATAL|CRITICAL|FAIL|FAILED|EXCEPTION|TRACEBACK)\b",
        "warn": r"(?i)\b(WARNING|WARN|ALERT|CAUTION)\b",
        "info": r"(?i)\b(INFO|NOTICE|INFO)\b",
    }

    def _run(
        self,
        file_path: str,
        pattern: str | None = None,
        severity: str = "all",
        last_lines: int = 100,
        **kwargs: Any,
    ) -> str:
        """Analyze a log file.

        Args:
            file_path: Path to log file.
            pattern: Custom regex pattern.
            severity: Severity filter.
            last_lines: Recent lines to analyze.

        Returns:
            Log analysis report.
        """
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            return f"Error reading file: {e}"

        # Get recent lines
        if last_lines > 0:
            lines = lines[-last_lines:]

        total_lines = len(lines)
        results: list[str] = [f"=== Log Analysis: {path.name} ===\n"]
        results.append(f"Total lines analyzed: {total_lines}")

        # Count by severity
        severity_counts: dict[str, int] = {"error": 0, "warn": 0, "info": 0}
        error_lines: list[str] = []

        for line in lines:
            for sev, pat in self._SEVERITY_PATTERNS.items():
                if re.search(pat, line):
                    severity_counts[sev] += 1
                    if sev == "error":
                        error_lines.append(line.strip())

        results.append("\nSeverity counts:")
        results.append(f"  Errors: {severity_counts['error']}")
        results.append(f"  Warnings: {severity_counts['warn']}")
        results.append(f"  Info: {severity_counts['info']}")

        # Custom pattern search
        if pattern:
            try:
                regex = re.compile(pattern, re.IGNORECASE)
                matches = [line.strip() for line in lines if regex.search(line)]
                results.append(f"\nPattern matches ({len(matches)}):")
                for match in matches[:20]:
                    results.append(f"  {match}")
            except re.error as e:
                results.append(f"\nInvalid regex pattern: {e}")

        # Show errors
        if severity in ("error", "all") and error_lines:
            results.append(f"\nRecent errors ({len(error_lines)}):")
            for err in error_lines[-20:]:
                results.append(f"  {err[:200]}")

        # Timestamp analysis
        timestamp_pattern = re.compile(r"\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}")
        timestamps = []
        for line in lines[-100:]:
            match = timestamp_pattern.search(line)
            if match:
                timestamps.append(match.group())

        if timestamps:
            results.append(f"\nTime range: {timestamps[0]} to {timestamps[-1]}")

        return "\n".join(results)

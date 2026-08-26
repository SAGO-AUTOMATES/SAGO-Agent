"""Tool Loop Guardrails and Runaway Execution Breaker.

Tracks tool call signatures (SHA-256 of tool name + sorted arguments), consecutive
failures, identical read results, and runaway loop caps to prevent token burning.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger("sago.engine.tool_guardrails")


class ToolGuardrails:
    """Circuit breaker and loop prevention for agent tool execution."""

    def __init__(
        self,
        max_identical_failures: int = 4,
        max_total_tool_failures: int = 8,
        max_search_calls_per_turn: int = 25,
        max_no_progress_reads: int = 5,
    ) -> None:
        self.max_identical_failures = max_identical_failures
        self.max_total_tool_failures = max_total_tool_failures
        self.max_search_calls_per_turn = max_search_calls_per_turn
        self.max_no_progress_reads = max_no_progress_reads

        self._exact_failures: dict[str, int] = defaultdict(int)
        self._tool_failures: dict[str, int] = defaultdict(int)
        self._tool_results: dict[str, str] = {}
        self._no_progress_counts: dict[str, int] = defaultdict(int)
        self._search_count: int = 0

    def _compute_signature(self, tool_name: str, args: dict[str, Any] | None) -> str:
        """Compute a deterministic short hash for tool_name + args."""
        try:
            serialized_args = json.dumps(args or {}, sort_keys=True, default=str)
        except Exception:
            serialized_args = str(sorted((args or {}).items()))
        raw = f"{tool_name}:{serialized_args}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def before_call(self, tool_name: str, args: dict[str, Any] | None = None) -> str | None:
        """Check if the proposed tool call should be blocked before execution.

        Args:
            tool_name: The tool about to be called.
            args: Tool arguments dictionary.

        Returns:
            Block reason string if blocked, None if allowed.
        """
        # Hard cap on runaway search calls in a single turn/session
        if tool_name in {"web_search", "web_fetch", "web_crawler"}:
            self._search_count += 1
            if self._search_count > self.max_search_calls_per_turn:
                logger.warning(
                    "ToolGuardrails blocked runaway web search loop (%d calls)", self._search_count
                )
                return f"BLOCKED: Runaway search loop detected (exceeded {self.max_search_calls_per_turn} calls this turn)."

        # Check identical tool call failure threshold
        sig = self._compute_signature(tool_name, args)
        if self._exact_failures[sig] >= self.max_identical_failures:
            logger.warning(
                "ToolGuardrails tripped on exact failure: %s with args hash %s (count: %d)",
                tool_name,
                sig,
                self._exact_failures[sig],
            )
            return (
                f"BLOCKED: Tool '{tool_name}' has failed {self._exact_failures[sig]} times with identical arguments. "
                "Change arguments, inspect earlier errors, or try an alternative approach."
            )

        # Check aggregate failure threshold on this tool
        if self._tool_failures[tool_name] >= self.max_total_tool_failures:
            logger.warning(
                "ToolGuardrails tripped on aggregate tool failure: %s (count: %d)",
                tool_name,
                self._tool_failures[tool_name],
            )
            return (
                f"BLOCKED: Tool '{tool_name}' reached failure threshold ({self._tool_failures[tool_name]} failures). "
                "Please synthesize what is known or use another tool."
            )

        # Check no-progress loop threshold
        if self._no_progress_counts[tool_name] >= self.max_no_progress_reads:
            logger.warning(
                "ToolGuardrails tripped on no-progress loop: %s (count: %d)",
                tool_name,
                self._no_progress_counts[tool_name],
            )
            return (
                f"BLOCKED: Tool '{tool_name}' returned identical results {self._no_progress_counts[tool_name]} times "
                "with no new information gained. Move on to the next step."
            )

        return None

    def after_call(
        self,
        tool_name: str,
        args: dict[str, Any] | None,
        result: str,
        success: bool = True,
    ) -> None:
        """Record execution outcome to update guardrail states.

        Args:
            tool_name: Executed tool name.
            args: Arguments passed to the tool.
            result: Result string from the tool.
            success: Whether the tool executed without reporting errors.
        """
        sig = self._compute_signature(tool_name, args)

        # Detect error indicators in result text even if exception wasn't thrown
        is_failure = not success
        if not is_failure and isinstance(result, str):
            res_lower = result.lower()
            if res_lower.startswith("error:") or res_lower.startswith("error in "):
                is_failure = True

        if is_failure:
            self._exact_failures[sig] += 1
            self._tool_failures[tool_name] += 1
        else:
            # Success on this signature resets its exact failure count
            if sig in self._exact_failures:
                self._exact_failures[sig] = max(0, self._exact_failures[sig] - 1)

        # No-progress detection for read-only tools
        if tool_name in {
            "read_file",
            "search_files",
            "glob_files",
            "grep_content",
            "web_search",
            "web_fetch",
        }:
            result_hash = hashlib.sha256((result or "").encode("utf-8")).hexdigest()[:16]
            last_hash = self._tool_results.get(tool_name)

            if last_hash == result_hash and len(result or "") > 0:
                self._no_progress_counts[tool_name] += 1
            else:
                self._no_progress_counts[tool_name] = 0

            self._tool_results[tool_name] = result_hash

    def reset(self) -> None:
        """Reset all tracking counters (e.g., at turn or session start)."""
        self._exact_failures.clear()
        self._tool_failures.clear()
        self._tool_results.clear()
        self._no_progress_counts.clear()
        self._search_count = 0

"""Parallel Tool Dispatcher for Read-Only and Independent Operations.

Safely executes independent, side-effect free tools concurrently using a thread pool,
while maintaining deterministic sequential ordering for mutating file and shell operations.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger("sago.tools.parallel_executor")

# Set of tools known to be strictly read-only and free of mutating side-effects
READ_ONLY_TOOLS: set[str] = {
    "read_file",
    "list_dir",
    "search_code",
    "glob_files",
    "grep_content",
    "code_analyzer",
    "log_analyzer",
    "os_detector",
    "env_info",
    "dns_lookup",
    "port_scan",
    "http_client",
    "pdf_reader",
    "regex_tester",
    "diff_tool",
    "hash_checksum",
    "text_summarizer",
    "web_search",
    "web_fetch",
    "web_crawler",
    "ast_grep",
    "search_symbols",
    "git_blame",
    "secret_scanner",
}


def is_read_only_tool(tool_name: str) -> bool:
    """Check whether a tool is read-only and safe for parallel execution."""
    return tool_name in READ_ONLY_TOOLS


def execute_tools_batch(
    tool_calls: list[dict[str, Any]],
    executor_fn: Callable[[dict[str, Any]], Any],
    max_workers: int = 4,
) -> list[Any]:
    """Execute a list of tool calls with safe concurrency for read-only operations.

    Args:
        tool_calls: List of tool call objects (e.g. [{'id': ..., 'name': ..., 'args': ...}]).
        executor_fn: Single tool dispatch function taking a tool_call item.
        max_workers: Thread pool size for parallel execution.

    Returns:
        List of results in the original tool_calls order.
    """
    if not tool_calls:
        return []

    # If only 1 tool call or concurrency disabled, execute sequentially
    if len(tool_calls) == 1 or max_workers <= 1:
        return [executor_fn(tc) for tc in tool_calls]

    # Check if all tools are read-only
    all_read_only = all(is_read_only_tool(tc.get("name", "")) for tc in tool_calls)

    if all_read_only:
        logger.debug(
            "Executing all %d tool calls concurrently (%d workers)", len(tool_calls), max_workers
        )
        results: list[Any] = [None] * len(tool_calls)
        with ThreadPoolExecutor(max_workers=min(len(tool_calls), max_workers)) as pool:
            future_to_idx = {pool.submit(executor_fn, tc): idx for idx, tc in enumerate(tool_calls)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("Error executing parallel tool index %d: %s", idx, e)
                    results[idx] = f"Error in parallel execution: {e}"
        return results

    # Mixed or mutating calls: execute sequentially to avoid write race conditions
    logger.debug("Executing %d tool calls sequentially (mutating tools present)", len(tool_calls))
    return [executor_fn(tc) for tc in tool_calls]

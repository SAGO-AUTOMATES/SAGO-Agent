"""Subagent Tool Isolation and Policy Enforcement.

Defines tool restriction policies for delegated subagents to prevent
recursive subagent spawning, user question loops, and dangerous operations.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("sago.agents.subagent_isolation")

# Tools strictly blocked from subagent execution
SUBAGENT_BLOCKED_TOOLS: frozenset[str] = frozenset(
    {
        "delegate_to_agent",
        "agent_delegator",
        "spawn_agent",
        "ask_question",  # subagents cannot block on interactive user prompts
        "session_manager",
    }
)


def filter_tools_for_subagent(
    tools: list[Any] | set[str] | dict[str, Any],
) -> list[Any]:
    """Filter out prohibited tools for subagents.

    Args:
        tools: List of tool objects, tool name strings, or tool dictionary mappings.

    Returns:
        Filtered collection safe for child subagent dispatch.
    """
    if isinstance(tools, dict):
        return [tool for name, tool in tools.items() if name not in SUBAGENT_BLOCKED_TOOLS]

    filtered = []
    for t in tools:
        name = getattr(t, "name", str(t))
        if name not in SUBAGENT_BLOCKED_TOOLS:
            filtered.append(t)
        else:
            logger.debug("Filtered out blocked tool '%s' for subagent", name)

    return filtered


def is_tool_allowed_for_subagent(tool_name: str) -> bool:
    """Check if a specific tool name is allowed for a subagent."""
    return tool_name not in SUBAGENT_BLOCKED_TOOLS

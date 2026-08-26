"""Prompt Caching Utilities for LLM Providers.

Attaches provider-specific cache control markers (Anthropic ephemeral breakpoints,
OpenAI cached prompt blocks) to system prompts and historical message prefixes.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("sago.llm.caching")


def format_anthropic_system_with_cache(
    system_prompt: str | list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Format Anthropic system prompt with ephemeral prompt caching control.

    Args:
        system_prompt: Plain text system prompt or list of block dicts.

    Returns:
        Structured system prompt list with cache_control enabled, or None.
    """
    if not system_prompt:
        return None

    if isinstance(system_prompt, str):
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    if isinstance(system_prompt, list):
        blocks = []
        for i, block in enumerate(system_prompt):
            block_copy = dict(block)
            if i == len(system_prompt) - 1:  # mark the last system block for cache
                block_copy["cache_control"] = {"type": "ephemeral"}
            blocks.append(block_copy)
        return blocks

    return None


def format_anthropic_messages_with_cache(
    messages: list[dict[str, Any]],
    cache_last_turns: int = 2,
) -> list[dict[str, Any]]:
    """Inject cache_control into long conversation turns for Anthropic API.

    Args:
        messages: List of OpenAI/Anthropic message dictionaries.
        cache_last_turns: Number of recent turns to mark with cache breakpoints.

    Returns:
        Modified message list with ephemeral cache_control blocks.
    """
    if not messages:
        return []

    formatted: list[dict[str, Any]] = []
    total = len(messages)

    for i, msg in enumerate(messages):
        msg_copy = dict(msg)
        content = msg_copy.get("content")

        # Check if this message index qualifies for cache breakpoint
        should_cache = (i >= total - cache_last_turns) and (i > 0)

        if should_cache and isinstance(content, str) and len(content) > 100:
            msg_copy["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        formatted.append(msg_copy)

    return formatted

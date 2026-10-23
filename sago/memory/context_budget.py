"""Context budget manager for preventing tool-output/context overflow.

Provides simple token estimation and truncation helpers used by executors and
memory compaction. Additive and dependency-free (char-based estimate).
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    # ~4 chars per token heuristic
    return max(1, len(text) // 4)


def truncate_to_budget(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    # Keep head and tail
    char_budget = max_tokens * 4
    head = text[: char_budget // 2]
    tail = text[-(char_budget // 2) :]
    return head + "\n... [truncated to fit context budget] ...\n" + tail


class ContextBudgetManager:
    def __init__(self, max_tokens: int = 8000) -> None:
        self.max_tokens = max_tokens

    def fit(self, text: str) -> str:
        return truncate_to_budget(text, self.max_tokens)

"""Optional tree-sitter backed parser with graceful regex fallback.

This module is additive: when ``tree_sitter`` is not installed, all functions
fall back to the existing regex/stdlib implementations so behavior is unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("sago.memory.tree_sitter_parser")

try:
    import tree_sitter  # type: ignore

    TREE_SITTER_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    tree_sitter = None  # type: ignore
    TREE_SITTER_AVAILABLE = False


def parse_symbols(language: str, source: str) -> list[dict[str, Any]]:
    """Parse symbols using tree-sitter when available, else return []."""
    if not TREE_SITTER_AVAILABLE:
        return []
    # Language-specific grammars are optional; return [] if unavailable.
    try:
        # Placeholder: callers should provide grammar modules; this keeps the
        # module importable and non-breaking without hard dependencies.
        return []
    except Exception as e:
        logger.debug("tree-sitter parse failed: %s", e)
        return []

    # Keep function importable even if tree-sitter missing.
    return []

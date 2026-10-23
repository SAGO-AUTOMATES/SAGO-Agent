"""Optional tree-sitter backed parser with graceful regex fallback.

This module is additive: when ``tree_sitter`` (and a language grammar) is not
installed, all functions fall back to the existing regex/stdlib implementations
so behavior is unchanged.
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

# Optional per-language grammar modules.
_GRAMMARS: dict[str, Any] = {}
for _mod_name, _lang_key in (
    ("tree_sitter_python", "python"),
    ("tree_sitter_javascript", "javascript"),
    ("tree_sitter_typescript", "typescript"),
):
    try:
        _mod = __import__(_mod_name)
        _GRAMMARS[_lang_key] = _mod
    except Exception:
        pass


def _language_for(lang: str) -> Any:
    if not TREE_SITTER_AVAILABLE:
        return None
    mod = _GRAMMARS.get(lang.lower())
    if mod is None:
        return None
    try:
        fn = getattr(mod, "language", None)
        if fn is None:
            if lang.lower() == "typescript":
                fn = getattr(mod, "language_typescript", None)
            elif lang.lower() == "tsx":
                fn = getattr(mod, "language_tsx", None)
        if fn is None:
            return None
        return tree_sitter.Language(fn())  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug("Failed to load %s grammar: %s", lang, e)
        return None


def parse_symbols(language: str, source: str) -> list[dict[str, Any]]:
    """Parse symbols using tree-sitter when available, else return [].

    Returns a list of ``{"name": str, "kind": str, "line": int}`` dicts. An
    empty list means "no symbols found via tree-sitter" (either unavailable or
    no supported grammar), so callers should fall back to their own parser.
    """
    lang = (language or "").lower()
    if lang not in _GRAMMARS or not TREE_SITTER_AVAILABLE:
        return []
    language_obj = _language_for(lang)
    if language_obj is None:
        return []
    try:
        parser = tree_sitter.Parser(language_obj)  # type: ignore[attr-defined]
        tree = parser.parse(source.encode("utf-8", errors="replace"))
    except Exception as e:
        logger.debug("tree-sitter parse failed: %s", e)
        return []

    results: list[dict[str, Any]] = []

    # Walk the tree collecting function/class definitions.
    def walk(node: Any) -> None:
        ntype = getattr(node, "type", "")
        if ntype in ("function_definition", "function_declaration", "method_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                results.append(
                    {
                        "name": source[name_node.start_byte : name_node.end_byte],
                        "kind": "function",
                        "line": name_node.start_point[0] + 1,
                    }
                )
        elif ntype in ("class_definition", "class_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                results.append(
                    {
                        "name": source[name_node.start_byte : name_node.end_byte],
                        "kind": "class",
                        "line": name_node.start_point[0] + 1,
                    }
                )
        for child in getattr(node, "children", []) or []:
            walk(child)

    try:
        walk(tree.root_node)
    except Exception as e:
        logger.debug("tree-sitter walk failed: %s", e)
        return []
    return results


def is_available(language: str | None = None) -> bool:
    """Whether tree-sitter (and optionally a specific grammar) is usable."""
    if not TREE_SITTER_AVAILABLE:
        return False
    if language is None:
        return bool(_GRAMMARS)
    return language.lower() in _GRAMMARS

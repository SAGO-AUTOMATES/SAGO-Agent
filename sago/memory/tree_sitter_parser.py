"""Optional tree-sitter backed parser with graceful regex fallback.

This module is additive: when ``tree_sitter`` (and a language grammar) is not
installed, all functions fall back to the existing regex/stdlib implementations
so behavior is unchanged.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("sago.memory.tree_sitter_parser")

try:
    import tree_sitter  # type: ignore

    TREE_SITTER_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    tree_sitter = None  # type: ignore
    TREE_SITTER_AVAILABLE = False

# Optional per-language grammar modules.
_GRAMMAR_MAPPING = (
    ("tree_sitter_python", "python"),
    ("tree_sitter_javascript", "javascript"),
    ("tree_sitter_typescript", "typescript"),
    ("tree_sitter_typescript", "tsx"),
    ("tree_sitter_rust", "rust"),
    ("tree_sitter_go", "go"),
    ("tree_sitter_java", "java"),
    ("tree_sitter_cpp", "cpp"),
    ("tree_sitter_c", "c"),
)

_GRAMMARS: dict[str, Any] = {}
for _mod_name, _lang_key in _GRAMMAR_MAPPING:
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


# Node types categorized by language
_FUNCTION_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "function_item",
}

_TYPE_NODE_TYPES = {
    "class_definition": "class",
    "class_declaration": "class",
    "class_specifier": "class",
    "struct_item": "struct",
    "struct_specifier": "struct",
    "trait_item": "trait",
    "enum_item": "enum",
    "enum_declaration": "enum",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "type_spec": "type",
}


def parse_symbols(language: str, source: str) -> list[dict[str, Any]]:
    """Parse symbols using tree-sitter when available, else return [].

    Returns a list of ``{"name": str, "kind": str, "line": int, "signature": str, "docstring": str}`` dicts.
    An empty list means "no symbols found via tree-sitter" (either unavailable or
    no supported grammar), so callers should fall back to their own parser.
    """
    lang = (language or "").lower()
    if lang not in _GRAMMARS or not TREE_SITTER_AVAILABLE:
        return []
    language_obj = _language_for(lang)
    if language_obj is None:
        return []

    try:
        source_bytes = source.encode("utf-8", errors="replace")
        parser = tree_sitter.Parser(language_obj)  # type: ignore[attr-defined]
        tree = parser.parse(source_bytes)
    except Exception as e:
        logger.debug("tree-sitter parse failed for %s: %s", lang, e)
        return []

    results: list[dict[str, Any]] = []

    def _get_node_text(node: Any) -> str:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _extract_docstring(node: Any) -> str:
        # Check previous sibling or first child for comment/docstring
        prev = getattr(node, "prev_sibling", None)
        if prev and getattr(prev, "type", "") in ("comment", "line_comment", "block_comment"):
            return _get_node_text(prev).strip()
        body = node.child_by_field_name("body")
        if body and getattr(body, "children", None):
            first_stmt = body.children[0]
            if getattr(first_stmt, "type", "") == "expression_statement":
                txt = _get_node_text(first_stmt).strip()
                if txt.startswith(('"""', "'''", '"', "'")):
                    return txt.strip("\"'")
        return ""

    def walk(node: Any) -> None:
        ntype = getattr(node, "type", "")

        if ntype in _FUNCTION_NODE_TYPES:
            name_node = node.child_by_field_name("name")
            if not name_node:
                # Go method or fallback
                for child in getattr(node, "children", []) or []:
                    if child.type in ("field_identifier", "identifier"):
                        name_node = child
                        break

            if name_node is not None:
                name = _get_node_text(name_node)
                body = node.child_by_field_name("body")
                if body is not None:
                    sig = (
                        source_bytes[node.start_byte : body.start_byte]
                        .decode("utf-8", errors="replace")
                        .strip()
                    )
                else:
                    sig = _get_node_text(node).split("{")[0].split(":")[0].strip()

                kind = "method" if "method" in ntype else "function"
                results.append(
                    {
                        "name": name,
                        "kind": kind,
                        "line": name_node.start_point[0] + 1,
                        "signature": sig,
                        "docstring": _extract_docstring(node),
                    }
                )

        elif ntype in _TYPE_NODE_TYPES:
            kind = _TYPE_NODE_TYPES[ntype]
            name_node = node.child_by_field_name("name")
            if not name_node:
                for child in getattr(node, "children", []) or []:
                    if child.type in ("type_identifier", "identifier"):
                        name_node = child
                        break

            if name_node is not None:
                name = _get_node_text(name_node)
                results.append(
                    {
                        "name": name,
                        "kind": kind,
                        "line": name_node.start_point[0] + 1,
                        "signature": _get_node_text(node).split("{")[0].split(":")[0].strip(),
                        "docstring": _extract_docstring(node),
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


def generate_skeleton(language: str, source: str) -> str:
    """Generate a compact AST skeleton outline of classes and functions omitting bodies.

    Allows condensing thousands of lines into minimal token representation.
    """
    lang = (language or "").lower()
    if not TREE_SITTER_AVAILABLE or lang not in _GRAMMARS:
        return _fallback_regex_skeleton(source, lang)

    language_obj = _language_for(lang)
    if language_obj is None:
        return _fallback_regex_skeleton(source, lang)

    try:
        source_bytes = source.encode("utf-8", errors="replace")
        parser = tree_sitter.Parser(language_obj)  # type: ignore[attr-defined]
        tree = parser.parse(source_bytes)

        # Collect function body byte ranges to replace with placeholder
        replacements: list[tuple[int, int, bytes]] = []

        def collect_bodies(node: Any) -> None:
            ntype = getattr(node, "type", "")
            if ntype in _FUNCTION_NODE_TYPES:
                body = node.child_by_field_name("body")
                if body is not None:
                    # In python use '...', in brace languages use ' { ... }'
                    sub = b"..." if lang == "python" else b" { ... }"
                    replacements.append((body.start_byte, body.end_byte, sub))
                    return
            for child in getattr(node, "children", []) or []:
                collect_bodies(child)

        collect_bodies(tree.root_node)

        if not replacements:
            return _fallback_regex_skeleton(source, lang)

        # Sort replacements descending by start_byte to replace from back to front
        replacements.sort(key=lambda x: x[0], reverse=True)
        mod_bytes = bytearray(source_bytes)
        for start, end, sub in replacements:
            mod_bytes[start:end] = sub

        return mod_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("generate_skeleton AST failed for %s: %s", lang, e)
        return _fallback_regex_skeleton(source, lang)


def _fallback_regex_skeleton(source: str, lang: str) -> str:
    """Regex fallback to produce skeleton when tree-sitter is unavailable."""
    lines = source.splitlines()
    out = []
    patterns = [
        r"^(?:pub\s+)?(?:async\s+)?(?:def|fn|func|function)\s+([A-Za-z0-9_]+)",
        r"^(?:pub\s+)?(?:class|struct|interface|trait|enum|type)\s+([A-Za-z0-9_]+)",
        r"^(?:export\s+)?(?:default\s+)?(?:class|interface|type)\s+([A-Za-z0-9_]+)",
    ]
    for line in lines:
        stripped = line.strip()
        if any(re.match(pat, stripped) for pat in patterns):
            sig = stripped.split("{")[0].split(":")[0].rstrip()
            suffix = ": ..." if lang == "python" else " { ... }"
            indent = " " * (len(line) - len(line.lstrip()))
            out.append(f"{indent}{sig}{suffix}")
    return "\n".join(out) if out else source[:500]


def is_available(language: str | None = None) -> bool:
    """Whether tree-sitter (and optionally a specific grammar) is usable."""
    if not TREE_SITTER_AVAILABLE:
        return False
    if language is None:
        return bool(_GRAMMARS)
    return language.lower() in _GRAMMARS

"""Symbol Search Tool for querying FTS5 symbol index."""

from __future__ import annotations

import logging
from typing import Any

from sago.memory.symbol_index import PersistentSymbolIndex
from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.search_symbol_tool")


class SearchSymbolsTool(BaseTool):
    """Tool for searching code symbols across 10,000+ files via FTS5 index."""

    name: str = "search_symbols"
    description: str = "Search for function, class, and method definitions across large codebases using indexed full-text search."

    def _run(self, query: str = "", limit: int = 20, **kwargs: Any) -> str:
        if not query:
            return "Please provide a query to search symbols."
        idx = PersistentSymbolIndex()
        matches = idx.search_symbols(query, limit=limit)
        if not matches:
            return f"No symbols found matching '{query}'."

        lines = [f"Found {len(matches)} symbol matches for '{query}':\n"]
        for m in matches:
            sig = f"({m.get('signature', '')})" if m.get("signature") else ""
            doc = f"  # {m.get('docstring')[:60]}" if m.get("docstring") else ""
            lines.append(f"• `{m['file_path']}`: {m['type']} **{m['name']}**{sig}{doc}")

        return "\n".join(lines)

"""Code Search Tool - Semantic search across codebase."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.utils.safe import log_exception

logger = logging.getLogger("sago.tools.coding.code_search_tool")


class CodeSearchArgs(BaseModel):
    """Arguments for CodeSearchTool."""

    action: str = Field(description="Action: search, index, stats, file_context")
    query: str = Field(default="", description="Search query")
    path: str = Field(default=".", description="Directory to index or file for context")
    language: str = Field(default="", description="Language filter (optional)")
    max_results: int = Field(default=10, description="Max results to return")


class CodeSearchTool(BaseTool):
    """Tool for semantic code search across the codebase."""

    name = "code_search"
    description = (
        "Search code semantically. Index the codebase first, then search "
        "for functions, classes, patterns, or concepts across all files."
    )
    args_model = CodeSearchArgs

    def _run(
        self,
        action: str,
        query: str = "",
        path: str = ".",
        language: str = "",
        max_results: int = 10,
        **kwargs: Any,
    ) -> str:
        """Run code search action."""
        from sago.memory.codebase_indexer import get_indexer

        indexer = get_indexer()

        if action == "index":
            count = indexer.index_directory(path)
            stats = indexer.get_stats()
            return (
                f"Indexed {count} code chunks from {path}\nLanguages: {stats.get('languages', {})}"
            )

        elif action == "search":
            if not query:
                return "Error: query required for search"

            results = indexer.search(
                query,
                max_results=max_results,
                language_filter=language or None,
            )

            if not results:
                # Fallback to hybrid code search for natural language queries
                try:
                    from sago.tools.coding.hybrid_search_tool import HybridSearchTool

                    hybrid = HybridSearchTool()
                    res = hybrid.execute(
                        query=query, limit=max_results, directory=path if path != "." else None
                    )
                    if res.success and res.output and not res.output.startswith("No matching"):
                        return res.output
                except Exception as e:
                    log_exception(e, "Hybrid search fallback failed")
                return f"No results for: {query}"

            lines = [f"=== Search Results for: {query} ==="]
            for i, result in enumerate(results, 1):
                r = result.to_dict()
                lines.append(
                    f"\n{i}. [{r['score']:.3f}] {r['file']}:{r['start']}-{r['end']}"
                    f" ({r['type']}: {r.get('name', 'anonymous')})"
                )
                lines.append(f"   {r['preview'][:150]}...")

            return "\n".join(lines)

        elif action == "stats":
            stats = indexer.get_stats()
            return (
                f"Index stats:\n"
                f"  Chunks: {stats['total_chunks']}\n"
                f"  Languages: {stats['languages']}\n"
                f"  Indexed at: {stats['indexed_at']}"
            )

        elif action == "file_context":
            if not path:
                return "Error: path required for file_context"
            context = indexer.get_file_context(path)
            return context

        else:
            return f"Unknown action: {action}. Use: search, index, stats, file_context"

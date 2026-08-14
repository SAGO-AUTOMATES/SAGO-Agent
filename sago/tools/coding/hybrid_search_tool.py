"""Hybrid Code Search Tool - Semantic & BM25 Codebase Search for Agents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sago.memory.hybrid_indexer import get_hybrid_code_indexer
from sago.tools.base import BaseTool, ToolCategory, ToolResult


class HybridSearchArgs(BaseModel):
    query: str = Field(
        ...,
        description="Natural language question, concept, symbol, or error message to search in codebase.",
    )
    limit: int = Field(
        default=6,
        description="Maximum number of relevant code chunks to return (default: 6).",
    )
    directory: str | None = Field(
        default=None,
        description="Optional directory path to restrict search scope.",
    )


class HybridSearchTool(BaseTool):
    """Semantic & BM25 hybrid search tool for natural language codebase navigation."""

    name: str = "hybrid_code_search"
    description: str = (
        "Search codebase using combined BM25 keyword matching and dense semantic vector embeddings. "
        "Finds functions, classes, data models, error handlers, and business logic without needing exact regex."
    )
    category: ToolCategory = ToolCategory.CODING
    args_model: type[BaseModel] = HybridSearchArgs

    def execute(self, query: str, limit: int = 6, directory: str | None = None) -> ToolResult:
        try:
            indexer = get_hybrid_code_indexer(root_dir=directory)
            results = indexer.search(query=query, limit=limit)

            if not results:
                return ToolResult(
                    output=f"No matching code snippets found for query: '{query}'",
                    metadata={"count": 0},
                )

            formatted_blocks = [
                f"=== HYBRID CODE SEARCH RESULTS for '{query}' ({len(results)} matches) ===\n"
            ]
            for i, r in enumerate(results, 1):
                chunk = r.chunk
                title = f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
                if chunk.name:
                    title += f" ({chunk.chunk_type} {chunk.name})"
                formatted_blocks.append(
                    f"[{i}] {title} (Score: {r.combined_score:.2f} | BM25: {r.bm25_score:.2f} | Vec: {r.semantic_score:.2f})\n"
                    f"```{chunk.language}\n{chunk.content}\n```\n"
                )

            return ToolResult(
                output="\n".join(formatted_blocks),
                metadata={
                    "count": len(results),
                    "results": [r.to_dict() for r in results],
                },
            )
        except Exception as e:
            return ToolResult(
                output=f"Error executing hybrid code search: {e}",
                success=False,
                error=str(e),
            )

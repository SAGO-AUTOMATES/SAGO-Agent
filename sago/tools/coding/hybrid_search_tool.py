"""Hybrid Code Search Tool - Semantic & BM25 Codebase Search for Agents."""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from sago.memory.hybrid_indexer import get_hybrid_code_indexer
from sago.tools.base import BaseTool, ToolCategory, ToolResult

logger = logging.getLogger("sago.tools.coding.hybrid_search_tool")


EMBEDDING_ENV_FLAG = "SAGO_HYBRID_EMBEDDINGS"
EMBEDDING_MODEL_ENV = "SAGO_HYBRID_EMBED_MODEL"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


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
    args_model: type[BaseModel] | None = HybridSearchArgs

    def __init__(
        self,
        use_embeddings: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        env_on = os.environ.get(EMBEDDING_ENV_FLAG, "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if use_embeddings is None:
            self.use_embeddings = env_on
        else:
            self.use_embeddings = bool(use_embeddings)
        self._embed_model: Any = None

    def _run(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        limit = int(kwargs.get("limit", 6) or 6)
        directory = kwargs.get("directory")
        result = self.execute(query=query, limit=limit, directory=directory)
        return result.output

    def _load_embedding_model(self) -> Any | None:
        """Lazily import and cache a sentence-transformers model.

        Returns None when sentence-transformers is not installed so the tool
        gracefully falls back to the hashing-based scorer.
        """
        if self._embed_model is not None:
            return self._embed_model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            self._embed_model = False
            return None
        model_name = os.environ.get(EMBEDDING_MODEL_ENV, DEFAULT_EMBEDDING_MODEL)
        try:
            self._embed_model = SentenceTransformer(model_name)
        except Exception:
            self._embed_model = False
            return None
        return self._embed_model

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        return sum(x * y for x, y in zip(a, b))

    def _rerank_with_embeddings(
        self,
        query: str,
        results: list[Any],
        limit: int,
    ) -> list[Any]:
        """Re-rank candidate chunks by real embedding cosine similarity.

        Falls back to the unmodified (hashing-based) ordering when embeddings
        are unavailable or fail to compute so behavior stays robust.
        """
        model = self._load_embedding_model()
        if model is None or not results:
            return results[:limit]

        try:
            query_emb = model.encode([query])[0]
            chunk_embs = model.encode([r.chunk.content for r in results])
        except Exception:
            return results[:limit]

        max_bm25 = max((r.bm25_score for r in results), default=1.0) or 1.0
        for r, emb in zip(results, chunk_embs):
            sim = max(0.0, float(self._cosine_similarity(list(query_emb), list(emb))))
            r.semantic_score = sim
            norm_bm25 = r.bm25_score / max_bm25
            r.combined_score = (0.4 * norm_bm25) + (0.6 * sim)

        results.sort(key=lambda r: r.combined_score, reverse=True)
        return results[:limit]

    def execute(self, query: str, limit: int = 6, directory: str | None = None) -> ToolResult:
        try:
            indexer = get_hybrid_code_indexer(root_dir=directory)
            candidate_limit = limit if not self.use_embeddings else max(limit * 3, 20)
            results = indexer.search(query=query, limit=candidate_limit)

            if self.use_embeddings:
                results = self._rerank_with_embeddings(query, results, limit)
            else:
                results = results[:limit]

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

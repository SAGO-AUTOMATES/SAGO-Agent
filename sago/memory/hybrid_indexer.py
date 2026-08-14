"""Hybrid Code Indexer - BM25 + Dense Semantic Vector Search across Multi-Language Codebases.

Combines BM25 probabilistic term ranking with local dense vector embeddings and
AST symbol boosting for fast, zero-cloud semantic code search across 1,000+ files.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.paths import get_sago_home

logger = logging.getLogger("sago.memory.hybrid_indexer")


@dataclass
class HybridCodeChunk:
    """A semantic code chunk with lexical and vector metadata."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    chunk_type: str  # "function", "class", "method", "block", "module"
    name: str | None = None
    symbols: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    vector: list[float] = field(default_factory=list)
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            self.hash = hashlib.md5(
                f"{self.file_path}:{self.start_line}:{self.content[:100]}".encode()
            ).hexdigest()[:12]
        if not self.tokens:
            self.tokens = _tokenize_code(self.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "start": self.start_line,
            "end": self.end_line,
            "type": self.chunk_type,
            "name": self.name,
            "language": self.language,
            "symbols": self.symbols,
            "preview": self.content[:300],
        }


@dataclass
class HybridSearchResult:
    """Consolidated search result combining BM25 and vector scores."""

    chunk: HybridCodeChunk
    bm25_score: float
    semantic_score: float
    combined_score: float
    matched_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.chunk.to_dict()
        d["bm25_score"] = round(self.bm25_score, 4)
        d["semantic_score"] = round(self.semantic_score, 4)
        d["score"] = round(self.combined_score, 4)
        d["matched_terms"] = self.matched_terms
        return d


def _tokenize_code(text: str) -> list[str]:
    """Tokenize source code splitting camelCase, snake_case, and identifiers."""
    # Split camelCase into words
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    # Replace non-alphanumeric characters (including underscores) with spaces
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", s1)
    tokens = [t.lower() for t in cleaned.split() if len(t) > 1 and not t.isdigit()]
    return tokens


def _compute_dense_vector(tokens: list[str], dim: int = 128) -> list[float]:
    """Compute normalized dense semantic hash vector for zero-dependency local search."""
    if not tokens:
        return [0.0] * dim

    vec = [0.0] * dim
    for tok in tokens:
        # Compute sub-token n-grams (3-gram to 5-gram)
        ngrams = [tok[i : i + n] for n in (3, 4, 5) for i in range(len(tok) - n + 1)] or [tok]
        for ng in ngrams:
            h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two normalized vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


class HybridCodeIndexer:
    """High-performance hybrid BM25 + dense vector code indexer."""

    LANGUAGE_EXTENSIONS: dict[str, str] = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".rs": "rust",
        ".go": "go",
        ".sql": "sql",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
    }

    IGNORE_DIRS = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "target",
        ".pytest_cache",
        ".ruff_cache",
        ".sago",
        "brain",
    }

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
        self.chunks: list[HybridCodeChunk] = []
        self.doc_freqs: dict[str, int] = {}  # term -> number of chunks containing term
        self.avg_doc_len: float = 0.0
        self.total_docs: int = 0
        self.is_indexed: bool = False
        self._cache_dir = get_sago_home() / "cache" / "hybrid_index"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def index_project(self, max_files: int = 2000, force_reindex: bool = False) -> int:
        """Scan and index all codebase files with BM25 statistics and dense vectors."""
        if self.is_indexed and not force_reindex:
            return len(self.chunks)

        self.chunks.clear()
        self.doc_freqs.clear()

        files_to_index: list[Path] = []
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in self.LANGUAGE_EXTENSIONS:
                    files_to_index.append(Path(root) / f)
                if len(files_to_index) >= max_files:
                    break
            if len(files_to_index) >= max_files:
                break

        total_length = 0
        for file_path in files_to_index:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                chunks = self._chunk_file(file_path, content)
                for chunk in chunks:
                    chunk.vector = _compute_dense_vector(chunk.tokens)
                    self.chunks.append(chunk)
                    total_length += len(chunk.tokens)
                    # Update document frequencies
                    unique_terms = set(chunk.tokens)
                    for term in unique_terms:
                        self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1
            except Exception as e:
                logger.debug("Failed to index %s: %s", file_path, e)

        self.total_docs = len(self.chunks)
        self.avg_doc_len = total_length / max(self.total_docs, 1)
        self.is_indexed = True
        return self.total_docs

    def _chunk_file(self, file_path: Path, content: str) -> list[HybridCodeChunk]:
        """Extract multi-granularity semantic chunks from file content."""
        chunks: list[HybridCodeChunk] = []
        rel_path = (
            str(file_path.relative_to(self.root_dir))
            if file_path.is_relative_to(self.root_dir)
            else str(file_path)
        )
        ext = file_path.suffix.lower()
        lang = self.LANGUAGE_EXTENSIONS.get(ext, "text")

        lines = content.splitlines()
        if not lines:
            return chunks

        # Extract functions/classes via regex
        chunk_patterns = [
            (r"^(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(", "function"),
            (r"^class\s+([a-zA-Z0-9_]+)", "class"),
            (r"^(?:pub\s+)?fn\s+([a-zA-Z0-9_]+)", "function"),
            (r"^(?:pub\s+)?struct\s+([a-zA-Z0-9_]+)", "class"),
            (r"^func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)", "function"),
            (r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_]+)", "function"),
            (r"^(?:export\s+)?class\s+([a-zA-Z0-9_]+)", "class"),
        ]

        # Scan for structured definition chunks
        chunk_starts: list[tuple[int, str, str]] = []  # (line_idx, name, type)
        for i, line in enumerate(lines):
            for pattern, c_type in chunk_patterns:
                m = re.search(pattern, line.strip())
                if m:
                    chunk_starts.append((i, m.group(1), c_type))
                    break

        if chunk_starts:
            for idx, (start, name, c_type) in enumerate(chunk_starts):
                end = (
                    chunk_starts[idx + 1][0]
                    if idx + 1 < len(chunk_starts)
                    else min(start + 60, len(lines))
                )
                chunk_lines = lines[start:end]
                chunk_content = "\n".join(chunk_lines)
                if len(chunk_content.strip()) > 20:
                    chunks.append(
                        HybridCodeChunk(
                            file_path=rel_path,
                            start_line=start + 1,
                            end_line=end,
                            content=chunk_content,
                            language=lang,
                            chunk_type=c_type,
                            name=name,
                            symbols=[name],
                        )
                    )

        # Also add fixed-window sliding chunks for complete repository coverage
        window_size = 40
        step = 25
        for i in range(0, len(lines), step):
            window_lines = lines[i : i + window_size]
            window_content = "\n".join(window_lines)
            if len(window_content.strip()) > 30:
                chunks.append(
                    HybridCodeChunk(
                        file_path=rel_path,
                        start_line=i + 1,
                        end_line=min(i + window_size, len(lines)),
                        content=window_content,
                        language=lang,
                        chunk_type="block",
                    )
                )

        return chunks

    def search(
        self,
        query: str,
        limit: int = 8,
        k1: float = 1.5,
        b: float = 0.75,
        alpha: float = 0.60,
    ) -> list[HybridSearchResult]:
        """Perform hybrid BM25 + dense vector code search.

        Args:
            query: Natural language or symbol query
            limit: Number of top results to return
            k1: BM25 term saturation parameter
            b: BM25 length normalization parameter
            alpha: Weight for BM25 score (1 - alpha for vector similarity)
        """
        if not self.is_indexed:
            self.index_project()

        if not self.chunks or not query.strip():
            return []

        q_tokens = _tokenize_code(query)
        q_vec = _compute_dense_vector(q_tokens)
        if not q_tokens:
            return []

        results: list[HybridSearchResult] = []
        raw_bm25: list[float] = []
        raw_vec: list[float] = []

        for chunk in self.chunks:
            # 1. Compute BM25 Score
            score_bm25 = 0.0
            matched = []
            chunk_len = len(chunk.tokens)

            for term in q_tokens:
                if term in self.doc_freqs:
                    df = self.doc_freqs[term]
                    idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
                    tf = chunk.tokens.count(term)
                    if tf > 0:
                        matched.append(term)
                        num = tf * (k1 + 1.0)
                        denom = tf + k1 * (1.0 - b + b * (chunk_len / max(self.avg_doc_len, 1.0)))
                        score_bm25 += idf * (num / denom)

            # Boost if query matches function/class name
            if chunk.name and any(q.lower() == chunk.name.lower() for q in q_tokens):
                score_bm25 *= 1.5

            # 2. Compute Dense Vector Cosine Similarity
            score_vec = max(0.0, _cosine_similarity(q_vec, chunk.vector))

            raw_bm25.append(score_bm25)
            raw_vec.append(score_vec)
            results.append(
                HybridSearchResult(
                    chunk=chunk,
                    bm25_score=score_bm25,
                    semantic_score=score_vec,
                    combined_score=0.0,
                    matched_terms=list(set(matched)),
                )
            )

        # Normalize BM25 scores to [0, 1]
        max_bm25 = max(raw_bm25) if raw_bm25 and max(raw_bm25) > 0 else 1.0
        for i, res in enumerate(results):
            norm_bm25 = raw_bm25[i] / max_bm25
            norm_vec = raw_vec[i]
            # Combined score: convex combination with symbol boost
            combined = (alpha * norm_bm25) + ((1.0 - alpha) * norm_vec)
            if res.chunk.name and any(q.lower() in res.chunk.name.lower() for q in q_tokens):
                combined += 0.15
            res.combined_score = combined

        # Sort by combined score descending
        results.sort(key=lambda r: r.combined_score, reverse=True)

        # Deduplicate overlapping chunks in the same file
        deduped: list[HybridSearchResult] = []
        seen_ranges: set[str] = set()

        for r in results:
            range_key = f"{r.chunk.file_path}:{r.chunk.start_line // 20}"
            if range_key not in seen_ranges and r.combined_score > 0.05:
                seen_ranges.add(range_key)
                deduped.append(r)
            if len(deduped) >= limit:
                break

        return deduped


_global_hybrid_indexer: HybridCodeIndexer | None = None


def get_hybrid_code_indexer(root_dir: str | Path | None = None) -> HybridCodeIndexer:
    """Singleton getter for the hybrid code indexer."""
    global _global_hybrid_indexer
    if _global_hybrid_indexer is None or (
        root_dir and _global_hybrid_indexer.root_dir != Path(root_dir).resolve()
    ):
        _global_hybrid_indexer = HybridCodeIndexer(root_dir=root_dir)
    return _global_hybrid_indexer

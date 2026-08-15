"""Hybrid Code Indexer - BM25 + Dense Semantic Vector Search across Multi-Language Codebases.

Combines BM25 probabilistic term ranking with local dense vector embeddings and
AST symbol boosting for fast, zero-cloud semantic code search across 10,000+ files.
"""

from __future__ import annotations

import hashlib
import json
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
    term_freqs: dict[str, int] = field(default_factory=dict)
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            self.hash = hashlib.md5(
                f"{self.file_path}:{self.start_line}:{self.content[:100]}".encode()
            ).hexdigest()[:12]
        if not self.tokens:
            self.tokens = _tokenize_code(self.content)
        if not self.term_freqs and self.tokens:
            freqs: dict[str, int] = {}
            for t in self.tokens:
                freqs[t] = freqs.get(t, 0) + 1
            self.term_freqs = freqs

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

    def to_cache_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "language": self.language,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "symbols": self.symbols,
            "tokens": self.tokens,
            "vector": self.vector,
            "term_freqs": self.term_freqs,
            "hash": self.hash,
        }

    @classmethod
    def from_cache_dict(cls, data: dict[str, Any]) -> HybridCodeChunk:
        chunk = cls(
            file_path=data["file_path"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            content=data["content"],
            language=data["language"],
            chunk_type=data["chunk_type"],
            name=data.get("name"),
            symbols=data.get("symbols", []),
            tokens=data.get("tokens", []),
            vector=data.get("vector", []),
            term_freqs=data.get("term_freqs", {}),
            hash=data.get("hash", ""),
        )
        return chunk


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
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", s1)
    tokens = [t.lower() for t in cleaned.split() if len(t) > 1 and not t.isdigit()]
    return tokens


def _compute_dense_vector(tokens: list[str], dim: int = 128) -> list[float]:
    """Compute normalized dense semantic hash vector for zero-dependency local search."""
    if not tokens:
        return [0.0] * dim

    vec = [0.0] * dim
    for tok in tokens:
        ngrams = [tok[i : i + n] for n in (3, 4, 5) for i in range(len(tok) - n + 1)] or [tok]
        for ng in ngrams:
            h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign

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
    """High-performance hybrid BM25 + dense vector code indexer with inverted index & disk cache."""

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
        self.inverted_index: dict[str, list[int]] = {}  # term -> list of chunk indices
        self.doc_freqs: dict[str, int] = {}  # term -> number of chunks containing term
        self.avg_doc_len: float = 0.0
        self.total_docs: int = 0
        self.is_indexed: bool = False
        self._cache_dir = get_sago_home() / "cache" / "hybrid_index"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_file(self) -> Path:
        key = hashlib.md5(str(self.root_dir).encode()).hexdigest()[:16]
        return self._cache_dir / f"idx_{key}.json"

    def _load_cache(self, files_to_index: list[Path]) -> bool:
        cache_file = self._get_cache_file()
        if not cache_file.exists():
            return False
        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)

            cached_mtimes: dict[str, float] = data.get("mtimes", {})
            current_mtimes = {str(p): p.stat().st_mtime for p in files_to_index if p.exists()}

            # If all mtimes match exactly, load directly
            if cached_mtimes == current_mtimes:
                raw_chunks = data.get("chunks", [])
                self.chunks = [HybridCodeChunk.from_cache_dict(c) for c in raw_chunks]
                self.doc_freqs = data.get("doc_freqs", {})
                self.avg_doc_len = data.get("avg_doc_len", 0.0)
                self.total_docs = len(self.chunks)

                # Rebuild in-memory inverted index
                self.inverted_index.clear()
                for idx, chunk in enumerate(self.chunks):
                    for term in chunk.term_freqs:
                        self.inverted_index.setdefault(term, []).append(idx)

                self.is_indexed = True
                return True

            # Incremental load: retain chunks for unchanged files, re-parse only changed/new files
            raw_chunks = data.get("chunks", [])
            unchanged_chunks: list[HybridCodeChunk] = []
            retained_files = set()

            for c in raw_chunks:
                fp = c.get("file_path", "")
                if fp in current_mtimes and cached_mtimes.get(fp) == current_mtimes[fp]:
                    unchanged_chunks.append(HybridCodeChunk.from_cache_dict(c))
                    retained_files.add(fp)

            # Parse only modified or newly added files
            new_chunks: list[HybridCodeChunk] = []
            for p in files_to_index:
                if str(p) not in retained_files and p.exists():
                    try:
                        content = p.read_text(encoding="utf-8", errors="ignore")
                        if content.strip():
                            parsed = self._chunk_file(p, content)
                            for chunk in parsed:
                                chunk.vector = _compute_dense_vector(chunk.tokens)
                            new_chunks.extend(parsed)
                    except Exception:
                        pass

            self.chunks = unchanged_chunks + new_chunks
            self.total_docs = len(self.chunks)
            if self.total_docs == 0:
                return False

            total_tokens = sum(len(c.tokens) for c in self.chunks)
            self.avg_doc_len = total_tokens / max(self.total_docs, 1)

            # Rebuild doc_freqs and inverted index
            self.doc_freqs.clear()
            self.inverted_index.clear()
            for idx, chunk in enumerate(self.chunks):
                for term in chunk.term_freqs:
                    self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1
                    self.inverted_index.setdefault(term, []).append(idx)

            self.is_indexed = True
            # Save updated incremental state to cache
            self._save_cache(files_to_index)
            return True
        except Exception as e:
            logger.debug("Failed to load hybrid index cache: %s", e)
            return False

    def _save_cache(self, files_to_index: list[Path]) -> None:
        cache_file = self._get_cache_file()
        try:
            current_mtimes = {str(p): p.stat().st_mtime for p in files_to_index if p.exists()}
            data = {
                "root_dir": str(self.root_dir),
                "mtimes": current_mtimes,
                "chunks": [c.to_cache_dict() for c in self.chunks],
                "doc_freqs": self.doc_freqs,
                "avg_doc_len": self.avg_doc_len,
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.debug("Failed to save hybrid index cache: %s", e)

    def index_project(self, max_files: int = 50000, force_reindex: bool = False) -> int:
        """Scan and index codebase files with BM25 statistics, dense vectors, and disk caching."""
        if self.is_indexed and not force_reindex:
            return len(self.chunks)

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

        if not force_reindex and self._load_cache(files_to_index):
            return len(self.chunks)

        self.chunks.clear()
        self.doc_freqs.clear()
        self.inverted_index.clear()

        total_length = 0
        for file_path in files_to_index:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                chunks = self._chunk_file(file_path, content)
                for chunk in chunks:
                    chunk.vector = _compute_dense_vector(chunk.tokens)
                    chunk_idx = len(self.chunks)
                    self.chunks.append(chunk)
                    total_length += len(chunk.tokens)

                    # Update inverted index and document frequencies
                    for term in chunk.term_freqs:
                        self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1
                        self.inverted_index.setdefault(term, []).append(chunk_idx)
            except Exception as e:
                logger.debug("Failed to index %s: %s", file_path, e)

        self.total_docs = len(self.chunks)
        self.avg_doc_len = total_length / max(self.total_docs, 1)
        self.is_indexed = True
        self._save_cache(files_to_index)
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

        chunk_patterns = [
            (r"^(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(", "function"),
            (r"^class\s+([a-zA-Z0-9_]+)", "class"),
            (r"^(?:pub\s+)?fn\s+([a-zA-Z0-9_]+)", "function"),
            (r"^(?:pub\s+)?struct\s+([a-zA-Z0-9_]+)", "class"),
            (r"^func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)", "function"),
            (r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_]+)", "function"),
            (r"^(?:export\s+)?class\s+([a-zA-Z0-9_]+)", "class"),
        ]

        chunk_starts: list[tuple[int, str, str]] = []
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

        # Fixed-window sliding chunks for complete repository coverage
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
        """Perform sub-millisecond hybrid BM25 + dense vector code search using inverted index."""
        if not self.is_indexed:
            self.index_project()

        if not self.chunks or not query.strip():
            return []

        q_tokens = _tokenize_code(query)
        if not q_tokens:
            return []

        q_vec = _compute_dense_vector(q_tokens)

        # Collect candidate chunk indices from inverted index
        candidate_indices: set[int] = set()
        for term in q_tokens:
            if term in self.inverted_index:
                candidate_indices.update(self.inverted_index[term])

        # If zero lexical matches found, scan the entire chunk set for dense semantic vector matches
        if not candidate_indices:
            candidate_indices = set(range(len(self.chunks)))

        results: list[HybridSearchResult] = []
        raw_bm25: list[float] = []
        raw_vec: list[float] = []

        for idx in candidate_indices:
            chunk = self.chunks[idx]
            # 1. Compute BM25 Score with O(1) term_freqs lookups
            score_bm25 = 0.0
            matched: list[str] = []
            chunk_len = len(chunk.tokens)

            for term in q_tokens:
                if term in self.doc_freqs:
                    df = self.doc_freqs[term]
                    idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
                    tf = chunk.term_freqs.get(term, 0)
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

        if not results:
            return []

        # Normalize BM25 scores to [0, 1]
        max_bm25 = max(raw_bm25) if raw_bm25 and max(raw_bm25) > 0 else 1.0
        for i, res in enumerate(results):
            norm_bm25 = raw_bm25[i] / max_bm25
            norm_vec = raw_vec[i]
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

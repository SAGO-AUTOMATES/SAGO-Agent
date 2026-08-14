"""Codebase Indexer - Semantic search across code files.

Provides fast code search using TF-IDF scoring and content indexing.
No external dependencies - uses Python's built-in math and re modules.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.paths import get_sago_home


@dataclass
class CodeChunk:
    """A chunk of code with metadata."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    chunk_type: str  # "function", "class", "import", "block", "full"
    name: str | None = None
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            self.hash = hashlib.md5(self.content.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "start": self.start_line,
            "end": self.end_line,
            "type": self.chunk_type,
            "name": self.name,
            "language": self.language,
            "preview": self.content[:200],
        }


@dataclass
class SearchResult:
    """A search result with score."""

    chunk: CodeChunk
    score: float
    match_highlights: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            **self.chunk.to_dict(),
        }


class CodebaseIndexer:
    """Index and search code files using TF-IDF scoring."""

    def __init__(self) -> None:
        self._chunks: list[CodeChunk] = []
        self._idf: dict[str, float] = {}
        self._tf_cache: dict[str, dict[str, float]] = {}
        self._indexed_at: float = 0
        self._index_path = get_sago_home() / "codebase_index.json"
        # Load persisted index if available
        self._load_index()

    def index_directory(
        self,
        directory: str,
        extensions: list[str] | None = None,
        max_file_size: int = 100_000,
        exclude_dirs: list[str] | None = None,
    ) -> int:
        """Index all code files in a directory.

        Returns number of chunks indexed.
        """
        if extensions is None:
            extensions = [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php"]

        if exclude_dirs is None:
            exclude_dirs = [
                "node_modules",
                ".git",
                "target",
                "vendor",
                "__pycache__",
                ".venv",
                "venv",
            ]

        self._chunks = []
        work_dir = Path(directory)

        for root, dirs, files in os.walk(work_dir):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in extensions:
                    continue

                fpath = os.path.join(root, fname)
                if os.path.getsize(fpath) > max_file_size:
                    continue

                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                    rel_path = os.path.relpath(fpath, work_dir)
                    language = self._detect_language(fname)
                    chunks = self._chunk_code(content, rel_path, language)
                    self._chunks.extend(chunks)
                except Exception:
                    continue

        # Build TF-IDF index
        self._build_idf()
        self._indexed_at = time.time()

        # Persist index
        self._save_index()

        return len(self._chunks)

    def _detect_language(self, filename: str) -> str:
        """Detect language from filename."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
        }
        ext = os.path.splitext(filename)[1].lower()
        return ext_map.get(ext, "unknown")

    def _chunk_code(
        self,
        content: str,
        file_path: str,
        language: str,
        max_chunk_lines: int = 50,
    ) -> list[CodeChunk]:
        """Split code into meaningful chunks."""
        lines = content.split("\n")
        chunks = []

        if language == "python":
            chunks.extend(self._chunk_python(content, file_path, lines))
        elif language in ("javascript", "typescript"):
            chunks.extend(self._chunk_js(content, file_path, lines))
        else:
            # Generic chunking by lines
            for i in range(0, len(lines), max_chunk_lines):
                chunk_lines = lines[i : i + max_chunk_lines]
                chunk_content = "\n".join(chunk_lines)
                if chunk_content.strip():
                    chunks.append(
                        CodeChunk(
                            file_path=file_path,
                            start_line=i + 1,
                            end_line=min(i + max_chunk_lines, len(lines)),
                            content=chunk_content,
                            language=language,
                            chunk_type="block",
                        )
                    )

        return chunks

    def _chunk_python(self, content: str, file_path: str, lines: list[str]) -> list[CodeChunk]:
        """Chunk Python code by functions and classes."""
        import ast

        chunks = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fall back to generic chunking
            for i in range(0, len(lines), 50):
                chunk = "\n".join(lines[i : i + 50])
                if chunk.strip():
                    chunks.append(
                        CodeChunk(
                            file_path=file_path,
                            start_line=i + 1,
                            end_line=min(i + 50, len(lines)),
                            content=chunk,
                            language="python",
                            chunk_type="block",
                        )
                    )
            return chunks

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                start = node.lineno - 1
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                chunk_content = "\n".join(lines[start:end])
                chunks.append(
                    CodeChunk(
                        file_path=file_path,
                        start_line=start + 1,
                        end_line=end,
                        content=chunk_content,
                        language="python",
                        chunk_type="function",
                        name=node.name,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                start = node.lineno - 1
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                chunk_content = "\n".join(lines[start:end])
                chunks.append(
                    CodeChunk(
                        file_path=file_path,
                        start_line=start + 1,
                        end_line=end,
                        content=chunk_content,
                        language="python",
                        chunk_type="class",
                        name=node.name,
                    )
                )

        # Add imports as a chunk
        import_lines = []
        for i, line in enumerate(lines):
            if line.strip().startswith("import ") or line.strip().startswith("from "):
                import_lines.append((i, line))
            elif import_lines and line.strip():
                break

        if import_lines:
            start_idx = import_lines[0][0]
            end_idx = import_lines[-1][0]
            import_content = "\n".join(line for _, line in import_lines)
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    start_line=start_idx + 1,
                    end_line=end_idx + 1,
                    content=import_content,
                    language="python",
                    chunk_type="import",
                )
            )

        return chunks

    def _chunk_js(self, content: str, file_path: str, lines: list[str]) -> list[CodeChunk]:
        """Chunk JS/TS code by functions and classes."""
        chunks = []

        # Functions
        for m in re.finditer(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", content):
            line_idx = content[: m.start()].count("\n")
            # Find function end (approximate)
            end_idx = min(line_idx + 30, len(lines))
            chunk_content = "\n".join(lines[line_idx:end_idx])
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    start_line=line_idx + 1,
                    end_line=end_idx,
                    content=chunk_content,
                    language="javascript",
                    chunk_type="function",
                    name=m.group(1),
                )
            )

        # Classes
        for m in re.finditer(r"(?:export\s+)?class\s+(\w+)", content):
            line_idx = content[: m.start()].count("\n")
            end_idx = min(line_idx + 50, len(lines))
            chunk_content = "\n".join(lines[line_idx:end_idx])
            chunks.append(
                CodeChunk(
                    file_path=file_path,
                    start_line=line_idx + 1,
                    end_line=end_idx,
                    content=chunk_content,
                    language="javascript",
                    chunk_type="class",
                    name=m.group(1),
                )
            )

        return chunks

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words, splitting on underscores and camelCase."""
        tokens = []
        for match in re.finditer(r"\b\w+\b", text.lower()):
            word = match.group()
            tokens.append(word)
            # Also split on underscores (check_permission -> check, permission)
            if "_" in word:
                tokens.extend(word.split("_"))
        return tokens

    def _build_idf(self) -> None:
        """Build IDF scores for all terms."""
        doc_freq: dict[str, int] = {}
        total_docs = len(self._chunks)

        for chunk in self._chunks:
            tokens = set(self._tokenize(chunk.content))
            for token in tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1

        # Compute IDF
        for token, freq in doc_freq.items():
            self._idf[token] = math.log((total_docs + 1) / (freq + 1)) + 1

    def _compute_tf(self, text: str) -> dict[str, float]:
        """Compute term frequencies."""
        tokens = self._tokenize(text)
        if not tokens:
            return {}
        tf: dict[str, float] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        # Normalize
        for token in tf:
            tf[token] /= len(tokens)
        return tf

    def search(
        self,
        query: str,
        max_results: int = 10,
        language_filter: str | None = None,
        file_filter: str | None = None,
    ) -> list[SearchResult]:
        """Search the index using TF-IDF scoring."""
        if not self._chunks:
            return []

        query_tf = self._compute_tf(query)
        results: list[SearchResult] = []

        for chunk in self._chunks:
            # Apply filters
            if language_filter and chunk.language != language_filter:
                continue
            if file_filter and file_filter not in chunk.file_path:
                continue

            # Compute TF-IDF similarity
            chunk_tf = self._compute_tf(chunk.content)
            score = 0.0

            for term, q_tf in query_tf.items():
                if term in chunk_tf:
                    idf = self._idf.get(term, 1.0)
                    score += q_tf * chunk_tf[term] * idf

            if score > 0:
                results.append(SearchResult(chunk=chunk, score=score))

        # Sort by score
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:max_results]

    def get_file_context(self, file_path: str, max_lines: int = 200) -> str:
        """Get a summary of a file for context."""
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            if len(lines) <= max_lines:
                return content

            # Return imports + first N lines
            import_lines = []
            for line in lines:
                if line.strip().startswith("import ") or line.strip().startswith("from "):
                    import_lines.append(line)
                elif line.strip() and not line.strip().startswith("#"):
                    break

            header = "\n".join(import_lines[:20])
            remaining = "\n".join(lines[max_lines - len(header.split("\n")) : max_lines])
            return f"{header}\n\n# ... ({len(lines)} total lines) ...\n\n{remaining}"
        except Exception:
            return f"Could not read {file_path}"

    def get_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        languages = {}
        for chunk in self._chunks:
            languages[chunk.language] = languages.get(chunk.language, 0) + 1

        return {
            "total_chunks": len(self._chunks),
            "languages": languages,
            "indexed_at": self._indexed_at,
        }

    def _save_index(self) -> None:
        """Persist index to disk."""
        if not self._index_path:
            return
        try:
            data = {
                "chunks": [
                    {
                        "file_path": c.file_path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "content": c.content,
                        "language": c.language,
                        "chunk_type": c.chunk_type,
                        "name": c.name,
                    }
                    for c in self._chunks
                ],
                "idf": self._idf,
                "indexed_at": self._indexed_at,
            }
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            self._index_path.write_text(json.dumps(data, default=str))
        except Exception:
            pass

    def _load_index(self) -> None:
        """Load persisted index from disk."""
        if not self._index_path or not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text())
            self._idf = data.get("idf", {})
            self._indexed_at = data.get("indexed_at", 0)
            for chunk_data in data.get("chunks", []):
                self._chunks.append(
                    CodeChunk(
                        file_path=chunk_data["file_path"],
                        start_line=chunk_data["start_line"],
                        end_line=chunk_data["end_line"],
                        content=chunk_data["content"],
                        language=chunk_data["language"],
                        chunk_type=chunk_data["chunk_type"],
                        name=chunk_data.get("name"),
                    )
                )
        except Exception:
            pass


# Global instance
_indexer: CodebaseIndexer | None = None


def get_indexer() -> CodebaseIndexer:
    """Get the global codebase indexer."""
    global _indexer
    if _indexer is None:
        _indexer = CodebaseIndexer()
    return _indexer

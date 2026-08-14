"""Tests for optional real-embedding support in the hybrid code search tool."""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import MagicMock, patch

from sago.memory.hybrid_indexer import HybridCodeChunk, HybridSearchResult
from sago.tools.base import ToolResult
from sago.tools.coding.hybrid_search_tool import (
    EMBEDDING_ENV_FLAG,
    HybridSearchTool,
)

_SENTENCE_TRANSFORMERS_AVAILABLE = importlib.util.find_spec("sentence_transformers") is not None


def _make_result(content: str = "def foo(): pass", name: str = "foo") -> HybridSearchResult:
    chunk = HybridCodeChunk(
        file_path="src/app.py",
        start_line=1,
        end_line=2,
        content=content,
        language="python",
        chunk_type="function",
        name=name,
    )
    return HybridSearchResult(
        bm25_score=1.0,
        semantic_score=0.8,
        combined_score=0.9,
        chunk=chunk,
    )


def test_default_remains_hashing_path() -> None:
    """Without opt-in, embeddings are OFF and the hashing path is used."""
    tool = HybridSearchTool()
    assert tool.use_embeddings is False

    fake_indexer = MagicMock()
    results = [_make_result(), _make_result("class Bar: pass", "Bar")]
    fake_indexer.search.return_value = results

    with patch(
        "sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer",
        return_value=fake_indexer,
    ):
        out = tool.run(query="where is foo", limit=5)

    assert isinstance(out, str)
    # The indexing/hashing path produced a valid ToolResult-shaped string.
    assert "HYBRID CODE SEARCH RESULTS" in out


def test_env_flag_default_off() -> None:
    env = os.environ.get(EMBEDDING_ENV_FLAG)
    os.environ.pop(EMBEDDING_ENV_FLAG, None)
    try:
        tool = HybridSearchTool()
        assert tool.use_embeddings is False
    finally:
        if env is not None:
            os.environ[EMBEDDING_ENV_FLAG] = env


def test_env_flag_turns_embeddings_on() -> None:
    env = os.environ.get(EMBEDDING_ENV_FLAG)
    os.environ[EMBEDDING_ENV_FLAG] = "1"
    try:
        tool = HybridSearchTool()
        assert tool.use_embeddings is True
    finally:
        if env is None:
            os.environ.pop(EMBEDDING_ENV_FLAG, None)
        else:
            os.environ[EMBEDDING_ENV_FLAG] = env


def test_explicit_flag_overrides_env() -> None:
    env = os.environ.get(EMBEDDING_ENV_FLAG)
    os.environ[EMBEDDING_ENV_FLAG] = "1"
    try:
        tool = HybridSearchTool(use_embeddings=False)
        assert tool.use_embeddings is False
    finally:
        if env is None:
            os.environ.pop(EMBEDDING_ENV_FLAG, None)
        else:
            os.environ[EMBEDDING_ENV_FLAG] = env


def test_falls_back_gracefully_when_embeddings_unavailable() -> None:
    """When embeddings are requested but sentence-transformers is missing,
    the tool must still produce a valid ToolResult using the hashing scorer."""
    tool = HybridSearchTool(use_embeddings=True)

    fake_indexer = MagicMock()
    fake_indexer.search.return_value = [_make_result()]

    with (
        patch(
            "sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer",
            return_value=fake_indexer,
        ),
        patch.object(HybridSearchTool, "_load_embedding_model", return_value=None),
    ):
        result = tool.execute(query="where is foo", limit=5)

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.metadata["count"] == 1


def test_embedding_ranking_when_available() -> None:
    """Full ranking via real embeddings. Skipped if sentence-transformers
    is not installed in the environment."""
    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        import pytest

        pytest.skip(
            "sentence-transformers is not installed; "
            "embedding ranking test skipped (optional dependency)."
        )

    tool = HybridSearchTool(use_embeddings=True)
    assert tool._load_embedding_model() is not None

    # Two candidates: one strongly related to the query, one unrelated.
    relevant = _make_result("def authenticate_user(token): verify credentials")
    irrelevant = _make_result("def render_pie_chart(data): draw slices")
    fake_indexer = MagicMock()
    fake_indexer.search.return_value = [irrelevant, relevant]

    with patch(
        "sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer",
        return_value=fake_indexer,
    ):
        result = tool.execute(query="user login and token authentication", limit=1)

    assert result.metadata["count"] == 1
    top = result.metadata["results"][0]
    assert "authenticate" in top["preview"]
    assert top["semantic_score"] >= 0.0

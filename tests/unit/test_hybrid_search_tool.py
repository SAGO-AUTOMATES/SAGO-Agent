"""Tests for the hybrid code search tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sago.memory.hybrid_indexer import HybridCodeChunk, HybridSearchResult
from sago.tools.base import ToolCategory, ToolResult
from sago.tools.coding.hybrid_search_tool import HybridSearchTool


def _make_result(content: str = "def foo(): pass") -> HybridSearchResult:
    chunk = HybridCodeChunk(
        file_path="src/app.py",
        start_line=1,
        end_line=2,
        content=content,
        language="python",
        chunk_type="function",
        name="foo",
    )
    return HybridSearchResult(
        bm25_score=1.0,
        semantic_score=0.8,
        combined_score=0.9,
        chunk=chunk,
    )


def test_tool_metadata_and_category() -> None:
    assert HybridSearchTool.name == "hybrid_code_search"
    assert HybridSearchTool.category is ToolCategory.CODING
    assert "BM25" in HybridSearchTool.description


def test_execute_returns_formatted_results() -> None:
    tool = HybridSearchTool()
    fake_indexer = MagicMock()
    fake_indexer.search.return_value = [_make_result()]

    with patch(
        "sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer",
        return_value=fake_indexer,
    ):
        result = tool.execute(query="where is foo", limit=5)

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.metadata["count"] == 1
    assert "HYBRID CODE SEARCH RESULTS" in result.output
    assert "src/app.py:1-2" in result.output


def test_execute_no_results() -> None:
    tool = HybridSearchTool()
    fake_indexer = MagicMock()
    fake_indexer.search.return_value = []

    with patch(
        "sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer",
        return_value=fake_indexer,
    ):
        result = tool.execute(query="nope")

    assert result.success is True
    assert result.metadata["count"] == 0
    assert "No matching code snippets" in result.output


def test_execute_handles_indexer_error() -> None:
    tool = HybridSearchTool()

    with patch(
        "sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer",
        side_effect=RuntimeError("boom"),
    ):
        result = tool.execute(query="x")

    assert result.success is False
    assert result.error == "boom"
    assert "Error executing hybrid code search" in result.output


def test_run_delegates_to_execute() -> None:
    tool = HybridSearchTool()
    fake_indexer = MagicMock()
    fake_indexer.search.return_value = [_make_result()]

    with patch(
        "sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer",
        return_value=fake_indexer,
    ):
        out = tool.run(query="where is foo", limit=3)

    assert isinstance(out, str)
    assert "src/app.py:1-2" in out

"""Integration tests for web search with live DDG HTML parsing."""

import httpx
import pytest

from sago.tools.web.search import (
    WebSearchTool,
    _cache_key,
    _DDGHTMLParser,
    _format_results,
)

# Real DDG HTML from August 2026 (snippet is <a class="result__snippet">)
MODERN_DDG = """
<html><body>
<h2 class="result__title"><a rel="nofollow" class="result__a" href="https://html.duckduckgo.com/l/?uddg=https%3A%2F%2Freal.example.com">Real Title</a></h2>
<a class="result__snippet" href="https://real.example.com">A helpful snippet about the topic.</a>
</body></html>
"""

# Legacy DDG HTML (snippet was inside <td>)
LEGACY_DDG = """
<html><body>
<a class="result__a" href="https://html.duckduckgo.com/l/?uddg=https%3A%2F%2Flexample.com">Legacy Title</a>
<td class="result__snippet">Legacy snippet.</td>
</body></html>
"""


def _ddg_reachable() -> bool:
    try:
        with httpx.Client(timeout=5.0, follow_redirects=True) as c:
            r = c.post(
                "https://html.duckduckgo.com/html/",
                data={"q": "test"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return r.status_code == 200
    except Exception:
        return False


class TestDDGParserModern:
    def test_modern_layout(self):
        parser = _DDGHTMLParser(max_results=5)
        parser.feed(MODERN_DDG)
        assert len(parser.results) == 1
        assert parser.results[0]["title"] == "Real Title"
        assert "real.example.com" in parser.results[0]["url"]
        assert "helpful snippet" in parser.results[0]["snippet"]

    def test_multiple_results(self):
        html = MODERN_DDG.replace("Real Title", "Title A").replace(
            "real.example.com", "a.example.com"
        )
        html += """
        <h2 class="result__title"><a rel="nofollow" class="result__a" href="https://b.example.com">Title B</a></h2>
        <a class="result__snippet" href="https://b.example.com">Snippet B.</a>
        """
        parser = _DDGHTMLParser(max_results=5)
        parser.feed(html)
        assert len(parser.results) == 2
        assert parser.results[0]["title"] == "Title A"
        assert parser.results[1]["title"] == "Title B"


class TestDDGParserLegacy:
    def test_legacy_layout(self):
        parser = _DDGHTMLParser(max_results=5)
        parser.feed(LEGACY_DDG)
        assert len(parser.results) == 1
        assert parser.results[0]["title"] == "Legacy Title"
        assert "Legacy snippet" in parser.results[0]["snippet"]


class TestFormatResults:
    def test_empty(self):
        result = _format_results("query", [])
        assert "No results found" in result

    def test_formatted(self):
        result = _format_results("test", [{"title": "T", "url": "http://x.com", "snippet": "S"}])
        assert "test" in result
        assert "T" in result
        assert "http://x.com" in result
        assert "S" in result


@pytest.mark.skipif(not _ddg_reachable(), reason="DDG not reachable")
class TestWebSearchToolLive:
    def test_live_search_returns_results(self):
        tool = WebSearchTool()
        result = tool.execute(query="python programming", max_results=3)
        assert result.success, f"Search failed: {result.output}"
        assert len(result.output) > 100
        assert "Search Results" in result.output


class TestCacheKey:
    def test_deterministic(self):
        k1 = _cache_key("hello", 5)
        k2 = _cache_key("hello", 5)
        assert k1 == k2

    def test_different_queries(self):
        assert _cache_key("a", 5) != _cache_key("b", 5)
        assert _cache_key("a", 5) != _cache_key("a", 10)

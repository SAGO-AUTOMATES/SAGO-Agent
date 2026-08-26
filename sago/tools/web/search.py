"""Web Search Tool - Multi-engine search with Tavily, Serper, and DuckDuckGo fallback.

Supports:
1. Tavily API (if TAVILY_API_KEY is set)
2. Serper API (if SERPER_API_KEY is set)
3. DuckDuckGo HTML scraping (fallback)
4. DuckDuckGo Instant Answers API (fallback)

Includes in-memory TTL cache to avoid duplicate queries.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, unquote

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

logger = logging.getLogger("sago.tools.web.search")

# Simple TTL cache
_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 300  # 5 minutes


class WebSearchArgs(BaseModel):
    """Arguments for WebSearchTool."""

    query: str = Field(description="Search query or documentation topic")
    max_results: int = Field(default=5, description="Number of results to return (1-10)")
    engine: str = Field(
        default="auto",
        description="Search engine: auto, tavily, serper, duckduckgo",
    )


class _DDGHTMLParser(HTMLParser):
    """Extract organic search results from DuckDuckGo HTML.

    Real structure (verified live, Aug 2026):
      <h2 class="result__title"><a rel="nofollow" class="result__a" href="URL">Title</a></h2>
      ...
      <a class="result__snippet" href="URL">Snippet text</a>

    Also supports legacy layout where snippet was inside <td> or <div>.
    Handles class=None safely (HTMLParser returns (key, None) for empty class).
    """

    def __init__(self, max_results: int = 5) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[dict[str, str]] = []
        self._current_title = ""
        self._current_url = ""
        self._current_snippet = ""
        self._in_title = False
        self._in_snippet = False

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> str:
        for k, v in attrs:
            if k == "class" and v:
                return v
        return ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        if tag == "a":
            href = dict(attrs).get("href", "") or ""
            if "result__a" in classes:
                self._in_title = True
                if "uddg=" in href:
                    match = re.search(r"uddg=([^&]+)", href)
                    if match:
                        href = unquote(match.group(1))
                self._current_url = href
            elif "result__snippet" in classes:
                # Modern layout: snippet is an <a> tag
                self._in_snippet = True
        elif tag in ("td", "div") and "result__snippet" in classes:
            # Legacy layout: snippet was in <td> or <div>
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            if self._in_snippet:
                self._in_snippet = False
                if self._current_url or self._current_title or self._current_snippet:
                    self.results.append(
                        {
                            "title": self._current_title.strip() or "Result",
                            "url": self._current_url.strip(),
                            "snippet": self._current_snippet.strip(),
                        }
                    )
                self._current_title = ""
                self._current_url = ""
                self._current_snippet = ""
            elif self._in_title:
                self._in_title = False
        elif tag in ("td", "div") and self._in_snippet:
            # Legacy layout: flush on closing td/div
            self._in_snippet = False
            if self._current_url or self._current_title or self._current_snippet:
                self.results.append(
                    {
                        "title": self._current_title.strip() or "Result",
                        "url": self._current_url.strip(),
                        "snippet": self._current_snippet.strip(),
                    }
                )
            self._current_title = ""
            self._current_url = ""
            self._current_snippet = ""

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title += data
        elif self._in_snippet:
            self._current_snippet += data


def _cache_key(query: str, max_results: int) -> str:
    return hashlib.md5(f"{query}:{max_results}".encode()).hexdigest()  # noqa: S324


def _get_cached(query: str, max_results: int) -> str | None:
    key = _cache_key(query, max_results)
    if key in _CACHE:
        ts, result = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return result
        del _CACHE[key]
    return None


def _set_cache(query: str, max_results: int, result: str) -> None:
    key = _cache_key(query, max_results)
    _CACHE[key] = (time.time(), result)
    # Evict old entries
    if len(_CACHE) > 200:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
        del _CACHE[oldest]


def _format_results(query: str, results: list[dict[str, str]]) -> str:
    """Format search results as markdown."""
    if not results:
        return f"No results found for '{query}'."
    formatted = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Result")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        formatted.append(f"{i}. **[{title}]({url})**\n   {snippet}")
    return f"## Search Results for: '{query}'\n\n" + "\n\n".join(formatted)


class WebSearchTool(BaseTool):
    """Search the web with multiple engines and caching."""

    name = "web_search"
    description = (
        "Search the web using Tavily, Serper, or DuckDuckGo. Returns structured "
        "results with title, URL, and snippet. Supports caching and engine selection."
    )
    category: ToolCategory = ToolCategory.WEB
    args_model: type[BaseModel] | None = WebSearchArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    def execute(
        self,
        query: str,
        max_results: int = 5,
        engine: str = "auto",
        **extra: Any,
    ) -> ToolResult:
        max_results = max(1, min(10, max_results))

        # Check cache
        cached = _get_cached(query, max_results)
        if cached:
            return ToolResult(
                output=cached,
                success=True,
                metadata={"cached": True, "query": query},
            )

        # Try engines in order
        result = None
        if engine in ("auto", "tavily"):
            result = self._search_tavily(query, max_results)
            if result:
                _set_cache(query, max_results, result)
                return ToolResult(
                    output=result, success=True, metadata={"engine": "tavily", "query": query}
                )

        if engine in ("auto", "serper"):
            result = self._search_serper(query, max_results)
            if result:
                _set_cache(query, max_results, result)
                return ToolResult(
                    output=result, success=True, metadata={"engine": "serper", "query": query}
                )

        if engine in ("auto", "duckduckgo"):
            result = self._search_ddg_html(query, max_results)
            if result:
                _set_cache(query, max_results, result)
                return ToolResult(
                    output=result, success=True, metadata={"engine": "duckduckgo", "query": query}
                )

            result = self._search_ddg_api(query, max_results)
            if result:
                _set_cache(query, max_results, result)
                return ToolResult(
                    output=result,
                    success=True,
                    metadata={"engine": "duckduckgo_api", "query": query},
                )

        return ToolResult(
            output=f"No results found for '{query}'. Try rephrasing or a different engine.",
            success=False,
            error="no_results",
            metadata={"query": query, "engine": engine},
        )

    def _search_tavily(self, query: str, max_results: int) -> str | None:
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_key:
            return None
        try:
            import httpx

            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "api_key": tavily_key, "max_results": max_results},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("content", ""),
                        }
                        for r in data.get("results", [])
                    ]
                    return _format_results(query, results)
        except Exception as e:
            logger.debug("Tavily search failed: %s", e)
        return None

    def _search_serper(self, query: str, max_results: int) -> str | None:
        serper_key = os.environ.get("SERPER_API_KEY")
        if not serper_key:
            return None
        try:
            import httpx

            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    "https://google.serper.dev/search",
                    json={"q": query, "num": max_results},
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("link", ""),
                            "snippet": r.get("snippet", ""),
                        }
                        for r in data.get("organic", [])
                    ]
                    return _format_results(query, results)
        except Exception as e:
            logger.debug("Serper search failed: %s", e)
        return None

    def _search_ddg_html(self, query: str, max_results: int) -> str | None:
        try:
            import httpx

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.5",
            }
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                    headers=headers,
                )
                if resp.status_code == 200:
                    parser = _DDGHTMLParser(max_results=max_results)
                    parser.feed(resp.text)
                    if parser.results:
                        return _format_results(query, parser.results[:max_results])
        except Exception as e:
            logger.debug("DuckDuckGo HTML search failed: %s", e)
        return None

    def _search_ddg_api(self, query: str, max_results: int) -> str | None:
        try:
            import httpx

            with httpx.Client(timeout=8.0) as client:
                url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    abstract = data.get("AbstractText")
                    if abstract:
                        results.append(
                            {
                                "title": "Direct Summary",
                                "url": data.get("AbstractURL", ""),
                                "snippet": abstract,
                            }
                        )
                    for t in data.get("RelatedTopics", [])[:max_results]:
                        if isinstance(t, dict) and "Text" in t:
                            results.append(
                                {
                                    "title": t.get("FirstURL", ""),
                                    "url": t.get("FirstURL", ""),
                                    "snippet": t.get("Text", ""),
                                }
                            )
                    return _format_results(query, results)
        except Exception as e:
            logger.debug("DuckDuckGo API search failed: %s", e)
        return None


def get_tool() -> type[WebSearchTool]:
    """Get the tool class."""
    return WebSearchTool

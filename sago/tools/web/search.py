"""Web Search & Technical Documentation Tool.

Multi-engine search client with automatic fallback:
1. Direct search extraction via DuckDuckGo HTML & Lite
2. DuckDuckGo Instant Answers API
3. Tavily API / Serper API if environment variables are set
"""

from __future__ import annotations

import logging
import os
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote_plus, unquote

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.web.search")


class WebSearchArgs(BaseModel):
    """Arguments for WebSearchTool."""

    query: str = Field(description="Search query or documentation topic")
    max_results: int = Field(default=5, description="Number of results to return (1-10)")


class _DDGHTMLParser(HTMLParser):
    """Extract organic search results from DuckDuckGo HTML."""

    def __init__(self, max_results: int = 5) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[dict[str, str]] = []
        self._current_title = ""
        self._current_url = ""
        self._current_snippet = ""
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a":
            href = attrs_dict.get("href", "")
            classes = attrs_dict.get("class", "")
            if "result__url" in classes or "result__a" in classes or "result-link" in classes:
                self._in_title = True
                # Unpack DDG redirect
                if "uddg=" in href:
                    match = re.search(r"uddg=([^&]+)", href)
                    if match:
                        href = unquote(match.group(1))
                self._current_url = href
        elif tag in ("td", "div") and "result__snippet" in attrs_dict.get("class", ""):
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        elif self._in_snippet:
            self._in_snippet = False
            if self._current_url and (self._current_title or self._current_snippet):
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


class WebSearchTool(BaseTool):
    """Search the web and technical documentation for libraries, APIs, and error solutions."""

    name = "web_search"
    description = "Search the web and technical documentation for libraries, APIs, code samples, and error fixes."
    args_model = WebSearchArgs
    risk_level = "safe"

    def _run(self, query: str, max_results: int = 5, **kwargs: Any) -> str:
        try:
            import httpx
        except ImportError:
            return "Error: httpx is required for web search. Please install httpx."

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        # 1. Check Tavily API if configured
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if tavily_key:
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(
                        "https://api.tavily.com/search",
                        json={"query": query, "api_key": tavily_key, "max_results": max_results},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = [
                            f"### [{r.get('title')}]({r.get('url')})\n{r.get('content')}"
                            for r in data.get("results", [])
                        ]
                        if results:
                            return f"## Web Search Results for: '{query}'\n\n" + "\n\n".join(
                                results
                            )
            except Exception as e:
                logger.debug("Tavily/Serper search failed: %s", e)
        try:
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
                        formatted = []
                        for res in parser.results[:max_results]:
                            formatted.append(
                                f"### [{res['title']}]({res['url']})\n{res['snippet']}"
                            )
                        return f"## Web Search Results for: '{query}'\n\n" + "\n\n".join(formatted)
        except Exception as e:
            logger.debug("DuckDuckGo HTML Lite search failed: %s", e)
        try:
            with httpx.Client(timeout=8.0) as client:
                url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    abstract = data.get("AbstractText")
                    if abstract:
                        results.append(
                            f"### Direct Summary\n{abstract}\nSource: {data.get('AbstractURL', '')}\n"
                        )
                    topics = data.get("RelatedTopics", [])
                    for t in topics[:max_results]:
                        if isinstance(t, dict) and "Text" in t:
                            results.append(f"- **{t.get('FirstURL', '')}**\n  {t.get('Text')}")
                    if results:
                        return f"## Web Search Results for: '{query}'\n\n" + "\n".join(results)
        except Exception as exc:
            return f"Search service query notice for '{query}': {exc}"

        return f"No results found for query '{query}'. Try rephrasing or checking library documentation directly."

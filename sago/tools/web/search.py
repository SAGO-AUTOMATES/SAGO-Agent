"""Web Search & Documentation Tool."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class WebSearchArgs(BaseModel):
    """Arguments for WebSearchTool."""

    query: str = Field(description="Search query or documentation topic")
    max_results: int = Field(default=5, description="Number of results to return (1-10)")


class WebSearchTool(BaseTool):
    """Search the web and official documentation for technical answers."""

    name = "web_search"
    description = (
        "Search the web and technical documentation for libraries, APIs, and error solutions."
    )
    args_model = WebSearchArgs
    risk_level = "safe"

    def _run(self, query: str, max_results: int = 5, **kwargs: Any) -> str:
        try:
            import httpx

            url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
            headers = {
                "User-Agent": "Sago-Agent/0.1.1 (https://github.com/SAGO-AUTOMATES/SAGO-Agent)"
            }

            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []

                    abstract = data.get("AbstractText")
                    abstract_url = data.get("AbstractURL")
                    if abstract:
                        results.append(f"### Direct Summary\n{abstract}\nSource: {abstract_url}\n")

                    topics = data.get("RelatedTopics", [])
                    for t in topics[:max_results]:
                        if isinstance(t, dict) and "Text" in t:
                            results.append(f"- **{t.get('FirstURL', '')}**\n  {t.get('Text')}")

                    if results:
                        return f"## Web Search Results for: '{query}'\n\n" + "\n".join(results)

            return f"No instant abstract available for '{query}'. Consider searching library documentation or checking specific source URLs."
        except Exception as exc:
            return f"Search service query notice for '{query}': {exc}"

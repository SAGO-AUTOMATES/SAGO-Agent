"""Web Crawler Tool - Crawl and scrape web pages."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class WebCrawlerArgs(BaseModel):
    """Arguments for web crawling."""

    url: str = Field(description="URL to crawl")
    max_depth: int = Field(default=1, description="Max link depth to follow")
    max_pages: int = Field(default=10, description="Max pages to crawl")
    extract_text: bool = Field(default=True, description="Extract text content")
    extract_links: bool = Field(default=True, description="Extract all links")
    extract_images: bool = Field(default=False, description="Extract image URLs")
    user_agent: str = Field(
        default="SagoBot/1.0",
        description="User agent string",
    )


class WebCrawler(BaseTool):
    """Tool for crawling and scraping web content."""

    name: str = "web_crawler"
    description: str = (
        "Crawl websites and extract content. Supports depth control, "
        "text extraction, link extraction, and image extraction."
    )
    args_model: type[BaseModel] = WebCrawlerArgs

    def _run(
        self,
        url: str,
        max_depth: int = 1,
        max_pages: int = 10,
        extract_text: bool = True,
        extract_links: bool = True,
        extract_images: bool = False,
        user_agent: str = "SagoBot/1.0",
        **kwargs: Any,
    ) -> str:
        """Crawl a website and extract content."""
        try:
            import httpx
            from urllib.parse import urljoin, urlparse
        except ImportError:
            return "Error: httpx not installed. Run: pip install httpx"

        try:
            from html.parser import HTMLParser
        except ImportError:
            return "Error: html.parser not available"

        visited: set[str] = set()
        results: list[dict[str, Any]] = []

        class ContentExtractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.text_parts: list[str] = []
                self.links: list[str] = []
                self.images: list[str] = []
                self._in_script = False
                self._in_style = False

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                attrs_dict = dict(attrs)
                if tag == "script":
                    self._in_script = True
                elif tag == "style":
                    self._in_style = True
                elif tag == "a" and extract_links and "href" in attrs_dict:
                    href = attrs_dict["href"]
                    if href:
                        self.links.append(href)
                elif tag == "img" and extract_images and "src" in attrs_dict:
                    src = attrs_dict["src"]
                    if src:
                        self.images.append(src)
                elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "span"):
                    self.text_parts.append("\n")

            def handle_endtag(self, tag: str) -> None:
                if tag == "script":
                    self._in_script = False
                elif tag == "style":
                    self._in_style = False

            def handle_data(self, data: str) -> None:
                if not self._in_script and not self._in_style:
                    text = data.strip()
                    if text:
                        self.text_parts.append(text)

        def crawl_page(current_url: str, depth: int) -> None:
            if depth > max_depth or len(visited) >= max_pages or current_url in visited:
                return

            visited.add(current_url)

            try:
                with httpx.Client(timeout=15, follow_redirects=True) as client:
                    response = client.get(current_url, headers={"User-Agent": user_agent})
                    response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return

                extractor = ContentExtractor()
                extractor.feed(response.text)

                page_data: dict[str, Any] = {"url": current_url, "status": response.status_code}

                if extract_text:
                    page_data["text"] = " ".join(extractor.text_parts)[:2000]

                if extract_links:
                    absolute_links = [
                        urljoin(current_url, link)
                        for link in extractor.links
                        if link and not link.startswith(("#", "javascript:", "mailto:"))
                    ]
                    page_data["links"] = absolute_links[:50]

                if extract_images:
                    absolute_images = [
                        urljoin(current_url, img)
                        for img in extractor.images
                        if img
                    ]
                    page_data["images"] = absolute_images[:20]

                results.append(page_data)

                # Follow links if depth allows
                if depth < max_depth:
                    for link in page_data.get("links", [])[:5]:
                        parsed = urlparse(link)
                        if parsed.scheme in ("http", "https"):
                            crawl_page(link, depth + 1)

            except Exception as e:
                results.append({"url": current_url, "error": str(e)})

        crawl_page(url, 0)

        # Format output
        output_parts = [f"Crawled {len(results)} pages starting from: {url}\n"]

        for i, page in enumerate(results, 1):
            output_parts.append(f"--- Page {i}: {page['url']} ---")
            if "error" in page:
                output_parts.append(f"Error: {page['error']}")
            else:
                if "text" in page:
                    output_parts.append(f"Text: {page['text'][:500]}...")
                if "links" in page:
                    output_parts.append(f"Links found: {len(page['links'])}")
                if "images" in page:
                    output_parts.append(f"Images found: {len(page['images'])}")
            output_parts.append("")

        return "\n".join(output_parts)


def get_tool() -> type[WebCrawler]:
    """Get the tool class."""
    return WebCrawler

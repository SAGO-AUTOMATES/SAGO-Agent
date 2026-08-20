"""Web Fetch Tool - Retrieve a URL's content with retries, HTML-to-text, and validation.

Uses the standard library urllib with exponential backoff retries, a timeout,
URL validation, content-type filtering, and optional HTML-to-text conversion.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_DEFAULT_TIMEOUT = 15
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5
_MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

# Content types considered safe to decode as text
_TEXT_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "text/css",
    "text/javascript",
    "text/xml",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
    "application/javascript",
    "application/x-yaml",
    "text/yaml",
    "text/markdown",
    "text/csv",
    "text/tab-separated-values",
}

# Tags to strip when converting HTML to text
_STRIP_TAGS = {"script", "style", "noscript", "iframe", "svg", "head"}


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML-to-text converter that extracts readable content."""

    def __init__(self) -> None:
        super().__init__()
        self._result: list[str] = []
        self._skip_depth = 0
        self._title = ""
        self._in_title = False
        self._lists: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _STRIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._result.append("\n")
        if tag == "li":
            self._result.append("\n- ")
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._result.append("\n# ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _STRIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._result.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self._title += data
            return
        text = data.strip()
        if text:
            self._result.append(text + " ")

    def get_text(self) -> str:
        raw = "".join(self._result)
        # Collapse whitespace
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()

    def get_title(self) -> str:
        return self._title.strip()


class WebFetchArgs(BaseModel):
    url: str = Field(..., description="The HTTP/HTTPS URL to fetch.")
    timeout: int = Field(
        default=_DEFAULT_TIMEOUT,
        description="Per-request timeout in seconds.",
    )
    max_retries: int = Field(
        default=_MAX_RETRIES,
        description="Number of retry attempts with exponential backoff.",
    )
    as_text: bool = Field(
        default=True,
        description="Convert HTML to clean text (strips tags, scripts, styles).",
    )
    max_length: int = Field(
        default=_MAX_CONTENT_LENGTH,
        description="Maximum content length in bytes.",
    )
    user_agent: str = Field(
        default="SAGO-WebFetch/1.0",
        description="User-Agent header string.",
    )
    follow_redirects: bool = Field(
        default=True,
        description="Follow HTTP redirects.",
    )


class WebFetchTool(BaseTool):
    """Fetch a URL's content with validation, retries, HTML-to-text, and content filtering."""

    name: str = "web_fetch"
    description: str = (
        "Fetch web content from a URL with retries, content-type filtering, "
        "and automatic HTML-to-text conversion. Returns clean text optimized "
        "for LLM context consumption. Supports configurable timeout and max length."
    )
    category: ToolCategory = ToolCategory.WEB
    args_model: type[BaseModel] | None = WebFetchArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    @staticmethod
    def _validate_url(url: str) -> tuple[bool, str]:
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            return False, f"Invalid URL: {e}"
        if parsed.scheme not in ("http", "https"):
            return False, "URL must use http or https scheme."
        if not parsed.netloc:
            return False, "URL is missing a host/netloc."
        return True, ""

    def execute(
        self,
        url: str,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
        as_text: bool = True,
        max_length: int = _MAX_CONTENT_LENGTH,
        user_agent: str = "SAGO-WebFetch/1.0",
        follow_redirects: bool = True,
        **extra: Any,
    ) -> ToolResult:
        ok, err = self._validate_url(url)
        if not ok:
            return ToolResult(
                output=err,
                success=False,
                error="invalid_url",
                metadata={"url": url},
            )

        last_error: str = ""
        redirect_chain: list[str] = []

        for attempt in range(max(1, max_retries)):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": user_agent})
                with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                    # Track redirects
                    if hasattr(resp, "url") and resp.url != url:
                        redirect_chain.append(resp.url)

                    # Check content type
                    content_type = resp.headers.get("Content-Type", "")
                    mime_type = content_type.split(";")[0].strip().lower()

                    # Check content length
                    content_length = int(resp.headers.get("Content-Length", 0))
                    if content_length > max_length:
                        return ToolResult(
                            output=f"Content too large: {content_length:,} bytes (max: {max_length:,})",
                            success=False,
                            error="content_too_large",
                            metadata={"url": url, "content_length": content_length},
                        )

                    # Read content
                    raw = resp.read(max_length + 1)
                    if len(raw) > max_length:
                        return ToolResult(
                            output=f"Content truncated: received {len(raw):,} bytes (max: {max_length:,})",
                            success=False,
                            error="content_too_large",
                            metadata={"url": url, "bytes_read": len(raw)},
                        )

                    charset = resp.headers.get_content_charset() or "utf-8"
                    text = raw.decode(charset, errors="replace")

                    # HTML-to-text conversion
                    title = ""
                    if as_text and "html" in mime_type:
                        extractor = _HTMLTextExtractor()
                        try:
                            extractor.feed(text)
                            text = extractor.get_text()
                            title = extractor.get_title()
                        except Exception:
                            pass  # Fall back to raw text

                    # Truncate if still too long
                    if len(text) > max_length:
                        text = text[:max_length] + "\n\n[TRUNCATED]"

                    metadata: dict[str, Any] = {
                        "url": url,
                        "final_url": getattr(resp, "url", url),
                        "status": getattr(resp, "status", None),
                        "content_type": content_type,
                        "bytes": len(raw),
                        "text_length": len(text),
                        "attempt": attempt + 1,
                        "html_converted": as_text and "html" in mime_type,
                    }
                    if title:
                        metadata["title"] = title
                    if redirect_chain:
                        metadata["redirect_chain"] = redirect_chain

                    return ToolResult(
                        output=text,
                        success=True,
                        metadata=metadata,
                    )

            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                if e.code == 429:
                    # Rate limited - back off more
                    time.sleep(_BACKOFF_BASE * (4**attempt))
                elif e.code >= 400:
                    return ToolResult(
                        output=f"HTTP {e.code} {e.reason} for {url}",
                        success=False,
                        error=f"http_{e.code}",
                        metadata={"url": url, "status_code": e.code},
                    )
            except urllib.error.URLError as e:
                last_error = f"URL Error: {e.reason}"
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"

            if attempt < max(1, max_retries) - 1:
                time.sleep(_BACKOFF_BASE * (2**attempt))

        return ToolResult(
            output=f"Failed to fetch {url} after {max_retries} attempt(s): {last_error}",
            success=False,
            error=last_error,
            metadata={"url": url, "attempts": max_retries},
        )


def get_tool() -> type[WebFetchTool]:
    """Get the tool class."""
    return WebFetchTool

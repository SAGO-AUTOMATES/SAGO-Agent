"""Web Fetch Tool - Retrieve a URL's content with retries and validation.

Uses the standard library urllib (no new third-party dependency) with
exponential backoff retries, a timeout, and basic URL validation.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_DEFAULT_TIMEOUT = 15
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5


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


class WebFetchTool(BaseTool):
    """Fetch a URL's text content with validation, retries, and a timeout."""

    name: str = "web_fetch"
    description: str = (
        "Fetch the text content of a URL using the standard library with URL "
        "validation, a configurable timeout, and exponential-backoff retries. "
        "Returns the content or a structured error result."
    )
    category: ToolCategory = ToolCategory.WEB
    args_model: type[BaseModel] | None = WebFetchArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(
            url=kwargs.get("url", ""),
            timeout=kwargs.get("timeout", _DEFAULT_TIMEOUT),
            max_retries=kwargs.get("max_retries", _MAX_RETRIES),
        )
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
        for attempt in range(max(1, max_retries)):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "SAGO-WebFetch/1.0"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                    raw = resp.read()
                    charset = resp.headers.get_content_charset() or "utf-8"
                    text = raw.decode(charset, errors="replace")
                return ToolResult(
                    output=text,
                    success=True,
                    metadata={
                        "url": url,
                        "status": getattr(resp, "status", None),
                        "bytes": len(raw),
                        "attempt": attempt + 1,
                    },
                )
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

"""HTTP Client Tool - Make HTTP requests to APIs.

Cross-platform HTTP client with method support.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.network.http_client")


class HTTPClientArgs(BaseModel):
    """Arguments for HTTPClientTool."""

    url: str = Field(description="URL to send request to")
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"] = Field(
        default="GET", description="HTTP method"
    )
    headers: dict[str, str] | None = Field(default=None, description="Request headers")
    body: str | None = Field(default=None, description="Request body (JSON or text)")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class HTTPClientTool(BaseTool):
    """Tool for making HTTP requests."""

    name = "http_client"
    description = "Make HTTP requests to APIs and web services."
    args_model = HTTPClientArgs

    def _run(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int = 30,
        **kwargs: Any,
    ) -> str:
        """Send an HTTP request.

        Args:
            url: Target URL.
            method: HTTP method.
            headers: Request headers.
            body: Request body.
            timeout: Timeout in seconds.

        Returns:
            Response status and body.
        """
        import httpx

        logger.debug("HTTP request: method=%s, url=%s, timeout=%d", method, url, timeout)

        try:
            request_headers = headers or {}
            request_kwargs: dict[str, Any] = {
                "method": method,
                "url": url,
                "headers": request_headers,
                "timeout": timeout,
            }

            if body:
                # Try to parse as JSON
                import json

                try:
                    request_kwargs["json"] = json.loads(body)
                except (json.JSONDecodeError, TypeError):
                    request_kwargs["content"] = body.encode("utf-8")

            with httpx.Client() as client:
                response = client.request(**request_kwargs)

            logger.info(
                "HTTP response: method=%s, url=%s, status=%d", method, url, response.status_code
            )

            result_parts = [
                f"HTTP {response.status_code} {response.http_version}",
                f"Method: {method}",
                f"URL: {url}",
                "\nResponse Headers:",
            ]

            for key, value in response.headers.items():
                result_parts.append(f"  {key}: {value}")

            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                result_parts.append(f"\nBody (JSON):\n{response.text[:5000]}")
            else:
                result_parts.append(f"\nBody:\n{response.text[:5000]}")

            if len(response.text) > 5000:
                result_parts.append(f"\n... (truncated, {len(response.text)} total chars)")

            return "\n".join(result_parts)

        except httpx.TimeoutException:
            logger.warning(
                "HTTP request timed out: method=%s, url=%s, timeout=%d", method, url, timeout
            )
            return f"Error: Request timed out after {timeout} seconds"
        except httpx.ConnectError as e:
            logger.error("HTTP connection failed: url=%s, error=%s", url, e)
            return f"Error: Could not connect to {url}: {e}"
        except Exception as e:
            logger.error("HTTP request failed: method=%s, url=%s, error=%s", method, url, e)
            return f"Error: {e}"

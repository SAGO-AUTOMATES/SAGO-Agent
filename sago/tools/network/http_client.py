"""HTTP Client Tool - Make HTTP requests to APIs.

Cross-platform HTTP client with method support.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class HTTPClientArgs(BaseModel):
    """Arguments for HTTPClientTool."""

    url: str = Field(description="URL to send request to")
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"] = Field(default="GET", description="HTTP method")
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

            result_parts = [
                f"HTTP {response.status_code} {response.http_version}",
                f"Method: {method}",
                f"URL: {url}",
                f"\nResponse Headers:",
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
            return f"Error: Request timed out after {timeout} seconds"
        except httpx.ConnectError as e:
            return f"Error: Could not connect to {url}: {e}"
        except Exception as e:
            return f"Error: {e}"

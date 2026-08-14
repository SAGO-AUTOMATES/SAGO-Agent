"""Retry logic with exponential backoff for LLM API calls."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)

TRANSIENT_ERRORS: tuple[type[Exception], ...] = ()

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


def _get_retryable_exception_types() -> tuple[type[Exception], ...]:
    """Lazily collect retryable exception types from installed SDKs."""
    global TRANSIENT_ERRORS
    if TRANSIENT_ERRORS:
        return TRANSIENT_ERRORS

    exc_types: list[type[Exception]] = []

    try:
        import openai

        exc_types.extend(
            [
                openai.RateLimitError,
                openai.APIConnectionError,
                openai.APITimeoutError,
                openai.InternalServerError,
                openai.APIStatusError,
            ]
        )
    except ImportError:
        pass

    try:
        import anthropic

        exc_types.extend(
            [
                anthropic.RateLimitError,
                anthropic.APIConnectionError,
                anthropic.APITimeoutError,
                anthropic.InternalServerError,
            ]
        )
    except ImportError:
        pass

    try:
        import httpx

        exc_types.extend([httpx.TimeoutException, httpx.ConnectError])
    except ImportError:
        pass

    TRANSIENT_ERRORS = tuple(exc_types)
    return TRANSIENT_ERRORS


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is transient and worth retrying."""
    retryable = _get_retryable_exception_types()

    if isinstance(exc, retryable):
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            return status_code in _RETRYABLE_STATUS_CODES
        return True

    if isinstance(exc, TimeoutError):
        return True

    return False


def retry_with_backoff(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs: Any,
) -> T:
    """Execute fn with retries and exponential backoff.

    Args:
        fn: Callable to execute.
        max_retries: Maximum retry attempts (0 = no retries).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.

    Returns:
        Result of fn(*args, **kwargs).

    Raises:
        The last exception if all retries fail.
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc

            if attempt >= max_retries or not _is_retryable(exc):
                raise

            delay = min(base_delay * (2**attempt), max_delay)

            if getattr(exc, "status_code", None) == 429:
                retry_after = getattr(exc, "headers", {}).get("retry-after")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except (ValueError, TypeError):
                        pass

            logger.warning(
                "LLM API call failed (attempt %d/%d): %s. Retrying in %.1fs",
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            time.sleep(delay)

    raise last_exc  # type: ignore[misc]
